from __future__ import annotations

import json

import streamlit as st

from core.catalog import CUTTER_GENERATORS, GENERATORS
from core.exporters import build_batch_zip
from core.image_processor import image_from_bytes, trace_image
from core.mesh import export_bytes, generate, glb_bytes
from core.workspace import workspace_canvas
from core.models import DesignProject, PrinterProfile, ToolSettings, TraceSettings
from core.projects import list_projects, load_project, read_project_source, save_project
from core.validation import validate

st.set_page_config(page_title="Cookie Tool Designer", page_icon="🍪", layout="wide")

st.markdown("""
<style>
    :root { --pink-surface: #fff7f8; --pink-soft: #f6e5e9; --pink-border: #e5cdd3; --pink-strong: #e8c7d0; --ink: #282d32; }
    .stApp, [data-testid="stAppViewContainer"] { background: var(--pink-surface); color: var(--ink); }
    [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] { background: var(--pink-surface) !important; }
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child { background: var(--pink-soft) !important; border-right: 1px solid var(--pink-border); }
    h1, h2, h3, p, label, span, button, input { color: var(--ink) !important; }
    .stCaption, [data-testid="stMarkdownContainer"] p { color: #66575b !important; }
    .stButton > button, .stDownloadButton > button { background: var(--pink-strong) !important; color: var(--ink) !important; border: 1px solid #d9aeb9 !important; border-radius: 7px; font-weight: 600; }
    .stButton > button:hover, .stDownloadButton > button:hover { background: #f2d8de !important; border-color: #c995a3 !important; }
    .stButton > button:focus, .stDownloadButton > button:focus, input:focus { box-shadow: 0 0 0 0.2rem rgba(229, 174, 188, 0.38) !important; }
    [data-baseweb="select"] > div, [data-baseweb="input"] > div, [data-baseweb="base-input"] { background: #fffafb !important; border-color: var(--pink-border) !important; }
    [data-testid="stFileUploader"], [data-testid="stFileUploaderDropzone"], [data-testid="stFileUploaderDropzone"] > div { background: #fff0f3 !important; border-color: #d9aeb9 !important; color: var(--ink) !important; border-radius: 10px; }
    [data-testid="stAlert"] { background: #fff0f3 !important; border: 1px solid var(--pink-border) !important; border-radius: 8px; color: var(--ink) !important; }
    [data-testid="stAlert"] * { color: var(--ink) !important; }
    /* Streamlit base-web controls render their own inner surfaces. */
    [data-testid="stTextInput"] input, [data-testid="stTextInput"] input:focus, div[data-baseweb="input"], div[data-baseweb="input"] > div { background: #fffafb !important; color: var(--ink) !important; -webkit-text-fill-color: var(--ink) !important; border-color: var(--pink-border) !important; }
    [data-testid="stTextInput"] input:focus { border-color: #d9aeb9 !important; box-shadow: 0 0 0 0.2rem rgba(229, 174, 188, 0.38) !important; }
    [data-testid="stFileUploader"] button, [data-testid="stFileUploaderDropzone"] button { background: #e8c7d0 !important; color: var(--ink) !important; border: 1px solid #d9aeb9 !important; }
    [data-testid="stFileUploader"] button:hover, [data-testid="stFileUploaderDropzone"] button:hover { background: #f2d8de !important; border-color: #c995a3 !important; }
    [data-testid="stFileUploader"] button svg, [data-testid="stFileUploaderDropzone"] button svg { fill: var(--ink) !important; color: var(--ink) !important; }
    [data-testid="stAlert"] > div, [data-testid="stAlert"] > div > div { background: #fff0f3 !important; border-color: var(--pink-border) !important; }
    /* Select boxes and number steppers use separate BaseWeb surfaces. */
    [data-testid="stSelectbox"] [data-baseweb="select"] > div, [data-testid="stSelectbox"] [data-baseweb="select"] > div > div, [data-testid="stSelectbox"] [role="combobox"], [data-testid="stNumberInput"] input, [data-testid="stNumberInput"] [data-baseweb="input"] > div, [data-testid="stNumberInput"] [data-baseweb="input"] > div > div { background-color: #fffafb !important; background: #fffafb !important; color: var(--ink) !important; -webkit-text-fill-color: var(--ink) !important; border-color: var(--pink-border) !important; }
    [data-testid="stSelectbox"] svg, [data-testid="stNumberInput"] svg, [data-testid="stNumberInput"] button { color: var(--ink) !important; fill: var(--ink) !important; background: #fff0f3 !important; }
    [data-baseweb="popover"], [data-baseweb="menu"], ul[role="listbox"], ul[role="listbox"] li { background: #fff0f3 !important; color: var(--ink) !important; }
    [data-testid="stImage"] button, button[title*="fullscreen" i], button[title*="Fullscreen" i] { background: #e8c7d0 !important; border-color: #d9aeb9 !important; color: var(--ink) !important; }
    [data-testid="stImage"] button svg, button[title*="fullscreen" i] svg, button[title*="Fullscreen" i] svg { color: var(--ink) !important; fill: var(--ink) !important; }
    /* Minimal select indicator: remove Streamlit's dark default well. */
    [data-testid="stSelectbox"] [data-baseweb="select"] > div > div:last-child, [data-testid="stSelectbox"] [data-baseweb="select"] > div > div:last-child > div { background: #f6e5e9 !important; background-color: #f6e5e9 !important; border-left: 1px solid #e5cdd3 !important; }
    [data-testid="stSelectbox"] [data-baseweb="select"] > div > div:last-child * { background: transparent !important; color: var(--ink) !important; fill: var(--ink) !important; }
    [data-testid="stSelectbox"] [data-baseweb="select"] > div > div:last-child:hover { background: #f2d8de !important; }
    [data-testid="stNumberInput"] button { background: #f6e5e9 !important; border-left: 1px solid #e5cdd3 !important; }
    /* Closed selects: neutralize every nested Streamlit/BaseWeb surface. */
    [data-testid="stSelectbox"] [data-baseweb="select"], [data-testid="stSelectbox"] [data-baseweb="select"] div { background-color: #fffafb !important; background-image: none !important; }
    [data-testid="stSelectbox"] [data-baseweb="select"] div:has(> svg) { background-color: #f6e5e9 !important; }
    [data-testid="stSelectbox"] [data-baseweb="select"] svg { color: var(--ink) !important; fill: var(--ink) !important; stroke: var(--ink) !important; }
    /* Image fullscreen controls, including the expanded-view exit action. */
    [data-testid="stElementToolbar"] button, [data-testid="stFullScreenFrame"] button, button[aria-label*="fullscreen" i], button[title*="fullscreen" i] { background: #e8c7d0 !important; background-color: #e8c7d0 !important; color: var(--ink) !important; border: 1px solid #d9aeb9 !important; border-radius: 7px !important; box-shadow: 0 2px 8px rgba(92, 49, 61, 0.16) !important; opacity: 1 !important; }
    [data-testid="stElementToolbar"] button:hover, [data-testid="stFullScreenFrame"] button:hover, button[aria-label*="fullscreen" i]:hover, button[title*="fullscreen" i]:hover { background: #f2d8de !important; border-color: #c995a3 !important; }
    [data-testid="stElementToolbar"] button svg, [data-testid="stFullScreenFrame"] button svg, button[aria-label*="fullscreen" i] svg, button[title*="fullscreen" i] svg { color: var(--ink) !important; fill: var(--ink) !important; stroke: var(--ink) !important; opacity: 1 !important; }
    /* Fullscreen controls only: soft-pink icon, no gunmetal. */
    [data-testid="stElementToolbar"] button svg, [data-testid="stFullScreenFrame"] button svg, button[aria-label*="fullscreen" i] svg, button[title*="fullscreen" i] svg { color: #d8a6b4 !important; fill: #d8a6b4 !important; stroke: #d8a6b4 !important; }
</style>
""", unsafe_allow_html=True)
st.title("Cookie Tool Designer")
st.caption("A private local artwork-to-3D-printable-tool utility. No accounts or cloud services.")

