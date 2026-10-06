"""Deterministic battle-state primitives shared by prototype frontends."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
import random
from typing import Any, Literal

from . import animation, battle_grid, behaviour, combat, deployment, formation, interpreter, navigation, visibility
from . import nodes as node_table
from .battle_events import BattleEvent
from .battle_log import BattleLogger
from .rules import (EXPECTED_WEAPON_BONUS, MISSILE_RANGES, MOUNT_PROFILES, Side, may_engage, side_of_code,
                    stat_fields, stat_int)
from .script import StrPath, View, load_battle, resource_name

Point = formation.Point
TurnKey = tuple[Any, ...]  # ('move', x, y), ('charge', id), ('flee',) or ('turn', goal)

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
# game_rules.md "Formation changes": the flat re-form mover decelerates inside the last 6 world
# units, and a single step is capped at 1 world unit (only the fastest units ever reach that cap).
REFORM_DECEL_DISTANCE = 6.0
REFORM_STEP_CAP = 1.0
# Basic bow-type missile codes this engine models as shooters (game_rules.md 8.1/8.3): artillery and
# special weapons (cannons, mortars, breath weapons, ...) are not modelled in this simplified engine.
ARCHER_MISSILE_CODES = {1, 2, 9, 18, 19}
# Default combat profile for a regiment without a decoded profile (WS/BS/S/T/W/I/A/Ld); an ordinary
# human infantryman, matching DEFAULT_S_RLMV's M4 I3 example.
DEFAULT_PROFILE: dict[str, int] = {"WS": 3, "BS": 3, "S": 3, "T": 3, "W": 1, "I": 3, "A": 1, "Ld": 7}

# The battle HUD's command panel picks a button layout by one of five unit classes (Inf, Arch,
# Art, Wiz, Mon; notes/game_rules.md "Battle HUD layout"). The note names the classes but does not
# give their numeric encoding ("classes 0 and 7-9 have no buttons" does not obviously match this
# byte, since 0 here is Monster, which the HUD's own table gives buttons to) - PROVISIONAL: derived
# from the s_side race/type byte (script.RACE_TYPES) as the best available signal, not confirmed
# against the panel's own class numbering.
HUD_CLASS_BY_RACE_TYPE: dict[int, str] = {
    0: "mon", 1: "inf", 2: "inf", 3: "arch", 4: "inf", 5: "arch", 6: "inf", 7: "inf", 8: "inf",
    9: "inf", 10: "arch", 11: "inf", 12: "inf", 13: "arch", 14: "inf",
    15: "art", 16: "art", 17: "art", 18: "art", 19: "wiz",
}


def snap_facing_to_view(direction: float, view_angle: float) -> float:
    """Round `direction` to the nearest 45 degree step (64 of 512) of a grid offset by where the
    camera sits inside a 45 degree sector."""
    step = formation.FULL_TURN / 8
    offset = view_angle % step
    return (round((direction - offset) / step) * step + offset) % formation.FULL_TURN


def speed_per_tick(move_stat: float | None, initiative_stat: float | None, k: float = MOVING_FREELY_K) -> float:
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
    cell: battle_grid.Cell | None = None  # (row, col) this model holds on the grid, or None when not placed
    opponent: tuple[str, int] | None = None  # (regiment identifier, model uid) this model is paired with
    arrived: bool = False  # has walked into its cell, so it may strike (model flag 0x10000)
    reserve: bool = False  # found no free cell this tick and waits for one (model flag 0x8000)
    stagger: int = 0  # fixed 16-bit value (29 * n % 65536, n battle-wide) for this model's rank-dependent pace and later charge delay
    current_speed: float = 0.0  # speed counter, converted to world units by the rank step factor
    distance_budget: float = 0.0  # travel remaining before recomputing the slot heading
    heading_x: float = 0.0
    heading_y: float = 0.0
    at_rest: bool = True
    freeze_ticks: int = 0  # charge-start pause, (stagger & 7) + 1 ticks
    rout_pause_ticks: int = 0  # break-and-turn pause, (stagger & 7) * 3 + 6 ticks
    action: int = animation.STAND  # current action id, whshr.animation (game_rules.md "Figure animation")
    action_pc: int = 0  # ticks elapsed since the action's program counter was last reset
    action_entry: int = 0  # random entry/choice drawn on that reset, whshr.animation.step
    pending_action: int | None = None  # action queued behind a running one-shot script
    drawn_facing: float | None = None  # facing (0-511) the sprite direction is drawn from; None until first set
    fire_event: bool = False  # animation reached its fire point on this tick (whshr.animation)
    # ScatterModelsToNode destination this model walks to instead of its formation slot, or None while
    # in formation (notes/scatter_models_to_node.md); cleared by SnapModelsToFormation.
    scatter_target: Point | None = None


@dataclass
class Regiment:
    """A regiment anchor in BTS coordinates; its models walk to formation slots around that anchor."""

    identifier: str
    name: str
    x: float
    y: float
    direction: float
    side: Side  # notes/neutral_units.md: player, neutral/NPC, or enemy
    target_x: float | None = None
    target_y: float | None = None
    models: int = 1
    ranks: int = 1
    sprite: str | None = None  # script troop sprite resource, e.g. "ClanRats"
    banner: str | None = None  # script banner resource
    portrait: str | None = None  # leader portrait resource
    speed_per_tick: float = DEFAULT_SPEED_PER_TICK  # BTS world units per 100 ms tick, moving freely
    positions: list[Point] = field(default_factory=list[Point])  # current per-model (x, y); lazily seeded in formation
    melee_models: list[ModelState] = field(default_factory=list[ModelState])  # ModelState, index-parallel with `positions`
    _next_uid: int = 0  # next free model identity (see ModelState.uid)
    # Battle-wide model counter feeding `ModelState.stagger`; `Battle` shares one across all its regiments.
    # A regiment used on its own (tests) keeps a private one, created on first use.
    stagger_counter: "StaggerCounter | None" = None
    walking: bool = False  # true while the anchor or any model is still travelling
    independent: bool = False
    hidden: bool = False
    waypoints: list[Point] = field(default_factory=list[Point])
    route_follows_unit: bool = False

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
    psychology: frozenset[str] = frozenset()  # psy_status flag names, e.g. {"CantBreak", "CantRally"}
    hud_class: str | None = None  # "inf"/"arch"/"art"/"wiz"/"mon"; see HUD_CLASS_BY_RACE_TYPE
    unit_class: int | None = None  # s_race class; wagons use a four-deep movement layout
    points: int = 0  # s_pntval: experience gained by the killer, and the AI's per-model worth unit
    # (game_rules.md: unit worth = size x s_pntval x 12 artillery / 8 wizard / 4 monster / 1)
    # set:whoami as one byte: the persistent campaign regiment id (0 for ordinary mission units),
    # addressed by SendEventToUnitId (notes/threat_events_nodes.md, part B 0.1).
    whoami: int = 0

    # Combat/order state (whshr.combat).
    attack_target: str | None = None  # identifier of an enemy regiment this regiment is charging
    charge_started_target: str | None = None  # target whose current charge already froze its models
    turn_order_key: TurnKey | None = None
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
    # Set (to `Side.DUEL`) only while this regiment is fighting a same-side regiment its script named as
    # its opponent; see `rules.may_engage`. Cleared whenever it leaves its fight.
    melee_camp: Side | None = None
    melee_group: str | None = None  # id of the shared multi-regiment fight (Battle.fights), if any
    melee_touching: frozenset[str] = field(default_factory=frozenset[str])  # enemy ids this footprint touches now
    held: bool = False  # reserved for a Tangling-Thorn-style hold; already gates re-forms if ever set
    # game_rules.md "Formation changes": true while models are still walking to their newly assigned
    # slots after a re-form; `reform_slots` holds each model's assigned local (side, forward) offset,
    # index-parallel with `positions`/`melee_models`, turned into a world target every tick with
    # `formation.place` so it tracks a moving or turning anchor.
    reforming: bool = False
    anchor_cleared: bool = False  # set by `clear_anchor` (artillery misfire); see `anchored`
    reform_slots: list[Point] = field(default_factory=list[Point])
    routing: bool = False  # fleeing the field; ignores orders, moves away from the nearest enemy
    # game_rules.md "Flight and catching fleeing units": the flight bearing is fixed once, "directly
    # away from its opponent", when the rout starts (combat.start_rout) - not re-aimed every tick
    # at whichever enemy happens to be nearest at that instant. A far point along that bearing
    # (Battle.flee_point's own convention); None only before the first rout tick sets it.
    flee_x: float | None = None
    flee_y: float | None = None
    fled: bool = False  # a routing regiment that has left the battlefield (removed from play)
    flight_check_ticks: int = 0
    flight_departed: bool = False
    flight_complete: bool = False
    flight_complete_tick: int = -1
    avoid_target: Point | None = None
    avoid_key: tuple[str, str] | None = None
    fire_posts: int = 0  # fire events posted by this volley's shooters so far (consumed by combat)
    volley_countdown: int | None = None  # remaining fire-event decrements expected in the current volley
    volley_age: int = 0  # ticks elapsed since the current volley was ordered; drives the resolve window
    reload_ticks: float = 0.0  # ticks remaining before a missile regiment may shoot again
    dying: list[animation.DyingModel] = field(default_factory=list[animation.DyingModel])  # animation.DyingModel entries awaiting their collapse tick
    corpses: list[tuple[float, float, int]] = field(default_factory=list[tuple[float, float, int]])  # (x, y, direction) of models that have died, for the view
    burning: list[animation.BurningModel] = field(default_factory=list[animation.BurningModel])  # animation.BurningModel: burn sequences in progress (fire/warpfire kills)
    charred: list[tuple[float, float, int, str]] = field(default_factory=list[tuple[float, float, int, str]])  # (x, y, direction, body class) of models that finished burning

    # Traced close-combat/rally timing (game_rules.md 5.5, 6.1-6.2, 7.4), see whshr.combat.
    # The fight's own-side tally, breakdown and next break-test turn (6.1-6.2) live on
    # `Battle.fights[regiment.melee_group]`, shared by every regiment in that fight.
    original_models: int = -1  # starting model count, for rally's casualties modifier; negative = the `models` given
    # game_rules.md 6.1: the formed frontage, which casualties never reduce (only a re-form would).
    # The rank bonus divides the live model count by this, so it decays as the unit is worn down.
    frontage: int = -1  # negative = derived from `models`/`ranks` in __post_init__
    script_ranks: int = -1  # the rank count the battle file asks for (what re-form scripts restore); negative = `ranks`
    # game_rules.md 5.5: floor(1.5 x frontage), set when the regiment charges into a fight and spent
    # one attacking model at a time, so only the first models to strike get the +1 S.
    charge_counter: int = 0
    # game_rules.md 5.5: "re-engaging an opponent you are already fighting gives no bonus" -- the last
    # enemy identifier this regiment was recorded fighting, kept across leaving and re-joining a fight,
    # so a fresh charge counter is granted only against a genuinely new opponent.
    last_fought_opponent: str | None = None
    rally_next_segment: int | None = None  # absolute segment index of the next scheduled rally attempt (7.4)

    def __post_init__(self) -> None:
        if self.original_models < 0:
            self.original_models = self.models
        if self.script_ranks < 0:
            self.script_ranks = self.ranks
        if self.frontage < 0:
            sizes = formation.rank_sizes(self.models, self.ranks)
            self.frontage = sizes[0] if sizes else 0

    @property
    def camp(self) -> Side:
        """Who this regiment fights for in a melee: its side, unless a scripted same-side engagement
        put it on its own `Side.DUEL` camp."""
        return self.melee_camp or self.side

    @property
    def visible_to_player(self) -> bool:
        """Friendly display preserves opposing visibility (notes/deployment.md §1.3)."""
        return self.side != Side.ENEMY or not self.hidden

    @property
    def anchored(self) -> bool:
        """War machines are anchored by rule, not by AI or mission choice (game_rules.md "Turning,
        wheeling and reversing"): the artillery class always carries the anchor flag, until an
        artillery misfire explosion clears it (`clear_anchor`; there is no limbering).

        The flag refuses marching orders, every normal battle turn type, charge
        orders and internal charge starts, pursuit and script-initiated melee contact. It does not
        stop shooting/reloading, halting, being attacked or engaged, being pushed by collisions,
        rank changes, flight movement or the Independent/rally toggles."""
        return self.hud_class == "art" and not self.anchor_cleared

    def clear_anchor(self) -> None:
        """Hook for an artillery misfire explosion, the only thing that frees an anchored war machine.
        The engine has no misfire mechanic yet, so nothing calls this."""
        self.anchor_cleared = True

    @property
    def animation_family(self) -> str:
        return animation.family_for(self.sprite, self.unit_class)

    @property
    def body_class(self) -> str:
        return animation.body_class(self.unit_class, self.sprite)

    def burns_on(self, death_kind: int) -> bool:
        return animation.burns_on_death(death_kind, self.unit_class, self.sprite)

    @property
    def is_wagon(self) -> bool:
        return self.unit_class == 7 and self.models == 2

    @property
    def turns_on_the_spot(self) -> bool:
        """Single-model units and units mid-re-form skip the pivot, slot-shift and speed-penalty
        machinery of a gradual turn (game_rules.md, same section); their turn rate is unchanged."""
        return self.models <= 1 or self.reforming

    @property
    def moving(self) -> bool:
        return self.target_x is not None

    @property
    def mount_profile(self) -> dict[str, int] | None:
        return MOUNT_PROFILES.get(self.mount) if self.mount is not None and 8 <= self.armour <= 13 else None

    @property
    def destroyed(self) -> bool:
        return self.models <= 0

    @property
    def active(self) -> bool:
        """False once a regiment is out of the fight (all models dead, or routed off the field)."""
        return not self.destroyed and not self.fled

    def speed_for_mode(self, k: float) -> float:
        """Per-tick speed at movement factor ``k`` (game_rules.md k factors), scaled from the regiment's
        own free-movement speed rather than carrying a second raw ``s_rlmv`` field."""
        return self.speed_per_tick * k / MOVING_FREELY_K

    @property
    def charge_reach(self) -> float:
        """game_rules.md "Charge": a real charge reaches at most ``12 * (s_rlmv + 1)`` world units
        (about 6" for infantry, 9.5" for cavalry) -- a short final rush, not the whole approach.
        Recovers ``s_rlmv`` from the stored free-movement `speed_per_tick` (``s_rlmv * 1.8 / 16``)
        rather than carrying a second raw field, same approach as `speed_for_mode`."""
        s_rlmv = self.speed_per_tick * 16 / MOVING_FREELY_K
        return 12 * (s_rlmv + 1)

    def model_positions(self, spacing: float = formation.MODEL_SPACING) -> list[Point]:
        """Current per-model positions (BTS world units): seeded in formation, then advanced by `Battle.tick`."""
        if len(self.positions) != self.models:
            self.positions = formation.place(self.x, self.y, self.direction,
                                              formation.block_slots(self.models, self.ranks, spacing))
        if len(self.melee_models) != len(self.positions):
            # Reseeding the formation renews every model's identity. Identities are drawn from a
            # counter that never restarts, so a pairing left over from before the reseed can never be
            # mistaken for one of the new models: it simply refers to a model that no longer exists.
            if self.stagger_counter is None:
                self.stagger_counter = StaggerCounter()
            self.melee_models = [ModelState(uid=self._next_uid + offset,
                                            stagger=self.stagger_counter.next_value())
                                 for offset in range(len(self.positions))]
            self._next_uid += len(self.positions)
            # A reseed (casualties changing the model count outside kill_models, reinforcement, ...)
            # invalidates any in-progress re-slotting: `reform_slots` would no longer be index-parallel
            # with the renewed `positions`/`melee_models`.
            self.reforming = False
            self.reform_slots = []
        return self.positions

    def index_of(self, uid: int) -> int | None:
        """Position of the model with this identity, or None once it has been killed."""
        for index, model in enumerate(self.melee_models):
            if model.uid == uid:
                return index
        return None

    def front_rank_models(self) -> int:
        """Model count of the front rank, the attackers/shooters counted in a combat or volley round."""
        sizes = formation.rank_sizes(self.models, self.ranks)
        return sizes[0] if sizes else 0

    def _footprint(self) -> formation.Frame:
        return formation.footprint_frame(self.x, self.y, self.direction, self.models, self.ranks)

    def contains(self, x: float, y: float) -> bool:
        """True when a ground point lies inside the regiment's oriented block footprint."""
        cx, cy, half_side, half_forward, cos, sin = self._footprint()
        dx, dy = x - cx, y - cy
        local_side = dx * cos - dy * sin
        local_forward = dx * sin + dy * cos
        return abs(local_side) <= half_side and abs(local_forward) <= half_forward

    def bounding_radius(self) -> float:
        return formation.bounding_radius(self.models, self.ranks)

    def block(self) -> formation.Block:
        """`(x, y, direction, models, ranks)`, the block description `whshr.formation` works from."""
        return (self.x, self.y, self.direction, self.models, self.ranks)

    def footprint_corners(self) -> list[Point]:
        """The four world-space corners of this regiment's oriented block footprint, for
        `formation.footprint_gap` (close-combat contact, `whshr.combat.resolve_contacts`)."""
        return formation.footprint_corners(self.x, self.y, self.direction, self.models, self.ranks)


def _slot_offsets(assignment: Sequence[Point | None]) -> list[Point]:
    """`formation.reform_assignment`'s result with every model given a slot (always so when the block's
    slot count matches its model count)."""
    slots = [slot for slot in assignment if slot is not None]
    if len(slots) != len(assignment):
        raise ValueError("re-form left a model without a slot")
    return slots


def _decode_combat_profile(unit: Mapping[str, Any]) -> dict[str, Any]:
    """Decode a regiment's speed, WS/BS/S/T/W/I/A/Ld, armour, weapon and missile stats from its raw script
    setstats lines (game_rules.md section 3), stdlib-only (no GAMEF.DLL access needed at battle time:
    the tables it would supply are already verified constants in whshr.rules)."""
    fields, _conflicts = stat_fields(unit.get("stats") or {})
    profile: Mapping[str, Any] = unit.get("profile") or {}
    armour = stat_int(fields, "s_armr") or 0
    mount_code = stat_int(fields, "s_mount")
    mount = MOUNT_PROFILES.get(mount_code) if mount_code is not None and 8 <= armour <= 13 else None
    move_stat = mount["M"] if mount is not None else profile.get("M")
    weapon_class = stat_int(fields, "s_weap")
    missile_code = stat_int(fields, "S_BalWeap")
    missile_range = (MISSILE_RANGES.get(missile_code)
                     if missile_code is not None and missile_code in ARCHER_MISSILE_CODES else None)
    psy_status = unit.get("set", {}).get("psy_status")
    psychology = frozenset(f for f in str(psy_status or "").split("|") if f)
    side = stat_int(fields, "s_side")
    hud_class = HUD_CLASS_BY_RACE_TYPE.get(side & 0x3F) if side is not None else None
    race = stat_int(fields, "s_race")
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
        "mount": mount_code,
        "strength_bonus": EXPECTED_WEAPON_BONUS.get(weapon_class, 0) if weapon_class is not None else 0,
        "missile_code": missile_code if missile_range else None,
        "missile_range": missile_range,
        "psychology": psychology,
        "hud_class": hud_class,
        "unit_class": race >> 3 if race is not None else None,
        "points": stat_int(fields, "s_pntval") or 0,
    }


