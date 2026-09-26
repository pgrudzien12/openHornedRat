# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The Credits page opened from the main menu, presentation-independent.

Behavioural source: ``notes/native-windows.md`` section 3. A fixed page of 28 role headings, each followed by
a short list of name lines, in three columns; the intro tune loops until Done. It changes no state.
All text is read from the installation's string tables at runtime; only the id table below is a front-end fact.

Events: ``"credits:done"``.
"""

from dataclasses import dataclass
from typing import Any

from .glue_content import GlueContent
from .glue_fonts import glue_font_asset
from .scenes import Scene, SceneAssets, SceneEvent, Transition

TITLE_ID = 9142
HEADING_BASE = 9000
DONE_LABEL_ID = 304
TUNE = "intro3"

# Line ids (BKTXT) of section n, in order (notes/native-windows.md section 3).
SECTION_LINES: tuple[tuple[int, ...], ...] = (
    (9100,), (9100, 9101, 9102, 9103, 9104), (9102,), (9102, 9106), (9107,), (9108, 9106), (9109, 9110), (9111,),
    (9112, 9137, 9138, 9139, 9140), (9100,), (9101,), (9113, 9141, 9103), (9100, 9103), (9103, 9114),
    (9115, 9116, 9117, 9118), (9119,), (9100, 9119), (9127, 9128, 9104), (9100, 9104), (9120,), (9143, 9120),
    (9120, 9121), (9121,), (9122,), (9123, 9124, 9125), (9126,), (9109,),
    (9129, 9134, 9130, 9131, 9132, 9133, 9135, 9136),
)
# Column boundaries: sections 0-8, 9-18, 19-27 (x of the heading; lines are indented further).
COLUMNS: tuple[tuple[range, int], ...] = ((range(0, 9), 50), (range(9, 19), 250), (range(19, 28), 425))
LINE_INDENT = 25
COLUMN_TOP = 50
TITLE_Y = 23


@dataclass(frozen=True)
class CreditsSection:
    heading: str
    lines: tuple[str, ...]
    column_x: int


class CreditsScene(Scene):
    def __init__(self, parent: Scene) -> None:
        self.parent = parent
        self.context: SceneAssets | None = None
        self.tune: str | None = None

    def enter(self, context: SceneAssets) -> None:
        self.context = context
        self.tune = TUNE

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | None:
        if event == "credits:done":
            self.tune = None
            return Transition(self.parent, "credits closed")
        return None

    def _string(self, identifier: int, table: str = "BKTXT") -> str:
        try:
            return self.glue_content().string(table, identifier)
        except (KeyError, FileNotFoundError, OSError):
            return ""

    @property
    def title(self) -> str:
        return self._string(TITLE_ID)

    @property
    def done_label(self) -> str:
        return self._string(DONE_LABEL_ID, "BRTXT")

    @property
    def sections(self) -> tuple[CreditsSection, ...]:
        result: list[CreditsSection] = []
        for columns, x in COLUMNS:
            for index in columns:
                result.append(CreditsSection(self._string(HEADING_BASE + index),
                                             tuple(self._string(line) for line in SECTION_LINES[index]), x))
        return tuple(result)

    def font(self, slot: int) -> Any:
        if self.context is None:
            raise RuntimeError("the credits scene has not been entered")
        return self.context.load(glue_font_asset(slot))

    def glue_content(self) -> GlueContent:
        if self.context is None:
            raise RuntimeError("the credits scene has not been entered")
        return self.context.glue_content()
