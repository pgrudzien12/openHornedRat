"""Game rules data from GAMEF.DLL: unit stat layout, combat tables and their checks.

Derived from static analysis of GAMEF.DLL (full report: notes/game_rules.md). The tables are read
from the local installation at run time; no game data is stored in this module.
"""

import re
import struct
from collections.abc import Iterator, Mapping, Sequence
from enum import Enum
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from . import script
from .paths import Installation

if TYPE_CHECKING:
    from .engine import Regiment

StrPath = str | PathLike[str]


class Side(str, Enum):
    """A regiment's side (notes/neutral_units.md): the original's `s_side[0]` byte packs a 2-bit side
    code into bits 7,6 -- 00 player, 01 neutral/NPC, 10 enemy, 11 unused -- plus a unit type code in
    bits 0-5 (`script.side_info`). Subclasses `str` so it serialises as a plain string in battle logs
    and dict keys (`whshr.battle_log`) without extra handling.
    """
    PLAYER = "player"
    NEUTRAL = "neutral"
    ENEMY = "enemy"
    # Engine-internal *camp*, never decoded from data: the attacker of a scripted same-side engagement
    # (notes/game_rules.md, "Engagement is refused ... same side and the target is not the current
    # opponent") fights on a camp of its own for the length of that fight, so tallies and break tests
    # can tell the two same-side regiments apart. Not a side: `hostile_sides` gives it no opponents.
    DUEL = "duel"


_SIDE_BITS = {0: Side.PLAYER, 1: Side.NEUTRAL, 2: Side.ENEMY}
# Default hostility, absent an explicit script order (notes/neutral_units.md, "Implementation
# Requirements": behaviour is script-driven, not flag-driven). Player and enemy are each other's
# default opponents; neutral has none -- "no offensive orders unless provoked".
_HOSTILE: dict[Side, frozenset[Side]] = {Side.PLAYER: frozenset({Side.ENEMY}), Side.ENEMY: frozenset({Side.PLAYER}),
            Side.NEUTRAL: frozenset(), Side.DUEL: frozenset()}


def side_of_code(code: int | None) -> Side:
    """The `Side` of a raw `s_side[0]` byte, or `Side.ENEMY` if `code` is `None` or the bit pattern
    11 (notes/neutral_units.md: unused, no units found with it in the 54-battle survey) -- matching
    this engine's previous default for any `.BTS` army unit with no better information."""
    if code is None:
        return Side.ENEMY
    return _SIDE_BITS.get((code >> 6) & 0x3, Side.ENEMY)


def hostile_sides(side: Side) -> frozenset[Side]:
    """The sides `side` is hostile to by default (see `Side`'s docstring): used by generic,
    script-independent targeting (`whshr.combat`'s shooting target search) so a neutral
    regiment is never auto-targeted or auto-targeting. A script that explicitly names a target
    (e.g. the `AttackNearestFlag40Unit` opcode) is not limited by this."""
    return _HOSTILE[side]


_NEVER_FIGHT = frozenset({frozenset({Side.PLAYER, Side.NEUTRAL})})


def can_fight(side_a: Side, side_b: Side) -> bool:
    """Whether two regiments of different sides may engage in close combat *on physical contact*
    (`whshr.combat.resolve_contacts`) or must instead push apart like same-side regiments do
    (`whshr.engine.Battle._resolve_collisions`).

    Player and Neutral never fight each other, even just from bumping into one another: user-
    corrected from a real playthrough where NPC peasant regiments ended up in melee with the
    player's own infantry purely from footprint contact. In this game NPCs are either genuinely
    neutral or effectively on the player's side -- never hostile to the player -- so Enemy and
    Neutral can still fight (that is how a mission's own scripted threat against neutrals, e.g.
    `AttackNearestFlag40Unit`, actually plays out physically), but Player and Neutral cannot.
    """
    return side_a != side_b and frozenset({side_a, side_b}) not in _NEVER_FIGHT


def is_scripted_opponent(first: "Regiment", second: "Regiment") -> bool:
    """Two regiments of the *same* side where one has the other as its explicit attack target.

    The original refuses same-side engagement "when the target is not the current opponent"
    (notes/game_rules.md, engagement rules), so a script's own target (e.g. `AttackTagged`) may be a
    friend. The player's own orders never name a same-side target (`Battle.order_attack`)."""
    return (first.side == second.side
            and (first.attack_target == second.identifier or second.attack_target == first.identifier))


