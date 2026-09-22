"""Battle HUD: the 640x480 screen's command panel, minimap and selected-unit readout.

Layout source: notes/game_rules.md "Battle HUD layout" (windows, fixed buttons, command
sub-window slots, per-state button sets, minimap, readout, feedback). Everything except text is a
frame of the installation's ICONS sheet (225 frames); nothing here is procedurally drawn chrome
invented by the engine.

Order dispatch: `whshr.engine.Battle` currently implements only move/attack/halt as player orders
(the spec's ranks/facing/charge/withdraw/rally/magic/fire/items/independent/fight-harder orders
have no engine-side counterpart yet; ROADMAP.md M3/M4 is where the order system itself grows).
Buttons for orders without engine support still render at their documented position and icon (so
the panel looks and navigates correctly) but are disabled; panel-state *navigation* (which
sub-panel is shown) is implemented in full, since that is pure UI state independent of which
orders the engine can actually carry out.
"""

import pygame

from .gpu import ScreenQuad

# Documented for completeness; battle_view.py's 3D pipeline does not yet clip its viewport to this
# rect (it renders full-screen, with the HUD's own chrome simply drawn over it).
VIEW_RECT = (8, 8, 624, 417)
PANEL_RECT = (0, 304, 640, 176)
MINIMAP_RECT = (425, 7, 216, 297)
PANEL_BG_FRAME = 98

# Inside the panel, relative to PANEL_RECT's own origin.
COMMAND_SUBWINDOW = (492, 0, 148, 175)
READOUT_RECT = (72, 0, 128, 177)

# Fixed buttons: name -> (position relative to the panel, raised/pressed frame pair, size).
FIXED_BUTTONS = {
    "camera_rotate": ((11, 8), (42, 43), (52, 52)),
    "camera_zoom": ((11, 63), (44, 45), (52, 52)),
    "options": ((448, 13), (58, 59), (44, 44)),
    "prev_regiment": ((448, 75), (60, 61), (44, 44)),
    "next_regiment": ((448, 121), (62, 63), (44, 44)),
    # notes/game_rules.md gives one position, (140, 4), for both 32x48 toggles; the second's x is
    # inferred (placed immediately to the right), not confirmed.
    "toggle_a": ((140, 4), (64, 65), (32, 48)),
    "toggle_b": ((172, 4), (66, 67), (32, 48)),
    "scroll_up": ((224, 9), (68, 69), (20, 20)),
    "scroll_down": ((224, 34), (70, 71), (20, 20)),
}
# The pause/resume button at (11, 118) changes frame pair by context; it is not in FIXED_BUTTONS.
PAUSE_POS, PAUSE_SIZE = (11, 118), (52, 52)
PAUSE_FRAMES = {"battle": (46, 47), "deployment": (48, 49), "paused": (50, 51)}

# Command sub-window: 5 slots relative to COMMAND_SUBWINDOW's own origin, each 60x60.
SLOT_POSITIONS = {"TL": (7, 11), "TR": (83, 11), "BR": (83, 109), "BL": (7, 109), "C": (45, 60)}
SLOT_SIZE = (60, 60)

# Command button frames: raised/pressed pair (a single-frame decoration repeats its own index).
COMMAND_FRAMES = {
    "move": (0, 1), "attack": (2, 3), "fire": (4, 5), "magic": (6, 7), "items": (8, 9),
    "back": (10, 11), "turn_right": (12, 13), "turn_left": (14, 15), "about_face": (16, 17),
    "ranks_subset": (18, 19), "ranks_up": (20, 21), "ranks_down": (22, 23),
    "ranks_decoration": (24, 24), "facing_subset": (25, 26), "face_point": (35, 36),
    "halt": (37, 38), "rally": (37, 38), "withdraw": (39, 40), "independent": (52, 53),
    "charge": (54, 55), "fight_harder": (56, 57),
}
# Commands whshr.engine.Battle can actually carry out today; everything else in COMMAND_FRAMES
# renders (and, where it is a set-entry button, still navigates the panel) but is disabled.
ORDER_SUPPORTED = {"move", "attack", "halt"}
# Buttons that only change which sub-panel is shown (pure HUD state, always clickable when present).
SET_ENTRY = {"move": "move", "attack": "attack", "ranks_subset": "ranks", "facing_subset": "facing",
            "back": "idle"}

