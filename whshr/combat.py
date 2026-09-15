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
# A regiment's bounding circles are considered "in contact" with this much slack, so two blocks that
# are merely adjacent (not exactly overlapping) still engage (game_rules.md, "Engagement").
CONTACT_MARGIN = 4.0
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
    """Remove up to `count` models, turning them into corpses at their current positions."""
    if count <= 0 or regiment.models <= 0:
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
    """Free a regiment from melee once its opponent is no longer an active, standing enemy."""
    for regiment in battle.regiments.values():
        if not regiment.in_melee:
            continue
        opponent = battle.regiments.get(regiment.melee_opponent)
        if opponent is None or not opponent.active or opponent.routing:
            regiment.in_melee = False
            regiment.melee_opponent = None
            regiment.attack_target = None


def _segment_state(tick_count):
    """(absolute_segment, turn, segment_number): segment_number counts down 10..1 within each 10-segment
    turn (game_rules.md 5.1); `absolute_segment` is a global segment counter used for rally scheduling."""
    absolute_segment = tick_count // SEGMENT_TICKS
    turn, segment_in_turn = divmod(absolute_segment, SEGMENTS_PER_TURN)
    return absolute_segment, turn, SEGMENTS_PER_TURN - segment_in_turn


def resolve_contacts(battle):
    """Regiments whose footprints touch enter melee (game_rules.md 5.7's battle grid, simplified to a
    circle-circle contact test); a routing regiment is never engaged in close combat (game_rules.md
    7.7: "pursuers never engage fleeing units in close combat")."""
    _, turn, _ = _segment_state(battle.tick_count)
    candidates = [r for r in battle.regiments.values() if r.active and not r.in_melee and not r.routing]
    for i, first in enumerate(candidates):
        if first.in_melee:
            continue
        for second in candidates[i + 1:]:
            if second.in_melee or second.player == first.player:
                continue
            distance = math.hypot(second.x - first.x, second.y - first.y)
            if distance <= first.bounding_radius() + second.bounding_radius() + CONTACT_MARGIN:
                first.in_melee = second.in_melee = True
                first.melee_opponent, second.melee_opponent = second.identifier, first.identifier
                # game_rules.md 5.5: the moving side with a charge/pursuit order is the charger and gets
                # +1 S on its first strike; both units' tallies and break-test timer reset on contact.
                first.melee_charging = first.attack_target == second.identifier
                second.melee_charging = second.attack_target == first.identifier
                first.melee_tally = second.melee_tally = 0.0
                first.melee_next_test_turn = second.melee_next_test_turn = turn + 2
                first.target_x = first.target_y = second.target_x = second.target_y = None
                battle.events.append(BattleEvent(
                    f"{first.name} clashes with {second.name}!", "clash",
                    first=first.identifier, second=second.identifier, distance=distance))
                break


def resolve_melee(battle):
    """A unit strikes only in its own Initiative segment, once per turn (game_rules.md 5.1); its kills
    plus rank and direction bonus accumulate into its own tally (6.1). At each turn's last segment, the
    losing side (by tally difference) takes a break test, timed per `resolve_contacts`/`_schedule_next_test`
    (6.2, simplified: every turn once due, instead of varying with Initiative)."""
    _, turn, segment_number = _segment_state(battle.tick_count)
    resolved = set()
    for regiment in battle.regiments.values():
        if not regiment.in_melee or regiment.identifier in resolved:
            continue
        opponent = battle.regiments.get(regiment.melee_opponent)
        if opponent is None or not opponent.in_melee:
            continue
        resolved.add(regiment.identifier)
        resolved.add(opponent.identifier)
        for attacker, defender in ((regiment, opponent), (opponent, regiment)):
            if attacker.initiative != segment_number:
                continue
            charge_bonus = 1 if attacker.melee_charging else 0
            attacker.melee_charging = False
            kills, detail = _roll_attacks(attacker, defender, battle.rng, charge_bonus=charge_bonus)
            apply_casualties(defender, kills, battle.rng)
            rank_bonus = _rank_bonus(attacker)
            direction_bonus = _direction_bonus(attacker, defender)
            attacker.melee_tally += kills + rank_bonus + direction_bonus
            battle.events.append(BattleEvent(
                f"{attacker.name} strikes {defender.name} in segment {segment_number} (turn {turn}): "
                f"{kills} casualties, tally {attacker.melee_tally:.0f} (+{rank_bonus} rank, +{direction_bonus} dir"
                f"{', +1 charge' if charge_bonus else ''}).",
                "melee_strike",
                attacker=attacker.identifier, defender=defender.identifier, turn=turn, segment=segment_number,
                kills=kills, rank_bonus=rank_bonus, direction_bonus=direction_bonus, charge_bonus=charge_bonus,
                tally=attacker.melee_tally, attacks=detail))
        if segment_number == 1:
            _resolve_break_tests(regiment, opponent, turn, battle)


def _resolve_break_tests(regiment, opponent, turn, battle):
    """Evaluate the shared battle grid's break test once it is due (game_rules.md 6.2): only the losing
    side (by accumulated tally) is tested; both tallies reset and the next test is due next turn."""
    if regiment.melee_next_test_turn is None or turn < regiment.melee_next_test_turn:
        return
    difference = regiment.melee_tally - opponent.melee_tally
    _break_test(regiment, difference, opponent, battle)
    _break_test(opponent, -difference, regiment, battle)
    regiment.melee_tally = opponent.melee_tally = 0.0
    regiment.melee_next_test_turn = opponent.melee_next_test_turn = turn + 1


def _break_test(regiment, difference, opponent, battle):
    """The losing side's Leadership test (game_rules.md 6.2, simplified). Logs every check, including a
    skipped one (regiment already destroyed, won or drew the round, or CantBreak), so a rout can always
    be traced back to its exact Ld, roll and modifier."""
    if not regiment.active:
        return
    if difference >= 0:
        return  # regiment.active check above still lets a drawn/won round through with no test needed
    modifier = -difference
    if "CantBreak" in regiment.psychology:
        battle.events.append(BattleEvent(
            f"{regiment.name} cannot break (CantBreak).", "leadership_test",
            regiment=regiment.identifier, opponent=opponent.identifier, leadership=regiment.leadership,
            modifier=modifier, cant_break=True, roll=None, passed=True))
        return
    roll = _2_to_12(battle.rng)
    passed = modifier + roll <= regiment.leadership
    battle.events.append(BattleEvent(
        f"{regiment.name} takes a Leadership test (Ld {regiment.leadership}, roll {roll} + {modifier}): "
        f"{'passes' if passed else 'fails'}.", "leadership_test",
        regiment=regiment.identifier, opponent=opponent.identifier, leadership=regiment.leadership,
        roll=roll, modifier=modifier, cant_break=False, passed=passed))
    if not passed:
        _start_rout(regiment, battle)


def _start_rout(regiment, battle):
    flee_x, flee_y = battle._flee_point(regiment)
    regiment.routing = True
    regiment.in_melee = False
    regiment.melee_opponent = None
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
        if not regiment.routing:
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
