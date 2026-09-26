"""The reinforcement offer of the Army Records screen; notes/builtin_widgets.md §2.4, notes/campaign.md §2.4."""

from collections.abc import Mapping

from .roster import Regiment, with_models


class ReinforcementLedger:
    """The reinforcement offer per regiment; notes/builtin_widgets.md §2.4, notes/campaign.md §2.4.

    ``available`` is the roster's reinforcement pool (glue ``addtroop``). When a book opens, each regiment
    is offered ``min(pool, orgsize - models)`` men. ``increase``/``decrease`` move men into or out of the
    regiment at once (so its price changes immediately); ``take`` consumes the offer and keeps the unused
    rest of the pool for a later visit. ``company`` is shared with the owning model and updated in place.
    """

    def __init__(self, company: dict[int, Regiment], available: Mapping[int, int]) -> None:
        self.company = company
        self.available: dict[int, int] = {whoami: count for whoami, count in available.items() if count > 0}
        self.offered: dict[int, int] = {}
        self.taken: dict[int, int] = {}
        for whoami, regiment in company.items():
            # Wounded/away men also count against the room; the engine does not track them yet (GEI8).
            room = regiment.orgsize - regiment.models
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
        self.company[whoami] = with_models(self.company[whoami], self.company[whoami].models + 1)
        self.changed = True
        return True

    def decrease(self, whoami: int) -> bool:
        if self.taken.get(whoami, 0) <= 0:
            return False
        self.taken[whoami] -= 1
        self.company[whoami] = with_models(self.company[whoami], self.company[whoami].models - 1)
        return True

    def take(self, whoami: int) -> int:
        """The Take button: consume the offer, return how many men joined."""
        taken = self.taken.get(whoami, 0)
        self.available[whoami] = max(0, self.available.get(whoami, 0) - taken)
        self.offered[whoami] = 0
        self.taken[whoami] = 0
        return taken