def may_engage(first: "Regiment", second: "Regiment") -> bool:
    """Whether two regiments fight on physical contact: different camps (`can_fight`), or a scripted
    same-side opponent pair (`is_scripted_opponent`). Takes regiments, not sides, for that reason."""
    return can_fight(first.camp, second.camp) or is_scripted_opponent(first, second)


# Virtual addresses in GAMEF.DLL (image base 0x10000000, linker timestamp 1995-12-11).
VA_STAT_TOKENS = 0x100E97C8   # {char *name; int token} pairs: psy_status=10, ..., s_side=13 ... s_Exp=43
VA_PSY_TOKENS = 0x100E9AA8    # CantBreak=19 ... CantDie=32; psy_status bit = token - 19
VA_RACE_NAMES = 0x100E9B20    # 8 name pointers indexed by s_race & 7
VA_CLASS_NAMES = 0x100E9B40   # 10 name pointers indexed by s_race >> 3
VA_TO_HIT = 0x100E8C28        # 11 x 11 bytes: [attacker WS][defender WS] -> lowest D6 that hits
VA_WEAPON_STRENGTH = 0x100E8CA8  # 16 bytes indexed by s_weap: strength bonus (bit 7: fixed value)
VA_TO_WOUND = 0x100E8CB8      # 11 x 11 bytes: [S][T] -> lowest D6 that wounds (7 = impossible)
VA_SAVE_MODIFIER = 0x100E8D38  # 16 bytes indexed by S, added to the armour save value
VA_ARMOUR_SAVE = 0x100E8D48   # 16 bytes indexed by s_armr: a D6 below this value fails the save
VA_MOUNTS = 0x100E8D58        # 32-byte records indexed by s_mount: name, charge S, M WS BS S T W I A Ld

STAT_BASE = 0x7A              # unit record offset of the byte written by token 13 (s_side)
FIRST_STAT_TOKEN, LAST_BLOCK_TOKEN = 13, 39   # s_side .. s_banner: one byte each
PROFILE = script.PROFILE
PSY_FIRST_TOKEN = 19

# Field order of the stat block as stored in the token table; checked against the binary.
EXPECTED_STATS = (
    's_side', 's_orgsize', 's_size', 's_rnks', 's_wdth', 's_rkmd', 's_spar', 's_rlmv',
    's_move', 's_wepn', 's_bals', 's_strn', 's_tuff', 's_wnds', 's_init', 's_atks', 's_lead',
    's_mount', 's_armr', 's_weap', 's_race', 's_pntval', 'S_BalWeap', 's_cmdr', 's_armname',
    's_weponame', 's_banner',
)
EXPECTED_PSY = (
    'CantBreak', 'Frenzy', 'CauseFear', 'CauseTerror', 'FearToGobs', 'HateDwarfs', 'HateGreens',
    'HateSkaven', 'PsyImmune', 'MagicResistent', 'CantRally', 'AlwaysPursue', 'CantMelee', 'CantDie',
)
# Readable names of the profile bytes (the token names are abbreviations of these).
FIELD_ALIASES = dict(zip(('s_move', 's_wepn', 's_bals', 's_strn', 's_tuff', 's_wnds', 's_init',
                          's_atks', 's_lead'), PROFILE))

# S_BalWeap codes, named after the units that carry them in the campaign scripts.
MISSILE_WEAPONS = {
    0: None, 1: 'bow (Orc Arrer Boyz)', 2: 'crossbow', 5: 'great cannon', 6: 'mortar',
    7: 'Hellblaster volley gun', 8: 'rock lobber', 9: 'Wood Elf bow', 11: 'cannon',
    12: 'doom diver catapult', 13: 'warp lightning (Doomwheel)', 14: 'breath (Dragon)',
    15: 'warpfire thrower', 16: 'spellcaster marker (Wyvern shaman)', 17: 'Gyrocopter bomb (Archers class) / steam gun',
    18: 'short bow (Goblin Archers)', 19: 'longbow (Keeler\'s Longbows)',
}
# Maximum ranges hard-coded in GAMEF.DLL (game_rules.md, section 8), in BTS world units (24 units = 1 tabletop inch).
MISSILE_RANGES = {1: 576, 2: 720, 5: 1440, 6: 768, 7: 576, 8: 1440, 9: 576, 11: 1152, 12: 1440,
                  14: 576, 15: 576, 17: 384, 18: 384, 19: 720}


