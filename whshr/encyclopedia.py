"""Clean-room Encyclopedia entry order and default unlocks (native-windows.md §6)."""

# Each row is (save flag key, BITMAP.DLL picture, BKTXT.DLL RCDATA description).
ENTRIES: tuple[tuple[int, str, str], ...] = (
    (28, "MenPic", "MenText"), (6, "DwarfPic", "DwarfText"),
    (12, "GyrocopterPic", "GyrocopterText"), (22, "SlayerPic", "SlayerText"),
    (1, "WoodElfPic", "WoodElfText"), (10, "GoblinPic", "GoblinText"),
    (3, "DoomDiverPic", "DoomDiverText"), (8, "FanaticPic", "FanaticText"),
    (13, "NiteGoblinPic", "NiteGoblinText"), (14, "NiteShamanPic", "NiteShamanText"),
    (23, "SquigPic", "SquigText"), (26, "WolvesPic", "WolvesText"),
    (0, "OrcPic", "OrcText"), (27, "BlackOrcPic", "BlackOrcText"),
    (2, "WarBoarPic", "WarBoarText"), (15, "OrcShamanPic", "OrcShamanText"),
    (19, "RockLobberPic", "RockLobberText"), (21, "SkavenPic", "SkavenText"),
    (4, "DoomWheelPic", "DoomWheelText"), (7, "EshinPic", "EshinText"),
    (20, "SeerPic", "SeerText"), (16, "PackMasterPic", "PackMasterText"),
    (17, "PlaguePic", "PlagueText"), (18, "RatOgrePic", "RatOgreText"),
    (25, "WarpFirePic", "WarpFireText"), (5, "DragonPic", "DragonText"),
    (9, "GiantPic", "GiantText"), (24, "TrollPic", "TrollText"),
)

DEFAULT_KEYS = frozenset((0, 6, 10, 21, 28))


def known_positions(flags: set[int]) -> tuple[int, ...]:
    """Map save flag keys to the book's fixed display positions."""
    return tuple(position for position, (key, _, _) in enumerate(ENTRIES) if key in flags)
