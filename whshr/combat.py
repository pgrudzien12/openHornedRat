"""Close combat, morale, rally and shooting resolution, stdlib-only (no frontend import).

Called from `whshr.engine.Battle.tick`. Rules are simplified from `notes/game_rules.md` sections
5-8 (see the module docstring of each function for what is skipped); this is not meant to reproduce
the original byte-for-byte, only to give a deterministic, documented first playable battle.

Close combat is resolved model by model on the shared battle grid (`whshr.battle_grid`,
game_rules.md 5.7): a model strikes only once it holds a cell orthogonally next to an enemy model and
has walked into it, and it strikes that one model, so there is no front-rank rule and a deep unit
wraps around over several ticks.

Simplifications common to this module (documented placeholders, not traced values):
- No hatred re-rolls or monster return blows (game_rules.md 5.2, 5.4-5.6).
- Melee still treats a failed save as a lethal hit; ranged wounds are tracked per model in
  `whshr.ranged`.
- Break tests are timed and scored per the traced rules (game_rules.md 6.2): tallies accumulate rank
  and direction bonuses plus kills each strike; the first result comes two turns after contact, later
  ones every turn after that (the original varies this by Initiative). Rally follows game_rules.md 7.4's
  schedule (shared with the pursuit-restraint test, notes/pursuit_restraint.md 2), its rally-attempt
  gate and casualties-based Leadership modifier.

Every event `whshr.battle_log.BattleLogger` needs for diagnosing the playtest bugs (strike rolls,
Leadership tests, rout/rally, shooting) is emitted here as a `whshr.battle_events.BattleEvent`: a
`str` (so it still prints and compares like the old plain-string events) carrying a `kind` and a
`data` mapping of the exact numbers rolled.
"""
import math
import random
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from . import animation, battle_grid, formation, interpreter
from .battle_events import BattleEvent
from .rules import EXPECTED_ARMOUR_SAVE, Side, may_engage, wfb_to_hit, wfb_to_wound

if TYPE_CHECKING:
    from .engine import Battle, ModelState, Regiment

Fight = dict[str, Any]  # one shared fight (`Battle.fights[id]`): grid, segment, next_test_turn, rounds, tally, breakdown
Roll = dict[str, Any]  # one logged die roll sequence (hit / wound / save / result)
Breakdown = dict[Side, dict[str, int]]  # per side: kills, rank and direction bonus behind a tally
Blast = Mapping[str, int]  # a death blast: radius, strength, kind

SEGMENT_TICKS = 19  # game_rules.md, "Battle clock": 19 ticks per segment
SEGMENTS_PER_TURN = 10  # game_rules.md 5.1: segments count down from 10 to 1 within a turn
FLEE_SAFE_DISTANCE = 160.0  # game_rules.md 7.4: no rally attempt while an enemy is this close
# game_rules.md 7.7: a pursuing or charging unit makes automatic contact attacks on models within this
# reach (18 for cavalry and 24 for monsters are not modelled: the engine has no unit class).
CONTACT_REACH = 12.0
DIRECTION_BONUS: dict[int, int] = {0: 0, 1: 1, 2: 2, 3: 1}  # front, flank, rear, flank (game_rules.md 6.1)


def _d6(rng: random.Random) -> int:
    return rng.randint(1, 6)


def _2_to_12(rng: random.Random) -> int:
    return rng.randint(2, 12)


def leadership_test(leadership: float, rng: random.Random, modifier: float = 0) -> bool:
    """game_rules.md 7.1: pass <=> modifier + (uniform 2-12) <= Leadership (not 2D6)."""
    return modifier + _2_to_12(rng) <= leadership


def _armour_threshold(armour: int, strength: int) -> int:
    save = EXPECTED_ARMOUR_SAVE[armour] if 0 <= armour < len(EXPECTED_ARMOUR_SAVE) else 7
    return save + max(0, strength - 3)


def armour_threshold(armour: int, strength: int) -> int:
    """The D6 score that saves against a hit of `strength` (game_rules.md 5.3); 7 or more cannot save."""
    return _armour_threshold(armour, strength)


def apply_casualties(regiment: "Regiment", count: int, rng: random.Random, battle: "Battle",
                     death_kind: int = animation.DEATH_ORDINARY, killer: str | None = None) -> int:
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
    positions = list(regiment.model_positions())
    indices = (rng.sample(range(len(positions)), count) if count < len(positions)
               else list(range(len(positions))))
    return kill_models(regiment, indices, battle=battle, death_kind=death_kind, killer=killer)


def pay_credit(battle: "Battle", victim: "Regiment", model: "ModelState") -> None:
    """A model leaves ``victim`` (killed or removed alive): the unit it credits gains one kill and the victim
    unit's current ``points`` as experience (notes/casualty_bookkeeping.md 2.0, 2.2).  There is no side test, so
    friendly fire and a caster slaying its own unit are credited too; a credit naming no unit pays nothing."""
    credited = battle.regiments.get(model.credit) if model.credit is not None else None
    if credited is None:
        return
    credited.kills += 1
    credited.experience_gained += victim.points


def pay_removal_credits(battle: "Battle", regiment: "Regiment") -> None:
    """Every model still in ``regiment`` leaves the battle alive (it fled off the map, or a script removed it): each
    one pays whatever credit it still carries (notes/casualty_bookkeeping.md 2.1, "stale credit")."""
    for model in regiment.melee_models:
        pay_credit(battle, regiment, model)
        model.credit = None