class PeImage:
    """Minimal PE32 reader: maps virtual addresses of initialised sections to file bytes."""

    def __init__(self, path: StrPath) -> None:
        self.path = Path(path)
        self.data = self.path.read_bytes()
        pe = struct.unpack_from('<I', self.data, 0x3C)[0]
        if self.data[pe:pe + 4] != b'PE\0\0':
            raise ValueError(f'{self.path}: not a PE image')
        _, count, self.timestamp, _, _, optional_size, _ = struct.unpack_from('<HHIIIHH', self.data, pe + 4)
        self.image_base = struct.unpack_from('<I', self.data, pe + 24 + 28)[0]
        table = pe + 24 + optional_size
        self.sections: list[tuple[int, int, int, int]] = []
        for i in range(count):
            vsize, vaddr, raw_size, raw_ptr = struct.unpack_from('<8xIIII', self.data, table + 40 * i)
            self.sections.append((vsize, vaddr, raw_size, raw_ptr))

    def read(self, va: int, size: int) -> bytes:
        rva = va - self.image_base
        for vsize, vaddr, raw_size, raw_ptr in self.sections:
            if vaddr <= rva < vaddr + max(vsize, raw_size):
                offset = rva - vaddr
                if offset + size > raw_size:
                    raise ValueError(f'{va:#x}+{size} is outside initialised data')
                return self.data[raw_ptr + offset:raw_ptr + offset + size]
        raise ValueError(f'{va:#x} is not mapped')

    def u32(self, va: int, count: int = 1) -> tuple[int, ...]:
        return struct.unpack(f'<{count}I', self.read(va, 4 * count))

    def cstring(self, va: int, limit: int = 64) -> str:
        return self.read(va, limit).split(b'\0', 1)[0].decode('latin-1')

    def maps(self, va: int) -> bool:
        try:
            self.read(va, 1)
            return True
        except ValueError:
            return False


def _token_table(image: PeImage, va: int, limit: int = 128) -> dict[int, str]:
    """Reads {name, token} pairs up to the entry with an empty name that ends each keyword table."""
    tokens: dict[int, str] = {}
    for i in range(limit):
        pointer, token = image.u32(va + 8 * i, 2)
        if not image.maps(pointer) or not image.cstring(pointer):
            break
        tokens.setdefault(token, image.cstring(pointer))
    return tokens


class Mount(TypedDict):
    name: str
    flag: int
    charge_strength: int
    profile: dict[str, int]


class Tables(TypedDict):
    """The rule tables read from GAMEF.DLL by load_tables()."""
    image: PeImage
    stats: list[str | None]
    psy: list[str | None]
    races: list[str]
    classes: list[str]
    to_hit: list[list[int]]
    to_wound: list[list[int]]
    weapon_strength: list[int]
    save_modifier: list[int]
    armour_save: list[int]
    mounts: list[Mount]


def load_tables(installation: StrPath) -> Tables:
    """Reads the rule tables from GAMEF.DLL of an installation."""
    game = Installation(installation)
    image = PeImage(game.require('GAMEF.DLL'))

    def grid(va: int) -> list[list[int]]:
        return [list(image.read(va + 11 * row, 11)) for row in range(11)]

    tokens = _token_table(image, VA_STAT_TOKENS)
    psy = _token_table(image, VA_PSY_TOKENS, 16)
    mounts: list[Mount] = []
    for index in range(5):
        record = image.read(VA_MOUNTS + 32 * index, 32)
        mounts.append({'name': image.cstring(struct.unpack_from('<I', record)[0]), 'flag': record[4],
                       'charge_strength': record[5], 'profile': dict(zip(PROFILE, record[12:21]))})
    return {
        'image': image,
        'stats': [tokens.get(token) for token in range(FIRST_STAT_TOKEN, LAST_BLOCK_TOKEN + 1)],
        'psy': [psy.get(token) for token in range(PSY_FIRST_TOKEN, PSY_FIRST_TOKEN + 14)],
        'races': [image.cstring(p) for p in image.u32(VA_RACE_NAMES, 8)],
        'classes': [image.cstring(p) for p in image.u32(VA_CLASS_NAMES, 10)],
        'to_hit': grid(VA_TO_HIT), 'to_wound': grid(VA_TO_WOUND),
        'weapon_strength': list(image.read(VA_WEAPON_STRENGTH, 16)),
        'save_modifier': list(image.read(VA_SAVE_MODIFIER, 11)),
        'armour_save': list(image.read(VA_ARMOUR_SAVE, 14)),
        'mounts': mounts,
    }


