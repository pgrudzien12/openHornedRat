"""Spell table, power pools and the AI spell-choice rules used by the unit-script magic opcodes.

Public sources: game_rules.md "Winds of magic and casting" (pools, costs), "Spells" (ranges), "AI casting",
and notes/script_magic.md (spell codes, choice rules, payment). Stdlib only, no engine imports.
"""

from collections.abc import Iterable
from dataclasses import dataclass
import random

INCH = 24  # world units per inch (game_rules.md section 8.3: 24" = 576)
MAX_POWER = 8
UNLIMITED: None = None

# AI acceptance rules (notes/script_magic.md 2.2).
NEVER, ARC, MADNESS, AZURE, FISTS, AREA, FRIEND_POINT, SKITTER, DISPEL = (
    "never", "arc", "madness", "azure", "fists", "area", "friend_point", "skitter", "dispel")


@dataclass(frozen=True)
class Spell:
    code: int
    name: str  # the `addspell:` identifier of the battle and army files
    cost: int
    range: int | None  # world units, strict `trunc(d) < range`; None = unlimited (or not a ranged spell)
    rule: str
    area_radius: int = 0  # the AREA rule's "no non-friend within" radius


# PROVISIONAL: "own unit" / "self" spells (Azure Blades, Dispel Magic, Fists of Gork) have no listed range; they
# are treated as unlimited for the range step, their own rule limits the distance. Wind Blast's range is rolled.
SPELLS: dict[int, Spell] = {spell.code: spell for spell in (
    Spell(1, "CelestialWindBlast", 2, None, NEVER),
    Spell(2, "CelestialAzureBlades", 1, None, AZURE),
    Spell(3, "CelestialStormOfShemtek", 3, 24 * INCH, ARC),
    Spell(4, "CelestialSapphireArch", 2, 24 * INCH, NEVER),
    Spell(5, "CelestialLightning", 1, 24 * INCH, ARC),
    Spell(6, "BrightPiercingBoltsOfBurning", 2, 18 * INCH, ARC),
    Spell(7, "BrightBurningHead", 2, 18 * INCH, ARC),
    Spell(8, "BrightConflagrationOfDoom", 3, None, AREA, 56),
    Spell(9, "BrightFlamestorm", 3, 24 * INCH, ARC),
    Spell(10, "BrightFireball", 1, 24 * INCH, ARC),
    Spell(11, "AmberFlyingBower", 1, None, AREA, 32),
    Spell(12, "AmberTanglingThorn", 3, 24 * INCH, AREA, 32),
    Spell(13, "AmberHuntingSpear", 2, 24 * INCH, ARC),
    Spell(14, "AmberCurseOfAnraheir", 3, 24 * INCH, ARC),
    Spell(15, "AmberFlockOfDoom", 2, 24 * INCH, AREA, 32),
    Spell(16, "GeneralDispel", 1, None, DISPEL),
    Spell(17, "WaaaghGazeOfMork", 2, 24 * INCH, ARC),
    Spell(18, "WaaaghEreWeGo", 2, 36 * INCH, FRIEND_POINT),
    Spell(19, "WaaaghDaKrunch", 3, 24 * INCH, AREA, 32),
    Spell(20, "WaaaghFistsOfGork", 2, None, FISTS),
    Spell(21, "WaaaghMorkSaveUz", 1, 24 * INCH, FRIEND_POINT),
    Spell(22, "SkavenWarpLightning", 2, 24 * INCH, ARC),
    Spell(23, "SkavenSkitterleap", 1, None, SKITTER),
    Spell(24, "SkavenPestilentBreath", 1, 6 * INCH, ARC),
    Spell(25, "SkavenMadness", 2, 24 * INCH, MADNESS),
)}
SPELL_CODES = {spell.name.casefold(): spell.code for spell in SPELLS.values()}
WIND_BLAST = 1
MADNESS_SPELL = 25


def spell_codes(names: Iterable[str]) -> tuple[int, ...]:
    """A unit's spell list from its `addspell:` lines, in file order; unknown entries (casting-mode markers such as
    `CastOnce`) are skipped."""
    return tuple(SPELL_CODES[name.casefold()] for name in names if name.casefold() in SPELL_CODES)


def cost(code: int) -> int | None:
    """The cost of a spell code, ignoring the high marker bits a script may add (notes/script_magic.md 3.1)."""
    spell = SPELLS.get(code & 0xFF)
    return spell.cost if spell is not None else None


def spell_range(code: int, rng: random.Random) -> int | None:
    """The range of a spell: world units, or None for unlimited. A code carrying a marker bit is not recognised
    and is unlimited (notes/script_magic.md 3.1). Wind Blast draws a fresh range on every call:
    96 x (1 + rand mod 6), i.e. 4, 8 .. 24 inches (notes/spell_area_effects.md 1.1)."""
    if code == WIND_BLAST:
        return 4 * INCH * (1 + rng.randrange(6))
    spell = SPELLS.get(code)
    return spell.range if spell is not None else None


def in_range(distance: float, code: int, rng: random.Random) -> bool:
    """`trunc(d) < range`, unlimited spells always pass."""
    limit = spell_range(code, rng)
    return limit is None or int(distance) < limit


class PowerPools:
    """The player and enemy power pools, each clamped to 0..8 on every write; allies use the player's
    (game_rules.md "Winds of magic and casting"); the wind that replaces both every 50 s is
    whshr.spell_effects.blow_wind."""

    def __init__(self, player: int, enemy: int) -> None:
        self.player = max(0, min(MAX_POWER, player))
        self.enemy = max(0, min(MAX_POWER, enemy))

    @classmethod
    def rolled(cls, rng: random.Random) -> "PowerPools":
        """Each pool starts at 1-8."""
        return cls(rng.randrange(8) + 1, rng.randrange(8) + 1)

    def get(self, enemy_army: bool) -> int:
        return self.enemy if enemy_army else self.player

    def add(self, enemy_army: bool, amount: int) -> None:
        value = max(0, min(MAX_POWER, self.get(enemy_army) + amount))
        if enemy_army:
            self.enemy = value
        else:
            self.player = value
