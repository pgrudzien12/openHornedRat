"""Deterministic battle-state primitives shared by prototype frontends."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
import random
from typing import Any, Callable, Literal

from . import animation, battle_grid, behaviour, buildings, combat, deployment, formation, interpreter, navigation, ranged, visibility
from . import magic, objectives as objective_table, spell_effects, steering
from . import nodes as node_table
from .battle_events import BattleEvent
from .battle_log import BattleLogger
from .portrait_popup import PortraitPopup
from .rules import (EXPECTED_ARMOUR_SAVE, EXPECTED_WEAPON_BONUS, MISSILE_RANGES, MOUNT_PROFILES, Side, can_fight, may_engage, side_of_code,
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
# notes/reform_while_moving.md 3: the shuffle re-form step is `s_rlmv / 8` with no cap; only inside the last
# 6 world units is it divided by `7 - d` and then each axis component capped at 1 world unit.
REFORM_DECEL_DISTANCE = 6
REFORM_STEP_CAP = 1.0
# Ordinary missile codes from the public ranged handoff; innate attacks use a separate effect pool.
ARCHER_MISSILE_CODES = {1, 2, 5, 6, 7, 8, 9, 11, 12, 17, 18, 19}
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
    wounds_taken: int = 0
    # The unit credited with this model when it leaves its regiment, killed or removed alive (identifier, or None):
    # notes/casualty_bookkeeping.md 2.0-2.1.
    credit: str | None = None
    # The model's own pending action request (0 = none), consumed at its next update; it beats the
    # unit's broadcast for that tick (notes/script_animation_sound.md, 0.2).
    own_request: int = 0
    # ScatterModelsToNode destination this model walks to instead of its formation slot, or None while
    # in formation (notes/scatter_models_to_node.md); cleared by SnapModelsToFormation.
    scatter_target: Point | None = None
    # Shuffle re-form mover state (notes/reform_while_moving.md 3): the per-tick step chosen at the last re-aim
    # (None = re-aim on the next step) and the countdown to the next re-aim.
    reform_step: Point | None = None
    reaim_countdown: float = 0.0


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
    # The collision pass runs for a unit only while this is on (notes/script_behaviours.md 2.1): set by its own
    # position step, a boundary repel, another unit's pass touching or pushing it, the contact handler's
    # latch-release branches and Rally; cleared when its pass runs. Not set by turning in place or re-forming.
    collision_recheck: bool = False
    contact_attack_segment: int = -1  # the segment in which this unit last made contact attacks on a router underfoot
    update_counter: int = 0  # counts the unit's updates; starts at its slot so units are staggered (see collision_recheck)
    screen_mark: bool = False  # inside the camera's view rectangle at the end of the last tick (Battle.on_screen)
    airborne: bool = False
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
    race: int | None = None  # s_race & 7: 0 Human, 1 Elven, 2 Dwarven, 3 Goblinoid, 4 Orc, 5 Skaven, 6 Peasant, 7 big
    points: int = 0  # s_pntval: experience gained by the killer, and the AI's per-model worth unit
    # (game_rules.md: unit worth = size x s_pntval x 12 artillery / 8 wizard / 4 monster / 1)
    # This battle's s_kills and s_Exp gain: one kill and the victim unit's `points` per model credited to this unit
    # when it leaves its regiment (notes/casualty_bookkeeping.md 2.0).
    kills: int = 0
    experience_gained: int = 0
    # set:whoami as one byte: the persistent campaign regiment id (0 for ordinary mission units),
    # addressed by SendEventToUnitId (notes/threat_events_nodes.md, part B 0.1).
    whoami: int = 0
    has_leader: bool = False  # the .BTS unit has a leader (character) block: PlayLeaderAnimation's model
    leader_uid: int | None = None  # stable figure identity; never replaced after its death
    leader_ws: int | None = None
    leader_strength: int | None = None
    leader_attacks: int | None = None
    leader_toughness: int | None = None
    leader_wounds: int | None = None
    leader_armour: int | None = None
    leader_leadership: int | None = None
    spells: tuple[int, ...] = ()  # spell codes from the unit's addspell: lines, in file order (whshr.magic)
    items: tuple[str, ...] = ()  # magic items in its 5 slots, loaded ones first (notes/battle_end_objectives.md 12.2)
    used_items: set[str] = field(default_factory=set[str])  # battle-only activation state
    potion_strength: bool = False
    # The missile code "Who shoots" reads (game_rules.md): Archers their own S_BalWeap, Artillery the leader's,
    # others the leader's if non-zero, else their own; None without one. Read by IsSpecialShooter.
    shooting_code: int | None = None
    # A script's action broadcast (SetActionState/PlayUnitAnimation; 0 = none) and the unit's activity
    # when it was made: it sticks until the unit's next state change (notes/script_animation_sound.md, 0.1).
    script_action: int = 0
    script_action_key: tuple[bool, ...] | None = None

    # Combat/order state (whshr.combat).
    attack_target: str | None = None  # identifier of an enemy regiment this regiment is approaching or charging
    charge_started_target: str | None = None  # target whose current charge already froze its models
    assaulting_building: str | None = None  # identifier of the building this regiment is fighting (whshr.buildings)
    free_charging: bool = False  # straight-ahead ChargeForward until its point is reached or contact ends it
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
    fight_harder: bool = False  # player melee command; expires after the next combat segment
    # Set (to `Side.DUEL`) only while this regiment is fighting a same-side regiment its script named as
    # its opponent; see `rules.may_engage`. Cleared whenever it leaves its fight.
    melee_camp: Side | None = None
    melee_group: str | None = None  # id of the shared multi-regiment fight (Battle.fights), if any
    melee_touching: frozenset[str] = field(default_factory=frozenset[str])  # enemy ids this footprint touches now
    held: bool = False  # held by a Tangling Thorn (whshr.spell_effects, notes/spell_area_effects.md 3.3)
    # In a Flying Bower flight or inside a Sapphire Arch: not drawn, cannot engage or be engaged
    # (notes/spell_channelled_effects.md 2.3, 3.2); set by whshr.spell_effects.
    lifted: bool = False
    # game_rules.md "Formation changes": true while models are still walking to their newly assigned
    # slots after a re-form; `reform_slots` holds each model's assigned local (side, forward) offset,
    # index-parallel with `positions`/`melee_models`, turned into a world target every tick with
    # `formation.place` so it tracks a moving or turning anchor.
    reforming: bool = False
    anchor_cleared: bool = False  # set by `clear_anchor` (artillery misfire); see `anchored`
    reform_slots: list[Point] = field(default_factory=list[Point])
    # notes/reform_while_moving.md 2: a Rally re-form uses walk-back mode (the ordinary catch-up walk, the unit's
    # speed not halved, arrival keeps the figure's heading) instead of the shuffle mover; it lasts until the
    # re-form ends, through any new layout given meanwhile (12, treated as persisting).
    reform_walk_back: bool = False
    # The facing the re-form layout was made at. Re-form slots stay at it while the re-form runs: only a pursuit
    # turns then, and it does not rotate the slots (notes/reform_while_moving.md 5).
    reform_facing: float = 0.0
    # notes/reform_while_moving.md 4: a player Move, Face point, Charge or Attack order given while re-forming is
    # held here as (Battle method name, *args) and applied on the first tick after the re-form ends.
    pending_order: tuple[Any, ...] | None = None
    # Ordinary-move planning (notes/movement_formation.md 1.4): countdown to the next plan, and whether the last
    # plan owed a turn (the next plan comes when it finishes).
    move_plan_countdown: float = -1.0
    move_turn_owed: bool = False
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
    avoid_target: Point | None = None  # the current live steer point, or None when heading straight for the waypoint
    # notes/obstacle_steering.md sections 4-6: the side the route plan chose (0 = none yet), kept for live steering,
    # and the (order, waypoint) the last plan was made for, so the plan runs only at an order or a new waypoint.
    route_side: int = 0
    # notes/pursuit_map_edge.md: chasing a routing unit (set when a fight's routed opponent is pursued). It is not a
    # charge: the edge correction only pushes a pursuer, and a segment check stops it. The chase budget and the last
    # measured distance follow game_rules.md "Pursuit".
    pursuing: bool = False
    pursuit_budget: int | None = None
    pursuit_distance: int = 0
    pursuit_point: Point | None = None  # the chase point set at the last segment tick (None until the first one)
    route_planned_for: tuple[TurnKey, Point] | None = None
    # notes/obstacle_steering.md section 5 ("On failure") and section 6: updates left in a route pause. While
    # positive the regiment keeps its order but does not advance along its move.
    route_pause_ticks: int = 0
    route_speed: float = 0.0  # anchor travel on the previous movement update; scattering models do not count
    fire_posts: int = 0  # fire events posted by this volley's shooters so far (consumed by combat)
    fire_post_positions: list[Point] = field(default_factory=list[Point])
    shooting_target: str | None = None
    shooting_object: int | None = None
    shooting_point: Point | None = None
    shooting_mode: str | None = None  # target, search, ground, or building
    volley_aim: Point | None = None
    machine_alive: bool = True
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
    # notes/pursuit_restraint.md 2: the rally-attempt state (player Rally order, or Independent at the rout) and the
    # scheduled segment number (10..1, counting down) of the next rally attempt / restraint test. The schedule is
    # shared by the flight rally attempts and the pursuit-restraint test; each rout or pursuit start overwrites it.
    rally_attempt: bool = False
    rally_segment: int | None = None
    rally_schedule_tick: int = -1  # the tick the schedule was set: no check on that same boundary tick

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
        """Friendly display preserves opposing visibility (notes/deployment.md §1.3); a lifted unit (Flying Bower,
        Sapphire Arch) is not drawn (notes/spell_channelled_effects.md 2.3)."""
        return not self.lifted and (self.side != Side.ENEMY or not self.hidden)

    @property
    def effective_leadership(self) -> int:
        return self.base_leadership + int(self.fight_harder)

    @property
    def base_leadership(self) -> int:
        """Use a living leader's nonzero Ld, else the regiment's Ld (game_rules.md 3)."""
        if self.leader_leadership and self.living_leader_index is not None:
            return self.leader_leadership
        return self.leadership

    @property
    def living_leader_index(self) -> int | None:
        self.model_positions()
        return self.index_of(self.leader_uid) if self.leader_uid is not None else None

    @property
    def displayed_leader_strength(self) -> int | None:
        if self.living_leader_index is None:
            return None
        return min(9, (self.leader_strength if self.leader_strength is not None else self.strength)
                   + int("ItemGrudgeBringer" in self.items) + int("ItemSwordOfMight" in self.items)
                   + 3 * int(self.potion_strength))

    def leader_model(self, model: ModelState) -> bool:
        return self.leader_uid is not None and model.uid == self.leader_uid

    def model_toughness(self, model: ModelState) -> int:
        return (self.leader_toughness if self.leader_model(model) and self.leader_toughness is not None
                else self.toughness)

    def model_wounds(self, model: ModelState) -> int:
        return (self.leader_wounds if self.leader_model(model) and self.leader_wounds is not None
                else self.wounds)

    def model_armour(self, model: ModelState) -> int:
        code = self.leader_armour if self.leader_model(model) and self.leader_armour is not None else self.armour
        if not self.leader_model(model):
            return code
        if "ItemArmourOfMeteoricIron" in self.items:
            code = 13
        for item in ("ItemShieldOfPtolos", "ItemArmourOfTheBeard"):
            if item in self.items and code + 1 < len(EXPECTED_ARMOUR_SAVE):
                if EXPECTED_ARMOUR_SAVE[code + 1] < EXPECTED_ARMOUR_SAVE[code]:
                    code += 1
        return code

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
        """Free an anchored war machine. The transitions that call this: an artillery misfire explosion
        (`ranged._destroy_machine`), the death of the machine's leader model (`combat.kill_models`) and a script
        that changes the unit's class away from Artillery (`SetClass`)."""
        self.anchor_cleared = True

    def clear_shooting(self) -> None:
        """Cancel a selected aim and any unposted pose events when another order replaces it."""
        self.shooting_target = self.shooting_point = self.shooting_mode = None
        self.shooting_object = None
        self.volley_countdown = None
        self.volley_age = 0
        self.fire_posts = 0
        self.fire_post_positions.clear()

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

    def activity_key(self) -> tuple[bool, ...]:
        """The states whose change makes the original re-request the figures' action (halt, move or
        turn start, charge, melee, rout, re-form; notes/script_animation_sound.md, 0.1)."""
        return (self.moving or bool(self.waypoints), self.turn_order_key is not None,
                self.attack_target is not None, self.in_melee, self.routing, self.reforming)

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

    def seeded_positions(self) -> list[Point]:
        """The per-model positions for display and logging, without ever seeding them (empty until the battle seeds
        the regiment). `model_positions` seeds lazily and draws from the battle-wide stagger sequence, so a viewer or
        logger calling it would change the battle and break replay."""
        if len(self.positions) != self.models or len(self.melee_models) != len(self.positions):
            return []
        return self.positions

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
            if self.has_leader and self.leader_uid is None and self.melee_models:
                centre = 0 if self.hud_class == "art" else (max(1, self.front_rank_models()) - 1) // 2
                self.leader_uid = self.melee_models[centre].uid
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
        return float(math.trunc(formation.bounding_radius(self.models, self.ranks)))

    def block(self) -> formation.Block:
        """`(x, y, direction, models, ranks)`, the block description `whshr.formation` works from."""
        return (self.x, self.y, self.direction, self.models, self.ranks)

    def footprint_corners(self) -> list[Point]:
        """The four world-space corners of this regiment's oriented block footprint, for
        `formation.footprint_gap` (close-combat contact, `whshr.combat.resolve_contacts`)."""
        return formation.footprint_corners(self.x, self.y, self.direction, self.models, self.ranks)


