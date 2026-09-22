"""Battle view: terrain, scenery and troop sprite billboards on the GPU, with a free battle camera.

Controls: arrow keys or WASD pan, Q/E rotate, Page Up/Page Down tilt, mouse wheel zooms, right-drag pans,
middle-drag rotates, Home resets the camera. Left-click a player regiment to select it (tinted yellow);
left-click, or right-click without dragging, on the ground with a regiment selected orders it there;
Escape deselects.
"""

from collections import deque
from dataclasses import replace
import math
import struct

import pygame
import zengl

from .. import picking
from ..battle3d import SPRITE_DEPTH_BIAS
from ..battlefield import VERTEX_FLOATS, VERTEX_FORMAT, WORLD_PER_MESH, sprite_direction
from ..camera import BattleCamera
from ..formation import SPRITE_PIXEL_WORLD_UNITS
from .scene_view import SceneView
from .hud import Hud

SKY = (112, 150, 196)
NEAR, FAR = 0.5, 4000.0  # mesh units
PAN_SPEED = 0.8  # camera distances per second
ROTATE_SPEED = 90.0  # degrees per second
TILT_SPEED = 30.0  # degrees per second
WHEEL_ZOOM = 0.9
DRAG_ROTATE = 0.3  # degrees per pixel
CLICK_DRAG_THRESHOLD = 4  # pixels; a right button press/release closer than this counts as a click
# Frames per second of the walking animation while a regiment is not settled in formation. The original
# per-frame animation timing is not traced (notes/game_rules.md, "Animation bytecode"): this is a
# documented placeholder, not a measured value.
WALK_ANIMATION_FPS = 8.0
BANNER_MARKER_RAISE = 4.0  # mesh units: above a 64-pixel troop sprite, below the camera's horizon
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