# ---------------------------------------------------------------- unit decoding

StatFields = dict[str, script.Scalar]
Conflict = tuple[str, str, script.Scalar, script.Scalar]


def stat_int(fields: Mapping[str, script.Scalar], name: str) -> int | None:
    """One stat field as an int, or None when it is absent or not an integer in the script."""
    value = fields.get(name)
    return value if isinstance(value, int) else None


def stat_fields(stats: Mapping[str, Sequence[script.Scalar]],
                order: Sequence[str] = EXPECTED_STATS) -> tuple[StatFields, list[Conflict]]:
    """Applies setstats lines to the stat block: each line fills consecutive fields from its key.

    Returns (fields, conflicts); a conflict is a later line overwriting a field with another value.
    Keys outside the byte block (s_calualties ...) are ignored.
    """
    index = {name.lower(): i for i, name in enumerate(order)}
    fields: StatFields = {}
    conflicts: list[Conflict] = []
    for key, values in stats.items():
        start = index.get(key.lower())
        if start is None:
            continue
        if start + len(values) > len(order):
            raise ValueError(f'setstats:{key} with {len(values)} values overflows the stat block')
        for offset, value in enumerate(values):
            name = order[start + offset]
            if name in fields and fields[name] != value:
                conflicts.append((key, name, fields[name], value))
            fields[name] = value
    return fields, conflicts


def armour_description(code: int, tables: Tables | None = None) -> str:
    if code == 6:
        text = 'regenerates'
    elif code == 7:
        text = 'void'
    elif code >= 8:
        text = f'mounted, rating {code - 7}'
    else:
        text = f'rating {code}'
    if tables and code < len(tables['armour_save']):
        need = tables['armour_save'][code]
        text += ', no save' if need >= 7 else f', save {need}+'
    return text


def decode_unit(node: script.Node, tables: Tables) -> dict[str, Any]:
    """Named view of one addunit/addleader node from whshr.script.parse()."""
    fields, conflicts = stat_fields(node['stats'])
    race = stat_int(fields, 's_race')
    mount = stat_int(fields, 's_mount')
    armour = stat_int(fields, 's_armr')
    weapon = stat_int(fields, 's_weap')
    weapon_name = stat_int(fields, 's_weponame')
    missile = stat_int(fields, 'S_BalWeap')
    view: dict[str, Any] = {
        'name': script.display_name(node['name']),
        'profile': {FIELD_ALIASES[k]: fields[k] for k in FIELD_ALIASES if k in fields},
        'side': fields.get('s_side'), 'size': fields.get('s_size'), 'orgsize': fields.get('s_orgsize'),
        'ranks': fields.get('s_rnks'),
        'race': None if race is None else f"{tables['races'][race & 7]} {tables['classes'][race >> 3]}",
        'mount': None if mount is None else tables['mounts'][mount]['name'],
        'armour': None if armour is None else armour_description(armour, tables),
        'weapon_class': weapon,
        'strength_bonus': None if weapon is None else tables['weapon_strength'][weapon],
        'missile': MISSILE_WEAPONS.get(missile, missile) if missile is not None else None,
        'weapon_name_id': None if weapon_name is None else 200 + weapon_name,
        'points': fields.get('s_pntval'),
        'psychology': script.flag_names(node['set'].get('psy_status')),
        'conflicts': conflicts,
    }
    return view


def _units(node: script.Node) -> Iterator[script.Node]:
    for child in node['children']:
        if child['kind'] in ('addunit', 'addleader'):
            yield child
        yield from _units(child)