PROFILE_PRESETS = {
    "Anycubic Kobra S1": PrinterProfile(),
    "Generic FDM (0.4 mm)": PrinterProfile("Generic FDM (0.4 mm)", 0.4, 220, 220, 250, "PLA"),
}




if "project" not in st.session_state:
    st.session_state.project = DesignProject()
if "source_data" not in st.session_state:
    st.session_state.source_data = None

# Migrate projects already held in this Streamlit session as settings evolve.
for _field, _default in {
    "bridge_height_mm": 1.2,
    "min_webs_per_island": 2,
    "max_unsupported_span_mm": 20.0,
    "support_web_mode": "Auto",
    "manual_webs": [],
}.items():
    if not hasattr(st.session_state.project.tool, _field):
        setattr(st.session_state.project.tool, _field, _default)


def _sync_generator() -> None:
    """Keep the selected generator and project model in lockstep on every rerun."""
    st.session_state.project.tool.generator = st.session_state.tool_generator


with st.sidebar:
    st.header("Project")
    project = st.session_state.project
    project.name = st.text_input("Project name", project.name)
    saved = list_projects()
    if saved:
        selected = st.selectbox("Recent projects", ["— Open a project —"] + [p.parent.name for p in saved])
        if selected != "— Open a project —" and st.button("Open selected"):
            chosen = next(p for p in saved if p.parent.name == selected)
            st.session_state.project = load_project(chosen)
            st.session_state.source_data = read_project_source(chosen)
            # The selector is a persistent widget; explicitly hydrate it for a
            # different project before the next render.
            st.session_state.tool_generator = st.session_state.project.tool.generator
            st.session_state._generator_project_identity = id(st.session_state.project)
            st.rerun()
    if st.button("Save project"):
        try:
            path = save_project(project, st.session_state.source_data)
            st.success(f"Saved locally to {path}")
        except Exception as exc:
            st.error(str(exc))

