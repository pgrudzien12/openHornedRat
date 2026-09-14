"""Battle view: terrain, scenery and troop sprite billboards on the GPU, with a free battle camera.

Controls: arrow keys or WASD pan, Q/E rotate, Page Up/Page Down tilt, mouse wheel zooms, right-drag pans,
middle-drag rotates, Home resets the camera.
"""

from dataclasses import replace
import math
import struct

import pygame
import zengl

from ..battle3d import SPRITE_DEPTH_BIAS
from ..battlefield import VERTEX_FLOATS, VERTEX_FORMAT, WORLD_PER_MESH, sprite_direction
from ..camera import BattleCamera
from ..formation import SPRITE_PIXEL_WORLD_UNITS
from .scene_view import SceneView

SKY = (112, 150, 196)
NEAR, FAR = 0.5, 4000.0  # mesh units
PAN_SPEED = 0.8  # camera distances per second
ROTATE_SPEED = 90.0  # degrees per second
TILT_SPEED = 30.0  # degrees per second
WHEEL_ZOOM = 0.9
DRAG_ROTATE = 0.3  # degrees per pixel
INSTANCE = struct.Struct("9f")  # foot position (mesh), atlas rectangle (pixels), anchor (pixels)
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

out vec2 v_texel;

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
}
"""

SPRITE_FRAGMENT_SHADER = """
#version 330 core

uniform sampler2D atlas;
uniform sampler2D palette;

in vec2 v_texel;
out vec4 frag_color;

void main() {
    int index = int(texelFetch(atlas, ivec2(v_texel), 0).r * 255.0 + 0.5);
    if (index == 0) {
        discard;
    }
    frag_color = vec4(texelFetch(palette, ivec2(index, 0), 0).rgb, 1.0);
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

        ctx.includes["camera"] = CAMERA_BLOCK
        self.camera_buffer = ctx.buffer(size=CAMERA.size, uniform=True)
        self.vertex_buffer = ctx.buffer(field.vertices.tobytes())
        self.textures = ctx.image(field.texture_size, "rgba8unorm", b"".join(field.texture_layers),
                                  array=len(field.texture_layers))
        self.atlas = ctx.image(field.atlas_size, "r8unorm", field.atlas)
        self.palette = ctx.image((256, 1), "rgba8unorm", b"".join(bytes((*rgb, 255)) for rgb in field.palette))
        self.capacity = max(1, sum(regiment.models for regiment in scene.battle.regiments.values()))
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
            vertex_buffers=zengl.bind(self.instance_buffer, "3f 4f 2f /i", 0, 1, 2),
            topology="triangle_strip", vertex_count=4, instance_count=0,
        )

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

    def status(self):
        camera, battle = self.camera, self.scene.battle
        return (
            f"battle tick {battle.tick_count}, soldiers {self.soldiers}",
            f"camera yaw {camera.yaw:.0f} pitch {camera.pitch:.0f} distance {camera.distance:.0f}",
            f"target {camera.target_x:.0f}, {camera.target_y:.0f}",
        )

    def _instances(self):
        field, yaw, data = self.scene.field, self.camera.yaw, bytearray()
        for regiment in self.scene.battle.regiments.values():
            sheet = field.sprite_sheet(regiment.sprite)
            if sheet is None:
                continue
            index = sheet.frame_index("stand", 0, sprite_direction(yaw, regiment.direction))
            frame, rect = sheet.frames[index], sheet.rects[index]
            for x, y in regiment.model_positions():
                data += INSTANCE.pack(x / WORLD_PER_MESH, field.ground_height(x, y), y / WORLD_PER_MESH,
                                      *rect, frame.anchor_x, frame.anchor_y)
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
        self.soldiers = self.sprites.instance_count = len(instances) // INSTANCE.size
        self.mesh.render()
        self.sprites.render()

    def release(self):
        for resource in (self.mesh, self.sprites, self.vertex_buffer, self.instance_buffer, self.camera_buffer,
                         self.textures, self.atlas, self.palette):
            self.gpu.ctx.release(resource)
