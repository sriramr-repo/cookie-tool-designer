from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .models import TraceSettings


def image_from_bytes(data: bytes, filename: str) -> Image.Image:
    if filename.lower().endswith(".svg"):
        # resvg-py ships a platform wheel with its renderer included, avoiding
        # Cairo/Homebrew system-library dependencies on a fresh desktop.
        from resvg_py import svg_to_bytes
        data = svg_to_bytes(data.decode("utf-8"), width=1600, height=1600)
    return Image.open(io.BytesIO(data)).convert("RGBA")


def trace_image(image: Image.Image, settings: TraceSettings):
    """Return a cleaned mm-space polygon or multipolygon from visible pixels."""
    rgba = np.asarray(image)
    alpha = rgba[..., 3]
    rgb = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2GRAY)
    # Transparent pixels are background; use luminance for opaque artwork.
    binary = np.where(alpha < 20, 0, (rgb < settings.threshold).astype(np.uint8) * 255).astype(np.uint8)
    if settings.invert:
        binary = cv2.bitwise_not(binary)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        raise ValueError("No visible artwork could be traced. Increase contrast or adjust the threshold.")
    hierarchy = hierarchy[0]
    scale = settings.target_width_mm / max(image.width, 1)
    polys = []
    for i, contour in enumerate(contours):
        if hierarchy[i][3] != -1:
            continue
        exterior = [(float(x) * scale, float(image.height - y) * scale) for [[x, y]] in contour]
        holes = []
        child = hierarchy[i][2]
        while child != -1:
            hole = [(float(x) * scale, float(image.height - y) * scale) for [[x, y]] in contours[child]]
            if len(hole) >= 3:
                holes.append(hole)
            child = hierarchy[child][0]
        if len(exterior) >= 3:
            p = Polygon(exterior, holes).buffer(0)
            if not p.is_empty:
                polys.append(p)
    if not polys:
        raise ValueError("The trace did not produce a closed outline.")
    result = unary_union(polys).buffer(0)
    if settings.simplify_mm:
        result = result.simplify(settings.simplify_mm, preserve_topology=True).buffer(0)
    min_area = settings.min_feature_mm ** 2
    if result.geom_type == "MultiPolygon":
        result = unary_union([p for p in result.geoms if p.area >= min_area])
    if result.is_empty:
        raise ValueError("All traced features are smaller than the selected minimum feature size.")
    return result
