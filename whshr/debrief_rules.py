"""Debrief evaluators and text programs (notes/debrief_evaluation.md sections 2-4).

One table row per evaluator index (``setdebrief:n`` records ``n - 1``): the end-screen key, the evaluator kind
and up to three text programs.  A program is written here as a whitespace-separated list of tokens: a number is
a ``BKTXT`` line, ``/`` an empty line, ``commit-wounded`` a line-less side effect and any other token a measured
value line (``MEASURES``).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Callable

from .campaign_runtime import ObjectiveResult

Results = Mapping[str, ObjectiveResult]

# notes/debrief_evaluation.md 4.1: letters the default evaluator ignores.
DEFAULT_IGNORED = frozenset("FHIJKNRXY")
STATUS_BIT_VICTORY_WITH_C = 0x4000
STATUS_BIT_VICTORY_WITHOUT_C = 0x8000


@dataclass(frozen=True)
class Measure:
    """A measured-value line (notes/debrief_evaluation.md 4.3): the objective letter, its ``BKTXT`` format id and
    the format arguments computed from the record's four values."""

    letter: str
    text_id: int
    arguments: Callable[[tuple[int, ...]], tuple[int, ...]]


def _percent(part: int, whole: int) -> int:
    return part * 100 // whole if whole else 0


MEASURES: dict[str, Measure] = {
    "B-lost%": Measure("B", 10010, lambda v: (v[1] - v[3], 100 - v[2])),
    "B-lost": Measure("B", 10015, lambda v: (v[1] - v[3],)),
    "B-lost%(2)": Measure("B", 10060, lambda v: (v[1] - v[3], 100 - v[2])),
    "B-lost(2)": Measure("B", 10028, lambda v: (v[1] - v[3],)),
    "B-saved%": Measure("B", 10037, lambda v: (v[3], v[2])),
    "B-saved%(2)": Measure("B", 10106, lambda v: (v[3], v[2])),
    "C-lost%": Measure("C", 10011, lambda v: (v[1] - v[3], 100 - v[2])),
    "C-lost": Measure("C", 10016, lambda v: (v[1] - v[3],)),
    "C-lost%(2)": Measure("C", 10094, lambda v: (v[1] - v[3], 100 - v[2])),
    "D-lost%": Measure("D", 10023, lambda v: (v[2], _percent(v[2], v[1]))),
    "L-left%": Measure("L", 10036, lambda v: (v[2], _percent(v[2], v[0]))),
    "Q-lost%": Measure("Q", 10111, lambda v: (v[1] - v[3], _percent(v[1] - v[3], v[1]))),
    "W-kill%": Measure("W", 10058, lambda v: (v[3], _percent(v[3], v[1]))),
}


@dataclass(frozen=True)
class Entry:
    """One evaluator row: notes/debrief_evaluation.md 4.2."""

    key: str  # end-screen key: 0 neutral, A, T, Z, z
    kind: int  # evaluator kind E0..E7
    lists: tuple[str | None, str | None, str | None]  # text programs A (success), B (failure), C (alternate)


def _e(key: str, kind: int, a: str | None, b: str | None = None, c: str | None = None) -> Entry:
    return Entry(key, kind, (a, b, c))


# Row i is the evaluator of ``setdebrief:i + 1``; n = 40 in the notes' numbering is row 39 (used by no script).
ENTRIES: tuple[Entry, ...] = (
    _e("0", 1, "10000 / 10001 10002 / 10003", "10004 / 10005 / 10006 10007"),
    _e("Z", 0, "10008 / 10009 / B-lost% C-lost%", "10012 / 10013 10014 / B-lost C-lost"),
    _e("z", 0, "10000 / 10001 10002 / 10003", "10012 / 10017 / 10018 10019"),
    _e("z", 0, "10000 / 10001 10002 / 10003", "10012 / 10017 / 10020 10021"),
    _e("0", 0, "10008 / 10022 / D-lost%", "10008 / 10022 / D-lost%"),
    _e("Z", 0, "10008 / 10009 / 10024"),
    _e("0", 1, "10008 / 10022", "10008 / 10022"),
    _e("A", 0, "10008 / 10025 10026"),
    _e("A", 0, "10008 / 10025 10027 / B-lost(2)"),
    _e("0", 0, "10008 / 10029", "10008 / 10029"),
    _e("0", 0, "10008 / 10030 10031", "10008 / 10030 10031"),
    _e("A", 0, "10008 / 10025 10032", "10142 / 10143 10144"),
    _e("A", 1, "10008 / 10025 10033 / B-lost% C-lost%", "10142 / 10143 10144"),
    _e("A", 1, "10008 / 10035 / L-left%", "10142 / 10143 10144"),
    _e("T", 2, "10008 / 10025 10027 / B-saved%", "10012 / 10038"),
    _e("Z", 0, "10008 / 10025 10039", "10012 / 10040 10041 10042"),
    _e("z", 1, None, "10012 / 10043 10044 / 10045"),
    _e("z", 1, None, "10012 / 10046 / 10045"),
    _e("z", 1, None, "10012 / 10047 10048 / 10045"),
    _e("Z", 3, "10008 / 10025 10049", "10012 / 10050 10051 / 10052 10053", "10012 / 10054 / 10055"),
    _e("Z", 0, "10008 / 10009 10056 10057 / W-kill%", "10012 / 10103 10104 10105 / W-kill%"),
    _e("Z", 0, "10008 / 10059 / B-lost%(2)", "10012 / 10061 10062 B-lost%(2)"),
    _e("T", 4, "10008 / 10030 10031 10063"),
    _e("T", 4, "10008 / 10030 10031 10063 W-kill%"),
    _e("Z", 0, "10008 / 10065", "10012 / 10066 / 10067 10068"),
    _e("0", 0, "10008 / 10069 10070", "10012 / 10071 / 10072 10073"),
    _e("T", 5, "10008 / 10074 / 10063 / B-saved%(2)", "10012 / 10075"),
    _e("0", 0, "10008 / 10076"),
    _e("Z", 0, "10008 / 10077 10078 10079", "10012 / 10080 10081"),
    _e("Z", 1, "10008 / 10082 10083", "10012 / 10084 / 10085 10086"),
    _e("Z", 0, "10008 / 10087 10088", "10012 / 10089 10090 / 10091 10092 10093"),
    _e("Z", 1, "10008 / 10009 / C-lost%(2)", "10012 / 10095 / 10096"),
    _e("Z", 0, "10008 / 10097 10098 / 10099 10100 commit-wounded 10147 10148", "10012 / 10101 10102"),
    _e("0", 0, "10008 / 10107"),
    _e("0", 0, "10008 / 10108"),
    _e("T", 6, "10008 / 10109 10110 / Q-lost%", "10012 / 10112 10113 / Q-lost%", "10012 / 10114 10115 / 10116 10117 10118"),
    _e("Z", 0, "10008 / 10009 / 10119 10120"),
    _e("Z", 0, "10125 / 10126 / 10127 10128 10129"),
    _e("0", 7, "10130 / 10131 / 10132 10133 / 10134", None, "10130 / 10131 / 10135 10136 10137 / 10134"),
    _e("0", 0, "10008 / 10025 10141"),
    _e("0", 0, "10145 / 10146", "10142 / 10143 10144"),
)