def _round_half_down(value: float) -> int:
    """Round to the nearest integer, an exact half rounding down (notes/reform_while_moving.md 3)."""
    return math.ceil(value - 0.5)


def _slot_offsets(assignment: Sequence[Point | None]) -> list[Point]:
    """`formation.reform_assignment`'s result with every model given a slot (always so when the block's
    slot count matches its model count)."""
    slots = [slot for slot in assignment if slot is not None]
    if len(slots) != len(assignment):
        raise ValueError("re-form left a model without a slot")
    return slots


def _shooting_code(unit: Mapping[str, Any]) -> int | None:
    """The missile code game_rules.md "Who shoots" reads for a unit (see `Regiment.shooting_code`)."""
    fields, _conflicts = stat_fields(unit.get("stats") or {})
    leader: Mapping[str, Any] = unit.get("leader") or {}
    leader_fields, _leader_conflicts = stat_fields(leader.get("stats") or {})
    own, leaders = stat_int(fields, "S_BalWeap"), stat_int(leader_fields, "S_BalWeap")
    race = stat_int(fields, "s_race")
    unit_class = race >> 3 if race is not None else None
    if unit_class == 3:
        return own
    if unit_class == 4:
        return leaders
    return leaders or own


def _decode_combat_profile(unit: Mapping[str, Any]) -> dict[str, Any]:
    """Decode a regiment's speed, WS/BS/S/T/W/I/A/Ld, armour, weapon and missile stats from its raw script
    setstats lines (game_rules.md section 3), stdlib-only (no GAMEF.DLL access needed at battle time:
    the tables it would supply are already verified constants in whshr.rules)."""
    fields, _conflicts = stat_fields(unit.get("stats") or {})
    profile: Mapping[str, Any] = unit.get("profile") or {}
    leader: Mapping[str, Any] = unit.get("leader") or {}
    leader_profile: Mapping[str, Any] = leader.get("profile") or {}
    armour = stat_int(fields, "s_armr") or 0
    mount_code = stat_int(fields, "s_mount")
    mount = MOUNT_PROFILES.get(mount_code) if mount_code is not None and 8 <= armour <= 13 else None
    move_stat = mount["M"] if mount is not None else profile.get("M")
    weapon_class = stat_int(fields, "s_weap")
    firing_code = _shooting_code(unit)
    missile_range = MISSILE_RANGES.get(firing_code or 0)
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
        "leader_ws": int(leader_profile["WS"]) if "WS" in leader_profile else None,
        "leader_strength": int(leader_profile["S"]) if "S" in leader_profile else None,
        "leader_attacks": int(leader_profile["A"]) if "A" in leader_profile else None,
        "leader_toughness": int(leader_profile["T"]) if "T" in leader_profile else None,
        "leader_wounds": int(leader_profile["W"]) if "W" in leader_profile else None,
        "leader_armour": stat_int(stat_fields(leader.get("stats") or {})[0], "s_armr") if leader else None,
        "leader_leadership": int(leader_profile["Ld"]) if "Ld" in leader_profile else None,
        "toughness": int(profile.get("T", DEFAULT_PROFILE["T"])),
        "wounds": int(profile.get("W", DEFAULT_PROFILE["W"])),
        "initiative": int(profile.get("I", DEFAULT_PROFILE["I"])),
        "attacks": int(profile.get("A", DEFAULT_PROFILE["A"])),
        "leadership": int(profile.get("Ld", DEFAULT_PROFILE["Ld"])),
        "armour": armour,
        "mount": mount_code,
        "strength_bonus": EXPECTED_WEAPON_BONUS.get(weapon_class, 0) if weapon_class is not None else 0,
        "missile_code": firing_code if missile_range else None,
        "missile_range": missile_range,
        "psychology": psychology,
        "hud_class": hud_class,
        "unit_class": race >> 3 if race is not None else None,
        "race": race & 7 if race is not None else None,
        "airborne": hud_class == "arch" and firing_code == 17,
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
                 deploy: bool = False, boundaries: Sequence[View] = (), objects: Sequence[View] = (),
                 scenery: Sequence[View] = ()) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("battle dimensions must be positive")
        self.width = width
        self.height = height
        self.regiments: dict[str, Regiment] = {regiment.identifier: regiment for regiment in regiments}
        self._recheck_carry: set[str] = set()  # re-check states set by the push-apart pass (see _carry_recheck)
        if len(self.regiments) != len(regiments):
            raise ValueError("regiment identifiers must be unique")
        self.stagger_counter = StaggerCounter()
        for slot, regiment in enumerate(regiments):
            regiment.stagger_counter = self.stagger_counter
            regiment.update_counter = slot
        self.tick_count = 0
        self.update_count = 0  # monotonic input/replay time, including deployment
        self.phase: Literal["deployment", "battle"] = "deployment" if deploy else "battle"
        self.paused = False
        self.mission_state = 0  # script choreography, independent of the player-visible phase
        # The objective letters the battle file defines (MISSIONINFO Objective: lines), read by IfObjective.
        self.objective_letters: frozenset[str] = frozenset()
        # The mission's evaluation list (whshr.objectives); None for a mission-less battle, which keeps the flat
        # "one side has no active regiment" end rule.
        self.objectives: objective_table.Objectives | None = None
        self.deployment_regions = deployment.regions(boundaries)
        self.deployment_region: deployment.Region | None = None
        self.deployment_drag: deployment.Drag | None = None
        self.boundaries = list(boundaries)
        self.navigation_boundaries = navigation.boundaries_from_views(boundaries)
        self.objects = list(objects)
        # Radius is a replaceable engine choice for placed furniture without a parsed footprint.
        self.scenery_names = [str(item.get("name", "")) for item in scenery]  # furniture types, in file order
        self.shooting_objects = list(objects) + [
            {"x": item.get("x"), "y": item.get("y"),
             "radius": buildings.footprint_radius(str(item.get("name", ""))),
             "status": ["os_solid"], "name": item.get("name")}
            for item in scenery]
        # Building pseudo-units (issue #173): the building-type furniture, addressable by `building:N`.
        self.buildings: list[buildings.Building] = buildings.from_scenery(scenery)
        self.building_index: dict[str, buildings.Building] = {b.identifier: b for b in self.buildings}
        offset = len(objects)
        for building in self.buildings:
            self.shooting_objects[offset + int(building.identifier[len(buildings.PREFIX):])]["building"] = (
                building.identifier)
        # Camera rotation in 1/512 turns, set by the frontend; wagons snap to it (see set_view_angle).
        self.view_angle: float | None = None
        # Map-aligned (min x, min y, max x, max y) around what the camera shows, set by the frontend
        # (notes/react_portrait.md section 5); None = no camera (headless), then "on screen" = visible to the player.
        self.view_rect: tuple[float, float, float, float] | None = None
        self.portrait_popup = PortraitPopup()  # leader portrait shown for reactions (notes/react_portrait.md 3)
        self._snapped_view_angle: float | None = None
        self.rng = random.Random(seed)
        self.script_logger = script_logger
        self._warned_blocked_routes: set[tuple[str, TurnKey, str]] = set()
        self.events: list[BattleEvent] = []  # battle events emitted by the most recent tick
        self.pending_feedback: list[BattleEvent] = []
        self.text_resources: dict[int, str] = {}
        self.projectiles: list[Any] = []
        self.innate_projectiles: list[Any] = []
        self.spell_effects = spell_effects.EffectTable()  # active spell effects (whshr.spell_effects)
        self.impact_effects: list[Any] = []
        self.death_blasts: list[Any] = []
        self.ctrl_held = False
        self.ground_height: Callable[[float, float], float] = lambda x, y: 0.0
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
        # Engagements asked for by the contact handler (Query 8) this tick: (joiner, owner, charge counter). With
        # scripts running, these are the only way a fight starts (notes/script_behaviours.md 2.0).
        self.engage_requests: list[tuple[str, str, int]] = []
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
                    has_leader=bool(unit.get("leader")),
                    spells=magic.spell_codes(unit.get("spells") or ()),
                    items=tuple(str(item) for item in unit.get("items") or ())[:objective_table.ITEM_SLOTS],
                    shooting_code=_shooting_code(unit),
                    **_decode_combat_profile(unit),
                ))
                script_value = position.get("script")
                if isinstance(script_value, str) and script_value.upper() == "PLAYER_SCRIPT":
                    script_ids[identifier] = behaviour.PLAYER_SCRIPT
                elif isinstance(script_value, (int, float)):
                    script_ids[identifier] = int(script_value)
        mission: View = source.get("mission") or {}
        battle = cls(field_data["width"], field_data["height"], regiments, seed=seed,
                   script_dll=script_dll, script_ids=script_ids, script_logger=script_logger, nodes=nodes,
                   script_nodes=script_nodes,
                   deploy=bool(mission.get("deploy_troops")), boundaries=source.get("boundaries") or (),
                   objects=source.get("objects") or (), scenery=source.get("scenery") or ())
        battle.objective_letters = frozenset(str(entry[0]).upper() for entry in mission.get("objectives") or ()
                                             if entry)
        # Battle load, before deployment: every letter takes its counts (notes/battle_end_objectives.md 3.1). Every
        # shipped battle declares objectives; a script with none (a test or mod field) keeps the flat end rule.
        if mission.get("objectives"):
            battle.objectives = objective_table.Objectives.from_entries(mission.get("objectives"))
            battle.objectives.load(battle)
        return battle

    def start_battle(self) -> None:
        """Confirm deployment once, retaining placements and prepared orders (§5)."""
        if self.phase == "deployment":
            self.end_deployment_drag()
            self.phase = "battle"
            self.refresh_visibility()

    def set_view_rect(self, rect: tuple[float, float, float, float] | None) -> None:
        """Frontend hook: the ground rectangle (with margin) the camera currently shows, in world units."""
        self.view_rect = rect

    def on_screen(self, regiment: Regiment) -> bool:
        """Whether a regiment counts as "currently drawn" for enemy reactions (notes/react_portrait.md section 5):
        its front-rank position was inside the view rectangle at the end of the last tick, and it is not a hidden
        enemy. Without a camera (headless battles) this falls back to `visible_to_player`."""
        if self.view_rect is None:
            return regiment.visible_to_player
        return regiment.screen_mark and not (regiment.side == Side.ENEMY and regiment.hidden)

    def refresh_screen_marks(self) -> None:
        """End-of-tick refresh of every regiment's drawn mark; scripts read the previous tick's value."""
        rect = self.view_rect
        for regiment in self.regiments.values():
            if rect is None or not regiment.active:
                regiment.screen_mark = False
                continue
            x, y = self.route_reference_point(regiment)
            regiment.screen_mark = rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]

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

    @staticmethod
    def route_reference_point(regiment: Regiment) -> Point:
        """The regiment's front-rank position: the point route scans, steer points, trials and waypoint
        distances are measured from (notes/obstacle_steering.md section 2; notes/movement_boundaries_route_finding.md,
        "A moving regiment has several relevant positions"). Unlike `formation_centre`, which sits
        ``(ranks - 1) * 6`` units behind it along the facing and serves only collision and edge correction."""
        return regiment.x, regiment.y

    def route_effective_speed(self, regiment: Regiment) -> float:
        """The speed the route filter compares (notes/obstacle_steering.md section 6): the unit's travel speed while
        it is not pausing and has a move, flight, pursuit or charge under way; 0 otherwise. PROVISIONAL: the
        travel speed is the free-move speed, the charge speed while charging and the flight speed while broken."""
        if regiment.route_pause_ticks > 0:
            return 0.0
        if regiment.routing:
            return regiment.speed_for_mode(FLEEING_K)
        if regiment.attack_target is not None or regiment.free_charging and regiment.moving:
            return regiment.speed_for_mode(CHARGING_K)
        if regiment.moving or regiment.waypoints:
            return regiment.speed_per_tick
        return 0.0

    def route_heading(self, regiment: Regiment) -> float:
        """A unit's route heading: towards its steer point while steering, else towards its waypoint, else its
        facing (notes/obstacle_steering.md section 6)."""
        point = regiment.avoid_target or ((regiment.target_x, regiment.target_y)
                                          if regiment.target_x is not None and regiment.target_y is not None else None)
        if point is None:
            return float(regiment.direction)
        return math.atan2(point[0] - regiment.x, point[1] - regiment.y) * 512 / math.tau % 512

    def route_unit_relation(self, mover: Regiment, other: Regiment, trial: bool,
                            mover_speed: float | None = None) -> Literal["block", "ignore", "pause"]:
        """How `other`'s footprint affects `mover`'s route once the geometric obstacle test has selected it
        (notes/obstacle_steering.md section 3 item 6 and section 6 item 3; notes/bf003_peasant_move_obstruction.md,
        relationship table). "pause" means the mover waits 54 updates (`pause_route`) instead of detouring.
        `trial` is true while a plan trial runs, when enemy units are not obstacles."""
        if mover.is_wagon:
            return "ignore"
        mover_state = self.event_bus.unit_states.get(mover.identifier)
        # PROVISIONAL: the report gives no measure for the threat range; the octagonal distance is used, and an
        # unset range (0) means no limit.
        dx = abs(mover.x - other.x)
        dy = abs(mover.y - other.y)
        distance = max(dx, dy) + math.ceil(min(dx, dy) / 2)
        if mover_state is not None and mover_state.threat_range > 0 and distance >= mover_state.threat_range:
            return "ignore"
        other_state = self.event_bus.unit_states.get(other.identifier)
        if other_state is not None and other_state.unit_flags & interpreter.LEAVING_BATTLE_FLAG:
            return "ignore"
        if can_fight(mover.side, other.side):
            return "ignore" if trial or other.hidden or other.routing else "block"
        if mover.attack_target == other.identifier or (
                mover.melee_group is not None and mover.melee_group == other.melee_group):
            return "ignore"
        # Effective speeds and route headings (notes/obstacle_steering.md section 6); `mover_speed` overrides the
        # mover's, e.g. 0 for the plan made at the moment of a new order.
        own_speed = self.route_effective_speed(mover) if mover_speed is None else mover_speed
        faster = own_speed > self.route_effective_speed(other)
        turn = abs(self.route_heading(mover) - self.route_heading(other)) % 512
        turn = min(turn, 512 - turn)
        if turn < 64:
            return "block" if faster else "ignore"
        if faster:
            return "block"
        s_rlmv = mover.speed_per_tick * 16 / MOVING_FREELY_K
        return "pause" if distance < 16 * s_rlmv else "block"

    def pause_route(self, regiment: Regiment, ticks: int = 54) -> None:
        """Pause `regiment`'s move for `ticks` updates, keeping its destination, waypoints, attack target and
        order (notes/obstacle_steering.md section 5 "On failure" and section 6 items 2-3). Movement resumes
        afterwards; a new order or a halt clears the pause (PROVISIONAL: the notes are silent on that)."""
        regiment.route_pause_ticks = max(0, ticks)

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

    def order_rally(self, identifier: str) -> None:
        """The player's Rally order (notes/pursuit_restraint.md 3): flip the rally-attempt state of a player
        regiment that is pursuing or broken. Nothing else changes (no shout, halt, re-form or reschedule); a
        second press switches it off again. Any other regiment refuses the order."""
        self._require_battle_order()
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER or not regiment.active or not (regiment.pursuing or regiment.routing):
            raise ValueError("rally requires an active player regiment that is pursuing or broken")
        regiment.rally_attempt = not regiment.rally_attempt

    def order_fight_harder(self, identifier: str) -> None:
        """Apply the melee command to the focused player unit for one segment (game_rules.md, Player orders)."""
        self._require_battle_order()
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER or not regiment.active or not regiment.in_melee:
            raise ValueError("fight harder requires an active player regiment in melee")
        regiment.fight_harder = True

    def arm_item(self, identifier: str, item: str) -> bool:
        """Spend an activated item on selection; return whether it needs a battlefield point."""
        self._require_battle_order()
        unit = self.regiments[identifier]
        if (unit.side != Side.PLAYER or not unit.active or unit.living_leader_index is None
                or item not in unit.items or item in unit.used_items):
            raise ValueError("item is unavailable")
        if item not in {"ItemBannerOfWrath", "ItemGrudgeBringer", "ItemPotionOfStrength"}:
            raise ValueError("item has no activation")
        unit.used_items.add(item)
        if item == "ItemPotionOfStrength":
            if not unit.held:
                unit.potion_strength = True
            return False
        return True

    def order_item_target(self, identifier: str, item: str, x: float, y: float) -> None:
        """Give an already selected item its point; a held bearer loses the use without launching."""
        self._require_battle_order()
        unit = self.regiments[identifier]
        if unit.side != Side.PLAYER or item not in unit.items or item not in unit.used_items:
            raise ValueError("item was not selected")
        if not unit.active or unit.held or unit.living_leader_index is None:
            return
        code = {"ItemBannerOfWrath": 0x105, "ItemGrudgeBringer": 0x10A}.get(item)
        if code is None:
            raise ValueError("item does not take a point")
        if self.interpreter is not None:
            self.event_bus.queue_event(identifier, interpreter.Event(code=0x2D, parameter=code, x=int(x), y=int(y)))
        else:
            self.launch_item(unit, code, x, y)

    def launch_item(self, unit: Regiment, code: int, x: float, y: float) -> bool:
        """Apply the item launch checks, then create Lightning or Fireball without spending power."""
        if not unit.active or unit.held or unit.living_leader_index is None:
            return False
        target = self.event_bus.unit_states.get(unit.identifier)
        if target is not None and target.current_target is not None:
            aimed = self.regiments.get(target.current_target[0])
            if aimed is not None and aimed.active:
                x, y = spell_effects.reference_figure(aimed)
        distance = int(math.hypot(x - unit.x, y - unit.y))
        bearing = int(256 - 256 * math.atan2(x - unit.x, -(y - unit.y)) / math.pi) % 512
        difference = abs(int(unit.direction) - bearing) % 512
        if distance >= 576 or (not unit.in_melee and min(difference, 512 - difference) >= 71):
            self.events.append(BattleEvent(f"{unit.name} cannot use the item at that point.", "message",
                                           regiment=unit.identifier, text_id=2021))
            return False
        spell = spell_effects.LIGHTNING if code == 0x105 else spell_effects.FIREBALL
        return spell_effects.launch(self, spell, unit, -1, x, y)

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

    def _hold_while_reforming(self, regiment: Regiment, order: tuple[Any, ...]) -> bool:
        """Hold a player order while the regiment re-forms (notes/reform_while_moving.md 4): it becomes the
        pending order, replacing any earlier one, with a `React 13` reply the first time. Attack is held the same
        way: the original accepts it at once but its approach waits for the re-form, which looks the same."""
        if self.phase != "battle" or not regiment.reforming:
            return False
        if regiment.pending_order is None:
            self.react(regiment.identifier, 13)
        regiment.pending_order = order
        return True

    def _apply_pending_orders(self) -> None:
        """Apply each held order once its regiment's re-form has ended; an order no longer valid is dropped."""
        for regiment in list(self.regiments.values()):
            if regiment.pending_order is None or regiment.reforming:
                continue
            name, *args = regiment.pending_order
            regiment.pending_order = None
            try:
                getattr(self, name)(regiment.identifier, *args)
            except ValueError:
                pass

    def order_move(self, identifier: str, x: float, y: float) -> None:
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if regiment.pursuing:  # notes/pursuit_map_edge.md 5: move, attack, turn, rank and halt orders do nothing
            raise ValueError(f"{identifier} is pursuing and cannot be ordered")
        if regiment.held:  # notes/spell_area_effects.md 3.3: a thorn-held unit cannot move, charge or turn
            raise ValueError(f"{identifier} is held and cannot be ordered")
        regiment.route_pause_ticks = 0  # a new order ends a route pause
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
        if self._hold_while_reforming(regiment, ("order_move", x, y)):
            return
        regiment.waypoints.clear()
        regiment.clear_shooting()
        regiment.attack_target = None
        regiment.charge_started_target = None
        regiment.free_charging = False
        regiment.turn_order_key = None
        regiment.route_follows_unit = False
        self.set_point_route(regiment, (float(x), float(y)))

    def set_point_route(self, regiment: Regiment, goal: Point) -> None:
        points = navigation.point_route((regiment.x, regiment.y), goal, self.navigation_boundaries)
        regiment.target_x, regiment.target_y = points[0]
        regiment.waypoints = points[1:]
        regiment.avoid_target = None
        regiment.route_side, regiment.route_planned_for = 0, None

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
        if regiment.pursuing:  # notes/pursuit_map_edge.md 5: move, attack, turn, rank and halt orders do nothing
            raise ValueError(f"{identifier} is pursuing and cannot be ordered")
        if regiment.held:  # notes/spell_area_effects.md 3.3: a thorn-held unit cannot move, charge or turn
            raise ValueError(f"{identifier} is held and cannot be ordered")
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
        if self._hold_while_reforming(regiment, ("order_attack", target_id)):
            return
        regiment.target_x = regiment.target_y = None
        regiment.route_pause_ticks = 0
        regiment.clear_shooting()
        regiment.attack_target = target_id
        regiment.charge_started_target = None
        regiment.free_charging = False
        regiment.route_follows_unit = False
        regiment.turn_order_key = None

    def order_charge_forward(self, identifier: str) -> None:
        """Begin the selected regiment's straight-ahead Charge command."""
        self._require_battle_order()
        regiment = self.regiments[identifier]
        if (regiment.side != Side.PLAYER or not regiment.active or regiment.routing or regiment.pursuing
                or regiment.held or regiment.braced or regiment.anchored or regiment.in_melee):
            raise ValueError("regiment cannot charge")
        if self._hold_while_reforming(regiment, ("order_charge_forward",)):
            return
        if self.interpreter is not None:
            self.event_bus.queue_event(identifier, interpreter.Event(code=0x06), route="self")
            return
        reach = 12 * regiment.speed_per_tick * 16 / MOVING_FREELY_K
        angle = regiment.direction * math.tau / formation.FULL_TURN
        regiment.target_x = regiment.x + int(math.sin(angle) * reach)
        regiment.target_y = regiment.y + int(math.cos(angle) * reach)
        regiment.waypoints.clear()
        regiment.attack_target = regiment.charge_started_target = None
        regiment.free_charging = True
        regiment.hidden = False

    def order_halt(self, identifier: str) -> None:
        """Cancel the selected regiment's current movement or charge order in place."""
        self._require_battle_order()
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if regiment.pursuing:  # notes/pursuit_map_edge.md 5: move, attack, turn, rank and halt orders do nothing
            raise ValueError(f"{identifier} is pursuing and cannot be ordered")
        if regiment.in_melee:
            raise ValueError(f"{identifier} is in melee and cannot be ordered")
        regiment.pending_order = None  # a later order replaces a held one
        regiment.target_x = regiment.target_y = None
        regiment.route_pause_ticks = 0
        regiment.attack_target = None
        regiment.charge_started_target = None
        regiment.free_charging = False
        regiment.turn_order_key = None
        regiment.route_speed = 0.0
        regiment.waypoints.clear()
        regiment.route_follows_unit = False
        regiment.clear_shooting()
        # game_rules.md "Braced": Halt is the one order still accepted while braced, and clears it.
        regiment.braced = False
        regiment.braced_target = None

    def order_fire(self, identifier: str, target_id: str | None = None,
                   point: Point | None = None, *, script: bool = False,
                   object_index: int | None = None, bomb: bool = False) -> int | None:
        """Select a lasting object or one ground attempt; return a GMTXT feedback id."""
        self._require_battle_order()
        unit = self.regiments[identifier]
        if not script and unit.side != Side.PLAYER:
            raise ValueError("only player units accept player Fire")
        if not script and unit.hud_class not in {"arch", "art"}:
            raise ValueError("unit has no Fire control")
        if (unit.shooting_code or unit.missile_code) not in ARCHER_MISSILE_CODES and not script:
            raise ValueError("unit has no ordinary missile weapon")
        if unit.routing or unit.in_melee or unit.braced or unit.attack_target:
            raise ValueError("unit is busy")
        if unit.held:  # notes/spell_area_effects.md 3.3: a thorn-held unit does not shoot
            raise ValueError("unit is held")
        if bomb and unit.shooting_code == 17 and unit.hud_class == "arch":
            if not unit.airborne:
                return 2020
            point, target_id, object_index = (unit.x, unit.y), None, None
        if target_id == identifier:
            mode, feedback = "search", 2017 if unit.independent else 2009
            target_id = None
        elif target_id is not None:
            target = self.regiments.get(target_id)
            if target is None or not target.active or target.hidden:
                raise ValueError("target cannot be picked")
            mode, feedback = "target", 2008
        elif object_index is not None and 0 <= object_index < len(self.shooting_objects):
            mode, feedback = "building", 2007
        elif point is not None:
            mode, feedback = "ground", None
        else:
            raise ValueError("Fire needs a target or point")
        unit.target_x = unit.target_y = None
        unit.waypoints.clear()
        unit.turn_order_key = None
        unit.clear_shooting()
        if self.interpreter is not None and not script and not bomb:
            self._post_fire_event(unit, mode, target_id, point, object_index)
            return feedback
        unit.shooting_target = target_id
        unit.shooting_object = object_index
        unit.shooting_point = point
        unit.shooting_mode = mode
        return feedback

    def destroy_building(self, building: buildings.Building) -> None:
        """A building at its wounds-to-destroy ends: it stops counting as a target, every live scripted unit gets
        event 0x18 (notes/building_units.md 7) and a battle event is recorded. The footprint stays solid -- the
        ruin still pushes regiments apart and intercepts shots. Not modelled: the ruin's own size and height."""
        building.destroyed = True
        building.models = 0
        credited = self.regiments.get(building.credit or "")
        if credited is not None:  # +1 kill per piece, no experience: building points are 0 (casualty_bookkeeping.md)
            credited.kills += building.pieces
        building.credit = None
        self.release_building_assaults(building.identifier)
        for unit_id in list(self.event_bus.unit_states):
            self.event_bus.queue_event(unit_id, interpreter.Event(code=0x18, source=building.identifier,
                                                                  x=int(building.x), y=int(building.y)))
        self.events.append(BattleEvent(f"{building.name} is destroyed.", "building_destroyed",
                                       building=building.identifier, x=building.x, y=building.y))

    def _post_fire_event(self, unit: Regiment, mode: str, target_id: str | None, point: Point | None,
                         object_index: int | None) -> None:
        """With behaviour scripts running, a player Fire order is the event the shooter's script handles
        (notes/script_shooting.md 5.1): 0x1F at a unit, 0x1E at a building, 0x20 on itself, 0x21 on the ground;
        an independent Archers unit gets 0x25 (unit or building) and 0x24 (itself). A building order names the
        building pseudo-unit as its source (issue #173); other solid objects carry only their position."""
        hunts = unit.independent and unit.hud_class == "arch"
        if mode == "target":
            event = interpreter.Event(code=0x25 if hunts else 0x1F, source=target_id)
        elif mode == "building" and object_index is not None:
            obj = self.shooting_objects[object_index]
            event = interpreter.Event(code=0x25 if hunts else 0x1E, source=obj.get("building"),
                                      x=int(obj.get("x") or 0), y=int(obj.get("y") or 0))
        elif mode == "search":
            event = interpreter.Event(code=0x24 if hunts else 0x20, x=-1, y=-1)
        else:
            x, y = point if point is not None else (-1.0, -1.0)
            event = interpreter.Event(code=0x21, x=int(x), y=int(y))
        self.event_bus.queue_event(unit.identifier, event)

    def resolve_no_battle(self) -> None:
        """No-battle mode (a campaign-progression shortcut, not a game rule): skip this fight and
        settle it as an immediate, lossless win -- every enemy regiment destroyed, no player
        regiment touched -- so the campaign flow past it (debrief, roster, map) can be walked
        without simulating it. Leaves neutral regiments alone; `_update_result` reads only player
        and enemy sides."""
        for regiment in self.regiments.values():
            if regiment.side == Side.ENEMY:
                regiment.models = 0
        if self.objectives is not None:
            self.result = "victory"
            return
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
        if regiment.pursuing:  # notes/pursuit_map_edge.md 5: move, attack, turn, rank and halt orders do nothing
            raise ValueError(f"{identifier} is pursuing and cannot be ordered")
        if regiment.held:
            raise ValueError(f"{identifier} is held and cannot be ordered")
        if regiment.attack_target is not None or regiment.in_melee:
            raise ValueError(f"{identifier} is charging or in melee and cannot be ordered")
        regiment.pending_order = None  # a later order replaces a held one
        self._begin_reform(regiment, formation.clamp_ranks(regiment.models, ranks))
        regiment.clear_shooting()
        if self.phase == "deployment":
            self._snap_deployment_layout(regiment)
            self.refresh_visibility()

    def reform_to_ranks(self, regiment: Regiment, ranks: int, formation_clamp: bool = True,
                        walk_back: bool = False) -> None:
        """Lay `regiment` out in `ranks` ranks and start re-slotting its models: the layout a re-form script
        opcode asks for, with none of the player-order guards. The count is clamped to the span the model
        count allows, or (`formation_clamp` false) only to the 1-8 ranks a battle file may name. `walk_back`
        selects the Rally re-form mode (notes/reform_while_moving.md 2, 6)."""
        self._begin_reform(regiment, formation.clamp_ranks(regiment.models, ranks) if formation_clamp
                           else max(1, min(8, ranks)), walk_back=walk_back)

    def _check_turn_order(self, identifier: str) -> Regiment:
        """Shared guard for all standalone turn orders (game_rules.md "Turning, wheeling and reversing")."""
        self._require_battle_order()
        regiment = self.regiments[identifier]
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if regiment.pursuing:  # notes/pursuit_map_edge.md 5: move, attack, turn, rank and halt orders do nothing
            raise ValueError(f"{identifier} is pursuing and cannot be ordered")
        if regiment.in_melee:
            raise ValueError(f"{identifier} is in melee and cannot be ordered")
        if regiment.held:  # notes/spell_area_effects.md 3.3: a thorn-held unit cannot move, charge or turn
            raise ValueError(f"{identifier} is held and cannot be ordered")
        regiment.clear_shooting()
        regiment.pending_order = None  # a later order replaces a held one (a held face-point order sets it again)
        return regiment

    def order_turn_left(self, identifier: str) -> None:
        """Rotate a player regiment 90° counter-clockwise in place (game_rules.md, opcodes 0x0C)."""
        regiment = self._check_turn_order(identifier)
        goal = (regiment.direction - 128) % 512
        self._plan_turn_order(regiment, goal)
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = None
        regiment.turn_order_key = ("turn", goal)
        regiment.route_speed = 0.0

    def order_turn_right(self, identifier: str) -> None:
        """Rotate a player regiment 90° clockwise in place (game_rules.md, opcodes 0x0D)."""
        regiment = self._check_turn_order(identifier)
        goal = (regiment.direction + 128) % 512
        self._plan_turn_order(regiment, goal)
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = None
        regiment.turn_order_key = ("turn", goal)
        regiment.route_speed = 0.0

    def order_about_face(self, identifier: str) -> None:
        """Rotate a player regiment 180° in place (game_rules.md, opcodes 0x0E)."""
        regiment = self._check_turn_order(identifier)
        goal = (regiment.direction + 256) % 512
        self._plan_turn_order(regiment, goal)
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = None
        regiment.turn_order_key = ("turn", goal)
        regiment.route_speed = 0.0

    def order_face_point(self, identifier: str, x: float, y: float) -> None:
        """Turn a player regiment to face world coordinates (x, y) in place."""
        regiment = self._check_turn_order(identifier)
        dx, dy = x - regiment.x, y - regiment.y
        if math.hypot(dx, dy) < 1e-9:
            return  # click on own position: ignore
        if self._hold_while_reforming(regiment, ("order_face_point", x, y)):
            return
        goal = round(math.atan2(dx, dy) * 512 / math.tau) % 512
        self._plan_turn_order(regiment, goal)
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = None
        regiment.turn_order_key = ("turn", goal)
        regiment.route_speed = 0.0

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

    def _begin_reform(self, regiment: Regiment, ranks: int, walk_back: bool = False) -> None:
        """Recompute the shape for `ranks` and re-slot every model into it (game_rules.md, "Formation
        changes"). A living leader keeps the front-rank-centre slot through the re-slotting.

        Shuffle mode (the default) wakes every figure so it re-aims at its new slot on its next step. Walk-back
        mode (`walk_back`, Rally; kept while a walk-back re-form is still running) applies the nearest-slot
        assignment as a permutation into raster order, so the ordinary catch-up walk drives the figures
        (notes/reform_while_moving.md 2, 6, 12).
        """
        positions = regiment.model_positions()
        leader_index = regiment.living_leader_index if not regiment.routing else None
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
                leader_index=leader_index,
                farthest=regiment.hud_class == "art" and self.phase != "deployment"))
            raster_index = {offset: index for index, offset in
                            enumerate(formation.block_slots(regiment.models, ranks))}
            order = sorted(range(len(assignment)), key=lambda i: raster_index[assignment[i]])
            regiment.positions = [positions[i] for i in order]
            regiment.melee_models = [regiment.melee_models[i] for i in order]
            regiment.reform_slots = []
            regiment.reforming = regiment.reform_walk_back = False
            regiment.collision_recheck = True  # every formation re-layout, wagons and war machines included
            return
        walk_back = walk_back or (regiment.reforming and regiment.reform_walk_back)
        regiment.reform_slots = _slot_offsets(formation.reform_assignment(
            regiment.x, regiment.y, regiment.direction, regiment.models, ranks, positions,
            leader_index=leader_index))
        if walk_back and regiment.reform_slots:
            raster = formation.block_slots(regiment.models, ranks)
            raster_index = {offset: index for index, offset in enumerate(raster)}
            order = sorted(range(len(regiment.reform_slots)), key=lambda i: raster_index[regiment.reform_slots[i]])
            regiment.positions = [positions[i] for i in order]
            regiment.melee_models = [regiment.melee_models[i] for i in order]
            regiment.reform_slots = list(raster)
        regiment.reforming = bool(regiment.reform_slots)
        regiment.reform_walk_back = walk_back and regiment.reforming
        regiment.collision_recheck = True  # notes/fanatic_collisions.md 5: every formation re-layout switches it on
        regiment.reform_facing = regiment.direction
        for model in regiment.melee_models:
            model.at_rest = False
            model.reform_step = None
            model.reaim_countdown = 0.0

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
                "shooting_target": regiment.shooting_target,
                "shooting_point": list(regiment.shooting_point) if regiment.shooting_point is not None else None,
                "shooting_mode": regiment.shooting_mode, "machine_alive": regiment.machine_alive,
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
        self.events = self.pending_feedback
        self.pending_feedback = []
        self.update_count += 1
        if self.paused:
            return
        self.portrait_popup.tick()
        if self.result is not None:
            # Remaining missiles and death poses continue after the victory condition is met.
            for regiment in self.regiments.values():
                self._step_burning(regiment)
                self._step_dying(regiment)
            ranged.finish_tick(self)
            spell_effects.tick(self)
            self.tick_count += 1
            return
        scale = seconds / TICK_SECONDS
        self._apply_pending_orders()
        if (self.objectives is not None and self.phase == "battle" and self.tick_count > 0
                and self.tick_count % objective_table.SEGMENT_TICKS == 0):
            # Segment boundary, before any unit is updated (notes/battle_end_objectives.md 3.2).
            self.objectives.segment(self)
        if self.phase == "battle":
            spell_effects.blow_wind(self)
            self.refresh_visibility()
        # Run behaviour scripts via the bytecode interpreter (issue #3); a mission-less/synthetic
        # battle has no interpreter and so no automatic orders (only explicit Battle.order_* calls).
        if self.interpreter:
            # A snapshot: SpawnUnit may add units while scripts run (they start next tick).
            for unit_id, state in list(self.event_bus.unit_states.items()):
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
        self._restore_carried_rechecks()
        combat.refresh_braced_state(self)
        if self.interpreter:
            self.interpreter.stop_ended_charge_sounds()
        if self.tick_count % combat.SEGMENT_TICKS == 0:
            self._update_pursuits()
            combat.resolve_melee(self)
            combat.resolve_contact_attacks(self)  # game_rules.md 7.7, once per segment
            combat.resolve_building_assaults(self)
            combat.resolve_rally(self)
            if self.tick_count > 0:
                for regiment in self.regiments.values():
                    regiment.fight_harder = False
        combat.resolve_router_contact_attacks(self)
        combat.resolve_shooting(self)
        spell_effects.tick(self)  # after units and ordinary missiles (notes/spell_effects.md 1.7)
        if self.objectives is None:
            self._update_result()
        self.refresh_screen_marks()
        self.tick_count += 1

    def _advance_regiments(self, scale: float, seconds: float) -> None:
        for regiment in self.regiments.values():
            self._step_burning(regiment)
            self._step_dying(regiment)
            if not regiment.active:
                regiment.walking = False
                continue
            regiment.update_counter += 1  # every update of a live unit, whatever it does (the throttle phase)
            regiment.model_positions()  # seed positions at the current anchor/facing before it moves
            anchor_before = regiment.x, regiment.y
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
            # notes/reform_while_moving.md 2: not in the Rally's walk-back mode.
            move_scale = scale * (0.5 if regiment.reforming and not regiment.reform_walk_back else 1.0)
            latch_snapshot = self._latch_snapshot(regiment, state)
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
                        self.remove_from_play(regiment)
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
            elif regiment.assaulting_building is not None:
                regiment.turn_order_key = regiment.turn_mode = None  # held at the building until it falls
            elif regiment.attack_target in self.building_index:
                moved = self._advance_on_building(regiment, self.building_index[regiment.attack_target],
                                                  move_scale, scale)
            elif regiment.route_pause_ticks > 0 and (regiment.attack_target or regiment.moving):
                regiment.route_pause_ticks -= 1  # route pause: keep the order, do not advance
                regiment.route_speed = 0.0
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
                    # A pursuer runs straight at the chase point set at the last segment tick
                    # (notes/pursuit_map_edge.md 2); a charge re-aims at its target every update.
                    chase = (regiment.pursuit_point if regiment.pursuing and regiment.pursuit_point is not None
                             else (target.x, target.y))
                    # game_rules.md "Unit speed" and R39: a pursuer moves at the pursuit step,
                    # min(24 * s_rlmv, 10 * distance) / 256 world units per tick, instead of the charge speed.
                    speed = (min(regiment.speed_for_mode(FLEEING_K),
                                 10 * math.hypot(target.x - regiment.x, target.y - regiment.y) / 256)
                             if regiment.pursuing else regiment.speed_for_mode(CHARGING_K))
                    if regiment.pursuing and math.dist(chase, (regiment.x, regiment.y)) < 2 * speed:
                        # PROVISIONAL: having reached the chase point before the next re-aim, run on along the facing
                        # instead of circling it.
                        facing = regiment.direction * math.tau / 512
                        chase = (regiment.x + 256 * math.sin(facing), regiment.y + 256 * math.cos(facing))
                    moved = self._advance_toward(regiment, chase, speed * move_scale, arrive=False,
                                                 order_key=("charge", target.identifier), scale=scale)
            elif regiment.target_x is not None and regiment.target_y is not None and regiment.free_charging:
                moved = self._advance_toward(regiment, (regiment.target_x, regiment.target_y),
                                             regiment.speed_for_mode(CHARGING_K) * move_scale, arrive=True,
                                             order_key=("charge", "forward"), scale=scale)
            elif regiment.target_x is not None and regiment.target_y is not None:
                moved = self._advance_move(regiment, (regiment.target_x, regiment.target_y),
                                           regiment.speed_per_tick * move_scale,
                                           ("move", regiment.target_x, regiment.target_y), scale)
            elif regiment.turn_order_key is not None and regiment.turn_order_key[0] == "turn":
                # Standalone turn order (game_rules.md "Turning, wheeling and reversing"): speed zero,
                # shift 8; pivot about the inner front corner like all other gradual turns. Suspended
                # while re-forming: the tick is skipped (notes/reform_while_moving.md 5).
                if not regiment.reforming:
                    self._step_turn(regiment, scale)
                if regiment.turn_mode is None:
                    regiment.turn_order_key = None
            else:
                regiment.turn_order_key = regiment.turn_mode = None
                regiment.route_pause_ticks = 0
            if latch_snapshot is not None:
                moved = self._resolve_latched_step(regiment, state, latch_snapshot) and moved
            if regiment.in_melee or not (regiment.routing or regiment.attack_target or regiment.moving):
                regiment.route_speed = 0.0
            if regiment.attack_target is None and not regiment.in_melee:
                for model in regiment.melee_models:
                    model.freeze_ticks = 0
            if regiment.reforming:
                # Re-form steps correct each model's offset from its slot. Carry the block's
                # translation first; otherwise a cavalry anchor outruns the one-unit correction
                # cap and WaitWhileUnitFlags 8 can never finish while it moves.
                dx, dy = regiment.x - anchor_before[0], regiment.y - anchor_before[1]
                regiment.positions = [(x + dx, y + dy) for x, y in regiment.positions]
                models_catching_up = self._advance_reforming_models(regiment, scale)
            else:
                models_catching_up = self._advance_models(regiment, scale)
            regiment.walking = moved or models_catching_up
            # notes/fanatic_collisions.md 5: a position step switches the re-check state on only on every 4th update
            # of the unit (staggered by slot); gradual turn steps do so every time. PROVISIONAL: a turn step is read
            # as "a turn is in progress while the unit moved".
            if moved and (regiment.turn_mode is not None or regiment.update_counter % 4 == 0):
                regiment.collision_recheck = True
            self._step_animations(regiment)

    def _latch_snapshot(self, regiment: Regiment, state: interpreter.UnitScriptState | None
                        ) -> tuple[float, float, float, list[Point]] | None:
        """The pose to restore if a latched unit's step is undone (notes/script_behaviours.md 2.5). Only a unit that
        holds the contact latch and is not in melee, routing or pursuing moves under the latch rule."""
        if (state is None or not state.contact_latch or regiment.in_melee or regiment.routing
                or regiment.pursuing):
            return None
        return regiment.x, regiment.y, regiment.direction, list(regiment.positions)

    def _resolve_latched_step(self, regiment: Regiment, state: interpreter.UnitScriptState | None,
                              snapshot: tuple[float, float, float, list[Point]]) -> bool:
        """Latch lifecycle for movement (notes/script_behaviours.md 2.5): a latched charger does not advance; an
        ordinary move or turn that still overlaps something afterwards is undone and the unit halts and re-forms; a
        step that leaves nothing overlapping stands and the latch goes off. Returns whether the unit still moved.
        PROVISIONAL: "overlaps something" is any active, visible regiment it may engage whose footprint it
        penetrates (the push-apart table for other footprint kinds, 2.2, is not modelled)."""
        if state is None:
            return True
        charging = regiment.attack_target is not None
        if not charging and (regiment.x, regiment.y, regiment.direction) == snapshot[:3]:
            return False
        if not charging and not self._overlaps_anything(regiment):
            state.contact_latch = False
            return True
        regiment.x, regiment.y, regiment.direction, regiment.positions = snapshot
        if not charging:
            regiment.target_x = regiment.target_y = None
            regiment.waypoints = []
            regiment.turn_order_key = regiment.turn_mode = None
            self.reform_to_ranks(regiment, regiment.ranks)
        return False

    def _overlaps_anything(self, regiment: Regiment) -> bool:
        centre = self.formation_centre(regiment)
        radius = regiment.bounding_radius()
        return any(other is not regiment and other.active and not other.hidden and not other.routing
                   and may_engage(regiment, other) and formation.penetrates(regiment.block(), other.block())
                   for other in self.regiments.values()) or any(
            building.penetration(centre[0], centre[1], radius) is not None for building in self.buildings)

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
        """Advance one active gradual turn, shifting the anchor around the inner corner (not while re-forming:
        only a pursuit turns then, without the pivot shift, notes/reform_while_moving.md 5)."""
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
        if not regiment.turns_on_the_spot and not regiment.reforming:
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
            regiment.route_speed = 0.0
            regiment.target_x = regiment.target_y = None
            regiment.waypoints.clear()
            regiment.attack_target = regiment.charge_started_target = None
            regiment.free_charging = False
            regiment.avoid_target = None
            regiment.route_side, regiment.route_planned_for = 0, None
            return False
        dx, dy = steering_target[0] - regiment.x, steering_target[1] - regiment.y
        distance = math.hypot(dx, dy)
        if distance < 1e-9:
            regiment.route_speed = 0.0
            if arrive:
                regiment.target_x = regiment.target_y = None
                regiment.free_charging = False
            return False
        goal = round(math.atan2(dx, dy) * 512 / math.tau) % 512
        new_order = order_key != regiment.turn_order_key
        if new_order:
            # game_rules.md "Real time and movement": the 90/180 snap happens only at the moment a move order is
            # issued (every order clears `turn_order_key`). A destination changed under a running move -- the next
            # waypoint, or a script re-aim such as IfTargetInChargeReach -- only re-plans the turn.
            issued = regiment.turn_order_key is None
            regiment.turn_order_key = order_key
            if issued and order_key[0] in ("move", "charge"):
                self._snap_order_turn(regiment, goal)
            self._plan_turn(regiment, goal, charge=order_key[0] == "charge")
        elif order_key[0] == "charge" and self.tick_count % combat.SEGMENT_TICKS == 0:
            self._plan_turn(regiment, goal, charge=True)
        elif regiment.turn_mode is None and order_key[0] != "charge":
            self._plan_turn(regiment, goal, charge=order_key[0] == "charge")
        if regiment.reforming and not regiment.pursuing:
            # notes/reform_while_moving.md 5: turning is suspended while re-forming (except in a pursuit). A wheel or
            # a charge keeps translating along the current facing (at the re-form's halved speed); a halted turn
            # does not translate at all. The planned turn resumes once the re-form ends.
            mode = regiment.turn_mode
            if mode == "halted" and order_key[0] != "charge":
                step = 0
        elif (mode := self._step_turn(regiment, scale)) is None or regiment.turns_on_the_spot:
            pass  # no turn this tick, or no speed penalty: translates at full speed while turning
        elif mode == "wheel":
            step /= 2
        elif mode != "charge_reaim":
            step = 0  # a charge re-aim keeps full anchor speed (game_rules.md, model_movement.md)
        if step <= 0:
            regiment.route_speed = 0.0
            return mode is not None
        if arrive and steering_target == target and distance <= step and abs(self._turn_delta(regiment.direction, goal)) <= 10:
            regiment.route_speed = distance
            regiment.x, regiment.y = target
            regiment.target_x = regiment.target_y = None
            regiment.free_charging = False
            return False
        angle = regiment.direction * math.tau / formation.FULL_TURN
        regiment.route_speed = min(step, distance)
        regiment.x += math.sin(angle) * min(step, distance)
        regiment.y += math.cos(angle) * min(step, distance)
        return True

    def _advance_move(self, regiment: Regiment, target: Point, step: float, order_key: TurnKey, scale: float) -> bool:
        """One tick of an ordinary point move (notes/movement_formation.md 1.4).

        The move re-plans only at intervals: after each plan a countdown of `min(2 d, 150)` (`d` = distance to the
        current waypoint, or to the steer point while steering round an obstruction) falls by `s_rlmv` every tick,
        and the next plan comes when it goes negative or when a turn the last plan owed has finished. At a plan:
        a needed turn over 64/512 starts a halted turn owing **half** the angle; otherwise, while `d > 32` (or the
        route follows a unit on its last leg) the unit keeps moving, wheeling if the turn is 11/512 or more and
        `d > 32` (a smaller one is absorbed); within 32 units it goes on to its next waypoint, or with none left
        halts and re-forms. A point move therefore stops within 32 units of its point. Between plans it translates
        along its facing (half speed in a wheel, none in a halted turn). While re-forming plans still run but the
        turn is suspended (notes/reform_while_moving.md 5, notes/close_point_move.md 2). Deviation: within 32 units
        the move halts even when the turn exceeds 64/512 (see the halt branch).
        """
        steering_target = self._steering_target(regiment, target, order_key)
        if steering_target is None:
            regiment.route_speed = 0.0
            regiment.target_x = regiment.target_y = None
            regiment.waypoints.clear()
            regiment.avoid_target = None
            regiment.route_side, regiment.route_planned_for = 0, None
            return False
        dx, dy = steering_target[0] - regiment.x, steering_target[1] - regiment.y
        distance = math.hypot(dx, dy)
        goal = round(math.atan2(dx, dy) * 512 / math.tau) % 512 if distance > 1e-9 else regiment.direction
        if order_key != regiment.turn_order_key:
            # game_rules.md "Real time and movement": the 90/180 snap only when a move order is issued (every order
            # clears `turn_order_key`); a new waypoint or a script re-aim only brings the next plan forward.
            if regiment.turn_order_key is None:
                self._snap_order_turn(regiment, goal)
            regiment.turn_order_key = order_key
            regiment.move_plan_countdown = -1.0
        suspended = regiment.reforming and not regiment.pursuing
        # A halted turn steps first: it does not translate or run down the countdown, and the tick it ends in
        # re-plans (notes/close_point_move.md 2). While re-forming it does nothing at all.
        halted_tick = regiment.move_turn_owed and regiment.turn_mode == "halted"
        if halted_tick and not suspended:
            self._step_turn(regiment, scale)
        turn_finished = regiment.move_turn_owed and regiment.turn_mode is None
        if (regiment.move_plan_countdown < 0 and not halted_tick) or turn_finished:
            regiment.move_plan_countdown = min(2 * distance, 150.0)
            regiment.move_turn_owed = False
            delta = self._turn_delta(regiment.direction, goal)
            current = (regiment.target_x, regiment.target_y)
            follows_last_leg = regiment.route_follows_unit and (not regiment.waypoints or regiment.waypoints == [current])
            if abs(delta) > 64 and (distance > 32 or follows_last_leg):
                self._owe_turn(regiment, delta / 2, "halted", 8)
            elif distance > 32 or follows_last_leg:
                if abs(delta) >= 11 and distance > 32:
                    self._owe_turn(regiment, delta, "wheel", 7)
                elif abs(delta) < 11:
                    regiment.direction = goal  # absorbed
                    regiment.turn_mode = None
            else:
                # Within 32 units: on to the next waypoint, or halt and re-form. PROVISIONAL deviation
                # (notes/close_point_move.md 3, 6): the original tests the turn first, so a point this close but more
                # than 64/512 off the facing starts a halted turn; when it lies inside the pivot circle the unit then
                # spins forever. This engine halts here whatever the turn, which changes only those endless cases. A Ctrl-queued route keeps its current
                # destination at the head of the list; a planned route keeps only the legs still to come.
                if regiment.waypoints and regiment.waypoints[0] == current:
                    regiment.waypoints.pop(0)
                regiment.route_speed = 0.0
                regiment.turn_mode = None
                if regiment.waypoints:
                    regiment.target_x, regiment.target_y = regiment.waypoints[0]
                    regiment.move_plan_countdown = -1.0
                    regiment.turn_order_key = ("move", regiment.target_x, regiment.target_y)
                    return True
                regiment.target_x = regiment.target_y = None
                regiment.turn_order_key = None
                if regiment.models > 0 and not regiment.in_melee:
                    self.reform_to_ranks(regiment, regiment.ranks)
                return False
        if halted_tick:
            step = 0  # the halted turn already stepped this tick
        elif suspended:
            if regiment.turn_mode == "halted":
                step = 0  # does nothing while re-forming; a wheel translates without turning
        elif (mode := self._step_turn(regiment, scale)) is None or regiment.turns_on_the_spot:
            pass
        elif mode == "wheel":
            step /= 2
        else:
            step = 0
        if not (regiment.move_turn_owed and regiment.turn_mode == "halted"):
            regiment.move_plan_countdown -= regiment.speed_per_tick * 16 / MOVING_FREELY_K * scale
        if step <= 0:
            regiment.route_speed = 0.0
            return True
        angle = regiment.direction * math.tau / formation.FULL_TURN
        regiment.route_speed = step
        regiment.x += math.sin(angle) * step
        regiment.y += math.cos(angle) * step
        return True

    @staticmethod
    def _owe_turn(regiment: Regiment, delta: float, mode: str, shift: int) -> None:
        """Start a gradual turn of `delta` (signed, 1/512 turn) that the next plan waits for."""
        regiment.turn_goal = (regiment.direction + delta) % 512
        regiment.turn_remaining = abs(delta)
        regiment.turn_sign = 1 if delta > 0 else -1
        regiment.turn_mode, regiment.turn_shift = mode, shift
        regiment.move_turn_owed = True

    def _steering_target(self, regiment: Regiment, target: Point, order_key: TurnKey) -> Point | None:
        """Where the regiment heads this update (notes/obstacle_steering.md). The two-trial route plan runs only
        when the order or the waypoint changes (a new order, the next waypoint) and when live steering's steer
        point leaves the permitted area; every update, live steering turns round what lies ahead on the side the
        plan chose. Distances and scans use the front-rank reference point (section 2).

        A failed plan at an order or a new waypoint ends the move (the regiment halts); a failed boundary-forced
        re-plan while moving pauses it 54 updates with its order kept (section 5 "On failure"). A same-side unit
        the relationship filter answers with "pause" also pauses the mover 54 updates (section 6 item 3). Flight
        steers round scenery only and ignores the battle edge."""
        start = self.route_reference_point(regiment)
        if math.dist(start, target) < 1e-9:
            return target
        fleeing = order_key[0] == "flee"
        footprints, units = self._route_footprints(regiment, order_key)
        own_radius = float(int(regiment.bounding_radius()))

        def blocks(trial: bool, mover_speed: float | None = None) -> Callable[[steering.Footprint], bool]:
            def test(footprint: steering.Footprint) -> bool:
                other = units.get(footprint.key)
                return other is None or self.route_unit_relation(regiment, other, trial, mover_speed) == "block"
            return test

        def permitted(point: Point) -> bool:
            return not any(boundary.forbidden(point) for boundary in self.navigation_boundaries
                           if boundary.solid or boundary.inverse or (boundary.battle_edge and not fleeing))

        if regiment.route_planned_for != (order_key, target):
            # At a new order the mover has no move under way yet, so its effective speed is 0 (section 6).
            new_order = regiment.route_planned_for is None or regiment.route_planned_for[0] != order_key
            regiment.route_planned_for = (order_key, target)
            plan = steering.plan(start, int(regiment.direction) % 512, target, footprints, own_radius,
                                 blocks(True, 0.0 if new_order else None), permitted)
            regiment.route_side = plan.side
            if not plan.ok:
                self._warn_blocked_route(regiment, order_key, start, target, footprints, own_radius, plan)
                regiment.avoid_target = None
                return target if fleeing else None
        pause_hit = steering.scan(start, target, footprints, own_radius,
                                  lambda fp: fp.key in units and self.route_unit_relation(
                                      regiment, units[fp.key], False) == "pause")
        if pause_hit is not None and steering.scan(start, target, footprints, own_radius, blocks(False)) is None:
            self.pause_route(regiment)
            return target
        steer = steering.steer(start, target, footprints, own_radius, blocks(False),
                               remembered_side=regiment.route_side, facing=int(regiment.direction) % 512)
        if steer is None:
            regiment.route_side = 0
            regiment.avoid_target = None
            return target
        regiment.route_side = steer.side
        if steer.gave_up:
            regiment.avoid_target = None
            return target
        if not permitted(steer.point):
            plan = steering.plan(start, int(regiment.direction) % 512, target, footprints, own_radius,
                                 blocks(True), permitted)
            if not plan.ok:
                self.pause_route(regiment)
                return target
            regiment.route_side = plan.side
            steer = steering.steer(start, target, footprints, own_radius, blocks(False),
                                   remembered_side=regiment.route_side, facing=int(regiment.direction) % 512)
            if steer is None or steer.gave_up:
                return target
        regiment.avoid_target = steer.point
        return steer.point

    def _route_footprints(self, regiment: Regiment, order_key: TurnKey
                          ) -> tuple[list[steering.Footprint], dict[str, Regiment]]:
        """Live footprints in collision-object order (solid scenery, buildings, then the other regiments by their
        collision centre), and the regiments behind the unit footprints. A charge's own target and routing regiments are
        not obstacles (notes/obstacle_steering.md section 3); flight steers round units too
        (notes/flight_solid_obstacles.md 3)."""
        footprints: list[steering.Footprint] = []
        for index, obj in enumerate(self.objects):
            flags = {str(flag).casefold() for flag in obj.get("status") or ()}
            if {"os_active", "os_solid"}.issubset(flags):
                footprints.append(steering.Footprint(f"object:{index}", float(obj.get("x") or 0),
                                                     float(obj.get("y") or 0), float(int(obj.get("radius") or 0))))
        for building in self.buildings:  # notes/obstacle_steering.md 3: a building blocks unless it is the target
            if order_key[0] == "charge" and order_key[1] == building.identifier:
                continue
            footprints.append(steering.Footprint(building.identifier, building.x, building.y, float(building.radius)))
        units: dict[str, Regiment] = {}
        for other in self.regiments.values():
            if (other is regiment or not other.active or other.routing
                    or (order_key[0] == "charge" and order_key[1] == other.identifier)):
                continue
            key = f"unit:{other.identifier}"
            centre = self.formation_centre(other)
            footprints.append(steering.Footprint(key, centre[0], centre[1], float(int(other.bounding_radius())),
                                                 troops=not (other.is_wagon or other.hud_class in ("art", "mon"))))
            units[key] = other
        return footprints, units

    def _warn_blocked_route(self, regiment: Regiment, order_key: TurnKey, start: Point, target: Point,
                            footprints: Sequence[steering.Footprint], own_radius: float, plan: steering.Plan) -> None:
        """One battle-log warning per unit, order and first obstacle when both route trials fail."""
        hit = steering.scan(start, target, footprints, own_radius, lambda footprint: True)
        obstacle = hit.footprint.key if hit is not None else "-"
        warning_key = (regiment.identifier, order_key, obstacle)
        if self.script_logger is None or not self.script_logger.enabled or warning_key in self._warned_blocked_routes:
            return
        self._warned_blocked_routes.add(warning_key)
        self.script_logger.write_route_warning(
            max(0, self.update_count - 1), unit_id=regiment.identifier, order=str(order_key[0]),
            start=start, target=target, obstacle=obstacle, detour_scores=plan.scores,
            outside_boundary=any(boundary.forbidden(start) for boundary in self.navigation_boundaries
                                 if boundary.solid or boundary.inverse or boundary.battle_edge))

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
            if cell is not None and model.freeze_ticks <= 0:
                # notes/grid_gap_closing.md 0: arrival is an event for awake models only (at-rest models in a melee
                # are skipped above and never re-tested).
                if math.hypot(tx - new_position[0], ty - new_position[1]) <= battle_grid.ARRIVAL_DISTANCE:
                    if not model.arrived:
                        battle_grid.on_arrival(self, regiment, model)
                else:
                    model.arrived = False
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
        """Drive a re-forming unit's figures (notes/reform_while_moving.md 2-3). The unit's own translation has
        already been carried onto them; this adds each figure's re-form step on top.

        Walk-back mode (Rally) uses the ordinary catch-up walk and ends on the first tick every figure is at
        rest. Shuffle mode uses the flat mover of section 3: a figure in a timed pause counts down and does
        not step; an at-rest figure is skipped; otherwise, on its first step and whenever its countdown has run
        out, it re-aims: the offset to its slot, each component rounded (an exact half rounds down), is zero
        -> it arrives on the slot, at rest, its heading snapped to the unit facing; else its heading is the
        bearing to the slot and its step `s_rlmv / 8` along it, divided by `7 - d` when `d` (the truncated
        distance) is below 6 and then capped at 1 world unit per axis. The report notes the original caps only
        positive components; this engine caps both signs (section 3 allows either). The countdown is set to
        `d div 2` at each re-aim and falls by `s_rlmv` every tick. The re-form ends on the first tick no
        figure stepped and none was pausing, raising "re-form complete".
        """
        if regiment.reform_walk_back:
            still_moving = self._advance_models(regiment, scale)
            if not still_moving and all(model.at_rest for model in regiment.melee_models):
                return self._finish_reform(regiment)
            return True
        targets = list(formation.place(regiment.x, regiment.y, regiment.reform_facing, regiment.reform_slots))
        facing_angle = regiment.direction * math.tau / formation.FULL_TURN
        facing_x, facing_y = math.sin(facing_angle), math.cos(facing_angle)
        s_rlmv = regiment.speed_per_tick * 16 / MOVING_FREELY_K
        current = list(regiment.positions)
        stepped = pausing = False
        for index in range(len(current)):
            model = regiment.melee_models[index]
            if model.freeze_ticks > 0 or model.rout_pause_ticks > 0:
                if model.freeze_ticks > 0:
                    model.freeze_ticks -= 1
                else:
                    model.rout_pause_ticks -= 1
                pausing = True
                continue
            if model.at_rest:
                continue
            px, py = current[index]
            tx, ty = targets[index]
            if model.reform_step is None or model.reaim_countdown <= 0:
                ox, oy = _round_half_down(tx - px), _round_half_down(ty - py)
                if ox == 0 and oy == 0:
                    current[index] = (tx, ty)
                    model.at_rest = True
                    model.reform_step = None
                    model.current_speed = model.distance_budget = 0.0
                    model.heading_x, model.heading_y = facing_x, facing_y
                    continue
                length = math.hypot(ox, oy)
                distance = int(length)
                model.heading_x, model.heading_y = ox / length, oy / length
                sx, sy = model.heading_x * s_rlmv / 8, model.heading_y * s_rlmv / 8
                if distance < REFORM_DECEL_DISTANCE:
                    sx, sy = sx / (7 - distance), sy / (7 - distance)
                    sx = max(-REFORM_STEP_CAP, min(REFORM_STEP_CAP, sx))
                    sy = max(-REFORM_STEP_CAP, min(REFORM_STEP_CAP, sy))
                model.reform_step = (sx, sy)
                model.reaim_countdown = distance // 2
            sx, sy = model.reform_step
            nx, ny = px + sx * scale, py + sy * scale
            model.reaim_countdown -= s_rlmv * scale
            # game_rules.md "Formation changes" point 3: stepping onto an at-rest comrade about half a
            # spacing away, heading into it, exchanges the two slot assignments (the walker inherits the
            # comrade's place and stops; the comrade wakes and walks to the walker's old slot).
            other = self._swap_partner(current, targets, index, nx, ny, model.heading_x, model.heading_y)
            if other is not None:
                slots = regiment.reform_slots
                slots[index], slots[other] = slots[other], slots[index]
                targets[index], targets[other] = targets[other], targets[index]
                partner = regiment.melee_models[other]
                partner.at_rest = False
                partner.reform_step = None
                model.at_rest = True
                model.reform_step = None
                model.current_speed = model.distance_budget = 0.0
                stepped = True
                continue
            current[index] = (nx, ny)
            stepped = True
        regiment.positions = current
        if not stepped and not pausing:
            return self._finish_reform(regiment)
        return True

    @staticmethod
    def end_reform_for_engagement(regiment: Regiment) -> None:
        """Engaging in close combat ends a re-form at once, without "re-form complete" (notes/reform_while_moving.md
        8): the figures keep their positions, back in raster order, and go to their close-combat cells."""
        if not regiment.reforming:
            return
        raster_index = {offset: index for index, offset in
                        enumerate(formation.block_slots(regiment.models, regiment.ranks))}
        if (len(regiment.reform_slots) == len(regiment.positions)
                and all(slot in raster_index for slot in regiment.reform_slots)):
            order = sorted(range(len(regiment.reform_slots)), key=lambda i: raster_index[regiment.reform_slots[i]])
            regiment.positions = [regiment.positions[i] for i in order]
            regiment.melee_models = [regiment.melee_models[i] for i in order]
        regiment.reforming = regiment.reform_walk_back = False
        regiment.reform_slots = []
        for model in regiment.melee_models:
            model.reform_step = None

    def _finish_reform(self, regiment: Regiment) -> bool:
        """End a settled re-form: put the figures back in raster order and raise "re-form complete". Returns
        whether figures are still moving (a casualty during the re-form starts a fresh re-slotting instead)."""
        # The rest of the engine (`_advance_models`, `model_positions`) assumes `positions[i]` belongs to
        # `formation.block_slots`'s raster slot `i`; restore that ordering now that the re-slotting
        # permutation has done its job, or the very next tick's ordinary catch-up walk would immediately
        # send every model chasing a different slot again.
        raster_index = {offset: index for index, offset in
                        enumerate(formation.block_slots(regiment.models, regiment.ranks))}
        if any(slot not in raster_index for slot in regiment.reform_slots):
            # A casualty during the re-form left slots of the old, larger layout: re-slot the survivors into the
            # current layout from where they stand instead of mapping slots that no longer exist.
            self._begin_reform(regiment, regiment.ranks)
            return True
        order = sorted(range(len(regiment.reform_slots)), key=lambda i: raster_index[regiment.reform_slots[i]])
        regiment.positions = [regiment.positions[i] for i in order]
        regiment.melee_models = [regiment.melee_models[i] for i in order]
        regiment.reforming = False
        regiment.reform_walk_back = False
        regiment.reform_slots = []
        self.events.append(BattleEvent(
            f"{regiment.name} completes its re-form.", "reform_complete",
            regiment=regiment.identifier))
        # notes/movement_formation.md 1.2, 9: the unit sends itself event 0x34 when its models have settled.
        self.event_bus.queue_event(regiment.identifier, interpreter.Event(code=0x34))
        return False

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
        special_shot = regiment.shooting_code in {14, 15} or (regiment.shooting_code == 17 and regiment.hud_class != "arch")
        volley_divisor = 1 if regiment.hud_class == "art" or special_shot else 4
        # A script's broadcast holds until the unit's activity changes (notes/script_animation_sound.md,
        # 0.1); a model's own request beats it for one update (0.2).
        if regiment.script_action and regiment.script_action_key != regiment.activity_key():
            regiment.script_action = 0
        for model_index, model in enumerate(regiment.melee_models):
            if model.own_request:
                requested, model.own_request = model.own_request, 0
            elif regiment.script_action:
                requested = regiment.script_action
            elif regiment.in_melee:
                requested = animation.FIGHT if model.opponent is not None else animation.WEAPON_READY
            elif regiment.volley_countdown is not None and (regiment.hud_class != "art" and not special_shot or model_index == 0):
                requested = animation.SHOOT
            elif not model.at_rest:
                requested = animation.WALK
            else:
                requested = animation.IDLE
            animation.step(model, requested, self.rng, regiment.animation_family)
            self._slew_drawn_facing(regiment, model, wagon)
            if model.fire_event:
                self.event_bus.animation_event_step(regiment.identifier, model_index)
            # Each model's fire event decrements the volley countdown once; a post is issued each
            # time the new countdown value is a multiple of the divisor (game_rules.md 8.1).
            # Reload does not gate this: it was stamped at order time, so reload > 0 is normal
            # mid-volley. The countdown > 0 guard prevents second-cycle decrements.
            if model.fire_event and regiment.volley_countdown is not None and regiment.volley_countdown > 0:
                regiment.volley_countdown -= 1
                if regiment.volley_countdown % volley_divisor == 0:
                    regiment.fire_posts += 1
                    regiment.fire_post_positions.append(regiment.positions[model_index])
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

    @property
    def decided(self) -> bool:
        """An objective decided the battle; it keeps running until the player leaves (battle_end_objectives.md 6)."""
        return self.objectives is not None and self.objectives.decided is not None

    @property
    def can_leave(self) -> bool:
        """The tent button is shown: after the decision, or from the impossible mission's first warning (section 7)."""
        return self.objectives is not None and self.objectives.tent and self.result is None

    def leave(self) -> None:
        """The tent button (section 7): the battle stops, the final pass runs and the result is fixed."""
        if self.objectives is None or not self.can_leave:
            raise ValueError("the battle cannot be left before it is decided")
        self.objectives.finish(self)
        self.result = "defeat" if self.objectives.defeat else "victory"
        self.events.append(BattleEvent("The army leaves the battlefield.", "result", result=self.result,
                                       counts=self.side_counts(), letter=self.objectives.decided))

    def open_book(self) -> None:
        """The minimap book (notes/battle_end_objectives.md 6 and 8): the objective list before the decision,
        afterwards "Mission complete." and the speech again. Shown from the next tick."""
        if self.objectives is None:
            return
        if self.decided and not self.objectives.defined("U"):
            self.objectives.announce(self, self.pending_feedback)
            return
        for text_id in self.objectives.book_text_ids():
            self.pending_feedback.append(BattleEvent(f"message {text_id}", "message", text_id=text_id))

    def react(self, identifier: str, code: int) -> None:
        """A React reaction outside the unit's script (an objective's pickup or warning)."""
        if self.interpreter is not None:
            self.interpreter.react(identifier, code)

    def broadcast_script_event(self, code: int) -> None:
        """Queue a script event to every unit (the siege Z rule's event 0x38)."""
        for identifier in list(self.regiments):
            self.event_bus.queue_event(identifier, interpreter.Event(code=code), checked=True)

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

    def remove_from_play(self, regiment: Regiment) -> None:
        """``regiment`` leaves the battle alive (it routed off the map, or a script removed it): it is marked fled,
        keeping its models as routed, and each model pays the kill credit it still carries
        (notes/casualty_bookkeeping.md 2.1)."""
        if regiment.fled:
            return
        regiment.fled = True
        combat.pay_removal_credits(self, regiment)

    def _resolve_collisions(self, deployment_id: str | None = None) -> None:
        """Push regiments apart (a simplified push-apart; game_rules.md, "Routes, collisions and visibility"), not
        the polygon obstruction routing (`Nav*`). In the battle phase the pass runs for the units whose collision
        re-check state is on, in identifier order (`_push_apart_pass`); during deployment only the dragged
        regiment yields to the regiments it overlaps, so scripted deployments that already overlap (BF001's
        Grudgebringer cavalry and infantry) stay where the script placed them.
        """
        regiments = [self.regiments[key] for key in sorted(self.regiments) if self.regiments[key].active]
        if deployment_id is None:
            for regiment in regiments:
                self._correct_boundaries(regiment)
                self._correct_solid_objects(regiment)
                self._correct_buildings(regiment)
            for mover in regiments:
                if mover.collision_recheck:
                    self._recheck_carry.discard(mover.identifier)  # its own pass consumes the state
                    if self.interpreter is None:  # no scripted contact pass consumes the state afterwards
                        mover.collision_recheck = False
                    self._push_apart_pass(mover, regiments)
            return
        # notes/deployment.md 2: collision correction follows the zone clipping, with no final zone clamp.
        dragged = self.regiments[deployment_id]
        self._correct_boundaries(dragged)
        self._correct_solid_objects(dragged)
        self._correct_buildings(dragged)
        for other in regiments:
            if other is dragged or other.in_melee or dragged.in_melee:
                continue
            self._push_pair(dragged, other, 1.0, 0.0)

    def _push_apart_pass(self, mover: Regiment, regiments: Sequence[Regiment]) -> None:
        """The push-apart rows of the collision pass for one unit (notes/script_behaviours.md 2.2, "Push apart,
        exactly"): a marked unit is not touched at all; a unit in melee neither pushes nor is pushed; a pair that
        can fight never pushes apart (it makes contact instead), except that a war machine or wagon pair is pushed
        apart when the mover is broken or in a catch-up (walk-back) re-form; any other pair is pushed apart unless
        either unit is broken or pursuing. Only the unit running the pass moves, away from the other centre; the
        other unit's re-check state goes on and it moves itself in its own pass. One friendly push per pass; a
        wagon mover is never moved; a push of a charging mover by a footprint within +-45 degrees of its facing
        ends the charge. Not modelled: fanatic footprints (the engine has no fanatic model, so none is skipped
        here; notes/fanatic_collisions.md 2)."""
        if mover.in_melee or self._marked(mover):
            return
        pushed = False
        for other in regiments:
            if other is mover or other.in_melee or other.routing or self._marked(other):
                continue
            if may_engage(mover, other):
                machine = (mover.is_wagon or mover.hud_class == "art") or (other.is_wagon or other.hud_class == "art")
                if not (machine and (mover.routing or (mover.reforming and mover.reform_walk_back))):
                    if machine and self._circles_overlap(mover, other):
                        self._carry_recheck(other)  # notes/script_behaviours.md 2.2: U re-check on, contact or not
                    continue
            elif mover.routing or mover.pursuing or other.pursuing:
                continue
            if pushed or mover.is_wagon:
                if self._circles_overlap(mover, other):
                    self._carry_recheck(mover, other)
                continue
            pushed = self._push_self(mover, other)

    @staticmethod
    def _circles_overlap(first: Regiment, second: Regiment) -> bool:
        return math.hypot(first.x - second.x, first.y - second.y) < first.bounding_radius() + second.bounding_radius()

    def _push_self(self, mover: Regiment, other: Regiment) -> bool:
        """Move `mover` away from `other` by (|o| + 2) / 2 along the line between the centres, per axis
        trunc(trunc(SIN/COS[bearing] x (o - 2) / 256) / 2) with o = trunc(distance) - both radii (negative); switch
        both re-check states on; end a charge that meets the footprint within +-45 degrees of its facing. Returns
        whether a push was made."""
        dx, dy = other.x - mover.x, other.y - mover.y
        overlap = math.trunc(math.hypot(dx, dy)) - mover.bounding_radius() - other.bounding_radius()
        if overlap >= 0:
            return False
        bearing = round(math.atan2(dx, dy) * 512 / math.tau) % 512 if (dx or dy) else 0
        angle = bearing * math.tau / 512
        shift_x = math.trunc(math.trunc(math.trunc(256 * math.sin(angle)) * (overlap - 2) / 256) / 2)
        shift_y = math.trunc(math.trunc(math.trunc(256 * math.cos(angle)) * (overlap - 2) / 256) / 2)
        if mover.attack_target is not None and abs(self._turn_delta(mover.direction, bearing)) < 64:
            self._end_charge_on_obstruction(mover, "a friendly unit")
        self._translate_regiment(mover, shift_x, shift_y)
        self._carry_recheck(mover, other)
        return True

    def _carry_recheck(self, *regiments: Regiment) -> None:
        """Switch the re-check state on for units whose state the collision pass sets. The scripted contact sweep
        that follows clears the state of every unit it visited, so these units are switched on again after it
        (`_restore_carried_rechecks`) unless their own pass runs later in the same update and consumes it."""
        for regiment in regiments:
            regiment.collision_recheck = True
            self._recheck_carry.add(regiment.identifier)

    def _restore_carried_rechecks(self) -> None:
        for identifier in self._recheck_carry:
            self.regiments[identifier].collision_recheck = True
        self._recheck_carry.clear()

    def _push_pair(self, first: Regiment, second: Regiment, first_share: float, second_share: float) -> None:
        """Move two overlapping circles apart along their centre line, `first_share` and `second_share` of the
        overlap each, and switch both re-check states on."""
        dx, dy = second.x - first.x, second.y - first.y
        distance = math.hypot(dx, dy)
        overlap = first.bounding_radius() + second.bounding_radius() - distance
        if overlap <= 0:
            return
        ux, uy = (dx / distance, dy / distance) if distance > 1e-6 else (1.0, 0.0)
        self._translate_regiment(first, -ux * overlap * first_share, -uy * overlap * first_share)
        self._translate_regiment(second, ux * overlap * second_share, uy * overlap * second_share)
        first.collision_recheck = second.collision_recheck = True

    def _update_pursuits(self) -> None:
        """The once-per-segment pursuit update (notes/pursuit_map_edge.md 2): a pursuit stops when the target is no
        longer a live routing unit, when the chase budget runs out (not with AlwaysPursue; first min(2 x distance,
        120), then + previous distance - distance - 4), or when the probe one collision radius ahead of the front
        rank along the facing lies inside no BattleEdge area (or the battle has none). First of all, on the pursuer's
        scheduled segment with its rally-attempt state on, the restraint test (notes/pursuit_restraint.md 4): a pass
        stops the pursuit the same way; one stop is enough, so the rest of the update is skipped then."""
        edges = [boundary for boundary in self.navigation_boundaries if boundary.battle_edge]
        for regiment in self.regiments.values():
            if not regiment.pursuing or not regiment.active or regiment.routing:
                continue
            if combat.rally_check_due(regiment, self) and combat.pursuit_restraint_test(self, regiment):
                self._stop_pursuit(regiment)
                continue
            target = self.regiments.get(regiment.attack_target) if regiment.attack_target is not None else None
            if target is None or not target.active or not target.routing:
                self._stop_pursuit(regiment)
                continue
            distance = int(math.hypot(target.x - regiment.x, target.y - regiment.y))
            if regiment.pursuit_budget is None:
                regiment.pursuit_budget = min(2 * distance, 120)
            else:
                regiment.pursuit_budget += regiment.pursuit_distance - distance - 4
            regiment.pursuit_distance = distance
            if regiment.pursuit_budget <= 0 and "AlwaysPursue" not in regiment.psychology:
                self._stop_pursuit(regiment)
                continue
            facing = int(regiment.direction) % 512
            radius = int(regiment.bounding_radius())
            probe = (regiment.x + math.trunc(round(256 * math.sin(facing * math.tau / 512)) * radius / 256),
                     regiment.y + math.trunc(round(256 * math.cos(facing * math.tau / 512)) * radius / 256))
            if not any(not edge.forbidden(probe) for edge in edges):
                self._stop_pursuit(regiment)
                continue
            # Re-aim (notes/pursuit_map_edge.md 2 step 3, notes/flight_solid_obstacles.md 5): the chase point is the
            # fugitive's leading edge, its footprint centre plus one radius along its facing.
            centre = self.formation_centre(target)
            angle = int(target.direction) * math.tau / 512
            lead = float(int(target.bounding_radius()))
            regiment.pursuit_point = (centre[0] + lead * math.sin(angle), centre[1] + lead * math.cos(angle))

    def _stop_pursuit(self, regiment: Regiment) -> None:
        """Event 0x10 ("stop pursuing") to the pursuer: with behaviour scripts, its library handler shouts, stops
        and re-forms in place (notes/pursuit_map_edge.md 4); without scripts the engine does the same at once."""
        state = self.event_bus.unit_states.get(regiment.identifier)
        if self.interpreter is not None and state is not None:
            self.event_bus.queue_event(regiment.identifier, interpreter.Event(code=0x10))
            return
        regiment.pursuing = False
        regiment.rally_attempt = False  # as the Rally opcode (notes/pursuit_restraint.md 5)
        regiment.pursuit_budget = regiment.pursuit_point = None
        regiment.attack_target = regiment.charge_started_target = None
        regiment.target_x = regiment.target_y = None
        regiment.waypoints.clear()
        self.reform_to_ranks(regiment, regiment.ranks, walk_back=True)  # as Rally (notes/reform_while_moving.md 6)

    def _marked(self, regiment: Regiment) -> bool:
        state = self.event_bus.unit_states.get(regiment.identifier)
        return state is not None and bool(state.unit_flags & interpreter.LEAVING_BATTLE_FLAG)

    @staticmethod
    def _translate_regiment(regiment: Regiment, dx: float, dy: float) -> None:
        regiment.x += dx
        regiment.y += dy
        regiment.positions = [(x + dx, y + dy) for x, y in regiment.positions]

    def _end_charge_on_obstruction(self, regiment: Regiment, description: str) -> None:
        target_id = regiment.attack_target
        if target_id is None or regiment.charge_started_target != target_id:
            return
        regiment.attack_target = regiment.charge_started_target = None
        regiment.turn_order_key = regiment.turn_mode = None
        self.event_bus.queue_event(target_id, interpreter.Event(code=0x09, source=regiment.identifier))
        self.events.append(BattleEvent(
            f"{regiment.name}'s charge ends at {description}.", "charge_end",
            regiment=regiment.identifier))

    def path_obstructed(self, regiment: Regiment, goal: Point, ignore: str | None = None) -> bool:
        """Whether the straight line from the regiment's front-rank reference point to `goal` meets a blocking map
        object or unit footprint, so that the unit would steer round it (notes/target_queries.md 5.2 steps 3 and 5;
        notes/obstacle_steering.md). `ignore` names a regiment that is not an obstacle (the charge's own target)."""
        start = self.route_reference_point(regiment)
        if math.dist(start, goal) < 1e-9:
            return False
        footprints, units = self._route_footprints(regiment, ("charge", ignore or ""))

        def blocks(footprint: steering.Footprint) -> bool:
            other = units.get(footprint.key)
            return other is None or self.route_unit_relation(regiment, other, False) == "block"

        return steering.scan(start, goal, footprints, float(int(regiment.bounding_radius())), blocks) is not None

    def on_blocked_ground(self, regiment: Regiment) -> bool:
        """Whether the regiment's position (its front-rank reference point) lies in a blocking region: outside a
        solid area, inside an inverse-solid one or outside the battle edge (notes/movement_formation.md 3.6,
        notes/target_queries.md 5.2 check 11)."""
        point = self.route_reference_point(regiment)
        return any(boundary.forbidden(point) for boundary in self.navigation_boundaries
                   if boundary.solid or boundary.inverse or boundary.battle_edge)

    def _correct_boundaries(self, regiment: Regiment) -> None:
        if regiment.routing:
            return  # notes/flight_solid_obstacles.md 4: routing units get no boundary correction of any kind
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
            self._translate_regiment(regiment, dx, dy)
            regiment.collision_recheck = True
            if not regiment.pursuing:  # notes/pursuit_map_edge.md 3: the correction only pushes a pursuer
                self._end_charge_on_obstruction(regiment, "a movement boundary")

    def _advance_on_building(self, regiment: Regiment, building: buildings.Building, move_scale: float,
                             scale: float) -> bool:
        """A charge at a building walks at its centre (not the far side used for regiments); the charge counts
        as started once the distance less the building's radius is within charge reach
        (notes/building_units.md 6). A destroyed building cannot be charged."""
        if building.destroyed or not regiment.active:
            regiment.attack_target = regiment.charge_started_target = None
            return False
        centre = (building.x, building.y)
        distance = math.hypot(building.x - regiment.x, building.y - regiment.y)
        if regiment.charge_started_target != building.identifier and distance - building.radius <= regiment.charge_reach:
            for model in regiment.melee_models:
                model.freeze_ticks = (model.stagger & 7) + 1
                model.current_speed = 0.0
            regiment.charge_started_target = building.identifier
        return self._advance_toward(regiment, centre, regiment.speed_for_mode(CHARGING_K) * move_scale, arrive=False,
                                    order_key=("charge", building.identifier), scale=scale)

    def building_at(self, x: float, y: float) -> str | None:
        """Identifier of the standing building whose footprint contains the point (a click target), or None."""
        return next((b.identifier for b in self.buildings if not b.destroyed and b.contains(x, y)), None)

    def order_attack_building(self, identifier: str, building_id: str) -> None:
        """Order a player regiment to charge a standing building (notes/building_units.md 6): with behaviour
        scripts the order is event 0x04 with the building as source, otherwise the regiment charges at once.
        Destroyed buildings cannot be targeted."""
        self._require_battle_order()
        regiment = self.regiments[identifier]
        building = self.building_index.get(building_id)
        if regiment.side != Side.PLAYER:
            raise ValueError(f"{identifier} is not player-controlled")
        if building is None or building.destroyed:
            raise ValueError("attack target must be a standing building")
        if (regiment.routing or regiment.pursuing or regiment.held or regiment.braced or regiment.anchored
                or regiment.assaulting_building is not None):
            raise ValueError(f"{identifier} cannot be ordered to attack")
        if self._hold_while_reforming(regiment, ("order_attack", building_id)):
            return
        regiment.target_x = regiment.target_y = None
        regiment.clear_shooting()
        regiment.free_charging = False
        regiment.turn_order_key = None
        if self.interpreter is not None:
            self.event_bus.queue_event(identifier, interpreter.Event(code=0x04, source=building_id))
            return
        regiment.attack_target = building_id
        regiment.charge_started_target = None

    def release_building_assaults(self, building_id: str) -> None:
        """Every regiment fighting or charging the building lets go of it (the building fell)."""
        for regiment in self.regiments.values():
            if regiment.assaulting_building == building_id:
                regiment.assaulting_building = None
            if regiment.attack_target == building_id:
                regiment.attack_target = regiment.charge_started_target = None

    def _correct_buildings(self, regiment: Regiment) -> None:
        """Building footprints against a regiment (notes/building_units.md 5; notes/script_behaviours.md 2.2). A
        regiment that is not charging or fighting is pushed clear. With behaviour scripts running, a charging
        regiment overlapping a building is not pushed: its pass records the contact and raises 0x0B, and the contact
        handler decides (assault on its own target, charge ends on any other); the pass runs only while the unit's
        collision re-check state is on. Without scripts the engine decides at once. A destroyed building keeps its
        footprint. PROVISIONAL: the regiment is pushed by the circle of its bounding radius against the rectangle."""
        if regiment.routing:
            return
        centre = self.formation_centre(regiment)
        radius = regiment.bounding_radius()
        state = self.event_bus.unit_states.get(regiment.identifier) if self.interpreter is not None else None
        for building in self.buildings:
            if regiment.assaulting_building == building.identifier:
                continue
            push = building.penetration(centre[0], centre[1], radius)
            if push is None:
                continue
            charging = regiment.attack_target is not None
            if state is not None and charging:
                if regiment.collision_recheck and not state.contact_latch:
                    regiment.collision_recheck = False
                    state.contact_record = building.identifier
                    self.event_bus.queue_event(regiment.identifier, interpreter.Event(code=0x0B), checked=True)
                continue
            if state is None and charging and regiment.attack_target == building.identifier \
                    and regiment.charge_started_target == building.identifier and not building.destroyed:
                self.begin_building_assault(regiment, building)
                continue
            if state is None and charging and regiment.charge_started_target == regiment.attack_target:
                self._end_charge_on_obstruction(regiment, f"the {building.name}")
            self._translate_regiment(regiment, push[0], push[1])
            centre = centre[0] + push[0], centre[1] + push[1]

    def begin_building_assault(self, regiment: Regiment, building: buildings.Building) -> None:
        """The regiment starts fighting the building: it halts at the footprint, its charge is over and it strikes
        in its own Initiative segment until the building falls (notes/building_units.md 4)."""
        regiment.assaulting_building = building.identifier
        regiment.attack_target = regiment.charge_started_target = None
        regiment.target_x = regiment.target_y = None
        regiment.waypoints.clear()
        self.events.append(BattleEvent(f"{regiment.name} storms the {building.name}!", "building_assault",
                                       regiment=regiment.identifier, building=building.identifier))

    def end_charge_at_building(self, regiment: Regiment, building: buildings.Building) -> None:
        """A charge that touched a building other than its target ends there, with event 0x09 to its target."""
        self._end_charge_on_obstruction(regiment, f"the {building.name}")

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
            if regiment.charge_started_target == regiment.attack_target and regiment.attack_target is not None:
                bearing = round(math.atan2(ox - centre[0], oy - centre[1]) * 512 / math.tau) % 512
                if abs(self._turn_delta(regiment.direction, bearing)) <= 64:
                    self._end_charge_on_obstruction(regiment, "solid scenery")
            push = (radius - distance) / 2
            shift_x, shift_y = ux * push, uy * push
            self._translate_regiment(regiment, shift_x, shift_y)
            centre = centre[0] + shift_x, centre[1] + shift_y

    def _reroute_flight(self, regiment: Regiment) -> None:
        """The flight re-route of a flee period (notes/flight_solid_obstacles.md 3), from the current facing: probe
        256 units ahead, snap it clear of solid and inverse-solid areas (the BattleEdge is not used); a probe that
        moved, or a line to it crossing such a boundary, turns the heading 22.5 degrees beyond the bearing to the
        snapped probe in the turning direction (clockwise when head-on); a clear probe becomes the flee point and
        footprint steering (units included) may deflect it. Stops when the heading holds or after a full turn of
        changes; the facing is set at once."""
        areas = [boundary for boundary in self.navigation_boundaries if boundary.solid or boundary.inverse]
        footprints, units = self._route_footprints(regiment, ("flight",))
        own_radius = float(int(regiment.bounding_radius()))
        front = (regiment.x, regiment.y)

        def blocks(footprint: steering.Footprint) -> bool:
            other = units.get(footprint.key)
            return other is None or self.route_unit_relation(regiment, other, False) == "block"

        heading = int(regiment.direction) % 512
        total = 0
        point: Point | None = None
        for _ in range(64):
            probe = (front[0] + round(256 * math.sin(heading * math.tau / 512)),
                     front[1] + round(256 * math.cos(heading * math.tau / 512)))
            snapped = probe
            for area in areas:
                if area.forbidden(snapped):
                    snapped = area.nearest(snapped)
            if snapped == probe and navigation.first_crossing(front, probe, areas) is None:
                point = probe
                steer = steering.steer(front, probe, footprints, own_radius, blocks, facing=heading)
                new_heading = steer.heading if steer is not None and not steer.gave_up else heading
            else:
                point = None
                bearing = steering.bearing(front, snapped)
                clockwise = (bearing - heading) % 512 <= 256
                new_heading = (bearing + 32) % 512 if clockwise else (bearing - 32) % 512
            if new_heading == heading:
                break
            change = abs(new_heading - heading) % 512
            total += min(change, 512 - change)
            heading = new_heading
            if total >= 512:
                break
        regiment.direction = heading
        if point is None or steering.bearing(front, point) != heading:
            point = (front[0] + 256 * math.sin(heading * math.tau / 512), front[1] + 256 * math.cos(heading * math.tau / 512))
        regiment.flee_x, regiment.flee_y = point

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
                if not regiment.flight_departed:
                    self._reroute_flight(regiment)
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
                regiment.rally_segment = None
