"""The reinforcement offer of the Army Records screen; notes/builtin_widgets.md §2.4, notes/campaign.md §2.4."""

from collections.abc import Mapping

from .roster import Regiment, with_models


class ReinforcementLedger:
    """The reinforcement offer per regiment; notes/builtin_widgets.md §2.4, notes/campaign.md §2.4.

    ``available`` is the roster's reinforcement pool (glue ``addtroop``). When a book opens, each regiment
    is offered ``min(pool, orgsize - models - wounded)`` men. ``increase``/``decrease`` edit only the pending
    popup choice; ``take`` adds those men to the regiment and consumes them from the pool. ``company`` is
    shared with the owning model and updated in place when Hire is pressed.
    """

    def __init__(self, company: dict[int, Regiment], available: Mapping[int, int],
                 wounded: Mapping[int, int] | None = None) -> None:
        self.company = company
        self.wounded = {whoami: max(0, count) for whoami, count in (wounded or {}).items()}
        self.available: dict[int, int] = {whoami: count for whoami, count in available.items() if count > 0}
        self.offered: dict[int, int] = {}
        self.taken: dict[int, int] = {}
        for whoami, regiment in company.items():
            room = regiment.orgsize - regiment.models - self.wounded.get(whoami, 0)
            self.offered[whoami] = max(0, min(self.available.get(whoami, 0), room))
        self.changed = False
        self._opening = ({whoami: regiment.models for whoami, regiment in company.items()}, dict(self.available))

    def revert(self) -> None:
        """Abort: men moved into regiments and the pool go back to what they were when the book opened."""
        models, available = self._opening
        for whoami, count in models.items():
            self.company[whoami] = with_models(self.company[whoami], count)
        self.available = dict(available)
        self.taken.clear()
        self.changed = False

    def has_offer(self, whoami: int) -> bool:
        return self.offered.get(whoami, 0) > 0

    def offer_left(self, whoami: int) -> int:
        """``Available : n`` of the sub-window: offered minus taken."""
        return self.offered.get(whoami, 0) - self.taken.get(whoami, 0)

    def taken_count(self, whoami: int) -> int:
        return self.taken.get(whoami, 0)

    def increase(self, whoami: int) -> bool:
        if self.offer_left(whoami) <= 0:
            return False
        self.taken[whoami] = self.taken.get(whoami, 0) + 1
        return True

    def decrease(self, whoami: int) -> bool:
        if self.taken.get(whoami, 0) <= 0:
            return False
        self.taken[whoami] -= 1
        return True

    def take(self, whoami: int) -> int:
        """The Hire button: apply the pending choice and retain unused men for a later visit."""
        taken = self.taken.get(whoami, 0)
        if taken:
            regiment = self.company[whoami]
            self.company[whoami] = with_models(regiment, regiment.models + taken)
            self.changed = True
        self.available[whoami] = max(0, self.available.get(whoami, 0) - taken)
        self.offered[whoami] = 0
        self.taken[whoami] = 0
        return taken
