"""Deterministic battle-state primitives shared by prototype frontends."""

from dataclasses import dataclass, field
import math
import random

from . import battle_grid, behaviour, combat, formation, interpreter
from .battle_events import BattleEvent
from .rules import EXPECTED_WEAPON_BONUS, MISSILE_RANGES, MOUNT_PROFILES, Side, can_fight, side_of_code, stat_fields
from .script import load_battle, resource_name

TICK_SECONDS = 0.1  # the battle clock ticks every 100 ms (game_rules.md, "Battle clock")

# k factors from game_rules.md, "Real time and movement": s_rlmv * k / 16 world units per tick.
MOVING_FREELY_K = 1.8
CLOSING_K = 1.0     # unused directly (player/AI attack orders go straight to charging speed here,
                     # a documented simplification: the original distinguishes closing from charging
                     # by the charge counter, which this engine does not model)
CHARGING_K = 2.5
FLEEING_K = 1.5

DEFAULT_SEED = 1995  # arbitrary but fixed: battles are deterministic unless a caller picks a seed

# Placeholder s_rlmv for a regiment whose script has no decoded M/I profile (game_rules.md leaves
# `set:map`, `whoami` and part of `setstats` open, but every BF001 combat unit does carry `s_move`):
# trunc(4.8 x 4 + 3) / 2, the M4 I3 infantry example from game_rules.md.
DEFAULT_S_RLMV = 11.0
# game_rules.md, "Models chase the unit": a model rests within three world units of its slot.
MODEL_ARRIVAL_DISTANCE = 3.0
MODEL_STEP_SCALE = 2.4 / 256
# Basic bow-type missile codes this engine models as shooters (game_rules.md 8.1/8.3): artillery and
# special weapons (cannons, mortars, breath weapons, ...) are not modelled in this simplified engine.
ARCHER_MISSILE_CODES = {1, 2, 9, 18, 19}
# Default combat profile for a regiment without a decoded profile (WS/BS/S/T/W/I/A/Ld); an ordinary
# human infantryman, matching DEFAULT_S_RLMV's M4 I3 example.
DEFAULT_PROFILE = {"WS": 3, "BS": 3, "S": 3, "T": 3, "W": 1, "I": 3, "A": 1, "Ld": 7}

# The battle HUD's command panel picks a button layout by one of five unit classes (Inf, Arch,
# Art, Wiz, Mon; notes/game_rules.md "Battle HUD layout"). The note names the classes but does not
# give their numeric encoding ("classes 0 and 7-9 have no buttons" does not obviously match this
# byte, since 0 here is Monster, which the HUD's own table gives buttons to) - PROVISIONAL: derived
# from the s_side race/type byte (script.RACE_TYPES) as the best available signal, not confirmed
# against the panel's own class numbering.
HUD_CLASS_BY_RACE_TYPE = {
    0: "mon", 1: "inf", 2: "inf", 3: "arch", 4: "inf", 5: "arch", 6: "inf", 7: "inf", 8: "inf",
    9: "inf", 10: "arch", 11: "inf", 12: "inf", 13: "arch", 14: "inf",
    15: "art", 16: "art", 17: "art", 18: "art", 19: "wiz",
}


def speed_per_tick(move_stat, initiative_stat, k=MOVING_FREELY_K):
    """World units a regiment covers in one 100 ms tick (game_rules.md, "Real time and movement"):
    ``s_rlmv = trunc(4.8 * M + I) / 2``, then ``s_rlmv * k / 16`` units per tick. ``k`` selects the
    movement mode: 1.8 moving freely, 1.0 closing, 2.5 charging or in melee, 1.5 fleeing.
    """
    if move_stat is None or initiative_stat is None:
        s_rlmv = DEFAULT_S_RLMV
    else:
        s_rlmv = math.trunc(4.8 * move_stat + initiative_stat) / 2
    return s_rlmv * k / 16


DEFAULT_SPEED_PER_TICK = speed_per_tick(None, None)


@dataclass
class ModelState:
    """One model's close-combat state on its fight's battle grid (game_rules.md 5.7, whshr.battle_grid).

    Kept index-parallel with `Regiment.positions`, which stays the authoritative per-model position
    for movement and rendering.
    """

    uid: int = 0  # identity within its regiment, stable across casualties (never an index)
    cell: tuple | None = None  # (row, col) this model holds on the grid, or None when not placed
    opponent: tuple | None = None  # (regiment identifier, model uid) this model is paired with
    arrived: bool = False  # has walked into its cell, so it may strike (model flag 0x10000)
    reserve: bool = False  # found no free cell this tick and waits for one (model flag 0x8000)
    stagger: int = 0  # fixed 0-7 value for this model's rank-dependent pace and later charge delay
    current_speed: float = 0.0  # speed counter, converted to world units by the rank step factor
    distance_budget: float = 0.0  # travel remaining before recomputing the slot heading
    heading_x: float = 0.0
    heading_y: float = 0.0
    at_rest: bool = True
    freeze_ticks: int = 0  # charge-start pause, (stagger & 7) + 1 ticks
    rout_pause_ticks: int = 0  # break-and-turn pause, (stagger & 7) * 3 + 6 ticks


