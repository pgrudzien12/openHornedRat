"""Close combat, morale, rally and shooting resolution, stdlib-only (no frontend import).

Called from `whshr.engine.Battle.tick`. Rules are simplified from `notes/game_rules.md` sections
5-8 (see the module docstring of each function for what is skipped); this is not meant to reproduce
the original byte-for-byte, only to give a deterministic, documented first playable battle.

Simplifications common to this module (documented placeholders, not traced values):
- No ganging-up WS bonus, hatred re-rolls, magic items, mounts or monsters (game_rules.md 5.2, 5.4-5.6).
- Only front-rank models attack (game_rules.md 5.2/5.7's per-model battle-grid pairing is not modelled);
  not capped by the opponent's frontage.
- The charge bonus (+1 S, game_rules.md 5.5) is granted once, to a regiment's whole first strike after
  joining a fight, instead of decrementing per attacking model.
- Multi-wound models die on their first failed save (no per-model wound tracking).
- Shooting hit chance is a documented BS-based placeholder (`SHOOT_TO_HIT`), not the original's
  geometric scatter/flight simulation (game_rules.md 8.1-8.3); only basic bow-type missile codes are
  modelled as shooters (`engine.ARCHER_MISSILE_CODES`), never artillery or special weapons.
- Break tests are timed and scored per the traced rules (game_rules.md 6.2): tallies accumulate rank
  and direction bonuses plus kills each strike; the first result comes two turns after contact, later
  ones every turn after that (the original varies this by Initiative). Rally follows game_rules.md 7.4's
  schedule and casualties-based Leadership modifier, but at segment (not sub-segment) granularity.

Every event `whshr.battle_log.BattleLogger` needs for diagnosing the playtest bugs (strike rolls,
Leadership tests, rout/rally, shooting) is emitted here as a `whshr.battle_events.BattleEvent`: a
`str` (so it still prints and compares like the old plain-string events) carrying a `kind` and a
`data` mapping of the exact numbers rolled.
"""
import math

from . import formation
from .battle_events import BattleEvent
from .rules import EXPECTED_ARMOUR_SAVE, wfb_to_hit, wfb_to_wound

SEGMENT_TICKS = 19  # game_rules.md, "Battle clock": 19 ticks per segment
SEGMENTS_PER_TURN = 10  # game_rules.md 5.1: segments count down from 10 to 1 within a turn
FLEE_SAFE_DISTANCE = 160.0  # game_rules.md 7.4: no rally attempt while an enemy is this close
# Two footprints (formation.footprint_gap) are considered "in contact" once they are within about one
# model spacing (game_rules.md, "Engagement": front ranks must actually touch, not just be close).
CONTACT_MARGIN = formation.MODEL_SPACING
SHOOT_ARC_HALF = 64  # +/- 45 degrees (of 512), game_rules.md 8.1 "Arc of fire"
DIRECTION_BONUS = {0: 0, 1: 1, 2: 2, 3: 1}  # front, flank, rear, flank (game_rules.md 6.1)
# Placeholder shooting to-hit chart by BS (game_rules.md 8.1 says shooting is geometric, not a WS-style
# chart; this substitutes a simple, documented BS-based die target so "hits by BS" is deterministic).
SHOOT_TO_HIT = {1: 6, 2: 5, 3: 4, 4: 4, 5: 3, 6: 3, 7: 2, 8: 2, 9: 2, 10: 2}
MISSILE_STRENGTH = {1: 3, 2: 4, 9: 4, 18: 3, 19: 3}  # game_rules.md 8.3 table, archer codes only
# game_rules.md 8.2 reload formula constants, by missile code.
RELOAD_K = {1: 7, 2: 4, 9: 10, 18: 8, 19: 6}


def _d6(rng):
    return rng.randint(1, 6)


def _2_to_12(rng):
    return rng.randint(2, 12)