def kill_models(regiment: "Regiment", indices: Iterable[int], battle: "Battle",
                death_kind: int = animation.DEATH_ORDINARY, killer: str | None = None,
                clear_credit: bool = False) -> int:
    """Remove the named models, leaving corpses where they stood and freeing any grid cells they held.

    Unlike a whole-formation reseed, the surviving models keep their identity (`ModelState.uid`) and
    their position, so every pairing and cell on the battle grid still names exactly the model it
    named before: nothing has to be renumbered, and a death can never silently re-point a surviving
    pairing at a different model.

    `death_kind` is the damage type of the killing wound (game_rules.md "Figure animation", "Death
    kinds": 0 ordinary, 1 fire, 2 missile / slain outright, 3 warpfire). Kinds 1-3 collapse in one tick;
    kinds 1 and 3 then burn (`animation.burns_on_death`) instead of leaving the family's own corpse.
    Callers: close combat and contact attacks pass 0; ordinary shooting passes 2; innate
    breath, warpfire and death blasts pass their fire or warpfire kind.

    Kill credit (notes/casualty_bookkeeping.md 2.1): the hit that removes a model names the unit credited with it.
    ``killer`` (the striking, shooting or casting unit) overwrites each victim's credit; ``clear_credit`` (an
    artillery misfire) clears it; with neither, the credit the model already carries is paid.  Every removal here
    is lethal, so the any-wound and lethal-only write rules of the report both reduce to "the killer is credited".
    PROVISIONAL: the credit is paid when the model leaves the formation, which is when its collapse delay
    starts, so a model still collapsing when the battle ends counts as a casualty and is credited (the report's
    2.4 does neither).
    """
    indices = list(indices)
    if not indices or regiment.models <= 0 or "CantDie" in regiment.psychology:
        return 0
    positions = list(regiment.model_positions())
    victims = sorted({index for index in indices if 0 <= index < len(positions)}, reverse=True)
    if not victims:
        return 0
    leader_killed = regiment.leader_uid is not None and any(
        regiment.melee_models[index].uid == regiment.leader_uid for index in victims)
    if regiment.hud_class == "art" and leader_killed:
        regiment.machine_alive = False
        regiment.clear_anchor()
        regiment.shooting_mode = regiment.shooting_target = None
        regiment.volley_countdown = None
    grid = _grid_of(battle, regiment)
    dead_opponents: dict[int, tuple[str, int] | None] = {}
    for index in victims:
        model = regiment.melee_models[index]
        if clear_credit:
            model.credit = None
        elif killer is not None:
            model.credit = killer
        pay_credit(battle, regiment, model)
        delay = animation.collapse_delay_ticks(model.stagger, regiment.in_melee, death_kind)
        if delay > 0:
            regiment.dying.append(animation.DyingModel(
                *positions[index], model=model, ticks_left=delay, death_kind=death_kind,
                body=regiment.body_class, burns=regiment.burns_on(death_kind)))
        else:
            animation.step(model, animation.DEAD, battle.rng, regiment.animation_family)
            regiment.corpses.append((*positions[index], battle.rng.randrange(animation.FULL_TURN)))
        dead_opponents[model.uid] = model.opponent
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
    if leader_killed:
        battle.event_bus.queue_event(regiment.identifier, interpreter.Event(code=0x17), route="self")
    _unpair_dead(battle, regiment, dead_opponents)
    sprite = (regiment.sprite or "").casefold()
    if death_kind not in (animation.DEATH_FIRE, animation.DEATH_WARPFIRE):
        if "warpfire" in sprite:
            puffs, final = warpfire_death_schedule(*positions[victims[-1]])
            battle.death_blasts.extend((battle.tick_count + delay, "puff", px, py)
                                       for delay, px, py in puffs)
            battle.death_blasts.append((battle.tick_count + final, "warpfire", *positions[victims[-1]]))
        elif "giant" in sprite:
            battle.death_blasts.append((battle.tick_count, "giant", *positions[victims[-1]]))
    return len(victims)


def _grid_of(battle: "Battle", regiment: "Regiment") -> battle_grid.BattleGrid | None:
    fight = battle.fights.get(regiment.melee_group) if regiment.melee_group is not None else None
    return fight.get("grid") if fight else None


def _unpair_dead(battle: "Battle", regiment: "Regiment", dead_opponents: dict[int, tuple[str, int] | None]) -> None:
    """Release every enemy model that was fighting one of the models just killed (`dead_opponents`: dead model uid ->
    that model's own opponent). A survivor the dead model was fighting back is woken; a ganging attacker stays at
    rest (notes/grid_gap_closing.md 2.4)."""
    for other in battle.regiments.values():
        for model in other.melee_models:
            if model.opponent is None or model.opponent[0] != regiment.identifier:
                continue
            if model.opponent[1] in dead_opponents:
                mutual = dead_opponents[model.opponent[1]] == (other.identifier, model.uid)
                battle_grid.unpair_survivor(model, was_its_opponent=mutual)


def _rank_bonus(attacker: "Regiment") -> int:
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


def _direction_bonus(attacker: "Regiment", defender: "Regiment") -> int:
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


def _roll_model_attacks(attacker: "Regiment", defender: "Regiment", rng: random.Random, charge_bonus: int = 0,
                        gang_bonus: int = 0, attacks: int | None = None, ws: int | None = None,
                        strength: int | None = None, model: "ModelState | None" = None,
                        mount_attack: bool = False,
                        defender_model: "ModelState | None" = None) -> tuple[bool, Roll]:
    """One model's attacks against the one enemy model it is paired with (game_rules.md 5.2).

    Returns `(killed, detail)`: `killed` is True once any wound gets past the save, because this
    engine still tracks one wound per model (the module's documented multi-wound simplification).
    `detail` records the target numbers and every roll made, for the battle log.

    `gang_bonus` is the ganging-up +1 WS every attacker after the defender's designated opponent
    gets; `charge_bonus` is the +1 S spent one attacking model at a time from the unit's charge
    counter.
    """
    leader = model is not None and attacker.leader_model(model) and not mount_attack
    defending_leader = defender_model is not None and defender.leader_model(defender_model)
    defending_toughness = defender.model_toughness(defender_model) if defender_model is not None else defender.toughness
    defending_armour = defender.model_armour(defender_model) if defender_model is not None else defender.armour
    defending_ws = (defender.leader_ws if defending_leader and defender.leader_ws is not None else defender.ws)
    base_attacks = attacker.leader_attacks if leader and attacker.leader_attacks is not None else attacker.attacks
    attacks = max(1, base_attacks) if attacks is None else attacks
    if leader and defending_leader and "ItemParryingBlade" in defender.items:
        attacks = max(0, attacks - 1)
    base_ws = attacker.leader_ws if leader and attacker.leader_ws is not None else attacker.ws
    weapon_skill = base_ws if ws is None else ws
    if leader:
        weapon_skill += int("ItemGrudgeBringer" in attacker.items) + int("ItemBannerOfMight" in attacker.items)
    hit_need = wfb_to_hit(min(10, weapon_skill + gang_bonus), defending_ws)
    base_strength = attacker.leader_strength if leader and attacker.leader_strength is not None else attacker.strength
    strength = (base_strength + attacker.strength_bonus + charge_bonus if strength is None else strength)
    strength += int(attacker.fight_harder)
    if leader:
        strength += (int("ItemGrudgeBringer" in attacker.items)
                     + int("ItemSwordOfMight" in attacker.items) + 3 * int(attacker.potion_strength))
        if "ItemSwordOfHeroes" in attacker.items and defending_toughness >= 5:
            strength += 3
        if "ItemRockSplitter" in attacker.items and defender.unit_class in {4, 7, 9}:
            strength += 5
    strength = min(9, strength)
    wound_need = wfb_to_wound(strength, defending_toughness)
    threshold = 4 if defending_armour == 6 else _armour_threshold(defending_armour, strength)
    wound_rolls = 1
    if leader:
        wound_rolls += int("ItemDragonBlade" in attacker.items)
        if "ItemSwordOfElior" in attacker.items and defender.race == 2:
            wound_rolls *= 2
        if "ItemRockSplitter" in attacker.items and defender.unit_class in {4, 7, 9}:
            wound_rolls += 5
    detail: Roll = {"attacks": attacks, "hit_need": hit_need, "wound_need": wound_need,
              "save_need": threshold, "gang_bonus": gang_bonus, "wound_rolls": wound_rolls, "rolls": []}
    if wound_need > 6:
        return False, detail
    killed = False
    for _ in range(attacks):
        hit_roll = _d6(rng)
        if hit_roll < hit_need:
            detail["rolls"].append({"hit": hit_roll, "wound": None, "save": None, "result": "missed"})
            continue
        for _ in range(wound_rolls):
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


