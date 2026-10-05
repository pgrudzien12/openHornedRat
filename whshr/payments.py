# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Mission payments: the `cash` line of a mission record, the balance-sheet programs run at the debrief,
and the "flawless" battle result the no-battle mode substitutes for a played battle.

Behaviour source: notes/campaign.md section 2.5 (payment programs, line items), section 2.3 (the initial
payment is credited when troop selection is confirmed) and notes/debrief_evaluation.md section 2
(objective records: ``Result:<L>,<met>,<v1>,<v2>,<v3>,<v4>``).

An objective result is ``(met, (v1, v2, v3, v4))`` keyed by upper-case letter, as
``CampaignState.objective_results`` stores it.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .campaign_runtime import ObjectiveResult
from .glue import MissionRecord

if TYPE_CHECKING:
    from .campaign_state import CampaignState

# notes/debrief_evaluation.md 3: for these letters a met flag means defeat; the others never come out met.
DEFEAT_LETTERS = frozenset("ZGY")
NEVER_MET_LETTERS = frozenset("UILRM")

# notes/campaign.md 2.5: the balance-sheet program per `cash` type.  "blank" lines and the "Mission Total"
# display line ("total") do not change the amount; "final" is the amount credited (max(total, 0)).
PROGRAMS: dict[int, tuple[str, ...]] = {
    0: (),
    1: ("initial", "completion", "total", "blank", "received", "villagers", "buildings", "blank", "final"),
    2: ("initial", "completion", "total", "blank", "received", "wagons", "blank", "final"),
    3: ("completion", "blank", "final"),
    4: ("initial", "completion", "skaven", "total", "blank", "received", "blank", "final"),
    5: ("arrival", "blank", "final"),
    6: ("arrival", "blank", "final"),
    7: ("arrival", "blank", "rock_lobbers", "blank", "final"),
    8: ("initial", "completion", "total", "blank", "received", "blank", "final"),
    9: ("rock_lobbers", "all_rock_lobbers", "blank", "final"),
    10: ("completion", "livestock", "blank", "final"),
    11: ("completion", "all_men", "blank", "final", "blank", "armour"),
    12: ("completion", "bolt_holes", "blank", "final"),
    13: ("completion", "elder", "blank", "final"),
    14: ("completion", "hiln", "blank", "final"),
    15: ("experience",),
    16: ("completion", "blank", "livestock", "buildings", "blank", "final"),
    17: ("dwarfs", "blank", "final"),
    18: ("arrival", "blank", "final"),
}
# Line items the notes do not fully specify for the engine: skipped with a diagnostic.
UNMODELLED: dict[str, str] = {
    "elder": "High Elder not rescued penalty: the notes leave its condition open",
    "hiln": "Hiln killed penalty: the notes leave its condition open",
    "experience": "doubled experience: experience awards are not part of the payment",
    "armour": "+1 armour rewards: not part of the payment",
}


@dataclass(frozen=True)
class CashTerms:
    """The fields of a mission record's ``cash:<type>,<initial>,<completion>,<rate A>,<rate B>,<letters>`` line."""

    type: int
    initial: int = 0
    completion: int = 0
    rate_a: int = 0
    rate_b: int = 0
    letters: tuple[str, ...] = ()


def _number(text: Any) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return 0


def parse_cash(argument: str | None) -> CashTerms | None:
    """Parse a ``cash`` argument; ``None`` when it is empty or has no numeric type.  A four-number line such as
    ``5,0,5000,0,M`` puts the non-numeric last field into rate B as 0 and leaves no required letter (notes 2.5)."""
    if not argument:
        return None
    parts = [part.strip() for part in argument.split(",")]
    try:
        kind = int(parts[0])
    except ValueError:
        return None
    letters = tuple(part.upper() for part in parts[5:7] if len(part) == 1 and part.isalpha())
    initial, completion, rate_a, rate_b = (_number(parts[i]) if i < len(parts) else 0 for i in range(1, 5))
    return CashTerms(kind, initial, completion, rate_a, rate_b, letters)


def mission_terms(mission_record: MissionRecord) -> CashTerms | None:
    """The :class:`CashTerms` of a typed mission record, or ``None`` when it has no ``cash`` line."""
    cash = next((field_.argument for field_ in mission_record.fields if field_.command == "cash"), None)
    return parse_cash(cash)


@dataclass
class Settlement:
    """The balance sheet of one mission: the applied line items, the skipped ones and the amount to credit."""

    lines: list[tuple[str, int]] = field(default_factory=list[tuple[str, int]])  # (label, amount) in program order
    skipped: list[str] = field(default_factory=list[str])
    final: int = 0
    # every program step, blank and display-only ones included: (op, amount); amount is None for a blank line or a
    # label-only line ("experience", "armour"), the running total for "total" and 0 for a line whose objective is absent
    steps: list[tuple[str, int | None]] = field(default_factory=list[tuple[str, int | None]])

    @property
    def credited(self) -> int:
        return self.final


