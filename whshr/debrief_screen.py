"""Debrief screen model: pages, buttons and the drawing lists of P2/P3/P4 (notes/native-windows.md section 9).

Pure state, no pygame.  The view paints the returned :class:`Text` and :class:`RowArt` items on the 640x480
window; every string comes from ``strings(table, id, *arguments)`` so this module never touches the game files.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from . import debrief_rules
from .campaign_runtime import ObjectiveResult
from .debrief_rules import Evaluation, evaluate
from .payments import CashTerms, Settlement, settle

Strings = Callable[..., str]  # strings("BKTXT", id, *format arguments)
Rgb = tuple[int, int, int]
BLACK: Rgb = (0, 0, 0)
GREY: Rgb = (127, 127, 127)
RED: Rgb = (255, 0, 0)

PAGE_ROWS = 6  # regiments per P3 page
DEFAULT_DEAD_PERCENT = 65  # option `dead`: the share of lost models counted as wounded (notes/campaign.md 3.3)
MODES = (2, 4, 6, 7)
LABEL_X, AMOUNT_RIGHT_X = 45, 390

# notes/native-windows.md 9.3.4 P4: penalties print "-<n> <unit>", every other amount " <n> <unit>".
DEBIT_OPS = frozenset({"received", "villagers", "buildings", "wagons", "livestock", "bolt_holes", "elder", "hiln"})
# notes/campaign.md 2.5: BKTXT label of each program step ("arrival" depends on the cash type, see ARRIVAL_LABELS).
STEP_LABELS: dict[str, int] = {
    "initial": 5000, "completion": 5001, "total": 5002, "final": 5003, "received": 5004, "villagers": 5010,
    "buildings": 5011, "wagons": 5012, "skaven": 5013, "rock_lobbers": 5014, "livestock": 5015, "all_men": 5016,
    "bolt_holes": 5017, "elder": 5019, "all_rock_lobbers": 5020, "hiln": 5023, "dwarfs": 5024,
}
ARRIVAL_LABELS = {5: 5040, 6: 5041, 7: 5041, 18: 5042}
DOUBLE_EXPERIENCE_LABEL, ARMOUR_LABEL = 5021, 5022
# notes/campaign.md 1.4: the regiments (whoami) a type-11 program rewards with +1 armour, in program order.
ARMOUR_REWARDS = (4, 27, 20, 16, 17, 1, 7)


@dataclass(frozen=True)
class DebriefUnit:
    """One regiment of the battle result (``debrief.dbf`` unit, notes/campaign.md 4.8)."""

    whoami: int
    name: str
    models: int  # s_size at the end of the battle
    routed: int  # s_routed
    casualties: int  # s_calualties (dead and routed)
    kills: int
    experience: int  # s_Exp at the end of the battle
    experience_start: int  # the roster's experience-at-start
    orgsize: int
    weapon_name: int
    armour: int
    points: int  # s_pntval
    banner: str | None
    hired: bool
    artillery: bool

    @property
    def shown_models(self) -> int:
        return self.models + self.routed

    @property
    def destroyed(self) -> bool:
        return self.shown_models < 2 if self.artillery else self.shown_models <= 0

    @property
    def lost(self) -> int:
        return self.casualties - self.routed

    def wounded(self, dead_percent: int = DEFAULT_DEAD_PERCENT) -> int:
        return self.lost * dead_percent // 100

    def dead(self, dead_percent: int = DEFAULT_DEAD_PERCENT) -> int:
        return self.lost - self.wounded(dead_percent)

    @property
    def gained(self) -> int:
        return self.experience - self.experience_start

    @property
    def skull(self) -> int:
        """The rank icon: notes/troop_selection.md 3.3."""
        return min(4, (self.points & 31) * 4 // 31)


@dataclass(frozen=True)
class UnitOutcome:
    """What one marching regiment came out of a played battle with (the unit fields ``debrief.dbf`` records)."""

    models: int
    routed: int
    casualties: int
    kills: int = 0
    experience_gained: int = 0


@dataclass(frozen=True)
class DebriefReport:
    """The battle result: objective records by letter and the regiments that fought."""

    results: Mapping[str, ObjectiveResult]
    units: tuple[DebriefUnit, ...] = ()


@dataclass(frozen=True)
class Text:
    """A text run: ``x`` is the left edge, the right edge for ``align="right"`` and ignored when centred."""

    text: str
    y: int
    x: int = 0
    font: int = 2
    align: str = "left"
    colour: Rgb = BLACK


@dataclass(frozen=True)
class RowArt:
    """The rank icon and banner of one P3 row (the row's top is ``y``)."""

    y: int
    skull: int
    banner: str | None


@dataclass(frozen=True)
class Layout:
    texts: tuple[Text, ...] = ()
    rows: tuple[RowArt, ...] = ()


@dataclass(frozen=True)
class Buttons:
    next: bool
    back: bool
    done: bool = True


@dataclass
class DebriefScreen:
    """The post-battle pages for one open mode (2: battle with debrief, 4: `debrief:`, 6: battle without debrief,
    7: `debriefwithsummary:`; notes/native-windows.md 9.2)."""

    mode: int
    report: DebriefReport
    index: int  # the evaluator row (``setdebrief:n`` records n - 1)
    terms: CashTerms | None
    coffers: int
    mission_name_id: int | None
    strings: Strings
    bonus_counter: int = 0
    dead_percent: int = DEFAULT_DEAD_PERCENT
    body_height: int = 12  # font slot 2 cell height
    heading_height: int = 22  # font slot 4 cell height
    item_name: Callable[[int], str | None] = lambda _index: None
    page: str = field(init=False)
    unit_page: int = field(init=False, default=0)
    evaluation: Evaluation = field(init=False)
    settlement: Settlement = field(init=False)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"debrief open mode {self.mode} is never requested")
        self.evaluation = evaluate(self.index, self.report.results)
        self.settlement = settle(self.terms, self.report.results, self.bonus_counter) if self.terms is not None \
            else Settlement()
        self.page = "p4" if self.mode == 4 else "p2"

    @property
    def unit_pages(self) -> int:
        return max(1, -(-len(self.report.units) // PAGE_ROWS))

    def will_skip(self) -> bool:
        """Modes 2, 6 and 7 show nothing when the evaluator has no text for the outcome (9.3.1a); mode 4 always shows."""
        return self.mode != 4 and self.evaluation.program is None

    def music(self) -> str:
        """The tune that plays while the screen is up: win/lose by the T-result (modes 2, 6, 7), else tactical."""
        if self.mode == 4:
            return "tactical"
        return "win" if self.evaluation.victory else "lose"

    @property
    def experience_multiplier(self) -> int:
        return 2 if any(op == "experience" for op, _ in self.settlement.steps) else 1

    def buttons(self) -> Buttons:
        """Which of Next/Back are enabled (Done always is): notes/native-windows.md 9.3.3."""
        last = self.unit_page >= self.unit_pages - 1
        if self.mode == 2:
            return Buttons(self.page != "p4", self.page != "p2")
        if self.mode == 6:
            return Buttons(self.page == "p2" or (self.page == "p3" and not last), self.page == "p3")
        if self.mode == 7:
            return Buttons(self.page == "p2", self.page == "p4")
        return Buttons(False, False)

    def next(self) -> None:
        if not self.buttons().next:
            return
        if self.page == "p2":
            self.page, self.unit_page = ("p4" if self.mode == 7 else "p3"), 0
        elif self.unit_page < self.unit_pages - 1:
            self.unit_page += 1
        else:
            self.page, self.unit_page = "p4", 0

    def back(self) -> None:
        if not self.buttons().back:
            return
        if self.page == "p3":
            if self.unit_page > 0:
                self.unit_page -= 1
            else:
                self.page = "p2"
        elif self.mode == 7:
            self.page = "p2"
        else:
            self.page, self.unit_page = "p3", self.unit_pages - 1

    def layout(self) -> Layout:
        """The drawing list of the current page."""
        title = Text(self._string("BKTXT", 403, self._mission_name()), 25, align="center")
        page = {"p2": self._p2, "p3": self._p3, "p4": self._p4}[self.page]()
        return Layout((title, *page.texts), page.rows)

    def _string(self, table: str, text_id: int, *arguments: Any) -> str:
        return self.strings(table, text_id, *arguments)

    def _mission_name(self) -> str:
        return "" if self.mission_name_id is None else self._string("BRTXT", self.mission_name_id)

    def _p2(self) -> Layout:
        h, h4 = self.body_height, self.heading_height
        program = self.evaluation.program or ()
        lines = debrief_rules.program_lines(
            program, self.report.results, lambda text_id, arguments: self._string("BKTXT", text_id, *arguments))
        texts: list[Text] = []
        y = 8 * h + 50
        for number, line in enumerate(lines):
            if number == 0:
                texts.append(Text(line, y, font=4, align="center"))
                y += 2 * h4
                continue
            if line:
                texts.append(Text(line, y, align="center"))
            y += h
        y += h
        for letter in "KX":
            record = self.report.results.get(letter)
            if record is None or not record[0]:
                continue
            item = self.item_name(record[1][3])
            if item is None:
                continue
            unit = next((unit for unit in self.report.units if unit.whoami == record[1][2]),
                        self.report.units[0] if self.report.units else None)
            texts.append(Text(self._string("BKTXT", 610, unit.name if unit else "", item), y, align="center"))
            y += h
        return Layout(tuple(texts))
    def _p3(self) -> Layout:
        h = self.body_height
        texts = [Text(self._string("BKTXT", text_id), 50, x=x)
                 for text_id, x in ((404, 345), (405, 405), (406, 465), (412, 530))]
        rows: list[RowArt] = []
        start = self.unit_page * PAGE_ROWS
        shown = self.report.units[start:start + PAGE_ROWS]
        for number, unit in enumerate(shown):
            y = 50 + h + 4 * h * number
            colour = GREY if not unit.hired else RED if unit.destroyed else BLACK
            texts.append(Text(f"{unit.name} {unit.shown_models} ({unit.orgsize})", y, x=105, colour=colour))
            texts.append(Text(f"{self._string('BRTXT', 200 + unit.weapon_name)}/"
                              f"{self._string('BRTXT', 100 + unit.armour)}", y + h, x=105, colour=colour))
            rows.append(RowArt(y, unit.skull, unit.banner))
            for value, x in ((unit.kills, 345), (unit.dead(self.dead_percent), 405),
                             (unit.wounded(self.dead_percent), 465), (unit.gained, 530)):
                texts.append(Text(str(value), y, x=x))
        record = self.report.results.get("Z")
        if record is not None and record[0]:
            texts.append(Text(self._string("BKTXT", 611), 50 + 4 * h * len(shown), x=345))
        return Layout(tuple(texts), tuple(rows))

    def _p4(self) -> Layout:
        h, h4 = self.body_height, self.heading_height
        pitch = 3 * h // 2
        unit_word = self._string("BKTXT", 419)
        texts = [Text(self._string("BKTXT", 5005), 50, font=4, align="center")]
        y = 50 + 2 * h4
        for op, amount in self.settlement.steps:
            if op == "blank":
                y += pitch
                continue
            if op == "experience":
                texts.append(Text(self._string("BKTXT", DOUBLE_EXPERIENCE_LABEL), y, x=LABEL_X))
            elif op == "armour":
                for whoami in ARMOUR_REWARDS:
                    unit = next((unit for unit in self.report.units if unit.whoami == whoami), None)
                    if unit is None or unit.shown_models <= 0:
                        continue
                    texts.append(Text(self._string("BKTXT", ARMOUR_LABEL, unit.name), y, x=LABEL_X))
                    y += pitch
                continue
            else:
                label = ARRIVAL_LABELS.get(self.terms.type if self.terms else -1, 5040) if op == "arrival" \
                    else STEP_LABELS[op]
                texts.append(Text(self._string("BKTXT", label), y, x=LABEL_X))
                if amount is not None:
                    shown = f"-{abs(amount)}" if op in DEBIT_OPS else f" {amount}"
                    texts.append(Text(f"{shown} {unit_word}", y, x=AMOUNT_RIGHT_X, align="right"))
            y += pitch
        y += pitch
        texts.append(Text(self._string("BKTXT", 5007), y, x=LABEL_X))
        texts.append(Text(self._string("BKTXT", 5008, self.coffers + self.settlement.final), y,
                          x=AMOUNT_RIGHT_X, align="right"))
        return Layout(tuple(texts))