def refresh_melee_state(battle: "Battle") -> None:
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
        gone = _opponent_gone(battle, regiment, regiment.melee_touching)
        battle_grid.release(battle, regiment)
        regiment.in_melee = False
        regiment.melee_camp = None
        regiment.melee_group = None
        regiment.melee_touching = frozenset()
        _reform_for_pursuit(battle, regiment)
        if gone:
            _send_opponent_gone(battle, regiment)
        # The unit's *order* survives leaving a fight: leaving a grid never touches one (game_rules.md 5.7), and the
        # pursuit granted when the last enemy broke is issued on the very tick before this runs.
        # Clearing it here cancelled every pursuit one tick after it started. A target that is gone
        # is dropped by `Battle._advance_regiments` instead.


def refresh_braced_state(battle: "Battle") -> None:
    """Clear a regiment's Braced status (game_rules.md "Braced") once the charger it braced against
    is gone -- inactive, fled, no longer charging it, or routing (routing units are never engaged in melee, so they are no
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
        charger = battle.regiments.get(regiment.braced_target) if regiment.braced_target is not None else None
        # A charger that has itself stopped charging this regiment (it braced against someone else, was halted,
        # or lost its target) is no threat either. Without this two regiments that charged each other braced
        # against one another for good -- neither can be ordered out of it.
        if (charger is None or not charger.active or charger.routing
                or charger.attack_target != regiment.identifier):
            regiment.braced = False
            regiment.braced_target = None


OPPONENT_GONE_EVENT = 0x19  # game_rules.md event table: "current opponent gone"


def _opponent_gone(battle: "Battle", regiment: "Regiment", touched: Iterable[str]) -> bool:
    """True when every regiment this one was fighting is destroyed or off the field. A routing opponent
    is not gone: the rout itself (event 0x0F) decides between pursuit and a new opponent."""
    touched = list(touched)
    return bool(touched) and all(
        other is None or not other.active for other in (battle.regiments.get(i) for i in touched))


def _send_opponent_gone(battle: "Battle", regiment: "Regiment") -> None:
    """Queue event 0x19 to `regiment` (game_rules.md section 5, "Leaving": its opponent is gone and no
    other enemy remains on the grid), so its script clears the target and re-forms."""
    battle.event_bus.queue_event(regiment.identifier, interpreter.Event(code=OPPONENT_GONE_EVENT), route="self")


def _fight_has_enemy(battle: "Battle", regiment: "Regiment") -> bool:
    """True while some active, standing enemy is still in `regiment`'s fight."""
    if regiment.melee_group is None:
        return False
    return any(other.active and not other.routing
               and other.camp != regiment.camp
               and other.melee_group == regiment.melee_group
               for other in battle.regiments.values())


def segment_state(tick_count: int) -> tuple[int, int, int]:
    """(absolute_segment, turn, segment_number): segment_number counts down 10..1 within each 10-segment
    turn (game_rules.md 5.1); `absolute_segment` is a global segment counter used for rally scheduling."""
    absolute_segment = tick_count // SEGMENT_TICKS
    turn, segment_in_turn = divmod(absolute_segment, SEGMENTS_PER_TURN)
    return absolute_segment, turn, SEGMENTS_PER_TURN - segment_in_turn


def schedule_rally_segment(regiment: "Regiment", battle: "Battle") -> None:
    """notes/pursuit_restraint.md 2: at a rout or pursuit start the scheduled segment is the current segment
    number, so the first check comes one full turn (SEGMENTS_PER_TURN boundaries) later."""
    regiment.rally_segment = segment_state(battle.tick_count)[2]
    regiment.rally_schedule_tick = battle.tick_count


def rally_check_due(regiment: "Regiment", battle: "Battle") -> bool:
    """notes/pursuit_restraint.md 2: on a segment boundary, the scheduled check runs only when the new segment
    number equals the scheduled segment **and** the rally-attempt state is on. When it runs, the schedule moves
    3 segments on (`s - 3`, wrapped into 1..10); when the state is off nothing happens and `s` is kept."""
    if (not regiment.rally_attempt or regiment.rally_segment is None
            or battle.tick_count == regiment.rally_schedule_tick
            or segment_state(battle.tick_count)[2] != regiment.rally_segment):
        return False
    regiment.rally_segment = next_rally_segment(regiment.rally_segment)
    return True


def next_rally_segment(segment: int) -> int:
    """notes/pursuit_restraint.md 2: `s - 3`, plus 10 when below 1 (10 -> 7 -> 4 -> 1 -> 8 -> ...)."""
    segment -= 3
    return segment + SEGMENTS_PER_TURN if segment < 1 else segment


def pursuit_restraint_test(battle: "Battle", regiment: "Regiment") -> bool:
    """notes/pursuit_restraint.md 4 steps 2-3: the restraint test of a pursuer whose scheduled check runs.
    `AlwaysPursue` skips the roll (the pursuit continues); otherwise a plain Leadership test with no modifier
    against the effective Leadership (leader's Ld, else the regiment's). Casualties, nearby enemies and
    `CantRally` do not matter here. Returns whether the pursuit stops."""
    if "AlwaysPursue" in regiment.psychology:
        battle.events.append(BattleEvent(
            f"{regiment.name} always pursues: no restraint test.", "restraint_test",
            regiment=regiment.identifier, leadership=regiment.effective_leadership, roll=None, passed=False))
        return False
    roll = _2_to_12(battle.rng)
    passed = roll <= regiment.effective_leadership
    battle.events.append(BattleEvent(
        f"{regiment.name} takes a restraint test (Ld {regiment.effective_leadership}, roll {roll}): "
        f"{'stops the pursuit' if passed else 'keeps pursuing'}.", "restraint_test",
        regiment=regiment.identifier, leadership=regiment.effective_leadership, roll=roll, passed=passed))
    return passed


