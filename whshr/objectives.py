"""In-battle mission objectives and the battle end (notes/battle_end_objectives.md).

Each mission letter is a record (flags, the `.BTS` numbers, a met flag and four result values) on an
**evaluation list**: Z first and always present, then the `.BTS` letters in file order (section 3.1). Every
record is initialised at battle load, the per-segment check runs on segment-boundary battle ticks before any
unit moves (section 3.2), and the final pass runs when the player leaves through the tent (section 3.3).
Meeting a battle-ending letter only **decides** the battle (section 6): nothing stops, and the battle ends when
the player presses the tent button.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .battle_events import BattleEvent
from .campaign_runtime import ObjectiveResult
from .rules import Side

if TYPE_CHECKING:
    from .engine import Battle, Regiment

# Flag meanings (game_rules.md "Missions and objectives"; battle_end_objectives.md section 5).
ENDS_BATTLE = 0x1
SEGMENT_CHECK = 0x2
NOT_LISTED = 0x4
FINAL_PASS = 0x8
AFTER_DECISION = 0x10
CUSTOM_LINE = 0x20

FLAGS: dict[str, int] = {
    "A": 0x03, "B": 0x28, "C": 0x28, "D": 0x08, "E": 0x08, "F": 0x07, "G": 0x08, "H": 0x07, "I": 0x0C,
    "J": 0x16, "K": 0x16, "L": 0x0C, "M": 0x0C, "N": 0x03, "O": 0x08, "P": 0x28, "Q": 0x08, "R": 0x0C,
    "S": 0x08, "T": 0x08, "U": 0x0E, "V": 0x0C, "W": 0x0C, "X": 0x16, "Y": 0x0C, "Z": 0x0F,
}

SEGMENT_TICKS = 19  # a segment boundary every 19 battle ticks; a turn is 10 segments (section 3.2)
TURN_SEGMENTS = 10
ITEM_SLOTS = 5
KEPT_FOR_RETURN = 0x1000  # the SetUnitFlags2 operand of the escape scripts (section 2)
PEASANT_RACE = 6
ROLLING_STOCK_CLASS = 7
COMMANDER_WHOAMI = 2
# The decision (section 6): battle message GMTXT 1005, speech from the HumBtl packet (5): 9 complete, 15 failed.
MISSION_COMPLETE_TEXT = 1005
OBJECTIVES_TEXT = 1004
CAPTION_BASE = 33000
HUMBTL_PACKET, HUM_COMPLETE, HUM_FAILED = 5, 9, 15
ZHUFBAR_PACKET = 11
ALL_UNITS_EVENT = 0x38
FOUND_ITEM_REACT, RETREAT_REACT = 16, 15
# Section 5.2 tree pieces for Q: the pine furniture types and their night and snow variants.
_PINES = ("Pine", "PineSml", "PineLrg", "TriPineSml", "TriPineMed", "TriPineLrg")
TREE_TYPES = frozenset(prefix + name for name in _PINES for prefix in ("", "Nite", "Snw"))
# Section 12.1: furniture types that become building pseudo-units (C counts those with models).
BUILDING_TYPES = frozenset((
    "Tudor2Stry", "Yelo2Stry", "StnYelo2Stry", "TudorChimney", "BalconyHouse", "WaterMill", "SmithyHut",
    "BrewerySmall", "Brck2Stry", "Crypt", "NiteCrypt", "WatchTower", "Farm", "WindMill", "Tavern", "StnFarmHouse",
    "AngRoofHouse", "BreweryMain", "WoodShack", "BlackWoodShack", "Barn1", "BreweryShed", "Well2", "HumanTent",
    "NiteHumanTent", "BlackOrcTent", "OrcBoyzTent", "B_OrcBoyzTent", "GrsOrcBoyzTent", "GrsBlackOrcTent", "Menhir",
    "SkavBase10FR", "SkavBase10FL", "SkavBase20FLR", "SkavBase20FaR", "SkavBase20x10", "SkavBase20FaL"))
# Section 12.2: K/X item number n (GMTXT 31000 + n); v4 is its index in the combined spell and item table.
ITEM_NUMBERS = (
    "ItemBannerOfArcaneWarding", "ItemBannerOfMight", "ItemDreadBanner", "ItemBannerOfWrath",
    "ItemBannerOfArcaneProtection", "ItemTalismanOfObsidian", "ItemShieldOfPtolos", "ItemPotionOfStrength",
    "ItemSwordOfHeroes", "ItemParryingBlade", "ItemSwordOfMight", "ItemDragonBlade", "ItemArmourOfMeteoricIron",
    "ItemArmourOfTheBeard", "ItemGrudgeBringer", "ItemRockSplitter", "ItemSwordOfElior")
ITEM_TABLE_BASE = 29  # spells and casting modes take entries 0-28
# Section 8: R's a selects the custom end-of-list line of B, C and P.
CUSTOM_LINES: dict[int, dict[str, int]] = {
    1: {"B": 33026, "C": 33030}, 2: {"B": 33026, "C": 33030}, 6: {"B": 33026, "C": 33030},
    3: {"B": 33027}, 4: {"B": 33028}, 5: {"B": 33029}, 7: {"C": 33031}, 8: {"P": 33032}, 9: {"P": 33033},
    10: {"B": 33034},
}


@dataclass
class Objective:
    """One letter's record: `values` are the `Result:` numbers v1..v4 (section 5)."""

    letter: str
    values: list[int]
    met: bool = False

    @property
    def flags(self) -> int:
        return FLAGS[self.letter]

    @property
    def a(self) -> int:
        return self.values[0]

    def result(self) -> ObjectiveResult:
        v1, v2, v3, v4 = self.values
        return self.met, (v1, v2, v3, v4)