@dataclass
class Regiment:
    """A regiment anchor in BTS coordinates; its models walk to formation slots around that anchor."""

    identifier: str
    name: str
    x: float
    y: float
    direction: int
    side: Side  # notes/neutral_units.md: player, neutral/NPC, or enemy
    target_x: float | None = None
    target_y: float | None = None
    models: int = 1
    ranks: int = 1
    sprite: str | None = None  # script troop sprite resource, e.g. "ClanRats"
    banner: str | None = None  # script banner resource
    portrait: str | None = None  # leader portrait resource
    speed_per_tick: float = DEFAULT_SPEED_PER_TICK  # BTS world units per 100 ms tick, moving freely
    positions: list = field(default_factory=list)  # current per-model (x, y); lazily seeded in formation
    melee_models: list = field(default_factory=list)  # ModelState, index-parallel with `positions`
    _next_uid: int = 0  # next free model identity (see ModelState.uid)
    walking: bool = False  # true while the anchor or any model is still travelling
    animation_seconds: float = 0.0  # elapsed time while walking, for the frontend's frame-rate placeholder

    # Combat profile (game_rules.md section 3, section 5-8), decoded from the script's setstats lines.
    ws: int = DEFAULT_PROFILE["WS"]
    bs: int = DEFAULT_PROFILE["BS"]
    strength: int = DEFAULT_PROFILE["S"]
    toughness: int = DEFAULT_PROFILE["T"]
    wounds: int = DEFAULT_PROFILE["W"]
    initiative: int = DEFAULT_PROFILE["I"]
    attacks: int = DEFAULT_PROFILE["A"]
    leadership: int = DEFAULT_PROFILE["Ld"]
    armour: int = 0  # s_armr code, indexes rules.EXPECTED_ARMOUR_SAVE
    mount: int | None = None  # s_mount profile, active only for mounted armour codes 8-13
    strength_bonus: int = 0  # weapon class bonus, rules.EXPECTED_WEAPON_BONUS[s_weap]
    missile_code: int | None = None  # S_BalWeap, only ARCHER_MISSILE_CODES are modelled as shooters
    missile_range: float | None = None  # world units, from rules.MISSILE_RANGES
    psychology: frozenset = frozenset()  # psy_status flag names, e.g. {"CantBreak", "CantRally"}
    hud_class: str | None = None  # "inf"/"arch"/"art"/"wiz"/"mon"; see HUD_CLASS_BY_RACE_TYPE
    unit_class: int | None = None  # s_race class; wagons use a four-deep movement layout
    points: int = 0  # s_pntval: experience gained by the killer, and the AI's per-model worth unit
    # (game_rules.md: unit worth = size x s_pntval x 12 artillery / 8 wizard / 4 monster / 1)

    # Combat/order state (whshr.combat).
    attack_target: str | None = None  # identifier of an enemy regiment this regiment is charging
    charge_started_target: str | None = None  # target whose current charge already froze its models
    turn_order_key: tuple | None = None
    turn_goal: float | None = None
    turn_remaining: float = 0.0
    turn_sign: int = 0
    turn_shift: int = 0
    turn_mode: str | None = None  # "halted", "wheel", or "charge_reaim"
    # game_rules.md "Braced" (flag 0x100000): set when this regiment passes its fear/terror test on
    # being charged (interpreter.op_FearWhenCharged, event 0x07). While set, move/attack/turn/rank/
    # charge/fire orders are ignored -- for the player exactly like for a script -- until the charger
    # named by `braced_target` is gone (combat.refresh_braced_state) or it enters melee.
    braced: bool = False
    braced_target: str | None = None  # identifier of the regiment this one is braced against
    in_melee: bool = False
    melee_group: str | None = None  # id of the shared multi-regiment fight (Battle.fights), if any
    melee_touching: frozenset = field(default_factory=frozenset)  # enemy ids this footprint touches now
    routing: bool = False  # fleeing the field; ignores orders, moves away from the nearest enemy
    # game_rules.md "Flight and catching fleeing units": the flight bearing is fixed once, "directly
    # away from its opponent", when the rout starts (combat._start_rout) - not re-aimed every tick
    # at whichever enemy happens to be nearest at that instant. A far point along that bearing
    # (Battle._flee_point's own convention); None only before the first rout tick sets it.
    flee_x: float | None = None
    flee_y: float | None = None
    fled: bool = False  # a routing regiment that has left the battlefield (removed from play)
    reload_ticks: float = 0.0  # ticks remaining before a missile regiment may shoot again
    corpses: list = field(default_factory=list)  # (x, y, direction) of models that have died, for the view

    # Traced close-combat/rally timing (game_rules.md 5.5, 6.1-6.2, 7.4), see whshr.combat.
    # The fight's own-side tally, breakdown and next break-test turn (6.1-6.2) live on
    # `Battle.fights[regiment.melee_group]`, shared by every regiment in that fight.
    original_models: int | None = None  # starting model count, for rally's casualties modifier
    # game_rules.md 6.1: the formed frontage, which casualties never reduce (only a re-form would).
    # The rank bonus divides the live model count by this, so it decays as the unit is worn down.
    frontage: int | None = None
    # game_rules.md 5.5: floor(1.5 x frontage), set when the regiment charges into a fight and spent
    # one attacking model at a time, so only the first models to strike get the +1 S.
    charge_counter: int = 0
    rally_next_segment: int | None = None  # absolute segment index of the next scheduled rally attempt (7.4)

    def __post_init__(self):
        if self.original_models is None:
            self.original_models = self.models
        if self.frontage is None:
            sizes = formation.rank_sizes(self.models, self.ranks)
            self.frontage = sizes[0] if sizes else 0

    @property
    def moving(self):
        return self.target_x is not None

    @property
    def mount_profile(self):
        return MOUNT_PROFILES.get(self.mount) if 8 <= self.armour <= 13 else None

    @property
    def destroyed(self):
        return self.models <= 0

    @property
    def active(self):
        """False once a regiment is out of the fight (all models dead, or routed off the field)."""
        return not self.destroyed and not self.fled

    def speed_for_mode(self, k):
        """Per-tick speed at movement factor ``k`` (game_rules.md k factors), scaled from the regiment's
        own free-movement speed rather than carrying a second raw ``s_rlmv`` field."""
        return self.speed_per_tick * k / MOVING_FREELY_K

    @property
    def charge_reach(self):
        """game_rules.md "Charge": a real charge reaches at most ``12 * (s_rlmv + 1)`` world units
        (about 6" for infantry, 9.5" for cavalry) -- a short final rush, not the whole approach.
        Recovers ``s_rlmv`` from the stored free-movement `speed_per_tick` (``s_rlmv * 1.8 / 16``)
        rather than carrying a second raw field, same approach as `speed_for_mode`."""
        s_rlmv = self.speed_per_tick * 16 / MOVING_FREELY_K
        return 12 * (s_rlmv + 1)

    def model_positions(self, spacing=formation.MODEL_SPACING):
        """Current per-model positions (BTS world units): seeded in formation, then advanced by `Battle.tick`."""
        if len(self.positions) != self.models:
            self.positions = formation.place(self.x, self.y, self.direction,
                                              formation.block_slots(self.models, self.ranks, spacing))
        if len(self.melee_models) != len(self.positions):
            # Reseeding the formation renews every model's identity. Identities are drawn from a
            # counter that never restarts, so a pairing left over from before the reseed can never be
            # mistaken for one of the new models: it simply refers to a model that no longer exists.
            self.melee_models = [ModelState(uid=self._next_uid + offset,
                                            stagger=(self._next_uid + offset) & 7)
                                 for offset in range(len(self.positions))]
            self._next_uid += len(self.positions)
        return self.positions

    def index_of(self, uid):
        """Position of the model with this identity, or None once it has been killed."""
        for index, model in enumerate(self.melee_models):
            if model.uid == uid:
                return index
        return None

    def front_rank_models(self):
        """Model count of the front rank, the attackers/shooters counted in a combat or volley round."""
        sizes = formation.rank_sizes(self.models, self.ranks)
        return sizes[0] if sizes else 0

    def _footprint(self):
        return formation.footprint_frame(self.x, self.y, self.direction, self.models, self.ranks)

    def contains(self, x, y):
        """True when a ground point lies inside the regiment's oriented block footprint."""
        cx, cy, half_side, half_forward, cos, sin = self._footprint()
        dx, dy = x - cx, y - cy
        local_side = dx * cos - dy * sin
        local_forward = dx * sin + dy * cos
        return abs(local_side) <= half_side and abs(local_forward) <= half_forward

    def bounding_radius(self):
        return formation.bounding_radius(self.models, self.ranks)

    def block(self):
        """`(x, y, direction, models, ranks)`, the block description `whshr.formation` works from."""
        return (self.x, self.y, self.direction, self.models, self.ranks)

    def footprint_corners(self):
        """The four world-space corners of this regiment's oriented block footprint, for
        `formation.footprint_gap` (close-combat contact, `whshr.combat.resolve_contacts`)."""
        return formation.footprint_corners(self.x, self.y, self.direction, self.models, self.ranks)


