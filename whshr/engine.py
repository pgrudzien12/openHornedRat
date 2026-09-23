"""Deterministic battle-state primitives shared by prototype frontends."""

from dataclasses import dataclass, field
import math
import random

from . import ai, battle_grid, behaviour, combat, formation, interpreter
from .battle_events import BattleEvent
from .rules import EXPECTED_WEAPON_BONUS, MISSILE_RANGES, Side, side_of_code, stat_fields
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
# World units a model may close on its formation slot in one tick before it counts as "settled" (not
# walking); small compared to a tick's travel distance so it only masks floating-point residue.
SETTLE_EPSILON = 0.05
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
    strength_bonus: int = 0  # weapon class bonus, rules.EXPECTED_WEAPON_BONUS[s_weap]
    missile_code: int | None = None  # S_BalWeap, only ARCHER_MISSILE_CODES are modelled as shooters
    missile_range: float | None = None  # world units, from rules.MISSILE_RANGES
    psychology: frozenset = frozenset()  # psy_status flag names, e.g. {"CantBreak", "CantRally"}
    hud_class: str | None = None  # "inf"/"arch"/"art"/"wiz"/"mon"; see HUD_CLASS_BY_RACE_TYPE

    # Combat/order state (whshr.combat, whshr.ai).
    attack_target: str | None = None  # identifier of an enemy regiment this regiment is charging
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

    def model_positions(self, spacing=formation.MODEL_SPACING):
        """Current per-model positions (BTS world units): seeded in formation, then advanced by `Battle.tick`."""
        if len(self.positions) != self.models:
            self.positions = formation.place(self.x, self.y, self.direction,
                                              formation.block_slots(self.models, self.ranks, spacing))
        if len(self.melee_models) != len(self.positions):
            # Reseeding the formation renews every model's identity. Identities are drawn from a
            # counter that never restarts, so a pairing left over from before the reseed can never be
            # mistaken for one of the new models: it simply refers to a model that no longer exists.
            self.melee_models = [ModelState(uid=self._next_uid + offset)
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
    """Decode a regiment's WS/BS/S/T/W/I/A/Ld, armour, weapon and missile stats from its raw script
    setstats lines (game_rules.md section 3), stdlib-only (no GAMEF.DLL access needed at battle time:
    the tables it would supply are already verified constants in whshr.rules)."""
    fields, _conflicts = stat_fields(unit.get("stats") or {})
    profile = unit.get("profile") or {}
    armour = fields.get("s_armr", 0)
    weapon_class = fields.get("s_weap")
    missile_code = fields.get("S_BalWeap")
    missile_range = MISSILE_RANGES.get(missile_code) if missile_code in ARCHER_MISSILE_CODES else None
    psy_status = unit.get("set", {}).get("psy_status")
    psychology = frozenset(f for f in str(psy_status or "").split("|") if f)
    side = fields.get("s_side")
    hud_class = HUD_CLASS_BY_RACE_TYPE.get(side & 0x3F) if side is not None else None
    return {
        "ws": int(profile.get("WS", DEFAULT_PROFILE["WS"])),
        "bs": int(profile.get("BS", DEFAULT_PROFILE["BS"])),
        "strength": int(profile.get("S", DEFAULT_PROFILE["S"])),
        "toughness": int(profile.get("T", DEFAULT_PROFILE["T"])),
        "wounds": int(profile.get("W", DEFAULT_PROFILE["W"])),
        "initiative": int(profile.get("I", DEFAULT_PROFILE["I"])),
        "attacks": int(profile.get("A", DEFAULT_PROFILE["A"])),
        "leadership": int(profile.get("Ld", DEFAULT_PROFILE["Ld"])),
        "armour": armour,
        "strength_bonus": EXPECTED_WEAPON_BONUS.get(weapon_class, 0),
        "missile_code": missile_code if missile_range else None,
        "missile_range": missile_range,
        "psychology": psychology,
        "hud_class": hud_class,
    }


class Battle:
    """Authoritative fixed-tick state: movement, and (whshr.combat/whshr.ai) close combat, shooting,
    morale and a simple enemy AI."""

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
        # battle, in which case whshr.ai's placeholder AI drives every regiment instead (Battle.tick).
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
        interpreter drives every regiment instead of `whshr.ai`'s placeholder rule. Each unit's own
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
                profile = unit.get("profile") or {}
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
                    speed_per_tick=speed_per_tick(profile.get("M"), profile.get("I")),
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
        if not 0 <= x <= self.width or not 0 <= y <= self.height:
            raise ValueError("destination is outside the battlefield")
        regiment.attack_target = None
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
        target = self.regiments.get(target_id)
        if target is None or target.side == Side.PLAYER:
            raise ValueError("attack target must not be a player regiment")
        if not target.active:
            raise ValueError(f"{target_id} is no longer on the field")
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = target_id

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
        # Run behaviour scripts via the bytecode interpreter (issue #3), or fall back to simple AI
        if self.interpreter:
            for unit_id, state in self.event_bus.unit_states.items():
                self.interpreter.run(unit_id, state, self.tick_count, self.rng)
        else:
            ai.decide_orders(self)
        combat.refresh_melee_state(self)
        self._advance_regiments(scale, seconds)
        self._resolve_collisions()
        combat.resolve_contacts(self)
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
            moved = False
            if regiment.in_melee:
                pass  # frozen in place while fighting; the view shows the attack animation instead
            elif regiment.routing:
                if regiment.flee_x is None:  # self-heal: should only happen for pre-existing state
                    regiment.flee_x, regiment.flee_y = self._flee_point(regiment)
                moved = self._advance_toward(regiment, (regiment.flee_x, regiment.flee_y),
                                             regiment.speed_for_mode(FLEEING_K) * scale, arrive=False)
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
                else:
                    moved = self._advance_toward(regiment, (target.x, target.y),
                                                 regiment.speed_for_mode(CHARGING_K) * scale, arrive=False)
            elif regiment.moving:
                moved = self._advance_toward(regiment, (regiment.target_x, regiment.target_y),
                                             regiment.speed_per_tick * scale, arrive=True)
            models_catching_up = self._advance_models(regiment, regiment.speed_per_tick * scale)
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
    def _advance_toward(regiment, target, step, arrive):
        """Move `regiment`'s anchor by at most `step` toward `target`, turning to face travel direction.

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
        # 0 = north/+Y and directions increase clockwise.
        Battle._turn_to(regiment, round(math.atan2(dx, dy) * 512 / math.tau) % 512)
        if arrive and distance <= step:
            regiment.x, regiment.y = target
            regiment.target_x = regiment.target_y = None
            return False
        regiment.x += dx / distance * step
        regiment.y += dy / distance * step
        return True

    def _nearest_enemy(self, regiment):
        """The nearest active regiment of a *different* side, whatever it is (used for a rout's flee
        bearing and rally's "enemy nearby" check): the opponent to flee from is whoever `regiment` is
        actually engaged with, not restricted to `rules.hostile_sides`' default hostility, which only
        gates unprompted/autonomous targeting (`whshr.ai`, `whshr.combat._shooting_target`)."""
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

    def _advance_models(self, regiment, step):
        """Walk each model toward its target, never faster than the unit's speed.

        The target is normally the model's formation slot, but a model that holds a cell on a battle
        grid walks to that cell instead and is marked `arrived` once it is within
        `battle_grid.ARRIVAL_DISTANCE` of it (game_rules.md 5.8 step 6): only then may it strike.
        """
        targets = formation.place(regiment.x, regiment.y, regiment.direction,
                                  formation.block_slots(regiment.models, regiment.ranks))
        updated, still_moving = [], False
        for index, ((px, py), slot) in enumerate(zip(regiment.positions, targets)):
            model = regiment.melee_models[index] if index < len(regiment.melee_models) else None
            cell = battle_grid.cell_target(self, regiment, index) if model is not None else None
            tx, ty = cell if cell is not None else slot
            dx, dy = tx - px, ty - py
            distance = math.hypot(dx, dy)
            if cell is not None and model is not None:
                model.arrived = distance <= battle_grid.ARRIVAL_DISTANCE
            if distance <= SETTLE_EPSILON:
                updated.append((tx, ty))
                continue
            still_moving = True
            if distance <= step:
                updated.append((tx, ty))
            else:
                updated.append((px + dx / distance * step, py + dy / distance * step))
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
                if first.side != second.side:
                    # Different sides never push apart: a charging regiment must be free to close all
                    # the way to footprint contact (combat.resolve_contacts), not stop at circle
                    # distance (see combat.resolve_contacts: contact needs real overlap).
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
