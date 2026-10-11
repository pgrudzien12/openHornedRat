"""Presentation of the area particle spells (notes/spell_area_particle_visuals.md): The Flock of Doom and Conflagration
of Doom.

Pure Python (no GPU), so it is unit-testable. Every random choice of these spells belongs to the battle (the birds'
points, the bursts and their flames, which decide when Conflagration ends), so this module only turns the battle's
state and the effect's age into frames; it keeps no state of its own. A cancelled effect is not seen again, so all its
art goes on that update. Ages count from the launch tick T.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .. import spell_effects
from .spell_visuals import MeshItem, Sprite

if TYPE_CHECKING:
    from ..engine import Battle

Point = tuple[float, float]

# Section 1.3: the Flock's runs.
FLOCK_APPROACH, FLOCK_STRIKE, FLOCK_FLY_OFF = 357, 367, 375  # 357-366, 367-374 per strike, 375-378
FLOCK_STRIKE_FROM, FLOCK_FLY_OFF_FROM, FLOCK_GONE = 10, 34, 38
# Section 2: Conflagration of Doom.
FALL_HEIGHTS = (120, 106, 93, 80, 66, 53, 40, 26, 13, 0)  # trunc(120 r / 9), r = 9 .. 0
FLASH_FIRST, FLASH_FRAMES = 108, 9
BURST_FIRST, BURST_ALTERNATIVE_FIRST = 177, 541

AREA_CODES = frozenset({spell_effects.FLOCK, spell_effects.CONFLAGRATION})


@dataclass(frozen=True)
class AreaSpell:
    """One active area spell seen this tick: `age` since launch (0 on T), the aim P, the Flock's birds (x, y, 0),
    Conflagration's k (`value`) and burst places."""
    serial: int
    code: int
    age: int
    aim: Point
    birds: tuple[tuple[float, float, float], ...] = ()
    value: int = 1
    places: tuple[spell_effects.BurstPlace | None, ...] = ()


def flock_frame(age: int) -> int | None:
    """Every bird's frame (section 1.3): the approach on T..T+9, a strike cycle of eight frames from T+10, T+18 and
    T+26, the fly-off on T+34..T+37, nothing from T+38."""
    if age < FLOCK_STRIKE_FROM:
        return FLOCK_APPROACH + age
    if age < FLOCK_FLY_OFF_FROM:
        return FLOCK_STRIKE + (age - FLOCK_STRIKE_FROM) % 8
    if age < FLOCK_GONE:
        return FLOCK_FLY_OFF + age - FLOCK_FLY_OFF_FROM
    return None


def falling_fire_base(k: int) -> int:
    """The falling fire's size grows with the fuse (section 2.1): k 1 -> 92, 2-3 -> 96, 4-5 -> 100, 6 -> 104."""
    return 92 if k <= 1 else 96 if k <= 3 else 100 if k <= 5 else 104


def area_sprites(spell: AreaSpell) -> list[Sprite]:
    age = spell.age
    if spell.code == spell_effects.FLOCK:
        frame = flock_frame(age)
        return [] if frame is None else [Sprite(frame, x, y, height) for x, y, height in spell.birds]
    fall = age - 9 * spell.value  # section 2.3: nothing is drawn during the fuse
    drawn: list[Sprite] = []
    if 0 <= fall < len(FALL_HEIGHTS):
        drawn.append(Sprite(falling_fire_base(spell.value) + fall % 4, *spell.aim, FALL_HEIGHTS[fall]))
    flash = fall - len(FALL_HEIGHTS)
    if 0 <= flash < FLASH_FRAMES:
        drawn.append(Sprite(FLASH_FIRST + flash, *spell.aim, 0.0))
    drawn += [Sprite((BURST_ALTERNATIVE_FIRST if place.alternative else BURST_FIRST) + place.age, place.x, place.y, 0.0)
              for place in spell.places if place is not None and not place.phase]
    return drawn


def area_meshes(spell: AreaSpell) -> list[MeshItem]:
    """Conflagration's small flames (section 2.5): FLAMES1-4 at each burnt-out burst's point plus its flicker, on the
    ground at the point itself, in the mesh's default orientation."""
    return [MeshItem(f"flames{place.phase}", place.x + place.jitter[0], place.y + place.jitter[1], 0.0, 0.0, 1.0,
                     ground_at=(place.x, place.y))
            for place in spell.places if place is not None and place.phase]


def area_effects(battle: Battle) -> list[AreaSpell]:
    """The area particle spells active after this tick's effect update (`elapsed` counts the updates)."""
    return [AreaSpell(effect.serial, effect.code, max(0, effect.elapsed - 1), effect.aim, tuple(effect.particles),
                      effect.value, tuple(effect.places))
            for effect in battle.spell_effects.active if not effect.ended and effect.code in AREA_CODES]