def _empty_breakdown() -> Breakdown:
    return {side: {"kills": 0, "rank": 0, "direction": 0} for side in Side}


def _new_fight(turn: int, segment: int) -> Fight:
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


def _new_fight_id(battle: "Battle") -> str:
    battle.fight_seq += 1
    return f"fight{battle.fight_seq}"


def _merge_fights(battle: "Battle", keep_id: str, other_ids: Iterable[str]) -> None:
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


def _split_scripted_pair(first: "Regiment", second: "Regiment") -> None:
    """A scripted same-side engagement starts: the regiment whose script named the other as its
    opponent (the attacker) takes the `Side.DUEL` camp, so the two are opponents in every
    tally, break test and grid check that follows (rules.may_engage)."""
    attacker = first if first.attack_target == second.identifier else second
    attacker.melee_camp = Side.DUEL


def resolve_contacts(battle: "Battle") -> None:
    """Group regiments whose oriented footprints actually touch into shared fights (game_rules.md 5.7's
    battle grid: several regiments per side may share one fight, so a side can gang up on a lone enemy);
    a routing regiment is never engaged in close combat (game_rules.md 7.7: "pursuers never engage
    fleeing units in close combat"). Recomputed every tick so a regiment that dies or a footprint that
    shrinks below contact range releases its neighbours, and a third regiment closing in joins the fight
    already in progress instead of starting a separate 1v1.

    Two different sides may still not fight on contact: `rules.can_fight` excludes Player-Neutral
    specifically (NPCs never fight the player, even by bumping into them), while still allowing
    Enemy-Neutral so a mission's own scripted threat against neutrals plays out physically."""
    _, turn, segment = segment_state(battle.tick_count)
    active = [r for r in battle.regiments.values() if r.active and not r.hidden and not r.routing]
    by_id = {r.identifier: r for r in active}
    touching: dict[str, set[str]] = {r.identifier: set() for r in active}
    old_touching = {r.identifier: r.melee_touching for r in active}
    # With behaviour scripts running, touching footprints only raise contact events (0x0B); a fight starts only
    # when a unit's contact handler asks for it (Battle.engage_requests; notes/script_behaviours.md 2.0, 2.10).
    scripted = battle.interpreter is not None
    contacts: list[tuple["Regiment", "Regiment"]] = []
    for i, first in enumerate(active):
        for second in active[i + 1:]:
            if not may_engage(first, second):
                continue
            if formation.penetrates(first.block(), second.block()):
                if scripted:
                    contacts.append((first, second))
                    continue
                if first.camp == second.camp:
                    _split_scripted_pair(first, second)
                touching[first.identifier].add(second.identifier)
                touching[second.identifier].add(first.identifier)
    pending_counter: dict[str, int] = {}
    if battle.interpreter is not None:
        battle.interpreter.raise_wagon_collisions(active)  # before the pass clears the re-check states
        battle.interpreter.raise_contacts(contacts)
        for joiner_id, owner_id, counter in battle.engage_requests:
            if joiner_id in by_id and owner_id in by_id:
                touching[joiner_id].add(owner_id)
                touching[owner_id].add(joiner_id)
                pending_counter[joiner_id] = counter
        battle.engage_requests.clear()

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

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for identifier, neighbours in touching.items():
        for enemy_id in neighbours:
            root_a, root_b = find(identifier), find(enemy_id)
            if root_a != root_b:
                parent[root_a] = root_b

    components: dict[str, list[str]] = {}
    for identifier in touching:
        if touching[identifier]:
            components.setdefault(find(identifier), []).append(identifier)

    kept_groups: set[str] = set()
    for members in components.values():
        existing_ids = sorted({group for group in (by_id[m].melee_group for m in members) if group})
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
                opponent = (regiment.attack_target or
                            (sorted(touching[identifier])[0] if regiment.free_charging and touching[identifier]
                             else None))
                if scripted:
                    if identifier in pending_counter:
                        regiment.charge_counter = pending_counter[identifier]
                elif opponent in touching[identifier]:
                    if opponent == regiment.last_fought_opponent:
                        regiment.charge_counter = 0
                    else:
                        regiment.charge_counter = int(1.5 * regiment.frontage)
                    regiment.last_fought_opponent = opponent
                regiment.melee_group = group_id
                regiment.target_x = regiment.target_y = None
            if not regiment.in_melee:
                battle.end_reform_for_engagement(regiment)  # notes/reform_while_moving.md 8
            regiment.in_melee = True
            regiment.free_charging = False
        fight = battle.fights[group_id]
        group = [by_id[identifier] for identifier in sorted(members)]
        if fight.get("grid") is None:
            fight["grid"] = battle_grid.create(battle, group_id, group)
        battle_grid.update(battle, group_id, fight["grid"], group)

    for identifier, regiment in by_id.items():
        if not touching[identifier] and regiment.in_melee:
            gone = _opponent_gone(battle, regiment, old_touching[identifier])
            battle_grid.release(battle, regiment)
            regiment.in_melee = False
            regiment.melee_camp = None
            regiment.melee_group = None
            regiment.melee_touching = frozenset()
            _reform_for_pursuit(battle, regiment)
            if gone:
                _send_opponent_gone(battle, regiment)

    for group_id in list(battle.fights):
        if group_id not in kept_groups:
            battle.fights.pop(group_id, None)


def resolve_melee(battle: "Battle") -> None:
    """A unit strikes only in its own Initiative segment, once per turn (game_rules.md 5.1); each of its
    paired, arrived models strikes the one enemy model it faces on the grid (5.7), and the kills plus
    the unit's rank and direction bonus accumulate into its fight's own-side tally (6.1). At each turn's
    last segment, every fight's losing side (by tally difference) takes a break test, timed by that
    fight's `next_test_turn` (6.2, simplified: every turn once due, instead of varying with Initiative)."""
    _, turn, segment_number = segment_state(battle.tick_count)
    groups: dict[str, list["Regiment"]] = {}
    for regiment in battle.regiments.values():
        # A regiment that was destroyed or fled mid-fight is dropped from `resolve_contacts`' active
        # set, so it keeps `in_melee` and its group id after the fight record itself is gone.
        if (regiment.in_melee and regiment.melee_group is not None and regiment.melee_group in battle.fights
                and regiment.active):
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