def settle(terms: CashTerms, results: Mapping[str, ObjectiveResult], bonus_counter: int = 0) -> Settlement:
    """Run the payment program of ``terms`` over the objective ``results``; returns a :class:`Settlement`.

    The running total starts at 0; ``final`` is ``max(total, 0)`` at the program's final line.  Lines that need an
    objective the result lacks, or that the notes leave open, are skipped with a reason and add nothing."""
    settlement = Settlement()
    total = 0

    def value(letter: str, index: int) -> int | None:
        record = results.get(letter)
        return None if record is None else record[1][index]

    for op in PROGRAMS.get(terms.type, ()):
        amount: int | None = None
        if op == "blank":
            settlement.steps.append((op, None))
            continue
        if op == "total":
            settlement.steps.append((op, total))
            continue
        if op in UNMODELLED:
            settlement.skipped.append(f"{op}: {UNMODELLED[op]}")
        elif op == "initial":
            amount = terms.initial
        elif op == "completion":
            met = all(results.get(letter, (False,))[0] for letter in terms.letters)
            amount = terms.completion if met else 0
        elif op == "arrival":
            amount = terms.completion
        elif op == "received":
            amount = -terms.initial
        elif op == "skaven":
            amount = terms.rate_a * bonus_counter
        elif op in ("villagers", "livestock"):
            start, now = value("B", 1), value("B", 3)
            amount = None if start is None or now is None else -terms.rate_a * (start - now)
        elif op == "buildings":
            start, now = value("C", 1), value("C", 3)
            amount = None if start is None or now is None else -terms.rate_b * (start - now)
        elif op == "wagons":
            lost = value("D", 2)
            amount = None if lost is None else -terms.rate_a * lost
        elif op == "bolt_holes":
            left = value("C", 3)
            amount = None if left is None else -terms.rate_a * left
        elif op == "rock_lobbers":
            destroyed = value("W", 3)
            amount = None if destroyed is None else terms.rate_a * destroyed
        elif op == "all_rock_lobbers":
            start, destroyed = value("W", 1), value("W", 3)
            amount = None if start is None or destroyed is None else (terms.rate_b if start <= destroyed else 0)
        elif op == "all_men":
            models = value("Z", 0)
            amount = None if models is None else terms.rate_a * models
        elif op == "dwarfs":
            rescued = value("B", 3)
            amount = None if rescued is None else terms.rate_a * rescued
        elif op == "final":
            settlement.final = max(total, 0)
            settlement.lines.append(("final", settlement.final))
            settlement.steps.append((op, settlement.final))
            continue
        if amount is None:
            if op not in UNMODELLED:
                settlement.skipped.append(f"{op}: the battle result lacks the objective it needs")
            settlement.steps.append((op, None if op in ("experience", "armour") else 0))
            continue
        total += amount
        settlement.lines.append((op, amount))
        settlement.steps.append((op, amount))
    return settlement


def flawless_results(objectives: Iterable[Sequence[Any]] | None, required_letters: Iterable[str] = (),
                     player_models: int | None = None) -> dict[str, ObjectiveResult]:
    """The battle result of a perfect win with no casualties (no-battle mode).

    ``objectives`` are the battle script's ``(letter, a, b)`` lines.  Every letter is met with its full values:
    ``v1 = a``, ``v2 = b`` (the start count), ``v3`` the percentage now (100, or 0 lost/killed for the
    counting letters), ``v4`` the count now (all ``b`` alive, killed or destroyed).  The defeat letters (Z, G, Y)
    and never-met information letters come out not met; a letter the mission's ``cash`` line requires is always
    met.  ``Z`` carries the number of player models at the start (``player_models`` when known, else ``a``)."""
    results: dict[str, ObjectiveResult] = {}
    for entry in objectives or ():
        letter, a, b = str(entry[0]).upper(), _number(entry[1]), _number(entry[2]) if len(entry) > 2 else 0
        if letter == "Z":
            results[letter] = (False, (a if player_models is None else int(player_models), b, 0, 0))
        elif letter in DEFEAT_LETTERS or letter in NEVER_MET_LETTERS:
            results[letter] = (False, (a, b, 0, 0))
        elif letter == "A":
            results[letter] = (True, (a, b, 0, 0))
        elif letter in "DVW":
            results[letter] = (True, (a, b, 0, b))
        else:
            results[letter] = (True, (a, b, 100, b))
    for letter in required_letters:
        letter = letter.upper()
        if letter not in DEFEAT_LETTERS:
            _, values = results.get(letter, (True, (0, 0, 0, 0)))
            results[letter] = (True, values)
    return results


def played_results(objectives: Iterable[Sequence[Any]] | None, victory: bool, required_letters: Iterable[str] = (),
                   player_models: int | None = None, regiments_lost: int = 0) -> dict[str, ObjectiveResult]:
    """The objective records of a played battle, derived from its outcome (the engine measures no objective itself).

    A victory is the flawless result (every measured quantity unharmed: PROVISIONAL, villagers, buildings and the
    like are not counted yet).  A defeat meets the hidden loss letter ``Z`` and leaves every other letter unmet."""
    if victory:
        return flawless_results(objectives, required_letters, player_models)
    results: dict[str, ObjectiveResult] = {}
    for entry in objectives or ():
        letter, a, b = str(entry[0]).upper(), _number(entry[1]), _number(entry[2]) if len(entry) > 2 else 0
        results[letter] = (False, (a, b, 0, 0))
    models = player_models if player_models is not None else 0
    z_values = results.get("Z", (False, (0, 0, 0, 0)))[1]
    results["Z"] = (True, (models or z_values[0], z_values[1], regiments_lost, 0))
    return results


def marching_models(campaign: "CampaignState") -> int | None:
    """The models of the regiments marching on the current mission, or ``None`` when the company is unknown."""
    marching = set(getattr(campaign, "march_units", ()))
    models = sum(regiment.models for regiment in getattr(campaign, "company", ()) if regiment.whoami in marching)
    return models or None


def store_flawless(campaign: "CampaignState", objectives: Iterable[Sequence[Any]] = ()) -> None:
    """Give the campaign a flawless result for the current mission (no-battle mode): see :func:`flawless_results`."""
    terms = getattr(campaign, "mission_cash", None)
    campaign.objective_results = flawless_results(objectives, terms.letters if terms else (), marching_models(campaign))
    campaign.flawless_result = True