def _decode_combat_profile(unit):
    """Decode a regiment's speed, WS/BS/S/T/W/I/A/Ld, armour, weapon and missile stats from its raw script
    setstats lines (game_rules.md section 3), stdlib-only (no GAMEF.DLL access needed at battle time:
    the tables it would supply are already verified constants in whshr.rules)."""
    fields, _conflicts = stat_fields(unit.get("stats") or {})
    profile = unit.get("profile") or {}
    armour = fields.get("s_armr") or 0
    mount = MOUNT_PROFILES.get(fields.get("s_mount")) if 8 <= armour <= 13 else None
    move_stat = mount["M"] if mount is not None else profile.get("M")
    weapon_class = fields.get("s_weap")
    missile_code = fields.get("S_BalWeap")
    missile_range = MISSILE_RANGES.get(missile_code) if missile_code in ARCHER_MISSILE_CODES else None
    psy_status = unit.get("set", {}).get("psy_status")
    psychology = frozenset(f for f in str(psy_status or "").split("|") if f)
    side = fields.get("s_side")
    hud_class = HUD_CLASS_BY_RACE_TYPE.get(side & 0x3F) if side is not None else None
    return {
        "speed_per_tick": speed_per_tick(move_stat, profile.get("I", DEFAULT_PROFILE["I"])),
        "ws": int(profile.get("WS", DEFAULT_PROFILE["WS"])),
        "bs": int(profile.get("BS", DEFAULT_PROFILE["BS"])),
        "strength": int(profile.get("S", DEFAULT_PROFILE["S"])),
        "toughness": int(profile.get("T", DEFAULT_PROFILE["T"])),
        "wounds": int(profile.get("W", DEFAULT_PROFILE["W"])),
        "initiative": int(profile.get("I", DEFAULT_PROFILE["I"])),
        "attacks": int(profile.get("A", DEFAULT_PROFILE["A"])),
        "leadership": int(profile.get("Ld", DEFAULT_PROFILE["Ld"])),
        "armour": armour,
        "mount": fields.get("s_mount"),
        "strength_bonus": EXPECTED_WEAPON_BONUS.get(weapon_class, 0),
        "missile_code": missile_code if missile_range else None,
        "missile_range": missile_range,
        "psychology": psychology,
        "hud_class": hud_class,
        "unit_class": fields["s_race"] >> 3 if "s_race" in fields else None,
        "points": int(fields.get("s_pntval") or 0),
    }


