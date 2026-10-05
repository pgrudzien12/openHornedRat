"""What the debrief's Done applies to the company besides the payment: armour rewards, experience and promotions
(notes/campaign.md 1.2-1.4, notes/native-windows.md 9.9.1)."""

from collections.abc import Iterable

from . import roster
from .debrief_screen import ARMOUR_REWARDS, DebriefUnit
from .roster import Regiment

# notes/campaign.md 1.3: an experience threshold crossed once gives +1 to one troop stat.
PROMOTION_THRESHOLDS: tuple[tuple[int, str], ...] = ((2000, "s_wepn"), (4000, "s_strn"), (6000, "s_wnds"))
PROMOTION_PRICE, PROMOTION_POINTS = 5, 7


def promote(regiment: Regiment, before: int, after: int) -> tuple[Regiment, list[str], list[str]]:
    """Apply every promotion whose threshold ``before < T <= after`` crosses; returns the regiment, what applied and
    what was skipped.

    Wizards learn spells instead of gaining a stat, which the engine does not model: nothing is applied for them."""
    notes: list[str] = []
    if regiment.row.wizard:
        crossed = after // 1000 - before // 1000
        skipped = [f"{regiment.name}: {crossed} spell promotion(s) (spells are not modelled)"] if crossed > 0 else []
        return regiment, notes, skipped
    for threshold, stat in PROMOTION_THRESHOLDS:
        if not before < threshold <= after:
            continue
        regiment = roster.with_improved_stat(regiment, stat)
        regiment = roster.with_points(regiment, regiment.points + PROMOTION_POINTS)
        if regiment.row.base_price:
            regiment = roster.with_base_price(regiment, regiment.row.base_price + PROMOTION_PRICE)
        notes.append(f"{regiment.name}: +1 {stat}")
    return regiment, notes, []


def apply_rewards(company: Iterable[Regiment], units: Iterable[DebriefUnit], multiplier: int,
                  armour_rewards: bool) -> tuple[tuple[Regiment, ...], list[str], list[str]]:
    """The company after armour rewards, experience (times ``multiplier``) and promotions, with what was applied
    and what was skipped."""
    fought = {unit.whoami: unit for unit in units}
    applied: list[str] = []
    skipped: list[str] = []
    updated: list[Regiment] = []
    for regiment in company:
        unit = fought.get(regiment.whoami)
        if unit is not None:
            if armour_rewards and regiment.whoami in ARMOUR_REWARDS and unit.shown_models > 0:
                regiment = roster.with_improved_stat(regiment, "s_armr")
                applied.append(f"{regiment.name}: +1 armour")
            gained = unit.gained * multiplier
            if gained:
                after = unit.experience_start + gained
                regiment = roster.with_experience(regiment, after)
                applied.append(f"{regiment.name}: +{gained} experience")
                regiment, notes, left = promote(regiment, unit.experience_start, after)
                applied.extend(notes)
                skipped.extend(left)
        updated.append(regiment)
    return tuple(updated), applied, skipped
