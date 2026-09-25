# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Local browser controls for the static battle viewers."""

import html
import json
import math
import sys
import tempfile
import traceback
from collections.abc import Callable, Iterable, Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from os import PathLike
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import battle2d, battle3d
from .image import load_rgb_palette, write_png
from .paths import Installation
from .script import load_battle

Query = dict[str, list[str]]  # urllib.parse.parse_qs result
Routes = dict[str, tuple[str, bytes]]  # path -> (content type, body)
Render = Callable[[Query], bytes]
Control = tuple[str, str, float, float, float, float]  # key, label, low, high, step, value
PathArg = str | PathLike[str]

HTML = "text/html; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
MINIMAP_WIDTH = 500
DISCONNECTED = (BrokenPipeError, ConnectionResetError)

STYLE = """body{background:#202228;color:#eee;font:14px sans-serif;margin:16px}
main{display:flex;gap:16px;align-items:flex-start}aside{width:250px;flex:none}section{min-width:0}
label,.field{display:block;margin:12px 0}output{float:right;color:#9de}input,select{width:100%}
#minimap{display:block;width:100%;height:auto;margin-top:4px;background:#415b70;cursor:crosshair}
#status{margin:0 0 8px;color:#9de;min-height:1.2em}#status.error{color:#ff8080;white-space:pre-wrap}
img{display:block;max-width:calc(100vw - 310px);max-height:calc(100vh - 70px)}"""

# Latest-wins rendering: at most one request is in flight, and only the newest parameters follow it.
CLIENT = """const inputs=[...document.querySelectorAll('aside input,aside select')];
const scene=document.getElementById('scene'),statusLine=document.getElementById('status');
let timer=null,pending=null,busy=false,objectUrl=null;
function query(){return new URLSearchParams(inputs.map(e=>[e.id,e.value])).toString()}
function setStatus(text,error){statusLine.textContent=text;statusLine.classList.toggle('error',!!error)}
function showValues(){for(const e of inputs){const o=document.getElementById(e.id+'-value');if(o)o.textContent=e.value}
if(window.onControls)window.onControls()}
async function pump(){
if(busy||pending===null)return;
const q=pending,started=performance.now();pending=null;busy=true;setStatus('Rendering\\u2026');
try{const response=await fetch('/render?'+q,{cache:'no-store'});
if(!response.ok)throw new Error('HTTP '+response.status+': '+(await response.text()).trim());
const blob=await response.blob();if(objectUrl)URL.revokeObjectURL(objectUrl);
objectUrl=URL.createObjectURL(blob);scene.src=objectUrl;
setStatus('Rendered in '+Math.round(performance.now()-started)+' ms')}
catch(error){setStatus(error.message,true)}
finally{busy=false;pump()}}
function requestNow(){showValues();clearTimeout(timer);pending=query();pump()}
function changed(){showValues();clearTimeout(timer);timer=setTimeout(()=>{pending=query();pump()},CONFIG.debounce)}
inputs.forEach(e=>{e.addEventListener('input',changed);e.addEventListener('change',changed)});
requestNow();"""