class Battle:
    """Authoritative fixed-tick state: movement, and (whshr.combat) close combat, shooting, morale."""

    def __init__(self, width, height, regiments, seed=DEFAULT_SEED, script_dll=None, script_ids=None,
                 script_logger=None, nodes=None):
        if width <= 0 or height <= 0:
            raise ValueError("battle dimensions must be positive")
        self.width = width
        self.height = height
        self.regiments = {regiment.identifier: regiment for regiment in regiments}
        if len(self.regiments) != len(regiments):
            raise ValueError("regiment identifiers must be unique")
        self.tick_count = 0
        self.rng = random.Random(seed)
        self.events = []  # battle events emitted by the most recent tick (plain strings)
        # {node id: (x, y)} from the battle's own [NODES] section (whshr.script.load_battle),
        # BTS world coordinates; read by the interpreter's MoveToNode/FaceNode/TeleportToNode/
        # PlaceAtNode opcodes (issue #3/#46). Empty for a synthetic/nodeless battle.
        self.nodes = nodes or {}
        self.fights = {}  # group id -> {"next_test_turn", "tally": {True/False}, "breakdown": {...}}
        self._fight_seq = 0  # counter for fresh whshr.combat fight group ids
        self.result = None  # None while the battle is ongoing, else "victory" or "defeat"
        # A battle only has a win/lose condition once it actually has both sides (movement-only tests
        # and synthetic battles commonly field only one side, which must never auto-resolve). Neutral
        # regiments never decide it either way (notes/neutral_units.md: their combat-credit rules are
        # still an open research question, so this engine simply excludes them from victory/defeat).
        self._has_enemy = any(regiment.side == Side.ENEMY for regiment in regiments)
        self._has_player = any(regiment.side == Side.PLAYER for regiment in regiments)

        # Bytecode interpreter for mission scripts (issue #3/#46): `script_dll` is the mission's
        # loaded SCRIPT/BFxxx.DLL (whshr.behaviour.ScriptDll), or None for a mission-less/synthetic
        # battle, in which case no script-driven regiment gets automatic orders (Battle.tick) --
        # only explicit Battle.order_* calls move it.
        # `script_ids` is {regiment identifier: initial script id}, from each unit's own
        # set:script= value; a regiment absent from it starts on the shared library script
        # (behaviour.PLAYER_SCRIPT), matching the original's own default for units with no explicit
        # set:script= line.
        self.script_dll = script_dll
        self.event_bus = interpreter.EventBus(self)
        script_ids = script_ids or {}
        for regiment_id in self.regiments:
            initial_script = script_ids.get(regiment_id, behaviour.PLAYER_SCRIPT)
            self.event_bus.unit_states[regiment_id] = interpreter.UnitScriptState(script_id=initial_script)
        # `script_logger` (whshr.battle_log.BattleLogger) optionally records every dispatched opcode
        # when its own trace_scripts flag is on -- see ScriptInterpreter.run/write_opcode.
        self.interpreter = (interpreter.ScriptInterpreter(self, self.event_bus, script_dll, logger=script_logger)
                             if script_dll else None)

    @classmethod
    def from_battle_file(cls, path, seed=DEFAULT_SEED, script_dll=None, script_logger=None):
        return cls.from_script(load_battle(path), seed=seed, script_dll=script_dll, script_logger=script_logger)

    @classmethod
    def from_script(cls, source, seed=DEFAULT_SEED, script_dll=None, script_logger=None):
        """Build the battle from a loaded BTS/MRC script; repeated unit ids get ``#2``, ``#3``... suffixes.

        ``script_dll``, when given, is threaded through to `Battle.__init__` (issue #3/#46) so its
        interpreter drives every regiment; without it, no regiment gets automatic orders. Each unit's own
        ``set:script=`` value (a number, or the literal ``PLAYER_SCRIPT``) becomes that regiment's
        initial script id, matching the original's `set:script=PLAYER_SCRIPT` convention
        (`whshr.behaviour.PLAYER_SCRIPT` = library script 100). The script's own ``[NODES]`` table
        (already parsed by `whshr.script.load_battle`, just not previously read here) becomes
        `Battle.nodes`, so movement opcodes (MoveToNode and friends) can resolve a node id to a
        real world coordinate instead of only recording the id.
        """
        field_data = source["field"]
        nodes = {node["id"]: (float(node["x"]), float(node["y"]))
                 for node in source.get("nodes") or ()
                 if node.get("id") is not None and node.get("x") is not None and node.get("y") is not None}
        regiments, script_ids, used = [], {}, set()
        # `source["armies"]` are the .BTS file's own [UNITS] sections (both the "Enemy Army" and "NPC
        # units" ones, notes/neutral_units.md section 2): each unit's own s_side byte says whether it
        # is enemy or neutral. `source["merc"]` is the player's own roster from the loaded .MRC, always
        # Side.PLAYER regardless of any s_side value it happens to carry.
        armies = [(army, None) for army in source["armies"]]
        armies.extend((army, Side.PLAYER) for army in (source["merc"] or {}).get("armies", []))
        for army, forced_side in armies:
            for unit in army["units"]:
                position = unit["set"]
                if "x" not in position or "y" not in position:
                    continue
                identifier, suffix = unit["id"], 2
                while identifier in used:
                    identifier, suffix = f"{unit['id']}#{suffix}", suffix + 1
                used.add(identifier)
                models, ranks = formation.unit_size(unit)
                if forced_side is not None:
                    side = forced_side
                else:
                    fields, _conflicts = stat_fields(unit.get("stats") or {})
                    side = side_of_code(fields.get("s_side"))
                regiments.append(Regiment(
                    identifier, unit["name"], float(position["x"]), float(position["y"]),
                    int(position.get("dir") or 0) % 512, side, models=models, ranks=ranks,
                    sprite=resource_name(unit.get("sprites")),
                    banner=resource_name(unit.get("banner")),
                    portrait=resource_name((unit.get("leader") or {}).get("portrait")),
                    **_decode_combat_profile(unit),
                ))
                script_value = position.get("script")
                if isinstance(script_value, str) and script_value.upper() == "PLAYER_SCRIPT":
                    script_ids[identifier] = behaviour.PLAYER_SCRIPT
                elif isinstance(script_value, (int, float)):
                    script_ids[identifier] = int(script_value)
        return cls(field_data["width"], field_data["height"], regiments, seed=seed,
                   script_dll=script_dll, script_ids=script_ids, script_logger=script_logger, nodes=nodes)

    def order_move(self, identifier, x, y):
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if regiment.braced:
            raise ValueError(f"{identifier} is braced against a charge and cannot be ordered")
        if not 0 <= x <= self.width or not 0 <= y <= self.height:
            raise ValueError("destination is outside the battlefield")
        regiment.attack_target = None
        regiment.charge_started_target = None
        regiment.turn_order_key = None
        regiment.target_x, regiment.target_y = float(x), float(y)

    def order_attack(self, identifier, target_id):
        """Order a player regiment to charge a non-player regiment into contact (game_rules.md,
        "Charge"): the target may be an enemy or a neutral regiment (notes/neutral_units.md documents
        neutral units as ordinary battle units, not automatically off-limits to a deliberate order)."""
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if regiment.braced:
            raise ValueError(f"{identifier} is braced against a charge and cannot be ordered")
        target = self.regiments.get(target_id)
        if target is None or target.side == Side.PLAYER:
            raise ValueError("attack target must not be a player regiment")
        if not target.active:
            raise ValueError(f"{target_id} is no longer on the field")
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = target_id
        regiment.turn_order_key = None

    def order_halt(self, identifier):
        """Cancel the selected regiment's current movement or charge order in place."""
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if regiment.in_melee:
            raise ValueError(f"{identifier} is in melee and cannot be ordered")
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = None
        regiment.charge_started_target = None
        regiment.turn_order_key = None
        # game_rules.md "Braced": Halt is the one order still accepted while braced, and clears it.
        regiment.braced = False
        regiment.braced_target = None

    def snapshot(self):
        """Per-regiment state for `whshr.battle_log` (a segment snapshot or the final battle state):
        position, facing, models, corpse count, and every order/engagement flag needed to trace a
        regiment's behaviour without re-deriving it from the tick-by-tick event log."""
        return {
            identifier: {
                "x": regiment.x, "y": regiment.y, "direction": regiment.direction,
                "models": regiment.models, "corpses": len(regiment.corpses),
                "walking": regiment.walking, "routing": regiment.routing, "fled": regiment.fled,
                "in_melee": regiment.in_melee, "melee_group": regiment.melee_group,
                "melee_touching": sorted(regiment.melee_touching),
                "attack_target": regiment.attack_target, "reload_ticks": regiment.reload_ticks,
                "braced": regiment.braced, "braced_target": regiment.braced_target,
                # Battle-grid occupancy (game_rules.md 5.7): how many models hold a cell, how many
                # have walked into it and are paired, and how many are waiting for a cell to free up.
                "placed": sum(1 for m in regiment.melee_models if m.cell is not None),
                "fighting": len(battle_grid.fighting_models(self, regiment)),
                "reserves": sum(1 for m in regiment.melee_models if m.reserve),
                "charge_counter": regiment.charge_counter,
            }
            for identifier, regiment in self.regiments.items()
        }

    def regiment_at(self, x, y, player_only=True):
        """Identifier of the regiment whose footprint contains (x, y), or None; the closest one if several."""
        best_id, best_distance = None, None
        for regiment in self.regiments.values():
            if not regiment.active:
                continue
            if player_only and regiment.side != Side.PLAYER:
                continue
            if not regiment.contains(x, y):
                continue
            distance = math.hypot(x - regiment.x, y - regiment.y)
            if best_distance is None or distance < best_distance:
                best_id, best_distance = regiment.identifier, distance
        return best_id

    def tick(self, seconds=TICK_SECONDS):
        if seconds <= 0:
            raise ValueError("tick duration must be positive")
        self.events = []
        if self.result is not None:
            self.tick_count += 1
            return
        scale = seconds / TICK_SECONDS
        # Run behaviour scripts via the bytecode interpreter (issue #3); a mission-less/synthetic
        # battle has no interpreter and so no automatic orders (only explicit Battle.order_* calls).
        if self.interpreter:
            for unit_id, state in self.event_bus.unit_states.items():
                self.interpreter.run(unit_id, state, self.tick_count, self.rng)
            self.interpreter.raise_charge_events()
        combat.refresh_melee_state(self)
        self._advance_regiments(scale, seconds)
        self._resolve_collisions()
        combat.resolve_contacts(self)
        combat.refresh_braced_state(self)
        if self.tick_count % combat.SEGMENT_TICKS == 0:
            combat.resolve_melee(self)
            combat.resolve_contact_attacks(self)  # game_rules.md 7.7, once per segment
            combat.resolve_rally(self)
        combat.resolve_shooting(self)
        self._update_result()
        self.tick_count += 1

    def _advance_regiments(self, scale, seconds):
        for regiment in self.regiments.values():
            if not regiment.active:
                regiment.walking = False
                regiment.animation_seconds = 0.0
                continue
            regiment.model_positions()  # seed positions at the current anchor/facing before it moves
            if regiment.attack_target is None:
                regiment.charge_started_target = None
            moved = False
            if regiment.in_melee:
                regiment.turn_order_key = regiment.turn_mode = None
                pass  # frozen in place while fighting; the view shows the attack animation instead
            elif regiment.routing:
                if regiment.flee_x is None:  # self-heal: should only happen for pre-existing state
                    regiment.flee_x, regiment.flee_y = self._flee_point(regiment)
                moved = self._advance_toward(regiment, (regiment.flee_x, regiment.flee_y),
                                             regiment.speed_for_mode(FLEEING_K) * scale, arrive=False,
                                             order_key=("flee",), scale=scale)
                if not (0 <= regiment.x <= self.width and 0 <= regiment.y <= self.height):
                    regiment.fled = True
                    self.events.append(BattleEvent(
                        f"{regiment.name} routs off the battlefield.", "fled",
                        regiment=regiment.identifier, x=regiment.x, y=regiment.y,
                        width=self.width, height=self.height))
            elif regiment.attack_target:
                target = self.regiments.get(regiment.attack_target)
                if target is None or not target.active:
                    regiment.attack_target = None
                    regiment.charge_started_target = None
                else:
                    if (regiment.charge_started_target != target.identifier
                            and math.hypot(target.x - regiment.x, target.y - regiment.y)
                            <= regiment.charge_reach):
                        for model in regiment.melee_models:
                            model.freeze_ticks = (model.stagger & 7) + 1
                            model.current_speed = 0.0
                        regiment.charge_started_target = target.identifier
                    moved = self._advance_toward(regiment, (target.x, target.y),
                                                 regiment.speed_for_mode(CHARGING_K) * scale, arrive=False,
                                                 order_key=("charge", target.identifier), scale=scale)
            elif regiment.moving:
                moved = self._advance_toward(regiment, (regiment.target_x, regiment.target_y),
                                             regiment.speed_per_tick * scale, arrive=True,
                                             order_key=("move", regiment.target_x, regiment.target_y), scale=scale)
            else:
                regiment.turn_order_key = regiment.turn_mode = None
            if regiment.attack_target is None and not regiment.in_melee:
                for model in regiment.melee_models:
                    model.freeze_ticks = 0
            models_catching_up = self._advance_models(regiment, scale)
            regiment.walking = moved or models_catching_up
            regiment.animation_seconds = regiment.animation_seconds + seconds if regiment.walking else 0.0

    @staticmethod
    def _turn_to(regiment, direction):
        """Change a regiment's facing, moving its anchor so the turn pivots about the block centre.

        game_rules.md, "A turn always moves the unit position to keep the pivot still": the original
        displaces the unit position on every in-place turn so that the block centre -- which is what
        the collision footprint is built around -- does not move. Turning the anchor in place instead
        swings the footprint away and can break a contact that should have held.
        """
        if direction == regiment.direction:
            return
        shift_x, shift_y = formation.turn_pivot_shift(
            regiment.direction, direction, regiment.models, regiment.ranks)
        regiment.direction = direction
        regiment.x += shift_x
        regiment.y += shift_y

    @staticmethod
    def _turn_delta(direction, goal):
        """Signed shortest turn in 1/512-turn units."""
        return (goal - direction + 256) % 512 - 256

    @staticmethod
    def _snap_order_turn(regiment, goal):
        """Apply the one-time 90/180-degree snap on a new movement order."""
        delta = Battle._turn_delta(regiment.direction, goal)
        magnitude = abs(delta)
        snap = 256 if magnitude > 192 else 128 if magnitude >= 97 else 0
        if not snap:
            return
        old_direction = regiment.direction
        old_ranks = regiment.ranks
        new_direction = (old_direction + math.copysign(snap, delta)) % 512
        if snap == 128:
            regiment.ranks, regiment.frontage = regiment.frontage, old_ranks
        old_offset = (old_ranks - 1) * formation.MODEL_SPACING / 2
        new_offset = (regiment.ranks - 1) * formation.MODEL_SPACING / 2
        old_angle = old_direction * math.tau / 512
        new_angle = new_direction * math.tau / 512
        regiment.x += new_offset * math.sin(new_angle) - old_offset * math.sin(old_angle)
        regiment.y += new_offset * math.cos(new_angle) - old_offset * math.cos(old_angle)
        regiment.direction = new_direction

    @staticmethod
    def _plan_turn(regiment, goal, charge=False):
        """Choose the gradual turn mode once from the angle still owed."""
        delta = Battle._turn_delta(regiment.direction, goal)
        magnitude = abs(delta)
        regiment.turn_goal = goal
        regiment.turn_remaining = magnitude
        regiment.turn_sign = 1 if delta > 0 else -1
        if magnitude <= 10 or (charge and magnitude <= 32):
            regiment.turn_mode = None
            if magnitude <= 10:
                regiment.direction = goal
            return
        if charge:
            regiment.turn_mode, regiment.turn_shift = "charge_reaim", 9
        elif magnitude > 64:
            regiment.turn_mode, regiment.turn_shift = "halted", 8
        else:
            regiment.turn_mode, regiment.turn_shift = "wheel", 7

    @staticmethod
    def _step_turn(regiment, scale):
        """Advance one active gradual turn, shifting the anchor around the inner corner."""
        if regiment.turn_mode is None:
            return None
        frontage = regiment.frontage
        ranks = max(1, min(regiment.models, regiment.ranks))
        size = frontage + ranks - min(frontage, ranks) / 2
        s_rlmv = regiment.speed_per_tick * 16 / MOVING_FREELY_K
        step = max(0.0, s_rlmv * (144 - size * size) / (2 ** (16 - regiment.turn_shift))) * scale
        if step <= 0:
            return regiment.turn_mode
        old_direction = regiment.direction
        amount = min(step, regiment.turn_remaining)
        new_direction = (old_direction + regiment.turn_sign * amount) % 512
        shift_x, shift_y = formation.turn_corner_shift(old_direction, new_direction,
                                                       frontage, regiment.turn_sign)
        regiment.x += shift_x
        regiment.y += shift_y
        regiment.direction = new_direction
        regiment.turn_remaining -= amount
        mode = regiment.turn_mode
        if regiment.turn_remaining <= 10:
            regiment.turn_mode = None
        return mode

    def _advance_toward(self, regiment, target, step, arrive, order_key, scale):
        """Turn toward a target over time, then advance along the current facing.

        With `arrive=True` (an ordinary move order) reaching the target clears it, matching the
        original "moving freely" order completion. With `arrive=False` (a charge chase or a rout) the
        regiment keeps closing on a moving point every tick and never "arrives" on its own; contact
        detection (`combat.resolve_contacts`) or leaving the field ends the movement instead.
        """
        dx, dy = target[0] - regiment.x, target[1] - regiment.y
        distance = math.hypot(dx, dy)
        if distance < 1e-9:
            if arrive:
                regiment.target_x = regiment.target_y = None
            return False
        goal = round(math.atan2(dx, dy) * 512 / math.tau) % 512
        new_order = order_key != regiment.turn_order_key
        if new_order:
            regiment.turn_order_key = order_key
            if order_key[0] in ("move", "charge"):
                self._snap_order_turn(regiment, goal)
            self._plan_turn(regiment, goal, charge=order_key[0] == "charge")
        elif order_key[0] == "charge" and self.tick_count % combat.SEGMENT_TICKS == 0:
            self._plan_turn(regiment, goal, charge=True)
        elif regiment.turn_mode is None and order_key[0] != "charge":
            self._plan_turn(regiment, goal, charge=order_key[0] == "charge")
        mode = self._step_turn(regiment, scale)
        if mode == "wheel":
            step /= 2
        elif mode is not None:
            step = 0
        if step <= 0:
            return mode is not None
        if arrive and distance <= step and abs(self._turn_delta(regiment.direction, goal)) <= 10:
            regiment.x, regiment.y = target
            regiment.target_x = regiment.target_y = None
            return False
        angle = regiment.direction * math.tau / formation.FULL_TURN
        regiment.x += math.sin(angle) * min(step, distance)
        regiment.y += math.cos(angle) * min(step, distance)
        return True

    def _nearest_enemy(self, regiment):
        """The nearest active regiment of a *different* side, whatever it is (used for a rout's flee
        bearing and rally's "enemy nearby" check): the opponent to flee from is whoever `regiment` is
        actually engaged with, not restricted to `rules.hostile_sides`' default hostility, which only
        gates unprompted/autonomous targeting (`whshr.combat._shooting_target`)."""
        enemies = [r for r in self.regiments.values() if r.side != regiment.side and r.active]
        if not enemies:
            return None
        return min(enemies, key=lambda e: math.hypot(e.x - regiment.x, e.y - regiment.y))

    def _flee_point(self, regiment):
        """A point far away on the bearing directly away from the nearest enemy (game_rules.md, "Flight":
        "starts the flight directly away from its opponent"), or along the current facing if none remain."""
        enemy = self._nearest_enemy(regiment)
        if enemy is not None:
            dx, dy = regiment.x - enemy.x, regiment.y - enemy.y
            distance = math.hypot(dx, dy)
            if distance > 1e-6:
                return regiment.x + dx / distance * 1e4, regiment.y + dy / distance * 1e4
        angle = regiment.direction * math.tau / formation.FULL_TURN
        return regiment.x + math.sin(angle) * 1e4, regiment.y + math.cos(angle) * 1e4

    def _advance_models(self, regiment, scale):
        """Walk each model toward its target with its own ramping, rank-dependent pace.

        The target is normally the model's formation slot, but a model that holds a cell on a battle
        grid walks to that cell instead and is marked `arrived` once it is within
        `battle_grid.ARRIVAL_DISTANCE` of it (game_rules.md 5.8 step 6): only then may it strike.
        """
        targets = formation.place(regiment.x, regiment.y, regiment.direction,
                                  formation.block_slots(regiment.models, regiment.ranks))
        rank_sizes = formation.rank_sizes(regiment.models, regiment.ranks)
        rank_indices = [rank for rank, width in enumerate(rank_sizes)
                        for _ in range(width)]
        ranks = max(1, len(rank_sizes))
        if regiment.unit_class == 7 and regiment.models == 2:
            # game_rules.md "Formations": a wagon's two models occupy ranks 0 and 1 of a
            # four-deep movement layout, giving F=36/28 before their stagger terms.
            ranks, rank_indices = 4, [0, 1]
        s_rlmv = regiment.speed_per_tick * 16 / MOVING_FREELY_K
        updated, still_moving = [], False
        for index, ((px, py), slot) in enumerate(zip(regiment.positions, targets)):
            model = regiment.melee_models[index]
            if model.rout_pause_ticks > 0:
                model.rout_pause_ticks -= 1
                updated.append((px, py))
                still_moving = True
                continue
            if regiment.in_melee and model.at_rest:
                updated.append((px, py))
                continue
            cell = battle_grid.cell_target(self, regiment, index)
            tx, ty = cell if cell is not None else slot
            dx, dy = tx - px, ty - py
            distance = math.hypot(dx, dy)
            if model.freeze_ticks > 0:
                model.freeze_ticks -= 1
                model.at_rest = distance <= MODEL_ARRIVAL_DISTANCE
                new_position = (px, py)
                still_moving |= not model.at_rest
            elif distance <= MODEL_ARRIVAL_DISTANCE:
                model.current_speed = model.distance_budget = 0.0
                model.at_rest = True
                new_position = (px, py)
            else:
                model.at_rest = False
                target_speed = distance if regiment.routing else min(distance, s_rlmv)
                model.current_speed = min(target_speed, model.current_speed + scale)
                if model.distance_budget <= 0:
                    model.heading_x, model.heading_y = dx / distance, dy / distance
                    model.distance_budget = distance / 2
                step_factor = ((ranks - rank_indices[index]) * 8 + (model.stagger & 6) + 4)
                step = min(distance, model.current_speed * step_factor * MODEL_STEP_SCALE * scale)
                new_position = (px + model.heading_x * step, py + model.heading_y * step)
                model.distance_budget -= step
                remaining = math.hypot(tx - new_position[0], ty - new_position[1])
                if remaining <= MODEL_ARRIVAL_DISTANCE:
                    model.current_speed = model.distance_budget = 0.0
                    model.at_rest = True
                else:
                    still_moving = True
            if cell is not None:
                model.arrived = math.hypot(tx - new_position[0], ty - new_position[1]) <= battle_grid.ARRIVAL_DISTANCE
            updated.append(new_position)
        regiment.positions = updated
        return still_moving

    def side_counts(self):
        """Per-side active/routing/fled/destroyed regiment counts (whshr.battle_log snapshots, and the
        diagnosis for "defeat never triggered": every result check's inputs are visible here)."""
        counts = {}
        for side in Side:
            regiments = [r for r in self.regiments.values() if r.side == side]
            counts[side.value] = {
                "active": sum(1 for r in regiments if r.active),
                "routing": sum(1 for r in regiments if r.routing and r.active),
                "fled": sum(1 for r in regiments if r.fled),
                "destroyed": sum(1 for r in regiments if r.destroyed),
                "total": len(regiments),
            }
        return counts

    def _update_result(self):
        if not (self._has_enemy and self._has_player):
            return
        alive_enemy = any(r.active for r in self.regiments.values() if r.side == Side.ENEMY)
        alive_player = any(r.active for r in self.regiments.values() if r.side == Side.PLAYER)
        if not alive_enemy and alive_player:
            self.result = "victory"
            self.events.append(BattleEvent(
                "Victory! The enemy army is destroyed.", "result",
                result="victory", counts=self.side_counts()))
        elif not alive_player:
            self.result = "defeat"
            self.events.append(BattleEvent(
                "Defeat! Your army is destroyed.", "result",
                result="defeat", counts=self.side_counts()))

    def _resolve_collisions(self):
        """Push regiments under orders out of the regiments they overlap (a simplified push-apart;
        game_rules.md, "Routes, collisions and visibility"), not the polygon obstruction routing (`Nav*`).

        Standing regiments never give way, so scripted deployments that already overlap (BF001's Grudgebringer
        cavalry and infantry) stay where the script placed them. Pairs are visited in identifier order.
        """
        regiments = [self.regiments[key] for key in sorted(self.regiments) if self.regiments[key].active]
        for i, first in enumerate(regiments):
            for second in regiments[i + 1:]:
                if first.in_melee or second.in_melee:
                    continue
                if can_fight(first.side, second.side):
                    # A pair that can actually fight never pushes apart: a charging regiment must be
                    # free to close all the way to footprint contact (combat.resolve_contacts), not
                    # stop at circle distance (see combat.resolve_contacts: contact needs real
                    # overlap). A pair that can never fight (same side, or the Player-Neutral
                    # exception rules.can_fight documents) still pushes apart like same-side
                    # regiments always did, so e.g. peasants don't sit interpenetrating the player.
                    continue
                first_yields = first.moving or first.routing or first.attack_target is not None
                second_yields = second.moving or second.routing or second.attack_target is not None
                yielding = first_yields + second_yields
                if not yielding:
                    continue
                dx, dy = second.x - first.x, second.y - first.y
                distance = math.hypot(dx, dy)
                overlap = first.bounding_radius() + second.bounding_radius() - distance
                if overlap <= 0:
                    continue
                ux, uy = (dx / distance, dy / distance) if distance > 1e-6 else (1.0, 0.0)
                share = overlap / yielding
                if first_yields:
                    first.x -= ux * share
                    first.y -= uy * share
                if second_yields:
                    second.x += ux * share
                    second.y += uy * share