def script_files(installation: StrPath) -> list[Path]:
    game = Installation(installation)
    save = game.find('SAVE')
    dirs = [game.file_dir('SCRIPT')] + ([save] if save else [])
    return sorted(p for d in dirs for p in d.iterdir() if p.suffix.upper() in ('.BTS', '.MRC'))


# ---------------------------------------------------------------- checks

def wfb_to_hit(attacker: int, defender: int) -> int:
    """Warhammer Fantasy Battle 4th edition close combat chart (WS 1-10)."""
    if attacker > defender:
        return 3
    if defender > 2 * attacker:
        return 5
    return 4


def wfb_to_wound(strength: int, toughness: int) -> int:
    """Warhammer Fantasy Battle 4th edition wound chart (S, T 1-10); 7 = cannot wound."""
    difference = strength - toughness
    if difference >= 2:
        return 2
    return {1: 3, 0: 4, -1: 5, -2: 6, -3: 6}.get(difference, 7)


EXPECTED_ARMOUR_SAVE = [7, 6, 5, 4, 3, 7, 4, 7, 6, 5, 4, 3, 2, 2]   # code 5 gives no save (see notes)
EXPECTED_WEAPON_BONUS = {0: 0, 3: 0, 4: 2, 10: 1}                    # the classes used by the scripts
EXPECTED_MOUNTS = ['None', 'Warhorse', 'War Boar', 'Giant Wolf', 'Cave Squig']
# Public mount profiles from game_rules.md, "Mounts". Movement uses M; the other combat values
# are kept here for the mount's own attack resolution.
MOUNT_PROFILES = {
    1: {"M": 7, "WS": 3, "BS": 0, "S": 3, "T": 3, "W": 1, "I": 3, "A": 1, "Ld": 5,
        "charge_strength": 5},
    2: {"M": 6, "WS": 4, "BS": 0, "S": 3, "T": 4, "W": 1, "I": 3, "A": 1, "Ld": 3,
        "charge_strength": 6},
    3: {"M": 8, "WS": 4, "BS": 0, "S": 3, "T": 3, "W": 1, "I": 3, "A": 1, "Ld": 3,
        "charge_strength": 3},
    4: {"M": 5, "WS": 4, "BS": 0, "S": 5, "T": 3, "W": 1, "I": 5, "A": 2, "Ld": 2,
        "charge_strength": 0},
}


def check_tables(tables: Tables) -> list[str]:
    failures: list[str] = []
    if tables['stats'] != list(EXPECTED_STATS):
        failures.append(f"stat token order {tables['stats']}")
    if tables['psy'] != list(EXPECTED_PSY):
        failures.append(f"psychology token order {tables['psy']}")
    for a in range(1, 11):
        for d in range(1, 11):
            if tables['to_hit'][a][d] != wfb_to_hit(a, d):
                failures.append(f"to-hit WS{a} vs WS{d}: {tables['to_hit'][a][d]} != {wfb_to_hit(a, d)}")
            if tables['to_wound'][a][d] != wfb_to_wound(a, d):
                failures.append(f"to-wound S{a} vs T{d}: {tables['to_wound'][a][d]} != {wfb_to_wound(a, d)}")
    if tables['save_modifier'] != [max(0, s - 3) for s in range(11)]:
        failures.append(f"save modifiers {tables['save_modifier']}")
    if tables['armour_save'] != EXPECTED_ARMOUR_SAVE:
        failures.append(f"armour saves {tables['armour_save']}")
    for code, bonus in EXPECTED_WEAPON_BONUS.items():
        if tables['weapon_strength'][code] != bonus:
            failures.append(f"weapon class {code}: bonus {tables['weapon_strength'][code]} != {bonus}")
    if [m['name'] for m in tables['mounts']] != EXPECTED_MOUNTS:
        failures.append(f"mount names {[m['name'] for m in tables['mounts']]}")
    return failures


S_RACE_COMMENT = re.compile(r';S_RACE is (.*?)\.\.\.')


