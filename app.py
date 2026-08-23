from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import streamlit as st

from core.image_processor import image_from_bytes, trace_image
from core.mesh import export_bytes, generate, glb_bytes
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

GENERATORS = ["Cookie cutter", "Imprint cutter", "Stamp", "Embosser", "Debosser", "Cutter + stamp", "Stencil", "Cake topper", "Sandwich sealer", "Multi-cutter", "Cake-pop mold"]
PROFILE_PRESETS = {
    "Anycubic Kobra S1": PrinterProfile(),
    "Generic FDM (0.4 mm)": PrinterProfile("Generic FDM (0.4 mm)", 0.4, 220, 220, 250, "PLA"),
}


def build_batch_zip(files, trace, tool, fmt: str) -> tuple[bytes, int, list[str]]:
    """Generate one export for each uploaded artwork using shared settings."""
    archive = io.BytesIO()
    errors: list[str] = []
    written = 0
    names_seen: set[str] = set()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in files:
            try:
                image = image_from_bytes(item.getvalue(), item.name)
                outline = trace_image(image, trace)
                model = generate(outline, tool)
                base = "".join(char if char.isalnum() or char in "-_" else "_" for char in Path(item.name).stem) or "design"
                filename = f"{base}.{fmt}"
                suffix = 2
                while filename in names_seen:
                    filename = f"{base}_{suffix}.{fmt}"
                    suffix += 1
                names_seen.add(filename)
                bundle.writestr(filename, export_bytes(model, fmt))
                written += 1
            except Exception as exc:
                errors.append(f"{item.name}: {exc}")
        if errors:
            bundle.writestr("batch-errors.txt", "\n".join(errors))
    return archive.getvalue(), written, errors