def _number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass
class Objectives:
    """The evaluation list of one battle and its shared bookkeeping (sections 2 and 3)."""

    records: list[Objective]
    counted: set[str] = field(default_factory=set[str])  # the shared "counted" state (section 2)
    decided: str | None = None  # the letter that decided the battle
    tent: bool = False  # the tent button replaced the pause button (decision, or U's first warning)
    enemy_start: int = 0  # A's regiment count, also read by N (section 4.3)
    item_marks: dict[str, tuple[float, float]] = field(default_factory=dict[str, tuple[float, float]])
    finished: bool = False

    @classmethod
    def from_entries(cls, entries: Iterable[Sequence[Any]] | None) -> Objectives:
        """Z first, always, ignoring a `.BTS` Z line; then the other letters in file order (section 3.1)."""
        records = [Objective("Z", [0, 0, 0, 0])]
        seen = {"Z"}
        for entry in entries or ():
            if not entry:
                continue
            letter = str(entry[0]).upper()
            if letter in seen or letter not in FLAGS:
                continue
            seen.add(letter)
            records.append(Objective(letter, [_number(entry[1]) if len(entry) > 1 else 0,
                                              _number(entry[2]) if len(entry) > 2 else 0, 0, 0]))
        return cls(records)

    def get(self, letter: str) -> Objective | None:
        return next((record for record in self.records if record.letter == letter), None)

    def defined(self, letter: str) -> bool:
        return self.get(letter) is not None

    @property
    def siege(self) -> bool:
        return self.defined("G")

    @property
    def defeat(self) -> bool:
        """Whether the battle counts as lost: Z met in an ordinary battle, G met in a siege (debrief_evaluation.md §3)."""
        if self.siege:
            return self._met("G")
        return self._met("Z")

    def _met(self, letter: str) -> bool:
        record = self.get(letter)
        return record is not None and record.met

    def results(self) -> dict[str, ObjectiveResult]:
        """The `Result:` records in list order (section 3.3 step 3)."""
        return {record.letter: record.result() for record in self.records}

    # ------------------------------------------------------------------ load (mode 1)

    def load(self, battle: Battle) -> None:
        """Initialise every letter once, in list order, at battle load (section 3.1)."""
        for record in self.records:
            _LOAD.get(record.letter, _no_load)(self, battle, record)

    # ------------------------------------------------------------------ segment check (mode 2)

    def segment(self, battle: Battle) -> None:
        """The segment check (section 3.2): walk the list; the first battle-ending letter met decides."""
        for record in self.records:
            if record.met or not record.flags & SEGMENT_CHECK:
                continue
            if self.decided is not None and not record.flags & AFTER_DECISION:
                continue
            check = _SEGMENT.get(record.letter)
            if check is None or not check(self, battle, record):
                continue
            record.met = True
            if self.decided is None and record.flags & ENDS_BATTLE:
                self._decide(battle, record.letter)
                return

    def _decide(self, battle: Battle, letter: str) -> None:
        """Section 6: message, speech cue and the tent button; the battle keeps running."""
        self.decided = letter
        self.tent = True
        battle.events.append(BattleEvent(f"Objective {letter} decided the battle.", "objective_decided",
                                         letter=letter, defeat=self.defeat))
        self.announce(battle)

    def announce(self, battle: Battle, sink: list[BattleEvent] | None = None) -> None:
        """GMTXT 1005 and the complete/failed speech; in U battles only the failed speech (section 6 step 2)."""
        events = battle.events if sink is None else sink
        failed = self._met("Z") and not self.siege
        if not self.defined("U"):
            events.append(BattleEvent("Mission complete.", "message", text_id=MISSION_COMPLETE_TEXT))
        elif not self._met("Z"):
            return
        effect = HUM_FAILED if failed else HUM_COMPLETE
        events.append(BattleEvent(f"sound play {HUMBTL_PACKET}/{effect}", "sound", cue="play",
                                         packet=HUMBTL_PACKET, effect=effect, position=None))

    # ------------------------------------------------------------------ final pass (mode 3)

    def finish(self, battle: Battle) -> None:
        """The final pass when the player presses the tent (section 3.3 step 2)."""
        if self.finished:
            return
        self.finished = True
        for record in self.records:
            if record.met or not record.flags & FINAL_PASS:
                continue
            check = _FINAL.get(record.letter)
            if check is not None and check(self, battle, record):
                record.met = True

    # ------------------------------------------------------------------ book button (section 8)

    def book_text_ids(self) -> list[int]:
        """What the book prints: the objective list before the decision (and always in U battles), else 1005."""
        if self.decided is not None and not self.defined("U"):
            return [MISSION_COMPLETE_TEXT]
        r = self.get("R")
        custom = CUSTOM_LINES.get(r.a if r is not None else -1, {})
        lines = [OBJECTIVES_TEXT]
        for record in self.records:
            if record.flags & NOT_LISTED:
                continue
            if record.flags & CUSTOM_LINE:
                if record.letter in custom:
                    lines.append(custom[record.letter])
            else:
                lines.append(CAPTION_BASE + ord(record.letter) - ord("A"))
        return lines


