# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Launcher look: colours, fonts, the PNG art and the image-based widgets drawn with it.

The art in ``art/`` is made for this project (``tools/launcher_art/build_art.py`` builds every size and
state from the source illustrations); none of it comes from the original game. Tk loads PNGs but cannot
scale them, so each widget uses an image prepared at its final size. If the art directory is missing the
widgets fall back to flat drawn shapes, so the launcher keeps working.
"""

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from pathlib import Path
from typing import Any

ART_DIR = Path(__file__).resolve().parent / "art"

BACKGROUND = "#140f0b"  # keep in sync with tools/launcher_art/build_art.py (the portrait fades into it)
PANEL = "#1f1812"
PANEL_EDGE = "#5a4126"
TEXT = "#e3d3a8"
TEXT_MUTED = "#9c8a66"
TEXT_DISABLED = "#6b5f48"
ACCENT = "#9fd04a"
SELECTION = "#3d5a1c"
THUMB = "#7a5530"
THUMB_ACTIVE = "#a8763f"

# Text sits on the middle of the button's rust panel, which is above the image's middle because spikes and
# cloth hang below it; keep in sync with tools/launcher_art/build_art.py's PLATE_CENTRE.
BUTTON_TEXT_CENTRE = 0.37

SERIF_PREFERENCE = ("Cinzel", "Trajan Pro", "Palatino Linotype", "Book Antiqua", "Georgia",
                    "DejaVu Serif", "Liberation Serif", "Times New Roman", "Times")


class Theme:
    """Fonts and images shared by every launcher window; create one per Tk root."""

    def __init__(self, root: tk.Misc) -> None:
        families = set(tkfont.families(root))
        family = next((name for name in SERIF_PREFERENCE if name in families), "TkDefaultFont")
        self.title_font = tkfont.Font(root, family=family, size=22, weight="bold")
        self.heading_font = tkfont.Font(root, family=family, size=12, weight="bold")
        self.body_font = tkfont.Font(root, family=family, size=10)
        self.button_font = tkfont.Font(root, family=family, size=12, weight="bold")
        self.small_button_font = tkfont.Font(root, family=family, size=10, weight="bold")
        self.speech_font = tkfont.Font(root, family=family, size=15, weight="bold")
        self.mono_font = tkfont.Font(root, family="TkFixedFont", size=9)
        self._images: dict[str, tk.PhotoImage | None] = {}
        self._root = root

    def image(self, name: str) -> tk.PhotoImage | None:
        """The PNG ``art/<name>.png``, loaded once; None when the file is missing or unreadable."""
        if name not in self._images:
            path = ART_DIR / f"{name}.png"
            try:
                self._images[name] = tk.PhotoImage(master=self._root, file=str(path))
            except (tk.TclError, OSError):
                self._images[name] = None
        return self._images[name]

    def frame(self, parent: tk.Misc, **options: Any) -> tk.Frame:
        return tk.Frame(parent, bg=BACKGROUND, **options)

    def label(self, parent: tk.Misc, text: str, *, muted: bool = False, heading: bool = False,
              **options: Any) -> tk.Label:
        return tk.Label(parent, text=text, bg=BACKGROUND, fg=TEXT_MUTED if muted else TEXT,
                        font=self.heading_font if heading else self.body_font, **options)

    def check(self, parent: tk.Misc, text: str, variable: tk.BooleanVar) -> tk.Checkbutton:
        return tk.Checkbutton(parent, text=text, variable=variable, bg=BACKGROUND, fg=TEXT,
                              activebackground=BACKGROUND, activeforeground=ACCENT, selectcolor=PANEL,
                              highlightthickness=0, bd=0, font=self.body_font, anchor="w")

    def radio(self, parent: tk.Misc, text: str, variable: tk.StringVar, value: str) -> tk.Radiobutton:
        return tk.Radiobutton(parent, text=text, variable=variable, value=value, bg=BACKGROUND, fg=TEXT,
                              activebackground=BACKGROUND, activeforeground=ACCENT, selectcolor=PANEL,
                              highlightthickness=0, bd=0, font=self.body_font, anchor="w")

    def entry(self, parent: tk.Misc, variable: tk.StringVar) -> tk.Entry:
        return tk.Entry(parent, textvariable=variable, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                        relief="flat", highlightthickness=1, highlightbackground=PANEL_EDGE,
                        highlightcolor=ACCENT, selectbackground=SELECTION, font=self.body_font)

    def panel_options(self) -> dict[str, Any]:
        """Colours for a Text or Listbox drawn as a dark inset panel."""
        return {"bg": PANEL, "fg": TEXT, "relief": "flat", "highlightthickness": 1,
                "highlightbackground": PANEL_EDGE, "highlightcolor": PANEL_EDGE,
                "selectbackground": SELECTION, "selectforeground": TEXT}


class ImageButton(tk.Canvas):
    """A push button drawn from ``button_<size>[_hover|_pressed].png`` with its text on top.

    Hover brightens the plate, pressing darkens it; the command runs on release over the button.
    """

    def __init__(self, parent: tk.Misc, theme: Theme, text: str, command: Callable[[], None],
                 size: str = "wide") -> None:
        self._normal = theme.image(f"button_{size}")
        self._hover = theme.image(f"button_{size}_hover") or self._normal
        self._pressed = theme.image(f"button_{size}_pressed") or self._normal
        if self._normal is not None:
            width, height = self._normal.width(), self._normal.height()
        else:
            width, height = (300, 56) if size == "wide" else (128, 40)
        super().__init__(parent, width=width, height=height, bg=BACKGROUND, highlightthickness=0, bd=0,
                         cursor="hand2")
        self._command = command
        self._enabled = True
        self._inside = False
        self._held = False
        if self._normal is not None:
            self._plate = self.create_image(0, 0, image=self._normal, anchor="nw")
        else:
            self._plate = self.create_rectangle(2, 2, width - 2, height - 2, fill=PANEL, outline=PANEL_EDGE,
                                                width=2)
        font = theme.button_font if size == "wide" else theme.small_button_font
        self._text_y = round(height * BUTTON_TEXT_CENTRE) if self._normal is not None else height // 2
        self._shadow = self.create_text(width // 2 + 1, self._text_y + 1, text=text, font=font, fill="#000000")
        self._text = self.create_text(width // 2, self._text_y, text=text, font=font, fill=TEXT)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "")
        self._redraw()

    def _redraw(self) -> None:
        pressed = self._held and self._inside
        if self._normal is not None:
            image = self._normal
            if not self._enabled or pressed:
                image = self._pressed
            elif self._inside:
                image = self._hover
            self.itemconfigure(self._plate, image=image)
        else:
            self.itemconfigure(self._plate, fill="#120d09" if pressed else PANEL,
                               outline=ACCENT if self._inside and self._enabled else PANEL_EDGE)
        colour = TEXT_DISABLED if not self._enabled else ACCENT if self._inside else TEXT
        self.itemconfigure(self._text, fill=colour)
        offset = 1 if pressed else 0
        width = int(self["width"])
        self.coords(self._text, width // 2 + offset, self._text_y + offset)
        self.coords(self._shadow, width // 2 + 1 + offset, self._text_y + 1 + offset)

    def _on_enter(self, _event: tk.Event) -> None:
        self._inside = True
        self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._inside = False
        self._redraw()

    def _contains(self, event: tk.Event) -> bool:
        return 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()

    def _on_press(self, event: tk.Event) -> None:
        self._held = self._enabled
        self._inside = self._contains(event)
        self._redraw()

    def _on_release(self, event: tk.Event) -> None:
        self._inside = self._contains(event)
        fire = self._held and self._inside and self._enabled
        self._held = False
        self._redraw()
        if fire:
            self._command()


class ArrowScrollbar(tk.Canvas):
    """A vertical scrollbar with the art's up/down arrow buttons and a draggable thumb.

    Use like ``tk.Scrollbar``: ``widget.configure(yscrollcommand=bar.set)`` and pass ``widget.yview``.
    Holding an arrow keeps scrolling; clicking the track pages.
    """

    REPEAT_DELAY_MS = 300
    REPEAT_INTERVAL_MS = 60

    def __init__(self, parent: tk.Misc, theme: Theme, yview: Callable[..., Any]) -> None:
        self._images = {
            (direction, state): theme.image(f"scroll_{direction}{suffix}")
            for direction in ("up", "down")
            for state, suffix in (("normal", ""), ("hover", "_hover"), ("pressed", "_pressed"))
        }
        up = self._images[("up", "normal")]
        self._arrow = up.height() if up is not None else 22
        width = up.width() if up is not None else 22
        super().__init__(parent, width=width, bg=BACKGROUND, highlightthickness=0, bd=0)
        self._yview = yview
        self._first, self._last = 0.0, 1.0
        self._hover: str | None = None
        self._held: str | None = None
        self._repeat_job: str | None = None
        self._drag_from: tuple[int, float] | None = None
        self.bind("<Configure>", lambda _event: self._redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set(self, first: str | float, last: str | float) -> None:
        self._first, self._last = float(first), float(last)
        self._redraw()

    def _track(self) -> tuple[int, int]:
        return self._arrow + 2, max(self._arrow + 3, self.winfo_height() - self._arrow - 2)

    def _thumb(self) -> tuple[int, int]:
        top, bottom = self._track()
        span = bottom - top
        start = top + round(span * self._first)
        end = top + round(span * self._last)
        return start, max(end, start + 12)

    def _part_at(self, y: int) -> str:
        if y < self._arrow:
            return "up"
        if y > self.winfo_height() - self._arrow:
            return "down"
        start, end = self._thumb()
        if start <= y <= end:
            return "thumb"
        return "page_up" if y < start else "page_down"

    def _redraw(self) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        top, bottom = self._track()
        middle = width // 2
        self.create_rectangle(middle - 4, top, middle + 4, bottom, fill=PANEL, outline=PANEL_EDGE)
        if self._last - self._first < 1.0:
            start, end = self._thumb()
            active = self._hover == "thumb" or self._drag_from is not None
            self.create_rectangle(middle - 3, start, middle + 3, end, fill=THUMB_ACTIVE if active else THUMB,
                                  outline="#c99a55" if active else PANEL_EDGE)
        for direction, y, anchor in (("up", 0, "n"), ("down", height, "s")):
            state = "pressed" if self._held == direction else "hover" if self._hover == direction else "normal"
            image = self._images[(direction, state)] or self._images[(direction, "normal")]
            if image is not None:
                self.create_image(middle, y, image=image, anchor=anchor)
            else:
                y0 = 0 if direction == "up" else height - self._arrow
                fill = "#120d09" if state == "pressed" else PANEL
                self.create_rectangle(1, y0 + 1, width - 1, y0 + self._arrow - 1, fill=fill, outline=PANEL_EDGE)
                tip, base = (y0 + 6, y0 + self._arrow - 6) if direction == "up" else (y0 + self._arrow - 6, y0 + 6)
                self.create_polygon(middle, tip, middle - 6, base, middle + 6, base, fill=ACCENT)

    def _on_motion(self, event: tk.Event) -> None:
        part = self._part_at(event.y)
        if part != self._hover:
            self._hover = part
            self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hover = None
        self._redraw()

    def _step(self, part: str) -> None:
        if part in ("up", "down"):
            self._yview("scroll", -1 if part == "up" else 1, "units")
        else:
            self._yview("scroll", -1 if part == "page_up" else 1, "pages")
        self._repeat_job = self.after(self.REPEAT_INTERVAL_MS, self._step, part)

    def _on_press(self, event: tk.Event) -> None:
        part = self._part_at(event.y)
        if part == "thumb":
            self._drag_from = (event.y, self._first)
        else:
            self._held = part
            self._yview("scroll", -1 if part in ("up", "page_up") else 1,
                        "units" if part in ("up", "down") else "pages")
            self._repeat_job = self.after(self.REPEAT_DELAY_MS, self._step, part)
        self._redraw()

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_from is None:
            return
        start_y, start_first = self._drag_from
        top, bottom = self._track()
        self._yview("moveto", start_first + (event.y - start_y) / max(1, bottom - top))

    def _on_release(self, _event: tk.Event) -> None:
        if self._repeat_job is not None:
            self.after_cancel(self._repeat_job)
            self._repeat_job = None
        self._held = None
        self._drag_from = None
        self._redraw()


def scrolled(parent: tk.Misc, theme: Theme, make: Callable[[tk.Misc], Any]) -> tuple[tk.Frame, Any]:
    """A frame holding the widget built by ``make`` (a Text or Listbox) beside an :class:`ArrowScrollbar`."""
    holder = theme.frame(parent)
    widget = make(holder)
    bar = ArrowScrollbar(holder, theme, widget.yview)
    widget.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y", padx=(6, 0))
    widget.pack(side="left", fill="both", expand=True)
    return holder, widget
