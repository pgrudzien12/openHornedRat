# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Company roster: the static per-``whoami`` RMYI table, the starting company (STRTARMY.MRC),
and writing the engine's own roster/marching-order saves.

Behavioral source: notes/campaign.md sections 3.1 (whoami/hired unit fields) and 4.5 (the RMYI
static roster table). Data is read from the user's own installation at runtime; nothing here is
copied game content (`notes/campaign.md` §4.5's full table already lives in that note as a fact,
not as copyrightable expression). Writes (``write_company``/``write_march``) never touch the
original installation: they go to the engine's own save directory, not the original's `SAVE/`
(notes/glue_engine_integration.md GEI7e). The engine keeps no other save/load compatibility
promise toward the original (format included); reusing the readable `.MRC` grammar here is a
convenient current implementation choice, not a compatibility commitment (GEI14 owns the actual
save/load design).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from os import PathLike
from pathlib import Path

from .paths import Installation
from .rules import EXPECTED_STATS, PeImage, StatFields, stat_fields, stat_int
from . import script

# WHSHR.EXE .data VA of the 39-record RMYI table (record 38 is the -1 terminator); notes/campaign.md §4.5.
RMYI_VA, RMYI_COUNT, RMYI_STRIDE = 0x5B95F0, 39, 0x34
STARTING_COMPANY = ("SCRIPT", "STRTARMY.MRC")
MASTER_ROSTER = ("SCRIPT", "MAXARMY.MRC")  # all 38 regiments; the fresh-campaign PLAY.MRC (notes/campaign.md §4.4)
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


def static_roster(installation: Installation | str | PathLike[str]) -> dict[int, RosterRow]:
    """The 38 RMYI rows read from WHSHR.EXE, keyed by whoami."""
    game = installation if isinstance(installation, Installation) else Installation(installation)
    image = PeImage(game.require("WHSHR.EXE"))
    rows: dict[int, RosterRow] = {}
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
    profile: tuple[int, ...] = ()
    experience: int = 0
    leader_name: str | None = None
    leader_portrait: str | None = None
    leader_profile: tuple[int, ...] = ()
    leader_armour: int = 0
    leader_weapon: int = 0
    raw: script.Node | None = field(default=None, repr=False, compare=False)  # the parse() node, for write_company/write_march

    @property
    def destroyed(self) -> bool:
        """notes/troop_selection.md §3.4: artillery with fewer than 2 models, otherwise 0 models."""
        return self.models < 2 if self.row.artillery else self.models <= 0

    @property
    def price(self) -> int:
        """notes/campaign.md §2.3: price per model x current models.

        Routed models (``s_routed``) are not tracked yet: a freshly loaded company always has
        0 routed, and updating a regiment's model count after a battle is not implemented
        (notes/glue_engine_integration.md GEI8, debrief).
        """
        return self.row.base_price * self.models

    @property
    def retainer(self) -> int:
        """10% of price; notes/campaign.md §2.3."""
        return self.price // 10


def _stat(fields: StatFields, name: str) -> int:
    return stat_int(fields, name) or 0


_PROFILE_STATS = ("s_move", "s_wepn", "s_bals", "s_strn", "s_tuff", "s_wnds", "s_init", "s_atks", "s_lead")


def load_company(installation: Installation | str | PathLike[str], roster: Mapping[int, RosterRow] | None = None,
                 path: Sequence[str] = STARTING_COMPANY) -> tuple[Regiment, ...]:
    """Load a company .MRC (``STRTARMY.MRC`` for a new campaign) into ``Regiment`` records.

    ``roster`` may be supplied directly (a ``{whoami: RosterRow}`` mapping) to avoid reading
    WHSHR.EXE, e.g. in tests.
    """
    game = installation if isinstance(installation, Installation) else Installation(installation)
    roster = roster if roster is not None else static_roster(game)
    root = script.parse(str(game.file_dir(*path)))
    regiments: list[Regiment] = []
    for node in script.units_of(root):
        unit = script.unit_view(node)
        whoami = unit["set"].get("whoami")
        if whoami is None:
            continue
        row = roster.get(whoami)
        if row is None:
            continue
        fields = stat_fields(unit["stats"])[0]
        leader = unit.get("leader")
        leader_fields: StatFields = stat_fields(leader["stats"])[0] if leader is not None else {}
        regiments.append(Regiment(
            whoami=whoami, name=unit["name"], hired=bool(unit["set"].get("hired", 0)),
            models=_stat(fields, "s_size"), orgsize=_stat(fields, "s_orgsize"),
            points=_stat(fields, "s_pntval"), row=row,
            weapon_name=_stat(fields, "s_weponame"), armour=_stat(fields, "s_armr"),
            banner=unit.get("banner"),
            profile=tuple(_stat(fields, name) for name in _PROFILE_STATS),
            # s_Exp is a scalar `set:` field (FORMATS.md's unit block), not a `setstats:`
            # block entry, so it lives in unit["set"], not unit["stats"]; Army Records
            # displays it (§8, campaign.md §1).
            experience=unit["set"].get("s_Exp", 0),
            leader_name=leader["name"] if leader else None,
            leader_portrait=leader["portrait"] if leader else None,
            leader_profile=tuple(_stat(leader_fields, name) for name in _PROFILE_STATS),
            leader_armour=_stat(leader_fields, "s_armr"),
            leader_weapon=_stat(leader_fields, "s_weponame"),
            raw=node,
        ))
    return tuple(regiments)


