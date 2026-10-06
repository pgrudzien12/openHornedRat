"""Magic Book entry tables and company-derived visibility (notes/native-windows.md §5)."""

from collections.abc import Sequence

from . import script
from .magic import SPELL_CODES
from .roster import Regiment

ITEM_IDS = (
    "ItemBannerOfWrath", "ItemBannerOfArcaneWarding", "ItemBannerOfArcaneProtection",
    "ItemArmourOfTheBeard", "ItemDragonBlade", "ItemDreadBanner", "ItemGrudgeBringer",
    "ItemSwordOfHeroes", "ItemArmourOfMeteoricIron", "ItemBannerOfMight",
    "ItemParryingBlade", "ItemPotionOfStrength", "ItemShieldOfPtolos", "ItemRockSplitter",
    "ItemSwordOfMight", "ItemTalismanOfObsidian", "ItemSwordOfElior",
)

# (bitmap resource, BKTXT RCDATA resource), ordered by book entry.
SPELL_ENTRIES = (
    ("CelestialMagicPic", "SpeCelestialText"),
    ("BrightMagicPic", "SpeBrightText"),
    ("AmberMagicPic", "SpeAmberText"),
)
ITEM_ENTRIES = (
    ("BanOfWrathPic", "BanOfWrathText"),
    ("BanOfArcaneWardingPic", "BanOfArcaneWardingText"),
    ("BanOfArcaneProtectionPic", "BanOfArcaneProtectionText"),
    ("ArmOfBeardPic", "ArmOfBeardText"),
    ("SwoDragonPic", "SwoDragonText"),
    ("BanDreadPic", "BanDreadText"),
    ("SwoGrudgebringerPic", "SwoGrudgebringerText"),
    ("SwoOfHerosPic", "SwoOfHerosText"),
    ("ArmOfMeteoricIronPic", "ArmOfMeteoricIronText"),
    ("BanOfMightPic", "BanOfMightText"),
    ("SwoParryingPic", "SwoParryingText"),
    ("PotOfStrengthPic", "PotOfStrengthText"),
    ("ShiOfPtolosPic", "ShiOfPtolosText"),
    ("SwoRocksplitterPic", "SwoRocksplitterText"),
    ("SwoOfMightPic", "SwoOfMightText"),
    ("TalOfObsidianPic", "TalOfObsidianText"),
    ("SwoOfEliorPic", "SwoOfEliorText"),
)
ENTRIES = (SPELL_ENTRIES, ITEM_ENTRIES)


def known_entries(company: Sequence[Regiment]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Include unit-level spells and items from every company regiment, hired or not."""
    spells: set[int] = set()
    items: set[str] = set()
    for regiment in company:
        if regiment.raw is None:
            continue
        unit = script.unit_view(regiment.raw)
        for name in unit.get("spells") or ():
            code = SPELL_CODES.get(str(name).casefold())
            if code is not None and 1 <= code <= 15:
                spells.add((code - 1) // 5)
        items.update(str(name) for name in unit.get("items") or ())
    return tuple(sorted(spells)), tuple(i for i, name in enumerate(ITEM_IDS) if name in items)