uploaded_files = st.file_uploader(
    "Upload PNG, JPG, WebP, or SVG",
    type=["png", "jpg", "jpeg", "webp", "svg"],
    accept_multiple_files=True,
)
uploaded = None
if uploaded_files:
    names = [item.name for item in uploaded_files]
    active_name = st.selectbox("Active artwork", names, key="active_uploaded_artwork")
    uploaded = next(item for item in uploaded_files if item.name == active_name)

if uploaded is not None:
    data = uploaded.getvalue()
    project.source_filename = uploaded.name
    st.session_state.source_data = data
elif st.session_state.source_data and project.source_filename:
    data = st.session_state.source_data
else:
    st.info("Upload high-contrast artwork to begin. Simple drawings and logos produce the cleanest trace.")
    st.stop()

try:
    image = image_from_bytes(data, project.source_filename or "source.png")
except Exception as exc:
    st.error(f"Could not read artwork: {exc}")
    st.stop()

left, middle, right = st.columns([1, 1, 1.35])
with left:
    st.subheader("Trace")
    trace = project.trace
    trace.target_width_mm = st.slider("Target width (mm)", 20.0, 220.0, trace.target_width_mm, 1.0)
    trace.threshold = st.slider("Threshold", 0, 255, trace.threshold)
    trace.invert = st.toggle("Invert artwork", trace.invert)
    trace.simplify_mm = st.slider("Contour resolution (mm)", 0.02, 1.0, trace.simplify_mm, 0.01)
    trace.min_feature_mm = st.slider("Minimum feature (mm)", 0.2, 2.0, trace.min_feature_mm, 0.05)
    st.caption("These are master trace settings. Batch export applies them to every uploaded artwork.")
    st.image(image, caption="Source artwork", use_container_width=True)