# The plan map is drawn with BTS Y growing upward; the camera eye sits at target + (sin yaw, cos yaw).
MINIMAP = """const map=document.getElementById('minimap'),g=map.getContext('2d');
const targetX=document.getElementById('target_x'),targetY=document.getElementById('target_y'),yaw=document.getElementById('yaw');
const plan=new Image();let planReady=false;plan.onload=()=>{planReady=true;drawMap()};plan.src='/planmap.png';
function toCanvas(x,y){return[x/CONFIG.field.width*map.width,(1-y/CONFIG.field.height)*map.height]}
function stroke(path,color,width){g.lineCap='round';g.beginPath();path();g.lineWidth=width+3;g.strokeStyle='#000';g.stroke();
g.beginPath();path();g.lineWidth=width;g.strokeStyle=color;g.stroke()}
function drawMap(){
g.fillStyle='#415b70';g.fillRect(0,0,map.width,map.height);if(planReady)g.drawImage(plan,0,0,map.width,map.height);
for(const unit of CONFIG.units){const[px,py]=toCanvas(unit.x,unit.y);g.beginPath();g.arc(px,py,6,0,2*Math.PI);
g.fillStyle=unit.player?'#4aa3ff':'#ff4a4a';g.fill();g.lineWidth=2;g.strokeStyle='#000';g.stroke()}
const[px,py]=toCanvas(+targetX.value,+targetY.value),angle=yaw.value*Math.PI/180;
const dx=-Math.sin(angle),dy=Math.cos(angle),length=60,hx=px+dx*length,hy=py+dy*length,head=Math.atan2(dy,dx);
stroke(()=>{g.moveTo(px,py);g.lineTo(hx,hy);for(const side of[-1,1]){g.moveTo(hx,hy);
g.lineTo(hx-16*Math.cos(head+side*.5),hy-16*Math.sin(head+side*.5))}},'#ffdf55',3);
stroke(()=>{g.moveTo(px-14,py);g.lineTo(px+14,py);g.moveTo(px,py-14);g.lineTo(px,py+14)},'#ffffff',3)}
window.onControls=drawMap;
map.addEventListener('click',e=>{const b=map.getBoundingClientRect(),clamp=v=>Math.max(0,Math.min(1,v));
targetX.value=clamp((e.clientX-b.left)/b.width)*CONFIG.field.width;
targetY.value=(1-clamp((e.clientY-b.top)/b.height))*CONFIG.field.height;requestNow()});"""


class BadRequest(ValueError):
    """Invalid query parameters; reported to the browser as HTTP 400."""


def _battle_path(game: Installation, battle_file: PathArg) -> Path:
    path = Path(battle_file)
    return path if path.is_file() else game.file_dir("SCRIPT", str(battle_file))


def _number(query: Query, key: str) -> float:
    try:
        value = float(query[key][0])
    except KeyError:
        raise BadRequest(f"missing parameter: {key}") from None
    except ValueError:
        raise BadRequest(f"{key} must be a number") from None
    if not math.isfinite(value):
        raise BadRequest(f"{key} must be finite")
    return value


def _controls(controls: Iterable[Control]) -> str:
    return "".join(
        f'<label>{html.escape(label)}<output id="{key}-value"></output>'
        f'<input id="{key}" type="range" min="{low}" max="{high}" step="{step}" value="{value}"></label>'
        for key, label, low, high, step, value in controls
    )


def _page(title: str, heading: str, controls: str, config: Mapping[str, Any], extra_script: str = "",
          image_style: str = "") -> str:
    script_config = json.dumps(config).replace("</", "<\\/")
    return f"""<!doctype html><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{STYLE}{image_style}</style>
<main><aside><h1>{html.escape(heading)}</h1>{controls}
<small>Rendered locally; game data stays on this computer.</small></aside>
<section><p id="status"></p><img id="scene" alt=""></section></main>
<script>const CONFIG={script_config};
{extra_script}
{CLIENT}</script>"""


