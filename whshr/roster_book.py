"""Headless Army Records (roster book) state: hire/fire with coffers, and the reinforcement offer.

Behavioural source: notes/builtin_widgets.md §2 (variants, Hire/Fire rules, reinforcement sub-window),
notes/troop_selection.md §4.3 and §8, notes/campaign.md §2.4. Two variants share the Army Records screen:

* the **caravan** book (``RosterBook``): ``ArmyBook`` (no money) and ``HireOnlyArmyBook`` (hiring charges
  the coffers and can be undone for a refund within the same visit);
* the **selection** book opened by Ctrl+click, whose Hire/Fire lives on ``TroopSelection`` and which shares
  only the :class:`~whshr.reinforcements.ReinforcementLedger`.
"""

from collections.abc import Iterable, Mapping
from typing import Protocol

from .reinforcements import ReinforcementLedger
from .roster import ALWAYS_FORCED_WHOAMI, Regiment
from .troop_selection import DEFAULT_LIMIT, LIMIT_RANGE


class BookModel(Protocol):
    """What the Army Records screen needs from either variant's model."""

    company: dict[int, Regiment]
    hired: dict[int, bool]
    ledger: ReinforcementLedger
    pays: bool  # hiring charges the coffers (HireOnlyArmyBook)
    coffers: int
    selection: list[int]

    def hire_fire_enabled(self, whoami: int) -> bool: ...

    def toggle_hired(self, whoami: int) -> bool: ...

    def restore_book_hired(self, snapshot: Mapping[int, bool]) -> None: ...

    @property
    def dirty(self) -> bool: ...


class RosterBook:
    """The caravan's Army Records; notes/builtin_widgets.md §2.1, §2.3."""

    def __init__(self, company: Iterable[Regiment], *, coffers: int, reinforcements: Mapping[int, int],
                 pays: bool, limit: int = DEFAULT_LIMIT) -> None:
        self.company: dict[int, Regiment] = {regiment.whoami: regiment for regiment in company}
        self.pays = pays
        self.coffers = coffers
        self.limit = max(LIMIT_RANGE[0], min(LIMIT_RANGE[1], limit))
        # A forced regiment appears already hired, exactly as troop selection opens (§2.1).
        self.hired: dict[int, bool] = {whoami: regiment.hired or whoami == ALWAYS_FORCED_WHOAMI
                                       for whoami, regiment in self.company.items()}
        self.hired_at_open = dict(self.hired)
        # HireOnly starts with an empty list of new hires; Done merges it into the existing march.
        # The money-free book retains the forced regiment in its local selection.
        self.selection: list[int] = ([] if pays else
                                     [whoami for whoami, regiment in self.company.items()
                                      if whoami == ALWAYS_FORCED_WHOAMI and not regiment.destroyed])
        self.ledger = ReinforcementLedger(self.company, reinforcements)

    @property
    def dirty(self) -> bool:
        """Anything a Done must write: a hired flag differs from the snapshot, or men were taken."""
        return self.hired != self.hired_at_open or self.ledger.changed

    def hire_fire_enabled(self, whoami: int) -> bool:
        """notes/builtin_widgets.md §2.3 (money variant) and notes/troop_selection.md §4.3 table."""
        regiment = self.company[whoami]
        if not regiment.row.for_hire:
            return False
        if not self.pays:
            return True
        if self.hired_at_open[whoami]:
            return False
        return self.hired[whoami] or self.coffers >= regiment.price

    def toggle_hired(self, whoami: int) -> bool:
        """Hire or fire (whichever the label shows); returns whether anything changed."""
        if not self.hire_fire_enabled(whoami):
            return False
        regiment = self.company[whoami]
        if self.hired[whoami]:
            self.hired[whoami] = False
            if whoami in self.selection:
                self.selection.remove(whoami)
            if self.pays:
                self.coffers += regiment.price
        else:
            self.hired[whoami] = True
            if whoami not in self.selection and len(self.selection) < self.limit:
                self.selection.append(whoami)
            if self.pays:
                self.coffers -= regiment.price
        return True

    def restore_book_hired(self, snapshot: Mapping[int, bool]) -> None:
        """Abort: the hired flags return to the snapshot. The coffers are deliberately *not* restored
        (notes/builtin_widgets.md §2.3 quirk: the money variant charged each click at once)."""
        self.hired.update(snapshot)
        self.selection[:] = [whoami for whoami in self.selection if self.hired[whoami]]