with middle:
    st.subheader("Tool")
    tool = project.tool
    # Rehydrate the persistent selector when projects change, preventing a
    # previous project's widget state from overriding the new generator.
    if st.session_state.get("_generator_project_identity") != id(project):
        st.session_state.tool_generator = tool.generator
        st.session_state._generator_project_identity = id(project)
    tool.generator = st.selectbox(
        "Generator", GENERATORS, key="tool_generator", on_change=_sync_generator
    )
    tool.blade_height_mm = st.slider("Blade / body height (mm)", 2.0, 30.0, tool.blade_height_mm, 0.5)
    tool.blade_thickness_mm = st.slider("Wall thickness (mm)", 0.4, 4.0, tool.blade_thickness_mm, 0.1)
    if tool.generator in CUTTER_GENERATORS:
        tool.sharp_tip = st.toggle("Sharp cutting tip", tool.sharp_tip)
        if tool.sharp_tip:
            tool.tip_width_mm = st.slider("Tip width (mm)", 0.2, 1.5, tool.tip_width_mm, 0.05)
            tool.chamfer_height_mm = st.slider("Chamfer height (mm)", 0.5, 6.0, tool.chamfer_height_mm, 0.25)
        tool.support_blade = st.toggle("Secondary support blade", tool.support_blade)
        tool.handle_height_mm = st.slider("Handle height (mm)", 1.0, 12.0, tool.handle_height_mm, 0.5)
        tool.handle_width_mm = st.slider("Handle width (mm)", 1.0, 8.0, tool.handle_width_mm, 0.5)
        tool.handle_shape = st.selectbox("Handle shape", ["Rounded", "Chamfered", "Rectangular"], index=["Rounded", "Chamfered", "Rectangular"].index(tool.handle_shape))
    if tool.generator in {"Imprint cutter", "Stamp", "Embosser", "Debosser", "Cutter + stamp"}:
        tool.imprint_depth_mm = st.slider("Imprint depth (mm)", 0.5, 6.0, tool.imprint_depth_mm, 0.25)
        tool.imprint_thickness_mm = st.slider("Imprint thickness (mm)", 0.4, 3.0, tool.imprint_thickness_mm, 0.1)
        tool.relief_height_mm = st.slider("Stamp relief (mm)", 0.5, 8.0, tool.relief_height_mm, 0.25)
    if tool.generator in CUTTER_GENERATORS:
        tool.center_bars = st.selectbox(
            "Low-profile bridge placement", ["Auto", "None", "Horizontal", "Vertical"],
            index=["Auto", "None", "Horizontal", "Vertical"].index(tool.center_bars),
        )
        if tool.center_bars != "None":
            tool.center_bar_width_mm = st.slider("Bridge width (mm)", 0.6, 4.0, tool.center_bar_width_mm, 0.1)
            tool.bridge_height_mm = st.slider("Bridge height (mm)", 0.4, 4.0, tool.bridge_height_mm, 0.1)
            tool.min_webs_per_island = st.slider("Minimum webs per floating island", 2, 4, tool.min_webs_per_island)
            tool.max_unsupported_span_mm = st.slider("Maximum unsupported span (mm)", 8.0, 40.0, tool.max_unsupported_span_mm, 1.0)
            tool.support_web_mode = st.selectbox(
                "Support-web mode", ["Auto", "Manual", "Auto + manual"],
                index=["Auto", "Manual", "Auto + manual"].index(tool.support_web_mode),
            )
            st.caption("Auto reinforces weak regions. Manual mode exports only when every floating island has enough snapped web attachments.")
            if tool.support_web_mode in {"Manual", "Auto + manual"}:
                st.caption("Add a snapped manual web by choosing a floating-island number and attachment region. Island numbers are shown in the support-web review below.")
                manual_island = st.number_input("Floating island number", min_value=1, max_value=24, value=1, step=1)
                manual_region = st.selectbox("Manual attachment region", ["Top", "Right", "Bottom", "Left"])
                if st.button("Add manual support web"):
                    spec = {"island": int(manual_island), "region": manual_region}
                    if spec not in tool.manual_webs:
                        tool.manual_webs.append(spec)
                    st.rerun()
                if tool.manual_webs:
                    st.caption("Manual web requests")
                    for _index, _spec in enumerate(tool.manual_webs):
                        _col_label, _col_remove = st.columns([4, 1])
                        _col_label.caption(f"Island {_spec.get('island', '?')} · {_spec.get('region', 'Top')}")
                        if _col_remove.button("Remove", key=f"remove_manual_web_{_index}"):
                            tool.manual_webs.pop(_index)
                            st.rerun()
    tool.mirror = st.toggle("Mirror design", tool.mirror)

