"""Ordinary ranged orders, missile flight and impacts from the public ranged combat handoff.

Geometry choices (unit height 24, triangular arc, four terrain samples per tick) are
isolated here so they can be refined without changing wound or order rules.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import animation
from .battle_events import BattleEvent
from .rules import hostile_sides, wfb_to_wound

if TYPE_CHECKING:
    from .engine import Battle, Regiment


@dataclass(frozen=True)
class Weapon:
    reach: int
    ticks: int
    rise: int
    radius: int
    wounds: int
    strength: int
    building_strength: int = 0


WEAPONS = {
    1: Weapon(576, 18, 20, 0, 1, 3), 2: Weapon(720, 18, 5, 0, 1, 4),
    5: Weapon(1440, 9, 10, 24, 6, 10, 10),
    6: Weapon(768, 27, 30, 24, 3, 7, 7),
    7: Weapon(576, 9, 10, 24, 4, 5, 5),
    8: Weapon(1440, 27, 30, 60, 6, 5, 5),
    9: Weapon(576, 18, 20, 0, 1, 4),
    11: Weapon(1152, 9, 10, 24, 4, 10, 10),
    12: Weapon(1440, 18, 10, 0, 6, 5, 5),
    17: Weapon(1, 9, 0, 72, 1, 4, 4),
    18: Weapon(384, 18, 20, 0, 1, 3),
    19: Weapon(720, 18, 20, 0, 1, 3),
}
ARTILLERY = {5, 6, 7, 8, 11, 12}
SPECIAL = {14: Weapon(576, 9, 10, 0, 1, 8),
           15: Weapon(576, 9, 10, 0, 1, 4),
           17: Weapon(144, 9, 0, 0, 1, 4)}
BOWS = {1, 9, 18, 19}
RELOAD_REDUCTION = {1: 43, 2: 30, 9: 54, 18: 46, 19: 39}


@dataclass
class Projectile:
    source: str
    code: int
    x0: float
    y0: float
    z0: float
    x1: float
    y1: float
    z1: float
    radius: int
    strength: int
    wounds: int
    elapsed: int = 0
    x: float = 0
    y: float = 0
    z: float = 0
    visual: str = ""
    building_strength: int = 0
    slot: int = -1


@dataclass
class InnateProjectile:
    source: str
    code: int
    x0: float
    y0: float
    x1: float
    y1: float
    elapsed: int = 0
    x: float = 0
    y: float = 0
    struck: frozenset[str] = frozenset()


def _message(battle: Battle, unit: Regiment, text_id: int) -> None:
    battle.events.append(BattleEvent(f"GMTXT {text_id}", "ranged_message",
                                     regiment=unit.identifier, text_id=text_id))


def reload_time(unit: Regiment) -> float:
    code = unit.shooting_code or unit.missile_code
    base = (10 - min(unit.initiative, 10)) * 18
    if code in RELOAD_REDUCTION:
        return max(18, base - RELOAD_REDUCTION[code])
    if code in ARTILLERY:
        return base + 36 * max(0, 4 - unit.models)
    return base


def _bearing(unit: Regiment, point: tuple[float, float]) -> float:
    return math.atan2(point[0] - unit.x, point[1] - unit.y) * 512 / math.tau % 512


def _arc(unit: Regiment, point: tuple[float, float]) -> bool:
    if point == (unit.x, unit.y):
        return True
    return abs((_bearing(unit, point) - unit.direction + 256) % 512 - 256) < 64


def _segment_distance(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0 if length == 0 else max(0.0, min(1.0, ((p[0]-a[0])*dx + (p[1]-a[1])*dy)/length))
    return math.hypot(a[0]+t*dx-p[0], a[1]+t*dy-p[1]), t


def _circle_entry(a: tuple[float, float], b: tuple[float, float],
                  center: tuple[float, float], radius: float) -> float | None:
    """First segment fraction entering a horizontal footprint, inclusive of an inside start."""
    dx, dy = b[0]-a[0], b[1]-a[1]
    aa = dx*dx + dy*dy
    if aa == 0:
        return 0.0 if math.dist(a, center) < radius else None
    fx, fy = a[0]-center[0], a[1]-center[1]
    bb = 2*(fx*dx + fy*dy)
    cc = fx*fx + fy*fy-radius*radius
    if cc < 0:
        return 0.0
    determinant = bb*bb-4*aa*cc
    if determinant < 0:
        return None
    t = (-bb-math.sqrt(determinant))/(2*aa)
    return max(0.0, t+1e-6) if 0 <= t <= 1 else None


def _scenery_between(battle: Battle, unit: Regiment, point: tuple[float, float]) -> bool:
    for obj in battle.shooting_objects:
        status = {str(v).casefold() for v in obj.get("status") or ()}
        if "os_solid" not in status:
            continue
        center = (float(obj.get("x") or 0), float(obj.get("y") or 0))
        radius = float(obj.get("radius") or 8)
        if math.dist((unit.x, unit.y), center) < radius:
            continue
        gap, t = _segment_distance((unit.x, unit.y), point, center)
        if 0 < t < 1 and gap < radius:
            return True
    return False


def _blocked_crossbow(battle: Battle, unit: Regiment, point: tuple[float, float]) -> bool:
    if (unit.shooting_code or unit.missile_code) != 2:
        return False
    for other in battle.regiments.values():
        if other is unit or not other.active or other.side in hostile_sides(unit.side):
            continue
        gap, t = _segment_distance((unit.x, unit.y), point, (other.x, other.y))
        if 0 < t < 1 and gap < other.bounding_radius():
            return True
    return False


def _search(battle: Battle, unit: Regiment) -> Regiment | None:
    candidates = (other for other in battle.regiments.values()
                  if other.active and not other.hidden and not other.routing
                  and other.side in hostile_sides(unit.side)
                  and (unit.independent or math.hypot(other.x-unit.x, other.y-unit.y) < (unit.missile_range or 0))
                  and (not unit.independent or not any(
                      friend is not unit and friend is not other and friend.active
                      and friend.side not in hostile_sides(unit.side)
                      and math.hypot(friend.x-other.x, friend.y-other.y)
                      < other.bounding_radius() + max(
                          (WEAPONS.get(unit.shooting_code or unit.missile_code or 1)
                           or SPECIAL.get(unit.shooting_code or unit.missile_code or 1)
                           or WEAPONS[1]).radius, 24)
                      for friend in battle.regiments.values())))
    return min(candidates, key=lambda other: math.hypot(other.x-unit.x, other.y-unit.y), default=None)


def _ready(unit: Regiment) -> bool:
    return (unit.reload_ticks <= 0 and (unit.hud_class != "art" or
            (unit.machine_alive and unit.models >= 2)))


def _aim(battle: Battle, unit: Regiment) -> tuple[float, float] | None:
    if unit.shooting_mode == "search":
        target = _search(battle, unit)
        return (target.x, target.y) if target else None
    if unit.shooting_mode == "target":
        target = battle.regiments.get(unit.shooting_target or "")
        if target is None or not target.active or target.hidden:
            unit.shooting_target = None
            unit.shooting_mode = "search" if unit.independent else None
            replacement = _search(battle, unit) if unit.independent else None
            return (replacement.x, replacement.y) if replacement else None
        return target.x, target.y
    if unit.shooting_mode == "building" and unit.shooting_object is not None:
        obj = battle.shooting_objects[unit.shooting_object]
        return float(obj.get("x") or 0), float(obj.get("y") or 0)
    return unit.shooting_point


def _order_volleys(battle: Battle) -> None:
    for unit in battle.regiments.values():
        if unit.reload_ticks > 0:
            unit.reload_ticks = max(0.0, unit.reload_ticks - 1)
        if unit.volley_countdown is None:
            unit.volley_age = 0
        if battle.interpreter is not None and not (unit.shooting_mode == "ground" and unit.shooting_code == 17
                                                   and unit.hud_class == "arch"):
            # notes/script_shooting.md 5.1: with behaviour scripts running, every ordinary shot comes from the
            # scripts (FireAtTarget on events 34/35); the engine orders no volley of its own. The Gyrocopter
            # bomb (Ctrl + Fire) is the one player order that bypasses the scripts.
            continue
        if not unit.active or unit.routing or unit.in_melee or unit.braced or unit.attack_target:
            unit.shooting_mode = None
            continue
        if unit.shooting_mode is None or unit.volley_countdown is not None or unit.volley_age:
            continue
        aim = _aim(battle, unit)
        if aim is None:
            continue
        code = unit.shooting_code or unit.missile_code
        weapon = SPECIAL[17] if code == 17 and unit.hud_class != "arch" else WEAPONS.get(code or 0) or SPECIAL.get(code or 0)
        if weapon is None:
            continue
        # Ground is a single attempted order; its refusal order is readiness, arc, range.
        ground = unit.shooting_mode == "ground"
        if ground and not _ready(unit):
            _message(battle, unit, 2003 if unit.reload_ticks > 0 else 2015 if not unit.machine_alive else 2016)
            unit.shooting_mode = unit.shooting_point = None
            continue
        distance = math.dist((unit.x, unit.y), aim)
        if not _arc(unit, aim):
            if ground:
                _message(battle, unit, 2002)
                unit.shooting_mode = unit.shooting_point = None
            elif not unit.anchored and not unit.moving and distance < weapon.reach and unit.turn_order_key is None:
                difference = abs((_bearing(unit, aim) - unit.direction + 256) % 512 - 256)
                if difference > 16:
                    battle.begin_script_turn(unit, _bearing(unit, aim))
            continue
        if distance >= weapon.reach:
            if ground:
                _message(battle, unit, 2001)
                unit.shooting_mode = unit.shooting_point = None
                continue
            elif unit.shooting_mode == "building":
                fraction = .9 * weapon.reach / distance
                aim = (unit.x + (aim[0]-unit.x)*fraction, unit.y + (aim[1]-unit.y)*fraction)
            elif unit.shooting_mode == "search" and unit.independent and not unit.anchored and not unit.moving:
                fraction = max(0.0, 1 - .9 * weapon.reach / distance)
                battle.set_point_route(unit, (unit.x + (aim[0]-unit.x)*fraction,
                                              unit.y + (aim[1]-unit.y)*fraction))
                continue
            else:
                continue
        if _blocked_crossbow(battle, unit, aim):
            if ground:
                unit.shooting_mode = unit.shooting_point = None
            continue
        if not _ready(unit) or unit.moving or unit.turn_order_key is not None:
            continue
        unit.volley_aim = aim
        unit.volley_countdown = 1 if unit.hud_class == "art" or code in {14, 15} or (code == 17 and unit.hud_class != "arch") else unit.models
        unit.volley_age = 0
        unit.reload_ticks = reload_time(unit)
        battle.events.append(BattleEvent(f"{unit.name} prepares a volley.", "volley",
                                         regiment=unit.identifier, code=code))
        if ground:
            unit.shooting_mode = unit.shooting_point = None


def _launch_posts(battle: Battle) -> None:
    for unit in battle.regiments.values():
        if not unit.fire_posts:
            continue
        positions = list(unit.fire_post_positions)
        unit.fire_post_positions.clear()
        posts, unit.fire_posts = unit.fire_posts, 0
        code = unit.shooting_code or unit.missile_code
        weapon = WEAPONS.get(code or 0) or SPECIAL.get(code or 0)
        if weapon is None:
            continue
        for index in range(posts):
            if code in {14, 15} or (code == 17 and unit.hud_class != "arch"):
                _launch_innate(battle, unit, code, positions[index] if index < len(positions) else (unit.x, unit.y))
                continue
            if len(battle.projectiles) >= 32:
                continue
            occupied = {projectile.slot for projectile in battle.projectiles}
            slot = next((value for value in range(32) if value not in occupied), None)
            if slot is None:
                continue
            if code in ARTILLERY and not unit.machine_alive:
                continue
            aim = _aim(battle, unit) if unit.shooting_mode else unit.volley_aim
            if aim is None:
                continue
            origin = positions[index] if index < len(positions) else (unit.x, unit.y)
            _create_projectile(battle, unit, code, weapon, origin, aim, slot)


def _create_projectile(battle: Battle, unit: Regiment, code: int, weapon: Weapon,
                       origin: tuple[float, float], aim: tuple[float, float], slot: int) -> str:
    """One ordinary projectile from `origin` at `aim` in pool `slot`: artillery and the bomb roll for a misfire
    first (no projectile, "misfire"); otherwise scatter, height and the flight record ("launched")."""
    first_die = 1
    if code in ARTILLERY or code == 17:
        first_die = battle.rng.randint(1, 6)
        if first_die == 6:
            second = battle.rng.randint(1, 6)
            if second == 1:
                _destroy_machine(battle, unit)
                _message(battle, unit, 2018)
            else:
                _message(battle, unit, 2019)
            return "misfire"
    x0, y0 = origin
    distance = math.dist((x0, y0), aim)
    spread = (8 * first_die if code in ARTILLERY else 8)
    if _scenery_between(battle, unit, aim):
        spread += 8
    scatter_max = 10 - min(unit.bs, 10)
    offsets = [battle.rng.randint(0, scatter_max) * battle.rng.choice((-1, 1))
               * spread * distance / weapon.reach for _ in range(2)]
    radius = battle.rng.randint(24, 48) if code in {5, 11} else weapon.radius
    strength = 4 if code == 7 and distance > 287 else weapon.strength
    z0 = battle.ground_height(x0, y0) + (72 if code == 17 else 24 if code in {8, 12} else 0)
    p = Projectile(unit.identifier, code, x0, y0, z0, aim[0]+offsets[0], aim[1]+offsets[1],
                   battle.ground_height(*aim), radius, strength, weapon.wounds,
                   x=x0, y=y0, z=z0,
                   visual=_visual(code) + ("_alt" if code in BOWS and battle.ctrl_held else ""),
                   building_strength=weapon.building_strength, slot=slot)
    battle.projectiles.append(p)
    battle.events.append(BattleEvent(f"{unit.name} launches a missile.", "projectile_launch",
                                     regiment=unit.identifier, code=code, x=x0, y=y0))
    return "launched"


def launch_shot(battle: Battle, unit: Regiment, origin: tuple[float, float], aim: tuple[float, float]) -> str:
    """One scripted shot (notes/script_shooting.md 1.2): "special" for a special shooter (14, 15, 17) that is not
    Archers or Artillery class, fired as its innate routine; "failed" for any other non-Archers/Artillery unit,
    a full projectile pool (where a special-shooter code still fires its routine) or a missile code without a
    projectile; otherwise the reload is stamped first and an ordinary projectile is launched ("launched",
    revealing a hidden shooter) or the artillery misfires ("misfire", which counts as fired). The stamp is one
    tick longer than the reload so the strict "elapsed > reload" readiness test holds; PROVISIONAL: the extra
    tick per segment boundary of the original clock is not modelled."""
    code = unit.shooting_code or unit.missile_code or 0
    shooter_class = unit.unit_class in (3, 4) or unit.hud_class in ("arch", "art")
    if code in SPECIAL and not shooter_class:
        _launch_innate(battle, unit, code, origin, aim)
        return "special"
    if not shooter_class:
        return "failed"
    occupied = {projectile.slot for projectile in battle.projectiles}
    slot = next((value for value in range(32) if value not in occupied), None)
    if slot is None:
        if code in SPECIAL:
            _launch_innate(battle, unit, code, origin, aim)
            return "special"
        return "failed"
    unit.reload_ticks = reload_time(unit) + 1
    weapon = WEAPONS.get(code)
    if weapon is None or code == 17 or (code in ARTILLERY and not unit.machine_alive):
        return "failed"
    result = _create_projectile(battle, unit, code, weapon, origin, aim, slot)
    if result == "launched":
        unit.hidden = False
    return result


def _destroy_machine(battle: Battle, unit: Regiment) -> None:
    from . import combat
    unit.machine_alive = False
    unit.clear_anchor()
    unit.shooting_mode = unit.shooting_target = None
    unit.volley_countdown = None
    unit.model_positions()
    victims = []
    for index, model in enumerate(unit.melee_models):
        if battle.rng.randrange(2) == 0:
            model.wounds_taken += 1
            if model.wounds_taken >= unit.wounds:
                victims.append(index)
    combat.kill_models(unit, victims, battle, animation.DEATH_MISSILE)
    if unit.active and not combat.leadership_test(unit.leadership, battle.rng):
        combat.start_rout(unit, battle)


def _visual(code: int) -> str:
    return ("arrow" if code in BOWS else "bolt" if code == 2 else
            "cannon" if code in {5, 11} else "mortar" if code == 6 else
            "rock" if code == 8 else "diver" if code == 12 else "bomb")


def _launch_innate(battle: Battle, unit: Regiment, code: int,
                   origin: tuple[float, float], aim: tuple[float, float] | None = None) -> None:
    if aim is None:
        aim = _aim(battle, unit) if unit.shooting_mode else unit.volley_aim
    if aim is None:
        return
    count = battle.rng.randint(1, 6) + 3 if code == 14 else battle.rng.randint(1, 6) if code == 15 else 1
    for _ in range(count):
        if len(battle.innate_projectiles) >= 64:
            break
        if code in {14, 15}:
            x1 = aim[0] + battle.rng.randint(-24, 24)
            y1 = aim[1] + battle.rng.randint(-24, 24)
        else:
            x1, y1 = aim
        battle.innate_projectiles.append(InnateProjectile(unit.identifier, code, *origin, x1, y1,
                                                            x=origin[0], y=origin[1]))
    battle.events.append(BattleEvent("Innate projectiles launched.", "innate_launch",
                                     regiment=unit.identifier, code=code, count=count))


def _damage_innate(battle: Battle, unit: Regiment, p: InnateProjectile) -> None:
    from . import combat
    unit.model_positions()
    if not unit.active:
        return
    index = battle.rng.randrange(unit.models)
    if "MagicResistent" in unit.psychology and battle.rng.randrange(2) == 0:
        return
    strength = 8 if p.code == 14 else 4
    if battle.rng.randint(1, 6) < wfb_to_wound(strength, unit.toughness):
        return
    model = unit.melee_models[index]
    model.wounds_taken += 1
    if model.wounds_taken >= unit.wounds:
        kind = animation.DEATH_FIRE if p.code == 14 else animation.DEATH_WARPFIRE if p.code == 15 else animation.DEATH_MISSILE
        combat.kill_models(unit, [index], battle, kind)
    if p.code == 14 and unit.active:
        combat.start_rout(unit, battle)
    battle.events.append(BattleEvent("Innate missile hit.", "innate_hit",
                                     regiment=unit.identifier, code=p.code))


def _step_innate(battle: Battle) -> None:
    remaining = []
    for p in battle.innate_projectiles:
        p.elapsed += 1
        t = min(1, p.elapsed / 9)
        p.x = p.x0 + (p.x1-p.x0)*t
        p.y = p.y0 + (p.y1-p.y0)*t
        struck = set(p.struck)
        for unit in battle.regiments.values():
            if unit.identifier == p.source or unit.identifier in struck or not unit.active:
                continue
            if math.hypot(unit.x-p.x, unit.y-p.y) < unit.bounding_radius():
                _damage_innate(battle, unit, p)
                struck.add(unit.identifier)
                if p.code != 17:
                    break
        p.struck = frozenset(struck)
        if p.elapsed < 9 and (p.code == 17 or not struck):
            remaining.append(p)
        elif p.elapsed >= 9 and not struck:
            for unit in battle.regiments.values():
                if unit.identifier != p.source and unit.active and math.hypot(unit.x-p.x1, unit.y-p.y1) < unit.bounding_radius():
                    _damage_innate(battle, unit, p)
                    break
    battle.innate_projectiles = remaining


def _damage_unit(battle: Battle, unit: Regiment, projectile: Projectile,
                 direct: bool, margin_picks: int = 0) -> None:
    from . import combat
    if not unit.active:
        return
    unit.model_positions()
    building = unit.unit_class in {8, 9}
    if building and not projectile.building_strength:
        return
    picks = (list(range(unit.models)) if direct and projectile.radius else
             [battle.rng.randrange(unit.models) for _ in range(margin_picks or 1)])
    if building:
        picks = [0]
    victims: set[int] = set()
    strength = (projectile.building_strength if building else projectile.strength)
    if not direct:
        strength //= 2
    for index in picks:
        if index in victims or index >= len(unit.melee_models):
            continue
        model = unit.melee_models[index]
        if unit.armour == 6:
            continue
        if battle.rng.randint(1, 6) < wfb_to_wound(strength, unit.toughness):
            continue
        if not building and battle.rng.randint(1, 6) >= combat._armour_threshold(unit.armour, strength):
            continue
        wounds = battle.rng.randint(1, projectile.wounds) if direct else 1
        model.wounds_taken = getattr(model, "wounds_taken", 0) + wounds
        if model.wounds_taken >= unit.wounds:
            victims.add(index)
    killed = combat.kill_models(unit, victims, battle, animation.DEATH_MISSILE)
    battle.events.append(BattleEvent(f"{unit.name} is hit by a missile.", "projectile_hit",
                                     regiment=unit.identifier, direct=direct, kills=killed,
                                     text_id=2004 if direct else 2005))
    if (not building and unit.models <= unit.original_models / 4 and projectile.code != 17
            and unit.active and not unit.routing and "CantBreak" not in unit.psychology):
        if not combat.leadership_test(unit.leadership, battle.rng):
            combat.start_rout(unit, battle)


def _impact(battle: Battle, p: Projectile, *, flight: bool,
            hit_unit: str | None = None) -> None:
    for unit in battle.regiments.values():
        if not unit.active or (flight and unit.identifier == p.source):
            continue
        if flight and unit.identifier != hit_unit:
            continue
        base = battle.ground_height(unit.x, unit.y) + (72 if unit.airborne else 0)
        if not base <= p.z <= base + 24:
            continue
        q = math.hypot(unit.x-p.x, unit.y-p.y)
        radius = unit.bounding_radius()
        if q < radius:
            _damage_unit(battle, unit, p, True)
        elif not flight and p.radius and q < radius + p.radius:
            count = max(1, int((radius+p.radius-q)*unit.models/(radius+p.radius)))
            _damage_unit(battle, unit, p, False, count)
    battle.impact_effects.append((p.x, p.y, p.code, battle.tick_count))
    battle.events.append(BattleEvent("Missile impact.", "projectile_impact", code=p.code,
                                     x=p.x, y=p.y, flight=flight))


def _step_projectiles(battle: Battle) -> None:
    remaining = []
    for p in sorted(battle.projectiles, key=lambda projectile: projectile.slot):
        old_x, old_y, old_z = p.x, p.y, p.z
        p.elapsed += 1
        weapon = WEAPONS[p.code]
        t = min(1.0, p.elapsed / weapon.ticks)
        p.x, p.y = p.x0 + (p.x1-p.x0)*t, p.y0 + (p.y1-p.y0)*t
        # Engine choice: symmetric rise/fall, flat bow apex in an 18-tick flight.
        rise_ticks = min(p.elapsed, weapon.ticks-p.elapsed, 9 if weapon.ticks == 18 else weapon.ticks//2)
        p.z = p.z0 + (p.z1-p.z0)*t + weapon.rise*max(0, rise_ticks)
        start, end = (old_x, old_y), (p.x, p.y)
        terrain_hit = next((fraction for fraction in (0.25, 0.5, 0.75, 1.0)
                            if old_z+(p.z-old_z)*fraction < battle.ground_height(
                                old_x+(p.x-old_x)*fraction, old_y+(p.y-old_y)*fraction)), None)
        hits: list[tuple[float, str | None]] = []
        if p.elapsed < weapon.ticks:
            for unit in battle.regiments.values():
                if unit.identifier == p.source or not unit.active:
                    continue
                entry = _circle_entry(start, end, (unit.x, unit.y), unit.bounding_radius())
                if entry is not None:
                    hx, hy = old_x+(p.x-old_x)*entry, old_y+(p.y-old_y)*entry
                    height = old_z+(p.z-old_z)*entry
                    base = battle.ground_height(hx, hy) + (72 if unit.airborne else 0)
                    if base <= height <= base+24:
                        hits.append((entry, unit.identifier))
            for obj in battle.shooting_objects:
                status = {str(v).casefold() for v in obj.get("status") or ()}
                if "os_solid" not in status:
                    continue
                center = (float(obj.get("x") or 0), float(obj.get("y") or 0))
                radius = float(obj.get("radius") or 8)
                if math.dist((p.x0, p.y0), center) < radius:
                    continue
                entry = _circle_entry(start, end, center, radius)
                if entry is not None:
                    hx, hy = old_x+(p.x-old_x)*entry, old_y+(p.y-old_y)*entry
                    if old_z+(p.z-old_z)*entry <= battle.ground_height(hx, hy)+24:
                        hits.append((entry, None))
        if terrain_hit is not None and (not hits or terrain_hit <= min(item[0] for item in hits)):
            continue
        if hits:
            entry, hit_unit = min(hits, key=lambda item: item[0])
            p.x, p.y = old_x+(p.x-old_x)*entry, old_y+(p.y-old_y)*entry
            p.z = old_z+(p.z-old_z)*entry
            _impact(battle, p, flight=True, hit_unit=hit_unit)
            continue
        if p.elapsed >= weapon.ticks:
            p.x, p.y, p.z = p.x1, p.y1, battle.ground_height(p.x1, p.y1)
            _impact(battle, p, flight=False)
        else:
            remaining.append(p)
    battle.projectiles = remaining
    battle.impact_effects = [e for e in battle.impact_effects if battle.tick_count-e[3] < 8]


def _step_death_blasts(battle: Battle) -> None:
    from . import combat
    # Chain explosions are queued by kill_models; process them in insertion order this tick.
    while True:
        due = next((i for i, entry in enumerate(battle.death_blasts)
                    if entry[0] <= battle.tick_count), None)
        if due is None:
            break
        _, kind, x, y = battle.death_blasts.pop(due)
        battle.impact_effects.append((x, y, 15 if kind != "giant" else 8, battle.tick_count))
        if kind != "puff":
            combat.resolve_death_blast(battle, x, y,
                                       combat.WARPFIRE_BLAST if kind == "warpfire" else combat.GIANT_BLAST)
        battle.events.append(BattleEvent("Death blast.", "death_blast", kind_name=kind, x=x, y=y))


def tick(battle: Battle) -> None:
    _step_projectiles(battle)
    _step_innate(battle)
    _launch_posts(battle)
    _order_volleys(battle)
    _step_death_blasts(battle)


def finish_tick(battle: Battle) -> None:
    """Continue existing effects after battle result, without accepting another volley."""
    _step_projectiles(battle)
    _step_innate(battle)
    _step_death_blasts(battle)