# ---------------------------------------------------------------------- unit states (section 2)

def removed(regiment: Regiment) -> bool:
    return not regiment.active


def escaped_models(regiment: Regiment) -> int:
    """Models still alive when the regiment was removed; killed models are not escaped (section 2)."""
    return regiment.models if regiment.fled else 0


def cannot_rally(regiment: Regiment) -> bool:
    return "CantRally" in regiment.psychology or regiment.original_models - regiment.models >= 3 * regiment.models


def out_of_action(regiment: Regiment) -> bool:
    return regiment.active and regiment.routing and cannot_rally(regiment)


def kept_for_return(battle: Battle, regiment: Regiment) -> bool:
    state = battle.event_bus.unit_states.get(regiment.identifier)
    return state is not None and bool(state.unit_flags2 & KEPT_FOR_RETURN)


def in_node(battle: Battle, regiment: Regiment, index: int) -> bool:
    """The node circle test (section 4.3): front-rank point within the node radius, inclusive."""
    nodes = battle.script_nodes
    if not 0 <= index < len(nodes):
        return False
    node = nodes[index]
    return (regiment.x - node.x) ** 2 + (regiment.y - node.y) ** 2 <= node.radius ** 2


def building_count(battle: Battle) -> int:
    """Building pseudo-units with models (section 12.1). Nothing damages a building in this engine yet, so every
    building-type furniture piece keeps its models: C stays at 100%."""
    return sum(1 for name in battle.scenery_names if name in BUILDING_TYPES)


def standing_trees(battle: Battle) -> int:
    """Q's tree pieces (section 5). Nothing knocks a tree down in this engine (not traced in the original)."""
    return sum(1 for name in battle.scenery_names if name in TREE_TYPES)


def _side(battle: Battle, side: Side) -> list[Regiment]:
    return [regiment for regiment in battle.regiments.values() if regiment.side == side]