def _strike_with_models(attacker: "Regiment", group_id: str, fight: Fight, turn: int, segment_number: int,
                        battle: "Battle") -> None:
    """Every one of `attacker`'s paired, arrived models strikes the single enemy model it faces
    (game_rules.md 5.2/5.7). Kills are applied to the specific models that were struck, and the
    unit's own rank and direction bonus are added once to its side's tally (6.1)."""
    pairs = battle_grid.fighting_models(battle, attacker)
    if not pairs:
        return
    victims: dict[str, set[int]] = {}  # defending regiment id -> set of model indices killed this strike
    rolls: list[Roll] = []
    kills = 0
    for _, model, defender, defender_index in pairs:
        defender_model = defender.melee_models[defender_index]
        # game_rules.md 5.2: the defender's designated opponent fights at its own WS; every further
        # attacker on that same model gets the ganging-up +1 WS.
        battle_grid.grab(attacker, model, defender_model)  # an unpaired victim is grabbed (grid_gap_closing.md 4)
        gang_bonus = 0 if defender_model.opponent == (attacker.identifier, model.uid) else 1
        charge_bonus = 1 if attacker.charge_counter > 0 else 0
        if attacker.charge_counter > 0:
            attacker.charge_counter -= 1  # spent one attacking model at a time (5.5)
        killed, detail = _roll_model_attacks(attacker, defender, battle.rng,
                                             charge_bonus=charge_bonus, gang_bonus=gang_bonus, model=model,
                                             defender_model=defender_model)
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
                attacks=mount["A"], ws=mount["WS"], strength=mount_strength,
                model=model, mount_attack=True, defender_model=defender_model)
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
        kill_models(battle.regiments[defender_id], indices, battle=battle, killer=attacker.identifier)
    defender = battle.regiments[max(victims, key=lambda key: len(victims[key]))] if victims else pairs[0][2]
    rank_bonus = _rank_bonus(attacker)
    direction_bonus = _direction_bonus(attacker, defender)
    fight["tally"][attacker.camp] += kills + rank_bonus + direction_bonus
    breakdown = fight["breakdown"][attacker.camp]
    breakdown["kills"] += kills
    breakdown["rank"] += rank_bonus
    breakdown["direction"] += direction_bonus
    battle.events.append(BattleEvent(
        f"{attacker.name} strikes {defender.name} in segment {segment_number} (turn {turn}): "
        f"{len(pairs)} models fighting, {kills} casualties, side tally "
        f"{fight['tally'][attacker.camp]:.0f} (+{rank_bonus} rank, +{direction_bonus} dir).",
        "melee_strike",
        attacker=attacker.identifier, defender=defender.identifier, fight=group_id, turn=turn,
        segment=segment_number, kills=kills, fighting=len(pairs), rank_bonus=rank_bonus,
        direction_bonus=direction_bonus, charge_counter=attacker.charge_counter,
        tally=dict(fight["tally"]), attacks=rolls))


def _resolve_group_break_test(group_id: str, members: Sequence["Regiment"], turn: int, battle: "Battle") -> None:
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
    present = {regiment.camp for regiment in members}
    if len(present) >= 2:
        tallies = {side: fight["tally"][side] for side in present}
        winning_tally = max(tallies.values())
        losing_side, losing_tally = min(tallies.items(), key=lambda item: item[1])
        modifier = winning_tally - losing_tally
        if modifier != 0:
            breakdown = {side: dict(fight["breakdown"][side]) for side in Side}
            for regiment in members:
                if regiment.camp == losing_side and seen.get(regiment.identifier, 0) >= 2:
                    _break_test(regiment, modifier, group_id, breakdown, battle)
    fight["tally"] = {side: 0.0 for side in Side}
    fight["breakdown"] = _empty_breakdown()
    fight["next_test_turn"] = turn + 1


def _break_test(regiment: "Regiment", modifier: float, group_id: str, breakdown: Breakdown,
                battle: "Battle") -> None:
    """The losing side's Leadership test (game_rules.md 6.2, simplified). Logs every check, including a
    skipped one (regiment already destroyed or CantBreak), so a rout can always be traced back to its
    exact Ld, roll, modifier and the kills/rank/direction breakdown (per side) behind that modifier."""
    if not regiment.active:
        return
    if "CantBreak" in regiment.psychology:
        battle.events.append(BattleEvent(
            f"{regiment.name} cannot break (CantBreak).", "leadership_test",
            regiment=regiment.identifier, fight=group_id, leadership=regiment.base_leadership,
            modifier=modifier, breakdown=breakdown, cant_break=True, roll=None, passed=True))
        return
    roll = _2_to_12(battle.rng)
    passed = modifier + roll <= regiment.effective_leadership
    battle.events.append(BattleEvent(
        f"{regiment.name} takes a Leadership test (Ld {regiment.base_leadership}, roll {roll} + {modifier}): "
        f"{'passes' if passed else 'fails'}.", "leadership_test",
        regiment=regiment.identifier, fight=group_id, leadership=regiment.base_leadership,
        roll=roll, modifier=modifier, breakdown=breakdown, cant_break=False, passed=passed))
    if not passed:
        start_rout(regiment, battle)


def _reform_for_pursuit(battle: "Battle", regiment: "Regiment") -> None:
    """A pursuer leaving its fight starts the pursuit with a re-form to the script's ranks
    (notes/reform_while_moving.md 4): the pursuit runs at half speed, its figures carried, until they settle."""
    if regiment.pursuing and regiment.models > 0:
        battle.reform_to_ranks(regiment, regiment.script_ranks)


def leave_grid(battle: "Battle", regiment: "Regiment") -> None:
    """Take a regiment out of its fight's grid (game_rules.md 5.7, "Leaving"): its models are unpaired and the
    melee state is cleared. Orders and targets survive; the opponent finds out on the next pairing pass."""
    battle_grid.release(battle, regiment)
    regiment.in_melee = False
    regiment.melee_camp = None
    regiment.melee_group = None
    regiment.melee_touching = frozenset()