def leadership_test(leadership, rng, modifier=0):
    """game_rules.md 7.1: pass <=> modifier + (uniform 2-12) <= Leadership (not 2D6)."""
    return modifier + _2_to_12(rng) <= leadership


def _armour_threshold(armour, strength):
    save = EXPECTED_ARMOUR_SAVE[armour] if 0 <= armour < len(EXPECTED_ARMOUR_SAVE) else 7
    return save + max(0, strength - 3)


def apply_casualties(regiment, count, rng):
    """Remove up to `count` models, turning them into corpses at their current positions.

    game_rules.md 7.6: `CantDie` models are never removed by wounds. The combat result score still
    counts every wound rolled against them regardless (`resolve_melee` scores `_roll_attacks`' raw
    `kills`, not this function's return value): the notes do not say whether a `CantDie` model's
    wounds count toward the break-test tally, so this is a documented placeholder that they do.
    """
    if count <= 0 or regiment.models <= 0 or "CantDie" in regiment.psychology:
        return 0
    count = min(count, regiment.models)
    positions = list(regiment.model_positions())
    indices = rng.sample(range(len(positions)), count) if count < len(positions) else range(len(positions))
    for index in indices:
        regiment.corpses.append((*positions[index], regiment.direction))
    regiment.models -= count
    regiment.positions = []  # force the next model_positions() call to reseed the smaller formation
    return count


