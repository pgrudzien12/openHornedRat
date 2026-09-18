"""Deterministic battle-state primitives shared by prototype frontends."""

from dataclasses import dataclass, field
import math
import random

from . import ai, combat, formation
from .battle_events import BattleEvent
from .rules import EXPECTED_WEAPON_BONUS, MISSILE_RANGES, stat_fields
from .script import load_battle

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
class Regiment:
    """A regiment anchor in BTS coordinates; its models walk to formation slots around that anchor."""

    identifier: str
    name: str
    x: float
    y: float
    direction: int
    player: bool
    target_x: float | None = None
    target_y: float | None = None
    models: int = 1
    ranks: int = 1
    sprite: str | None = None  # script troop sprite resource, e.g. "ClanRats"
    banner: str | None = None  # script banner resource
    portrait: str | None = None  # leader portrait resource
    speed_per_tick: float = DEFAULT_SPEED_PER_TICK  # BTS world units per 100 ms tick, moving freely
    positions: list = field(default_factory=list)  # current per-model (x, y); lazily seeded in formation
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

    # Combat/order state (whshr.combat, whshr.ai).
    attack_target: str | None = None  # identifier of an enemy regiment this regiment is charging
    in_melee: bool = False
    melee_group: str | None = None  # id of the shared multi-regiment fight (Battle.fights), if any
    melee_touching: frozenset = field(default_factory=frozenset)  # enemy ids this footprint touches now
    routing: bool = False  # fleeing the field; ignores orders, moves away from the nearest enemy
    fled: bool = False  # a routing regiment that has left the battlefield (removed from play)
    reload_ticks: float = 0.0  # ticks remaining before a missile regiment may shoot again
    corpses: list = field(default_factory=list)  # (x, y, direction) of models that have died, for the view

    # Traced close-combat/rally timing (game_rules.md 5.5, 6.1-6.2, 7.4), see whshr.combat.
    # The fight's own-side tally, breakdown and next break-test turn (6.1-6.2) live on
    # `Battle.fights[regiment.melee_group]`, shared by every regiment in that fight.
    original_models: int | None = None  # starting model count, for rally's casualties modifier
    melee_charging: bool = False  # true until this regiment's first strike after joining a charge (5.5)
    rally_next_segment: int | None = None  # absolute segment index of the next scheduled rally attempt (7.4)

    def __post_init__(self):
        if self.original_models is None:
            self.original_models = self.models

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
        return self.positions

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
    }