def start_rout(regiment: "Regiment", battle: "Battle", flee_point: formation.Point | None = None) -> None:
    # game_rules.md "Flight and catching fleeing units": the flight starts "directly away from its
    # opponent" - a one-time bearing, not re-aimed every tick at whichever enemy is momentarily
    # nearest (whshr.engine.Battle._advance_regiments reads this fixed point back every tick).
    # `flee_point` overrides that bearing (a scripted flight along the unit's own facing).
    flee_x, flee_y = flee_point if flee_point is not None else battle.flee_point(regiment)
    regiment.flee_x, regiment.flee_y = flee_x, flee_y
    group_id = regiment.melee_group
    opponents = [other for other in battle.regiments.values()
                 if other.active and other.camp != regiment.camp
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
            if opponent is not None and opponent_index is not None:
                opposing_model = opponent.melee_models[opponent_index]
                opposing_model.rout_pause_ticks = max(opposing_model.rout_pause_ticks, pause)
    battle_grid.release(battle, regiment)
    regiment.routing = True
    regiment.flight_check_ticks = 0
    regiment.flight_departed = False
    regiment.flight_complete = False
    regiment.flight_complete_tick = -1
    regiment.in_melee = False
    regiment.melee_camp = None
    regiment.melee_group = None
    regiment.melee_touching = frozenset()
    regiment.attack_target = None
    regiment.target_x = regiment.target_y = None
    # notes/pursuit_restraint.md 2: a rout resets the rally-attempt state, switching it on only for a player
    # regiment with Independent set, and schedules the first rally attempt one full turn later.
    regiment.pursuing = False
    regiment.pursuit_budget = regiment.pursuit_point = None
    regiment.rally_attempt = regiment.side == Side.PLAYER and regiment.independent
    schedule_rally_segment(regiment, battle)
    battle.events.append(BattleEvent(
        f"{regiment.name} routs!", "rout_start",
        regiment=regiment.identifier, x=regiment.x, y=regiment.y, flee_x=flee_x, flee_y=flee_y))
    _react_to_rout(regiment, opponents, group_id, battle)


def _react_to_rout(routed: "Regiment", opponents: Sequence["Regiment"], group_id: str | None,
                   battle: "Battle") -> None:
    """game_rules.md 7.5: the routed unit's opponents "first look for another opponent in the same
    fight and switch to it if there is one; otherwise pursue".

    Without this a victorious unit is simply released from the fight and stands idle until the player
    orders it somewhere, which is not what the original does.

    The chase budget, edge probe and restraint test run in `Battle._update_pursuits`
    (notes/pursuit_map_edge.md 2, notes/pursuit_restraint.md 4). Simplifications: no "more attractive
    target" check (game_rules.md 7.5); the pursuit is an ordinary charge order at the fleeing
    unit, which `resolve_contacts` will not turn back into close combat while that unit is routing
    (7.7: "pursuers never engage fleeing units in close combat"). Player missile troops never pursue,
    standing in for the traced "player artillery, wizards and archers never pursue".
    """
    for opponent in opponents:
        if opponent.routing or not opponent.active:
            continue
        still_fighting = any(
            other.active and not other.routing and other.camp != opponent.camp
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
        opponent.pursuing = True  # notes/pursuit_map_edge.md: a pursuit, not a charge
        opponent.free_charging = False  # starting a pursuit ends the charging state (bf003_playtest 5.2)
        opponent.pursuit_budget = opponent.pursuit_point = None
        # notes/pursuit_restraint.md 2: a pursuit start switches the rally-attempt state off (even for an
        # Independent regiment) and schedules the first possible restraint test one full turn later.
        opponent.rally_attempt = False
        schedule_rally_segment(opponent, battle)
        battle.events.append(BattleEvent(
            f"{opponent.name} pursues {routed.name}!", "pursuit_start",
            regiment=opponent.identifier, target=routed.identifier))


def resolve_contact_attacks(battle: "Battle") -> None:
    """game_rules.md 7.7: a charging or pursuing unit makes **contact attacks** on the models of a unit
    within `CONTACT_REACH`, once per segment.

    This is the only damage a chase ever does: a pursuer can never re-engage its fugitive in close
    combat, because a routing unit is excluded from engagement entirely. Each attacking model gets its
    `attacks` tries spread over the target models in reach, and a fleeing model -- running with its back
    turned -- is **hit automatically**: only the to-wound roll and the armour save are made, with no
    to-hit roll (game_rules.md 5.2).

    A unit that is not charging or pursuing makes them on a broken enemy it overlaps too, but that is checked every
    tick (`resolve_router_contact_attacks`), not only here.

    Simplifications: the reach is the infantry 12 (the engine has no unit class for the cavalry 18 and
    monster 24), and contact hits still ignore the rout pause's timed "turning" state, in which a model
    would get a to-hit roll -- every target model here is taken to be running.
    """
    segment = battle.tick_count // SEGMENT_TICKS
    for attacker in sorted(battle.regiments.values(), key=lambda r: r.identifier):
        if not attacker.active or attacker.routing or attacker.in_melee or attacker.contact_attack_segment == segment:
            continue  # a unit that made its contact attacks this segment (for instance for behaviour 14) is spent
        target = battle.regiments.get(attacker.attack_target) if attacker.attack_target else None
        if target is None or not target.active or not target.routing:
            continue  # contact attacks only matter against a unit that cannot fight back
        attacker.contact_attack_segment = segment
        contact_attack(battle, attacker, target)


def contact_attack(battle: "Battle", attacker: "Regiment", target: "Regiment") -> int:
    """The automatic contact attacks of `attacker`'s models on `target`'s models in reach (game_rules.md 7.7); returns
    the models killed. The caller decides who may attack and stamps the segment."""
    victims, rolls = _contact_attack_rolls(attacker, target, battle.rng)
    if not rolls:
        return 0
    killed = kill_models(target, victims, battle=battle, killer=attacker.identifier)
    battle.events.append(BattleEvent(
        f"{attacker.name} cuts down {killed} {'fleeing ' if target.routing else ''}{target.name}."
        if killed else f"{attacker.name} reaches {target.name} but draws no blood.",
        "contact_attack",
        attacker=attacker.identifier, target=target.identifier, kills=killed,
        reach=CONTACT_REACH, rolls=rolls))
    return killed


CLASS_CAVALRY, CLASS_ARTILLERY, CLASS_MONSTER = 2, 4, 6  # s_race >> 3 (game_rules.md 3, s_race)
TOUCH_ONLY_CLASSES = frozenset({0, 7, 8, 9})  # no type, rolling stock, special, furniture: touched, never wounded
LANDING_REACH = {CLASS_CAVALRY: 18.0, CLASS_MONSTER: 24.0}  # everything else 12
LANDING_MELEE_FILTER = 204.0  # the coarse filter's radius for a unit in melee (notes/script_spawn_move.md 5)


def squig_landing(battle: "Battle", hopper: "Regiment") -> bool:
    """The hop landing collision of FanaticRelease (notes/script_spawn_move.md 5): at the hopper's leader model, every
    model of a fighting unit within reach (12, 18 against cavalry, 24 against monsters) takes the hopper's Strength
    wound roll with the armour save allowed, one wound each; artillery crews are hit the same way. Rolling stock,
    special units, furniture, standing buildings and scenery are only touched; an artillery piece is touched too, and
    its crew models are wounded but not its machine. The hopper never dies. Every object is tested; the result is
    True when a model was wounded or anything was touched.

    PROVISIONAL: the coarse filter before the per-model test (the unit's bounding radius, twice that when it is
    charging, 204 in melee); a unit leaving the battle or hidden is not touched; the D6 rolls the fanatic makes
    against an artillery machine are not made (nothing is documented about what they do), so the machine model takes
    no wound roll; buildings and scenery are touched within their footprint radius."""
    positions = hopper.model_positions()
    leader = hopper.leader_model_index
    lx, ly = positions[leader] if leader is not None and leader < len(positions) else (hopper.x, hopper.y)
    strength = hopper.strength + hopper.strength_bonus
    engaged = False
    for other in sorted(battle.regiments.values(), key=lambda r: r.identifier):
        if other is hopper or not other.active or other.hidden or _marked(battle, other):
            continue
        charging = other.attack_target is not None or other.free_charging
        limit = LANDING_MELEE_FILTER if other.in_melee else other.bounding_radius() * (2 if charging else 1)
        if math.hypot(other.x - lx, other.y - ly) >= limit:
            continue
        if other.is_wagon or other.unit_class in TOUCH_ONLY_CLASSES:
            engaged = True  # rolling stock, a special unit or furniture: touched, nothing more
            continue
        artillery = other.unit_class == CLASS_ARTILLERY or other.hud_class == "art"
        engaged = engaged or artillery  # an artillery piece counts as touched whatever the crew rolls do
        machine = other.leader_model_index if artillery else None
        reach = LANDING_REACH.get(other.unit_class if other.unit_class is not None else -1, CONTACT_REACH)
        victims: list[int] = []
        rolls: list[Roll] = []
        for index, (mx, my) in enumerate(other.model_positions()):
            if index == machine or math.hypot(mx - lx, my - ly) > reach:
                continue
            model = other.melee_models[index]
            need = wfb_to_wound(strength, other.model_toughness(model))
            wound_roll = _d6(battle.rng)
            if need > 6 or wound_roll < need:
                rolls.append({"target_model": index, "wound": wound_roll, "save": None, "result": "no_wound"})
                continue
            save_roll = _d6(battle.rng)
            if save_roll >= _armour_threshold(other.model_armour(model), strength):
                rolls.append({"target_model": index, "wound": wound_roll, "save": save_roll, "result": "saved"})
                continue
            model.wounds_taken += 1
            engaged = True
            rolls.append({"target_model": index, "wound": wound_roll, "save": save_roll, "result": "wounded"})
            if model.wounds_taken >= other.model_wounds(model):
                victims.append(index)
        if victims:
            kill_models(other, victims, battle=battle, killer=hopper.identifier)
        if rolls:
            battle.events.append(BattleEvent(
                f"{hopper.name} lands among {other.name}.", "squig_landing",
                attacker=hopper.identifier, target=other.identifier, kills=len(victims), rolls=rolls))
    point_hit = any(math.hypot(b.x - lx, b.y - ly) < b.radius for b in battle.buildings if not b.destroyed)
    point_hit = point_hit or any(
        math.hypot(float(obj.get("x") or 0) - lx, float(obj.get("y") or 0) - ly) < float(obj.get("radius") or 0)
        for obj in battle.objects if "os_active" in {str(flag).casefold() for flag in obj.get("status") or ()})
    return engaged or point_hit


def _marked(battle: "Battle", unit: "Regiment") -> bool:
    state = battle.event_bus.unit_states.get(unit.identifier)
    return state is not None and bool(state.unit_flags & interpreter.LEAVING_BATTLE_FLAG)


def resolve_router_contact_attacks(battle: "Battle") -> None:
    """Every tick: a unit that is not in melee makes contact attacks on a broken enemy whose footprint it overlaps
    although it is not charging or pursuing (notes/script_behaviours.md 2.2, "U need not be charging"), at most
    once per segment (game_rules.md 7.7). The first such router by identifier. Nothing happens for a marked
    (leaving) attacker or router, or against a router with CantMelee (notes/game_rules.md, psychology table).
    PROVISIONAL: the original runs this inside the router's own collision pass; here the router's re-check state is
    not required (a fleeing unit moves every update anyway)."""
    segment = battle.tick_count // SEGMENT_TICKS
    ordered = sorted(battle.regiments.values(), key=lambda r: r.identifier)
    for attacker in ordered:
        if (not attacker.active or attacker.routing or attacker.in_melee or attacker.contact_attack_segment == segment
                or _marked(battle, attacker)):
            continue
        for router in ordered:
            if (router is not attacker and router.active and router.routing and not router.hidden
                    and "CantMelee" not in router.psychology and not _marked(battle, router)
                    and may_engage(attacker, router) and formation.penetrates(attacker.block(), router.block())):
                attacker.contact_attack_segment = segment
                contact_attack(battle, attacker, router)
                break


def resolve_building_assaults(battle: "Battle") -> None:
    """Regiments fighting a building strike in their own Initiative segment (notes/building_units.md 4): every
    attacking model's attacks hit automatically and wound the building's first model at its own toughness, with
    no save; the building never strikes back and nothing counts for a combat result. Frenzy doubles the attacks.

    PROVISIONAL: the original lays the attackers along the building's sides on the battle grid; here the number of
    attacking models is capped by the side cells, 2 x (frontage + depth) in 12-unit cells, and no grid is built.
    Not modelled: the armour save (assumed none) and the Rocksplitter bonuses."""
    _, _, segment_number = segment_state(battle.tick_count)
    for regiment in sorted(battle.regiments.values(), key=lambda r: r.identifier):
        building = battle.building_index.get(regiment.assaulting_building or "")
        if regiment.assaulting_building is None:
            continue
        if building is None or building.destroyed or not regiment.active or regiment.routing:
            regiment.assaulting_building = None
            continue
        if regiment.initiative != segment_number:
            continue
        cells = round(2 * building.half_x / 12) + round(2 * building.half_y / 12)
        attackers = min(regiment.models, 2 * cells)
        attacks = max(1, regiment.attacks) * (2 if "Frenzy" in regiment.psychology else 1)
        strength = min(9, regiment.strength + regiment.strength_bonus + int(regiment.fight_harder))
        need = wfb_to_wound(strength, building.toughness)
        if need > 6:
            continue
        wounds = sum(1 for _ in range(attackers * attacks) if _d6(battle.rng) >= need)
        battle.events.append(BattleEvent(
            f"{regiment.name} hacks at the {building.name}.", "building_hit",
            regiment=regiment.identifier, building=building.identifier, wounds=wounds))
        if building.take_wounds(wounds, regiment.identifier):
            battle.destroy_building(building)


def _contact_attack_rolls(attacker: "Regiment", target: "Regiment", rng: random.Random) -> tuple[set[int], list[Roll]]:
    """Automatic hits from every attacking model against the target models within reach."""
    attacker_positions = attacker.model_positions()
    target_positions = target.model_positions()
    strength = attacker.strength + attacker.strength_bonus
    wound_need = wfb_to_wound(strength, target.toughness)
    threshold = _armour_threshold(target.armour, strength)
    victims: set[int] = set()
    rolls: list[Roll] = []
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


def _rally_modifier(regiment: "Regiment") -> int | None:
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


def resolve_rally(battle: "Battle") -> None:
    """A routing regiment may rally once its scheduled segment has come, its rally-attempt state is on (the
    player's Rally order, or Independent at the rout) and no enemy is within FLEE_SAFE_DISTANCE (game_rules.md
    "Rally", notes/pursuit_restraint.md 2). Logs every due rally check, including why it was skipped
    (CantRally, too many casualties, enemy too close); a regiment whose segment has not come yet, or whose
    rally-attempt state is off, makes no attempt at all (an AI regiment never gets the state on, so it keeps
    fleeing)."""
    for regiment in battle.regiments.values():
        # A regiment that has fled off the field is permanently out (game_rules.md, "Flight"): once
        # `fled`, `active` is false forever, so it must never be offered another rally attempt.
        if not regiment.routing or not regiment.active or regiment.flight_complete:
            continue
        # The scheduled segment has come with the state on: whatever happens below, the next poll (if the unit
        # is still routing) is 3 segments away, independent of why this attempt did not rally.
        if not rally_check_due(regiment, battle):
            continue
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
        nearest = battle.nearest_enemy(regiment)
        distance = math.hypot(nearest.x - regiment.x, nearest.y - regiment.y) if nearest is not None else None
        if distance is not None and distance < FLEE_SAFE_DISTANCE:
            battle.events.append(BattleEvent(
                f"{regiment.name} cannot rally: an enemy is {distance:.0f} units away.", "rally_test",
                regiment=regiment.identifier, cant_rally=False, blocked_by_enemy=True,
                nearest_enemy_distance=distance, roll=None, passed=False))
            continue
        roll = _2_to_12(battle.rng)
        passed = modifier + roll <= regiment.effective_leadership
        battle.events.append(BattleEvent(
            f"{regiment.name} takes a rally test (Ld {regiment.base_leadership}, roll {roll} + {modifier}): "
            f"{'rallies' if passed else 'still routing'}.", "rally_test",
            regiment=regiment.identifier, cant_rally=False, blocked_by_enemy=False,
            leadership=regiment.base_leadership, roll=roll, modifier=modifier, passed=passed))
        if passed:
            if battle.interpreter is not None:
                # The common event handler switches to script 163; its Rally opcode halts and
                # re-forms the unit. Clearing routing here strands an idling script at the edge.
                battle.event_bus.queue_event(regiment.identifier, interpreter.Event(code=0x10), route="self")
            else:
                regiment.routing = False
                regiment.rally_attempt = False  # as the Rally opcode (notes/pursuit_restraint.md 5)


def resolve_shooting(battle: "Battle") -> None:
    """Advance ordinary missiles and consume animation posts via the shared ranged path."""
    from . import ranged
    ranged.tick(battle)


# Death blasts (game_rules.md "Figure animation", end of the death-kind section).
WARPFIRE_BLAST: dict[str, int] = {"radius": 48, "strength": 5, "kind": animation.DEATH_WARPFIRE}
GIANT_BLAST: dict[str, int] = {"radius": 40, "strength": 5, "kind": animation.DEATH_MISSILE}
# Flame puffs of a dying Warpfire Thrower: the centre, then 8 units right, left, up and down, two ticks
# apart; the final blast follows the last puff (the exact gap is not documented: PROVISIONAL, one tick).
WARPFIRE_PUFF_OFFSETS = ((0, 0), (8, 0), (-8, 0), (0, 8), (0, -8))
WARPFIRE_PUFF_SPACING = 2


def warpfire_death_schedule(x: float, y: float) -> tuple[list[tuple[int, float, float]], int]:
    """Flame puffs of a Warpfire Thrower dying from a non-fire kind: ``[(tick, x, y)]`` with tick 0 the
    death, then the final blast tick (PROVISIONAL: one tick after the last puff)."""
    puffs = [(i * WARPFIRE_PUFF_SPACING, x + dx, y + dy) for i, (dx, dy) in enumerate(WARPFIRE_PUFF_OFFSETS)]
    return puffs, puffs[-1][0] + 1


def resolve_death_blast(battle: "Battle", x: float, y: float, blast: Blast) -> dict[str, int]:
    """A blast of `blast` (`WARPFIRE_BLAST` or `GIANT_BLAST`) centred at (x, y): every model closer than the
    radius takes one D6 wound roll at the blast strength (to-wound chart, armour save, then a D6 count of
    wounds; multi-wound models die when the count reaches their Wounds). Kills carry the blast's death
    kind, so a warpfire blast's victims burn green. Returns ``{regiment identifier: kills}``.

    Not hooked up: the engine has no Warpfire Thrower or Giant unit with a death event yet, so nothing
    calls this outside tests (notes/engine_gaps/figure_animation.md).
    """
    kills: dict[str, int] = {}
    for regiment in battle.regiments.values():
        if not regiment.active or regiment.models <= 0:
            continue
        need = wfb_to_wound(blast["strength"], regiment.toughness)
        threshold = _armour_threshold(regiment.armour, blast["strength"])
        victims: list[int] = []
        for index, (mx, my) in enumerate(regiment.model_positions()):
            if math.hypot(mx - x, my - y) >= blast["radius"]:
                continue
            if _d6(battle.rng) < need or _d6(battle.rng) >= threshold:
                continue
            if _d6(battle.rng) >= regiment.wounds:
                victims.append(index)
        if victims:
            kills[regiment.identifier] = kill_models(regiment, victims, battle=battle, death_kind=blast["kind"])
    return kills