CLASSES = ("inf", "arch", "art", "wiz", "mon")
PANEL_LAYOUT = {}


def _set(state, classes, **slots):
    for unit_class in classes:
        PANEL_LAYOUT[(state, unit_class)] = dict(slots)


_set("idle", ("inf", "arch", "mon"), TL="move", TR="attack", BR="independent")
_set("idle", ("art",), TR="attack", BR="independent")
_set("idle", ("wiz",), TL="move", TR="attack", BR="independent", BL="magic", C="back")
PANEL_LAYOUT[("idle", None)] = {"TL": "move", "TR": "attack", "BR": "independent"}  # nothing selected

_set("move", ("inf", "arch"), TL="ranks_subset", TR="facing_subset", BR="halt", BL="face_point", C="back")
_set("move", ("wiz", "mon"), TL="turn_left", TR="turn_right", BR="halt", BL="about_face", C="back")
_set("move", ("art",))  # none

_set("ranks", ("inf", "arch"), TL="ranks_up", TR="ranks_decoration", BL="ranks_down", C="back")
_set("ranks", ("art", "wiz", "mon"))  # none

_set("facing", ("inf", "arch"), TL="turn_left", TR="turn_right", BL="about_face", C="back")
_set("facing", ("art", "wiz", "mon"))  # none

_set("attack_caster", ("inf", "wiz", "mon"), TL="charge", BR="items", C="back")
_set("attack_caster", ("arch",), TL="charge", TR="fire", BR="items", BL="halt", C="back")
_set("attack_caster", ("art",), TR="fire", BR="items", BL="halt", C="back")

_set("attack_noncaster", ("inf", "wiz", "mon"), TL="charge", C="back")
_set("attack_noncaster", ("arch",), TL="charge", TR="fire", BL="halt", C="back")
_set("attack_noncaster", ("art",), TR="fire", BL="halt", C="back")

_set("rally", CLASSES, BR="rally")

_set("melee_caster", ("inf", "arch", "art", "mon"), TR="withdraw", BR="items", C="fight_harder")
_set("melee_caster", ("wiz",), TR="withdraw", BR="items", BL="magic", C="fight_harder")

_set("melee_noncaster", ("inf", "arch", "art", "mon"), TR="withdraw", C="fight_harder")
_set("melee_noncaster", ("wiz",), TR="withdraw", BL="magic", C="fight_harder")

_set("deployment", ("inf", "arch"), TL="ranks_up", TR="move", BR="independent", BL="ranks_down",
    C="ranks_decoration")
_set("deployment", ("wiz", "mon"), TR="move", BR="independent")
_set("deployment", ("art",), BR="independent")

_set("charging", CLASSES)  # none

# Minimap (relative to MINIMAP_RECT's own origin).
MINIMAP_LAYERS = (("101", (0, 0), (216, 16)), ("102", (0, 16), (16, 216)), ("103", (200, 16), (16, 216)),
                  ("104", (0, 233), (216, 64)))
