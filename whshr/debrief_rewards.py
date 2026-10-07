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


def promote(regiment: Regiment, before: int, after: int) -> tuple[Regiment, list[str], list[str]]:
    """Apply every promotion whose threshold ``before < T <= after`` crosses; returns the regiment, what applied and
    what was skipped.

    Wizards learn one unknown spell from their existing college at each 1000 XP threshold, up to five spells."""
    notes: list[str] = []
    if regiment.row.wizard:
        crossed = after // 1000 - before // 1000
        if crossed <= 0:
            return regiment, notes, []
        known = list(magic.spell_codes(script.unit_view(regiment.raw)["spells"])) if regiment.raw else []
        college = next(((code - 1) // 5 for code in known if 1 <= code <= 15), None)
        if college is None:
            return regiment, notes, [f"{regiment.name}: no known spell college for promotion"]
        for _ in range(crossed):
            candidates = [code for code in range(college * 5 + 1, college * 5 + 6) if code not in known]
            if len(known) >= MAX_WIZARD_SPELLS or not candidates:
                break
            code = random.choice(candidates)
            known.append(code)
            regiment = roster.with_spell(regiment, magic.SPELLS[code].name)
            regiment = roster.with_points(regiment, regiment.points + PROMOTION_POINTS)
            regiment = roster.with_base_price(regiment, regiment.row.base_price + WIZARD_PRICE)
            notes.append(f"{regiment.name}: learned {magic.SPELLS[code].name}")
        return regiment, notes, []
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