def _rank_bonus(attacker):
    """game_rules.md 6.1: if frontage > 3, size / width - 1 full ranks behind the first, uncapped."""
    frontage = attacker.front_rank_models()
    if frontage <= 3:
        return 0
    return max(0, attacker.models // frontage - 1)


def _direction_bonus(attacker, defender):
    """game_rules.md 6.1: the attacker's angle relative to the defender's facing, front/flank/rear/flank
    quartered into four 128 (of 512) wide arcs centred on front (0), right flank (128), rear (256) and
    left flank (384)."""
    dx, dy = attacker.x - defender.x, attacker.y - defender.y
    if dx == 0 and dy == 0:
        return 0
    bearing = round(math.atan2(dx, dy) * formation.FULL_TURN / math.tau) % formation.FULL_TURN
    offset = (bearing - defender.direction) % formation.FULL_TURN
    sector = round(offset / (formation.FULL_TURN / 4)) % 4
    return DIRECTION_BONUS[sector]


def _roll_attacks(attacker, defender, rng, charge_bonus=0):
    """Casualties `attacker`'s front rank inflicts on `defender` in one strike (game_rules.md 5.2).

    Returns `(kills, detail)`, where `detail` documents every individual attack for the battle log:
    `hit_need`/`wound_need`/`save_need` (the target numbers) and, per attack, the hit/wound/save rolls
    actually made and the result ("missed", "no_wound", "saved" or "killed"; a roll stops early on a
    miss or failure to wound, so `save_roll` is `None` unless the attack reached the save).
    """
    attacks = attacker.front_rank_models() * max(1, attacker.attacks)
    hit_need = wfb_to_hit(attacker.ws, defender.ws)
    strength = attacker.strength + attacker.strength_bonus + charge_bonus
    wound_need = wfb_to_wound(strength, defender.toughness)
    threshold = _armour_threshold(defender.armour, strength)
    detail = {"attacks": attacks, "hit_need": hit_need, "wound_need": wound_need, "save_need": threshold,
              "rolls": []}
    if wound_need > 6:
        return 0, detail
    kills = 0
    for _ in range(attacks):
        hit_roll = _d6(rng)
        if hit_roll < hit_need:
            detail["rolls"].append({"hit": hit_roll, "wound": None, "save": None, "result": "missed"})
            continue
        wound_roll = _d6(rng)
        if wound_roll < wound_need:
            detail["rolls"].append({"hit": hit_roll, "wound": wound_roll, "save": None, "result": "no_wound"})
            continue
        save_roll = _d6(rng)
        if save_roll >= threshold:
            detail["rolls"].append({"hit": hit_roll, "wound": wound_roll, "save": save_roll, "result": "saved"})
            continue
        detail["rolls"].append({"hit": hit_roll, "wound": wound_roll, "save": save_roll, "result": "killed"})
        kills += 1
    return min(kills, defender.models), detail


def refresh_melee_state(battle):
    """Free a regiment from melee one tick early (before `_advance_regiments` unfreezes it) once every
    enemy it was touching is no longer an active, standing target; `resolve_contacts` would release it
    anyway next tick, but only after movement already ran frozen for one more tick."""
    for regiment in battle.regiments.values():
        if not regiment.in_melee:
            continue
        if not any(_touching_enemy_active(battle, enemy_id) for enemy_id in regiment.melee_touching):
            regiment.in_melee = False
            regiment.melee_group = None
            regiment.melee_touching = frozenset()
            regiment.attack_target = None


def _touching_enemy_active(battle, enemy_id):
    enemy = battle.regiments.get(enemy_id)
    return enemy is not None and enemy.active and not enemy.routing


def _segment_state(tick_count):
    """(absolute_segment, turn, segment_number): segment_number counts down 10..1 within each 10-segment
    turn (game_rules.md 5.1); `absolute_segment` is a global segment counter used for rally scheduling."""
    absolute_segment = tick_count // SEGMENT_TICKS
    turn, segment_in_turn = divmod(absolute_segment, SEGMENTS_PER_TURN)
    return absolute_segment, turn, SEGMENTS_PER_TURN - segment_in_turn


def _new_fight(turn):
    return {
        "next_test_turn": turn + 2,  # game_rules.md 6.2: the first result comes two turns after contact
        "tally": {True: 0.0, False: 0.0},
        "breakdown": {True: {"kills": 0, "rank": 0, "direction": 0},
                      False: {"kills": 0, "rank": 0, "direction": 0}},
    }


def _new_fight_id(battle):
    battle._fight_seq += 1
    return f"fight{battle._fight_seq}"


def _merge_fights(battle, keep_id, other_ids):
    """Fold `other_ids`' tallies/breakdowns/timers into `keep_id` when previously separate fights turn
    out to be connected through a shared regiment (game_rules.md 5.7's battle grid: several units may
    share one fight)."""
    keep = battle.fights[keep_id]
    for other_id in other_ids:
        other = battle.fights.pop(other_id, None)
        if other is None:
            continue
        for side in (True, False):
            keep["tally"][side] += other["tally"][side]
            for field_name in ("kills", "rank", "direction"):
                keep["breakdown"][side][field_name] += other["breakdown"][side][field_name]
        keep["next_test_turn"] = min(keep["next_test_turn"], other["next_test_turn"])


def resolve_contacts(battle):
    """Group regiments whose oriented footprints actually touch into shared fights (game_rules.md 5.7's
    battle grid: several regiments per side may share one fight, so a side can gang up on a lone enemy);
    a routing regiment is never engaged in close combat (game_rules.md 7.7: "pursuers never engage
    fleeing units in close combat"). Recomputed every tick so a regiment that dies or a footprint that
    shrinks below contact range releases its neighbours, and a third regiment closing in joins the fight
    already in progress instead of starting a separate 1v1."""
    _, turn, _ = _segment_state(battle.tick_count)
    active = [r for r in battle.regiments.values() if r.active and not r.routing]
    by_id = {r.identifier: r for r in active}
    touching = {r.identifier: set() for r in active}
    old_touching = {r.identifier: r.melee_touching for r in active}
    for i, first in enumerate(active):
        for second in active[i + 1:]:
            if second.player == first.player:
                continue
            gap = formation.footprint_gap(first.footprint_corners(), second.footprint_corners())
            if gap <= CONTACT_MARGIN:
                touching[first.identifier].add(second.identifier)
                touching[second.identifier].add(first.identifier)

    for identifier, neighbours in touching.items():
        regiment = by_id[identifier]
        for enemy_id in neighbours - old_touching[identifier]:
            if identifier < enemy_id:  # log each new pair once
                enemy = by_id[enemy_id]
                battle.events.append(BattleEvent(
                    f"{regiment.name} clashes with {enemy.name}!", "clash",
                    first=identifier, second=enemy_id,
                    distance=math.hypot(enemy.x - regiment.x, enemy.y - regiment.y)))

    parent = {identifier: identifier for identifier in touching}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for identifier, neighbours in touching.items():
        for enemy_id in neighbours:
            root_a, root_b = find(identifier), find(enemy_id)
            if root_a != root_b:
                parent[root_a] = root_b

    components = {}
    for identifier in touching:
        if touching[identifier]:
            components.setdefault(find(identifier), []).append(identifier)

    kept_groups = set()
    for members in components.values():
        existing_ids = sorted({by_id[m].melee_group for m in members if by_id[m].melee_group})
        if existing_ids:
            group_id = existing_ids[0]
            if len(existing_ids) > 1:
                _merge_fights(battle, group_id, existing_ids[1:])
        else:
            group_id = _new_fight_id(battle)
            battle.fights[group_id] = _new_fight(turn)
        kept_groups.add(group_id)
        for identifier in members:
            regiment = by_id[identifier]
            regiment.melee_touching = frozenset(touching[identifier])
            if regiment.melee_group != group_id:
                # game_rules.md 5.5: the moving side with a charge/pursuit order is the charger and gets
                # +1 S on its first strike after joining a fight (whether the fight is brand new or a
                # third regiment joining one already under way).
                if regiment.attack_target in touching[identifier]:
                    regiment.melee_charging = True
                regiment.melee_group = group_id
                regiment.target_x = regiment.target_y = None
            regiment.in_melee = True

    for identifier, regiment in by_id.items():
        if not touching[identifier] and regiment.in_melee:
            regiment.in_melee = False
            regiment.melee_group = None
            regiment.melee_touching = frozenset()

    for group_id in list(battle.fights):
        if group_id not in kept_groups:
            battle.fights.pop(group_id, None)


def _pick_melee_target(attacker, battle):
    """The nearest active enemy `attacker` is footprint-touching right now (game_rules.md 5.7: an
    attacker strikes whichever touching opponent it is engaged with); ties break on identifier for a
    deterministic replay."""
    candidates = []
    for enemy_id in attacker.melee_touching:
        enemy = battle.regiments.get(enemy_id)
        if enemy is not None and enemy.active:
            candidates.append(enemy)
    if not candidates:
        return None
    return min(candidates, key=lambda e: (math.hypot(e.x - attacker.x, e.y - attacker.y), e.identifier))


def resolve_melee(battle):
    """A unit strikes only in its own Initiative segment, once per turn (game_rules.md 5.1), at whichever
    touching enemy `_pick_melee_target` selects; kills plus rank and direction bonus accumulate into its
    fight's own-side tally (6.1). At each turn's last segment, every fight's losing side (by tally
    difference) takes a break test, timed by that fight's `next_test_turn` (6.2, simplified: every turn
    once due, instead of varying with Initiative)."""
    _, turn, segment_number = _segment_state(battle.tick_count)
    groups = {}
    for regiment in battle.regiments.values():
        if regiment.in_melee and regiment.melee_group:
            groups.setdefault(regiment.melee_group, []).append(regiment)
    for group_id, members in groups.items():
        fight = battle.fights[group_id]
        for attacker in members:
            if attacker.initiative != segment_number:
                continue
            defender = _pick_melee_target(attacker, battle)
            if defender is None:
                continue
            charge_bonus = 1 if attacker.melee_charging else 0
            attacker.melee_charging = False
            kills, detail = _roll_attacks(attacker, defender, battle.rng, charge_bonus=charge_bonus)
            apply_casualties(defender, kills, battle.rng)
            rank_bonus = _rank_bonus(attacker)
            direction_bonus = _direction_bonus(attacker, defender)
            fight["tally"][attacker.player] += kills + rank_bonus + direction_bonus
            breakdown = fight["breakdown"][attacker.player]
            breakdown["kills"] += kills
            breakdown["rank"] += rank_bonus
            breakdown["direction"] += direction_bonus
            battle.events.append(BattleEvent(
                f"{attacker.name} strikes {defender.name} in segment {segment_number} (turn {turn}): "
                f"{kills} casualties, side tally {fight['tally'][attacker.player]:.0f} "
                f"(+{rank_bonus} rank, +{direction_bonus} dir{', +1 charge' if charge_bonus else ''}).",
                "melee_strike",
                attacker=attacker.identifier, defender=defender.identifier, fight=group_id, turn=turn,
                segment=segment_number, kills=kills, rank_bonus=rank_bonus, direction_bonus=direction_bonus,
                charge_bonus=charge_bonus, tally=dict(fight["tally"]), attacks=detail))
        if segment_number == 1:
            _resolve_group_break_test(group_id, members, turn, battle)


def _resolve_group_break_test(group_id, members, turn, battle):
    """Evaluate one fight's break test once it is due (game_rules.md 6.2): only the losing side (by
    accumulated tally) is tested, every active regiment on that side; the tally and its breakdown reset
    and the next test is due next turn."""
    fight = battle.fights[group_id]
    if turn < fight["next_test_turn"]:
        return
    difference = fight["tally"][True] - fight["tally"][False]
    if difference != 0:
        losing_side = difference < 0
        modifier = abs(difference)
        breakdown = {True: dict(fight["breakdown"][True]), False: dict(fight["breakdown"][False])}
        for regiment in members:
            if regiment.player == losing_side:
                _break_test(regiment, modifier, group_id, breakdown, battle)
    fight["tally"] = {True: 0.0, False: 0.0}
    fight["breakdown"] = {True: {"kills": 0, "rank": 0, "direction": 0},
                           False: {"kills": 0, "rank": 0, "direction": 0}}
    fight["next_test_turn"] = turn + 1


def _break_test(regiment, modifier, group_id, breakdown, battle):
    """The losing side's Leadership test (game_rules.md 6.2, simplified). Logs every check, including a
    skipped one (regiment already destroyed or CantBreak), so a rout can always be traced back to its
    exact Ld, roll, modifier and the kills/rank/direction breakdown (per side) behind that modifier."""
    if not regiment.active:
        return
    if "CantBreak" in regiment.psychology:
        battle.events.append(BattleEvent(
            f"{regiment.name} cannot break (CantBreak).", "leadership_test",
            regiment=regiment.identifier, fight=group_id, leadership=regiment.leadership,
            modifier=modifier, breakdown=breakdown, cant_break=True, roll=None, passed=True))
        return
    roll = _2_to_12(battle.rng)
    passed = modifier + roll <= regiment.leadership
    battle.events.append(BattleEvent(
        f"{regiment.name} takes a Leadership test (Ld {regiment.leadership}, roll {roll} + {modifier}): "
        f"{'passes' if passed else 'fails'}.", "leadership_test",
        regiment=regiment.identifier, fight=group_id, leadership=regiment.leadership,
        roll=roll, modifier=modifier, breakdown=breakdown, cant_break=False, passed=passed))
    if not passed:
        _start_rout(regiment, battle)


def _start_rout(regiment, battle):
    flee_x, flee_y = battle._flee_point(regiment)
    regiment.routing = True
    regiment.in_melee = False
    regiment.melee_group = None
    regiment.melee_touching = frozenset()
    regiment.attack_target = None
    regiment.target_x = regiment.target_y = None
    # game_rules.md 7.4: the first rally attempt comes one full turn (SEGMENTS_PER_TURN segments) after
    # the rout, then every 3 segments.
    absolute_segment, _, _ = _segment_state(battle.tick_count)
    regiment.rally_next_segment = absolute_segment + SEGMENTS_PER_TURN
    battle.events.append(BattleEvent(
        f"{regiment.name} routs!", "rout_start",
        regiment=regiment.identifier, x=regiment.x, y=regiment.y, flee_x=flee_x, flee_y=flee_y))


def _rally_modifier(regiment):
    """game_rules.md 7.4: +2 if casualties > size, +1 if 3 x casualties > size, else 0; `None` (no rally
    at all) when casualties >= 3 x size (at or below a quarter of the original strength)."""
    casualties = regiment.original_models - regiment.models
    size = regiment.models
    if casualties >= 3 * size:
        return None
    if casualties > size:
        return 2
    if 3 * casualties > size:
        return 1
    return 0


def resolve_rally(battle):
    """A routing regiment may rally once its scheduled segment has come and no enemy is within
    FLEE_SAFE_DISTANCE (game_rules.md 7.4). Logs every due rally check, including why it was skipped
    (CantRally, too many casualties, enemy too close); a regiment whose segment has not come yet, or
    that has "CantRally", makes no attempt at all."""
    absolute_segment, _, _ = _segment_state(battle.tick_count)
    for regiment in battle.regiments.values():
        # A regiment that has fled off the field is permanently out (game_rules.md, "Flight"): once
        # `fled`, `active` is false forever, so it must never be offered another rally attempt.
        if not regiment.routing or not regiment.active:
            continue
        if regiment.rally_next_segment is None or absolute_segment < regiment.rally_next_segment:
            continue
        # The scheduled segment has come: whatever happens below, the next poll (if the unit is still
        # routing) is 3 segments away (game_rules.md 7.4), independent of why this attempt did not rally.
        regiment.rally_next_segment = absolute_segment + 3
        if "CantRally" in regiment.psychology:
            battle.events.append(BattleEvent(
                f"{regiment.name} cannot rally (CantRally).", "rally_test",
                regiment=regiment.identifier, cant_rally=True, blocked_by_enemy=False, roll=None, passed=False))
            continue
        modifier = _rally_modifier(regiment)
        if modifier is None:
            battle.events.append(BattleEvent(
                f"{regiment.name} cannot rally: casualties are too heavy.", "rally_test",
                regiment=regiment.identifier, cant_rally=False, blocked_by_enemy=False,
                too_many_casualties=True, roll=None, passed=False))
            continue
        nearest = battle._nearest_enemy(regiment)
        distance = math.hypot(nearest.x - regiment.x, nearest.y - regiment.y) if nearest is not None else None
        if distance is not None and distance < FLEE_SAFE_DISTANCE:
            battle.events.append(BattleEvent(
                f"{regiment.name} cannot rally: an enemy is {distance:.0f} units away.", "rally_test",
                regiment=regiment.identifier, cant_rally=False, blocked_by_enemy=True,
                nearest_enemy_distance=distance, roll=None, passed=False))
            continue
        roll = _2_to_12(battle.rng)
        passed = modifier + roll <= regiment.leadership
        battle.events.append(BattleEvent(
            f"{regiment.name} takes a rally test (Ld {regiment.leadership}, roll {roll} + {modifier}): "
            f"{'rallies' if passed else 'still routing'}.", "rally_test",
            regiment=regiment.identifier, cant_rally=False, blocked_by_enemy=False,
            leadership=regiment.leadership, roll=roll, modifier=modifier, passed=passed))
        if passed:
            regiment.routing = False
            regiment.rally_next_segment = None


def resolve_shooting(battle):
    """Missile regiments (game_rules.md 8.1-8.3, simplified: only bow-type codes, a BS-based hit chart
    instead of geometric scatter, no volleys other than the model count / 4 shot count) fire at the
    nearest enemy in range and front arc when not moving and not in melee."""
    for regiment in battle.regiments.values():
        if regiment.reload_ticks > 0:
            regiment.reload_ticks = max(0.0, regiment.reload_ticks - 1)
        if not regiment.missile_range or not regiment.active or regiment.in_melee or regiment.routing:
            continue
        if regiment.moving or regiment.attack_target is not None or regiment.reload_ticks > 0:
            continue
        target = _shooting_target(battle, regiment)
        if target is None:
            continue
        distance = math.hypot(target.x - regiment.x, target.y - regiment.y)
        shots = max(1, -(-regiment.front_rank_models() // 4))  # ceil(front rank / 4), game_rules.md 8.1
        strength = MISSILE_STRENGTH.get(regiment.missile_code, regiment.strength)
        hit_need = SHOOT_TO_HIT.get(max(1, min(10, regiment.bs)), 4)
        wound_need = wfb_to_wound(strength, target.toughness)
        threshold = _armour_threshold(target.armour, strength)
        kills = 0
        rolls = []
        if wound_need <= 6:
            for _ in range(shots):
                hit_roll = _d6(battle.rng)
                if hit_roll < hit_need:
                    rolls.append({"hit": hit_roll, "wound": None, "save": None, "result": "missed"})
                    continue
                wound_roll = _d6(battle.rng)
                if wound_roll < wound_need:
                    rolls.append({"hit": hit_roll, "wound": wound_roll, "save": None, "result": "no_wound"})
                    continue
                save_roll = _d6(battle.rng)
                if save_roll >= threshold:
                    rolls.append({"hit": hit_roll, "wound": wound_roll, "save": save_roll, "result": "saved"})
                    continue
                rolls.append({"hit": hit_roll, "wound": wound_roll, "save": save_roll, "result": "killed"})
                kills += 1
        apply_casualties(target, kills, battle.rng)
        battle.events.append(BattleEvent(
            f"{regiment.name} shoots {target.name}: {kills} casualties." if kills else
            f"{regiment.name} shoots {target.name}: no casualties.", "shooting",
            shooter=regiment.identifier, target=target.identifier, distance=distance,
            range=regiment.missile_range, shots=shots, hit_need=hit_need, wound_need=wound_need,
            save_need=threshold, rolls=rolls, kills=kills))
        regiment.reload_ticks = _reload_ticks(regiment)
        battle.events.append(BattleEvent(
            f"{regiment.name} reloads: ready in {regiment.reload_ticks:.0f} ticks.", "reload",
            regiment=regiment.identifier, reload_ticks=regiment.reload_ticks))


def _shooting_target(battle, regiment):
    """The nearest active enemy regiment in range and front arc (game_rules.md 8.1)."""
    best, best_distance = None, None
    for enemy in battle.regiments.values():
        if enemy.player == regiment.player or not enemy.active or enemy.routing:
            continue
        dx, dy = enemy.x - regiment.x, enemy.y - regiment.y
        distance = math.hypot(dx, dy)
        if distance >= regiment.missile_range or distance < 1e-6:
            continue
        bearing = round(math.atan2(dx, dy) * 512 / math.tau) % 512
        offset = (bearing - regiment.direction + 256) % 512 - 256
        if abs(offset) > SHOOT_ARC_HALF:
            continue
        if best is None or distance < best_distance:
            best, best_distance = enemy, distance
    return best


def _reload_ticks(regiment):
    """game_rules.md 8.2: base = (10 - min(I, 10)) * 18, reduced by a weapon-specific constant k."""
    base = (10 - min(regiment.initiative, 10)) * 18
    k = RELOAD_K.get(regiment.missile_code)
    if k:
        if k < 3:
            reduction = 9 * k
        elif k < 6:
            reduction = 6 * k + 6
        else:
            reduction = (2 * k - 10) * 9 / 5 + 36
        base = max(base - reduction, 18)
    return base