MAP_AREA_RECT = (16, 17, 184, 216)
MINIMAP_TABS = (((63, 241), (72, 73)), ((110, 241), (74, 75)), ((63, 264), (76, 77)), ((110, 264), (78, 79)))
MINIMAP_TAB_SIZE = (44, 20)
MINIMAP_BOOK_POS, MINIMAP_BOOK_FRAMES, MINIMAP_BOOK_SIZE = (162, 242), (80, 81), (40, 40)
# Tab-to-mode order is not confirmed (notes/game_rules.md marks it 🟡); this assumes the tabs
# appear left to right in the documented mode order 0-3.
MARKER_MODES = (0, 1, 2, 3)
DEPLOYMENT_ZONE_FRAME = 160  # not drawn yet: no deployment phase (see _draw_minimap)
# Numbered waypoint dots for a queued multi-stop order; whshr.engine.Regiment has only one
# target_x/target_y (no queue), so only WAYPOINT_END_FRAME is ever drawn today.
WAYPOINT_FRAMES = tuple(range(161, 170))
WAYPOINT_END_FRAME = 159
CAMERA_MARKER_FRAMES = tuple(range(170, 178))
# Regiment dot base frame per (fighting-or-charging, side); add the 0-7 facing index. Broken adds
# the same offset from its own base.
DOT_BASE = {
    ("fighting", True): 119, ("fighting", False): 111,
    ("normal", True): 135, ("normal", False): 127,
    ("broken", True): 151, ("broken", False): 143,
}
COMPASS_FRAMES = (99, 105)

BLACK = (0, 0, 0)


def frame_rgba(frame, palette):
    """Convert a decoded indexed frame to top-down RGBA for a ScreenQuad."""
    rgba = bytearray(frame.width * frame.height * 4)
    for offset, index in enumerate(frame.pixels):
        rgba[offset * 4:offset * 4 + 4] = (*palette[index], 0 if index == 0 else 255)
    return bytes(rgba)


