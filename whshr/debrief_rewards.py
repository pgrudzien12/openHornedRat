"""What the debrief's Done applies to the company besides the payment: armour rewards, experience and promotions
(notes/campaign.md 1.2-1.4, notes/native-windows.md 9.9.1)."""

from collections.abc import Iterable
import random

from . import magic, roster, script
from .debrief_screen import ARMOUR_REWARDS, DebriefUnit
from .roster import Regiment
from .rules import MISSILE_RANGES, stat_fields, stat_int

# notes/campaign.md 1.3: an experience threshold crossed once gives +1 to one troop stat.
PROMOTION_THRESHOLDS: tuple[tuple[int, str], ...] = ((2000, "s_wepn"), (4000, "s_strn"), (6000, "s_wnds"))
PROMOTION_PRICE, PROMOTION_POINTS = 5, 7
WIZARD_PRICE = 15
MAX_WIZARD_SPELLS = 5


def _shooting_regiment(regiment: Regiment) -> bool:
    """Archers, artillery, and other units carrying a ranged weapon improve BS at 2000 XP."""
    if regiment.row.artillery:
        return True
    if regiment.raw is None:
        return False
    fields, _ = stat_fields(script.unit_view(regiment.raw)["stats"])
    race = stat_int(fields, "s_race")
    weapon = stat_int(fields, "S_BalWeap")
    return (race is not None and race >> 3 in (3, 4)) or weapon in MISSILE_RANGES


def _learn_spell(regiment: Regiment) -> tuple[Regiment, str | None, str | None]:
    """One wizard level's spell (notes/native-windows.md 9.13.1); returns the regiment, the learned spell's name and a
    diagnostic.  The college is that of the first college spell in list order (Dispel Magic, the Waaagh and the Skaven
    spells are skipped); the new spell is uniform over the college's unknown spells, and the list is then re-sorted by
    casting cost, highest first, keeping the order of equal costs.  A wizard without a college spell learns nothing
    (undefined in the original; the report recommends a diagnostic)."""
    known = list(magic.spell_codes(script.unit_view(regiment.raw)["spells"])) if regiment.raw else []
    if len(known) >= MAX_WIZARD_SPELLS:
        return regiment, None, None
    college = next(((code - 1) // 5 for code in known if 1 <= code <= 15), None)
    if college is None:
        return regiment, None, f"{regiment.name}: no known spell college for promotion"
    candidates = [code for code in range(college * 5 + 1, college * 5 + 6) if code not in known]
    code = random.choice(candidates)
    ordered = sorted([*known, code], key=lambda spell: -magic.SPELLS[spell].cost)
    regiment = roster.with_spell(regiment, magic.SPELLS[code].name)
    regiment = roster.with_spell_order(regiment, [magic.SPELLS[spell].name for spell in ordered])
    return regiment, magic.SPELLS[code].name, None


def promote(regiment: Regiment, before: int, after: int) -> tuple[Regiment, list[str], list[str]]:
    """Apply every promotion whose threshold ``before < T <= after`` crosses; returns the regiment, what applied and
    what was skipped.

    A wizard (the roster's ``wizard`` field) gains, at each 1000 XP threshold, one unknown spell of its college while it
    knows fewer than five, then +15 price per model (only when the price is not 0) and +7 ``s_pntval`` whether or not
    a spell was learned (notes/native-windows.md 9.13.1)."""
    notes: list[str] = []
    if regiment.row.wizard:
        crossed = after // 1000 - before // 1000
        if crossed <= 0:
            return regiment, notes, []
        skipped: list[str] = []
        for _ in range(crossed):
            regiment, learned, problem = _learn_spell(regiment)
            if learned is not None:
                notes.append(f"{regiment.name}: learned {learned}")
            if problem is not None and problem not in skipped:
                skipped.append(problem)
            if regiment.row.base_price:  # a wizard who serves for free stays free (as troops do, §1.3)
                regiment = roster.with_base_price(regiment, regiment.row.base_price + WIZARD_PRICE)
            regiment = roster.with_points(regiment, regiment.points + PROMOTION_POINTS)
        return regiment, notes, skipped
    for threshold, stat in PROMOTION_THRESHOLDS:
        if not before < threshold <= after:
            continue
        if stat == "s_wepn" and _shooting_regiment(regiment):
            stat = "s_bals"
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