def load_master(installation: Installation | str | PathLike[str],
                roster: Mapping[int, RosterRow] | None = None) -> tuple[Regiment, ...]:
    """The master roster of a fresh campaign (all regiments, ``PLAY.MRC``'s starting content)."""
    return load_company(installation, roster, MASTER_ROSTER)


def _unit_section(units: Sequence[script.Node], label: str) -> script.Node:
    """A [MERCARMY]/[UNITS] root wrapping ``units`` (raw addunit nodes); notes/campaign.md §4.4."""
    units_section: script.Node = {'kind': 'section', 'name': 'UNITS', 'line': 0, 'label': label,
                     'set': {'count': str(len(units))}, 'stats': {}, 'cmds': [], 'children': list(units)}
    return {'kind': 'section', 'name': 'MERCARMY', 'line': 0, 'label': None,
           'set': {}, 'stats': {}, 'cmds': [], 'children': [units_section]}


def _with_hired(node: script.Node, hired: bool) -> script.Node:
    """A shallow copy of ``node`` with its ``set:hired`` value replaced; never mutates ``node``."""
    copy = node.copy()
    copy['set'] = dict(node['set'])
    copy['set']['hired'] = '1' if hired else '0'
    return copy


def _with_models(node: script.Node, models: int) -> script.Node:
    """A copy of ``node`` whose ``s_size`` stat is ``models``; never mutates ``node``."""
    position = EXPECTED_STATS.index("s_size")
    index = {name.lower(): i for i, name in enumerate(EXPECTED_STATS)}
    copy = node.copy()
    copy["stats"] = {key: list(values) for key, values in node["stats"].items()}
    for key, values in copy["stats"].items():
        start = index.get(key.lower())
        if start is not None and start <= position < start + len(values):
            values[position - start] = models
    return copy


def with_hired(regiment: Regiment, hired: bool) -> Regiment:
    """The same regiment with its hired flag changed (the raw node included, so writes stay in step)."""
    raw = None if regiment.raw is None else _with_hired(regiment.raw, hired)
    return replace(regiment, hired=hired, raw=raw)


def with_models(regiment: Regiment, models: int) -> Regiment:
    """The same regiment with a new current model count (the raw node included)."""
    raw = None if regiment.raw is None else _with_models(regiment.raw, models)
    return replace(regiment, models=models, raw=raw)


def write_company(save_dir: str | PathLike[str], regiments: Iterable[Regiment], hired: Mapping[int, bool],
                  filename: str = "ARMY.MRC") -> None:
    """Write the company roster (notes/troop_selection.md §5.3 point 5: hired regiments only).

    ``save_dir`` is the engine's own save directory (never the original installation: this
    engine does not keep save-format or save-location compatibility with the original game,
    notes/glue_engine_integration.md GEI7e). ``hired`` is a ``{whoami: bool}`` mapping (the
    confirmed troop-selection state); regiments without a ``raw`` node (not loaded from a real
    .MRC, e.g. in tests) are skipped.
    """
    units = [_with_hired(regiment.raw, True) for regiment in regiments
             if regiment.raw is not None and hired.get(regiment.whoami, regiment.hired)]
    _write_units_file(save_dir, filename, units, "Mercenary Army")


def write_army(save_dir: str | PathLike[str], regiments: Iterable[Regiment], filename: str = "ARMY.MRC") -> None:
    """Write the whole company, unhired regiments included (they wait in the recruit book with ``hired=0``)."""
    units = [regiment.raw for regiment in regiments if regiment.raw is not None]
    _write_units_file(save_dir, filename, units, "Mercenary Army")


def write_march(save_dir: str | PathLike[str], ordered_whoami: Iterable[int], regiments: Iterable[Regiment],
                filename: str = "MARCH.MRC") -> None:
    """Write the marching order (notes/troop_selection.md §5.3 point 3), in list order."""
    by_whoami = {regiment.whoami: regiment for regiment in regiments}
    units: list[script.Node] = []
    for whoami in ordered_whoami:
        regiment = by_whoami.get(whoami)
        if regiment is not None and regiment.raw is not None:
            units.append(_with_hired(regiment.raw, True))
    _write_units_file(save_dir, filename, units, "Mercenary Army (Marching Orders)")


def _write_units_file(save_dir: str | PathLike[str], filename: str, units: Sequence[script.Node], label: str) -> None:
    target = Path(save_dir) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(script.write(_unit_section(units, label)))