class Battle:
    """Authoritative fixed-tick state: movement, and (whshr.combat/whshr.ai) close combat, shooting,
    morale and a simple enemy AI."""

    def __init__(self, width, height, regiments, seed=DEFAULT_SEED):
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
        self.fights = {}  # group id -> {"next_test_turn", "tally": {True/False}, "breakdown": {...}}
        self._fight_seq = 0  # counter for fresh whshr.combat fight group ids
        self.result = None  # None while the battle is ongoing, else "victory" or "defeat"
        # A battle only has a win/lose condition once it actually has both sides (movement-only tests
        # and synthetic battles commonly field only one side, which must never auto-resolve).
        self._has_enemy = any(not regiment.player for regiment in regiments)
        self._has_player = any(regiment.player for regiment in regiments)

    @classmethod
    def from_battle_file(cls, path, seed=DEFAULT_SEED):
        return cls.from_script(load_battle(path), seed=seed)

    @classmethod
    def from_script(cls, source, seed=DEFAULT_SEED):
        """Build the battle from a loaded BTS/MRC script; repeated unit ids get ``#2``, ``#3``... suffixes."""
        field_data = source["field"]
        regiments, used = [], set()
        armies = [(army, False) for army in source["armies"]]
        armies.extend((army, True) for army in (source["merc"] or {}).get("armies", []))
        for army, player in armies:
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
                regiments.append(Regiment(
                    identifier, unit["name"], float(position["x"]), float(position["y"]),
                    int(position.get("dir") or 0) % 512, player, models=models, ranks=ranks,
                    sprite=(unit.get("sprites") or "").split(",", 1)[0].strip() or None,
                    banner=unit.get("banner") or None,
                    portrait=(unit.get("leader") or {}).get("portrait") or None,
                    speed_per_tick=speed_per_tick(profile.get("M"), profile.get("I")),
                    **_decode_combat_profile(unit),
                ))
        return cls(field_data["width"], field_data["height"], regiments, seed=seed)

    def order_move(self, identifier, x, y):
        regiment = self.regiments[identifier]
        if not regiment.player:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        if not 0 <= x <= self.width or not 0 <= y <= self.height:
            raise ValueError("destination is outside the battlefield")
        regiment.attack_target = None
        regiment.target_x, regiment.target_y = float(x), float(y)

    def order_attack(self, identifier, target_id):
        """Order a player regiment to charge an enemy regiment into contact (game_rules.md, "Charge")."""
        regiment = self.regiments[identifier]
        if not regiment.player:
            raise ValueError(f"{identifier} is not player-controlled")
        if regiment.routing:
            raise ValueError(f"{identifier} is routing and cannot be ordered")
        target = self.regiments.get(target_id)
        if target is None or target.player:
            raise ValueError("attack target must be an enemy regiment")
        if not target.active:
            raise ValueError(f"{target_id} is no longer on the field")
        regiment.target_x = regiment.target_y = None
        regiment.attack_target = target_id

    def order_halt(self, identifier):
        """Cancel the selected regiment's current movement or charge order in place."""
        regiment = self.regiments[identifier]
        if not regiment.player:
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
            }
            for identifier, regiment in self.regiments.items()
        }

    def regiment_at(self, x, y, player_only=True):
        """Identifier of the regiment whose footprint contains (x, y), or None; the closest one if several."""
        best_id, best_distance = None, None
        for regiment in self.regiments.values():
            if not regiment.active:
                continue
            if player_only and not regiment.player:
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
        ai.decide_orders(self)
        combat.refresh_melee_state(self)
        self._advance_regiments(scale, seconds)
        self._resolve_collisions()
        combat.resolve_contacts(self)
        if self.tick_count % combat.SEGMENT_TICKS == 0:
            combat.resolve_melee(self)
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
                moved = self._advance_toward(regiment, self._flee_point(regiment),
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
        regiment.direction = round(math.atan2(dx, dy) * 512 / math.tau) % 512
        if arrive and distance <= step:
            regiment.x, regiment.y = target
            regiment.target_x = regiment.target_y = None
            return False
        regiment.x += dx / distance * step
        regiment.y += dy / distance * step
        return True

    def _nearest_enemy(self, regiment):
        enemies = [r for r in self.regiments.values() if r.player != regiment.player and r.active]
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

    @staticmethod
    def _advance_models(regiment, step):
        """Walk each model toward its formation slot, never faster than the unit's speed (`MoveModels`)."""
        targets = formation.place(regiment.x, regiment.y, regiment.direction,
                                  formation.block_slots(regiment.models, regiment.ranks))
        updated, still_moving = [], False
        for (px, py), (tx, ty) in zip(regiment.positions, targets):
            dx, dy = tx - px, ty - py
            distance = math.hypot(dx, dy)
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
        for side, label in ((True, "player"), (False, "enemy")):
            regiments = [r for r in self.regiments.values() if r.player == side]
            counts[label] = {
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
        alive_enemy = any(r.active for r in self.regiments.values() if not r.player)
        alive_player = any(r.active for r in self.regiments.values() if r.player)
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
        """Push regiments under orders out of the regiments they overlap (a simplified `PushApart`;
        game_rules.md, "Routes, collisions and visibility"), not the polygon obstruction routing (`Nav*`).

        Standing regiments never give way, so scripted deployments that already overlap (BF001's Grudgebringer
        cavalry and infantry) stay where the script placed them. Pairs are visited in identifier order.
        """
        regiments = [self.regiments[key] for key in sorted(self.regiments) if self.regiments[key].active]
        for i, first in enumerate(regiments):
            for second in regiments[i + 1:]:
                if first.in_melee or second.in_melee:
                    continue
                if first.player != second.player:
                    # Opposite sides never push apart: a charging regiment must be free to close all
                    # the way to footprint contact (combat.resolve_contacts), not stop at circle
                    # distance (see resolve_contacts' CONTACT_MARGIN docstring).
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