def check_scripts(installation: StrPath, tables: Tables) -> tuple[list[str], dict[str, Any]]:
    """Decodes every unit and leader; returns (failures, statistics)."""
    failures: list[str] = []
    units = fields_checked = race_pairs = race_matches = 0
    for path in script_files(installation):
        for node in _units(script.parse(str(path))):
            units += 1
            try:
                fields, conflicts = stat_fields(node['stats'])
            except ValueError as error:
                failures.append(f'{path.name} {node["name"]}: {error}')
                continue
            fields_checked += sum(len(v) for k, v in node['stats'].items() if k.lower() in
                                  {n.lower() for n in EXPECTED_STATS})
            failures += [f'{path.name} {node["name"]}: {c}' for c in conflicts]
            if (stat_int(fields, 's_armr') or 0) > 13 or (stat_int(fields, 's_mount') or 0) >= len(EXPECTED_MOUNTS):
                failures.append(f'{path.name} {node["name"]}: armour/mount code out of range {fields}')
        # the editor's ';S_RACE is <race> <class>' comment, computed from s_race when the file was saved
        race: int | None = None
        for line in path.read_bytes().decode('latin-1').splitlines():
            line = line.strip()
            if line.lower().startswith('addunit:'):
                race = None
            elif line.startswith('setstats:s_mount=') and race is None:
                values = [int(v) for v in line.split('=', 1)[1].split(',')]
                race = values[3] if len(values) == 6 else None
            elif race is not None and (comment := S_RACE_COMMENT.match(line)):
                race_pairs += 1
                label = comment.group(1).strip()
                race_matches += label == f"{tables['races'][race & 7]} {tables['classes'][race >> 3]}"
    if race_pairs == 0 or race_matches < 0.98 * race_pairs:
        failures.append(f'S_RACE comments agree with s_race in only {race_matches}/{race_pairs} units')
    return failures, {'units': units, 'values': fields_checked, 'race_comments': (race_matches, race_pairs)}


def check(installation: StrPath) -> bool:
    tables = load_tables(installation)
    failures = check_tables(tables)
    script_failures, stats = check_scripts(installation, tables)
    failures += script_failures
    for failure in failures[:20]:
        print(f'  {failure}')
    print(f"  rules: WFB 4th ed charts match; {stats['units']} units/leaders, {stats['values']} stat values "
          f"without conflicts; S_RACE comments {stats['race_comments'][0]}/{stats['race_comments'][1]}"
          if not failures else f'  rules: {len(failures)} failures')
    return not failures


# ---------------------------------------------------------------- command line

def _grid(title: str, rows: Sequence[Sequence[int]], row_label: str, column_label: str) -> str:
    lines = [title, f"{row_label}\\{column_label} " + ' '.join(f'{c:2d}' for c in range(11))]
    lines += [f'{r:>{len(row_label) + len(column_label) + 1}d} ' + ' '.join(f'{v:2d}' for v in row)
              for r, row in enumerate(rows)]
    return '\n'.join(lines)


def main(installation: StrPath, battle: str | None = None) -> int:
    tables = load_tables(installation)
    if battle is None:
        print(_grid('To hit (lowest D6)', tables['to_hit'], 'WS', 'WS'))
        print(_grid('To wound (lowest D6, 7 = impossible)', tables['to_wound'], 'S', 'T'))
        print('Save modifier by S:', tables['save_modifier'])
        for code in range(len(tables['armour_save'])):
            print(f'  s_armr {code:2d}: {armour_description(code, tables)}')
        print('Strength bonus by s_weap:', tables['weapon_strength'])
        for index, mount in enumerate(tables['mounts']):
            print(f"  s_mount {index}: {mount['name']}, charge S {mount['charge_strength']}, {mount['profile']}")
        return 0
    path: Path | None = Path(battle)
    if not path.exists():
        path = next((p for p in script_files(installation) if p.name.casefold() == battle.casefold()), None)
        if path is None:
            raise FileNotFoundError(battle)
    for node in _units(script.parse(str(path))):
        view = decode_unit(node, tables)
        prefix = '    leader ' if node['kind'] == 'addleader' else '  '
        print(f"{prefix}{view['name']}: {view['profile']} size {view['size']}/{view['orgsize']} "
              f"ranks {view['ranks']}; {view['race']}; mount {view['mount']}; armour {view['armour']}; "
              f"weapon class {view['weapon_class']} (+{view['strength_bonus']} S), name id {view['weapon_name_id']}; "
              f"missile {view['missile']}; psychology {view['psychology']}")
    return 0