class Hud:
    """Battle chrome built from the installation's ICONS sheet and the field's portrait/plan-map art."""

    def __init__(self, gpu, field):
        self.gpu, self.field = gpu, field
        self.icons = self._sheet("icons")
        self.panel_bg = self._quad(self.icons, PANEL_BG_FRAME)
        self.portrait_bg = self._sheet(field.script["field"].get("portrait_bg"))
        self.portrait_bg_quad = self._quad(self.portrait_bg, 0)
        self.planmap = self._sheet(field.script["field"].get("planmap"))
        self._icon_cache = {}  # ICONS frame index -> ScreenQuad, built lazily and kept for the view's life
        self._sheet_frame_cache = {}  # id(frame) -> ScreenQuad, for portrait/banner/plan-map frames outside ICONS
        self.minimap_layers = {index: self._icon(int(index)) for index, _pos, _size in MINIMAP_LAYERS}
        self.compass_quads = tuple(self._icon(f) for f in COMPASS_FRAMES)
        self.selected = None
        self.battle = None
        self.marker_mode = 0
        self.panel_set = "idle"  # HUD-local sub-panel navigation: idle/move/ranks/facing/attack
        self.pending_order = None  # "move" or "attack": next battlefield/minimap click issues it
        self._draw_size = None
        # Name of the fixed button or command held down, for its pressed art; hit_test()'s return
        # value (fixed-button names and command names never collide).
        self.pressed = None
        self._marker_order = []

    def _sheet(self, name):
        return self.field.ui_sheets.get(name.casefold()) if name else None

    def _quad(self, sheet, index):
        if sheet is None or index >= len(sheet.frames):
            return None
        frame = sheet.frames[index]
        quad = ScreenQuad(self.gpu, (frame.width, frame.height))
        quad.write(frame_rgba(frame, self.field.palette))
        return quad

    def _icon(self, frame_index):
        """A cached ICONS-sheet quad. Built once per frame index and reused: every draw()-time
        caller needs this cache, since a fresh ScreenQuad recreates a GPU texture (the earlier
        cause of a severe FPS drop when a similar mistake was made in troop_selection_view.py)."""
        if frame_index not in self._icon_cache:
            self._icon_cache[frame_index] = self._quad(self.icons, frame_index)
        return self._icon_cache[frame_index]

    def _sheet_frame_quad(self, frame):
        key = id(frame)
        quad = self._sheet_frame_cache.get(key)
        if quad is None:
            quad = ScreenQuad(self.gpu, (frame.width, frame.height))
            quad.write(frame_rgba(frame, self.field.palette))
            self._sheet_frame_cache[key] = quad
        return quad

    # ------------------------------------------------------------------ selection and panel state

    def set_selected(self, regiment_id):
        """Select a regiment and rebuild only its portrait/ornament art when it changes."""
        if regiment_id == self.selected:
            return
        self.selected = regiment_id
        self.panel_set = "idle"
        self.pending_order = None
        if regiment_id is not None:
            self._promote_marker(regiment_id)

    def set_portrait(self, regiment_id):
        """Compatibility name for selecting the HUD regiment."""
        self.set_selected(regiment_id)

    def bind_battle(self, battle):
        self.battle = battle

    def _regiment(self, identifier):
        return self.battle.regiments.get(identifier) if self.battle is not None else None

    def _caster(self, regiment):
        # notes/game_rules.md's attack/melee "caster" variant depends on the unit carrying spells or
        # items; whshr.engine.Regiment models neither (no magic/item system yet), so this is always
        # the non-caster variant, a documented simplification rather than a guess at unmodelled data.
        return False

    def panel_state(self):
        """(state, unit_class) selecting a row of PANEL_LAYOUT, per notes/game_rules.md."""
        regiment = self._regiment(self.selected)
        if regiment is None:
            return "idle", None
        unit_class = regiment.hud_class
        if unit_class is None:
            return None, None  # classes with no command buttons at all
        if regiment.in_melee:
            return ("melee_caster" if self._caster(regiment) else "melee_noncaster"), unit_class
        if regiment.routing:
            # notes/game_rules.md's "broken or pursuing" has no separate "pursuing" flag in this
            # engine; routing is the closest and only available signal.
            return "rally", unit_class
        if regiment.attack_target is not None and not regiment.in_melee:
            # No explicit "charging" flag either; approximated as "moving to a declared target".
            return "charging", unit_class
        if self.panel_set == "attack":
            return ("attack_caster" if self._caster(regiment) else "attack_noncaster"), unit_class
        return self.panel_set, unit_class

    def slots(self):
        state, unit_class = self.panel_state()
        if state is None:
            return {}
        return PANEL_LAYOUT.get((state, unit_class), {})

    def _button_enabled(self, name, regiment):
        if name not in ORDER_SUPPORTED and name not in SET_ENTRY:
            return False  # rendered per spec, but nothing in the engine can carry it out yet
        if name == "back":
            return True
        if regiment is None or not regiment.player or not regiment.active:
            return False
        if name == "halt":
            return regiment.moving
        return True

    # ------------------------------------------------------------------ hit testing

    def _panel_origin(self):
        return PANEL_RECT[0], PANEL_RECT[1]

    def _fixed_button_rects(self):
        panel_x, panel_y = self._panel_origin()
        for name, (pos, _frames, size) in FIXED_BUTTONS.items():
            yield name, pygame.Rect(panel_x + pos[0], panel_y + pos[1], *size)
        yield "pause", pygame.Rect(panel_x + PAUSE_POS[0], panel_y + PAUSE_POS[1], *PAUSE_SIZE)

    def _slot_rects(self):
        panel_x, panel_y = self._panel_origin()
        sub_x, sub_y = panel_x + COMMAND_SUBWINDOW[0], panel_y + COMMAND_SUBWINDOW[1]
        for slot, (x, y) in SLOT_POSITIONS.items():
            yield slot, pygame.Rect(sub_x + x, sub_y + y, *SLOT_SIZE)

    def occupies(self, pos):
        """Whether *pos* lands on any HUD chrome, including non-actionable pixels."""
        if self._draw_size is None:
            return False
        left, top, width, height = MINIMAP_RECT
        if pygame.Rect(left, top, width, height).collidepoint(pos):
            return True
        panel_left, panel_top, panel_width, panel_height = PANEL_RECT
        return pygame.Rect(panel_left, panel_top, panel_width, panel_height).collidepoint(pos)

    def hit_test(self, pos):
        """Return an enabled semantic command under *pos* ("pause", a fixed-button name, or a
        command name), otherwise None."""
        if self._draw_size is None:
            return None
        for name, rect in self._fixed_button_rects():
            if rect.collidepoint(pos):
                return name
        regiment = self._regiment(self.selected)
        slots = self.slots()
        for slot, rect in self._slot_rects():
            if rect.collidepoint(pos) and slot in slots and self._button_enabled(slots[slot], regiment):
                return slots[slot]
        return None

    def set_pressed(self, name):
        self.pressed = name

    def press(self, name):
        """Apply a clicked command's panel-navigation effect; returns the order to issue, if any."""
        if name in SET_ENTRY:
            self.panel_set = SET_ENTRY[name]
        if name in ("move", "attack"):
            self.pending_order = name
        elif name == "back":
            # notes/game_rules.md: "Any completed order or Back returns to idle."
            self.pending_order = None
        if name in ORDER_SUPPORTED and name not in ("move", "attack"):
            return name
        return None

    def order_completed(self):
        """Called once a pending move/attack order has actually been issued (a ground/minimap click)."""
        self.pending_order = None
        self.panel_set = "idle"

    # ------------------------------------------------------------------ minimap

    def _map_scale(self):
        left, top, width, height = MAP_AREA_RECT
        map_left, map_top = MINIMAP_RECT[0] + left, MINIMAP_RECT[1] + top
        return map_left, map_top, width, height

    def minimap_position(self, pos):
        """Convert a minimap pixel to BTS world coordinates, or return ``None`` off-map."""
        if self._draw_size is None or not self.field.width or not self.field.height:
            return None
        map_left, map_top, width, height = self._map_scale()
        if not pygame.Rect(map_left, map_top, width, height).collidepoint(pos):
            return None
        x = (pos[0] - map_left) / (width - 1) * self.field.width
        y = (1 - (pos[1] - map_top) / (height - 1)) * self.field.height
        return (x, y)

    def _world_to_map_pixel(self, x, y):
        map_left, map_top, width, height = self._map_scale()
        px = map_left + round(x / self.field.width * (width - 1))
        py = map_top + round((1 - y / self.field.height) * (height - 1))
        return px, py

    def _minimap_marker(self, regiment):
        banner = self._sheet(regiment.banner)
        return banner.frames[1] if banner is not None and len(banner.frames) > 1 else None

    def _minimap_regiments(self):
        """Active markers in persistent paint order; selecting a unit promotes it to the top."""
        order = self._marker_order
        identifiers = list(self.battle.regiments)
        order[:] = [identifier for identifier in order if identifier in self.battle.regiments]
        order.extend(identifier for identifier in identifiers if identifier not in order)
        return [self.battle.regiments[identifier] for identifier in order
                if self.battle.regiments[identifier].active]

    def _promote_marker(self, identifier):
        order = self._marker_order
        if self.battle is not None:
            order.extend(regiment_id for regiment_id in self.battle.regiments if regiment_id not in order)
        if identifier in order:
            order.remove(identifier)
        order.append(identifier)

    def minimap_regiment_at(self, pos):
        """Return the active regiment whose visible marker (dot or banner) was clicked, if any."""
        if self.battle is None or self.minimap_position(pos) is None:
            return None
        for regiment in reversed(self._minimap_regiments()):
            px, py = self._world_to_map_pixel(regiment.x, regiment.y)
            if abs(pos[0] - px) <= 4 and abs(pos[1] - py) <= 4:
                return regiment.identifier
        return None

    def click_minimap_tab(self, pos):
        """Handle a click on a marker-display-mode tab or the book; returns True if one was hit."""
        left, top = MINIMAP_RECT[0], MINIMAP_RECT[1]
        for index, ((x, y), _frames) in enumerate(MINIMAP_TABS):
            rect = pygame.Rect(left + x, top + y, *MINIMAP_TAB_SIZE)
            if rect.collidepoint(pos):
                self.marker_mode = MARKER_MODES[index]
                return True
        book_rect = pygame.Rect(left + MINIMAP_BOOK_POS[0], top + MINIMAP_BOOK_POS[1], *MINIMAP_BOOK_SIZE)
        return bool(book_rect.collidepoint(pos))

    def _regiment_dot_frame(self, regiment):
        if regiment.in_melee or regiment.attack_target is not None:
            state = "fighting"
        elif regiment.routing:
            state = "broken"
        else:
            state = "normal"
        facing = round((regiment.direction % 512) / 64) % 8
        return DOT_BASE[(state, regiment.player)] + facing

    def _shows_banner(self, regiment):
        if self.marker_mode == 0:
            return True
        if self.marker_mode == 1:
            return regiment.identifier == self.selected
        if self.marker_mode == 2:
            return regiment.player
        return False  # mode 3: banners only in deployment, which this engine does not model yet

    def _draw_minimap(self, regiment):
        left, top = MINIMAP_RECT[0], MINIMAP_RECT[1]
        for index, position, _size in MINIMAP_LAYERS:
            quad = self.minimap_layers.get(index)
            if quad:
                quad.draw(left + position[0], top + position[1], *quad.size)
        if self.planmap and self.planmap.frames:
            frame = self.planmap.frames[0]
            self._sheet_frame_quad(frame).draw(*self._map_scale()[:2], *self._map_scale()[2:])
        # Deployment zone squares (ICONS frame 160) are skipped: this engine has no deployment
        # phase yet (battles start already deployed, whshr.engine.Battle.from_battle_file), so the
        # "deployment only" condition never holds.
        if self.battle is not None:
            if regiment is not None and self.selected is not None:
                waypoint = None
                if regiment.target_x is not None and regiment.target_y is not None:
                    waypoint = (regiment.target_x, regiment.target_y)
                if waypoint is not None:
                    quad = self._icon(WAYPOINT_END_FRAME)
                    if quad:
                        px, py = self._world_to_map_pixel(*waypoint)
                        quad.draw(px - quad.size[0] // 2, py - quad.size[1] // 2, *quad.size)
            for member in self._minimap_regiments():
                self._draw_regiment_marker(member)
            if regiment is not None and regiment.active:
                self._draw_regiment_marker(regiment)
        for (x, y), frames in MINIMAP_TABS:
            quad = self._icon(frames[0])
            if quad:
                quad.draw(left + x, top + y, *MINIMAP_TAB_SIZE)
        book = self._icon(MINIMAP_BOOK_FRAMES[0])
        if book:
            book.draw(left + MINIMAP_BOOK_POS[0], top + MINIMAP_BOOK_POS[1], *MINIMAP_BOOK_SIZE)

    def _draw_regiment_marker(self, regiment):
        px, py = self._world_to_map_pixel(regiment.x, regiment.y)
        dot = self._icon(self._regiment_dot_frame(regiment))
        if dot:
            dot.draw(px - dot.size[0] // 2, py - dot.size[1] // 2, *dot.size)
        if self._shows_banner(regiment):
            marker = self._minimap_marker(regiment)
            if marker is not None:
                quad = self._sheet_frame_quad(marker)
                quad.draw(px - 8, py - 24, *quad.size)

    # ------------------------------------------------------------------ readout

    def _readout_ornament_frames(self, regiment):
        """notes/game_rules.md: 181-188 default, 189-196 enemy, 197-204 wizard/monster - which class
        bits actually pick the frame set is 🟡. PROVISIONAL: wizard/monster is checked ahead of
        enemy here (an enemy wizard/monster gets the wizard/monster set), an unconfirmed priority."""
        if regiment is None:
            return None
        if regiment.hud_class in ("wiz", "mon"):
            base = 197
        elif not regiment.player:
            base = 189
        else:
            base = 181
        return tuple(range(base, base + 8))

    def _draw_readout(self, regiment):
        panel_x, panel_y = self._panel_origin()
        rx, ry = panel_x + READOUT_RECT[0], panel_y + READOUT_RECT[1]
        if regiment is None:
            for quad in self.compass_quads:
                if quad:
                    quad.draw(rx + 4, ry + 12, *quad.size)
            return
        if self.portrait_bg_quad:
            self.portrait_bg_quad.draw(rx + 4, ry + 12, *self.portrait_bg_quad.size)
        portrait_sheet = self._sheet(regiment.portrait)
        if portrait_sheet is not None and portrait_sheet.frames:
            portrait_quad = self._sheet_frame_quad(portrait_sheet.frames[0])
            portrait_quad.draw(rx + 4, ry + 12, *portrait_quad.size)
        for frame_index in self._readout_ornament_frames(regiment) or ():
            quad = self._icon(frame_index)
            if quad:
                # Ornament piece offsets within the readout are not individually given by
                # notes/game_rules.md ("fixed offsets"); PROVISIONAL until confirmed.
                quad.draw(rx, ry, *quad.size)

    # ------------------------------------------------------------------ draw

    def draw(self, width, height, camera=None):
        self._draw_size = (width, height)
        panel_x, panel_y = self._panel_origin()
        if self.panel_bg:
            self.panel_bg.draw(panel_x, panel_y, *self.panel_bg.size)
        regiment = self._regiment(self.selected)
        self._draw_readout(regiment)
        self._draw_fixed_buttons()
        self._draw_slots(regiment)
        self._draw_minimap(regiment)
        if camera is not None:
            self._draw_camera_marker(camera)

    def _draw_fixed_buttons(self):
        panel_x, panel_y = self._panel_origin()
        for name, (pos, frames, size) in FIXED_BUTTONS.items():
            pressed = self.pressed == name
            quad = self._icon(frames[1] if pressed else frames[0])
            if quad:
                quad.draw(panel_x + pos[0], panel_y + pos[1], *size)
        deployment = self.panel_state()[0] == "deployment"
        pause_frames = PAUSE_FRAMES["deployment" if deployment else "battle"]
        pressed = self.pressed == "pause"
        quad = self._icon(pause_frames[1] if pressed else pause_frames[0])
        if quad:
            quad.draw(panel_x + PAUSE_POS[0], panel_y + PAUSE_POS[1], *PAUSE_SIZE)

    def _draw_slots(self, regiment):
        panel_x, panel_y = self._panel_origin()
        sub_x, sub_y = panel_x + COMMAND_SUBWINDOW[0], panel_y + COMMAND_SUBWINDOW[1]
        for slot, command in self.slots().items():
            x, y = SLOT_POSITIONS[slot]
            frames = COMMAND_FRAMES.get(command)
            if not frames:
                continue
            enabled = self._button_enabled(command, regiment)
            pressed = self.pressed == command
            frame_index = frames[1] if pressed and frames[1] != frames[0] else frames[0]
            quad = self._icon(frame_index)
            if quad:
                quad.draw(sub_x + x, sub_y + y, *SLOT_SIZE, tint=(1, 1, 1, 1) if enabled else (0.4, 0.4, 0.4, 0.85))

    def _draw_camera_marker(self, camera):
        px, py = self._world_to_map_pixel(camera.target_x, camera.target_y)
        facing = round((camera.yaw % 360) / 45) % 8
        quad = self._icon(CAMERA_MARKER_FRAMES[facing])
        if quad:
            quad.draw(px - quad.size[0] // 2, py - quad.size[1] // 2, *quad.size)

    def release(self):
        quads = [self.panel_bg, self.portrait_bg_quad, *self.compass_quads,
                *self._icon_cache.values(), *self._sheet_frame_cache.values()]
        for quad in quads:
            if quad:
                quad.release()
