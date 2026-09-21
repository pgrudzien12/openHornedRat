"""Company roster: the static per-``whoami`` RMYI table and the starting company (STRTARMY.MRC).

Behavioral source: notes/campaign.md sections 3.1 (whoami/hired unit fields) and 4.5 (the RMYI
static roster table). Data is read from the user's own installation at runtime; nothing here is
copied game content (`notes/campaign.md` §4.5's full table already lives in that note as a fact,
not as copyrightable expression).
"""

from dataclasses import dataclass

from .paths import Installation
from .rules import PeImage, stat_fields
from . import script

# WHSHR.EXE .data VA of the 39-record RMYI table (record 38 is the -1 terminator); notes/campaign.md §4.5.
RMYI_VA, RMYI_COUNT, RMYI_STRIDE = 0x5B95F0, 39, 0x34
STARTING_COMPANY = ("SCRIPT", "STRTARMY.MRC")
ALWAYS_FORCED_WHOAMI = 2  # Grudgebringer Cavalry (the commander); notes/campaign.md §2.3, §3.3


@dataclass(frozen=True)
class RosterRow:
    """One static RMYI record: notes/campaign.md §4.5."""

    whoami: int
    keep: bool
    for_hire: bool
    wizard: bool
    artillery: bool
    base_price: int


def static_roster(installation):
    """The 38 RMYI rows read from WHSHR.EXE, keyed by whoami."""
    game = installation if isinstance(installation, Installation) else Installation(installation)
    image = PeImage(game.require("WHSHR.EXE"))
    rows = {}
    for whoami in range(RMYI_COUNT - 1):
        record = image.u32(RMYI_VA + RMYI_STRIDE * whoami, 13)
        rows[whoami] = RosterRow(whoami, keep=bool(record[0]), for_hire=bool(record[1]),
                                 wizard=bool(record[2]), artillery=bool(record[3]), base_price=record[9])
    return rows


@dataclass(frozen=True)
class Regiment:
    """A company regiment: its current .MRC unit merged with its static roster row."""

    whoami: int
    name: str
    hired: bool
    models: int
    orgsize: int
    points: int
    row: RosterRow
    weapon_name: int = 0
    armour: int = 0
    banner: str | None = None
    profile: tuple = ()
    experience: int = 0
    leader_name: str | None = None
    leader_portrait: str | None = None
    leader_profile: tuple = ()
    leader_armour: int = 0
    leader_weapon: int = 0

    @property
    def destroyed(self):
        """notes/troop_selection.md §3.4: artillery with fewer than 2 models, otherwise 0 models."""
        return self.models < 2 if self.row.artillery else self.models <= 0

    @property
    def price(self):
        """notes/campaign.md §2.3: price per model x current models.

        Routed models (``s_routed``) are not tracked yet: a freshly loaded company always has
        0 routed, and updating a regiment's model count after a battle is not implemented
        (notes/glue_engine_integration.md GEI8, debrief).
        """
        return self.row.base_price * self.models

    @property
    def retainer(self):
        """10% of price; notes/campaign.md §2.3."""
        return self.price // 10


def load_company(installation, roster=None, path=STARTING_COMPANY):
    """Load a company .MRC (``STRTARMY.MRC`` for a new campaign) into ``Regiment`` records.

    ``roster`` may be supplied directly (a ``{whoami: RosterRow}`` mapping) to avoid reading
    WHSHR.EXE, e.g. in tests.
    """
    game = installation if isinstance(installation, Installation) else Installation(installation)
    roster = roster if roster is not None else static_roster(game)
    army = script.load_army(str(game.file_dir(*path)))
    regiments = []
    for group in army["armies"]:
        for unit in group["units"]:
            whoami = unit["set"].get("whoami")
            row = roster.get(whoami) if whoami is not None else None
            if row is None:
                continue
            fields = stat_fields(unit["stats"])[0]
            leader = unit.get("leader")
            leader_fields = stat_fields(leader["stats"])[0] if leader is not None else {}
            regiments.append(Regiment(
                whoami=whoami, name=unit["name"], hired=bool(unit["set"].get("hired", 0)),
                models=fields.get("s_size", 0), orgsize=fields.get("s_orgsize", 0),
                points=fields.get("s_pntval", 0), row=row,
                weapon_name=fields.get("s_weponame", 0), armour=fields.get("s_armr", 0),
                banner=unit.get("banner"),
                profile=tuple(fields.get(name, 0) for name in
                              ("s_move", "s_wepn", "s_bals", "s_strn", "s_tuff", "s_wnds", "s_init", "s_atks", "s_lead")),
                # s_Exp is outside the contiguous profile block consumed by
                # stat_fields(); Army Records displays it (§8, campaign §1).
                experience=(unit["stats"].get("s_Exp") or [0])[0],
                leader_name=leader["name"] if leader else None,
                leader_portrait=leader["portrait"] if leader else None,
                leader_profile=tuple(leader_fields.get(name, 0) for name in
                                     ("s_move", "s_wepn", "s_bals", "s_strn", "s_tuff", "s_wnds", "s_init", "s_atks", "s_lead")),
                leader_armour=leader_fields.get("s_armr", 0),
                leader_weapon=leader_fields.get("s_weponame", 0),
            ))
    return tuple(regiments)