with right:
    st.subheader("Printer validation")
    preset = st.selectbox("Profile", list(PROFILE_PRESETS), index=list(PROFILE_PRESETS).index(project.printer.name) if project.printer.name in PROFILE_PRESETS else 0)
    if preset != project.printer.name:
        project.printer = PROFILE_PRESETS[preset]
    printer = project.printer
    printer.nozzle_mm = st.selectbox("Nozzle (mm)", [0.25, 0.4, 0.6, 0.8], index=[0.25, 0.4, 0.6, 0.8].index(printer.nozzle_mm) if printer.nozzle_mm in [0.25, 0.4, 0.6, 0.8] else 1)
    printer.material = st.selectbox("Material", ["PLA", "PETG", "TPU"], index=["PLA", "PETG", "TPU"].index(printer.material) if printer.material in ["PLA", "PETG", "TPU"] else 0)
    printer.build_x_mm = st.number_input("Build X (mm)", 50.0, 500.0, float(printer.build_x_mm))
    printer.build_y_mm = st.number_input("Build Y (mm)", 50.0, 500.0, float(printer.build_y_mm))
    printer.build_z_mm = st.number_input("Build Z (mm)", 20.0, 500.0, float(printer.build_z_mm))

try:
    outline = trace_image(image, trace)
    model = generate(outline, tool)
    mesh = model.mesh
except Exception as exc:
    st.error(f"Generation failed: {exc}")
    st.stop()

st.subheader("Workspace")
st.components.v1.html(workspace_canvas(model, tool.generator, trace.target_width_mm), height=600, scrolling=False)

st.subheader("3D preview")
st.caption(f"{len(model.components)} components · {mesh.extents[0]:.1f} × {mesh.extents[1]:.1f} × {mesh.extents[2]:.1f} mm")
try:
    st.download_button("Download preview (GLB)", glb_bytes(model), "preview.glb", "model/gltf-binary")
except Exception:
    pass
st.info("Interactive mesh preview is available through the downloaded GLB in any local 3D viewer. The browser view is intentionally lightweight.")

for level, message in validate(mesh, tool, printer, model.bridge_analysis, model.export_error):
    getattr(st, level)(message)

st.subheader("Export")
cols = st.columns(4)
for col, fmt, mime in zip(cols, ["stl", "obj", "3mf"], ["model/stl", "text/plain", "model/3mf"]):
    with col:
        try:
            st.download_button(f"Download {fmt.upper()}", export_bytes(model, fmt), f"{project.name}.{fmt}", mime)
        except Exception as exc:
            st.caption(f"{fmt.upper()} unavailable: {exc}")
with cols[3]:
    st.download_button("Download SVG", outline.svg().encode(), f"{project.name}.svg", "image/svg+xml")

if len(uploaded_files or []) > 1:
    st.subheader("Batch export")
    st.caption("Every uploaded artwork uses the master trace and tool settings above.")
    batch_format = st.selectbox("Batch export format", ["stl", "obj", "3mf"], key="batch_export_format")
    zip_data, completed, batch_errors = build_batch_zip(uploaded_files, trace, tool, batch_format)
    batch_name = project.name or "cookie-tools"
    st.download_button(
        f"Download ZIP ({completed} designs)",
        zip_data,
        f"{batch_name}-batch.zip",
        "application/zip",
        disabled=completed == 0,
    )
    if batch_errors:
        st.warning(f"{len(batch_errors)} file(s) could not be generated. Details are included in batch-errors.txt inside the ZIP.")

if model.bridge_analysis.required:
    st.subheader("Support-web review")
    if model.bridge_analysis.webs:
        for _web in model.bridge_analysis.webs:
            _source = f"({_web.source[0]:.1f}, {_web.source[1]:.1f})"
            _target = f"({_web.target[0]:.1f}, {_web.target[1]:.1f})"
            st.caption(f"Island {_web.island_index} · {'Manual' if _web.manual else 'Automatic'} · {_web.reason} · {_source} → {_target}")
    if model.bridge_analysis.unresolved_reasons:
        for _reason in model.bridge_analysis.unresolved_reasons:
            st.warning("Flush support unresolved: " + _reason)
    elif model.bridge_analysis.under_supported_islands:
        st.warning("Floating island(s) " + ", ".join(map(str, model.bridge_analysis.under_supported_islands)) + " need more support webs before export.")
