# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Battle view: terrain, scenery and troop sprite billboards on the GPU, with a free battle camera.

Controls: arrow keys or WASD pan, Q/E rotate, Page Up/Page Down tilt, mouse wheel zooms, middle-drag
rotates, Home resets the camera. Left-click any regiment (player or enemy) to select it - a player
regiment tints yellow and can then be given orders (via the HUD's Move/Attack/Fire buttons, or the
right-click shortcut below); an enemy regiment only shows its HUD readout/banner/minimap highlight,
never orders, since whshr.engine.Battle's player order guards and
Hud._button_enabled() both refuse commands for a non-player regiment. Right-drag pans the camera;
a right-button press and release without dragging is instead a direct move/attack shortcut for the
current selection, bypassing the HUD buttons. Escape deselects.
"""

from collections import deque
from array import array
from collections.abc import Sequence
from dataclasses import replace
import math
import struct
from typing import Any

import pygame
import zengl

from .. import animation, figure_capture, picking
from ..battle3d import SPRITE_DEPTH_BIAS
from ..battlefield import VERTEX_FLOATS, VERTEX_FORMAT, WORLD_PER_MESH, bake_mesh, sprite_direction, view_angle
from ..camera import BattleCamera
from ..formation import SPRITE_PIXEL_WORLD_UNITS
from ..rules import Side
from ..battle_scene import BattleScene
from ..battle3d import Projection
from ..battlefield import SpriteSheet
from ..scenes import SceneEvent
from .cursors import GameCursors
from .battle_text import display_text, reaction_text
from .battle_sound import BattleSounds
from .ranged_sound import MissileSounds
from .gpu import Gpu
from .scene_view import SceneView
from .hud import Hud

Point = tuple[int, int]
SKY = (112, 150, 196)
NEAR, FAR = 0.5, 4000.0  # mesh units
PAN_SPEED = 0.8  # camera distances per second
ROTATE_SPEED = 90.0  # degrees per second
TILT_SPEED = 30.0  # degrees per second
WHEEL_ZOOM = 0.9
DRAG_ROTATE = 0.3  # degrees per pixel
CLICK_DRAG_THRESHOLD = 4  # pixels; a right button press/release closer than this counts as a click
# Public ranged handoff §5: installed GMCUR groups are Fire 100, default 101, Attack 102, Magic 103.
BATTLE_CURSOR_GROUPS: dict[str, int] = {"default": 101, "attack": 102, "fire": 100, "magic": 103}
MISSILE_MESH = {"arrow": "arrows1", "arrow_alt": "arrows2", "bolt": "arrows3",
                "cannon": "spear1", "mortar": "spear2", "rock": "spear3",
                "diver": "spear4", "bomb": "flames1"}
BANNER_MARKER_RAISE = 4.0  # mesh units: above a 64-pixel troop sprite, below the camera's horizon
SPRITE_MID_HEIGHT = BANNER_MARKER_RAISE / 2  # mesh units: halfway up that ~64px sprite, for picking
EVENT_LOG_LINES = 3  # battle events shown in the debug overlay (whshr.engine.Battle.events, per tick)
INSTANCE = struct.Struct("10f")  # foot position (mesh), atlas rectangle (pixels), anchor (pixels), selected
CAMERA = struct.Struct("24f")

CAMERA_BLOCK = """
layout (std140) uniform Camera {
    vec4 eye;
    vec4 right;
    vec4 up;
    vec4 forward;
    vec4 projection;  // x scale, y scale, near, far
    vec4 sprite;      // mesh units per sprite pixel, depth bias toward the camera
};

// World data is left-handed (+X east, +Y up, +Z north); view space is right, up and forward depth.
vec3 to_view(vec3 position) {
    vec3 relative = position - eye.xyz;
    return vec3(dot(relative, right.xyz), dot(relative, up.xyz), dot(relative, forward.xyz));
}

vec4 to_clip(vec3 view) {
    float near = projection.z;
    float far = projection.w;
    return vec4(view.x * projection.x, view.y * projection.y,
                (view.z * (far + near) - 2.0 * far * near) / (far - near), view.z);
}
"""

MESH_VERTEX_SHADER = """
#version 330 core
#include "camera"

layout (location = 0) in vec3 in_position;
layout (location = 1) in vec2 in_uv;
layout (location = 2) in float in_layer;
layout (location = 3) in float in_shade;

out vec3 v_uv;
out float v_shade;

void main() {
    gl_Position = to_clip(to_view(in_position));
    v_uv = vec3(in_uv, in_layer);
    v_shade = in_shade;
}
"""

MESH_FRAGMENT_SHADER = """
#version 330 core

uniform sampler2DArray textures;

in vec3 v_uv;
in float v_shade;
out vec4 frag_color;

void main() {
    vec4 color = texture(textures, v_uv);
    if (color.a < 0.5) {
        discard;
    }
    frag_color = vec4(min(color.rgb * v_shade, vec3(1.0)), 1.0);
}
"""

SPRITE_VERTEX_SHADER = """
#version 330 core
#include "camera"

layout (location = 0) in vec3 in_foot;
layout (location = 1) in vec4 in_rect;
layout (location = 2) in vec2 in_anchor;
layout (location = 3) in float in_selected;

out vec2 v_texel;
out float v_selected;

const vec2 corners[4] = vec2[](vec2(0.0, 0.0), vec2(1.0, 0.0), vec2(0.0, 1.0), vec2(1.0, 1.0));

