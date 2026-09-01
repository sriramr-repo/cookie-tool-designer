"""Self-contained browser workspace renderer for the local Streamlit app."""

from __future__ import annotations

import json


def workspace_canvas(model, generator: str, target_width_mm: float) -> str:
    """Return a self-contained workspace with a clean, unobstructed 3D grid."""
    component_data = []
    component_count = max(1, len(model.components))
    per_component_limit = max(1200, 9000 // component_count)
    for name, component in model.components.items():
        faces = component.faces.tolist()
        if len(faces) > per_component_limit:
            faces = faces[::max(1, len(faces) // per_component_limit)]
        display_name = {"bridge": "Contour gussets", "manual bridge": "Manual contour gussets"}.get(name, name.replace("_", " ").title())
        component_data.append({"name": display_name, "vertices": component.vertices.round(4).tolist(), "faces": faces})
    support_summary = ""
    if model.bridge_analysis.required:
        support_summary = (
            f"{model.bridge_analysis.bridge_count} support web(s) across "
            f"{model.bridge_analysis.isolated_islands} floating island(s) · "
            f"{'connected' if model.bridge_analysis.connected else 'disconnected'}"
        )
    payload = json.dumps({
        "components": component_data,
        "dimensions": model.mesh.extents.round(2).tolist(),
        "generator": generator,
        "target_width": round(target_width_mm),
        "support_summary": support_summary,
        "web_summary": f"{model.bridge_analysis.automatic_web_count} automatic · {model.bridge_analysis.manual_web_count} manual" if model.bridge_analysis.required else "",
    })
    template = """
<!doctype html><html><head><style>
* { box-sizing: border-box; } body { margin: 0; background: #fffafb; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
#workspace { display:grid; grid-template-columns:180px minmax(360px,1fr) 215px; gap:18px; align-items:start; min-height:560px; }
.shelf, .inspector { color:#66575b; font-size:13px; padding:8px 2px; } .eyebrow { color:#8b7a7e; font-size:11px; letter-spacing:.06em; margin-bottom:16px; } .shelf strong { display:block; color:#282d32; font-size:16px; margin-bottom:24px; } .shelf .meta { line-height:1.45; margin:17px 0 23px; } .shelf .meta b { color:#66575b; font-weight:600; }
#stage { height:510px; overflow:hidden; border:1px solid #e5cdd3; border-radius:12px; background:radial-gradient(circle at 50% 35%,#fffdfd,#f9e9ed); } canvas { width:100%; height:100%; display:block; cursor:grab; touch-action:none; } canvas:active { cursor:grabbing; }
.toolbar { display:flex; gap:7px; flex-wrap:wrap; margin-top:12px; } button, select { border:1px solid #d9aeb9; border-radius:7px; background:#fffdfd; color:#282d32; padding:7px 10px; font-size:13px; cursor:pointer; } button:hover, select:hover { background:#f6e5e9; }
.panel { min-width:155px; border:1px solid #e5cdd3; border-radius:8px; background:rgba(255,253,253,.94); padding:10px; color:#66575b; font-size:12px; margin-top:22px; } .panel strong { color:#282d32; display:block; margin-bottom:7px; } .panel label { display:block; margin:6px 0; cursor:pointer; } .panel input { accent-color:#d8a6b4; vertical-align:middle; }
.metric { color:#75646a; margin:17px 0 6px; } .metric b { display:block; color:#66575b; font-size:25px; font-weight:500; margin-top:3px; } .summary { color:#75646a; line-height:1.45; margin-top:18px; }
.status { display:flex; justify-content:space-between; gap:8px; margin-top:10px; color:#66575b; font-size:12px; } .hint, #dimensions { border-radius:6px; background:rgba(255,253,253,.92); border:1px solid #e5cdd3; padding:7px 9px; } .hint { border-color:transparent; }
@media(max-width:760px) { #workspace { grid-template-columns:1fr; } #stage { height:460px; } .panel { margin-top:12px; } }
</style></head><body><div id="workspace"><section class="shelf"><div class="eyebrow">TOOL SHELF</div><strong id="toolTitle"></strong><div class="meta">Workplane<br><b id="workplane"></b></div><div class="meta">Mode<br><b>Trace → tool</b></div><div class="eyebrow" style="margin-top:30px">VIEW</div><div class="toolbar"><button onclick="setView(0,0)">Front</button><button onclick="setView(0,-1.5708)">Side</button><button onclick="setView(-1.5708,0)">Top</button><button onclick="resetView()">Reset</button><select id="material" aria-label="Material appearance"><option value="Porcelain">Porcelain</option><option value="Clay">Clay</option><option value="Stone">Stone</option><option value="Graphite">Graphite</option></select><button id="edges">Edges: On</button><button id="dimensionsToggle">Dimensions: On</button></div></section><section><div id="stage"><canvas id="canvas"></canvas></div><div class="status"><div class="hint">Drag to orbit · Shift + drag to pan · scroll to zoom</div><div id="dimensions">Dimensions</div></div></section><section class="inspector"><div class="eyebrow">INSPECTOR</div><div class="metric">Width<b id="widthMetric"></b></div><div class="metric">Height<b id="heightMetric"></b></div><div class="metric">Depth<b id="depthMetric"></b></div><div class="summary" id="componentCount"></div><div class="summary" id="supportSummary"></div><div class="summary" id="webSummary"></div><div id="components" class="panel"><strong>Components</strong></div></section></div><script>
const model = __MODEL__; const canvas = document.getElementById("canvas"), ctx = canvas.getContext("2d"), componentPanel=document.getElementById("components"), materialSelect=document.getElementById("material"), edgeButton=document.getElementById("edges"), dimensionToggle=document.getElementById("dimensionsToggle"), dimensionBox=document.getElementById("dimensions");
document.getElementById("toolTitle").textContent=model.generator; document.getElementById("workplane").textContent=`${model.target_width} mm wide`; document.getElementById("widthMetric").textContent=`${model.dimensions[0]} mm`; document.getElementById("heightMetric").textContent=`${model.dimensions[1]} mm`; document.getElementById("depthMetric").textContent=`${model.dimensions[2]} mm`; document.getElementById("componentCount").textContent=`${model.components.length} components`; document.getElementById("supportSummary").textContent=model.support_summary; document.getElementById("webSummary").textContent=model.web_summary;
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
