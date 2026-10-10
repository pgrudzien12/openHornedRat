# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Battle HUD: the 640x480 screen's command panel, minimap and selected-unit readout.

Layout source: notes/game_rules.md "Battle HUD layout" (windows, fixed buttons, command
sub-window slots, per-state button sets, minimap, readout, feedback). Everything except text is a
frame of the installation's ICONS sheet (225 frames); nothing here is procedurally drawn chrome
invented by the engine.

Order dispatch: `whshr.engine.Battle` implements move, attack, Fire, halt, ranks, facing,
Independent, Fight harder, Rally and activated items. Not modelled: whether the Rally button shows the
rally-attempt state as pressed (notes/pursuit_restraint.md 3, untraced), so it does not. Other panel orders remain disabled until their engine paths exist.
Buttons for orders without engine support still render at their documented position and icon (so
the panel looks and navigates correctly) but are disabled; panel-state *navigation* (which
sub-panel is shown) is implemented in full, since that is pure UI state independent of which
orders the engine can actually carry out.
"""

import math
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any

import pygame

from ..battlefield import WORLD_PER_MESH, Battlefield, SpriteFrame, SpriteSheet
from ..portrait_popup import overlay_frames
from ..rules import Side
from .gpu import Gpu, ScreenQuad

if TYPE_CHECKING:
    from ..camera import BattleCamera
    from ..engine import Battle, Regiment

Point = tuple[int, int]
Size = tuple[int, int]
Rect4 = tuple[int, int, int, int]
Tint = tuple[float, float, float, float]


def select_regiment_hit(hits: Sequence["Regiment"], selected: str | None) -> str | None:
    """Choose a plain-click selection from a bottom-to-top hit stack."""
    if not hits:
        return None
    top = hits[-1]
    if top.identifier != selected:
        return top.identifier
    others = hits[:-1]
    pool = [regiment for regiment in others if regiment.side == Side.PLAYER] or others
    return pool[0].identifier if pool else top.identifier


def order_target_hit(hits: Sequence["Regiment"], acting: "Regiment | None") -> str | None:
    """Choose an Attack/Fire target from a bottom-to-top hit stack: the topmost unit of another side than the
    acting regiment, else the topmost hit. Where friend and foe overlap (a melee scrum) the player means the foe.
    An engine choice, not a documented original rule."""
    if not hits:
        return None
    if acting is not None:
        for regiment in reversed(hits):
            if regiment.side != acting.side:
                return regiment.identifier
    return hits[-1].identifier


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
FIXED_BUTTONS: dict[str, tuple[Point, tuple[int, int], Size]] = {
    "camera_rotate": ((11, 8), (42, 43), (52, 52)),
    "camera_zoom": ((11, 63), (44, 45), (52, 52)),
    "options": ((448, 13), (58, 59), (44, 44)),
    "prev_regiment": ((448, 75), (60, 61), (44, 44)),
    "next_regiment": ((448, 121), (62, 63), (44, 44)),
    # notes/game_rules.md gives one documented position, (140, 4), for both 32x48 toggles (the
    # second's x inferred as immediately to the right); moved here to the panel's horizontal
    # center for a first visual pass at the user's request - adjust freely, this pair is not tied
    # to any other measurement.
    "toggle_a": ((337, 66), (64, 65), (32, 48)),
    "toggle_b": ((337, 66), (66, 67), (32, 48)),
    "scroll_up": ((424, 9), (68, 69), (20, 20)),
    "scroll_down": ((424, 34), (70, 71), (20, 20)),
}
# The pause/resume button at (11, 118) changes frame pair by context; it is not in FIXED_BUTTONS.
PAUSE_POS, PAUSE_SIZE = (11, 118), (52, 52)
PAUSE_FRAMES: dict[str, tuple[int, int]] = {"battle": (46, 47), "deployment": (48, 49), "paused": (50, 51)}
# Once the battle is decided the tent (panel record 4) replaces the pause button (notes/battle_end_objectives.md 6).
TENT_FRAMES = (50, 51)

# Command sub-window: 5 slots relative to COMMAND_SUBWINDOW's own origin, each 60x60.
SLOT_POSITIONS: dict[str, Point] = {"TL": (7, 11), "TR": (83, 11), "BR": (83, 109), "BL": (7, 109), "C": (45, 60)}
SLOT_SIZE = (60, 60)

# Command button frames: raised/pressed pair (a single-frame decoration repeats its own index).
COMMAND_FRAMES: dict[str, tuple[int, int]] = {
    "move": (0, 1), "attack": (2, 3), "fire": (4, 5), "magic": (6, 7), "items": (8, 9),
    "back": (10, 11), "turn_right": (12, 13), "turn_left": (14, 15), "about_face": (16, 17),
    "ranks_subset": (18, 19), "ranks_up": (20, 21), "ranks_down": (22, 23),
    "ranks_decoration": (24, 24), "facing_subset": (25, 26), "face_point": (35, 36),
    "halt": (37, 38), "rally": (37, 38), "withdraw": (39, 40), "independent": (52, 53),
    "charge": (54, 55), "fight_harder": (56, 57),
}
# Commands whshr.engine.Battle can actually carry out today; everything else in COMMAND_FRAMES
# renders (and, where it is a set-entry button, still navigates the panel) but is disabled.
ORDER_SUPPORTED: set[str] = {"move", "attack", "charge", "fire", "halt", "ranks_up", "ranks_down",
                   "turn_left", "turn_right", "about_face", "face_point", "independent", "fight_harder", "items", "rally"}
# Buttons that only change which sub-panel is shown (pure HUD state, always clickable when present).
SET_ENTRY: dict[str, str] = {"move": "move", "attack": "attack", "ranks_subset": "ranks", "facing_subset": "facing",
            "back": "idle"}
# Sub-panel navigation that deployment honours: only the facing sub-panel and its Back (§4.1 extension).
DEPLOYMENT_SET_ENTRY = frozenset({"facing_subset", "back"})

CLASSES = ("inf", "arch", "art", "wiz", "mon")
PANEL_LAYOUT: dict[tuple[str, str | None], dict[str, str]] = {}


def _set(state: str, classes: Sequence[str], **slots: str) -> None:
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

# notes/deployment.md §4 panels, plus one engine extension (§4.1, "Facing buttons"): the centre slot opens a
# facing sub-panel whose turns apply at once. For infantry and archers it replaces the rank decoration.
_set("deployment", ("inf", "arch"), TL="ranks_up", TR="move", BR="independent", BL="ranks_down",
    C="facing_subset")
_set("deployment", ("wiz", "mon"), TR="move", BR="independent", C="facing_subset")
_set("deployment", ("art",), BR="independent", C="facing_subset")
_set("deployment_facing", CLASSES, TL="turn_left", TR="turn_right", BL="about_face", BR="face_point", C="back")

_set("charging", CLASSES)  # none

# Minimap (relative to MINIMAP_RECT's own origin).
MINIMAP_LAYERS: tuple[tuple[str, Point, Size], ...] = (("101", (0, 0), (216, 16)), ("102", (0, 16), (16, 216)), ("103", (200, 16), (16, 216)),
                  ("104", (0, 233), (216, 64)))
MAP_AREA_RECT = (16, 17, 184, 216)
MINIMAP_TABS: tuple[tuple[Point, tuple[int, int]], ...] = (((63, 241), (72, 73)), ((110, 241), (74, 75)), ((63, 264), (76, 77)), ((110, 264), (78, 79)))
MINIMAP_TAB_SIZE = (44, 20)
MINIMAP_BOOK_POS, MINIMAP_BOOK_FRAMES, MINIMAP_BOOK_SIZE = (162, 242), (80, 81), (40, 40)
# Tab-to-mode order is not confirmed (notes/game_rules.md marks it 🟡); this assumes the tabs
# appear left to right in the documented mode order 0-3.
MARKER_MODES = (0, 1, 2, 3)
DEPLOYMENT_ZONE_FRAME = 160
# Numbered waypoint dots for a queued multi-stop order; whshr.engine.Regiment has only one
# target_x/target_y (no queue), so only WAYPOINT_END_FRAME is ever drawn today.
WAYPOINT_FRAMES = tuple(range(161, 170))
WAYPOINT_END_FRAME = 159
CAMERA_MARKER_FRAMES = tuple(range(170, 178))
CAMERA_TARGET_FRAME = 178  # small "x", the ICONS frame right after the 8 camera-marker frames
# Regiment dot base frame per (fighting-or-charging, side); add the 0-7 facing index. Broken adds
# the same offset from its own base.
DOT_BASE: dict[tuple[str, bool], int] = {
    ("fighting", True): 119, ("fighting", False): 111,
    ("normal", True): 135, ("normal", False): 127,
    ("broken", True): 151, ("broken", False): 143,
}
COMPASS_FRAMES = (99, 105)

# Battle log panel: 4-line scrollable message area, left of the scroll arrows (panel-native coords).
# Scroll arrows are at (424, 9) and (424, 34); readout ends at ~200; log fills the space between.
LOG_RECT = (200, 8, 223, 51)
# Unit info panel: below the log, left of the toggle buttons at (337, 66).
UNIT_INFO_RECT = (204, 71, 128, 36)

HUD_CLASS_NAMES: dict[str, str] = {
    "inf": "Infantry", "arch": "Archers", "art": "Artillery",
    "wiz": "Wizard", "mon": "Monster",
}

BLACK = (0, 0, 0)


def frame_rgba(frame: SpriteFrame, palette: Sequence[tuple[int, int, int]]) -> bytes:
    """Convert a decoded indexed frame to top-down RGBA for a ScreenQuad."""
    rgba = bytearray(frame.width * frame.height * 4)
    for offset, index in enumerate(frame.pixels):
        rgba[offset * 4:offset * 4 + 4] = (*palette[index], 0 if index == 0 else 255)
    return bytes(rgba)


class Hud:
    """Battle chrome built from the installation's ICONS sheet and the field's portrait/plan-map art."""

    def __init__(self, gpu: Gpu, field: Battlefield) -> None:
        self.gpu, self.field = gpu, field
        self.icons = self._sheet("icons")
        self.panel_bg = self._quad(self.icons, PANEL_BG_FRAME)
        self.portrait_bg = self._sheet(field.script["field"].get("portrait_bg"))
        self.portrait_bg_quad = self._quad(self.portrait_bg, 0)
        self.planmap = self._sheet(field.script["field"].get("planmap"))
        self._icon_cache: dict[int, ScreenQuad | None] = {}  # ICONS frame index -> ScreenQuad, built lazily and kept for the view's life
        self._sheet_frame_cache: dict[int, ScreenQuad] = {}  # id(frame) -> ScreenQuad, for portrait/banner/plan-map frames outside ICONS
        self.minimap_layers = {index: self._icon(int(index)) for index, _pos, _size in MINIMAP_LAYERS}
        self.compass_quads = tuple(self._icon(f) for f in COMPASS_FRAMES)
        self.selected: str | None = None
        self.battle: Battle | None = None
        self.marker_mode = 0
        self.panel_set = "idle"  # HUD-local sub-panel navigation: idle/move/ranks/facing/attack
        self.pending_order: str | None = None  # "move" or "attack": next battlefield/minimap click issues it
        self.item_list_open = False
        self.item_list_owner: str | None = None
        self._item_labels: list[Any] = []
        self._used_item_check: ScreenQuad | None = None
        self._draw_size: Size | None = None
        # Name of the fixed button or command held down, for its pressed art; hit_test()'s return
        # value (fixed-button names and command names never collide).
        self.pressed: str | None = None
        self._marker_order: list[str] = []
        self._log_panel: Any = None
        self._unit_info_panel: Any = None

    def _size(self) -> Size:
        if self._draw_size is None:
            raise RuntimeError("the HUD has not been drawn yet")
        return self._draw_size

    def _scale(self) -> float:
        """The same integer-snap scale NativeScreenView._layout() uses (scene_view.py), applied to
        this HUD's native 640x480 design size. BattleView renders its 3D scene at full window
        resolution rather than through that native-screen letterboxing, but the HUD chrome itself
        is designed at the original's fixed 640x480, so its own pieces need scaling independently."""
        screen_width, screen_height = self._size()
        native_width, native_height = 640, 480
        exact = min(screen_width / native_width, screen_height / native_height)
        scale = max(1, round(exact))
        while scale > 1 and (native_width * scale > screen_width or native_height * scale > screen_height):
            scale -= 1
        if native_width * scale > screen_width or native_height * scale > screen_height:
            scale = exact
        return scale

    def _panel_screen_origin(self) -> tuple[float, float, float]:
        """(left, top, scale) placing the command panel's own (0, 0) on screen, pinned to the
        bottom of the actual window and centered horizontally - not assuming the window itself is
        640x480, per the user's report that a centered 640x480 letterbox left the panel and
        minimap stranded in the middle of a larger window instead of hugging its edges."""
        scale = self._scale()
        screen_width, screen_height = self._size()
        panel_width, panel_height = PANEL_RECT[2] * scale, PANEL_RECT[3] * scale
        return (screen_width - panel_width) / 2, screen_height - panel_height, scale

    def _minimap_screen_origin(self) -> tuple[float, float, float]:
        """(left, top, scale) placing the minimap's own (0, 0) on screen, pinned to the top-right
        corner of the actual window (keeping the original's own top inset)."""
        scale = self._scale()
        screen_width, _screen_height = self._size()
        return screen_width - MINIMAP_RECT[2] * scale, MINIMAP_RECT[1] * scale, scale

    def _panel_screen_rect(self) -> pygame.Rect:
        left, top, scale = self._panel_screen_origin()
        return pygame.Rect(left, top, PANEL_RECT[2] * scale, PANEL_RECT[3] * scale)

    def _minimap_screen_rect(self) -> pygame.Rect:
        left, top, scale = self._minimap_screen_origin()
        return pygame.Rect(left, top, MINIMAP_RECT[2] * scale, MINIMAP_RECT[3] * scale)

    def _native_panel_point(self, pos: Sequence[float]) -> tuple[float, float]:
        """A raw window pixel converted into the command panel's own native-space coordinates."""
        left, top, scale = self._panel_screen_origin()
        return ((pos[0] - left) / scale, (pos[1] - top) / scale)

    def _native_map_point(self, pos: Sequence[float]) -> tuple[float, float]:
        """A raw window pixel converted into the minimap's own native-space coordinates."""
        left, top, scale = self._minimap_screen_origin()
        return ((pos[0] - left) / scale, (pos[1] - top) / scale)

    @staticmethod
    def _draw_at(origin: tuple[float, float, float], quad: ScreenQuad | None, x: float, y: float,
                 w: float | None = None, h: float | None = None, **kwargs: Any) -> None:
        if quad is None:
            return
        left, top, scale = origin
        w = quad.size[0] if w is None else w
        h = quad.size[1] if h is None else h
        quad.draw(left + x * scale, top + y * scale, w * scale, h * scale, **kwargs)

    def _draw_panel(self, quad: ScreenQuad | None, x: float, y: float, w: float | None = None,
                    h: float | None = None, **kwargs: Any) -> None:
        """Draw one quad at a panel-native (x, y[, w, h]) rect, scaled onto the actual window."""
        self._draw_at(self._panel_screen_origin(), quad, x, y, w, h, **kwargs)

    def _draw_map(self, quad: ScreenQuad | None, x: float, y: float, w: float | None = None,
                  h: float | None = None, **kwargs: Any) -> None:
        """Draw one quad at a minimap-native (x, y[, w, h]) rect, scaled onto the actual window."""
        self._draw_at(self._minimap_screen_origin(), quad, x, y, w, h, **kwargs)

    def _sheet(self, name: str | None) -> SpriteSheet | None:
        return self.field.ui_sheets.get(name.casefold()) if name else None

    def _quad(self, sheet: SpriteSheet | None, index: int) -> ScreenQuad | None:
        if sheet is None or index >= len(sheet.frames):
            return None
        frame = sheet.frames[index]
        quad = ScreenQuad(self.gpu, (frame.width, frame.height))
        quad.write(frame_rgba(frame, self.field.palette))
        return quad

    def _icon(self, frame_index: int) -> ScreenQuad | None:
        """A cached ICONS-sheet quad. Built once per frame index and reused: every draw()-time
        caller needs this cache, since a fresh ScreenQuad recreates a GPU texture (the earlier
        cause of a severe FPS drop when a similar mistake was made in troop_selection_view.py)."""
        if frame_index not in self._icon_cache:
            self._icon_cache[frame_index] = self._quad(self.icons, frame_index)
        return self._icon_cache[frame_index]

    def _sheet_frame_quad(self, frame: SpriteFrame) -> ScreenQuad:
        key = id(frame)
        quad = self._sheet_frame_cache.get(key)
        if quad is None:
            quad = ScreenQuad(self.gpu, (frame.width, frame.height))
            quad.write(frame_rgba(frame, self.field.palette))
            self._sheet_frame_cache[key] = quad
        return quad

    # ------------------------------------------------------------------ selection and panel state

    def set_selected(self, regiment_id: str | None) -> None:
        """Select a regiment and rebuild only its portrait/ornament art when it changes."""
        if regiment_id == self.selected:
            return
        self.selected = regiment_id
        self.item_list_open = False
        self.item_list_owner = None
        self.panel_set = "idle"
        self.pending_order = None
        if regiment_id is not None:
            self._promote_marker(regiment_id)

    def set_portrait(self, regiment_id: str | None) -> None:
        """Compatibility name for selecting the HUD regiment."""
        self.set_selected(regiment_id)

    def bind_battle(self, battle: "Battle") -> None:
        self.battle = battle

    def _regiment(self, identifier: str | None) -> "Regiment | None":
        return self.battle.regiments.get(identifier) if self.battle is not None and identifier is not None else None

    def _caster(self, regiment: "Regiment") -> bool:
        return bool(regiment.items) and regiment.living_leader_index is not None

    def panel_state(self) -> tuple[str | None, str | None]:
        """(state, unit_class) selecting a row of PANEL_LAYOUT, per notes/game_rules.md."""
        regiment = self._regiment(self.selected)
        if self.battle is not None and self.battle.phase == "deployment":
            if regiment is None or regiment.side != Side.PLAYER:
                return "deployment", None
            if self.panel_set == "facing" and regiment.hud_class is not None:
                return "deployment_facing", regiment.hud_class
            return "deployment", regiment.hud_class
        if regiment is None:
            return "idle", None
        unit_class = regiment.hud_class
        if unit_class is None:
            return None, None  # classes with no command buttons at all
        if (not regiment.in_melee and (regiment.charge_started_target is not None
                and regiment.charge_started_target == regiment.attack_target
                or regiment.free_charging and regiment.moving)):
            return "charging", unit_class
        if regiment.in_melee or regiment.braced:
            return ("melee_caster" if self._caster(regiment) else "melee_noncaster"), unit_class
        if regiment.routing or regiment.pursuing:
            # Broken and pursuing units use the same Rally command set.
            return "rally", unit_class
        if self.panel_set == "attack":
            return ("attack_caster" if self._caster(regiment) else "attack_noncaster"), unit_class
        return self.panel_set, unit_class

    def slots(self) -> dict[str, str]:
        state, unit_class = self.panel_state()
        if state is None:
            return {}
        return PANEL_LAYOUT.get((state, unit_class), {})

    def _button_enabled(self, name: str, regiment: "Regiment | None") -> bool:
        if self.battle is not None and self.battle.phase == "deployment" and name not in self.slots().values():
            return False
        if name not in ORDER_SUPPORTED and name not in SET_ENTRY:
            return False  # rendered per spec, but nothing in the engine can carry it out yet
        if name == "back":
            return True
        if regiment is None or regiment.side != Side.PLAYER or not regiment.active:
            return False
        if name == "halt":
            return regiment.moving
        if name == "fire":
            return regiment.hud_class in {"arch", "art"} and bool(regiment.missile_range)
        if name == "items":
            return bool(regiment.items) and regiment.living_leader_index is not None
        return True

    # ------------------------------------------------------------------ hit testing

    def _fixed_button_rects(self) -> Iterator[tuple[str, pygame.Rect]]:
        for name, (pos, _frames, size) in FIXED_BUTTONS.items():
            yield name, pygame.Rect(pos[0], pos[1], *size)
        yield self._pause_slot_action(), pygame.Rect(PAUSE_POS[0], PAUSE_POS[1], *PAUSE_SIZE)

    def _pause_slot_action(self) -> str:
        if self.battle is not None and self.battle.phase == "deployment":
            return "start_battle"
        return "leave_battle" if self.battle is not None and self.battle.can_leave else "pause"

    def _slot_rects(self) -> Iterator[tuple[str, pygame.Rect]]:
        sub_x, sub_y = COMMAND_SUBWINDOW[0], COMMAND_SUBWINDOW[1]
        for slot, (x, y) in SLOT_POSITIONS.items():
            yield slot, pygame.Rect(sub_x + x, sub_y + y, *SLOT_SIZE)

    def occupies(self, pos: Sequence[float]) -> bool:
        """Whether *pos* lands on any HUD chrome, including non-actionable pixels."""
        if self._draw_size is None:
            return False
        return self._minimap_screen_rect().collidepoint(pos) or self._panel_screen_rect().collidepoint(pos)

    def hit_test(self, pos: Sequence[float]) -> str | None:
        """Return an enabled semantic command under *pos* ("pause", a fixed-button name, or a
        command name), otherwise None."""
        if self._draw_size is None or not self._panel_screen_rect().collidepoint(pos):
            return None
        native = self._native_panel_point(pos)
        if getattr(self, "item_list_open", False) and getattr(self, "item_list_owner", self.selected) == self.selected:
            regiment = self._regiment(self.selected)
            if regiment is not None:
                for index, item in enumerate(regiment.items[:5]):
                    if (item in {"ItemBannerOfWrath", "ItemGrudgeBringer", "ItemPotionOfStrength"}
                            and item not in regiment.used_items
                            and regiment.living_leader_index is not None
                            and pygame.Rect(205, 72 + index * 19, 232, 18).collidepoint(native)):
                        return f"item:{item}"
        for name, rect in self._fixed_button_rects():
            if rect.collidepoint(native):
                return name
        regiment = self._regiment(self.selected)
        slots = self.slots()
        for slot, rect in self._slot_rects():
            if rect.collidepoint(native) and slot in slots and self._button_enabled(slots[slot], regiment):
                return slots[slot]
        return None

    def set_pressed(self, name: str | None) -> None:
        self.pressed = name

    def press(self, name: str) -> str | None:
        """Apply a clicked command's panel-navigation effect; returns the order to issue, if any."""
        if name == "start_battle":
            # The deployment facing sub-panel has no battle counterpart for every class; start on the idle panel.
            self.panel_set = "idle"
            self.pending_order = None
        if name in {"start_battle", "pause", "leave_battle", "next_regiment", "prev_regiment"}:
            return name
        if name == "items":
            self.item_list_open = not self.item_list_open
            self.item_list_owner = self.selected if self.item_list_open else None
            return None
        if name.startswith("item:"):
            self.item_list_open = False
            return name
        self.item_list_open = False
        if self.battle is not None and self.battle.phase == "deployment" and name not in self.slots().values():
            return None
        if name in SET_ENTRY and (name in DEPLOYMENT_SET_ENTRY
                                  or not (self.battle is not None and self.battle.phase == "deployment")):
            self.panel_set = SET_ENTRY[name]
        if name in ("move", "attack", "fire", "face_point"):
            self.pending_order = name
        elif name == "back":
            # notes/game_rules.md: "Any completed order or Back returns to idle."
            self.pending_order = None
        if name in ORDER_SUPPORTED and name not in ("move", "attack", "fire", "face_point"):
            return name
        return None

    def order_completed(self) -> None:
        """Called once a pending move/attack order has actually been issued (a ground/minimap click)."""
        self.pending_order = None
        self.panel_set = "idle"
        self.item_list_open = False

    def set_log(self, entries: Sequence[tuple[str, str]]) -> None:
        """Render (sender, message) pairs into the battle log panel (4 visible lines)."""
        if self._log_panel is None:
            self._log_panel = self.gpu.battle_log((LOG_RECT[2], LOG_RECT[3]), background=(0, 0, 0, 0))
        self._log_panel.set_entries(entries)

    def set_unit_info(self, name: str | None, unit_class: str | None, models: int | None,
                      max_models: int | None) -> None:
        """Render selected unit name, class and casualty count into the info panel."""
        if self._unit_info_panel is None:
            self._unit_info_panel = self.gpu.unit_info((UNIT_INFO_RECT[2], UNIT_INFO_RECT[3]), background=(0, 0, 0, 0))
        class_name = HUD_CLASS_NAMES.get(unit_class or "", unit_class or "")
        self._unit_info_panel.set_info(name, class_name, models, max_models)

    # ------------------------------------------------------------------ minimap

    def _map_scale(self) -> Rect4:
        return MAP_AREA_RECT

    def minimap_position(self, pos: Sequence[float]) -> tuple[float, float] | None:
        """Convert a raw window pixel to BTS world coordinates, or return ``None`` off-map."""
        if (self._draw_size is None or not self.field.width or not self.field.height
                or not self._minimap_screen_rect().collidepoint(pos)):
            return None
        native = self._native_map_point(pos)
        map_left, map_top, width, height = self._map_scale()
        if not pygame.Rect(map_left, map_top, width, height).collidepoint(native):
            return None
        x = (native[0] - map_left) / (width - 1) * self.field.width
        y = (1 - (native[1] - map_top) / (height - 1)) * self.field.height
        return (x, y)

    def minimap_delta(self, delta: Sequence[float]) -> tuple[float, float]:
        _, _, width, height = self._map_scale()
        return (delta[0] * self.field.width / (width - 1) / self._scale(),
                -delta[1] * self.field.height / (height - 1) / self._scale())

    def _world_to_map_pixel(self, x: float, y: float) -> tuple[int, int]:
        map_left, map_top, width, height = self._map_scale()
        px = map_left + round(x / self.field.width * (width - 1))
        py = map_top + round((1 - y / self.field.height) * (height - 1))
        return px, py

    def _minimap_marker(self, regiment: "Regiment") -> SpriteFrame | None:
        banner = self._sheet(regiment.banner)
        return banner.frames[1] if banner is not None and len(banner.frames) > 1 else None

    def _minimap_regiments(self) -> list["Regiment"]:
        """Active markers in persistent paint order; selecting a unit promotes it to the top."""
        battle = self._battle()
        order = self._marker_order
        identifiers = list(battle.regiments)
        order[:] = [identifier for identifier in order if identifier in battle.regiments]
        order.extend(identifier for identifier in identifiers if identifier not in order)
        return [battle.regiments[identifier] for identifier in order
                if battle.regiments[identifier].active and battle.regiments[identifier].visible_to_player]

    def _battle(self) -> "Battle":
        if self.battle is None:
            raise RuntimeError("the HUD is not bound to a battle")
        return self.battle

    def _promote_marker(self, identifier: str) -> None:
        order = self._marker_order
        if self.battle is not None:
            order.extend(regiment_id for regiment_id in self.battle.regiments if regiment_id not in order)
        if identifier in order:
            order.remove(identifier)
        order.append(identifier)

    def _marker_hit(self, regiment: "Regiment", native: Sequence[float]) -> bool:
        """Whether *native* (already minimap-local) lands on this regiment's dot or, when shown,
        its banner - the banner is hit over its own drawn rect, not just the dot underneath it,
        since it is the larger and more obvious target on screen."""
        px, py = self._world_to_map_pixel(regiment.x, regiment.y)
        if abs(native[0] - px) <= 4 and abs(native[1] - py) <= 4:
            return True
        if self._shows_banner(regiment):
            marker = self._minimap_marker(regiment)
            if marker is not None:
                banner_rect = pygame.Rect(px - 8, py - 24, marker.width, marker.height)
                if banner_rect.collidepoint(native):
                    return True
        return False

    def _marker_hits(self, pos: Sequence[float]) -> list["Regiment"] | None:
        """Regiments whose marker (dot or banner) covers the raw window pixel *pos*, in normal
        bottom-to-top paint order, or None if *pos* is not on the minimap at all."""
        if self.battle is None or self._draw_size is None or not self._minimap_screen_rect().collidepoint(pos):
            return None
        native = self._native_map_point(pos)
        return [regiment for regiment in self._minimap_regiments() if self._marker_hit(regiment, native)]

    def minimap_regiment_at(self, pos: Sequence[float]) -> str | None:
        """Return the active regiment a plain click at *pos* should select, or None if none is hit.

        Several markers (dots and/or banners) can overlap at one point - most often several
        regiments' banners near each other on the minimap. Clicking there always hits the whole
        stack, in its normal top-to-bottom paint order (whichever marker is drawn last is "on
        top"): if the topmost hit regiment is not already selected, it wins, same as a single
        unambiguous hit. If it *is* already selected, clicking again cycles one step down the
        stack instead of doing nothing: it picks the bottom-most other regiment in the stack that
        is friendly (falling back to the bottom-most of any side if none is), which
        set_selected()/_promote_marker() then promote to the top of the paint order - so repeated
        clicks on the same spot step through every regiment there, friendly ones first.

        If the selected regiment is elsewhere in the stack but not on top, this treats it the same
        as not being in the stack at all (selects the top one) rather than special-casing a third
        rule - simpler, and topmost-wins is the expected default whenever the exact previously
        picked regiment isn't being re-clicked."""
        return select_regiment_hit(self._marker_hits(pos) or (), self.selected)

    def minimap_target_at(self, pos: Sequence[float]) -> str | None:
        """Return the topmost active regiment at *pos*, ignoring current selection entirely - for
        resolving an order's target (Attack). Unlike a plain click (minimap_regiment_at()'s
        cycle-when-already-selected rule, meant for picking a unit to inspect or command),
        commanding an attack against an overlapping stack always targets the topmost unit of another
        side than the selection (order_target_hit), with no cycling: the cycling rule exists to make an otherwise-stuck
        selection reachable, which does not apply here since the order's own acting regiment
        (self.selected) is essentially never the one being targeted."""
        hits = self._marker_hits(pos)
        return order_target_hit(hits or [], self._regiment(self.selected))

    def click_minimap_tab(self, pos: Sequence[float]) -> str | None:
        """Handle a click on a marker-display-mode tab or the book: "tab", "book" or None when neither was hit."""
        if self._draw_size is None or not self._minimap_screen_rect().collidepoint(pos):
            return None
        native = self._native_map_point(pos)
        for index, ((x, y), _frames) in enumerate(MINIMAP_TABS):
            rect = pygame.Rect(x, y, *MINIMAP_TAB_SIZE)
            if rect.collidepoint(native):
                self.marker_mode = MARKER_MODES[index]
                return "tab"
        book_rect = pygame.Rect(MINIMAP_BOOK_POS[0], MINIMAP_BOOK_POS[1], *MINIMAP_BOOK_SIZE)
        return "book" if book_rect.collidepoint(native) else None

    def _regiment_dot_frame(self, regiment: "Regiment") -> int:
        if regiment.in_melee or regiment.attack_target is not None:
            state = "fighting"
        elif regiment.routing:
            state = "broken"
        else:
            state = "normal"
        facing = round((regiment.direction % 512) / 64) % 8
        # No third minimap dot frame is documented for a neutral regiment (game_rules.md), so it
        # falls back to the non-player set, same as an enemy.
        return DOT_BASE[(state, regiment.side == Side.PLAYER)] + facing

    def _shows_banner(self, regiment: "Regiment") -> bool:
        if self.marker_mode == 0:
            return True
        if self.marker_mode == 1:
            return regiment.identifier == self.selected
        if self.marker_mode == 2:
            return regiment.side == Side.PLAYER
        return self._battle().phase == "deployment" and regiment.side == Side.PLAYER

    def deployment_markers(self) -> list[tuple[int, int]]:
        """Boundary marker positions derived from geometry at minimap pixel scale."""
        if self.battle is None or self.battle.phase != "deployment":
            return []
        points: list[tuple[int, int]] = []
        for region in self.battle.deployment_regions:
            for x1, y1, x2, y2 in region.lines:
                a, b = self._world_to_map_pixel(x1, y1), self._world_to_map_pixel(x2, y2)
                steps = max(1, math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / 8))
                points.extend(self._world_to_map_pixel(x1 + (x2 - x1) * i / steps,
                                                      y1 + (y2 - y1) * i / steps)
                              for i in range(steps + 1))
        return list(dict.fromkeys(points))

    def _draw_minimap(self, regiment: "Regiment | None", camera: "BattleCamera | None" = None) -> None:
        for index, position, _size in MINIMAP_LAYERS:
            self._draw_map(self.minimap_layers.get(index), position[0], position[1])
        if self.planmap and self.planmap.frames:
            frame = self.planmap.frames[0]
            map_left, map_top, map_width, map_height = self._map_scale()
            self._draw_map(self._sheet_frame_quad(frame), map_left, map_top, map_width, map_height)
        if camera is not None:
            # Drawn right above the plan map and nothing else, so every other minimap element
            # (waypoints, regiments, tabs) paints over it.
            self._draw_camera_target(camera)
        for x, y in self.deployment_markers():
            self._draw_map(self._icon(DEPLOYMENT_ZONE_FRAME), x - 4, y - 4, 8, 8)
        if self.battle is not None:
            if regiment is not None and self.selected is not None:
                waypoints = list(regiment.waypoints)
                if not waypoints and regiment.target_x is not None and regiment.target_y is not None:
                    waypoints = [(regiment.target_x, regiment.target_y)]
                for index, waypoint in enumerate(waypoints):
                    frame = WAYPOINT_END_FRAME if index == len(waypoints) - 1 else WAYPOINT_FRAMES[min(index, 8)]
                    quad = self._icon(frame)
                    if quad:
                        px, py = self._world_to_map_pixel(*waypoint)
                        self._draw_map(quad, px - quad.size[0] // 2, py - quad.size[1] // 2)
            for member in self._minimap_regiments():
                self._draw_regiment_marker(member)
            if regiment is not None and regiment.active:
                self._draw_regiment_marker(regiment)
        for (x, y), frames in MINIMAP_TABS:
            self._draw_map(self._icon(frames[0]), x, y, *MINIMAP_TAB_SIZE)
        self._draw_map(self._icon(MINIMAP_BOOK_FRAMES[0]), MINIMAP_BOOK_POS[0], MINIMAP_BOOK_POS[1],
                       *MINIMAP_BOOK_SIZE)

    def _draw_regiment_marker(self, regiment: "Regiment") -> None:
        px, py = self._world_to_map_pixel(regiment.x, regiment.y)
        selected = regiment.identifier == self.selected
        # notes/game_rules.md does not document a selection indicator on the minimap; the
        # original had a white rim around the selected marker. A brightness tint on whichever
        # marker(s) are actually visible (dot and/or banner) approximates it without inventing an
        # undocumented extra frame.
        tint = (2.0, 2.0, 2.0, 1.0) if selected else (1.0, 1.0, 1.0, 1.0)
        dot = self._icon(self._regiment_dot_frame(regiment))
        if dot:
            self._draw_map(dot, px - dot.size[0] // 2, py - dot.size[1] // 2, tint=tint)
        if self._shows_banner(regiment):
            marker = self._minimap_marker(regiment)
            if marker is not None:
                quad = self._sheet_frame_quad(marker)
                self._draw_map(quad, px - 8, py - 24, tint=tint)

    # ------------------------------------------------------------------ readout

    def _readout_ornament_frames(self, regiment: "Regiment | None") -> tuple[int, ...] | None:
        """notes/game_rules.md: 181-188 default, 189-196 enemy, 197-204 wizard/monster - which class
        bits actually pick the frame set is 🟡. PROVISIONAL: wizard/monster is checked ahead of
        enemy here (an enemy wizard/monster gets the wizard/monster set), an unconfirmed priority."""
        if regiment is None:
            return None
        if regiment.hud_class in ("wiz", "mon"):
            base = 197
        elif regiment.side != Side.PLAYER:
            base = 189
        else:
            base = 181
        return tuple(range(base, base + 8))

    def _draw_readout(self, regiment: "Regiment | None") -> None:
        """The portrait rectangle: the compass, or the reacting unit's portrait while the pop-up is up
        (notes/react_portrait.md 3-4); selecting a regiment never changes it."""
        rx, ry = READOUT_RECT[0], READOUT_RECT[1]
        popup = self.battle.portrait_popup if self.battle is not None else None
        shown = self._regiment(popup.unit_id) if popup is not None and popup.active else None
        if popup is None or shown is None:
            for quad in self.compass_quads:
                self._draw_panel(quad, rx + 4, ry + 12)
            return
        self._draw_panel(self.portrait_bg_quad, rx + 4, ry + 12)
        portrait_sheet = self._sheet(shown.portrait)
        if portrait_sheet is not None and portrait_sheet.frames and shown.living_leader_index is not None:
            frames = portrait_sheet.frames
            eyes, mouth = overlay_frames(popup.expression, len(frames), popup.age)
            for index in (0, eyes, mouth):
                if index < len(frames):
                    self._draw_panel(self._sheet_frame_quad(frames[index]), rx + 4, ry + 12)
        for frame_index in self._readout_ornament_frames(shown) or ():
            # Ornament piece offsets within the readout are not individually given by
            # notes/game_rules.md ("fixed offsets"); PROVISIONAL until confirmed.
            self._draw_panel(self._icon(frame_index), rx, ry)

    # ------------------------------------------------------------------ draw

    def draw(self, width: int, height: int, camera: "BattleCamera | None" = None) -> None:
        self._draw_size = (width, height)
        self._draw_panel(self.panel_bg, 0, 0)
        regiment = self._regiment(self.selected)
        self._draw_readout(regiment)
        self._draw_fixed_buttons()
        self._draw_slots(regiment)
        self._draw_minimap(regiment, camera)
        if camera is not None:
            self._draw_camera_marker(camera)
        if self._log_panel is not None:
            self._draw_panel(self._log_panel, LOG_RECT[0], LOG_RECT[1],
                             LOG_RECT[2], LOG_RECT[3])
        if self._unit_info_panel is not None:
            self._draw_panel(self._unit_info_panel, UNIT_INFO_RECT[0], UNIT_INFO_RECT[1],
                             UNIT_INFO_RECT[2], UNIT_INFO_RECT[3])
        # The item list covers part of the unit-info rectangle; paint it last so the unit name
        # cannot appear over the popup's rows.
        self._draw_item_list(regiment)

    def _draw_fixed_buttons(self) -> None:
        for name, (pos, frames, size) in FIXED_BUTTONS.items():
            pressed = self.pressed == name
            quad = self._icon(frames[1] if pressed else frames[0])
            self._draw_panel(quad, pos[0], pos[1], *size)
        action = self._pause_slot_action()
        if action == "leave_battle":
            pause_frames = TENT_FRAMES
        else:
            paused = self.battle is not None and self.battle.paused
            pause_frames = PAUSE_FRAMES["deployment" if action == "start_battle" else "paused" if paused else "battle"]
        pressed = self.pressed == action
        quad = self._icon(pause_frames[1] if pressed else pause_frames[0])
        self._draw_panel(quad, PAUSE_POS[0], PAUSE_POS[1], *PAUSE_SIZE)

    def _draw_slots(self, regiment: "Regiment | None") -> None:
        sub_x, sub_y = COMMAND_SUBWINDOW[0], COMMAND_SUBWINDOW[1]
        for slot, command in self.slots().items():
            x, y = SLOT_POSITIONS[slot]
            frames = COMMAND_FRAMES.get(command)
            if not frames:
                continue
            enabled = self._button_enabled(command, regiment)
            pressed = self.pressed == command or command == "independent" and regiment is not None and regiment.independent
            frame_index = frames[1] if pressed and frames[1] != frames[0] else frames[0]
            quad = self._icon(frame_index)
            self._draw_panel(quad, sub_x + x, sub_y + y, *SLOT_SIZE,
                             tint=(1, 1, 1, 1) if enabled else (0.4, 0.4, 0.4, 0.85))

    def _draw_item_list(self, regiment: "Regiment | None") -> None:
        if not self.item_list_open or regiment is None:
            return
        if getattr(self, "item_list_owner", self.selected) != self.selected:
            return
        self._draw_panel(self._icon(205), 200, 64)
        for index, item in enumerate(regiment.items[:5]):
            while len(self._item_labels) <= index:
                self._item_labels.append(self.gpu.text((240, 18), self.gpu.battle_log_font,
                                                       background=None, padding=0))
            label = self._item_labels[index]
            label.set_lines((item.removeprefix("Item").replace("Of", " of ").replace("The", " the "),))
            enabled = (item in {"ItemBannerOfWrath", "ItemGrudgeBringer", "ItemPotionOfStrength"}
                       and item not in regiment.used_items and regiment.living_leader_index is not None)
            pressed = self.pressed == f"item:{item}" and enabled
            self._draw_panel(label, 205 + int(pressed), 72 + index * 19 + int(pressed), 232, 18,
                             tint=(1, 1, 1, 1) if enabled else (0.45, 0.45, 0.45, 0.85))
            if item in regiment.used_items:
                self._draw_panel(self._used_item_check_quad(), 420, 74 + index * 19)

    def _used_item_check_quad(self) -> ScreenQuad:
        if self._used_item_check is None:
            surface = pygame.Surface((14, 14), pygame.SRCALPHA)
            points = ((2, 7), (6, 11), (12, 2))
            pygame.draw.lines(surface, (18, 44, 18), False, points, 5)
            pygame.draw.lines(surface, (58, 220, 70), False, points, 3)
            self._used_item_check = ScreenQuad(self.gpu, surface.get_size())
            self._used_item_check.write(pygame.image.tobytes(surface, "RGBA"))
        return self._used_item_check

    def _draw_camera_target(self, camera: "BattleCamera") -> None:
        """A small "x" mark at the camera's look-at target (BattleCamera.target_x/y), the ICONS
        frame right after the 8 camera-marker frames. Drawn at the lowest z-order of anything but
        the plan map itself, so waypoints, regiments and the eye marker all paint over it."""
        px, py = self._world_to_map_pixel(camera.target_x, camera.target_y)
        quad = self._icon(CAMERA_TARGET_FRAME)
        if quad is None:
            return
        self._draw_map(quad, px - quad.size[0] // 2, py - quad.size[1] // 2)

    def _draw_camera_marker(self, camera: "BattleCamera") -> None:
        # The marker shows the camera's eye position, not its look-at target: the eye sits
        # pulled back from the target along yaw by the (mesh-to-world scaled) orbit distance,
        # matching how whshr/frontend/battle_view.py positions the camera for panning. The
        # marker is a flat minimap dot, so pitch does not affect its position.
        eye_x, eye_y = self._camera_eye_position(camera)
        px, py = self._world_to_map_pixel(eye_x, eye_y)
        # CAMERA_MARKER_FRAMES' own zero-rotation point sits a half-turn from yaw's (observed
        # against the running game: the marker pointed the opposite way it should); compensate.
        facing = (round((camera.yaw % 360) / 45) + 4) % 8
        quad = self._icon(CAMERA_MARKER_FRAMES[facing])
        if quad is None:
            return
        # The eye can sit far outside the battlefield (a large zoom distance pulls it well past
        # the map edge); clamp it to the map area rather than let it spill past the minimap chrome.
        map_left, map_top, width, height = self._map_scale()
        half_w, half_h = quad.size[0] // 2, quad.size[1] // 2
        px = min(max(px, map_left + half_w), map_left + width - 1 - half_w)
        py = min(max(py, map_top + half_h), map_top + height - 1 - half_h)
        self._draw_map(quad, px - half_w, py - half_h)

    @staticmethod
    def _camera_eye_position(camera: "BattleCamera") -> tuple[float, float]:
        # whshr.camera.BattleCamera.pan()'s forward (eye-to-target) direction is
        # (-sin yaw, -cos yaw); the eye sits `distance` back along the opposite direction.
        yaw = math.radians(camera.yaw)
        distance = camera.distance * WORLD_PER_MESH
        return (
            camera.target_x + distance * math.sin(yaw),
            camera.target_y + distance * math.cos(yaw),
        )

    def release(self) -> None:
        quads = [self.panel_bg, self.portrait_bg_quad, *self.compass_quads,
                *self._icon_cache.values(), *self._sheet_frame_cache.values()]
        for quad in quads:
            if quad:
                quad.release()
        if self._log_panel is not None:
            self._log_panel.release()
        if self._unit_info_panel is not None:
            self._unit_info_panel.release()
        for label in self._item_labels:
            label.release()
        if self._used_item_check is not None:
            self._used_item_check.release()