void main() {
    vec2 corner = corners[gl_VertexID];
    // Upright billboard parallel to the screen; sprite rows grow downward from the foot anchor.
    vec2 pixel = corner * in_rect.zw - in_anchor;
    vec3 view = to_view(in_foot);
    view.xy += vec2(pixel.x, -pixel.y) * sprite.x;
    gl_Position = to_clip(view);
    // Depth-test the whole sprite at its foot moved toward the camera, so the ground under it does not clip it.
    vec4 biased = to_clip(vec3(view.xy, max(view.z - sprite.y, projection.z)));
    gl_Position.z = biased.z / biased.w * gl_Position.w;
    v_texel = in_rect.xy + corner * in_rect.zw;
    v_selected = in_selected;
}
"""

SPRITE_FRAGMENT_SHADER = """
#version 330 core

uniform sampler2D atlas;
uniform sampler2D palette;

in vec2 v_texel;
in float v_selected;
out vec4 frag_color;

void main() {
    int index = int(texelFetch(atlas, ivec2(v_texel), 0).r * 255.0 + 0.5);
    if (index == 0) {
        discard;
    }
    vec3 color = texelFetch(palette, ivec2(index, 0), 0).rgb;
    color = mix(color, vec3(1.0, 0.95, 0.3), v_selected * 0.5);
    frag_color = vec4(color, 1.0);
}
"""


def _atlas_rect(sheet: SpriteSheet, index: int) -> tuple[int, int, int, int]:
    """The atlas rectangle of one packed frame (every sheet drawn here went through `build_atlas`)."""
    rect = sheet.rects[index]
    if rect is None:
        raise ValueError(f"frame {index} of {sheet.name} has no atlas rectangle")
    return rect


# Snow scenery that selects the sparkle marker's second variant (notes/battle_end_objectives.md 12.2).
SNOW_FURNITURE = frozenset({"d_snwwatchtower", "snwrock1", "snwrock2", "snwrock3", "snwrock4"})


class BattleView(SceneView[BattleScene]):
    background = SKY

    def __init__(self, gpu: Gpu, scene: BattleScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        field, ctx, target = scene.field, gpu.ctx, gpu.target
        self.initial_camera = BattleCamera.for_battle(field.script, field.ground_height)
        if self.options.get("camera"):
            yaw, pitch, distance = self.options["camera"]
            self.initial_camera = replace(self.initial_camera, yaw=yaw % 360, pitch=pitch, distance=distance)
            self.initial_camera.set_target(self.initial_camera.target_x, self.initial_camera.target_y)
        self.camera = replace(self.initial_camera)
        self.soldiers = 0
        self._right_down: Point | None = None  # screen position of an unreleased right-button press, for click detection
        self.order_mode: str | None = None  # a HUD Move/Attack click changes how the next battlefield click is interpreted
        self._drag_surface: str | None = None
        self._drag_pixel: tuple[float, float] | None = None
        self._right_minimap = False
        self.event_log: deque[str] = deque(maxlen=EVENT_LOG_LINES)  # recent whshr.engine.Battle.events, newest last
        self._banner_order: list[str] = []  # promoted selection order; persists after deselect like the original battle view
        self.battle_log: deque[tuple[str, str]] = deque(maxlen=100)  # full react-message history for the HUD log panel
        self.log_scroll = 0  # lines scrolled back from the newest entry (0 = show latest)

        ctx.includes["camera"] = CAMERA_BLOCK
        self.camera_buffer = ctx.buffer(size=CAMERA.size, uniform=True)
        self.vertex_buffer = ctx.buffer(field.vertices.tobytes())
        self.textures = ctx.image(field.texture_size, "rgba8unorm", b"".join(field.texture_layers),
                                  array=len(field.texture_layers))
        self.atlas = ctx.image(field.atlas_size, "r8unorm", field.atlas)
        self.palette = ctx.image((256, 1), "rgba8unorm", b"".join(bytes((*rgb, 255)) for rgb in field.palette))
        self.capacity = max(1, sum(regiment.models for regiment in scene.battle.regiments.values())
                            + len(scene.battle.regiments))
        self.instance_buffer = ctx.buffer(size=self.capacity * INSTANCE.size)

        camera_layout: Any = {"name": "Camera", "binding": 0}
        camera_resource: Any = {"type": "uniform_buffer", "binding": 0, "buffer": self.camera_buffer}
        nearest: Any = {"min_filter": "nearest", "mag_filter": "nearest"}
        depth: Any = {"func": "less", "write": True}
        mesh_resources: list[Any] = [camera_resource, {"type": "sampler", "binding": 0, "image": self.textures,
                                                        **nearest, "wrap_x": "repeat", "wrap_y": "repeat"}]
        self.mesh = ctx.pipeline(
            vertex_shader=MESH_VERTEX_SHADER, fragment_shader=MESH_FRAGMENT_SHADER,
            layout=[camera_layout, {"name": "textures", "binding": 0}],
            resources=mesh_resources,
            depth=depth, framebuffer=[target.color, target.depth],
            vertex_buffers=zengl.bind(self.vertex_buffer, VERTEX_FORMAT, 0, 1, 2, 3),
            vertex_count=len(field.vertices) // VERTEX_FLOATS,
        )
        self.effect_capacity = 65536
        self.effect_buffer = ctx.buffer(size=self.effect_capacity * VERTEX_FLOATS * 4)
        self.effects = ctx.pipeline(
            vertex_shader=MESH_VERTEX_SHADER, fragment_shader=MESH_FRAGMENT_SHADER,
            layout=[camera_layout, {"name": "textures", "binding": 0}],
            resources=mesh_resources, depth=depth, framebuffer=[target.color, target.depth],
            vertex_buffers=zengl.bind(self.effect_buffer, VERTEX_FORMAT, 0, 1, 2, 3), vertex_count=0,
        )
        clamp: Any = {**nearest, "wrap_x": "clamp_to_edge", "wrap_y": "clamp_to_edge"}
        sprite_resources: list[Any] = [camera_resource,
                                       {"type": "sampler", "binding": 0, "image": self.atlas, **clamp},
                                       {"type": "sampler", "binding": 1, "image": self.palette, **clamp}]
        self.sprites = ctx.pipeline(
            vertex_shader=SPRITE_VERTEX_SHADER, fragment_shader=SPRITE_FRAGMENT_SHADER,
            layout=[camera_layout, {"name": "atlas", "binding": 0}, {"name": "palette", "binding": 1}],
            resources=sprite_resources,
            depth=depth, framebuffer=[target.color, target.depth],
            vertex_buffers=zengl.bind(self.instance_buffer, "3f 4f 2f 1f /i", 0, 1, 2, 3),
            topology="triangle_strip", vertex_count=4, instance_count=0,
        )

        self.hud = Hud(self.gpu, field)
        self.hud.bind_battle(scene.battle)

        installation = self.options.get("installation")
        loaded_packets = scene.field.script.get("load", {}).get("loadsfx", ())
        self.missile_sounds = MissileSounds(installation,
                                            any(str(name).casefold() == "missile" for name in loaded_packets))
        self.battle_sounds = BattleSounds(installation, loaded_packets)
        self.cursors = GameCursors(installation, dll="GMCUR.DLL") if installation is not None else None
        self._cursor_mode: str | None = None
        self._set_cursor("default")

    def _set_cursor(self, mode: str) -> None:
        """Feedback (notes/game_rules.md "Battle HUD layout"): the cursor reflects the pending
        order mode, not hover position - Attack/Fire/Magic get their own cursor, everything else
        (including Move, which has none of its own) uses the default."""
        if self.cursors is None or self._cursor_mode == mode:
            return
        self._cursor_mode = mode
        self.cursors.set(BATTLE_CURSOR_GROUPS.get(mode, BATTLE_CURSOR_GROUPS["default"]))

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        camera = self.camera
        deploying = getattr(self.scene.battle, "phase", "battle") == "deployment"
        if deploying and getattr(self, "_drag_surface", None) is not None:
            if event.type == pygame.MOUSEMOTION and event.buttons[0]:
                return self._drag_events(event.pos, self._control_held(event))
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._drag_surface = None
                self.hud.set_pressed(None)
                return (("end_drag",),)
            if event.type in {pygame.KEYDOWN, pygame.KEYUP} and event.key in {pygame.K_LCTRL, pygame.K_RCTRL}:
                if self._drag_pixel is not None:
                    return self._drag_events(self._drag_pixel, self._control_held(event))
        if event.type == pygame.MOUSEWHEEL:
            camera.zoom(WHEEL_ZOOM ** event.y)
        elif event.type == pygame.MOUSEMOTION and event.buttons[2]:
            if deploying and getattr(self, "_right_minimap", False):
                dx, dy = self.hud.minimap_delta(event.rel)
                camera.set_target(camera.target_x - dx, camera.target_y - dy)
                return ()
            # Drag the ground: one screen pixel at the target covers this many BTS world units.
            height = self.gpu.target.size[1]
            scale = 2 * camera.distance * math.tan(math.radians(camera.fov) / 2) / height * WORLD_PER_MESH
            camera.pan(-event.rel[0] * scale, event.rel[1] * scale / math.sin(math.radians(camera.pitch)))
        elif event.type == pygame.MOUSEMOTION and event.buttons[1]:
            camera.rotate(event.rel[0] * DRAG_ROTATE)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_HOME:
            self.camera = replace(self.initial_camera)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_F2:
            # Debugging aid (whshr.figure_capture): trace the selected regiment's figures for 5 s.
            battle = self.scene.battle
            unit_id = figure_capture.capture_unit(battle, self.scene.selected_id)
            if unit_id is not None and self.scene.log_dir is not None:
                name = battle.regiments[unit_id].name
                self.battle_log.append(("", f"Extending the {name} figure capture by 5 s"
                                            if self.scene.running_capture(unit_id) is not None else
                                            f"Capturing {name} figures from tick {battle.update_count} for 5 s"))
                self.log_scroll = 0
                return (("capture", unit_id),)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.order_mode = None
            self._set_cursor("default")
            self.hud.set_pressed(None)
            self.hud.order_completed()
            self._drag_surface = None
            return (("end_drag",), ("deselect",)) if deploying else (("deselect",),)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.hud.set_pressed(None)
            minimap_hit = self.hud.click_minimap_tab(event.pos)
            if minimap_hit == "book":
                return (("objectives_book",),)
            if minimap_hit:
                return ()
            # A regiment's banner marker can hang outside the strict inner map-area rect (it is
            # anchored 8px left, 24px above its dot - notes/game_rules.md), so minimap_position()
            # alone (which only resolves points inside that inner rect) would miss a click on a
            # banner near the map's edge; check minimap_regiment_at() too, or such a click falls
            # through to hit_test()/occupies() below and is silently swallowed as HUD chrome.
            if (self.hud.minimap_position(event.pos) is not None
                    or self.hud.minimap_regiment_at(event.pos) is not None):
                control = self._control_held(event)
                return self._minimap_click(event.pos, append=deploying and control, repeat_item=control)
            action = self.hud.hit_test(event.pos)
            if action is not None:
                self.hud.set_pressed(action)
                if action.startswith("item:"):
                    return ()  # item rows commit on release, so their pressed state is visible
                if action == "scroll_up":
                    self.log_scroll = min(self.log_scroll + 1, max(0, len(self.battle_log) - 1))
                    return ()
                if action == "scroll_down":
                    self.log_scroll = max(0, self.log_scroll - 1)
                    return ()
                if action in {"next_regiment", "prev_regiment"}:
                    return self._cycle_regiment(1 if action == "next_regiment" else -1)
                order = self.hud.press(action)
                if action in {"move", "attack", "fire", "face_point"}:
                    self.order_mode = action
                    self._set_cursor(action if action != "face_point" else "move")
                    return (("prepare_move",),) if deploying and action == "move" else ()
                if order is not None:
                    self.order_mode = None
                    self._set_cursor("default")
                    # Stay on the sub-panel for repeat-friendly formation buttons so the
                    # player can click ranks or facing adjustments multiple times in a row.
                    if action not in {"ranks_up", "ranks_down", "turn_left", "turn_right", "about_face"}:
                        self.hud.order_completed()
                    return ((order,),)
                if action in {"items", "back"}:
                    self.order_mode = None
                    self._set_cursor("default")
                return ()
            if self.hud.occupies(event.pos):
                return ()
            control = self._control_held(event)
            return self._ground_click(event.pos, append=deploying and control, repeat_item=control)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pressed = self.hud.pressed
            self.hud.set_pressed(None)
            if pressed is not None and pressed.startswith("item:") and self.hud.hit_test(event.pos) == pressed:
                self.hud.press(pressed)
                item = pressed[5:]
                self.order_mode = pressed if item != "ItemPotionOfStrength" else None
                self._set_cursor("magic" if self.order_mode else "default")
                return (("arm_item", item),)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._right_minimap = deploying and self.hud.minimap_position(event.pos) is not None
            self._right_down = None if self.hud.occupies(event.pos) else event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            start, self._right_down = self._right_down, None
            if (not deploying and start is not None and not self.hud.occupies(event.pos)
                    and math.dist(start, event.pos) <= CLICK_DRAG_THRESHOLD):
                return self._ground_click(event.pos, direct=True)
        return ()

    @staticmethod
    def _control_held(event: pygame.event.Event) -> bool:
        modifiers = getattr(event, "mod", pygame.key.get_mods() if pygame.display.get_init() else 0)
        return bool(modifiers & pygame.KMOD_CTRL)

    def _cycle_regiment(self, step: int) -> Sequence[SceneEvent]:
        candidates = [r for r in self.scene.battle.regiments.values()
                      if r.side == Side.PLAYER and r.active and not (r.routing or r.held)]
        if not candidates:
            return ()
        current = next((i for i, r in enumerate(candidates) if r.identifier == self.scene.selected_id), -1 if step > 0 else 0)
        regiment = candidates[(current + step) % len(candidates)]
        self.camera.set_target(regiment.x, regiment.y)
        return (("select", regiment.identifier),)

    def _deployment_press(self, identifier: str | None, world: tuple[float, float] | None,
                          pixel: Sequence[float], surface: str) -> Sequence[SceneEvent]:
        if identifier is None:
            return ()
        regiment = self.scene.battle.regiments[identifier]
        if not regiment.active or regiment.routing or regiment.held:
            return ()
        if regiment.side == Side.PLAYER and world is not None:
            self._drag_surface = surface
            self._drag_pixel = (float(pixel[0]), float(pixel[1]))
            return (("select", identifier), ("begin_drag", identifier, *world))
        return (("select", identifier),)

    def _drag_events(self, pixel: Sequence[float], rotate: bool) -> Sequence[SceneEvent]:
        self._drag_pixel = (float(pixel[0]), float(pixel[1]))
        if self._drag_surface == "minimap":
            point = self.hud.minimap_position(pixel)
            if point is None:
                self._drag_surface = None
                return (("end_drag",),)
        else:
            field = self.scene.field
            width, height = self.gpu.target.size
            projection = self.camera.projection(width, height, field.width, field.height,
                                                field.ground_height(self.camera.target_x, self.camera.target_y))
            ground = picking.pick_ground(projection, pixel[0], pixel[1],
                                         lambda x, z: field.ground_height(x * WORLD_PER_MESH, z * WORLD_PER_MESH))
            if ground is None:
                return ()
            point = (ground[0] * WORLD_PER_MESH, ground[1] * WORLD_PER_MESH)
        return (("drag_to", *point, rotate),)

    def _ground_click(self, pixel: Sequence[float], direct: bool = False, append: bool = False,
                      repeat_item: bool = False) -> Sequence[SceneEvent]:
        """Translate a screen click into a ("select", id), ("attack", id) or ("move_to", x, y)
        scene event, if it hits ground.

        Left click (direct=False): notes/game_rules.md "Player orders and the command panel" -
        every order needs its own button pressed first, then a click executes it ("Move (boots) +
        click", "Attack (crossed swords) + click"...); there is no documented "just click an enemy
        to charge" shortcut, so with no pending order this always just selects whatever regiment,
        player or enemy, is under it (for the enemy's readout/banner/stats only -
        whshr.engine.Battle's order_move/order_attack/order_halt and Hud._button_enabled() both
        refuse commands for a non-player regiment regardless of selection), never issuing an order
        by itself.

        Right click (direct=True, no drag): a pre-existing engine convenience, not part of that
        documented button flow - orders the current selection there directly, bypassing the
        Move/Attack HUD buttons entirely."""
        field, camera = self.scene.field, self.camera
        width, height = self.gpu.target.size
        projection = camera.projection(width, height, field.width, field.height,
                                       field.ground_height(camera.target_x, camera.target_y))
        ground = picking.pick_ground(
            projection, pixel[0], pixel[1],
            lambda x, z: field.ground_height(x * WORLD_PER_MESH, z * WORLD_PER_MESH),
        )
        if ground is None:
            return ()
        x, y = ground[0] * WORLD_PER_MESH, ground[1] * WORLD_PER_MESH
        regiment_id = self.scene.battle.regiment_at(x, y, player_only=False)
        if regiment_id is None:
            # The ground-plane pick above only ever lands on a regiment's own ground footprint;
            # troop sprites are billboards standing well above that (SPRITE_VERTEX_SHADER), so a
            # click on the visible body - not just the feet - misses it entirely. Fall back to a
            # screen-space hit test against each regiment's actual rendered sprite block.
            regiment_id = self._sprite_pick(pixel, projection)
        # A building is a target of the attack order only when no regiment is under the click.
        building_id = self.scene.battle.building_at(x, y) if regiment_id is None else None
        if direct:
            if self.scene.battle.phase == "deployment":
                return ()
            if self.scene.selected_id is None:
                return ()
            if building_id is not None:
                return (("attack", building_id),)
            return (("attack", regiment_id),) if regiment_id is not None else (("move_to", x, y),)
        if self.order_mode is None:
            if self.scene.battle.phase == "deployment":
                return self._deployment_press(regiment_id, (x, y), pixel, "main")
            return (("select", regiment_id),) if regiment_id is not None else ()
        if append and self.order_mode == "move":
            return (("append_waypoint", x, y),)
        if (self.order_mode.startswith("item:") and repeat_item
                and self.scene.battle.event_bus.power.player >= 1):
            return (("item_target", self.order_mode[5:], x, y),)
        mode, self.order_mode = self.order_mode, None
        self._set_cursor("default")
        self.hud.order_completed()
        if mode == "attack":
            if building_id is not None:
                return (("attack", building_id),)
            if regiment_id is None:
                self._log_cannot("attack")
                return ()
            return (("attack", regiment_id),)
        if mode == "move":
            return (("move_to", x, y),)
        if mode == "fire":
            return (("fire", regiment_id, (x, y), bool(pygame.key.get_mods() & pygame.KMOD_CTRL)),)
        if mode.startswith("item:"):
            return (("item_target", mode[5:], x, y),)
        if mode == "face_point":
            return (("face_point", x, y),)
        return ()

    def _sprite_pick(self, pixel: Sequence[float], projection: Projection) -> str | None:
        """Screen-space fallback for _ground_click(): which active regiment's rendered sprite
        block, if any, covers this raw window pixel - approximated as a circle around each
        regiment's centre, at half its sprite height (SPRITE_MID_HEIGHT) above the ground and
        sized to its actual formation footprint (Regiment.bounding_radius()), projected to screen
        space at that regiment's own depth. Nearest to the camera wins when more than one
        regiment's circle covers the point (the one actually visible there, same as occlusion)."""
        field = self.scene.field
        best_id: str | None = None
        best_depth: float | None = None
        for regiment in self.scene.battle.regiments.values():
            if not regiment.active or not regiment.visible_to_player:
                continue
            mesh_x, mesh_z = regiment.x / WORLD_PER_MESH, regiment.y / WORLD_PER_MESH
            ground_height = field.ground_height(regiment.x, regiment.y)  # already mesh-space
            view = projection.view(mesh_x, ground_height + SPRITE_MID_HEIGHT, mesh_z)
            depth = view[2]
            if depth <= projection.near:
                continue  # behind (or at) the camera
            screen_x, screen_y, _ = projection.project(view)
            radius = regiment.bounding_radius() / WORLD_PER_MESH * projection.focal_length / depth
            if math.hypot(pixel[0] - screen_x, pixel[1] - screen_y) > radius:
                continue
            if best_depth is None or depth < best_depth:
                best_id, best_depth = regiment.identifier, depth
        return best_id

    def _minimap_click(self, pixel: Sequence[float], append: bool = False,
                       repeat_item: bool = False) -> Sequence[SceneEvent]:
        """A minimap click behaves like a 3D-view ground click (notes/game_rules.md "Battle HUD
        layout": "a left click on the minimap is handled exactly like a click in the 3D view"),
        sourced from the HUD's own marker hit-testing instead of 3D picking - see _ground_click's
        own docstring for why a plain click (no pending order) always just selects."""
        if self.order_mode is None:
            regiment_id = self.hud.minimap_regiment_at(pixel)
            if getattr(self.scene.battle, "phase", "battle") == "deployment":
                return self._deployment_press(regiment_id, self.hud.minimap_position(pixel), pixel, "minimap")
            return (("select", regiment_id),) if regiment_id is not None else ()
        world = self.hud.minimap_position(pixel)
        # An attack target is always whatever is topmost at the click point, ignoring current
        # selection (Hud.minimap_target_at()'s own docstring); it can resolve without a world
        # point too (its banner can hang outside the strict inner map-area rect near an edge).
        target_id = self.hud.minimap_target_at(pixel)
        if (world is None and target_id is None) or self.scene.selected_id is None:
            return ()
        if append and self.order_mode == "move":
            return (("append_waypoint", *world),) if world is not None else ()
        if (self.order_mode.startswith("item:") and repeat_item and world is not None
                and self.scene.battle.event_bus.power.player >= 1):
            return (("item_target", self.order_mode[5:], *world),)
        mode, self.order_mode = self.order_mode, None
        self._set_cursor("default")
        self.hud.order_completed()
        if mode == "attack":
            if target_id is None:
                self._log_cannot("attack")
                return ()
            return (("attack", target_id),)
        if mode == "move":
            return (("move_to", *world),) if world is not None else ()
        if mode == "fire":
            return (("fire", target_id, tuple(world) if world is not None else None,
                     bool(pygame.key.get_mods() & pygame.KMOD_CTRL)),)
        if mode.startswith("item:") and world is not None:
            return (("item_target", mode[5:], *world),)
        return ()

    def _log_cannot(self, order: str) -> None:
        # notes/game_rules.md's "Feedback" documents no tooltips/hover highlight and a click sound
        # on button press, but not a specific failed-order message; this mirrors the classic WFB
        # UI convention of a "Cannot!" cue on a targetless order, in the same debug event log the
        # HUD's own message-text window would show it in if that window were wired
        # (notes/game_rules.md's "Implemented" paragraph already lists it as not wired). No sound
        # plays yet: which SFX resource is the UI feedback cue is not identified in notes/sfx.md.
        self.event_log.append(f"Cannot {order}!")

    def animate(self, seconds: float) -> None:
        self.scene.battle.ctrl_held = bool(pygame.key.get_mods() & pygame.KMOD_CTRL)
        keys = pygame.key.get_pressed()
        right = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
        forward = (keys[pygame.K_UP] or keys[pygame.K_w]) - (keys[pygame.K_DOWN] or keys[pygame.K_s])
        step = self.camera.distance * WORLD_PER_MESH * PAN_SPEED * seconds
        if right or forward:
            self.camera.pan(right * step, forward * step)
        if turn := keys[pygame.K_e] - keys[pygame.K_q]:
            self.camera.rotate(turn * ROTATE_SPEED * seconds)
        if tilt := keys[pygame.K_PAGEUP] - keys[pygame.K_PAGEDOWN]:
            self.camera.tilt(tilt * TILT_SPEED * seconds)
        self.scene.battle.set_view_angle(view_angle(self.camera.yaw))
        self._publish_view_rect()
        for event in self.scene.battle.events:
            if hasattr(event, "kind") and event.kind in {"projectile_launch", "projectile_impact"}:
                code = event.data.get("code")
                if isinstance(code, int) and (event.kind == "projectile_launch" or event.data.get("blast")):
                    self.missile_sounds.play(code, impact=event.kind == "projectile_impact")
            if hasattr(event, "kind") and event.kind in {"ranged_message", "projectile_hit", "message"}:
                text_id = event.data.get("text_id")
                message = self.scene.battle.text_resources.get(text_id, str(event)) if isinstance(text_id, int) else str(event)
                if "%s" in message:
                    named = event.data.get("target") or event.data.get("regiment")
                    named_regiment = self.scene.battle.regiments.get(named) if isinstance(named, str) else None
                    display_name = event.data.get("target_name") or (named_regiment.name if named_regiment else None)
                    if isinstance(display_name, str):
                        try:
                            message = message % display_name
                        except (TypeError, ValueError):
                            pass
                self.battle_log.append(("", display_text(message)))
                self.log_scroll = 0
            if hasattr(event, "kind") and event.kind == "react":
                sender = event.data.get("sender", "")
                message = event.data.get("message", str(event))
                self.battle_log.append((f"{sender}:", reaction_text(message)))
                self.log_scroll = 0  # auto-scroll to newest on a new message
        self.event_log.extend(str(event) for event in self.scene.battle.events)
        battle_sounds: BattleSounds | None = getattr(self, "battle_sounds", None)  # tests build views without __init__
        if battle_sounds is not None:
            battle_sounds.handle(self.scene.battle.events)

    def _publish_view_rect(self) -> None:
        """Tell the battle which ground the camera shows (the "on screen" test for enemy reactions)."""
        field, camera = self.scene.field, self.camera
        width, height = self.gpu.target.size
        projection = camera.projection(width, height, field.width, field.height,
                                       field.ground_height(camera.target_x, camera.target_y))
        min_x, min_z, max_x, max_z = picking.view_rect(
            projection, width, height, (camera.target_x / WORLD_PER_MESH, camera.target_y / WORLD_PER_MESH),
            lambda x, z: field.ground_height(x * WORLD_PER_MESH, z * WORLD_PER_MESH))
        self.scene.battle.set_view_rect((min_x * WORLD_PER_MESH, min_z * WORLD_PER_MESH,
                                         max_x * WORLD_PER_MESH, max_z * WORLD_PER_MESH))

    def status(self) -> Sequence[str]:
        camera, scene = self.camera, self.scene
        selected = scene.battle.regiments[scene.selected_id].name if scene.selected_id else "-"
        lines = (
            f"battle tick {scene.battle.tick_count}, soldiers {self.soldiers}",
            f"camera yaw {camera.yaw:.0f} pitch {camera.pitch:.0f} distance {camera.distance:.0f}",
            f"target {camera.target_x:.0f}, {camera.target_y:.0f}",
            f"selected {selected}",
        ) + tuple(f"F2 capture: saving {scene.battle.regiments[capture.unit_id].name} figure state, "
                  f"{capture.remaining} ticks left" for capture in scene.captures if capture.running
                  and capture.unit_id in scene.battle.regiments)
        return lines + tuple(self.event_log)

    def _effect_vertices(self) -> array[float]:
        """Bake active installed scenery effect meshes at projectile positions each frame."""
        field = self.scene.field
        meshes = getattr(field, "effect_meshes", {})
        vertices = array("f")

        def append(name: str, x: float, y: float, z: float, dx: float = 0, dy: float = 1) -> None:
            mesh = meshes.get(name)
            if mesh is None or len(vertices) // VERTEX_FLOATS >= self.effect_capacity - 512:
                return
            angle = math.atan2(dx, dy)
            cos, sin = math.cos(angle), math.sin(angle)

            def transform(v: Sequence[float]) -> tuple[float, float, float]:
                return (x / WORLD_PER_MESH + v[0]*cos + v[2]*sin,
                        z / WORLD_PER_MESH + v[1],
                        y / WORLD_PER_MESH - v[0]*sin + v[2]*cos)

            def rotate(v: Sequence[float]) -> tuple[float, float, float]:
                return (v[0]*cos + v[2]*sin, v[1], -v[0]*sin + v[2]*cos)

            bake_mesh(mesh, field.ground_texture_count, field.scenery_texture_count,
                      transform, rotate, out=vertices)

        for p in self.scene.battle.projectiles:
            append(MISSILE_MESH.get(p.visual, "arrows1"), p.x, p.y, p.z, p.x1-p.x0, p.y1-p.y0)
        for p in self.scene.battle.innate_projectiles:
            family = "fire" if p.code == 14 else "flames" if p.code == 15 else "boltbur"
            append(f"{family}{1 + p.elapsed % 4}", p.x, p.y,
                   self.scene.battle.ground_height(p.x, p.y) + 8, p.x1-p.x0, p.y1-p.y0)
        for x, y, _code, started in self.scene.battle.impact_effects:
            frame = min(8, 1 + self.scene.battle.tick_count - started)
            append(f"ex{frame}", x, y, self.scene.battle.ground_height(x, y))
        return vertices

    def _instances(self) -> bytes:
        field, yaw, selected_id, data = self.scene.field, self.camera.yaw, self.scene.selected_id, bytearray()
        banner_instances: list[tuple[str, bytes]] = []
        for regiment in self.scene.battle.regiments.values():
            if not regiment.visible_to_player:
                continue
            sheet = field.sprite_sheet(regiment.sprite)
            selected = 1.0 if regiment.identifier == selected_id else 0.0
            # The anchor (regiment.x/y) can visibly outrun the models during a charge (they only
            # ever catch up to it at the unit's base speed, notes/game_rules.md "Formations": models
            # walk "never faster than the unit's s_rlmv", notes/engine_architecture.md
            # "Formation catch-up") - the banner should hover over the rendered troops themselves,
            # not the anchor, or it visibly floats ahead of/behind the block it marks.
            # Read-only: seeding here would draw stagger values in draw order and break replay determinism.
            positions = regiment.seeded_positions() if regiment.active else []
            if sheet is not None and regiment.active:
                unit_sheet: SpriteSheet = sheet
                # Each model already steps its own action/program counter every tick
                # (whshr.animation, game_rules.md "Figure animation"); this only reads it.
                def draw_model(x: float, y: float, model: Any) -> bytes:
                    action, phase = animation.current(model, regiment.animation_family)
                    facing = regiment.direction if model.drawn_facing is None else model.drawn_facing
                    index = unit_sheet.frame_index(action, phase, sprite_direction(yaw, facing))
                    frame, rect = unit_sheet.frames[index], _atlas_rect(unit_sheet, index)
                    return INSTANCE.pack(x / WORLD_PER_MESH, field.ground_height(x, y), y / WORLD_PER_MESH,
                                         *rect, frame.anchor_x, frame.anchor_y, selected)
                for (x, y), model in zip(positions, regiment.melee_models):
                    data += draw_model(x, y, model)
                for dying in regiment.dying:  # still playing their animation until they collapse
                    data += draw_model(dying.x, dying.y, dying.model)
            if sheet is not None:
                # Corpses (game_rules.md, "Panic": models that died stay on the ground where they fell).
                for x, y, corpse_direction in regiment.corpses:
                    index = sheet.frame_index("dead", 0, sprite_direction(yaw, corpse_direction))
                    frame, rect = sheet.frames[index], _atlas_rect(sheet, index)
                    data += INSTANCE.pack(x / WORLD_PER_MESH, field.ground_height(x, y), y / WORLD_PER_MESH,
                                          *rect, frame.anchor_x, frame.anchor_y, 0.0)
            # Burning figures and charred corpses come from the general battle-effects set, addressed by
            # first-frame number (animation.BURN_SEQUENCES). TODO(visual check): the frame-to-group
            # matching is by eye in the source notes (game_rules.md "Figure animation").
            effects = field.ui_sheets.get("genbatt")
            if effects is not None and effects.rects:
                effect_sheet: SpriteSheet = effects

                def draw_effect(x: float, y: float, number: int) -> bytes:
                    number = min(number, len(effect_sheet.frames) - 1)
                    frame, rect = effect_sheet.frames[number], _atlas_rect(effect_sheet, number)
                    return INSTANCE.pack(x / WORLD_PER_MESH, field.ground_height(x, y), y / WORLD_PER_MESH,
                                         *rect, frame.anchor_x, frame.anchor_y, 0.0)
                for burning in regiment.burning:
                    data += draw_effect(burning.x, burning.y, animation.burning_frame(burning))
                for x, y, charred_direction, body in regiment.charred:
                    data += draw_effect(x, y, animation.charred_frame(body, sprite_direction(yaw, charred_direction)))
            banner = field.ui_sheets.get((regiment.banner or "").casefold())
            if regiment.active and banner is not None and len(banner.frames) > 2 and banner.rects and positions:
                frame, rect = banner.frames[2], _atlas_rect(banner, 2)
                center_x = sum(x for x, _ in positions) / len(positions)
                center_y = sum(y for _, y in positions) / len(positions)
                banner_instances.append((regiment.identifier, INSTANCE.pack(
                    center_x / WORLD_PER_MESH,
                    field.ground_height(center_x, center_y) + BANNER_MARKER_RAISE,
                    center_y / WORLD_PER_MESH,
                    *rect, frame.width / 2, frame.height, selected,
                )))
        data += self._item_markers()
        # The original promotes the focused banner in z-order and leaves it promoted after deselecting.
        order: list[str] = getattr(self, "_banner_order", [])  # tests build views without __init__
        identifiers = list(self.scene.battle.regiments)
        order[:] = [identifier for identifier in order if identifier in self.scene.battle.regiments]
        order.extend(identifier for identifier in identifiers if identifier not in order)
        if selected_id in order:
            order.remove(selected_id)
            order.append(selected_id)
        self._banner_order = order
        rank = {identifier: index for index, identifier in enumerate(order)}
        for _, instance in sorted(banner_instances, key=lambda pair: rank[pair[0]]):
            data.extend(instance)
        return bytes(data[:self.capacity * INSTANCE.size])

    def _item_markers(self) -> bytes:
        """The sparkle over each item still to be picked up (notes/battle_end_objectives.md 12.2): effect set
        `Sparkle`, variant 1 (frames 0-4) or, in a battle that loads snow scenery, variant 2 (frames 5-12).
        PROVISIONAL: the frames cycle one per two battle ticks (the original's timing was not traced)."""
        objectives = getattr(self.scene.battle, "objectives", None)
        sheet = self.scene.field.ui_sheets.get("sparkle")
        if objectives is None or not objectives.item_marks or sheet is None or not sheet.rects:
            return b""
        furniture = {str(name).casefold() for name in self.scene.field.script.get("load", {}).get("loadfurn", ())}
        snow = bool(furniture & SNOW_FURNITURE)
        first, count = (5, 8) if snow else (0, 5)
        number = min(first + (self.scene.battle.update_count // 2) % count, len(sheet.frames) - 1)
        frame, rect = sheet.frames[number], _atlas_rect(sheet, number)
        field, data = self.scene.field, bytearray()
        for x, y in objectives.item_marks.values():
            data += INSTANCE.pack(x / WORLD_PER_MESH, field.ground_height(x, y), y / WORLD_PER_MESH,
                                  *rect, frame.anchor_x, frame.anchor_y, 0.0)
        return bytes(data)

    def draw(self) -> None:
        super().draw()
        field, camera = self.scene.field, self.camera
        width, height = self.gpu.target.size
        projection = camera.projection(width, height, field.width, field.height,
                                       field.ground_height(camera.target_x, camera.target_y))
        self.camera_buffer.write(CAMERA.pack(
            *projection.eye, 0.0, *projection.right, 0.0, *projection.up, 0.0, *projection.view_direction, 0.0,
            1 / projection.tan_fov_x, 1 / projection.tan_fov_y, NEAR, FAR,
            SPRITE_PIXEL_WORLD_UNITS / WORLD_PER_MESH, SPRITE_DEPTH_BIAS, 0.0, 0.0,
        ))
        instances = self._instances()
        if instances:
            self.instance_buffer.write(instances)
        self.sprites.instance_count = len(instances) // INSTANCE.size
        self.soldiers = sum(regiment.models for regiment in self.scene.battle.regiments.values()
                            if regiment.active)
        self.mesh.render()
        effect_vertices = self._effect_vertices()
        if effect_vertices:
            self.effect_buffer.write(effect_vertices.tobytes())
        self.effects.vertex_count = len(effect_vertices) // VERTEX_FLOATS
        if self.effects.vertex_count:
            self.effects.render()
        self.sprites.render()
        self.hud.set_selected(self.scene.selected_id)
        log_list = list(self.battle_log)
        end = max(0, len(log_list) - self.log_scroll)
        self.hud.set_log(log_list[max(0, end - 4):end])
        sel = self.scene.selected_id
        if sel is not None and sel in self.scene.battle.regiments:
            reg = self.scene.battle.regiments[sel]
            initial: dict[str, int] = getattr(self.scene, "initial_models", {})
            self.hud.set_unit_info(reg.name, reg.hud_class, reg.models, initial.get(sel))
        else:
            self.hud.set_unit_info("", None, None, None)
        self.hud.draw(width, height, self.camera)

    def release(self) -> None:
        for resource in (self.mesh, self.effects, self.sprites, self.vertex_buffer, self.effect_buffer,
                         self.instance_buffer, self.camera_buffer,
                         self.textures, self.atlas, self.palette):
            self.gpu.ctx.release(resource)
        self.hud.release()
        if self.cursors is not None:
            try:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
            except pygame.error:
                pass