class BattleView(SceneView):
    background = SKY

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        field, ctx, target = scene.field, gpu.ctx, gpu.target
        self.initial_camera = BattleCamera.for_battle(field.script)
        if self.options.get("camera"):
            yaw, pitch, distance = self.options["camera"]
            self.initial_camera = replace(self.initial_camera, yaw=yaw % 360, pitch=pitch, distance=distance)
        self.camera = replace(self.initial_camera)
        self.soldiers = 0
        self._right_down = None  # screen position of an unreleased right-button press, for click detection
        self.order_mode = None  # a HUD Move/Attack click changes how the next battlefield click is interpreted
        self.event_log = deque(maxlen=EVENT_LOG_LINES)  # recent whshr.engine.Battle.events, newest last
        self._banner_order = []  # promoted selection order; persists after deselect like the original battle view

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

        camera_layout = {"name": "Camera", "binding": 0}
        camera_resource = {"type": "uniform_buffer", "binding": 0, "buffer": self.camera_buffer}
        nearest = {"min_filter": "nearest", "mag_filter": "nearest"}
        depth = {"func": "less", "write": True}
        self.mesh = ctx.pipeline(
            vertex_shader=MESH_VERTEX_SHADER, fragment_shader=MESH_FRAGMENT_SHADER,
            layout=[camera_layout, {"name": "textures", "binding": 0}],
            resources=[camera_resource, {"type": "sampler", "binding": 0, "image": self.textures, **nearest,
                                         "wrap_x": "repeat", "wrap_y": "repeat"}],
            depth=depth, framebuffer=[target.color, target.depth],
            vertex_buffers=zengl.bind(self.vertex_buffer, VERTEX_FORMAT, 0, 1, 2, 3),
            vertex_count=len(field.vertices) // VERTEX_FLOATS,
        )
        clamp = {**nearest, "wrap_x": "clamp_to_edge", "wrap_y": "clamp_to_edge"}
        self.sprites = ctx.pipeline(
            vertex_shader=SPRITE_VERTEX_SHADER, fragment_shader=SPRITE_FRAGMENT_SHADER,
            layout=[camera_layout, {"name": "atlas", "binding": 0}, {"name": "palette", "binding": 1}],
            resources=[camera_resource,
                       {"type": "sampler", "binding": 0, "image": self.atlas, **clamp},
                       {"type": "sampler", "binding": 1, "image": self.palette, **clamp}],
            depth=depth, framebuffer=[target.color, target.depth],
            vertex_buffers=zengl.bind(self.instance_buffer, "3f 4f 2f 1f /i", 0, 1, 2, 3),
            topology="triangle_strip", vertex_count=4, instance_count=0,
        )

        self.hud = Hud(self.gpu, field)
        self.hud.bind_battle(scene.battle)

    def events(self, event):
        camera = self.camera
        if event.type == pygame.MOUSEWHEEL:
            camera.zoom(WHEEL_ZOOM ** event.y)
        elif event.type == pygame.MOUSEMOTION and event.buttons[2]:
            # Drag the ground: one screen pixel at the target covers this many BTS world units.
            height = self.gpu.target.size[1]
            scale = 2 * camera.distance * math.tan(math.radians(camera.fov) / 2) / height * WORLD_PER_MESH
            camera.pan(-event.rel[0] * scale, event.rel[1] * scale / math.sin(math.radians(camera.pitch)))
        elif event.type == pygame.MOUSEMOTION and event.buttons[1]:
            camera.rotate(event.rel[0] * DRAG_ROTATE)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_HOME:
            self.camera = replace(self.initial_camera)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.order_mode = None
            self.hud.set_pressed(None)
            self.hud.order_completed()
            return (("deselect",),)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.hud.set_pressed(None)
            if self.hud.click_minimap_tab(event.pos):
                return ()
            if self.hud.minimap_position(event.pos) is not None:
                return self._minimap_click(event.pos)
            action = self.hud.hit_test(event.pos)
            if action is not None:
                self.hud.set_pressed(action)
                order = self.hud.press(action)
                if action in {"move", "attack"}:
                    self.order_mode = action
                    return ()
                if order is not None:
                    self.order_mode = None
                    self.hud.order_completed()
                    return ((order,),)
                return ()
            if self.hud.occupies(event.pos):
                return ()
            return self._ground_click(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.hud.set_pressed(None)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._right_down = None if self.hud.occupies(event.pos) else event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            start, self._right_down = self._right_down, None
            if (start is not None and not self.hud.occupies(event.pos)
                    and math.dist(start, event.pos) <= CLICK_DRAG_THRESHOLD):
                return self._ground_click(event.pos)
        return ()

    def _ground_click(self, pixel):
        """Translate a screen click into a ("select", id), ("attack", id) or ("move_to", x, y) scene
        event, if it hits ground. A click on an enemy regiment with a selection orders a charge; a click
        on an enemy regiment with no selection is treated as an ordinary ground click (no order issued)."""
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
        regiment_id = self.scene.battle.regiment_at(x, y)
        if regiment_id is not None and self.order_mode is None:
            return (("select", regiment_id),)
        if self.scene.selected_id is not None:
            enemy_id = self.scene.battle.regiment_at(x, y, player_only=False)
            mode, self.order_mode = self.order_mode, None
            self.hud.order_completed()
            if mode == "attack":
                return (("attack", enemy_id),) if enemy_id is not None else ()
            if mode == "move":
                return (("move_to", x, y),)
            if enemy_id is not None:
                return (("attack", enemy_id),)
        return (("move_to", x, y),)

    def _minimap_click(self, pixel):
        """A minimap click behaves like a 3D-view ground click (notes/game_rules.md "Battle HUD
        layout": "a left click on the minimap is handled exactly like a click in the 3D view"),
        sourced from the HUD's own marker hit-testing instead of 3D picking - except an empty
        click with no pending order never issues a direct move."""
        regiment_id = self.hud.minimap_regiment_at(pixel)
        if regiment_id is not None and self.order_mode is None:
            regiment = self.scene.battle.regiments.get(regiment_id)
            return (("select", regiment_id),) if regiment is not None and regiment.player else ()
        world = self.hud.minimap_position(pixel)
        if world is None or self.scene.selected_id is None:
            return ()
        mode, self.order_mode = self.order_mode, None
        self.hud.order_completed()
        if mode == "attack":
            return (("attack", regiment_id),) if regiment_id is not None else ()
        if mode == "move":
            return (("move_to", *world),)
        return ()

    def animate(self, seconds):
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
        self.event_log.extend(self.scene.battle.events)

    def status(self):
        camera, scene = self.camera, self.scene
        selected = scene.battle.regiments[scene.selected_id].name if scene.selected_id else "-"
        lines = (
            f"battle tick {scene.battle.tick_count}, soldiers {self.soldiers}",
            f"camera yaw {camera.yaw:.0f} pitch {camera.pitch:.0f} distance {camera.distance:.0f}",
            f"target {camera.target_x:.0f}, {camera.target_y:.0f}",
            f"selected {selected}",
        )
        return lines + tuple(self.event_log)

    def _instances(self):
        field, yaw, selected_id, data = self.scene.field, self.camera.yaw, self.scene.selected_id, bytearray()
        banner_instances = []
        for regiment in self.scene.battle.regiments.values():
            sheet = field.sprite_sheet(regiment.sprite)
            selected = 1.0 if regiment.identifier == selected_id else 0.0
            if sheet is not None and regiment.active:
                if regiment.in_melee:
                    action, phase = "attack", int(regiment.animation_seconds * WALK_ANIMATION_FPS)
                elif regiment.missile_range and not regiment.moving and not regiment.attack_target:
                    action, phase = "shoot", 0
                elif regiment.walking:
                    action, phase = "move", int(regiment.animation_seconds * WALK_ANIMATION_FPS)
                else:
                    action, phase = "stand", 0
                index = sheet.frame_index(action, phase, sprite_direction(yaw, regiment.direction))
                frame, rect = sheet.frames[index], sheet.rects[index]
                for x, y in regiment.model_positions():
                    data += INSTANCE.pack(x / WORLD_PER_MESH, field.ground_height(x, y), y / WORLD_PER_MESH,
                                          *rect, frame.anchor_x, frame.anchor_y, selected)
            if sheet is not None:
                # Corpses (game_rules.md, "Panic": models that died stay on the ground where they fell).
                for x, y, corpse_direction in regiment.corpses:
                    index = sheet.frame_index("dead", 0, sprite_direction(yaw, corpse_direction))
                    frame, rect = sheet.frames[index], sheet.rects[index]
                    data += INSTANCE.pack(x / WORLD_PER_MESH, field.ground_height(x, y), y / WORLD_PER_MESH,
                                          *rect, frame.anchor_x, frame.anchor_y, 0.0)
            banner = field.ui_sheets.get((regiment.banner or "").casefold())
            if regiment.active and banner is not None and len(banner.frames) > 2 and banner.rects:
                frame, rect = banner.frames[2], banner.rects[2]
                banner_instances.append((regiment.identifier, INSTANCE.pack(
                    regiment.x / WORLD_PER_MESH,
                    field.ground_height(regiment.x, regiment.y) + BANNER_MARKER_RAISE,
                    regiment.y / WORLD_PER_MESH,
                    *rect, frame.width / 2, frame.height, selected,
                )))
        # The original promotes the focused banner in z-order and leaves it promoted after deselecting.
        order = getattr(self, "_banner_order", [])
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

    def draw(self):
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
        self.sprites.render()
        self.hud.set_selected(self.scene.selected_id)
        self.hud.draw(width, height, self.camera)

    def release(self):
        for resource in (self.mesh, self.sprites, self.vertex_buffer, self.instance_buffer, self.camera_buffer,
                         self.textures, self.atlas, self.palette):
            self.gpu.ctx.release(resource)
        self.hud.release()