def _count_side(objectives: Objectives, regiments: Iterable[Regiment]) -> tuple[int, int]:
    """Count the in-battle regiments with models and mark them counted; returns (models, regiments)."""
    models = number = 0
    for regiment in regiments:
        if regiment.active and regiment.models > 0:
            objectives.counted.add(regiment.identifier)
            models += regiment.models
            number += 1
    return models, number


def _return_kept(battle: Battle) -> None:
    """D and L: every removed, kept-for-return, non-player regiment returns to the battle (section 5)."""
    for regiment in battle.regiments.values():
        if regiment.fled and regiment.side != Side.PLAYER and kept_for_return(battle, regiment):
            regiment.fled = False


def _percent(part: int, whole: int) -> int | None:
    return None if whole <= 0 else part * 100 // whole


# ---------------------------------------------------------------------- load handlers

def _no_load(objectives: Objectives, battle: Battle, record: Objective) -> None:
    return None


def _load_enemy(objectives: Objectives, battle: Battle, record: Objective) -> None:
    """A and F (section 4.1): v1 enemy models, v2 enemy regiments; they become counted."""
    record.values[0], record.values[1] = _count_side(objectives, _side(battle, Side.ENEMY))
    objectives.enemy_start = record.values[1]


def _load_n(objectives: Objectives, battle: Battle, record: Objective) -> None:
    """N keeps its node index in v1 and A's counts in A's record (section 4.3)."""
    _, objectives.enemy_start = _count_side(objectives, _side(battle, Side.ENEMY))


def _load_z(objectives: Objectives, battle: Battle, record: Objective) -> None:
    """Z (section 4.4): player regiments, plus allied ones in a siege battle."""
    regiments = _side(battle, Side.PLAYER)
    if objectives.siege:
        regiments += _side(battle, Side.NEUTRAL)
    record.values = [*_count_side(objectives, regiments), 0, 0]


def _load_b(objectives: Objectives, battle: Battle, record: Objective) -> None:
    peasants = [r for r in battle.regiments.values() if r.race == PEASANT_RACE]
    record.values[1] = _count_side(objectives, peasants)[0]


def _load_c(objectives: Objectives, battle: Battle, record: Objective) -> None:
    record.values[1] = building_count(battle)


def _wagons(battle: Battle) -> int:
    return sum(1 for r in _side(battle, Side.NEUTRAL)
               if r.active and r.models > 0 and r.unit_class == ROLLING_STOCK_CLASS)


def _load_d(objectives: Objectives, battle: Battle, record: Objective) -> None:
    record.values[1] = _wagons(battle)


def _load_e(objectives: Objectives, battle: Battle, record: Objective) -> None:
    """The `.BTS` b is not cleared: the enemy models are added to it (section 5, BF025)."""
    record.values[1] += _count_side(objectives, _side(battle, Side.ENEMY))[0]


def _load_k(objectives: Objectives, battle: Battle, record: Objective) -> None:
    """K/X (section 5.2): a known item gets its index and a marker at node a."""
    node, item = record.values[0], record.values[1]
    if 0 <= item < len(ITEM_NUMBERS) and 0 <= node < len(battle.script_nodes):
        record.values[3] = ITEM_TABLE_BASE + item
        objectives.item_marks[record.letter] = (battle.script_nodes[node].x, battle.script_nodes[node].y)


def _load_l(objectives: Objectives, battle: Battle, record: Objective) -> None:
    models, number = _count_side(objectives, _side(battle, Side.ENEMY))
    record.values[0], record.values[1] = models, number


def _find_whoami(battle: Battle, whoami: int) -> Regiment | None:
    return next((r for r in battle.regiments.values() if r.whoami == whoami & 0xFF), None)


def _load_q(objectives: Objectives, battle: Battle, record: Objective) -> None:
    record.values[1] = record.values[3] = standing_trees(battle)


def _load_v(objectives: Objectives, battle: Battle, record: Objective) -> None:
    race = [r for r in battle.regiments.values() if r.race == record.a]
    record.values[1] = _count_side(objectives, race)[0]


def _artillery(battle: Battle, code: int) -> int:
    return sum(1 for r in _side(battle, Side.ENEMY) if r.active and r.models > 0 and r.unit_class == code >> 3)


def _load_w(objectives: Objectives, battle: Battle, record: Objective) -> None:
    record.values[1] = _artillery(battle, record.a)


