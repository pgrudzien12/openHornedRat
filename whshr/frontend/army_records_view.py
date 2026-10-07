# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Army Records presentation: Ctrl-click from troop selection and the caravan's army books.

The native-screen constants below are deliberately local to this built-in front-end
screen (not WND.DLL data); see notes/troop_selection.md §8 and §8.1 and
notes/builtin_widgets.md §2.
"""

from collections.abc import Sequence
from typing import Any

import pygame

from ..campaign_scenes import ArmyRecordsScene
from ..glue_palette import AppPalette
from ..legacy import module
from ..portraits import BACKGROUND_SET, CROP_WINDOWS, LEADER_BOX_SIZE, NO_MATCH_CROP_WINDOW, load_sprite_sheet
from ..roster import Regiment
from ..scenes import SceneEvent
from ..script import resource_name
from .bitmap_font import BitmapFont
from .fancy_letters import CAPS
from .glue_bitmap import load_optional_bitmap
from .gpu import Gpu, QuadCache, ScreenQuad, TextLabel
from .scene_view import NativeScreenView


# notes/troop_selection.md §8.1.  Logical resource names are resolved from the
# user's BITMAP.DLL/BKTXT.DLL installation at runtime.
PICTURES: tuple[str | None, ...] = (
    "VanheimPic", "RagnarsWolvesPic", "Grudgebringers1Pic", "Grudgebringers2Pic",
    "BlackAvengersPic", "GreatswordsPic", "ReiksguardPic", "LeitdorfPic",
    "WoodElfArchersPic", "DwarvenSlayersPic", "DwarvenHammerersPic", "IronBreakersPic",
    "IronBreakersPic", "GyrocopterSquadronPic", "CannonCrewPic", "CannonCrewPic",
    "MortarCrewPic", "MortarCrewPic", "CelestialWizardPic", "BrightWizardPic", "AmberWizardPic",
    "CarlssonPic", "CarlssonPic", "DwarfWarriorsPic", "DwarfWarriorsPic", "VolleyGunPic",
    "NulnHalberdiersPic", "MercCrossbowmenPic", "LongbowsPic", "CeridanPic", "DwarfCrossbowPic",
    "DwarfEnvoyPic", None, "DwarfWarriorsPic", "TreemanPic", "CarlssonPic",
    "GyrocopterSquadronPic", "GyrocopterSquadronPic",
)
DESCRIPTIONS: tuple[str, ...] = (
    "VanheimText", "RagnarsWolvesText", "GrudgebringersText", "GrudgebringersText",
    "BlackAvengersText", "GreatswordsText", "ReiksguardText", "LeitdorfText", "WoodElfArchersText",
    "DwarvenSlayersText", "DwarvenHammerersText", "IronBreakersText", "IronBreakersText",
    "GyrocopterSquadronText", "ImperialCannonCrewText", "CannonCrewText", "MortarCrewText",
    "MortarCrewText", "CelestialWizardText", "BrightWizardText", "AmberWizardText", "CarlssonText",
    "CarlssonText", "DwarfWarriorsText", "DwarfWarriorsText", "VolleyGunText", "NulnHalberdiersText",
    "MercCrossbowmenText", "LongbowsText", "CeridanText", "DwarfCrossbowText", "DwarfEnvoyText",
    "NullText", "DwarfWarriorsText", "TreemanText", "CarlssonText", "GyrocopterSquadronText",
    "GyrocopterSquadronText",
)

# §8 buttons: logical action, x, resource tab base, BRTXT label.
Point = tuple[int, int]
Rgb = tuple[int, int, int]
BUTTONS: tuple[tuple[str, int, str, int | None], ...] = (
    ("book:stat-info", 14, "PurpleATab", 321), ("book:hire-fire", 104, "VioletATab", None),
    ("book:abort", 194, "BrownBTab", 307), ("book:done", 350, "GreenATab", 304),
    ("book:previous", 440, "BlueATab", 301), ("book:next", 530, "RedATab", 300),
)
BUTTON_Y, BUTTON_SIZE = 448, (84, 32)
# notes/builtin_widgets.md §2.4: the reinforcement sub-window is 144x134, centred in the book; the buttons are
# (action, offset in the window, size, bitmap): Take/Hire 116x20, +1 arrow (up) and -1 arrow (down) 11x13.
REINF_ORIGIN, REINF_SIZE = (248, 173), (144, 134)
REINF_BUTTONS: tuple[tuple[str, Point, Point, str], ...] = (
    ("reinf:take", (12, 110), (116, 20), "reinfButton"),
    ("reinf:up", (29, 85), (11, 13), "reinfArrowUp"),
    ("reinf:down", (104, 85), (11, 13), "reinfArrowDown"),
)
BLACK, GREY, YELLOW = (0, 0, 0), (127, 127, 127), (255, 255, 0)
NAME_INK: Rgb = (67, 47, 39)
# Content text is inset from each page's painted frame/spine (§8).  These are
# native ArmyBook presentation constants, not WND.DLL layout data.
LEFT_PAGE = (50, 290)
RIGHT_PAGE = (350, 590)


class ArmyRecordsView(NativeScreenView[ArmyRecordsScene]):
    """Render either variant of the book (selection or caravan) and translate its page controls."""

    def __init__(self, gpu: Gpu, scene: ArmyRecordsScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        self.bitmap_quads = QuadCache(gpu)
        self.content = scene.glue_scene.require_runtime().content
        self.body_font = BitmapFont(scene.glue_scene.font(2))
        self.heading_font = BitmapFont(scene.glue_scene.font(4))
        self.name_font = BitmapFont(scene.glue_scene.font(5))
        self.palette = AppPalette.select(9, self.content.palette_tables())
        self.quads: list[tuple[ScreenQuad, Point]] = []
        self.labels: list[tuple[TextLabel, Point]] = []
        self.overlay_quad_start = 0
        self.overlay_label_start = 0
        self.buttons: list[tuple[pygame.Rect, str]] = []
        self.pressed_button: str | None = None
        # Information is the documented default page (builtin_widgets.md §2.2).
        self.info = True
        self.state: tuple[Any, ...] | None = None
        self._description_cache: dict[str, str] = {}
        self.sprite_files: dict[str, str] | None = None
        self.sprite_surfaces: dict[tuple[str, int], pygame.Surface | None] = {}
        self.crop_surfaces: dict[tuple[str, Point], pygame.Surface | None] = {}
        self.refresh()

    def refresh(self) -> None:
        model = self.scene.model
        ledger = model.ledger
        state = (self.scene.whoami, self.info, tuple(sorted(model.hired.items())), self.pressed_button,
                 tuple(sorted((whoami, regiment.models) for whoami, regiment in model.company.items())),
                 tuple(sorted(ledger.offered.items())), tuple(sorted(ledger.taken.items())),
                 tuple(sorted(ledger.wounded.items())), model.dirty)
        if state == self.state:
            return
        self.state = state
        self._release_contents()
        self._bitmap("ArmyBook", (0, 0))
        regiment = self.scene.model.company[self.scene.whoami]
        self._left_page(regiment)
        self._right_page(regiment)
        self._buttons(regiment)
        self.overlay_quad_start = len(self.quads)
        self.overlay_label_start = len(self.labels)
        self._reinforcement_window(regiment)

    def _left_page(self, regiment: Regiment) -> None:
        height = self.body_font.font.height
        cost_y = 410 - height
        # The selection variant always uses the normal cost/retainer line; a regiment that was not hired when
        # the hire-only caravan book opened shows only its fee (BKTXT 509, notes/builtin_widgets.md §2.2).
        model = self.scene.model
        if model.pays and not self.scene.hired_at_open[regiment.whoami]:
            cost = self._string("BKTXT", 509, regiment.price)
        else:
            cost = self._string("BKTXT", 501, regiment.price, regiment.retainer)
        self._center(cost, cost_y, BLACK, x=LEFT_PAGE[0], width=240)
        self._center(self._string("BKTXT", 500, regiment.experience), cost_y - height, BLACK,
                     x=LEFT_PAGE[0], width=240)
        name_top = self._regiment_name(regiment.name)
        picture = PICTURES[regiment.whoami]
        if picture:
            self._bitmap_centered(picture, (170, name_top - 4), bottom=True)
        if not self.scene.model.hired[regiment.whoami]:
            self._bitmap("ForHireStamp", (50, 35))

    def _regiment_name(self, raw_name: str) -> int:
        """Draw the centred blackletter name above the cost lines; return its top edge."""
        name = raw_name.replace("_", " ").replace("<", " ").strip()
        if not name:
            return 374
        cap = CAPS.get(name[0].upper())
        cap_width, cap_height = cap[2:] if cap else (0, 0)
        words = (name[1:] if cap else name).split()
        lines: list[str] = []
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            indent = cap_width if len(lines) * self.name_font.font.height < cap_height else 0
            if line and self.name_font.size(candidate)[0] > 240 - indent:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        text_height = len(lines) * self.name_font.font.height - 1 if lines else 0
        block_height = max(text_height, cap_height)
        top = 374 - block_height
        block_width = max((self.name_font.size(value)[0] +
                           (cap_width if index * self.name_font.font.height < cap_height else 0)
                           for index, value in enumerate(lines)), default=cap_width)
        x = 50 + max(0, (240 - block_width) // 2)
        if cap:
            self._name_cap(name[0], (x, top), cap)
        for index, value in enumerate(lines):
            indent = cap_width if index * self.name_font.font.height < cap_height else 0
            label = self.gpu.text((max(1, 290 - x - indent), self.name_font.font.height), self.name_font,
                                  color=NAME_INK, background=None, padding=0, align="left", fixed_width=True)
            label.set_lines((value,))
            self.labels.append((label, (x + indent, top + index * self.name_font.font.height)))
        return top

    def _name_cap(self, letter: str, position: Point, rect: tuple[int, int, int, int]) -> None:
        def crop() -> pygame.Surface | None:
            source = load_optional_bitmap(self.content, "FancyLetters", app_palette=self.palette)
            return source.subsurface(pygame.Rect(*rect)).copy() if source is not None else None

        quad = self.bitmap_quads.get(("cap", letter.upper()), crop)
        if quad is not None:
            self.quads.append((quad, position))

    def _right_page(self, regiment: Regiment) -> None:
        if self.info:
            self._center(self._string("BKTXT", 504), 39, BLACK, x=350, width=240)
            h = self.body_font.font.height
            y = 39 + 2 * h
            self._sprite(regiment.banner, (350, y))
            self._equipment_block(regiment.armour, regiment.weapon_name, 350, y + 106)
            # notes/builtin_widgets.md §2.3: the Information page shows the leader block whenever
            # a leader is present; unlike the Statistics page it is not gated on models == 1.
            if regiment.leader_name:
                self._leader_box(470, y, regiment)
                self._label(regiment.leader_name, 470, y + 106, BLACK)
                self._equipment_block(regiment.leader_armour, regiment.leader_weapon, 470, y + 106 + h)
            description_y = y + 106 + (5 * h if regiment.leader_name else 4 * h)
            self._paragraph(self._description(regiment.whoami), 350, description_y, 240)
            self._status_line(regiment)
            return
        self._center(self._string("BKTXT", 503), 39, BLACK, x=350, width=240)
        # Regiment currently retains the profile fields needed by selection only;
        # absent profile data is intentionally not guessed.
        show_leader = regiment.leader_name and regiment.models == 1
        profile = regiment.leader_profile if show_leader else regiment.profile
        h = self.body_font.font.height
        y = 39 + 2 * h
        if show_leader:
            self._leader_box(350, y, regiment)
            self._label(regiment.leader_name or "", 350, y + 106, BLACK)
        else:
            self._sprite(regiment.banner, (350, y))
        y += 106 + (h if show_leader else 0)
        for index in range(9):
            value = profile[index] if index < len(profile) else "-"
            row_y = y + index * h
            self._label(self._string("BRTXT", 700 + index * 2), 428, row_y, BLACK)
            self._label(self._string("BRTXT", 701 + index * 2), 538, row_y, BLACK)
            self._label(str(value), 573, row_y, BLACK)

    def _reinforcement_window(self, regiment: Regiment) -> None:
        """The reinforcement sub-window shown over the book while the regiment has an offer
        (notes/builtin_widgets.md §2.4). Geometry is the documented native layout."""
        ledger = self.scene.model.ledger
        if not ledger.has_offer(regiment.whoami):
            return
        x0, y0 = REINF_ORIGIN
        h = self.body_font.font.height
        self._bitmap("reinfScroll", REINF_ORIGIN)
        self._center(self._string("BKTXT", 505), y0 + 16, BLACK, x=x0, width=REINF_SIZE[0])
        self._center(self._string("BKTXT", 507, ledger.offer_left(regiment.whoami)), y0 + 46, BLACK,
                     x=x0, width=REINF_SIZE[0])
        self._center(self._string("BKTXT", 508, ledger.taken_count(regiment.whoami)), y0 + 46 + h + 2, BLACK,
                     x=x0, width=REINF_SIZE[0])
        for action, offset, size, art in REINF_BUTTONS:
            if art == "reinfButton":  # only the Take button has a pressed picture
                name = art + ("Down" if self.pressed_button == action else "Up")
            else:
                name = art
            position = (x0 + offset[0], y0 + offset[1])
            self._bitmap(name, position)
            if action == "reinf:take":
                y = position[1] + (size[1] - h) // 2
                self._center(self._string("BRTXT", 319), y, YELLOW, x=position[0], width=size[0])
            self.buttons.append((pygame.Rect(*position, *size), action))

    def _equipment_block(self, armour: int, weapon: int, x: int, y: int) -> None:
        """Information-page regiment or commander equipment (§2.2)."""
        h = self.body_font.font.height
        self._label(self._string("BKTXT", 408), x, y, BLACK)
        self._label(self._string("BRTXT", 100 + armour), x, y + h, BLACK)
        self._label(self._string("BRTXT", 200 + weapon), x, y + 2 * h, BLACK)

    def _status_line(self, regiment: Regiment) -> None:
        """Draw the right-page skull/status group at the documented bottom line (§2.2)."""
        level = min(4, (regiment.points & 31) * 4 // 31)
        self._bitmap_centered(f"Skull{level}", (380, 385))
        wounded = self.scene.model.ledger.wounded.get(regiment.whoami, 0)
        self._label(self._string("BKTXT", 502, regiment.models, wounded), 395, 385, BLACK)

    def _buttons(self, regiment: Regiment) -> None:
        for action, x, art, label_id in BUTTONS:
            if action == "book:stat-info":
                label_id = 322 if self.info else 321
            elif action == "book:hire-fire":
                label_id = 320 if self.scene.model.hired[regiment.whoami] else 319
            enabled = self._enabled(action, regiment)
            pressed = enabled and self.pressed_button == action
            self._bitmap(f"{art}{'Dn0' if pressed else 'Up'}", (x, BUTTON_Y))
            offset_x, offset_y = (3, 3) if pressed else (2, 4)
            y = BUTTON_Y + (BUTTON_SIZE[1] - self.body_font.font.height) // 2 + offset_y
            self._center(self._string("BRTXT", label_id), y, YELLOW if enabled else (192, 192, 192),
                         x=x + offset_x, width=BUTTON_SIZE[0])
            if enabled:
                self.buttons.append((pygame.Rect(x, BUTTON_Y, *BUTTON_SIZE), action))

    def _enabled(self, action: str, regiment: Regiment) -> bool:
        if action == "book:hire-fire":
            return self.scene.model.hire_fire_enabled(regiment.whoami)
        if action == "book:abort":
            return self.scene.model.dirty  # nothing to abort until a hire, fire or reinforcement changed something
        if action == "book:previous":
            return self.scene.index > 0
        if action == "book:next":
            return self.scene.index < len(self.scene.company_ids) - 1
        return True

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.KEYDOWN:
            return ({pygame.K_PAGEUP: "book:previous", pygame.K_PAGEDOWN: "book:next",
                     pygame.K_HOME: "book:first", pygame.K_END: "book:last"}.get(event.key),) \
                if event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN, pygame.K_HOME, pygame.K_END) else ()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            point = self._native_point(event.pos)
            self.pressed_button = next((action for rect, action in self.buttons if rect.collidepoint(point)), None)
            self.refresh()
            return ()
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            point = self._native_point(event.pos)
            action, self.pressed_button = self.pressed_button, None
            self.refresh()
            if action and any(rect.collidepoint(point) and candidate == action for rect, candidate in self.buttons):
                if action == "book:stat-info":
                    self.info = not self.info
                    self.refresh()
                    return ()
                return (action,)
        return ()

    def _description(self, whoami: int) -> str:
        name = DESCRIPTIONS[whoami]
        if name not in self._description_cache:
            value = ""
            if self.content.installation is not None:
                try:
                    image = module("pe_resources").PE(self.content.installation.file_dir("DLL", "BKTXT.DLL"))
                    resource = next(item for item in image.resources()
                                    if item.type == 10 and str(item.name).upper() == name.upper())
                    value = image.data(resource).decode("latin-1").split("\x1b", 1)[0].rstrip("\x1a\0\r\n")
                except (FileNotFoundError, OSError, StopIteration, UnicodeDecodeError, ValueError):
                    pass
            self._description_cache[name] = value
        return self._description_cache[name]

    def _paragraph(self, value: str, x: int, y: int, width: int) -> None:
        words, line = value.replace("\r", " ").replace("\n", " ").split(), ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if line and self.body_font.size(candidate)[0] > width:
                self._label(line, x, y, BLACK)
                y += self.body_font.font.height
                line = word
            else:
                line = candidate
        if line:
            self._label(line, x, y, BLACK)

    def _string(self, table: str, identifier: int | None, *args: Any) -> str:
        try:
            if identifier is None:
                return ""
            value = self.content.string(table, identifier)
            return value % args if args else value
        except (KeyError, TypeError, ValueError):
            return ""

    def _bitmap(self, name: str, position: Point) -> None:
        quad = self.bitmap_quads.get(name, lambda: load_optional_bitmap(self.content, name, app_palette=self.palette))
        if quad is not None:
            self.quads.append((quad, position))

    def _bitmap_centered(self, name: str, anchor: Point, *, bottom: bool = False, top: bool = False) -> Point | None:
        quad = self.bitmap_quads.get(name, lambda: load_optional_bitmap(self.content, name, app_palette=self.palette))
        if quad is None:
            return None
        x = anchor[0] - quad.size[0] // 2
        y = anchor[1] if top else anchor[1] - quad.size[1] if bottom else anchor[1] - quad.size[1] // 2
        self.quads.append((quad, (x, y)))
        return quad.size

    def _sprite(self, name: str | None, position: Point, *, size: Point | None = None) -> None:
        """Draw frame zero of a runtime banner or leader-portrait resource (§2.2)."""
        base = self._resolve_sprite_base(name)
        if base is None:
            return
        surface = self._decode_frame(base)
        if surface is None:
            return
        if size is not None and surface.get_size() != size:
            surface = pygame.transform.scale(surface, size)
        self._append_quad(surface, position, ("sprite", base, size))

    def _leader_box(self, x: int, y: int, regiment: Regiment) -> None:
        """Crop-composite the leader portrait over its background (notes/builtin_widgets.md §2.3,
        notes/glue_portraits.md §1.3): background and portrait share one crop window into their
        120x152 frame 0, so the face stays centred. A leader whose portrait set is not in the
        roster book's resident list falls back to a fixed background window and the regiment's
        banner drawn at full size instead of a cropped portrait.
        """
        base = self._resolve_sprite_base(regiment.leader_portrait)
        window = CROP_WINDOWS.get(base.upper()) if base else None
        origin = window if window is not None else NO_MATCH_CROP_WINDOW
        self._draw_crop(BACKGROUND_SET, origin, (x, y))
        if window is not None and base:
            self._draw_crop(base, origin, (x, y))
        else:
            self._sprite(regiment.banner, (x, y))

    def _resolve_sprite_base(self, name: str | None) -> str | None:
        resource = resource_name(name)
        if resource is None or self.content.installation is None:
            return None
        if self.sprite_files is None:
            from ..battlefield import resource_files
            self.sprite_files = resource_files(self.content.installation, {"banners", "portraits"})
        return self.sprite_files.get(resource.casefold())

    def _decode_frame(self, base: str, frame_index: int = 0) -> pygame.Surface | None:
        key = (base, frame_index)
        if key not in self.sprite_surfaces:
            surface: pygame.Surface | None
            try:
                if self.content.installation is None:
                    raise FileNotFoundError("no installation")
                frame = load_sprite_sheet(self.content.installation, base).frames[frame_index]
                surface = pygame.image.frombuffer(self.palette.rgba(frame.pixels),
                                                   (frame.width, frame.height), "RGBA").copy()
            except (FileNotFoundError, IndexError, OSError, ValueError):
                surface = None
            self.sprite_surfaces[key] = surface
        return self.sprite_surfaces[key]

    def _draw_crop(self, base: str, origin: Point, position: Point) -> None:
        """Draw the documented 72x104 crop of ``base``'s frame 0 at ``origin`` (§1.3)."""
        key = (base, origin)
        if key not in self.crop_surfaces:
            crop: pygame.Surface | None
            try:
                if self.content.installation is None:
                    raise FileNotFoundError("no installation")
                frame = load_sprite_sheet(self.content.installation, base).frames[0]
                pixels = self._crop_pixels(frame, origin, LEADER_BOX_SIZE)
                crop = pygame.image.frombuffer(self.palette.rgba(pixels), LEADER_BOX_SIZE, "RGBA").copy()
            except (FileNotFoundError, IndexError, OSError, ValueError):
                crop = None
            self.crop_surfaces[key] = crop
        surface = self.crop_surfaces[key]
        if surface is None:
            return
        self._append_quad(surface, position, ("crop", base, origin))

    @staticmethod
    def _crop_pixels(frame: Any, origin: Point, size: Point) -> bytes:
        ox, oy = origin
        width, height = size
        return b"".join(frame.pixels[(oy + row) * frame.width + ox:(oy + row) * frame.width + ox + width]
                        for row in range(height))

    def _append_quad(self, surface: pygame.Surface, position: Point, key: tuple[Any, ...]) -> None:
        quad = self.bitmap_quads.get(key, lambda: surface)
        if quad is not None:
            self.quads.append((quad, position))

    def _label(self, value: str, x: int, y: int, colour: Rgb) -> None:
        label = self.gpu.text((640, self.body_font.font.height), self.body_font, color=colour,
                              background=None, padding=0, align="left", fixed_width=True)
        label.set_lines((value,))
        self.labels.append((label, (x, y)))

    def _center(self, value: str, y: int, colour: Rgb, *, x: int = 0, width: int = 640,
                font: BitmapFont | None = None) -> None:
        font = font or self.body_font
        label = self.gpu.text((width, font.font.height), font, color=colour, background=None,
                              padding=0, align="center", fixed_width=True)
        label.set_lines((value,))
        self.labels.append((label, (x, y)))

    def _native_point(self, position: Sequence[float]) -> tuple[float, float]:
        left, top, scale = self._layout()
        return (position[0] - left) / scale, (position[1] - top) / scale

    def draw(self) -> None:
        super().draw()
        left, top, scale = self._layout()
        # The reinforcement window is a layer above both page art and page text.
        for quads, labels in ((self.quads[:self.overlay_quad_start], self.labels[:self.overlay_label_start]),
                              (self.quads[self.overlay_quad_start:], self.labels[self.overlay_label_start:])):
            for quad, (x, y) in quads:
                quad.draw(left + x * scale, top + y * scale, quad.size[0] * scale, quad.size[1] * scale)
            for label, (x, y) in labels:
                label.draw(left + x * scale, top + y * scale, label.size[0] * scale, label.size[1] * scale)

    def _release_contents(self) -> None:
        for label, _ in self.labels:
            label.release()
        self.quads, self.labels, self.buttons = [], [], []
        self.overlay_quad_start = self.overlay_label_start = 0

    def release(self) -> None:
        self._release_contents()
        self.bitmap_quads.release()
