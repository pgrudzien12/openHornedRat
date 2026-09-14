"""Deterministic battle-state primitives shared by prototype frontends."""

from dataclasses import dataclass, field
import math

from . import formation
from .script import load_battle

TICK_SECONDS = 0.1  # the battle clock ticks every 100 ms (game_rules.md, "Battle clock")
MOVING_FREELY_K = 1.8  # k factor for unobstructed movement (game_rules.md, "Real time and movement")
# Placeholder s_rlmv for a regiment whose script has no decoded M/I profile (game_rules.md leaves
# `set:map`, `whoami` and part of `setstats` open, but every BF001 combat unit does carry `s_move`):
# trunc(4.8 x 4 + 3) / 2, the M4 I3 infantry example from game_rules.md.
DEFAULT_S_RLMV = 11.0
# World units a model may close on its formation slot in one tick before it counts as "settled" (not
# walking); small compared to a tick's travel distance so it only masks floating-point residue.
SETTLE_EPSILON = 0.05


def speed_per_tick(move_stat, initiative_stat, k=MOVING_FREELY_K):
    """World units a regiment covers in one 100 ms tick, moving freely (game_rules.md, "Real time and
    movement"): ``s_rlmv = trunc(4.8 * M + I) / 2``, then ``s_rlmv * k / 16`` units per tick. Mounts and the
    other k factors (closing, charging, fleeing) are not modelled yet; every regiment moves "freely".
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
    speed_per_tick: float = DEFAULT_SPEED_PER_TICK  # BTS world units per 100 ms tick, moving freely
    positions: list = field(default_factory=list)  # current per-model (x, y); lazily seeded in formation
    walking: bool = False  # true while the anchor or any model is still travelling
    animation_seconds: float = 0.0  # elapsed time while walking, for the frontend's frame-rate placeholder

    @property
    def moving(self):
        return self.target_x is not None

    def model_positions(self, spacing=formation.MODEL_SPACING):
        """Current per-model positions (BTS world units): seeded in formation, then advanced by `Battle.tick`."""
        if len(self.positions) != self.models:
            self.positions = formation.place(self.x, self.y, self.direction,
                                              formation.block_slots(self.models, self.ranks, spacing))
        return self.positions

    def _footprint(self):
        half_side, half_forward, centre = formation.footprint(self.models, self.ranks)
        angle = (self.direction or 0) * math.tau / formation.FULL_TURN
        cos, sin = math.cos(angle), math.sin(angle)
        return self.x - centre * sin, self.y - centre * cos, half_side, half_forward, cos, sin

    def contains(self, x, y):
        """True when a ground point lies inside the regiment's oriented block footprint."""
        cx, cy, half_side, half_forward, cos, sin = self._footprint()
        dx, dy = x - cx, y - cy
        local_side = dx * cos - dy * sin
        local_forward = dx * sin + dy * cos
        return abs(local_side) <= half_side and abs(local_forward) <= half_forward

    def bounding_radius(self):
        return formation.bounding_radius(self.models, self.ranks)


class Battle:
    """Authoritative fixed-tick state for the movement prototype."""

    def __init__(self, width, height, regiments):
        if width <= 0 or height <= 0:
            raise ValueError("battle dimensions must be positive")
        self.width = width
        self.height = height
        self.regiments = {regiment.identifier: regiment for regiment in regiments}
        if len(self.regiments) != len(regiments):
            raise ValueError("regiment identifiers must be unique")
        self.tick_count = 0

    @classmethod
    def from_battle_file(cls, path):
        return cls.from_script(load_battle(path))

    @classmethod
    def from_script(cls, source):
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
                    speed_per_tick=speed_per_tick(profile.get("M"), profile.get("I")),
                ))
        return cls(field_data["width"], field_data["height"], regiments)

    def order_move(self, identifier, x, y):
        regiment = self.regiments[identifier]
        if not regiment.player:
            raise ValueError(f"{identifier} is not player-controlled")
        if not 0 <= x <= self.width or not 0 <= y <= self.height:
            raise ValueError("destination is outside the battlefield")
        regiment.target_x, regiment.target_y = float(x), float(y)

    def regiment_at(self, x, y, player_only=True):
        """Identifier of the regiment whose footprint contains (x, y), or None; the closest one if several."""
        best_id, best_distance = None, None
        for regiment in self.regiments.values():
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
        scale = seconds / TICK_SECONDS
        for regiment in self.regiments.values():
            step = regiment.speed_per_tick * scale
            regiment.model_positions()  # seed positions before advancing them
            anchor_moving = regiment.moving
            if anchor_moving:
                dx, dy = regiment.target_x - regiment.x, regiment.target_y - regiment.y
                distance = math.hypot(dx, dy)
                if distance <= step:
                    regiment.x, regiment.y = regiment.target_x, regiment.target_y
                    regiment.target_x = regiment.target_y = None
                else:
                    regiment.x += dx / distance * step
                    regiment.y += dy / distance * step
                    # 0 = north/+Y and directions increase clockwise.
                    regiment.direction = round(math.atan2(dx, dy) * 512 / math.tau) % 512
            models_catching_up = self._advance_models(regiment, step)
            regiment.walking = anchor_moving or models_catching_up
            regiment.animation_seconds = regiment.animation_seconds + seconds if regiment.walking else 0.0
        self._resolve_collisions()
        self.tick_count += 1

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

    def _resolve_collisions(self):
        """Push regiments under orders out of the regiments they overlap (a simplified `PushApart`;
        game_rules.md, "Routes, collisions and visibility"), not the polygon obstruction routing (`Nav*`).

        Standing regiments never give way, so scripted deployments that already overlap (BF001's Grudgebringer
        cavalry and infantry) stay where the script placed them. Pairs are visited in identifier order.
        """
        regiments = [self.regiments[key] for key in sorted(self.regiments)]
        for i, first in enumerate(regiments):
            for second in regiments[i + 1:]:
                yielding = first.moving + second.moving
                if not yielding:
                    continue
                dx, dy = second.x - first.x, second.y - first.y
                distance = math.hypot(dx, dy)
                overlap = first.bounding_radius() + second.bounding_radius() - distance
                if overlap <= 0:
                    continue
                ux, uy = (dx / distance, dy / distance) if distance > 1e-6 else (1.0, 0.0)
                share = overlap / yielding
                if first.moving:
                    first.x -= ux * share
                    first.y -= uy * share
                if second.moving:
                    second.x += ux * share
                    second.y += uy * share