# The text-program token forms: ("text", id), ("blank",), ("measure", name), ("commit",).
Token = tuple[str, int | str]


def parse_program(text: str) -> tuple[Token, ...]:
    """The tokens of one written text program."""
    tokens: list[Token] = []
    for word in text.split():
        if word == "/":
            tokens.append(("blank", 0))
        elif word == "commit-wounded":
            tokens.append(("commit", 0))
        elif word.isdigit():
            tokens.append(("text", int(word)))
        else:
            tokens.append(("measure", word))
    return tuple(tokens)


@dataclass(frozen=True)
class Evaluation:
    """The outcome of running one evaluator: the T-result, the text program to show (``None`` = nothing to show)
    and the glue status bits it sets (only the last mission's evaluator does)."""

    entry: Entry
    victory: bool
    list_name: str | None
    status_bits: int = 0

    @property
    def program(self) -> tuple[Token, ...] | None:
        if self.list_name is None:
            return None
        text = self.entry.lists["ABC".index(self.list_name)]
        return None if text is None else parse_program(text)


def _met(results: Results, letter: str) -> bool:
    record = results.get(letter)
    return record is not None and record[0]


def _choose(entry: Entry, victory: bool, name: str | None = None) -> Evaluation:
    return Evaluation(entry, victory, name or ("A" if victory else "B"))


def evaluate(index: int, results: Results) -> Evaluation:
    """Run the evaluator of table row ``index`` over the objective ``results`` (notes/debrief_evaluation.md 4.1)."""
    entry = ENTRIES[index]
    kind = entry.kind
    z_lost = _met(results, "Z")
    if kind == 0:
        victory = all(met != (letter == "Z") for letter, (met, _) in results.items() if letter not in DEFAULT_IGNORED)
        return _choose(entry, victory)
    if kind == 1:
        return _choose(entry, "Z" in results and not z_lost)
    if kind in (2, 5):
        rescued = results.get("B")
        return _choose(entry, "Z" in results and not z_lost and rescued is not None and rescued[1][3] != 0)
    if kind == 3:
        if not z_lost:
            return _choose(entry, True)
        return Evaluation(entry, False, "B" if "P" not in results or _met(results, "P") else "C")
    if kind == 4:
        return _choose(entry, "G" in results and not _met(results, "G"))
    if kind == 6:
        if z_lost:
            return Evaluation(entry, False, "C")
        return _choose(entry, _met(results, "Q"))
    if kind == 7:
        if z_lost:
            return Evaluation(entry, False, "B")
        if "C" not in results:
            return Evaluation(entry, False, "B")
        if _met(results, "C"):
            return Evaluation(entry, True, "A", STATUS_BIT_VICTORY_WITH_C)
        return Evaluation(entry, True, "C", STATUS_BIT_VICTORY_WITHOUT_C)
    raise ValueError(f"unknown evaluator kind {kind}")


def measured_line(name: str, results: Results) -> tuple[int, tuple[int, ...]] | None:
    """The ``(BKTXT id, format arguments)`` of a measured-value line, or ``None`` when its objective is absent."""
    measure = MEASURES[name]
    record = results.get(measure.letter)
    if record is None:
        return None
    return measure.text_id, measure.arguments(record[1])


def program_lines(program: Sequence[Token], results: Results,
                  text: Callable[[int, tuple[int, ...]], str]) -> tuple[str, ...]:
    """A program as displayed lines: a text id, a measured value or an empty line each; ``text(id, args)`` formats."""
    lines: list[str] = []
    for kind, value in program:
        if kind == "text":
            lines.append(text(int(value), ()))
        elif kind == "blank":
            lines.append("")
        elif kind == "measure":
            line = measured_line(str(value), results)
            lines.append("" if line is None else text(line[0], line[1]))
    return tuple(lines)
