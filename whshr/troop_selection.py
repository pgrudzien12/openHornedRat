"""Headless troop-selection model: notes/troop_selection.md §10 (P0 select, P1 marching order).

Scope: the in-memory core flow only (notes/glue_engine_integration.md GEI7). The real P0/P1
view, the bankruptcy page's presentation, and the roster book are deferred to GEI7b-GEI7d.
"""

from dataclasses import dataclass

from .roster import ALWAYS_FORCED_WHOAMI

DEFAULT_LIMIT = 13
LIMIT_RANGE = (8, 38)

STATUS_AVAILABLE = "available"
STATUS_NOT_HIRED = "not_hired"
STATUS_EXCLUDED = "excluded"
STATUS_DESTROYED = "destroyed"


@dataclass(frozen=True)
class TroopRow:
    """One P0/P1 row; notes/troop_selection.md §3.2, §3.4."""

    regiment: object  # roster.Regiment
    status: str
    toggleable: bool
    selected: bool
    price: int
    retainer: int
    total: int


@dataclass(frozen=True)
class Deployment:
    """Result of a confirmed troop selection: notes/troop_selection.md §5.3."""

    units: tuple      # whoami, in marching order
    money_delta: int  # prepaid - total_cost; notes/campaign.md §2.3
    hired: frozenset  # whoami hired going forward


class TroopSelection:
    """Pure P0/P1 state; notes/troop_selection.md §4 (P0), §5 (P1)."""

    def __init__(self, company, forced=(), excluded=(), limit=DEFAULT_LIMIT, coffers=0, prepaid=0):
        self.company = {regiment.whoami: regiment for regiment in company}
        self.forced = frozenset(forced) | {ALWAYS_FORCED_WHOAMI}
        self.excluded = frozenset(excluded)
        self.limit = max(LIMIT_RANGE[0], min(LIMIT_RANGE[1], limit))
        self.coffers = coffers
        self.prepaid = prepaid
        # notes/troop_selection.md §4.1: forced regiments become hired; selected unless destroyed.
        self.hired = {whoami: regiment.hired or whoami in self.forced
                      for whoami, regiment in self.company.items()}
        self.selection = [whoami for whoami in self.company
                          if whoami in self.forced and self.hired[whoami] and not self.company[whoami].destroyed]

    def _destroyed(self, whoami):
        return self.company[whoami].destroyed

    def status(self, whoami):
        """notes/troop_selection.md §3.4, checked in this order."""
        if not self.hired[whoami]:
            return STATUS_NOT_HIRED
        if whoami in self.excluded:
            return STATUS_EXCLUDED
        if self._destroyed(whoami):
            return STATUS_DESTROYED
        return STATUS_AVAILABLE

    def toggleable(self, whoami):
        """notes/troop_selection.md §4.2: hired, not forced, not excluded, not destroyed."""
        return whoami not in self.forced and self.status(whoami) == STATUS_AVAILABLE

    def row(self, whoami):
        regiment = self.company[whoami]
        selected = whoami in self.selection
        total = regiment.price if selected else regiment.retainer
        return TroopRow(regiment, self.status(whoami), self.toggleable(whoami), selected,
                        regiment.price, regiment.retainer, total)

    def rows(self):
        return tuple(self.row(whoami) for whoami in self.company)

    @property
    def roster_full(self):
        return len(self.selection) >= self.limit

    def toggle(self, whoami):
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

    def move(self, whoami, new_index):
        """notes/troop_selection.md §5.2: reorder the marching-order list."""
        if whoami not in self.selection:
            return
        self.selection.remove(whoami)
        self.selection.insert(max(0, min(new_index, len(self.selection))), whoami)

    @property
    def total_cost(self):
        """notes/troop_selection.md §3.1: sum of the numbers shown, i.e. AVAILABLE rows only."""
        return sum(self.row(whoami).total for whoami in self.company if self.status(whoami) == STATUS_AVAILABLE)

    @property
    def affordable(self):
        return self.total_cost <= self.coffers + self.prepaid

    @property
    def bankrupt(self):
        """notes/troop_selection.md §4.1, §7: forced-selected cost exceeds coffers + prepaid."""
        forced_cost = sum(self.company[whoami].price for whoami in self.forced
                          if self.hired[whoami] and not self._destroyed(whoami))
        return forced_cost > self.coffers + self.prepaid

    def confirm(self):
        """notes/troop_selection.md §5.3 (money in notes/campaign.md §2.3). Assumes affordable."""
        money_delta = self.prepaid - self.total_cost
        hired = frozenset(whoami for whoami, is_hired in self.hired.items() if is_hired)
        return Deployment(tuple(self.selection), money_delta, hired)