def _units(battle: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Scripted unit positions in BTS world units; MRC regiments belong to the player."""
    armies = [(army, False) for army in battle["armies"]]
    armies += [(army, True) for army in (battle["merc"] or {}).get("armies", [])]
    return [{"x": unit["set"]["x"], "y": unit["set"]["y"], "player": player}
            for army, player in armies for unit in army["units"]
            if "x" in unit["set"] and "y" in unit["set"]]


def _planmap_png(game: Installation, field: Mapping[str, Any], path: Path) -> bytes | None:
    """Write the battle plan map (row 0 = highest BTS Y) as PNG bytes, or return None if unavailable."""
    try:
        width, height, indices = battle2d.load_planmap(game, field["planmap"] or "")
        palette = load_rgb_palette(game.binary_file("STANDARD.PAL"))
    except (FileNotFoundError, ValueError, IndexError) as error:
        print(f"Plan map unavailable: {error}", file=sys.stderr)
        return None
    write_png(path, width, height, b"".join(bytes(palette[index]) for index in indices))
    return path.read_bytes()


def _page_3d(battle: Mapping[str, Any]) -> str:
    field = battle["field"]
    camera = field.get("camera")
    # Hypothesis: Camera is the view heading clockwise from north; the eye sits opposite it.
    initial_yaw = (180 + camera) % 360 if camera is not None else battle3d.DEFAULT_YAW
    slider_controls = _controls((
        ("yaw", "Yaw", 0, 360, 1, initial_yaw),
        ("pitch", "Pitch", 5, 85, 1, battle3d.DEFAULT_PITCH),
        ("distance", "Distance", 20, 600, 1, battle3d.DEFAULT_DISTANCE),
        ("fov", "Vertical FOV", 20, 100, 1, battle3d.DEFAULT_FOV),
        ("zoom", "Orthographic zoom", .25, 8, .05, 1),
        ("scenery_scale", "Scenery scale", .5, 4, .05, 1),
        ("target_x", "Target X", 0, field["width"] * 1.25, 10, field["width"] / 2),
        ("target_y", "Target Y", 0, field["height"] * 1.25, 10, field["height"] / 2),
        ("ambient", "Ambient", 0, 1, .05, .45),
    ))
    minimap_height = round(MINIMAP_WIDTH * field["height"] / field["width"])
    controls = (
        '<label>Projection<select id="projection"><option value="orthographic">Orthographic</option>'
        '<option value="perspective">Perspective look-at</option></select></label>'
        '<div class="field">Ground target (click the plan map; arrow = look direction)'
        f'<canvas id="minimap" width="{MINIMAP_WIDTH}" height="{minimap_height}"></canvas></div>'
        + slider_controls
    )
    config = {"debounce": 180, "field": {"width": field["width"], "height": field["height"]},
              "units": _units(battle)}
    return _page("WHSHR battle viewer", "Battle camera", controls, config, MINIMAP)


def _parse_3d(query: Query, field: Mapping[str, Any]) -> dict[str, Any]:
    projection = query.get("projection", [""])[0]
    if projection not in battle3d.PROJECTIONS:
        raise BadRequest("projection must be orthographic or perspective")
    limits = {
        "yaw": (0, 360), "pitch": (5, 85), "distance": (20, 600), "fov": (20, 100), "zoom": (.25, 8),
        "scenery_scale": (.5, 4), "target_x": (0, field["width"] * 1.25),
        "target_y": (0, field["height"] * 1.25), "ambient": (0, 1),
    }
    values: dict[str, Any] = {key: _number(query, key) for key in limits}
    for key, (low, high) in limits.items():
        if not low <= values[key] <= high:
            raise BadRequest(f"{key} must be between {low:g} and {high:g}")
    values["projection"] = projection
    try:
        battle3d.validate_options(960, 680, values["yaw"], values["pitch"], values["zoom"], values["target_x"],
                                  values["target_y"], values["ambient"], battle3d.DEFAULT_LIGHT,
                                  values["scenery_scale"], projection, values["distance"], values["fov"])
    except ValueError as error:
        raise BadRequest(str(error)) from None
    return values


def _parse_2d(query: Query) -> dict[str, Any]:
    values: dict[str, Any] = {key: _number(query, key) for key in ("target_x", "target_y", "zoom", "spacing", "direction_offset")}
    if values["zoom"] <= 0:
        raise BadRequest("zoom must be greater than zero")
    if values["spacing"] <= 0:
        raise BadRequest("spacing must be greater than zero")
    if not values["direction_offset"].is_integer():
        raise BadRequest("direction_offset must be an integer")
    values["direction_offset"] = int(values["direction_offset"])
    return values


class _Server(HTTPServer):
    def handle_error(self, request: Any, client_address: Any) -> None:
        if not isinstance(sys.exc_info()[1], DISCONNECTED):
            super().handle_error(request, client_address)


class _Handler(BaseHTTPRequestHandler):
    """Serves fixed ``routes`` plus ``/render``, which calls ``render(query)`` for PNG bytes."""

    routes: Routes = {}

    @staticmethod
    def render(query: Query) -> bytes:
        raise NotImplementedError

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        request = urlparse(self.path)
        try:
            if request.path in self.routes:
                self._send(200, *self.routes[request.path])
            elif request.path != "/render":
                self._send(404, TEXT, b"not found")
            else:
                try:
                    body = self.render(parse_qs(request.query))
                except BadRequest as error:
                    self._send(400, TEXT, str(error).encode())
                except Exception as error:  # Report render failures to the page instead of dropping the socket.
                    traceback.print_exc()
                    self._send(500, TEXT, f"{type(error).__name__}: {error}".encode())
                else:
                    self._send(200, "image/png", body)
        except DISCONNECTED:
            pass

    def log_message(self, format: str, *args: Any) -> None:
        pass


def _serve(port: int, routes: Routes, render: Render, name: str) -> None:
    handler = type("Handler", (_Handler,), {"routes": routes, "render": staticmethod(render)})
    server = _Server(("127.0.0.1", port), handler)
    print(f"{name}: http://127.0.0.1:{port}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{name} stopped")
    finally:
        server.server_close()


def serve(installation: Installation | PathArg, battle_file: PathArg, port: int = 8765) -> None:
    """Serve a local slider UI for the 3D battle viewer until Ctrl+C."""
    game = installation if isinstance(installation, Installation) else Installation(installation)
    battle_path = _battle_path(game, battle_file)
    battle = load_battle(str(battle_path))
    field = battle["field"]
    if not field["width"] or not field["height"]:
        raise ValueError(f"{battle_path.name} has no battlefield dimensions")
    with tempfile.TemporaryDirectory(prefix="whshr-viewer-") as temporary:
        output = Path(temporary) / "scene.png"
        routes: Routes = {"/": (HTML, _page_3d(battle).encode())}
        planmap = _planmap_png(game, field, Path(temporary) / "planmap.png")
        if planmap is not None:
            routes["/planmap.png"] = ("image/png", planmap)

        def render(query: Query) -> bytes:
            values = _parse_3d(query, field)
            battle3d.render(
                game.root, battle_path, output, 960, 680, False, values["yaw"], values["pitch"],
                values["zoom"], values["target_x"], values["target_y"], values["ambient"],
                battle3d.DEFAULT_LIGHT, values["scenery_scale"], values["projection"], values["distance"],
                values["fov"],
            )
            return output.read_bytes()

        _serve(port, routes, render, "Battle viewer")


def serve_2d(installation: Installation | PathArg, battle_file: PathArg, port: int = 8765) -> None:
    """Serve local top-down game-view controls until Ctrl+C."""
    game = installation if isinstance(installation, Installation) else Installation(installation)
    battle_path = _battle_path(game, battle_file)
    battle = load_battle(str(battle_path))
    field = battle["field"]
    player = [unit for unit in _units(battle) if unit["player"]]
    target_x = sum(unit["x"] for unit in player) / len(player) if player else field["width"] / 2
    target_y = sum(unit["y"] for unit in player) / len(player) if player else field["height"] / 2
    controls = _controls((
        ("target_x", "Target X", 0, field["width"] * 1.25, 10, target_x),
        ("target_y", "Target Y", 0, field["height"] * 1.25, 10, target_y),
        ("zoom", "Zoom", .1, 2, .05, 1),
        ("spacing", "Formation spacing", 4, 64, 1, battle2d.DEFAULT_SPACING),
        ("direction_offset", "Sprite direction offset", 0, 7, 1, 0),
    ))
    page = _page("WHSHR 2D game view", "2D game view", controls, {"debounce": 120},
                 image_style="img{image-rendering:pixelated}")
    with tempfile.TemporaryDirectory(prefix="whshr-2d-viewer-") as temporary:
        output = Path(temporary) / "scene.png"

        def render(query: Query) -> bytes:
            values = _parse_2d(query)
            battle2d.render(game.root, battle_path, output, target_x=values["target_x"],
                            target_y=values["target_y"], zoom=values["zoom"], spacing=values["spacing"],
                            direction_offset=values["direction_offset"])
            return output.read_bytes()

        _serve(port, {"/": (HTML, page.encode())}, render, "2D game viewer")
