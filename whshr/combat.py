"""Close combat, morale, rally and shooting resolution, stdlib-only (no frontend import).

Called from `whshr.engine.Battle.tick`. Rules are simplified from `notes/game_rules.md` sections
5-8 (see the module docstring of each function for what is skipped); this is not meant to reproduce
the original byte-for-byte, only to give a deterministic, documented first playable battle.

Close combat is resolved model by model on the shared battle grid (`whshr.battle_grid`,
game_rules.md 5.7): a model strikes only once it holds a cell orthogonally next to an enemy model and
has walked into it, and it strikes that one model, so there is no front-rank rule and a deep unit
wraps around over several ticks.

Simplifications common to this module (documented placeholders, not traced values):
- No hatred re-rolls, magic items or monster return blows (game_rules.md 5.2, 5.4-5.6).
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

from . import animation, battle_grid, formation
from .battle_events import BattleEvent
from .rules import EXPECTED_ARMOUR_SAVE, Side, can_fight, hostile_sides, wfb_to_hit, wfb_to_wound

SEGMENT_TICKS = 19  # game_rules.md, "Battle clock": 19 ticks per segment
SEGMENTS_PER_TURN = 10  # game_rules.md 5.1: segments count down from 10 to 1 within a turn
FLEE_SAFE_DISTANCE = 160.0  # game_rules.md 7.4: no rally attempt while an enemy is this close
# game_rules.md 7.7: a pursuing or charging unit makes automatic contact attacks on models within this
# reach (18 for cavalry and 24 for monsters are not modelled: the engine has no unit class).
CONTACT_REACH = 12.0
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


def apply_casualties(regiment, count, rng, battle):
    """Remove up to `count` randomly chosen models, turning them into corpses at their positions.

    Used where the original does not single out a victim (shooting, spells). Close combat kills the
    specific model that was struck instead, through `kill_models`. `battle` is required so that the
    models left fighting a corpse are always released, whatever killed it.

    game_rules.md 7.6: `CantDie` models are never removed by wounds. The combat result score still
    counts every wound rolled against them regardless (the callers score the raw wound count, not
    this function's return value): the notes do not say whether a `CantDie` model's wounds count
    toward the break-test tally, so this is a documented placeholder that they do.
    """
    if count <= 0 or regiment.models <= 0 or "CantDie" in regiment.psychology:
        return 0
    count = min(count, regiment.models)
    positions = regiment.model_positions()
    indices = (rng.sample(range(len(positions)), count) if count < len(positions)
               else list(range(len(positions))))
    return kill_models(regiment, indices, battle=battle)


def kill_models(regiment, indices, battle):
    """Remove the named models, leaving corpses where they stood and freeing any grid cells they held.

    Unlike a whole-formation reseed, the surviving models keep their identity (`ModelState.uid`) and
    their position, so every pairing and cell on the battle grid still names exactly the model it
    named before: nothing has to be renumbered, and a death can never silently re-point a surviving
    pairing at a different model.
    """
    if not indices or regiment.models <= 0 or "CantDie" in regiment.psychology:
        return 0
    positions = regiment.model_positions()
    victims = sorted({index for index in indices if 0 <= index < len(positions)}, reverse=True)
    if not victims:
        return 0
    grid = _grid_of(battle, regiment)
    dead_uids = set()
    for index in victims:
        model = regiment.melee_models[index]
        delay = animation.collapse_delay_ticks(model.stagger, regiment.in_melee)
        if delay > 0:
            regiment.dying.append(animation.DyingModel(*positions[index], model=model, ticks_left=delay))
        else:
            animation.step(model, animation.DEAD, battle.rng, regiment.animation_family)
            regiment.corpses.append((*positions[index], battle.rng.randrange(animation.FULL_TURN)))
        dead_uids.add(model.uid)
        if grid is not None and model.cell is not None:
            grid.clear(model.cell)
        del regiment.positions[index]
        del regiment.melee_models[index]
        # Keep an in-progress re-form's per-model slot assignment index-parallel with the survivors
        # (game_rules.md "Formation changes"): a stale entry here would hand some other model's
        # target to whoever now sits at this index.
        if index < len(regiment.reform_slots):
            del regiment.reform_slots[index]
    regiment.models -= len(victims)
    _unpair_dead(battle, regiment, dead_uids)
    return len(victims)


def _grid_of(battle, regiment):
    fight = battle.fights.get(regiment.melee_group)
    return fight.get("grid") if fight else None


def _unpair_dead(battle, regiment, dead_uids):
    """Release every enemy model that was fighting one of the models just killed."""
    for other in battle.regiments.values():
        for model in other.melee_models:
            if model.opponent is None or model.opponent[0] != regiment.identifier:
                continue
            if model.opponent[1] in dead_uids:
                model.opponent = None
                model.arrived = False


def _rank_bonus(attacker):
    """game_rules.md 6.1: if frontage > 3, `size / width - 1` full ranks behind the first, uncapped.

    `width` is the regiment's **formed** frontage, which the original does not reduce as models die
    (only a re-form recomputes it), while `size` is the live model count. The bonus therefore decays
    as a unit takes casualties and disappears once it is down to less than two full ranks. Deriving
    the width from the current model count instead keeps it pinned near `ranks - 1` for the whole
    fight, which inflates every combat result the unit is part of.
    """
    frontage = attacker.frontage
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


def _roll_model_attacks(attacker, defender, rng, charge_bonus=0, gang_bonus=0,
                        attacks=None, ws=None, strength=None):
    """One model's attacks against the one enemy model it is paired with (game_rules.md 5.2).

    Returns `(killed, detail)`: `killed` is True once any wound gets past the save, because this
    engine still tracks one wound per model (the module's documented multi-wound simplification).
    `detail` records the target numbers and every roll made, for the battle log.

    `gang_bonus` is the ganging-up +1 WS every attacker after the defender's designated opponent
    gets; `charge_bonus` is the +1 S spent one attacking model at a time from the unit's charge
    counter.
    """
    attacks = max(1, attacker.attacks) if attacks is None else attacks
    hit_need = wfb_to_hit((attacker.ws if ws is None else ws) + gang_bonus, defender.ws)
    strength = (attacker.strength + attacker.strength_bonus + charge_bonus
                if strength is None else strength)
    wound_need = wfb_to_wound(strength, defender.toughness)
    threshold = _armour_threshold(defender.armour, strength)
    detail = {"attacks": attacks, "hit_need": hit_need, "wound_need": wound_need,
              "save_need": threshold, "gang_bonus": gang_bonus, "rolls": []}
    if wound_need > 6:
        return False, detail
    killed = False
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
        killed = True
    return killed, detail


def refresh_melee_state(battle):
    """Free a regiment from melee one tick early (before `_advance_regiments` unfreezes it) once **no
    enemy remains in its fight at all** (game_rules.md 5.7, "Leaving": a unit leaves the grid on
    destruction, rout, or when no enemy remains on it).

    The test is over the whole fight, not over the regiment's own `melee_touching` list: several
    regiments share one grid, so the enemy a given regiment happened to be touching can rout while the
    fight it belongs to carries on around it. Testing only the touching list made a unit walk away
    from a melee its allies were still locked in.
    """
    for regiment in battle.regiments.values():
        if not regiment.in_melee:
            continue
        if _fight_has_enemy(battle, regiment):
            continue
        battle_grid.release(battle, regiment)
        regiment.in_melee = False
        regiment.melee_group = None
        regiment.melee_touching = frozenset()
        # The unit's *order* survives leaving a fight: leaving a grid never touches one (game_rules.md 5.7), and the
        # pursuit granted when the last enemy broke is issued on the very tick before this runs.
        # Clearing it here cancelled every pursuit one tick after it started. A target that is gone
        # is dropped by `Battle._advance_regiments` instead.


def refresh_braced_state(battle):
    """Clear a regiment's Braced status (game_rules.md "Braced") once the charger it braced against
    is gone -- inactive, fled, or routing (routing units are never engaged in melee, so they are no
    longer a threat this unit needs to brace against) -- or once it has itself joined melee, where
    `in_melee` already suppresses orders more completely. `interpreter.op_FearWhenCharged` sets
    Braced; `Battle.order_halt` also clears it as the one order still accepted while braced.
    """
    for regiment in battle.regiments.values():
        if not regiment.braced:
            continue
        if regiment.in_melee:
            regiment.braced = False
            regiment.braced_target = None
            continue
        charger = battle.regiments.get(regiment.braced_target)
        if charger is None or not charger.active or charger.routing:
            regiment.braced = False
            regiment.braced_target = None


def _fight_has_enemy(battle, regiment):
    """True while some active, standing enemy is still in `regiment`'s fight."""
    if regiment.melee_group is None:
        return False
    return any(other.active and not other.routing
               and other.side != regiment.side
               and other.melee_group == regiment.melee_group
               for other in battle.regiments.values())


def _segment_state(tick_count):
    """(absolute_segment, turn, segment_number): segment_number counts down 10..1 within each 10-segment
    turn (game_rules.md 5.1); `absolute_segment` is a global segment counter used for rally scheduling."""
    absolute_segment = tick_count // SEGMENT_TICKS
    turn, segment_in_turn = divmod(absolute_segment, SEGMENTS_PER_TURN)
    return absolute_segment, turn, SEGMENTS_PER_TURN - segment_in_turn


def _empty_breakdown():
    return {side: {"kills": 0, "rank": 0, "direction": 0} for side in Side}


def _new_fight(turn, segment):
    return {
        "grid": None,  # whshr.battle_grid.BattleGrid, seeded on the first tick of the fight
        # game_rules.md 6.2: the result is evaluated in the grid's own creation segment, so the fight
        # remembers it; the first result comes two turns after contact, later ones every turn.
        "segment": segment,
        "next_test_turn": turn + 2,
        "rounds": {},  # regiment id -> result segments it has seen on this grid (6.2's +0x33C)
        # Keyed by Side rather than the two-sided bool this engine used before three sides existed
        # (notes/neutral_units.md): a fight normally still has only two sides in it, but nothing stops
        # a neutral regiment from being dragged into one (see _resolve_group_break_test).
        "tally": {side: 0.0 for side in Side},
        "breakdown": _empty_breakdown(),
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
        for side in Side:
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
    already in progress instead of starting a separate 1v1.

    Two different sides may still not fight on contact: `rules.can_fight` excludes Player-Neutral
    specifically (NPCs never fight the player, even by bumping into them), while still allowing
    Enemy-Neutral so a mission's own scripted threat against neutrals plays out physically."""
    _, turn, segment = _segment_state(battle.tick_count)
    active = [r for r in battle.regiments.values() if r.active and not r.routing]
    by_id = {r.identifier: r for r in active}
    touching = {r.identifier: set() for r in active}
    old_touching = {r.identifier: r.melee_touching for r in active}
    for i, first in enumerate(active):
        for second in active[i + 1:]:
            if not can_fight(first.side, second.side):
                continue
            if formation.penetrates(first.block(), second.block()):
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

    # game_rules.md 5.7, "Leaving": a unit leaves a fight on destruction, rout, or when no enemy
    # remains on it -- never because the two footprints drifted apart. Since a formation's footprint
    # shrinks as its models die, re-deriving engagement from geometry alone would silently disengage
    # units that are still fighting, so an existing engagement is kept alive here as long as the enemy
    # it names is still an active, standing member of the same fight (`active` already excludes the
    # dead and the routing).
    for identifier, regiment in by_id.items():
        if not regiment.in_melee or not regiment.melee_group:
            continue
        for enemy_id in old_touching[identifier]:
            enemy = by_id.get(enemy_id)
            if enemy is not None and enemy.melee_group == regiment.melee_group:
                touching[identifier].add(enemy_id)
                touching[enemy_id].add(identifier)

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
            battle.fights[group_id] = _new_fight(turn, segment)
        kept_groups.add(group_id)
        for identifier in members:
            regiment = by_id[identifier]
            regiment.melee_touching = frozenset(touching[identifier])
            if regiment.melee_group != group_id:
                # game_rules.md 5.7: "engaging clears the pairing of A's models", so every new
                # engagement re-pairs from scratch. This matters when fights merge or a regiment moves
                # between them: its cells belong to the grid it is leaving, and would otherwise be
                # read against the new grid's frame.
                battle_grid.release(battle, regiment)
                # game_rules.md 5.5: the moving side with a charge/pursuit order is the charger and gets
                # +1 S on its first strike after joining a fight (whether the fight is brand new or a
                # third regiment joining one already under way). The counter is spent one attacking
                # model at a time, so only the first 1.5 x frontage models to strike get the bonus.
                # Re-engaging an opponent this regiment was already recorded fighting stores 0 instead.
                opponent = regiment.attack_target
                if opponent in touching[identifier]:
                    if opponent == regiment.last_fought_opponent:
                        regiment.charge_counter = 0
                    else:
                        regiment.charge_counter = int(1.5 * regiment.frontage)
                    regiment.last_fought_opponent = opponent
                regiment.melee_group = group_id
                regiment.target_x = regiment.target_y = None
            regiment.in_melee = True
        fight = battle.fights[group_id]
        group = [by_id[identifier] for identifier in sorted(members)]
        if fight.get("grid") is None:
            fight["grid"] = battle_grid.create(battle, group_id, group)
        battle_grid.update(battle, group_id, fight["grid"], group)

    for identifier, regiment in by_id.items():
        if not touching[identifier] and regiment.in_melee:
            battle_grid.release(battle, regiment)
            regiment.in_melee = False
            regiment.melee_group = None
            regiment.melee_touching = frozenset()

    for group_id in list(battle.fights):
        if group_id not in kept_groups:
            battle.fights.pop(group_id, None)


def resolve_melee(battle):
    """A unit strikes only in its own Initiative segment, once per turn (game_rules.md 5.1); each of its
    paired, arrived models strikes the one enemy model it faces on the grid (5.7), and the kills plus
    the unit's rank and direction bonus accumulate into its fight's own-side tally (6.1). At each turn's
    last segment, every fight's losing side (by tally difference) takes a break test, timed by that
    fight's `next_test_turn` (6.2, simplified: every turn once due, instead of varying with Initiative)."""
    _, turn, segment_number = _segment_state(battle.tick_count)
    groups = {}
    for regiment in battle.regiments.values():
        # A regiment that was destroyed or fled mid-fight is dropped from `resolve_contacts`' active
        # set, so it keeps `in_melee` and its group id after the fight record itself is gone.
        if regiment.in_melee and regiment.melee_group in battle.fights and regiment.active:
            groups.setdefault(regiment.melee_group, []).append(regiment)
    for group_id, members in groups.items():
        fight = battle.fights[group_id]
        # game_rules.md 6.2: every break test on a grid resolves **before** any unit strikes in that
        # segment, and only in the grid's own creation segment. Testing at the end of the turn instead
        # folded a whole extra turn of rank and direction bonuses into every modifier.
        if segment_number == fight["segment"]:
            _resolve_group_break_test(group_id, members, turn, battle)
        for attacker in members:
            if attacker.initiative != segment_number:
                continue
            _strike_with_models(attacker, group_id, fight, turn, segment_number, battle)


def _strike_with_models(attacker, group_id, fight, turn, segment_number, battle):
    """Every one of `attacker`'s paired, arrived models strikes the single enemy model it faces
    (game_rules.md 5.2/5.7). Kills are applied to the specific models that were struck, and the
    unit's own rank and direction bonus are added once to its side's tally (6.1)."""
    pairs = battle_grid.fighting_models(battle, attacker)
    if not pairs:
        return
    victims = {}  # defending regiment id -> set of model indices killed this strike
    rolls = []
    kills = 0
    for index, model, defender, defender_index in pairs:
        defender_model = defender.melee_models[defender_index]
        # game_rules.md 5.2: the defender's designated opponent fights at its own WS; every further
        # attacker on that same model gets the ganging-up +1 WS.
        gang_bonus = 0 if defender_model.opponent == (attacker.identifier, model.uid) else 1
        charge_bonus = 1 if attacker.charge_counter > 0 else 0
        if attacker.charge_counter > 0:
            attacker.charge_counter -= 1  # spent one attacking model at a time (5.5)
        killed, detail = _roll_model_attacks(attacker, defender, battle.rng,
                                             charge_bonus=charge_bonus, gang_bonus=gang_bonus)
        detail.update({"model": model.uid, "target": defender.identifier,
                       "target_model": defender_model.uid, "charge_bonus": charge_bonus,
                       "source": "rider"})
        rolls.append(detail)
        mount = attacker.mount_profile
        if mount is not None:
            mount_charge = attacker.charge_counter > 0
            if mount_charge:
                attacker.charge_counter -= 1
            mount_strength = mount["charge_strength"] if mount_charge else mount["S"]
            mount_killed, mount_detail = _roll_model_attacks(
                attacker, defender, battle.rng, gang_bonus=gang_bonus,
                attacks=mount["A"], ws=mount["WS"], strength=mount_strength)
            mount_detail.update({"model": model.uid, "target": defender.identifier,
                                 "target_model": defender_model.uid,
                                 "charge_bonus": mount_charge, "source": "mount"})
            rolls.append(mount_detail)
            killed |= mount_killed
        # game_rules.md 5.5: consumed at two points per model per round -- the attack resolution that
        # grants the +1 S above, and a second decrement here once this model's round is fully resolved.
        if attacker.charge_counter > 0:
            attacker.charge_counter -= 1
        if killed and defender_index not in victims.get(defender.identifier, ()):
            victims.setdefault(defender.identifier, set()).add(defender_index)
            kills += 1
    for defender_id, indices in victims.items():
        kill_models(battle.regiments[defender_id], indices, battle=battle)
    defender = battle.regiments[max(victims, key=lambda key: len(victims[key]))] if victims else pairs[0][2]
    rank_bonus = _rank_bonus(attacker)
    direction_bonus = _direction_bonus(attacker, defender)
    fight["tally"][attacker.side] += kills + rank_bonus + direction_bonus
    breakdown = fight["breakdown"][attacker.side]
    breakdown["kills"] += kills
    breakdown["rank"] += rank_bonus
    breakdown["direction"] += direction_bonus
    battle.events.append(BattleEvent(
        f"{attacker.name} strikes {defender.name} in segment {segment_number} (turn {turn}): "
        f"{len(pairs)} models fighting, {kills} casualties, side tally "
        f"{fight['tally'][attacker.side]:.0f} (+{rank_bonus} rank, +{direction_bonus} dir).",
        "melee_strike",
        attacker=attacker.identifier, defender=defender.identifier, fight=group_id, turn=turn,
        segment=segment_number, kills=kills, fighting=len(pairs), rank_bonus=rank_bonus,
        direction_bonus=direction_bonus, charge_counter=attacker.charge_counter,
        tally=dict(fight["tally"]), attacks=rolls))


def _resolve_group_break_test(group_id, members, turn, battle):
    """Evaluate one fight's break test once it is due (game_rules.md 6.2): only the losing side (by
    accumulated tally) is tested, every active regiment on that side; the tally and its breakdown reset
    and the next test is due next turn.

    A fight normally has exactly two sides in it (the original binary player/enemy case this was
    traced from); the loser is then simply whichever of the two has the lower tally, by the same
    margin as before. With three possible sides (notes/neutral_units.md) a fight that happens to draw
    in all three at once has no traced original behaviour to match, so this picks the single lowest-
    tally side as the loser against the single highest, a direct, undocumented generalisation of the
    two-sided rule rather than a researched three-way one.

    Each regiment also counts the result segments it has seen on this grid, and is exempt from the
    first of them (the traced `+0x33C >= 2` rule), so a regiment that joins a fight late cannot be
    broken by a result it was not present for.
    """
    fight = battle.fights[group_id]
    seen = fight["rounds"]
    for regiment in members:
        seen[regiment.identifier] = seen.get(regiment.identifier, 0) + 1
    if turn < fight["next_test_turn"]:
        return
    present = {regiment.side for regiment in members}
    if len(present) >= 2:
        tallies = {side: fight["tally"][side] for side in present}
        winning_tally = max(tallies.values())
        losing_side, losing_tally = min(tallies.items(), key=lambda item: item[1])
        modifier = winning_tally - losing_tally
        if modifier != 0:
            breakdown = {side: dict(fight["breakdown"][side]) for side in Side}
            for regiment in members:
                if regiment.side == losing_side and seen.get(regiment.identifier, 0) >= 2:
                    _break_test(regiment, modifier, group_id, breakdown, battle)
    fight["tally"] = {side: 0.0 for side in Side}
    fight["breakdown"] = _empty_breakdown()
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
    # game_rules.md "Flight and catching fleeing units": the flight starts "directly away from its
    # opponent" - a one-time bearing, not re-aimed every tick at whichever enemy is momentarily
    # nearest (whshr.engine.Battle._advance_regiments reads this fixed point back every tick).
    flee_x, flee_y = battle._flee_point(regiment)
    regiment.flee_x, regiment.flee_y = flee_x, flee_y
    group_id = regiment.melee_group
    opponents = [other for other in battle.regiments.values()
                 if other.active and other.side != regiment.side
                 and other.melee_group == group_id and group_id is not None]
    regiment.model_positions()
    for index, model in enumerate(regiment.melee_models):
        if not model.at_rest:
            continue
        pause = (model.stagger & 7) * 3 + 6
        model.rout_pause_ticks = pause
        model.at_rest = False
        model.current_speed = model.distance_budget = 0.0
        # The public rule specifies a slight scatter, but not its exact distance or bearing.
        px, py = regiment.positions[index]
        regiment.positions[index] = (px + (1 if model.stagger & 1 else -1),
                                     py + (1 if model.stagger & 2 else -1))
        if group_id is not None and model.opponent is not None:
            opponent_id, opponent_uid = model.opponent
            opponent = battle.regiments.get(opponent_id)
            opponent_index = opponent.index_of(opponent_uid) if opponent is not None else None
            if opponent_index is not None:
                opposing_model = opponent.melee_models[opponent_index]
                opposing_model.rout_pause_ticks = max(opposing_model.rout_pause_ticks, pause)
    battle_grid.release(battle, regiment)
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
    _react_to_rout(regiment, opponents, group_id, battle)


def _react_to_rout(routed, opponents, group_id, battle):
    """game_rules.md 7.5: the routed unit's opponents "first look for another opponent in the same
    fight and switch to it if there is one; otherwise pursue".

    Without this a victorious unit is simply released from the fight and stands idle until the player
    orders it somewhere, which is not what the original does.

    Simplifications: the pursuit has no chase budget, restraint test or "more attractive target"
    check (game_rules.md 7.5); it is an ordinary charge order at the fleeing
    unit, which `resolve_contacts` will not turn back into close combat while that unit is routing
    (7.7: "pursuers never engage fleeing units in close combat"). Player missile troops never pursue,
    standing in for the traced "player artillery, wizards and archers never pursue".
    """
    for opponent in opponents:
        if opponent.routing or not opponent.active:
            continue
        still_fighting = any(
            other.active and not other.routing and other.side != opponent.side
            and other.melee_group == group_id
            for other in battle.regiments.values())
        if still_fighting:
            continue  # another enemy is still on this grid: keep fighting it, do not pursue
        if opponent.anchored:
            continue  # an anchored war machine never pursues
        if opponent.missile_range:
            # game_rules.md 7.5: which classes decline is encoded in the behaviour scripts and applies
            # to both sides -- artillery never pursues, and shooters and wizards divert to scripts
            # 127/148 (keep shooting, re-form) instead of the pursuit script. Missile troops stand in
            # for that here, the engine having no unit class.
            continue
        opponent.attack_target = routed.identifier
        opponent.target_x = opponent.target_y = None
        battle.events.append(BattleEvent(
            f"{opponent.name} pursues {routed.name}!", "pursuit_start",
            regiment=opponent.identifier, target=routed.identifier))


def resolve_contact_attacks(battle):
    """game_rules.md 7.7: a charging or pursuing unit makes **contact attacks** on the models of a unit
    within `CONTACT_REACH`, once per segment.

    This is the only damage a chase ever does: a pursuer can never re-engage its fugitive in close
    combat, because a routing unit is excluded from engagement entirely. Each attacking model gets its
    `attacks` tries spread over the target models in reach, and a fleeing model -- running with its back
    turned -- is **hit automatically**: only the to-wound roll and the armour save are made, with no
    to-hit roll (game_rules.md 5.2).

    Simplifications: the reach is the infantry 12 (the engine has no unit class for the cavalry 18 and
    monster 24), and contact hits still ignore the rout pause's timed "turning" state, in which a model
    would get a to-hit roll -- every target model here is taken to be running.
    """
    for attacker in sorted(battle.regiments.values(), key=lambda r: r.identifier):
        if not attacker.active or attacker.routing or attacker.in_melee:
            continue
        target = battle.regiments.get(attacker.attack_target) if attacker.attack_target else None
        if target is None or not target.active or not target.routing:
            continue  # contact attacks only matter against a unit that cannot fight back
        victims, rolls = _contact_attack_rolls(attacker, target, battle.rng)
        if not rolls:
            continue
        killed = kill_models(target, victims, battle=battle)
        battle.events.append(BattleEvent(
            f"{attacker.name} cuts down {killed} fleeing {target.name}."
            if killed else f"{attacker.name} reaches {target.name} but draws no blood.",
            "contact_attack",
            attacker=attacker.identifier, target=target.identifier, kills=killed,
            reach=CONTACT_REACH, rolls=rolls))


def _contact_attack_rolls(attacker, target, rng):
    """Automatic hits from every attacking model against the target models within reach."""
    attacker_positions = attacker.model_positions()
    target_positions = target.model_positions()
    strength = attacker.strength + attacker.strength_bonus
    wound_need = wfb_to_wound(strength, target.toughness)
    threshold = _armour_threshold(target.armour, strength)
    victims, rolls = set(), []
    if wound_need > 6:
        return victims, rolls
    for ax, ay in attacker_positions:
        in_reach = [index for index, (tx, ty) in enumerate(target_positions)
                    if index not in victims and math.hypot(tx - ax, ty - ay) <= CONTACT_REACH]
        for index in in_reach[:max(1, attacker.attacks)]:
            wound_roll = _d6(rng)
            if wound_roll < wound_need:
                rolls.append({"target_model": index, "wound": wound_roll, "save": None,
                              "result": "no_wound"})
                continue
            save_roll = _d6(rng)
            if save_roll >= threshold:
                rolls.append({"target_model": index, "wound": wound_roll, "save": save_roll,
                              "result": "saved"})
                continue
            rolls.append({"target_model": index, "wound": wound_roll, "save": save_roll,
                          "result": "killed"})
            victims.add(index)
    return victims, rolls


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
    instead of geometric scatter) fire at the nearest enemy in range and front arc when not in melee.

    A volley is an N-event countdown (N = model count; 1 for artillery) that starts the moment a
    regiment is eligible and reload is ready. Reload is stamped at order time so it does not cancel
    fire events already in flight. Posts arrive one per 4 countdown decrements (1 for artillery) and
    accumulate over 5 ticks; on tick 5 (or when the countdown is exhausted sooner) the full batch
    of posts fires as one volley event (game_rules.md 8.1 and "Figure animation")."""
    for regiment in battle.regiments.values():
        if regiment.reload_ticks > 0:
            regiment.reload_ticks = max(0.0, regiment.reload_ticks - 1)
        if not regiment.missile_range or not regiment.active or regiment.in_melee or regiment.routing:
            continue
        # Charging cancels the volley entirely; moving merely delays the next one.
        if regiment.attack_target is not None:
            regiment.fire_posts = 0
            regiment.volley_countdown = None
            regiment.volley_age = 0
            continue
        target = _shooting_target(battle, regiment)
        if target is None:
            regiment.fire_posts = 0
            regiment.volley_countdown = None
            regiment.volley_age = 0
            continue
        # Start a volley: no volley in progress, not moving, reload done.
        if (regiment.volley_countdown is None and regiment.volley_age == 0
                and not regiment.moving and regiment.reload_ticks <= 0):
            regiment.volley_countdown = 1 if regiment.hud_class == "art" else regiment.models
            regiment.reload_ticks = _reload_ticks(regiment)
        # The resolve window closes when the countdown is exhausted naturally (all expected fire events
        # arrived) or after 5 ticks (handles dead-model stalls where countdown > 0 never reaches 0).
        volley_window_closed = (regiment.volley_age >= 5 or
                                (regiment.volley_countdown is None and regiment.volley_age > 0))
        if not volley_window_closed:
            continue
        shots = regiment.fire_posts
        regiment.fire_posts = 0
        regiment.volley_countdown = None
        regiment.volley_age = 0
        if shots == 0:
            continue
        distance = math.hypot(target.x - regiment.x, target.y - regiment.y)
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
        # Pass the battle so a model shot out of a melee also releases whoever was fighting it.
        apply_casualties(target, kills, battle.rng, battle=battle)
        battle.events.append(BattleEvent(
            f"{regiment.name} shoots {target.name}: {kills} casualties." if kills else
            f"{regiment.name} shoots {target.name}: no casualties.", "shooting",
            shooter=regiment.identifier, target=target.identifier, distance=distance,
            range=regiment.missile_range, shots=shots, hit_need=hit_need, wound_need=wound_need,
            save_need=threshold, rolls=rolls, kills=kills))
        battle.events.append(BattleEvent(
            f"{regiment.name} reloads: ready in {regiment.reload_ticks:.0f} ticks.", "reload",
            regiment=regiment.identifier, reload_ticks=regiment.reload_ticks))


def _shooting_target(battle, regiment):
    """The nearest active hostile regiment in range and front arc (game_rules.md 8.1). Restricted to
    `rules.hostile_sides` rather than simply "a different side" so a neutral regiment with a missile
    weapon (notes/neutral_units.md's NPC artillery) never opens fire on its own, and is never
    auto-targeted either -- shooting here is autonomous engine behaviour, not a scripted order."""
    best, best_distance = None, None
    for enemy in battle.regiments.values():
        if enemy.side not in hostile_sides(regiment.side) or not enemy.active or enemy.routing:
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