class StaggerCounter:
    """Battle-wide count of models created; the n-th model gets stagger ``29 * n % 65536``
    (game_rules.md, model stagger). Never reset per regiment."""

    def __init__(self) -> None:
        self.count = 0

    def next_value(self) -> int:
        value = 29 * self.count % 65536
        self.count += 1
        return value


class Battle:
    """Authoritative fixed-tick state: movement, and (whshr.combat) close combat, shooting, morale."""

    def __init__(self, width: float, height: float, regiments: Sequence[Regiment], seed: int = DEFAULT_SEED,
                 script_dll: behaviour.ScriptDll | None = None, script_ids: Mapping[str, int] | None = None,
                 script_logger: BattleLogger | None = None, nodes: Mapping[int, Point] | None = None,
                 script_nodes: Sequence[node_table.ScriptNode] | None = None,
                 deploy: bool = False, boundaries: Sequence[View] = (), objects: Sequence[View] = ()) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("battle dimensions must be positive")
        self.width = width
        self.height = height
        self.regiments: dict[str, Regiment] = {regiment.identifier: regiment for regiment in regiments}
        if len(self.regiments) != len(regiments):
            raise ValueError("regiment identifiers must be unique")
        self.stagger_counter = StaggerCounter()
        for regiment in regiments:
            regiment.stagger_counter = self.stagger_counter
        self.tick_count = 0
        self.update_count = 0  # monotonic input/replay time, including deployment
        self.phase: Literal["deployment", "battle"] = "deployment" if deploy else "battle"
        self.paused = False
        self.mission_state = 0  # script choreography, independent of the player-visible phase
        self.deployment_regions = deployment.regions(boundaries)
        self.deployment_region: deployment.Region | None = None
        self.deployment_drag: deployment.Drag | None = None
        self.boundaries = list(boundaries)
        self.navigation_boundaries = navigation.boundaries_from_views(boundaries)
        self.objects = list(objects)
        # Camera rotation in 1/512 turns, set by the frontend; wagons snap to it (see set_view_angle).
        self.view_angle: float | None = None
        self._snapped_view_angle: float | None = None
        self.rng = random.Random(seed)
        self.events: list[BattleEvent] = []  # battle events emitted by the most recent tick
        # {node id: (x, y)} from the battle's own [NODES] section (whshr.script.load_battle),
        # BTS world coordinates; read by the interpreter's MoveToNode/FaceNode/TeleportToNode/
        # PlaceAtNode opcodes (issue #3/#46). Empty for a synthetic/nodeless battle.
        self.nodes: dict[int, Point] = dict(nodes or {})
        # The full [NODES] table in list order, with each entry's own `id`, `radius` and active status:
        # ScatterModelsToNode names a node by that `id`, not by list position
        # (notes/scatter_models_to_node.md). A synthetic battle without one gets `nodes` as active,
        # radius-16 entries whose id is their key.
        self.script_nodes: list[node_table.ScriptNode] = (
            list(script_nodes) if script_nodes is not None
            else [node_table.ScriptNode(x, y, key) for key, (x, y) in self.nodes.items()])
        self.fights: dict[str, combat.Fight] = {}  # group id -> {"next_test_turn", "tally": {True/False}, "breakdown": {...}}
        self.fight_seq = 0  # counter for fresh whshr.combat fight group ids
        self.result: str | None = None  # None while the battle is ongoing, else "victory" or "defeat"
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
        self.interpreter: interpreter.ScriptInterpreter | None = (interpreter.ScriptInterpreter(self, self.event_bus, script_dll, logger=script_logger)
                             if script_dll else None)

    @classmethod
    def from_battle_file(cls, path: StrPath, seed: int = DEFAULT_SEED, script_dll: behaviour.ScriptDll | None = None,
                         script_logger: BattleLogger | None = None) -> "Battle":
        return cls.from_script(load_battle(path), seed=seed, script_dll=script_dll, script_logger=script_logger)

    @classmethod
    def from_script(cls, source: View, seed: int = DEFAULT_SEED, script_dll: behaviour.ScriptDll | None = None,
                    script_logger: BattleLogger | None = None) -> "Battle":
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
        # Scripts name a node by its position in the [NODES] table, counted from 0. The `set:id=` field is
        # not a key: nearly every node has id 0, so keying by it collapsed BF001's 11 nodes into one.
        # Evidence for the base: BF001's Hiln's Guard patrols MoveToNode 6 <-> 7 and only counting from 0
        # gives it a beat beside its own camp ((924,1183) <-> (1247,1370)) instead of the east map edge.
        nodes = {index: (float(node["x"]), float(node["y"]))
                 for index, node in enumerate(source.get("nodes") or ())
                 if node.get("x") is not None and node.get("y") is not None}
        script_nodes = node_table.from_views(source.get("nodes") or ())
        regiments: list[Regiment] = []
        script_ids: dict[str, int] = {}
        used: set[str] = set()
        # `source["armies"]` are the .BTS file's own [UNITS] sections (both the "Enemy Army" and "NPC
        # units" ones, notes/neutral_units.md section 2): each unit's own s_side byte says whether it
        # is enemy or neutral. `source["merc"]` is the player's own roster from the loaded .MRC, always
        # Side.PLAYER regardless of any s_side value it happens to carry.
        armies: list[tuple[View, Side | None]] = [(army, None) for army in source["armies"]]
        merc: View = source["merc"] or {}
        armies.extend((army, Side.PLAYER) for army in merc.get("armies", []))
        # Deployment defaults apply even without DeployTroops (notes/deployment.md §1).
        # Keep the authored candidate order and reserve only occupied slots. Skipped
        # candidates remain available to subsequent units and army sections.
        start_nodes: list[View] = [node for node in source.get("nodes") or ()
                                  if {"ns_active", "ns_startpos"}.issubset(
                                      str(flag).casefold() for flag in node.get("status") or ())]
        reserved_slots: set[int] = set()
        for army, forced_side in armies:
            declared_count = int(army.get("count", len(army["units"])))
            skip_slots = len(start_nodes) - declared_count
            for unit in army["units"]:
                position = unit["set"]
                identifier, suffix = unit["id"], 2
                while identifier in used:
                    identifier, suffix = f"{unit['id']}#{suffix}", suffix + 1
                used.add(identifier)
                models, ranks = formation.unit_size(unit)
                leader: View = unit.get("leader") or {}
                if forced_side is not None:
                    side = forced_side
                else:
                    fields, _conflicts = stat_fields(unit.get("stats") or {})
                    side = side_of_code(stat_int(fields, "s_side"))
                x_value, y_value = position.get("x"), position.get("y")
                direction = int(position.get("dir") or 0) % 512
                if side == Side.PLAYER and skip_slots >= 0:
                    available = [index for index in range(len(start_nodes)) if index not in reserved_slots]
                    if skip_slots < len(available):
                        slot_index = available[skip_slots]
                        slot = start_nodes[slot_index]
                        x_value, y_value = slot["x"], slot["y"]
                        direction = int(slot.get("dir") or 0) % 512
                        reserved_slots.add(slot_index)
                if x_value is None or y_value is None:
                    continue
                x, y = float(x_value), float(y_value)
                regiments.append(Regiment(
                    identifier, unit["name"], x, y, direction, side, models=models, ranks=ranks,
                    sprite=resource_name(unit.get("sprites")),
                    banner=resource_name(unit.get("banner")),
                    portrait=resource_name(leader.get("portrait")),
                    hidden=bool(unit.get("hidden", False)),
                    whoami=int(position.get("whoami") or 0) & 0xFF,
                    **_decode_combat_profile(unit),
                ))
                script_value = position.get("script")
                if isinstance(script_value, str) and script_value.upper() == "PLAYER_SCRIPT":
                    script_ids[identifier] = behaviour.PLAYER_SCRIPT
                elif isinstance(script_value, (int, float)):
                    script_ids[identifier] = int(script_value)
        mission: View = source.get("mission") or {}
        return cls(field_data["width"], field_data["height"], regiments, seed=seed,
                   script_dll=script_dll, script_ids=script_ids, script_logger=script_logger, nodes=nodes,
                   script_nodes=script_nodes,
                   deploy=bool(mission.get("deploy_troops")), boundaries=source.get("boundaries") or (),
                   objects=source.get("objects") or ())

    def start_battle(self) -> None:
        """Confirm deployment once, retaining placements and prepared orders (§5)."""
        if self.phase == "deployment":
            self.end_deployment_drag()
            self.phase = "battle"
            self.refresh_visibility()

    def refresh_visibility(self) -> None:
        """Reveal individually hidden regiments permanently when another army spots them."""
        for target in self.regiments.values():
            if not target.hidden or not target.active:
                continue
            for looker in self.regiments.values():
                if not looker.active or looker.side == target.side:
                    continue
                cone = 142 if looker.in_melee else 71
                if visibility.visible(self.formation_centre(looker), looker.direction,
                                      self.formation_centre(target), target.bounding_radius(),
                                      cone, self.boundaries, self.objects):
                    target.hidden = False
                    self.event_bus.queue_event(target.identifier, interpreter.Event(code=0x1C, source=looker.identifier))
                    self.event_bus.queue_event(looker.identifier, interpreter.Event(code=0x1D, source=target.identifier))
                    self.events.append(BattleEvent(f"{target.name} is spotted.", "spotted", regiment=target.identifier,
                                                  spotter=looker.identifier))
                    break

    @staticmethod
    def formation_centre(regiment: Regiment) -> Point:
        frame = formation.footprint_frame(*regiment.block())
        return frame[0], frame[1]

    def begin_deployment_drag(self, identifier: str, x: float, y: float) -> None:
        regiment = self.regiments[identifier]
        if (self.phase != "deployment" or regiment.side != Side.PLAYER or not regiment.active
                or regiment.routing or regiment.held):
            raise ValueError("regiment cannot be dragged during deployment")
        centre = self.formation_centre(regiment)
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = regiment.charge_started_target = None
        regiment.turn_order_key = regiment.turn_mode = None
        regiment.waypoints.clear()
        self._begin_reform(regiment, regiment.ranks)
        self.deployment_drag = deployment.Drag(identifier, (x - centre[0], y - centre[1]), centre)

    def update_deployment_drag(self, x: float, y: float, rotate: bool = False) -> None:
        if self.deployment_drag is not None:
            drag = self.deployment_drag
            drag.target = (float(x) - drag.offset[0], float(y) - drag.offset[1])
            drag.rotate = rotate

    def end_deployment_drag(self) -> None:
        self.deployment_drag = None

    def _step_deployment_drag(self) -> None:
        drag = self.deployment_drag
        if drag is None:
            return
        regiment = self.regiments[drag.regiment_id]
        if not regiment.active:
            self.end_deployment_drag()
            return
        old = self.formation_centre(regiment)
        dx, dy = drag.target[0] - old[0], drag.target[1] - old[1]
        half_x, half_y = math.trunc(dx / 2), math.trunc(dy / 2)
        if half_x == 0 and half_y == 0:
            return
        if drag.rotate:
            goal = round(math.atan2(dx, dy) * 512 / math.tau) % 512
            shift_x, shift_y = formation.turn_pivot_shift(regiment.direction, goal, regiment.models, regiment.ranks)
            regiment.direction = goal
            regiment.x += shift_x
            regiment.y += shift_y
        else:
            matching = next((region for region in self.deployment_regions if region.contains(drag.target)), None)
            switched = matching is not None and matching is not self.deployment_region
            if matching is not None:
                self.deployment_region = matching
            if self.deployment_region is not None:
                base = drag.target if switched else old
                proposed = self.deployment_region.clip((base[0] + half_x, base[1] + half_y))
                regiment.x += proposed[0] - old[0]
                regiment.y += proposed[1] - old[1]
        # Correction deliberately follows clipping, without a final zone clamp (§2).
        for _ in range(10):
            before = (regiment.x, regiment.y)
            self._resolve_collisions(deployment_id=regiment.identifier)
            if (regiment.x, regiment.y) == before:
                break
        self._begin_reform(regiment, regiment.ranks)
        self._snap_deployment_layout(regiment)
        self.refresh_visibility()

    @staticmethod
    def _snap_deployment_layout(regiment: Regiment) -> None:
        slots = regiment.reform_slots or formation.block_slots(regiment.models, regiment.ranks)
        regiment.positions = formation.place(regiment.x, regiment.y, regiment.direction, slots)
        regiment.reforming = False
        regiment.reform_slots = []

    def _require_battle_order(self) -> None:
        if self.phase == "deployment":
            raise ValueError("this order is unavailable during deployment")

    def prepare_deployment_move(self, identifier: str) -> None:
        regiment = self.regiments[identifier]
        if regiment.side == Side.PLAYER and regiment.hud_class in {"inf", "arch", "wiz", "mon"}:
            regiment.target_x = regiment.target_y = None
            regiment.attack_target = None
            regiment.turn_order_key = regiment.turn_mode = None
            self._begin_reform(regiment, regiment.ranks)

    def toggle_independent(self, identifier: str) -> None:
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER or not regiment.active:
            raise ValueError("regiment is not player-controlled and active")
        if self.phase == "deployment" and regiment.hud_class not in {"inf", "arch", "wiz", "mon", "art"}:
            raise ValueError("this class has no deployment Independent control")
        regiment.independent = not regiment.independent

    def append_waypoint(self, identifier: str, x: float, y: float) -> None:
        """Ctrl Move targeting: retain up to nine manual destinations (§3)."""
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER or not regiment.active or regiment.routing or regiment.anchored:
            raise ValueError("regiment cannot receive a move order")
        if not 0 <= x <= self.width or not 0 <= y <= self.height:
            raise ValueError("destination is outside the battlefield")
        if self.phase == "deployment" and regiment.hud_class not in {"inf", "arch", "wiz", "mon"}:
            raise ValueError("this class has no deployment Move control")
        if len(regiment.waypoints) >= 9:
            return
        if regiment.waypoints and any(math.hypot(x - px, y - py) < 17
                                      for px, py in (regiment.waypoints[0], regiment.waypoints[-1])):
            return
        regiment.waypoints.append((float(x), float(y)))

    def order_move(self, identifier: str, x: float, y: float) -> None:
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if regiment.braced:
            raise ValueError(f"{identifier} is braced against a charge and cannot be ordered")
        if regiment.anchored:
            raise ValueError(f"{identifier} is anchored and cannot be ordered to move")
        if not 0 <= x <= self.width or not 0 <= y <= self.height:
            raise ValueError("destination is outside the battlefield")
        if self.phase == "deployment":
            if regiment.hud_class not in {"inf", "arch", "wiz", "mon"}:
                raise ValueError("this class has no deployment Move control")
            regiment.waypoints.clear()
            regiment.target_x = regiment.target_y = None
            if math.hypot(x - regiment.x, y - regiment.y) >= 17:
                self.append_waypoint(identifier, x, y)
            return
        regiment.waypoints.clear()
        regiment.attack_target = None
        regiment.charge_started_target = None
        regiment.turn_order_key = None
        regiment.route_follows_unit = False
        self.set_point_route(regiment, (float(x), float(y)))

    def set_point_route(self, regiment: Regiment, goal: Point) -> None:
        points = navigation.point_route((regiment.x, regiment.y), goal, self.navigation_boundaries)
        regiment.target_x, regiment.target_y = points[0]
        regiment.waypoints = points[1:]
        regiment.avoid_target = regiment.avoid_key = None

    def order_attack(self, identifier: str, target_id: str) -> None:
        """Order a player regiment to charge a non-player regiment into contact (game_rules.md,
        "Charge"): the target may be an enemy or a neutral regiment (notes/neutral_units.md documents
        neutral units as ordinary battle units, not automatically off-limits to a deliberate order)."""
        self._require_battle_order()
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if regiment.braced:
            raise ValueError(f"{identifier} is braced against a charge and cannot be ordered")
        if regiment.anchored:
            raise ValueError(f"{identifier} is anchored and cannot charge")
        target = self.regiments.get(target_id)
        if target is None or target.side == Side.PLAYER:
            raise ValueError("attack target must not be a player regiment")
        if target.hidden:
            raise ValueError("attack target is hidden")
        if not target.active:
            raise ValueError(f"{target_id} is no longer on the field")
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = target_id
        regiment.route_follows_unit = False
        regiment.turn_order_key = None

    def order_halt(self, identifier: str) -> None:
        """Cancel the selected regiment's current movement or charge order in place."""
        self._require_battle_order()
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
        regiment.waypoints.clear()
        regiment.route_follows_unit = False
        # game_rules.md "Braced": Halt is the one order still accepted while braced, and clears it.
        regiment.braced = False
        regiment.braced_target = None

    def resolve_no_battle(self) -> None:
        """No-battle mode (a campaign-progression shortcut, not a game rule): skip this fight and
        settle it as an immediate, lossless win -- every enemy regiment destroyed, no player
        regiment touched -- so the campaign flow past it (debrief, roster, map) can be walked
        without simulating it. Leaves neutral regiments alone; `_update_result` reads only player
        and enemy sides."""
        for regiment in self.regiments.values():
            if regiment.side == Side.ENEMY:
                regiment.models = 0
        self._update_result()

    def order_reform(self, identifier: str, ranks: int) -> None:
        """Change a player regiment's rank count (game_rules.md, "Formation changes: how the figures
        re-sort themselves"): refused while fleeing, held or charging (including once in melee, since
        a charge's `attack_target` is never cleared on contact); the request is clamped into
        `formation.rank_range`. Re-slots every model (`formation.reform_assignment`) and switches the
        unit to the flat re-form mover for as long as any model is still off its assigned slot.
        """
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if self.phase == "deployment" and regiment.hud_class not in {"inf", "arch"}:
            raise ValueError("this class has no deployment rank controls")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if regiment.held:
            raise ValueError(f"{identifier} is held and cannot be ordered")
        if regiment.attack_target is not None or regiment.in_melee:
            raise ValueError(f"{identifier} is charging or in melee and cannot be ordered")
        self._begin_reform(regiment, formation.clamp_ranks(regiment.models, ranks))
        if self.phase == "deployment":
            self._snap_deployment_layout(regiment)
            self.refresh_visibility()

    def reform_to_ranks(self, regiment: Regiment, ranks: int, formation_clamp: bool = True) -> None:
        """Lay `regiment` out in `ranks` ranks and start re-slotting its models: the layout a re-form script
        opcode asks for, with none of the player-order guards. The count is clamped to the span the model
        count allows, or (`formation_clamp` false) only to the 1-8 ranks a battle file may name."""
        self._begin_reform(regiment, formation.clamp_ranks(regiment.models, ranks) if formation_clamp
                           else max(1, min(8, ranks)))

    def _check_turn_order(self, identifier: str) -> Regiment:
        """Shared guard for all standalone turn orders (game_rules.md "Turning, wheeling and reversing")."""
        self._require_battle_order()
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if regiment.in_melee:
            raise ValueError(f"{identifier} is in melee and cannot be ordered")
        return regiment

    def order_turn_left(self, identifier: str) -> None:
        """Rotate a player regiment 90° counter-clockwise in place (game_rules.md, opcodes 0x0C)."""
        regiment = self._check_turn_order(identifier)
        goal = (regiment.direction - 128) % 512
        self._plan_turn_order(regiment, goal)
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = None
        regiment.turn_order_key = ("turn", goal)

    def order_turn_right(self, identifier: str) -> None:
        """Rotate a player regiment 90° clockwise in place (game_rules.md, opcodes 0x0D)."""
        regiment = self._check_turn_order(identifier)
        goal = (regiment.direction + 128) % 512
        self._plan_turn_order(regiment, goal)
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = None
        regiment.turn_order_key = ("turn", goal)

    def order_about_face(self, identifier: str) -> None:
        """Rotate a player regiment 180° in place (game_rules.md, opcodes 0x0E)."""
        regiment = self._check_turn_order(identifier)
        goal = (regiment.direction + 256) % 512
        self._plan_turn_order(regiment, goal)
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = None
        regiment.turn_order_key = ("turn", goal)

    def order_face_point(self, identifier: str, x: float, y: float) -> None:
        """Turn a player regiment to face world coordinates (x, y) in place."""
        regiment = self._check_turn_order(identifier)
        dx, dy = x - regiment.x, y - regiment.y
        if math.hypot(dx, dy) < 1e-9:
            return  # click on own position: ignore
        goal = round(math.atan2(dx, dy) * 512 / math.tau) % 512
        self._plan_turn_order(regiment, goal)
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = None
        regiment.turn_order_key = ("turn", goal)

    @staticmethod
    def begin_script_turn(regiment: Regiment, goal: float) -> None:
        """A turn order issued by a behaviour script (the same halted turn a player order starts)."""
        Battle._plan_turn_order(regiment, goal)
        regiment.turn_order_key = ("turn", goal)

    @staticmethod
    def snap_move_start(regiment: Regiment, goal: float) -> None:
        """The one-time 90/180-degree snap a unit makes when a move order starts from rest."""
        Battle._snap_order_turn(regiment, goal)

    @staticmethod
    def _plan_turn_order(regiment: Regiment, goal: float) -> None:
        """Plan a standalone turn order: always halted (shift 8, zero speed) regardless of angle."""
        delta = Battle._turn_delta(regiment.direction, goal)
        magnitude = abs(delta)
        regiment.turn_goal = goal
        regiment.turn_remaining = magnitude
        regiment.turn_sign = 1 if delta > 0 else -1
        if magnitude <= 10:
            regiment.direction = goal
            regiment.turn_mode = None
            return
        regiment.turn_mode, regiment.turn_shift = "halted", 8

    def _begin_reform(self, regiment: Regiment, ranks: int) -> None:
        """Recompute the shape for `ranks` and re-slot every model into it (game_rules.md, "Formation
        changes"). `leader_index` is left unset: this engine has no persistent leader-model identity
        to hand the front-rank-centre slot to directly, so `formation.reform_assignment` falls back to
        whichever model is currently nearest that slot, the documented fallback for that case.
        """
        positions = regiment.model_positions()
        ranks = max(1, min(regiment.models, ranks)) if regiment.models else 1
        regiment.ranks = ranks
        sizes = formation.rank_sizes(regiment.models, ranks)
        regiment.frontage = sizes[0] if sizes else 0
        if regiment.is_wagon or regiment.hud_class == "art":
            # game_rules.md "Formation differences": war machines and wagons never use the flat
            # re-form mover; their models keep the ordinary rank-dependent catch-up walk toward the
            # new raster slots (crew re-settle at varied rates), at the unit's normal speed. The
            # re-slotting is applied as a permutation into raster order. War machine crew always
            # take the FARTHEST unplaced model per slot; the machine's own front-rank centre slot is
            # filled directly (nearest fallback here); wagons use the ordinary nearest search.
            assignment = _slot_offsets(formation.reform_assignment(
                regiment.x, regiment.y, regiment.direction, regiment.models, ranks, positions,
                farthest=regiment.hud_class == "art" and self.phase != "deployment"))
            raster_index = {offset: index for index, offset in
                            enumerate(formation.block_slots(regiment.models, ranks))}
            order = sorted(range(len(assignment)), key=lambda i: raster_index[assignment[i]])
            regiment.positions = [positions[i] for i in order]
            regiment.melee_models = [regiment.melee_models[i] for i in order]
            regiment.reform_slots = []
            regiment.reforming = False
            return
        regiment.reform_slots = _slot_offsets(formation.reform_assignment(
            regiment.x, regiment.y, regiment.direction, regiment.models, ranks, positions))
        regiment.reforming = bool(regiment.reform_slots)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Per-regiment state for `whshr.battle_log` (a segment snapshot or the final battle state):
        position, facing, models, corpse count, and every order/engagement flag needed to trace a
        regiment's behaviour without re-deriving it from the tick-by-tick event log."""
        return {
            identifier: {
                "x": regiment.x, "y": regiment.y, "direction": regiment.direction,
                "models": regiment.models, "corpses": len(regiment.corpses),
                "ranks": regiment.ranks, "independent": regiment.independent,
                "hidden": regiment.hidden, "waypoints": [list(point) for point in regiment.waypoints],
                "walking": regiment.walking, "routing": regiment.routing, "fled": regiment.fled,
                "in_melee": regiment.in_melee, "melee_group": regiment.melee_group,
                "reforming": regiment.reforming,
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

    def regiment_at(self, x: float, y: float, player_only: bool = True) -> str | None:
        """Identifier of the regiment whose footprint contains (x, y), or None; the closest one if several."""
        best_id: str | None = None
        best_distance: float | None = None
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

    def set_view_angle(self, angle: float) -> None:
        """Record the camera rotation (1/512 turns). Wagons re-snap their facing to the nearest 45 degree
        step of a grid offset by the camera's position in its 45 degree sector, only when it changed
        (game_rules.md "Turning, wheeling and reversing")."""
        angle = angle % formation.FULL_TURN
        self.view_angle = angle
        if angle == self._snapped_view_angle:
            return
        self._snapped_view_angle = angle
        for regiment in self.regiments.values():
            if regiment.is_wagon:
                regiment.direction = snap_facing_to_view(regiment.direction, angle)

    def tick(self, seconds: float = TICK_SECONDS) -> None:
        if seconds <= 0:
            raise ValueError("tick duration must be positive")
        self.events = []
        self.update_count += 1
        if self.paused:
            return
        if self.result is not None:
            self.tick_count += 1
            return
        scale = seconds / TICK_SECONDS
        if self.phase == "battle":
            self.refresh_visibility()
        # Run behaviour scripts via the bytecode interpreter (issue #3); a mission-less/synthetic
        # battle has no interpreter and so no automatic orders (only explicit Battle.order_* calls).
        if self.interpreter:
            for unit_id, state in self.event_bus.unit_states.items():
                self.interpreter.run(unit_id, state, self.update_count - 1, self.rng)
            if self.phase == "battle":
                self.interpreter.raise_charge_events()
        for regiment in self.regiments.values():
            state = self.event_bus.unit_states.get(regiment.identifier)
            if (self.phase == "battle" and regiment.waypoints
                    and not (state and state.waiting_for_start)
                    and regiment.target_x is None):
                regiment.target_x, regiment.target_y = regiment.waypoints[0]
        if self.phase == "deployment":
            self._step_deployment_drag()
            self._advance_regiments(scale, seconds)
            return
        combat.refresh_melee_state(self)
        self._advance_regiments(scale, seconds)
        self._resolve_collisions()
        self._check_flight_edges()
        combat.resolve_contacts(self)
        combat.refresh_braced_state(self)
        if self.tick_count % combat.SEGMENT_TICKS == 0:
            combat.resolve_melee(self)
            combat.resolve_contact_attacks(self)  # game_rules.md 7.7, once per segment
            combat.resolve_rally(self)
        combat.resolve_shooting(self)
        self._update_result()
        self.tick_count += 1

    def _advance_regiments(self, scale: float, seconds: float) -> None:
        for regiment in self.regiments.values():
            self._step_burning(regiment)
            self._step_dying(regiment)
            if not regiment.active:
                regiment.walking = False
                continue
            regiment.model_positions()  # seed positions at the current anchor/facing before it moves
            state = self.event_bus.unit_states.get(regiment.identifier)
            if state is not None and state.waiting_for_start:
                if regiment.reforming:
                    self._advance_reforming_models(regiment, scale)
                else:
                    self._advance_models(regiment, scale)
                self._step_animations(regiment)
                continue
            if regiment.anchored and not regiment.routing:
                # An anchored war machine never starts a move or charge, from whatever source.
                regiment.target_x = regiment.target_y = None
                regiment.attack_target = None
            if regiment.attack_target is None:
                regiment.charge_started_target = None
            moved = False
            # game_rules.md "Formation changes": "the unit's own translation speed is halved for as
            # long as the re-form is in progress".
            move_scale = scale * (0.5 if regiment.reforming else 1.0)
            if regiment.in_melee:
                regiment.turn_order_key = regiment.turn_mode = None
                pass  # frozen in place while fighting; the view shows the attack animation instead
            elif regiment.routing:
                if regiment.flight_complete:
                    if regiment.reforming:
                        self._advance_reforming_models(regiment, scale)
                    else:
                        self._advance_models(regiment, scale)
                    if (self.tick_count > regiment.flight_complete_tick
                            and all(model.at_rest for model in regiment.melee_models)):
                        regiment.fled = True
                        self.events.append(BattleEvent(
                            f"{regiment.name} routs off the battlefield.", "fled",
                            regiment=regiment.identifier, x=regiment.x, y=regiment.y,
                            width=self.width, height=self.height))
                    continue
                if regiment.flee_x is None or regiment.flee_y is None:  # self-heal: should only happen for pre-existing state
                    regiment.flee_x, regiment.flee_y = self.flee_point(regiment)
                moved = self._advance_toward(regiment, (regiment.flee_x, regiment.flee_y),
                                             regiment.speed_for_mode(FLEEING_K) * move_scale, arrive=False,
                                             order_key=("flee",), scale=scale)
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
                                                 regiment.speed_for_mode(CHARGING_K) * move_scale, arrive=False,
                                                 order_key=("charge", target.identifier), scale=scale)
            elif regiment.target_x is not None and regiment.target_y is not None:
                moved = self._advance_toward(regiment, (regiment.target_x, regiment.target_y),
                                             regiment.speed_per_tick * move_scale,
                                             arrive=not regiment.route_follows_unit or bool(regiment.waypoints),
                                             order_key=("move", regiment.target_x, regiment.target_y), scale=scale)
                if not regiment.moving and regiment.waypoints:
                    regiment.waypoints.pop(0)
            elif regiment.turn_order_key is not None and regiment.turn_order_key[0] == "turn":
                # Standalone turn order (game_rules.md "Turning, wheeling and reversing"): speed zero,
                # shift 8; pivot about the inner front corner like all other gradual turns.
                self._step_turn(regiment, scale)
                if regiment.turn_mode is None:
                    regiment.turn_order_key = None
            else:
                regiment.turn_order_key = regiment.turn_mode = None
            if regiment.attack_target is None and not regiment.in_melee:
                for model in regiment.melee_models:
                    model.freeze_ticks = 0
            if regiment.reforming:
                models_catching_up = self._advance_reforming_models(regiment, scale)
            else:
                models_catching_up = self._advance_models(regiment, scale)
            regiment.walking = moved or models_catching_up
            self._step_animations(regiment)

    @staticmethod
    def turn_to(regiment: Regiment, direction: float) -> None:
        """Change a regiment's facing, moving its anchor so the turn pivots about the block centre.

        game_rules.md, "A turn always moves the unit position to keep the pivot still": the original
        displaces the unit position on every in-place turn so that the block centre -- which is what
        the collision footprint is built around -- does not move. Turning the anchor in place instead
        swings the footprint away and can break a contact that should have held.
        """
        if direction == regiment.direction or regiment.anchored:
            return
        shift_x, shift_y = formation.turn_pivot_shift(
            regiment.direction, direction, regiment.models, regiment.ranks)
        regiment.direction = direction
        regiment.x += shift_x
        regiment.y += shift_y

    @staticmethod
    def _turn_delta(direction: float, goal: float) -> float:
        """Signed shortest turn in 1/512-turn units."""
        return (goal - direction + 256) % 512 - 256

    @staticmethod
    def _snap_order_turn(regiment: Regiment, goal: float) -> None:
        """Apply the one-time 90/180-degree snap on a new movement order."""
        if regiment.turns_on_the_spot:
            return
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
    def _plan_turn(regiment: Regiment, goal: float, charge: bool = False) -> None:
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
    def _step_turn(regiment: Regiment, scale: float) -> str | None:
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
        if not regiment.turns_on_the_spot:
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

    def _advance_toward(self, regiment: Regiment, target: Point, step: float, arrive: bool, order_key: TurnKey,
                        scale: float) -> bool:
        """Turn toward a target over time, then advance along the current facing.

        With `arrive=True` (an ordinary move order) reaching the target clears it, matching the
        original "moving freely" order completion. With `arrive=False` (a charge chase or a rout) the
        regiment keeps closing on a moving point every tick and never "arrives" on its own; contact
        detection (`combat.resolve_contacts`) or leaving the field ends the movement instead.
        """
        steering_target = self._steering_target(regiment, target, order_key)
        if steering_target is None:
            regiment.target_x = regiment.target_y = None
            regiment.waypoints.clear()
            regiment.attack_target = regiment.charge_started_target = None
            regiment.avoid_target = regiment.avoid_key = None
            return False
        dx, dy = steering_target[0] - regiment.x, steering_target[1] - regiment.y
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
        if regiment.turns_on_the_spot:
            pass  # no speed penalty: translates at full speed while turning
        elif mode == "wheel":
            step /= 2
        elif mode is not None and mode != "charge_reaim":
            step = 0  # a charge re-aim keeps full anchor speed (game_rules.md, model_movement.md)
        if step <= 0:
            return mode is not None
        if arrive and steering_target == target and distance <= step and abs(self._turn_delta(regiment.direction, goal)) <= 10:
            regiment.x, regiment.y = target
            regiment.target_x = regiment.target_y = None
            return False
        angle = regiment.direction * math.tau / formation.FULL_TURN
        regiment.x += math.sin(angle) * min(step, distance)
        regiment.y += math.cos(angle) * min(step, distance)
        return True

    def _steering_target(self, regiment: Regiment, target: Point, order_key: TurnKey) -> Point | None:
        if order_key[0] == "flee":
            return target
        start = self.formation_centre(regiment)
        if math.dist(start, target) < 1e-9:
            return target
        obstacles: list[tuple[str, Point, float]] = []
        for index, obj in enumerate(self.objects):
            flags = {str(flag).casefold() for flag in obj.get("status") or ()}
            if {"os_active", "os_solid"}.issubset(flags):
                obstacles.append((f"object:{index}",
                                  (float(obj.get("x") or 0), float(obj.get("y") or 0)),
                                  float(obj.get("radius") or 0)))
        for other in self.regiments.values():
            if other is regiment or not other.active or (order_key[0] == "charge" and
                                                        order_key[1] == other.identifier):
                continue
            obstacles.append((f"unit:{other.identifier}", self.formation_centre(other),
                              other.bounding_radius()))
        obstacle = self._first_route_obstacle(start, target, obstacles, regiment.bounding_radius())
        if obstacle is None:
            regiment.avoid_target = regiment.avoid_key = None
            return target
        key, _, _ = obstacle
        if regiment.avoid_key != (order_key[0], key) or regiment.avoid_target is None:
            best_score = math.inf
            best_point: Point | None = None
            for side in (-1, 1):
                score, point = self._score_detour(start, target, regiment.direction,
                                                  obstacle, side, obstacles, regiment.bounding_radius())
                if score <= best_score:  # exact tie keeps the second side tested
                    best_score, best_point = score, point
            if best_score >= 12000 or best_point is None:
                return None
            regiment.avoid_target = best_point
            regiment.avoid_key = order_key[0], key
        if math.dist(start, regiment.avoid_target) <= max(regiment.speed_per_tick, 3):
            regiment.avoid_target = regiment.avoid_key = None
            return target
        return regiment.avoid_target

    @staticmethod
    def _first_route_obstacle(start: Point, target: Point,
                              obstacles: Sequence[tuple[str, Point, float]], own_radius: float
                              ) -> tuple[str, Point, float] | None:
        dx, dy = target[0] - start[0], target[1] - start[1]
        length2 = dx * dx + dy * dy
        if length2 < 1e-9:
            return None
        # Object order wins over geometric nearness, as in the public movement report.
        for key, centre, radius in obstacles:
            radius += own_radius
            if radius <= 0:
                continue
            t = ((centre[0] - start[0]) * dx + (centre[1] - start[1]) * dy) / length2
            if 0 < t < 1 and math.hypot(start[0] + t * dx - centre[0],
                                        start[1] + t * dy - centre[1]) < radius:
                return key, centre, radius
        return None

    def _score_detour(self, start: Point, target: Point, facing: float,
                      obstacle: tuple[str, Point, float], side: int,
                      obstacles: Sequence[tuple[str, Point, float]], own_radius: float
                      ) -> tuple[float, Point]:
        current = start
        score = 0.0
        first_point = start
        seen: set[str] = set()
        for _ in range(12):
            key, centre, radius = obstacle
            if key in seen:
                break
            seen.add(key)
            dx, dy = target[0] - current[0], target[1] - current[1]
            length = math.hypot(dx, dy)
            if length < 1e-9:
                break
            ux, uy = dx / length, dy / length
            separation = math.dist(current, centre)
            # Offset enough that the connector from the current position clears
            # the footprint circle, including when it is close to the mover.
            offset = (radius * separation / math.sqrt(separation * separation - radius * radius) + 3
                      if separation > radius + 1e-9 else radius + 8)
            point = (centre[0] - side * uy * offset, centre[1] + side * ux * offset)
            if first_point == start:
                first_point = point
            heading = round(math.atan2(point[0] - current[0], point[1] - current[1])
                            * 512 / math.tau) % 512
            score += 4 * abs(self._turn_delta(facing, heading)) + math.dist(current, point)
            if any(boundary.forbidden(point) or
                   navigation.first_crossing(current, point, [boundary]) is not None
                   for boundary in self.navigation_boundaries
                   if boundary.solid or boundary.inverse or boundary.battle_edge):
                score += 12000
                break
            current, facing = point, heading
            if score > 5999:
                break
            next_obstacle = self._first_route_obstacle(current, target, obstacles, own_radius)
            if next_obstacle is None:
                break
            obstacle = next_obstacle
        score += math.dist(current, target)
        if any(boundary.forbidden(target) or
               navigation.first_crossing(current, target, [boundary]) is not None
               for boundary in self.navigation_boundaries
               if boundary.solid or boundary.inverse or boundary.battle_edge):
            score += 12000
        return score, first_point

    def nearest_enemy(self, regiment: Regiment) -> Regiment | None:
        """The nearest active regiment of a *different* side, whatever it is (used for a rout's flee
        bearing and rally's "enemy nearby" check): the opponent to flee from is whoever `regiment` is
        actually engaged with, not restricted to `rules.hostile_sides`' default hostility, which only
        gates unprompted/autonomous targeting (`whshr.combat._shooting_target`)."""
        enemies = [r for r in self.regiments.values() if r.side != regiment.side and r.active]
        if not enemies:
            return None
        return min(enemies, key=lambda e: math.hypot(e.x - regiment.x, e.y - regiment.y))

    def flee_point(self, regiment: Regiment) -> Point:
        """A point far away on the bearing directly away from the nearest enemy (game_rules.md, "Flight":
        "starts the flight directly away from its opponent"), or along the current facing if none remain."""
        enemy = self.nearest_enemy(regiment)
        if enemy is not None:
            dx, dy = regiment.x - enemy.x, regiment.y - enemy.y
            distance = math.hypot(dx, dy)
            if distance > 1e-6:
                return regiment.x + dx / distance * 1e4, regiment.y + dy / distance * 1e4
        angle = regiment.direction * math.tau / formation.FULL_TURN
        return regiment.x + math.sin(angle) * 1e4, regiment.y + math.cos(angle) * 1e4

    def _advance_models(self, regiment: Regiment, scale: float) -> bool:
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
        updated: list[Point] = []
        still_moving = False
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
            # A scattered model walks to its own destination, not its slot (notes/scatter_models_to_node.md:
            # the regiment position and slots do not change), unless the regiment has an order of its own.
            busy = regiment.in_melee or regiment.routing or regiment.attack_target or regiment.moving
            scatter = model.scatter_target if not busy else None
            tx, ty = cell if cell is not None else scatter if scatter is not None else slot
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

    @staticmethod
    def _swap_partner(positions: Sequence[Point], targets: Sequence[Point], index: int, nx: float, ny: float,
                      ux: float, uy: float) -> int | None:
        """Index of an at-rest comrade (within its arrival distance of its own target) that the model
        stepping to (nx, ny) along unit direction (ux, uy) would land on -- about half a model spacing
        away -- while heading into it; None if there is none."""
        reach = formation.MODEL_SPACING / 2
        for other, (ox, oy) in enumerate(positions):
            if other == index:
                continue
            if math.hypot(targets[other][0] - ox, targets[other][1] - oy) > MODEL_ARRIVAL_DISTANCE:
                continue
            if math.hypot(ox - nx, oy - ny) <= reach and (ox - nx) * ux + (oy - ny) * uy > 0:
                return other
        return None

    def _advance_reforming_models(self, regiment: Regiment, scale: float) -> bool:
        """Drive a re-forming unit's models with the flat re-form mover instead of the ordinary
        rank-dependent catch-up walk (game_rules.md, "Formation changes: how the figures re-sort
        themselves"): a flat `s_rlmv / 8` world units/tick, no ramp-up, decelerating in the last
        `REFORM_DECEL_DISTANCE` world units (the step divided by `7 - distance`) and capped at
        `REFORM_STEP_CAP` world units/tick. A model's heading snaps to the unit's facing as soon as it
        settles into its slot. Clears `regiment.reforming` and raises a "re-form complete" event once
        the last model settles.
        """
        targets = formation.place(regiment.x, regiment.y, regiment.direction, regiment.reform_slots)
        facing_angle = regiment.direction * math.tau / formation.FULL_TURN
        facing_x, facing_y = math.sin(facing_angle), math.cos(facing_angle)
        step_base = regiment.speed_per_tick * 16 / MOVING_FREELY_K / 8 * scale
        targets = list(targets)
        current = list(regiment.positions)
        all_settled = True
        for index in range(len(current)):
            px, py = current[index]
            tx, ty = targets[index]
            model = regiment.melee_models[index]
            dx, dy = tx - px, ty - py
            distance = math.hypot(dx, dy)
            if distance <= MODEL_ARRIVAL_DISTANCE:
                model.at_rest = True
                model.current_speed = model.distance_budget = 0.0
                model.heading_x, model.heading_y = facing_x, facing_y
                current[index] = (tx, ty)
                continue
            all_settled = False
            step = step_base / (7 - distance) if distance <= REFORM_DECEL_DISTANCE else step_base
            step = min(step, REFORM_STEP_CAP * scale, distance)
            nx, ny = px + dx / distance * step, py + dy / distance * step
            # game_rules.md "Formation changes" point 3: stepping onto an at-rest comrade about half a
            # spacing away, heading into it, exchanges the two slot assignments (the walker inherits
            # the comrade's place and stops; the comrade wakes and walks to the walker's old slot).
            other = self._swap_partner(current, targets, index, nx, ny, dx / distance, dy / distance)
            if other is not None:
                slots = regiment.reform_slots
                slots[index], slots[other] = slots[other], slots[index]
                targets[index], targets[other] = targets[other], targets[index]
                regiment.melee_models[other].at_rest = False
                model.at_rest = True
                model.current_speed = model.distance_budget = 0.0
                continue
            model.at_rest = False
            current[index] = (nx, ny)
        updated = current
        regiment.positions = updated
        if all_settled:
            # The rest of the engine (`_advance_models`, `model_positions`) assumes `positions[i]`
            # belongs to `formation.block_slots`'s raster slot `i`; restore that ordering now that the
            # re-slotting permutation has done its job, or the very next tick's ordinary catch-up walk
            # would immediately send every model chasing a different slot again.
            raster_index = {offset: index for index, offset in
                            enumerate(formation.block_slots(regiment.models, regiment.ranks))}
            order = sorted(range(len(regiment.reform_slots)), key=lambda i: raster_index[regiment.reform_slots[i]])
            regiment.positions = [regiment.positions[i] for i in order]
            regiment.melee_models = [regiment.melee_models[i] for i in order]
            regiment.reforming = False
            regiment.reform_slots = []
            self.events.append(BattleEvent(
                f"{regiment.name} completes its re-form.", "reform_complete",
                regiment=regiment.identifier))
        return not all_settled

    def _step_dying(self, regiment: Regiment) -> None:
        """Count down each dying model's collapse delay, then lay it down as a corpse with a random
        facing (game_rules.md "Figure animation", mechanism 5)."""
        for dying in list(regiment.dying):
            dying.ticks_left -= 1
            if dying.ticks_left > 0:
                animation.step(dying.model, dying.model.action, self.rng, regiment.animation_family)
                continue
            regiment.dying.remove(dying)
            if dying.burns:
                # Fire/warpfire kills leave the roster's animation and burn as a free figure first.
                regiment.burning.append(animation.BurningModel(
                    dying.x, dying.y, dying.death_kind, dying.body, animation.burn_start(dying.body, self.rng)))
                continue
            animation.step(dying.model, animation.DEAD, self.rng, regiment.animation_family)
            regiment.corpses.append((dying.x, dying.y, self.rng.randrange(animation.FULL_TURN)))

    def _step_burning(self, regiment: Regiment) -> None:
        """Age each burning model; when its burn ends it becomes a charred corpse with a random facing,
        held forever (game_rules.md "Figure animation", burn sequences)."""
        for burning in list(regiment.burning):
            burning.age += 1
            if animation.burn_finished(burning):
                regiment.burning.remove(burning)
                regiment.charred.append((burning.x, burning.y, self.rng.randrange(animation.FULL_TURN),
                                         burning.body))

    def _drawn_facing_target(self, regiment: Regiment, model: ModelState) -> float:
        """Facing a model's drawn direction turns toward: the unit's for stand/weapon-ready/shoot, its own
        heading (or its opponent) for walk/fight."""
        if animation.facing_follows_unit(model.action):
            return regiment.direction
        if model.action == animation.FIGHT and model.opponent is not None:
            other = self.regiments.get(model.opponent[0])
            index = other.index_of(model.opponent[1]) if other is not None else None
            index_self = regiment.index_of(model.uid)
            if other is not None and index is not None and index_self is not None and index < len(other.positions):
                dx = other.positions[index][0] - regiment.positions[index_self][0]
                dy = other.positions[index][1] - regiment.positions[index_self][1]
                if dx or dy:
                    return round(math.atan2(dx, dy) * formation.FULL_TURN / math.tau) % formation.FULL_TURN
        if model.heading_x or model.heading_y:
            return round(math.atan2(model.heading_x, model.heading_y)
                         * formation.FULL_TURN / math.tau) % formation.FULL_TURN
        return regiment.direction

    def _step_animations(self, regiment: Regiment) -> None:
        """Step every model's action program one battle tick (whshr.animation, game_rules.md "Figure
        animation"). The requested action mirrors what the model is currently doing: fighting or
        weapon-ready in melee (paired with an opponent or not), the shoot pose while the regiment
        holds a missile stance and is not still reloading, walking while the model itself has not
        yet reached its slot (`ModelState.at_rest`), otherwise idling in place. Then the drawn
        facing slews toward its action-dependent target (wagons snap; a facing-locked script
        freezes it).

        Holding the shoot pose off until `reload_ticks <= 1` (one tick before the next volley is
        ordered in `combat.resolve_shooting`, which runs after this method within the same tick)
        keeps every model entering the shoot program on the same tick, so the whole regiment's fire
        events land inside the next countdown's resolve window; without the gate models free-run
        the shoot/stand cycle and drift out of step with the countdown across reloads."""
        wagon = regiment.unit_class == 7 and regiment.models == 2
        # Advance the volley age counter; the window is clamped at 6 ticks so the second SHOOT
        # animation cycle (which starts on tick 7 from the order) cannot contaminate this volley.
        if regiment.volley_countdown is not None:
            regiment.volley_age += 1
            if regiment.volley_age >= 6:
                regiment.volley_countdown = None
        volley_divisor = 1 if regiment.hud_class == "art" else 4
        for model in regiment.melee_models:
            if regiment.in_melee:
                requested = animation.FIGHT if model.opponent is not None else animation.WEAPON_READY
            elif regiment.missile_range and not regiment.moving and not regiment.attack_target \
                    and regiment.reload_ticks <= 1:
                requested = animation.SHOOT
            elif not model.at_rest:
                requested = animation.WALK
            else:
                requested = animation.IDLE
            animation.step(model, requested, self.rng, regiment.animation_family)
            self._slew_drawn_facing(regiment, model, wagon)
            # Each model's fire event decrements the volley countdown once; a post is issued each
            # time the new countdown value is a multiple of the divisor (game_rules.md 8.1).
            # Reload does not gate this: it was stamped at order time, so reload > 0 is normal
            # mid-volley. The countdown > 0 guard prevents second-cycle decrements.
            if model.fire_event and regiment.volley_countdown is not None and regiment.volley_countdown > 0:
                regiment.volley_countdown -= 1
                if regiment.volley_countdown % volley_divisor == 0:
                    regiment.fire_posts += 1
                if regiment.volley_countdown == 0:
                    regiment.volley_countdown = None

    def _slew_drawn_facing(self, regiment: Regiment, model: ModelState, wagon: bool = False) -> None:
        if animation.family_table(regiment.animation_family)[model.action].locks_facing:
            return
        target = self._drawn_facing_target(regiment, model)
        model.drawn_facing = target if wagon else animation.slew_facing(model.drawn_facing, target)

    def side_counts(self) -> dict[str, dict[str, int]]:
        """Per-side active/routing/fled/destroyed regiment counts (whshr.battle_log snapshots, and the
        diagnosis for "defeat never triggered": every result check's inputs are visible here)."""
        counts: dict[str, dict[str, int]] = {}
        for side in Side:
            if side is Side.DUEL:
                continue  # a melee camp, not a side (rules.Side.DUEL)
            regiments = [r for r in self.regiments.values() if r.side == side]
            counts[side.value] = {
                "active": sum(1 for r in regiments if r.active),
                "routing": sum(1 for r in regiments if r.routing and r.active),
                "fled": sum(1 for r in regiments if r.fled),
                "destroyed": sum(1 for r in regiments if r.destroyed),
                "total": len(regiments),
            }
        return counts

    def _update_result(self) -> None:
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

    def _resolve_collisions(self, deployment_id: str | None = None) -> None:
        """Push regiments under orders out of the regiments they overlap (a simplified push-apart;
        game_rules.md, "Routes, collisions and visibility"), not the polygon obstruction routing (`Nav*`).

        Standing regiments never give way, so scripted deployments that already overlap (BF001's Grudgebringer
        cavalry and infantry) stay where the script placed them. Pairs are visited in identifier order.
        """
        regiments = [self.regiments[key] for key in sorted(self.regiments) if self.regiments[key].active]
        if deployment_id is None:
            for regiment in regiments:
                self._correct_boundaries(regiment)
                self._correct_solid_objects(regiment)
        for i, first in enumerate(regiments):
            for second in regiments[i + 1:]:
                if first.in_melee or second.in_melee:
                    continue
                if may_engage(first, second) and deployment_id is None:
                    # A pair that can actually fight never pushes apart: a charging regiment must be
                    # free to close all the way to footprint contact (combat.resolve_contacts), not
                    # stop at circle distance (see combat.resolve_contacts: contact needs real
                    # overlap). A pair that can never fight (same side, or the Player-Neutral
                    # exception rules.can_fight documents) still pushes apart like same-side
                    # regiments always did, so e.g. peasants don't sit interpenetrating the player.
                    continue
                first_yields = (first.identifier == deployment_id if deployment_id is not None else
                                first.moving or first.routing or first.attack_target is not None)
                second_yields = (second.identifier == deployment_id if deployment_id is not None else
                                 second.moving or second.routing or second.attack_target is not None)
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

    def _correct_boundaries(self, regiment: Regiment) -> None:
        for boundary in self.navigation_boundaries:
            if not (boundary.solid or boundary.inverse or boundary.battle_edge):
                continue
            if regiment.routing and boundary.battle_edge:
                continue
            centre = self.formation_centre(regiment)
            if not boundary.forbidden(centre):
                continue
            nearest = boundary.nearest(centre)
            dx = math.trunc((nearest[0] - centre[0]) / 2)
            dy = math.trunc((nearest[1] - centre[1]) / 2)
            regiment.x += dx
            regiment.y += dy
            regiment.positions = [(x + dx, y + dy) for x, y in regiment.positions]
            if boundary.battle_edge and regiment.attack_target is not None:
                regiment.attack_target = regiment.charge_started_target = None
                regiment.turn_order_key = None
                self.events.append(BattleEvent(
                    f"{regiment.name}'s charge ends at the table edge.", "charge_end",
                    regiment=regiment.identifier))

    def _correct_solid_objects(self, regiment: Regiment) -> None:
        centre = self.formation_centre(regiment)
        for obj in self.objects:
            flags = {str(flag).casefold() for flag in obj.get("status") or ()}
            if not {"os_active", "os_solid"}.issubset(flags):
                continue
            ox, oy = float(obj.get("x") or 0), float(obj.get("y") or 0)
            radius = float(obj.get("radius") or 0) + regiment.bounding_radius()
            dx, dy = centre[0] - ox, centre[1] - oy
            distance = math.hypot(dx, dy)
            if distance >= radius or radius <= 0:
                continue
            ux, uy = (dx / distance, dy / distance) if distance > 1e-9 else (1.0, 0.0)
            push = radius - distance
            shift_x, shift_y = ux * push, uy * push
            regiment.x += shift_x
            regiment.y += shift_y
            regiment.positions = [(x + shift_x, y + shift_y) for x, y in regiment.positions]
            centre = centre[0] + shift_x, centre[1] + shift_y

    def _check_flight_edges(self) -> None:
        edges = [boundary for boundary in self.navigation_boundaries if boundary.battle_edge]
        for regiment in self.regiments.values():
            if not regiment.active or not regiment.routing or regiment.flight_complete:
                continue
            if regiment.flight_check_ticks > 0:
                regiment.flight_check_ticks -= 1
                continue
            regiment.flight_check_ticks = math.floor(regiment.bounding_radius() / 2)
            outside = not any(edge.contains((regiment.x, regiment.y)) for edge in edges)
            if not outside:
                continue
            if not regiment.flight_departed:
                regiment.flight_departed = True
                for other in self.regiments.values():
                    if other.identifier == regiment.identifier:
                        continue
                    if other.attack_target == regiment.identifier:
                        other.attack_target = other.charge_started_target = None
                    state = self.event_bus.unit_states.get(other.identifier)
                    if state is not None and state.current_target and state.current_target[0] == regiment.identifier:
                        state.current_target = None
                    self.event_bus.queue_event(other.identifier, interpreter.Event(code=0x0E,
                                                                                source=regiment.identifier))
                self.events.append(BattleEvent(f"{regiment.name} leaves the table.", "flight_departure",
                                               regiment=regiment.identifier))
            dx = (regiment.flee_x if regiment.flee_x is not None else regiment.x) - regiment.x
            dy = (regiment.flee_y if regiment.flee_y is not None else regiment.y) - regiment.y
            heading = math.atan2(dx, dy)
            radius = regiment.bounding_radius()
            trailing = (regiment.x - math.sin(heading) * radius,
                        regiment.y - math.cos(heading) * radius)
            if not any(edge.contains(trailing) for edge in edges):
                regiment.flight_complete = True
                regiment.flight_complete_tick = self.tick_count
                regiment.rally_next_segment = None