def workspace_canvas(model) -> str:
    """Return a self-contained local 3D viewport with inspection controls."""
    component_data = []
    component_count = max(1, len(model.components))
    per_component_limit = max(1200, 9000 // component_count)
    for name, component in model.components.items():
        faces = component.faces.tolist()
        if len(faces) > per_component_limit:
            faces = faces[::max(1, len(faces) // per_component_limit)]
        component_data.append({"name": name.replace("_", " ").title(), "vertices": component.vertices.round(4).tolist(), "faces": faces})
    payload = json.dumps({"components": component_data, "dimensions": model.mesh.extents.round(2).tolist()})
    template = """
<!doctype html><html><head><style>
* { box-sizing: border-box; } body { margin: 0; background: #fffafb; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
#stage { position: relative; height: 560px; overflow: hidden; border: 1px solid #e5cdd3; border-radius: 12px; background: radial-gradient(circle at 50% 35%, #fffdfd, #f9e9ed); }
canvas { width: 100%; height: 100%; display: block; cursor: grab; touch-action: none; } canvas:active { cursor: grabbing; }
.toolbar { position: absolute; top: 14px; left: 14px; z-index: 2; display: flex; gap: 7px; flex-wrap: wrap; max-width: 62%; } button, select { border: 1px solid #d9aeb9; border-radius: 7px; background: #fffdfd; color: #282d32; padding: 7px 10px; font-size: 13px; cursor: pointer; } button:hover, select:hover { background: #f6e5e9; }
.panel { position: absolute; top: 14px; right: 14px; z-index: 2; min-width: 155px; border: 1px solid #e5cdd3; border-radius: 8px; background: rgba(255,253,253,.94); padding: 10px; color: #66575b; font-size: 12px; } .panel strong { color: #282d32; display:block; margin-bottom:7px; } .panel label { display:block; margin:6px 0; cursor:pointer; } .panel input { accent-color:#d8a6b4; vertical-align:middle; }
.hint { position: absolute; bottom: 14px; left: 14px; z-index: 2; border-radius: 6px; background: rgba(255,253,253,.92); color: #66575b; padding: 6px 9px; font-size: 12px; } #dimensions { position:absolute; bottom:14px; right:14px; z-index:2; background:rgba(255,253,253,.92); border:1px solid #e5cdd3; border-radius:6px; padding:7px 9px; color:#66575b; font-size:12px; }
</style></head><body><div id="stage"><div class="toolbar"><button onclick="setView(0,0)">Front</button><button onclick="setView(0,-1.5708)">Side</button><button onclick="setView(-1.5708,0)">Top</button><button onclick="resetView()">Reset</button><select id="material" aria-label="Material appearance"><option value="Porcelain">Porcelain</option><option value="Clay">Clay</option><option value="Stone">Stone</option><option value="Graphite">Graphite</option></select><button id="edges">Edges: On</button><button id="dimensionsToggle">Dimensions: On</button></div><canvas id="canvas"></canvas><div id="components" class="panel"><strong>Components</strong></div><div class="hint">Drag to orbit · Shift + drag to pan · scroll to zoom</div><div id="dimensions">Dimensions</div></div><script>
const model = __MODEL__; const canvas = document.getElementById("canvas"), ctx = canvas.getContext("2d"), componentPanel=document.getElementById("components"), materialSelect=document.getElementById("material"), edgeButton=document.getElementById("edges"), dimensionToggle=document.getElementById("dimensionsToggle"), dimensionBox=document.getElementById("dimensions");
let rx=-0.55, ry=0.7, zoom=1, panX=0, panY=0, drag=null, edges=true, material="Porcelain", showDimensions=true;
const palettes={Porcelain:[226,211,215],Clay:[205,165,151],Stone:[171,168,163],Graphite:[88,91,95]};
const allVertices=model.components.flatMap(c=>c.vertices); const bounds=allVertices.reduce((out,p)=>[[Math.min(out[0][0],p[0]),Math.min(out[0][1],p[1]),Math.min(out[0][2],p[2])],[Math.max(out[1][0],p[0]),Math.max(out[1][1],p[1]),Math.max(out[1][2],p[2])]],[[Infinity,Infinity,Infinity],[-Infinity,-Infinity,-Infinity]]); const center=bounds[0].map((v,i)=>(v+bounds[1][i])/2); const extents=bounds[0].map((v,i)=>Math.max(1,(bounds[1][i]-v)/2)); const baseScale=195/Math.max(...extents), light=[.35,-.55,.75];
for(const component of model.components){const label=document.createElement("label"), box=document.createElement("input");box.type="checkbox";box.checked=true;box.addEventListener("change",render);label.append(box,document.createTextNode(" "+component.name));componentPanel.append(label);component.visible=box;}
function resize(){const r=canvas.getBoundingClientRect(),d=devicePixelRatio||1;canvas.width=r.width*d;canvas.height=r.height*d;ctx.setTransform(d,0,0,d,0,0);render();}
function rotate(p){const q=[p[0]-center[0],p[1]-center[1],p[2]-center[2]],cy=Math.cos(ry),sy=Math.sin(ry),cx=Math.cos(rx),sx=Math.sin(rx);const x=q[0]*cy-q[2]*sy,z=q[0]*sy+q[2]*cy;return[x,q[1]*cx-z*sx,q[1]*sx+z*cx];}
function project(p){const k=zoom*baseScale*650/(650-p[2]);return[canvas.clientWidth/2+panX+p[0]*k,canvas.clientHeight/2+panY-p[1]*k,p[2]];}
function render(){const w=canvas.clientWidth,h=canvas.clientHeight;ctx.clearRect(0,0,w,h);ctx.strokeStyle="#eddae0";ctx.lineWidth=1;for(let x=0;x<w;x+=30){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}for(let y=0;y<h;y+=30){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}const triangles=[];for(const component of model.components){if(!component.visible.checked)continue;const rotated=component.vertices.map(rotate);for(const f of component.faces){const a=rotated[f[0]],b=rotated[f[1]],c=rotated[f[2]],u=[b[0]-a[0],b[1]-a[1],b[2]-a[2]],v=[c[0]-a[0],c[1]-a[1],c[2]-a[2]],n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]],mag=Math.hypot(...n)||1,shade=Math.max(.28,Math.min(1,(n[0]*light[0]+n[1]*light[1]+n[2]*light[2])/mag*.45+.55));triangles.push({p:[project(a),project(b),project(c)],z:(a[2]+b[2]+c[2])/3,shade});}}triangles.sort((a,b)=>a.z-b.z);const color=palettes[material];for(const t of triangles){ctx.beginPath();ctx.moveTo(t.p[0][0],t.p[0][1]);ctx.lineTo(t.p[1][0],t.p[1][1]);ctx.lineTo(t.p[2][0],t.p[2][1]);ctx.closePath();ctx.fillStyle=`rgba(${color[0]},${color[1]},${color[2]},${.24+t.shade*.66})`;ctx.fill();if(edges){ctx.strokeStyle="rgba(141,92,106,.34)";ctx.stroke();}}dimensionBox.style.display=showDimensions?"block":"none";dimensionBox.textContent=`${model.dimensions[0]} × ${model.dimensions[1]} × ${model.dimensions[2]} mm`;}
function setView(x,y){rx=x;ry=y;panX=0;panY=0;render();}function resetView(){rx=-.55;ry=.7;zoom=1;panX=0;panY=0;render();}
materialSelect.addEventListener("change",e=>{material=e.target.value;render();});edgeButton.addEventListener("click",()=>{edges=!edges;edgeButton.textContent=`Edges: ${edges?"On":"Off"}`;render();});dimensionToggle.addEventListener("click",()=>{showDimensions=!showDimensions;dimensionToggle.textContent=`Dimensions: ${showDimensions?"On":"Off"}`;render();});
canvas.addEventListener("wheel",e=>{e.preventDefault();zoom=Math.max(.25,Math.min(5,zoom*(e.deltaY<0?1.06:.94)));render();},{passive:false});canvas.addEventListener("pointerdown",e=>{drag={x:e.clientX,y:e.clientY,rx,ry,panX,panY,pan:e.shiftKey||e.button===2};canvas.setPointerCapture(e.pointerId);});canvas.addEventListener("pointermove",e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(drag.pan){panX=drag.panX+dx;panY=drag.panY+dy;}else{ry=drag.ry-dx*.009;rx=Math.max(-1.52,Math.min(1.52,drag.rx+dy*.009));}render();});canvas.addEventListener("pointerup",()=>drag=null);canvas.addEventListener("contextmenu",e=>e.preventDefault());new ResizeObserver(resize).observe(canvas);resize();
</script></body></html>
"""
    return template.replace("__MODEL__", payload)


if "project" not in st.session_state:
    st.session_state.project = DesignProject()
if "source_data" not in st.session_state:
    st.session_state.source_data = None

# Migrate projects already held in this Streamlit session before bridge support was added.
if not hasattr(st.session_state.project.tool, "bridge_height_mm"):
    st.session_state.project.tool.bridge_height_mm = 1.2

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
    tool.generator = st.selectbox("Generator", GENERATORS, index=GENERATORS.index(tool.generator))
    tool.blade_height_mm = st.slider("Blade / body height (mm)", 2.0, 30.0, tool.blade_height_mm, 0.5)
    tool.blade_thickness_mm = st.slider("Wall thickness (mm)", 0.4, 4.0, tool.blade_thickness_mm, 0.1)
    if tool.generator in {"Cookie cutter", "Imprint cutter", "Cutter + stamp", "Sandwich sealer", "Multi-cutter"}:
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
    tool.center_bars = st.selectbox("Low-profile bridge placement", ["Auto", "None", "Horizontal", "Vertical"], index=["Auto", "None", "Horizontal", "Vertical"].index(tool.center_bars))
    tool.center_bar_width_mm = st.slider("Bridge width (mm)", 0.6, 4.0, tool.center_bar_width_mm, 0.1)
    if tool.center_bars != "None":
        tool.bridge_height_mm = st.slider("Bridge height (mm)", 0.4, 4.0, tool.bridge_height_mm, 0.1)
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
workspace_tools, workspace_stage, workspace_inspector = st.columns([1, 3, 1])
with workspace_tools:
    st.caption("TOOL SHELF")
    st.markdown(f"**{tool.generator}**")
    st.caption("Workplane")
    st.write(f"{trace.target_width_mm:.0f} mm wide")
    st.caption("Mode")
    st.write("Trace → tool")
with workspace_stage:
    st.components.v1.html(workspace_canvas(model), height=570, scrolling=False)
with workspace_inspector:
    st.caption("INSPECTOR")
    st.metric("Width", f"{mesh.extents[0]:.1f} mm")
    st.metric("Height", f"{mesh.extents[1]:.1f} mm")
    st.metric("Depth", f"{mesh.extents[2]:.1f} mm")
    st.caption(f"{len(model.components)} components")
    if model.bridge_analysis.required:
        st.caption(f"{model.bridge_analysis.bridge_count} support web(s) · {'connected' if model.bridge_analysis.connected else 'disconnected'}")

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
