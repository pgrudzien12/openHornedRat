"""Presentation of the transport spells (notes/spell_transport_visuals.md): the Flying Bower, the Sapphire Arch and
Skitterleap.

Pure Python (no GPU), so it is unit-testable. The battle owns every position that matters to gameplay (the Bower's
head and dust deposits, the Arch's sparkle points); this module turns them into frames, keyed by effect serial and
advanced once per battle tick with the effects still active after that tick's effect update. A cancelled effect is
not seen again, so all its art goes on that update (no shrink, no dust tail). Ages count from the launch tick T.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .. import spell_effects
from .spell_visuals import MeshItem, Sprite

if TYPE_CHECKING:
    from ..engine import Battle

Point = tuple[float, float]

# Section 2: the Flying Bower.
VORTEX_FORMING, VORTEX_LOOP = 186, 191  # 186-190 once, then 191-193
LIFT, LANDING = spell_effects.BOWER_LIFT, spell_effects.BOWER_LIFT + spell_effects.BOWER_FLIGHT + 1  # T+19, T+74
DUST_FIRST, DUST_FRAMES = 194, 5
# Section 3: the Sapphire Arch.
ARCH_MESH, ARCH_SPARKLE, ARCH_GROWN, ARCH_SHRINK, ARCH_GONE = "sapharch", 558, 18, 162, 180
# Section 4: Skitterleap.
SMOKE_FIRST, SMOKE_FRAMES = 529, 4

TRANSPORT_CODES = frozenset({spell_effects.FLYING_BOWER, spell_effects.SAPPHIRE_ARCH, spell_effects.SKITTERLEAP})


@dataclass(frozen=True)
class TransportSpell:
    """One active transport spell seen this tick: `age` since launch (0 on T); the Bower's head and dust deposits with
    their birth ticks; the Arch's sparkles (x, y, height above the ground there); the caster's footprint centre and
    figure positions (None / empty when the caster is gone)."""
    serial: int
    code: int
    age: int
    aim: Point
    head: Point = (0.0, 0.0)
    dust: tuple[Point, ...] = ()
    dust_births: tuple[int, ...] = ()
    sparkles: tuple[tuple[float, float, float], ...] = ()
    caster: Point | None = None
    figures: tuple[Point, ...] = ()


@dataclass
class _State:
    heading: Point = (0.0, 1.0)  # the Arch's caster-to-aim bearing at launch
    smoke: tuple[Point, ...] = ()  # Skitterleap's departure points


@dataclass
class TransportVisuals:
    """Presentation state of the transport spells. The Arch's heading and Skitterleap's departure points are taken on
    the first update an effect is seen (its launch tick, unless several ticks pass between two drawn frames)."""
    states: dict[int, _State] = field(default_factory=dict[int, _State])
    current: list[TransportSpell] = field(default_factory=list[TransportSpell])

    def advance(self, seen: Iterable[TransportSpell]) -> None:
        self.current = [spell for spell in seen if spell.code in TRANSPORT_CODES]
        alive = {spell.serial for spell in self.current}
        self.states = {serial: state for serial, state in self.states.items() if serial in alive}
        for spell in self.current:
            if spell.serial in self.states:
                continue
            state = self.states[spell.serial] = _State()
            if spell.code == spell_effects.SAPPHIRE_ARCH and spell.caster is not None:
                dx, dy = spell.aim[0] - spell.caster[0], spell.aim[1] - spell.caster[1]
                state.heading = (dx, dy) if dx or dy else (0.0, 1.0)
            elif spell.code == spell_effects.SKITTERLEAP:
                state.smoke = spell.figures

    def sprites(self) -> list[Sprite]:
        drawn: list[Sprite] = []
        for spell in self.current:
            age = spell.age
            if spell.code == spell_effects.FLYING_BOWER:
                if age < LANDING:
                    drawn.append(Sprite(vortex_frame(age), *spell.head, 0.0))
                drawn += [Sprite(DUST_FIRST + age - birth, x, y, 0.0)
                          for (x, y), birth in zip(spell.dust, spell.dust_births) if 0 <= age - birth < DUST_FRAMES]
            elif spell.code == spell_effects.SAPPHIRE_ARCH:
                if age < ARCH_GONE:
                    drawn += [Sprite(ARCH_SPARKLE + age % 4, x, y, height) for x, y, height in spell.sparkles]
            elif age < SMOKE_FRAMES:
                drawn += [Sprite(SMOKE_FIRST + age, x, y, 0.0) for x, y in self.states[spell.serial].smoke]
        return drawn

    def meshes(self) -> list[MeshItem]:
        return [MeshItem(ARCH_MESH, *spell.aim, 0.0, *self.states[spell.serial].heading, scale=arch_scale(spell.age))
                for spell in self.current if spell.code == spell_effects.SAPPHIRE_ARCH and spell.age < ARCH_GONE]


def vortex_frame(age: int) -> int:
    """The Bower's head (section 2.1): 186-190 on T..T+4, then 191-193; the flight head replaces the take-off head at
    T+19 without restarting, its phase repeated once (193 on T+19 and T+20)."""
    if age < VORTEX_LOOP - VORTEX_FORMING:
        return VORTEX_FORMING + age
    if age < LIFT:
        return VORTEX_LOOP + (age - 5) % 3
    if age == LIFT:
        return VORTEX_LOOP + 2
    return VORTEX_LOOP + (age - 21) % 3


def arch_scale(age: int) -> float:
    """The arch's uniform size (section 3.1): 10% at T, +5% a tick to 95% at T+17, full from T+18 to T+161, then -5%
    a tick to 10% at T+179."""
    if age < ARCH_GROWN:
        return (10 + 5 * age) / 100
    if age < ARCH_SHRINK:
        return 1.0
    return (100 - 5 * (age - ARCH_SHRINK + 1)) / 100


def transport_effects(battle: Battle) -> list[TransportSpell]:
    """The transport spells active after this tick's effect update (`elapsed` counts the updates)."""
    seen: list[TransportSpell] = []
    for effect in battle.spell_effects.active:
        if effect.ended or effect.code not in TRANSPORT_CODES:
            continue
        owner = battle.regiments.get(effect.owner)
        alive = owner is not None and owner.active
        seen.append(TransportSpell(
            effect.serial, effect.code, max(0, effect.elapsed - 1), effect.aim, (effect.x, effect.y),
            tuple(effect.trail), tuple(effect.trail_births), tuple(effect.particles),
            spell_effects.footprint_centre(owner) if owner is not None and alive else None,
            tuple(owner.model_positions()) if owner is not None and alive else ()))
    return seen