_LOAD: dict[str, Any] = {
    "A": _load_enemy, "F": _load_enemy, "N": _load_n, "Z": _load_z, "B": _load_b, "C": _load_c, "D": _load_d,
    "E": _load_e, "K": _load_k, "X": _load_k, "L": _load_l, "Q": _load_q, "V": _load_v, "W": _load_w,
}


# ---------------------------------------------------------------------- segment checks

def _enemy_remaining(objectives: Objectives, battle: Battle, start: int, adjust: bool) -> int:
    remaining = start
    for regiment in _side(battle, Side.ENEMY):
        if regiment.identifier not in objectives.counted:
            continue
        if removed(regiment) or (adjust and out_of_action(regiment)):
            remaining -= 1
    return remaining


def _check_a(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    return _enemy_remaining(objectives, battle, record.values[1], adjust=True) <= 0


def _check_f(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    return _enemy_remaining(objectives, battle, record.values[1], adjust=False) <= 0


def _check_n(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    if _enemy_remaining(objectives, battle, objectives.enemy_start, adjust=True) > 0:
        return False
    return any(r.active and in_node(battle, r, record.a) for r in _side(battle, Side.PLAYER))


def _check_z(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    """Section 4.4: out-of-action regiments first, then the removed ones (with the kept-for-return quirk)."""
    remaining = record.values[1]
    allied = objectives.siege
    for regiment in battle.regiments.values():
        if regiment.identifier in objectives.counted and out_of_action(regiment):
            if regiment.side == Side.PLAYER:
                remaining -= 1
            elif allied and regiment.side == Side.NEUTRAL:
                remaining += 1  # the siege rule adds out-of-action allies back
    if remaining <= 0:
        return _siege_z(battle) if allied else True
    for regiment in battle.regiments.values():
        if regiment.identifier not in objectives.counted or not removed(regiment):
            continue
        if (regiment.side == Side.PLAYER or (allied and regiment.side == Side.NEUTRAL)
                or kept_for_return(battle, regiment)):
            remaining -= 1
    if remaining > 0:
        return False
    if allied:
        return _siege_z(battle)
    record.values[2] = record.values[1]
    return True


def _siege_z(battle: Battle) -> bool:
    """Siege Z (section 4.4): nobody left outside moves the battle state; met only in states 1, 4 and 7."""
    if battle.mission_state in (1, 7):
        battle.mission_state = 7
        return True
    if battle.mission_state == 4:
        battle.mission_state = 5
        battle.events.append(BattleEvent(f"sound play {ZHUFBAR_PACKET}/0", "sound", cue="play",
                                         packet=ZHUFBAR_PACKET, effect=0, position=None))
        battle.broadcast_script_event(ALL_UNITS_EVENT)
        return True
    return False


def _check_h(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    return battle.mission_state == 7


def _check_j(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    """J (BF038): met once the battle is decided while the battle state is below 2."""
    if objectives.decided is None or battle.mission_state >= 2:
        return False
    battle.mission_state = 2
    battle.events.append(BattleEvent(f"sound play {ZHUFBAR_PACKET}/0", "sound", cue="play",
                                     packet=ZHUFBAR_PACKET, effect=0, position=None))
    return True


def _check_k(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    """Item pickup (section 5.2): the first player regiment in node a with a free slot takes the item."""
    if record.letter not in objectives.item_marks:
        return False
    for regiment in _side(battle, Side.PLAYER):
        if regiment.active and in_node(battle, regiment, record.a) and len(regiment.items) < ITEM_SLOTS:
            regiment.items = (*regiment.items, ITEM_NUMBERS[record.values[3] - ITEM_TABLE_BASE])
            del objectives.item_marks[record.letter]
            record.values[2] = regiment.whoami
            battle.react(regiment.identifier, FOUND_ITEM_REACT)
            return True
    return False


def _u_eligible(regiment: Regiment) -> bool:
    charging = regiment.attack_target is not None and not regiment.in_melee
    return (regiment.active and "CantBreak" not in regiment.psychology and not charging and not regiment.routing
            and not regiment.pursuing and regiment.whoami != COMMANDER_WHOAMI)


def _check_u(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    """U (section 5.3): from the first boundary of turn a, one more retreat warning per turn; never met."""
    boundary = battle.tick_count // SEGMENT_TICKS
    if boundary != TURN_SEGMENTS * (record.values[0] - 1) + 1:
        return False
    record.values[0] += 1
    record.values[2] += 1
    eligible = [r for r in _side(battle, Side.PLAYER) if _u_eligible(r)]
    if len(eligible) >= record.values[2]:
        battle.react(eligible[record.values[2] - 1].identifier, RETREAT_REACT)
    objectives.tent = True
    return False


_SEGMENT: dict[str, Any] = {
    "A": _check_a, "F": _check_f, "N": _check_n, "Z": _check_z, "H": _check_h, "J": _check_j,
    "K": _check_k, "X": _check_k, "U": _check_u,
}


# ---------------------------------------------------------------------- final pass

def _final_z(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    """Z's own final pass is never met; it records the regiments lost (section 4.4)."""
    _, now = _count_side(objectives, _side(battle, Side.PLAYER))
    record.values[2] = record.values[1] - now
    return False


def _final_b(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    peasants = [r for r in battle.regiments.values() if r.race == PEASANT_RACE]
    record.values[3] = sum(r.models if r.active else escaped_models(r) for r in peasants)
    return _threshold(record)


def _threshold(record: Objective) -> bool:
    percent = _percent(record.values[3], record.values[1])
    if percent is None:
        return False  # no population at load: undefined in the original, read as not met
    record.values[2] = percent
    return percent >= record.a


def _final_c(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    record.values[3] = building_count(battle)
    return _threshold(record)


def _final_d(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    _return_kept(battle)
    record.values[3] = _wagons(battle)
    record.values[2] = record.values[1] - record.values[3]
    return record.values[2] <= record.a


def _final_e(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    record.values[3] = sum(r.original_models - r.models for r in _side(battle, Side.ENEMY)
                           if r.identifier in objectives.counted and removed(r))
    percent = _percent(record.values[3], record.values[1])
    if percent is None:
        return False
    record.values[2] = percent
    return percent >= record.a


def _final_g(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    """G (debrief_evaluation.md §3.3): met unless the gate (whoami 100) is gone and whoami 2 and 29 remain;
    when met it also sets Z met. PROVISIONAL: "handled by the cleanup pass" is read as removed."""
    gate, commander, other = (_find_whoami(battle, w) for w in (100, COMMANDER_WHOAMI, 29))
    breached = (gate is not None and removed(gate) and commander is not None and commander.active
                and other is not None and other.active)
    if breached:
        return False
    _set_z(objectives)
    return True


def _set_z(objectives: Objectives) -> None:
    z = objectives.get("Z")
    if z is not None:
        z.met = True


def _final_l(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    _return_kept(battle)
    enemies = [r for r in _side(battle, Side.ENEMY) if r.active]
    record.values[2], record.values[3] = sum(r.models for r in enemies), len(enemies)
    return False


def _final_o(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    """O: the leader of the whoami-a regiment was killed. PROVISIONAL: the engine has no separate leader model,
    so the leader counts as killed when the regiment was wiped out (not when it fled off alive)."""
    target = _find_whoami(battle, record.a)
    return target is not None and target.has_leader and target.destroyed


def _final_p(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    target = _find_whoami(battle, record.a)
    return target is not None and target.active


def _final_q(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    record.values[3] = standing_trees(battle)
    return _threshold(record)


def _final_v(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    race = [r for r in battle.regiments.values() if r.race == record.a]
    alive = sum(r.models for r in race if r.active)
    escaped = sum(escaped_models(r) for r in race if r.identifier in objectives.counted and removed(r))
    record.values[3] = record.values[1] - alive - escaped
    return True


def _final_w(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    record.values[3] = record.values[1] - _artillery(battle, record.a)
    return True


def _final_u(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    _set_z(objectives)
    return False


def _final_y(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    return objectives._met("G") if objectives.siege else objectives._met("Z")  # pyright: ignore[reportPrivateUsage]


def _always(objectives: Objectives, battle: Battle, record: Objective) -> bool:
    return True


_FINAL: dict[str, Any] = {
    "Z": _final_z, "B": _final_b, "C": _final_c, "D": _final_d, "E": _final_e, "G": _final_g, "L": _final_l,
    "O": _final_o, "P": _final_p, "Q": _final_q, "S": _always, "T": _always, "U": _final_u, "V": _final_v,
    "W": _final_w, "Y": _final_y,
}
