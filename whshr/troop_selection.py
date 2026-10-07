# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Headless troop-selection model: notes/troop_selection.md §10 (P0 select, P1 marching order).

Scope: the in-memory core flow only (notes/glue_engine_integration.md GEI7). The real P0/P1
view, the bankruptcy page's presentation, and the roster book are deferred to GEI7b-GEI7d.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .reinforcements import ReinforcementLedger
from .roster import ALWAYS_FORCED_WHOAMI, Regiment

DEFAULT_LIMIT = 13
LIMIT_RANGE = (8, 38)

STATUS_AVAILABLE = "available"
STATUS_NOT_HIRED = "not_hired"
STATUS_EXCLUDED = "excluded"
STATUS_DESTROYED = "destroyed"


@dataclass(frozen=True)
class TroopRow:
    """One P0/P1 row; notes/troop_selection.md §3.2, §3.4."""

    regiment: Regiment
    status: str
    toggleable: bool
    selected: bool
    price: int
    retainer: int
    total: int


@dataclass(frozen=True)
class Deployment:
    """Result of a confirmed troop selection: notes/troop_selection.md §5.3."""

    units: tuple[int, ...]      # whoami, in marching order
    money_delta: int  # prepaid - total_cost; notes/campaign.md §2.3
    hired: frozenset[int]  # whoami hired going forward


class TroopSelection:
    """Pure P0/P1 state; notes/troop_selection.md §4 (P0), §5 (P1)."""

    def __init__(self, company: Iterable[Regiment], forced: Iterable[int] = (), excluded: Iterable[int] = (),
                 limit: int = DEFAULT_LIMIT, coffers: int = 0, prepaid: int = 0,
                 reinforcements: Mapping[int, int] | None = None,
                 wounded: Mapping[int, int] | None = None) -> None:
        self.company: dict[int, Regiment] = {regiment.whoami: regiment for regiment in company}
        # a forced regiment that is not in the company file (it has not joined yet) cannot be selected or paid for
        self.forced = (frozenset(forced) | {ALWAYS_FORCED_WHOAMI}) & self.company.keys()
        self.excluded = frozenset(excluded)
        self.limit = max(LIMIT_RANGE[0], min(LIMIT_RANGE[1], limit))
        self.coffers = coffers
        self.prepaid = prepaid
        self.ledger = ReinforcementLedger(self.company, reinforcements or {}, wounded)
        self.pays = False  # the selection book never touches the coffers (notes/troop_selection.md §4.3)
        # notes/troop_selection.md §4.1: forced regiments become hired; selected unless destroyed.
        self.hired = {whoami: regiment.hired or whoami in self.forced
                      for whoami, regiment in self.company.items()}
        self.selection: list[int] = [whoami for whoami in self.company
                          if whoami in self.forced and self.hired[whoami] and not self.company[whoami].destroyed]

    def _destroyed(self, whoami: int) -> bool:
        return self.company[whoami].destroyed

    def status(self, whoami: int) -> str:
        """notes/troop_selection.md §3.4, checked in this order."""
        if not self.hired[whoami]:
            return STATUS_NOT_HIRED
        if whoami in self.excluded:
            return STATUS_EXCLUDED
        if self._destroyed(whoami):
            return STATUS_DESTROYED
        return STATUS_AVAILABLE

    def toggleable(self, whoami: int) -> bool:
        """notes/troop_selection.md §4.2: hired, not forced, not excluded, not destroyed."""
        return whoami not in self.forced and self.status(whoami) == STATUS_AVAILABLE

    def row(self, whoami: int) -> TroopRow:
        regiment = self.company[whoami]
        selected = whoami in self.selection
        total = regiment.price if selected else regiment.retainer
        return TroopRow(regiment, self.status(whoami), self.toggleable(whoami), selected,
                        regiment.price, regiment.retainer, total)

    def rows(self) -> tuple[TroopRow, ...]:
        return tuple(self.row(whoami) for whoami in self.company)

    @property
    def roster_full(self) -> bool:
        return len(self.selection) >= self.limit

    def toggle(self, whoami: int) -> bool:
        """notes/troop_selection.md §4.2. Returns True when the refusal sound should play."""
        if not self.toggleable(whoami):
            return False
        if whoami in self.selection:
            self.selection.remove(whoami)
            return False
        if self.roster_full:
            return True
        self.selection.append(whoami)
        return False

    def hire_fire_enabled(self, whoami: int) -> bool:
        """notes/troop_selection.md §4.3: only the roster's ``forHire`` flag matters in this variant."""
        return self.company[whoami].row.for_hire

    def toggle_hired(self, whoami: int) -> bool:
        return self.set_hired_from_book(whoami, not self.hired[whoami])

    @property
    def dirty(self) -> bool:
        return self.ledger.changed or any(self.hired[whoami] != regiment.hired
                                          for whoami, regiment in self.company.items())

    def set_hired_from_book(self, whoami: int, hired: bool) -> bool:
        """Apply the selection-variant Army Records Hire/Fire action (§4.3, §8).

        This deliberately does not use :meth:`toggle`: book hiring never makes the
        full-roster refusal sound, and hiring is allowed even when the list is full.
        """
        regiment = self.company[whoami]
        if not regiment.row.for_hire:
            return False
        self.hired[whoami] = bool(hired)
        if hired:
            if whoami not in self.selection and not self.roster_full:
                self.selection.append(whoami)
        elif whoami in self.selection:
            self.selection.remove(whoami)
        return True

    def restore_book_hired(self, snapshot: Mapping[int, bool]) -> None:
        """Restore only the documented hired snapshot, retaining valid picks (§8).

        The specification does not state that Abort restores a prior marching
        order.  In particular, a fire/re-hire may already have appended a unit;
        do not invent an unverified ordering rollback here.
        """
        self.hired.update(snapshot)
        self.selection[:] = [whoami for whoami in self.selection if self.hired[whoami]]

    def move(self, whoami: int, new_index: int) -> None:
        """notes/troop_selection.md §5.2: reorder the marching-order list."""
        if whoami not in self.selection:
            return
        self.selection.remove(whoami)
        self.selection.insert(max(0, min(new_index, len(self.selection))), whoami)

    @property
    def total_cost(self) -> int:
        """notes/native-windows.md §11.3.5: the price of every selected regiment plus the retainer of every
        hired regiment that is not selected. Excluded and destroyed rows are not skipped, so their retainers count."""
        return sum(self.company[whoami].price if whoami in self.selection else self.company[whoami].retainer
                   for whoami in self.company if self.hired[whoami])

    @property
    def affordable(self) -> bool:
        return self.total_cost <= self.coffers + self.prepaid

    @property
    def bankrupt(self) -> bool:
        """notes/troop_selection.md §4.1, §7: forced-selected cost exceeds coffers + prepaid."""
        return self.forced_cost > self.coffers + self.prepaid

    @property
    def forced_cost(self) -> int:
        """P5's required amount: price of still-living forced regiments (§7)."""
        return sum(self.company[whoami].price for whoami in self.forced
                   if self.hired[whoami] and not self._destroyed(whoami))

    def confirm(self) -> Deployment:
        """notes/troop_selection.md §5.3 (money in notes/campaign.md §2.3). Assumes affordable."""
        money_delta = self.prepaid - self.total_cost
        hired = frozenset(whoami for whoami, is_hired in self.hired.items() if is_hired)
        return Deployment(tuple(self.selection), money_delta, hired)
