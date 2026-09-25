"""Bytecode interpreter for per-unit behaviour scripts (SCRIPT/BFxxx.DLL).

Every live unit runs a behaviour script each tick via this interpreter, which reads the 232-opcode
instruction set (catalogued in behaviour.py). The interpreter maintains per-unit runtime state
(script id, PC, return stack, event queue) and dispatches opcodes to handlers that integrate with
the battle engine (combat, morale, movement, etc.).

The event system (14-byte records queued per unit by SendEvent, BroadcastEvent, SendEventToSide)
is the primary control mechanism: scripts GetEvent, branch on CaseEvent, and route responses via
SendEventToSelf/ToOwnSide/ToEnemySide. The interpreter's event bus matches the original's routing
(self / own side / enemy side).

Opcodes are implemented as methods on the Interpreter class, invoked dynamically via _dispatch().
Missing opcodes raise NotImplementedError, which fails gracefully if a mission doesn't use them.
"""

from dataclasses import dataclass, field
import math
import struct
from collections import deque

from . import behaviour
from .battle_events import BattleEvent
from .rules import Side

SCATTER_RADIUS = 40.0  # world units: ScatterModelsToNode's wander distance from a node's exact
# point; a documented placeholder (see op_ScatterModelsToNode), not a confirmed game value.

# Hypothesis, not a confirmed public fact (see op_MoveToNode/_update_arrival_flag): unit_flags bit
# 0x10 signals "the unit's last ordinary move order has arrived", matching the MoveToNode N;
# WaitUntilUnitFlags 16 idiom seen throughout real mission scripts. No other candidate meaning for
# that specific bit, immediately after a MoveToNode call, was found in the public notes.
ARRIVED_FLAG = 0x10
# game_rules.md, unit flags: 0x200 is "in melee" -- Otto Hiln's script tests it (`TestUnitFlags 512`) and
# the wizard casting scripts refuse to cast while it is set. Mirrored from `Regiment.in_melee`.
IN_MELEE_FLAG = 0x200

# PROVISIONAL: the search radius of the `Attack*Enemy` opcode family for a unit that never ran
# `SetThreatRange`. The units that gate a mission on "an enemy came close" (BF001's Hiln's Guard) all
# set their own range, which is used instead; the fallback is a project decision, not an observed value.
DEFAULT_ATTACK_SEARCH_RANGE = 300


def _octagonal_distance(first, second):
    """The game's cheap distance (game_rules.md, threat score): larger axis delta + half the smaller."""
    dx, dy = abs(first.x - second.x), abs(first.y - second.y)
    return max(dx, dy) + min(dx, dy) / 2


@dataclass
class Event:
    """A 14-byte behaviour event record (game_rules.md, "Unit behaviour scripts and events")."""
    recipient: int = 0  # unit identifier (ignored by the queue: events are posted to units directly)
    code: int = 0  # event code 0x00..0x23 (36 codes enumerated in game_rules.md event table)
    source: str | None = None  # sender's regiment identifier (Battle.regiments key), or None
    parameter: int = 0  # opcode-specific payload (e.g. node id for movement event)
    x: int = 0  # world coordinate (or -1 for "not set")
    y: int = 0  # world coordinate (or -1 for "not set")
    link: int = 0  # chaining pointer for multi-record sequences (0 = none)


@dataclass
class UnitScriptState:
    """Per-unit runtime state for behaviour script execution.

    Corresponds to fields in game_rules.md "+0x..." notation: script +0x242, PC +0x244, etc.
    Each unit has exactly one live state, which the interpreter updates each tick.
    """
    # Script execution
    script_id: int = 100  # current script (0..37 for mission, 100..170 for library)
    pc: int = 0  # program counter (word index into the script)
    restart_pc: int = 0  # saved by InitUnit/SetRestartPoint, restored by Restart
    return_stack: list = field(default_factory=list)  # (script_id, pc) pairs for gosub/return

    # Event handling
    current_event: Event = field(default_factory=Event)  # the event being processed this tick
    event_queue: deque = field(default_factory=lambda: deque(maxlen=128))  # pending events
    interrupt_script: int | None = None  # set by SetInterruptScript; called by CallInterruptScript
    pending_switch: int | None = None  # set by SwitchScript; applied after event handling

    # Unit state (flags set by SetUnitFlags, SetCondFlags, etc.)
    unit_flags: int = 0  # bit field (+0xB4 in the original)
    unit_flags2: int = 0  # secondary flags (+0xB8)
    cond_flags: int = 0  # truth result read by If/IfNot/LoopIf*/SendEvent*If*, written by Test*/Find*/GetEvent
    cond_bits: int = 0  # persistent condition bit word: only SetCondFlags/ClearCondFlags/TestCondFlags touch it
    threat_range: int = 0  # set by SetThreatRange; used by threat scoring
    # The single "remembered event" slot of StoreEventInfo (game_rules.md, scripted target and flight
    # opcodes): (sender regiment identifier, event code) of the event last stored, or None.
    remembered_event: tuple | None = None

    # Timing (SetWait, TestWait, Wait)
    wait_remaining: float = 0.0  # ticks left in current Wait
    wait_duration: float = 0.0  # saved duration for TestWait checks

    # Current order and target (set by FindTarget*, AttackTarget, etc.)
    current_target: tuple | None = None  # (regiment_id, unit_id) for attack/movement orders
    current_node: int | None = None  # waypoint node for movement orders
    pending_arrival: bool = False  # a MoveToNode/ScatterModelsToNode order is in flight; see
    # ScriptInterpreter._update_arrival_flag, which sets ARRIVED_FLAG on unit_flags once the
    # regiment stops moving, so a WaitUntilUnitFlags(ARRIVED_FLAG) loop can unblock
    behaviour_id: int | None = None  # declared by SetBehaviour; recorded only, not auto-run
    # (see op_SetBehaviour -- there is no confirmed public evidence for when/how often a declared
    # library behaviour like 15/TrackThreat actually gets invoked versus a unit's own script opcodes
    # driving targeting directly, so nothing currently acts on this field automatically)
    parent_id: str | None = None  # set by SetParentByTag; the regiment this unit follows/reports to

    # Interrupt handling (SetInterruptScript/CallInterruptScript/ReturnInterrupt)
    interrupt_return: tuple | None = None  # (script_id, pc) to resume after ReturnInterrupt, set by
    # CallInterruptScript; None when not currently inside an interrupt call
    last_attack_target: str | None = None  # this unit's own attack_target as of the last tick, used
    # by ScriptInterpreter.raise_charge_events to detect a *fresh* charge (event 0x07) rather than
    # re-raising it every tick the same charge continues

    # Script metadata (loaded once at init)
    script_dll = None  # behaviour.ScriptDll instance for script lookup


class EventBus:
    """Per-side event routing (self, own-side, enemy-side broadcasts)."""

    def __init__(self, battle):
        self.battle = battle
        self.unit_states = {}  # {unit_identifier: UnitScriptState}

    def queue_event(self, recipient_id: int, event: Event, route: str = "self"):
        """Queue an event to a recipient or broadcast to a side.

        route: "self" (single recipient), "side" (own-side broadcast), "enemy" (enemy-side broadcast)
        """
        if recipient_id not in self.unit_states:
            return
        state = self.unit_states[recipient_id]

        if route == "self":
            state.event_queue.append(event)
        elif route == "side":
            # Broadcast to all units on the same side as recipient
            regiment = self.battle.regiments.get(recipient_id)
            if regiment:
                for unit_id, unit_state in self.unit_states.items():
                    other = self.battle.regiments.get(unit_id)
                    if other and other.side == regiment.side:
                        unit_state.event_queue.append(event)
        elif route == "enemy":
            # Broadcast to every unit of a different side (notes/neutral_units.md leaves the exact
            # routing to/from a neutral side as an open research question -- "does event 0x13 route to
            # NPC allies?" -- so this keeps the direct two-sided "not my side" generalisation rather
            # than guessing a narrower rule).
            regiment = self.battle.regiments.get(recipient_id)
            if regiment:
                for unit_id, unit_state in self.unit_states.items():
                    other = self.battle.regiments.get(unit_id)
                    if other and other.side != regiment.side:
                        unit_state.event_queue.append(event)


class LibraryBehaviors:
    """Standard library behaviors (scripts 100-170) that are used across missions.

    Behavior 15 (TrackThreat) is the primary AI for 290+ missions:
    Keep the best threat and attack when its score exceeds the unit's worth.
    """

    def __init__(self, interpreter):
        self.interpreter = interpreter

    def track_threat(self, unit_id: str, state: UnitScriptState, tick_count: int, rng):
        """Behavior 15: TrackThreat AI - seek and attack best threat.

        Threat score = worth × (range − distance) / round(range / 4)
        Only attack if score > unit's worth (simplified: always attack if threat found).
        Distance metric: octagonal (max(|dx|, |dy|) + min(|dx|, |dy|) / 2).
        """
        battle = self.interpreter.battle
        regiment = battle.regiments.get(unit_id)
        if not regiment or regiment.side == Side.PLAYER or not regiment.active:
            return

        # Find best threat (nearest active, different-side regiment): a script that assigns this
        # library behaviour to a neutral unit has already made the targeting decision explicitly, so
        # this is not gated by rules.hostile_sides.
        best_threat = None
        best_distance = float('inf')

        for other_id, other in battle.regiments.items():
            if other.side == regiment.side or not other.active:
                continue
            dx = other.x - regiment.x
            dy = other.y - regiment.y
            distance = max(abs(dx), abs(dy)) + min(abs(dx), abs(dy)) / 2.0  # octagonal
            if distance < best_distance:
                best_threat = other_id
                best_distance = distance

        if best_threat:
            state.current_target = (best_threat, 0)
            regiment.attack_target = best_threat


# PROVISIONAL: react message text by code (game_rules.md §React N); varies by s_race & 7 (race).
# Race-specific variants are not yet mapped from the public spec; codes 10-14 (shooting/orders)
# are noted in the spec but their exact strings are unconfirmed.
_REACT_MESSAGES = {
    1: "Engage!", 2: "CHARGE!", 3: "Destroy them!", 4: "Retreat!",
    5: "My men fear the beast!", 6: "Flee the abomination!",
    7: "We fight to the death!", 8: "No mercy!", 17: "Re-group!", 19: "Hold!",
}


class ScriptInterpreter:
    """Executes one unit's behaviour script for one tick.

    Maintains per-unit state (script_id, PC, return stack, event queue) and dispatches 232 opcodes
    to handler methods. Integrates with the battle engine for effects (charging, shooting, morale).

    Handlers follow the pattern: def op_<name>(self, state, operand) -> int (new PC).
    The new PC is returned, allowing control-flow opcodes (goto, gosub, loops) to manipulate it.
    For opcodes that fall through, handlers return pc + instruction_length.
    """

    def __init__(self, battle, event_bus, script_dll, logger=None):
        self.battle = battle
        self.event_bus = event_bus
        self.script_dll = script_dll
        self.behaviors = LibraryBehaviors(self)
        self.logger = logger  # whshr.battle_log.BattleLogger, or None; see write_opcode
        self._reported_gaps = set()  # (unit_id, script_id, opcode): a missing/broken opcode already
        # surfaced as a BattleEvent once, so a tight retry loop doesn't spam the same complaint
        # every tick for the rest of the battle.

    def _state_snapshot(self, unit_id, state):
        """A small, JSON-safe snapshot of the fields opcodes actually change, for write_opcode."""
        regiment = self.battle.regiments.get(unit_id) if self.battle else None
        return {
            "pc": state.pc, "script_id": state.script_id, "cond_flags": state.cond_flags,
            "unit_flags": state.unit_flags, "pending_switch": state.pending_switch,
            "current_target": list(state.current_target) if state.current_target else None,
            "wait_remaining": state.wait_remaining,
            "attack_target": regiment.attack_target if regiment else None,
        }

    def _update_arrival_flag(self, unit_id, state):
        """If a MoveToNode/ScatterModelsToNode order is in flight (state.pending_arrival) and the
        regiment is no longer moving, set ARRIVED_FLAG so a WaitUntilUnitFlags(ARRIVED_FLAG) loop
        can unblock (see the module docstring note on ARRIVED_FLAG -- a well-evidenced hypothesis,
        not a confirmed public fact).

        Known imprecision: "no longer moving" (Regiment.moving, i.e. target_x is None) also becomes
        true if something else halts the regiment before it reaches the target (e.g. HaltAndReform,
        or a later opcode overriding movement) -- this would report "arrived" a little early in that
        case. Not observed in any real script traced so far; accepted as a documented limitation
        rather than adding a separate "was this halted, not arrived" distinction for a case that
        hasn't actually come up yet.
        """
        if not state.pending_arrival or self.battle is None:
            return
        regiment = self.battle.regiments.get(unit_id)
        if regiment is not None and not regiment.moving:
            state.unit_flags |= ARRIVED_FLAG
            state.pending_arrival = False

    def _mirror_engine_flags(self, unit_id, state):
        """Copy engine-owned conditions into the script's unit flags, so scripts see what the battle
        knows: IN_MELEE_FLAG follows `Regiment.in_melee` (raised and cleared as the fight starts and ends)."""
        regiment = self.battle.regiments.get(unit_id) if self.battle is not None else None
        if regiment is None:
            return
        if regiment.in_melee:
            state.unit_flags |= IN_MELEE_FLAG
        else:
            state.unit_flags &= ~IN_MELEE_FLAG

    def raise_charge_events(self):
        """Queue event 0x07 ("you are being charged") to any regiment an attacker has closed to
        within actual charge reach of (game_rules.md event table: 0x07 = charge start; "Charge":
        a real charge reaches at most `12 * (s_rlmv + 1)` units -- a short final rush, not the whole
        approach). NOT the moment `attack_target` is merely set: this engine (a documented
        simplification, `engine.py`'s `CLOSING_K` note) drives the entire approach through
        `attack_target` at charging speed from wherever the AI first picks a target, which can be
        the length of the battlefield -- so gating on `attack_target` alone braced the target for
        the whole approach (tens of real seconds) instead of only the real charge's short final
        rush, making every targeted player regiment uncommandable for most of the battle.

        Called once per tick from Battle.tick(), after every unit's script has run -- centralized
        here rather than duplicated in every opcode that can set attack_target (ChargeTarget,
        AttackNearestEnemy and its many variants, AttackTagged, LibraryBehaviors.track_threat, ...)
        so they all raise it consistently. Fires once per fresh charge that has reached this range
        (None/other -> this target), not every tick the same charge continues, and fires again if
        the same target is charged a second time after an intervening gap (target lost, then
        re-acquired) -- `last_attack_target` is left untouched while still out of reach, so entering
        reach is what marks the notification as sent, not merely acquiring the target.

        This is what a charged unit's own event-handling frame (GetEvent; CaseEvent 7; ...) reacts
        to -- typically a fear/terror test (op 0x42, FearWhenCharged) then bracing in place, per
        game_rules.md's documented default handling for this event. Without this, a charged unit's
        script never learns it is being charged at all and keeps running whatever it was already
        doing (e.g. its own independent TrackThreat-driven approach), which looked like both units
        charging each other instead of the charged one holding -- exactly the discrepancy from the
        original this was written to fix.
        """
        for attacker_id, attacker in self.battle.regiments.items():
            state = self.event_bus.unit_states.get(attacker_id)
            if state is None:
                continue
            target_id = attacker.attack_target
            if target_id is None:
                state.last_attack_target = None
                continue
            target = self.battle.regiments.get(target_id)
            if target is None:
                continue
            distance = math.hypot(target.x - attacker.x, target.y - attacker.y)
            if distance > attacker.charge_reach:
                continue  # still closing, not yet within an actual charge's reach
            if target_id != state.last_attack_target:
                self.event_bus.queue_event(target_id, Event(code=0x07, source=attacker_id), route="self")
            state.last_attack_target = target_id

    @staticmethod
    def _preempt_for_pending_event(state: UnitScriptState):
        """game_rules.md "Event dispatch is pre-emptive, not polled": before a unit's script runs any
        of its own instructions this tick, force entry into its registered interrupt script if it has
        a queued, unconsumed event -- regardless of what instruction the main script's PC currently
        sits on (even inside an indefinite idle `Wait` loop, which never itself calls GetEvent). This
        is what makes an idling unit still react to events like 0x07 "you are being charged" every
        tick, without its own code polling for them, matching real play (a charged unit braces
        immediately, not only once its current Wait happens to finish).

        Mirrors `op_CallInterruptScript`'s own mechanics (one-level gosub via `interrupt_return`), but
        triggered by the interpreter itself rather than requiring the main script to execute opcode
        0x12 -- no library or mission script anywhere in the corpus ever does, so relying on an
        explicit call left this dormant. A no-op once already inside an interrupt (`interrupt_return`
        set): the interrupt script itself is expected to `ConsumeEvent`/`ReturnInterrupt`, not to be
        re-entered on top of itself for the same or a further event within one tick.
        """
        if state.interrupt_script is None or state.interrupt_return is not None:
            return
        if not state.event_queue and not state.current_event.code:
            return
        state.interrupt_return = (state.script_id, state.pc)
        state.script_id = state.interrupt_script
        state.pc = 0

    def run(self, unit_id: str, state: UnitScriptState, tick_count: int, rng):
        """Execute one unit's script for one tick.

        Returns the state after execution. Modifies state in-place.
        """
        self._update_arrival_flag(unit_id, state)
        self._mirror_engine_flags(unit_id, state)

        if state.script_dll is None:
            state.script_dll = self.script_dll

        self._preempt_for_pending_event(state)

        # Fetch the script words from the DLL
        try:
            script_words = state.script_dll.scripts([state.script_id])[state.script_id]
        except (KeyError, Exception):
            # Script not found or DLL error: safe default is to idle
            return state

        # Main interpreter loop: execute instructions until Yield, event handling, or end of tick
        max_iterations = 10000  # prevent infinite loops during development
        iterations = 0
        self._should_yield = False

        while iterations < max_iterations:
            iterations += 1

            if state.pc >= len(script_words):
                break

            word = script_words[state.pc]
            opcode = behaviour.opcode_of(word)

            # End of script or label/data
            if opcode is None:
                if word == behaviour.END:
                    break
                # Skip labels and data words
                state.pc += 1
                continue

            # Dispatch opcode to handler
            pc_before, script_before = state.pc, state.script_id
            operand_before = (script_words[pc_before + 1]
                               if behaviour.LENGTHS[opcode] > 1 and pc_before + 1 < len(script_words)
                               else None)
            outcome = "ok"
            try:
                new_pc = self._dispatch(state, opcode, script_words, unit_id, tick_count, rng)
                state.pc = new_pc if new_pc is not None else state.pc + behaviour.LENGTHS[opcode]
            except NotImplementedError:
                outcome = "unimplemented"
                state.pc += behaviour.LENGTHS[opcode]
                self._report_gap(unit_id, script_before, opcode, "has no handler")
            except Exception as error:
                outcome = "error"
                state.pc += behaviour.LENGTHS[opcode]
                self._report_gap(unit_id, script_before, opcode, f"raised {error!r}")

            if self.logger is not None and self.logger.trace_scripts:
                self.logger.write_opcode(
                    tick_count, unit_id=unit_id, script_id=script_before, pc=pc_before,
                    opcode=opcode, opcode_name=behaviour.opcode_name(opcode), operand=operand_before,
                    outcome=outcome, state=self._state_snapshot(unit_id, state))

            # A script-switching opcode (GosubScript/GotoScript/ReturnGosub/ReturnInterrupt/...) just
            # changed state.script_id mid-tick: `script_words` still holds the *previous* script's
            # words, so the next iteration must not keep dispatching against it -- that would
            # interpret the new script's PC against the wrong bytecode entirely (latent until
            # ScriptInterpreter._preempt_for_pending_event started actually entering interrupt
            # scripts; game_rules.md "Event dispatch is pre-emptive, not polled").
            if state.script_id != script_before:
                try:
                    script_words = state.script_dll.scripts([state.script_id])[state.script_id]
                except (KeyError, Exception):
                    break

            # Yield/event handling: return control to the battle
            if self._should_yield:
                self._should_yield = False
                break

        # After main loop: apply pending script switch
        if state.pending_switch is not None:
            state.script_id = state.pending_switch
            state.pending_switch = None
            state.pc = 0

        # Clear current event at end of tick
        state.current_event = Event()

        return state

    def _report_gap(self, unit_id, script_id, opcode, reason):
        """Surface a missing/broken opcode as a battle event, once per (unit, script, opcode)."""
        key = (unit_id, script_id, opcode)
        if key in self._reported_gaps or self.battle is None:
            return
        self._reported_gaps.add(key)
        name = behaviour.opcode_name(opcode)
        self.battle.events.append(BattleEvent(
            f"{unit_id}: script {script_id} opcode {name} ({opcode:#04x}) {reason}; skipped.",
            "script_gap", unit=unit_id, script_id=script_id, opcode=opcode, opcode_name=name))

    def _dispatch(self, state, opcode, script_words, unit_id, tick_count, rng):
        """Dispatch an opcode to its handler method.

        Handler methods are named op_<OPCODE_NAME> (e.g., op_InitUnit, op_Yield).
        Returns the new PC, or None to fall through (use default increment).
        """
        op_name = behaviour.opcode_name(opcode)
        handler_name = f"op_{op_name}"

        if not hasattr(self, handler_name):
            raise NotImplementedError(f"Opcode {opcode:02X} ({op_name}) not implemented")

        handler = getattr(self, handler_name)
        operand = self._get_operand(state, opcode, script_words)
        return handler(state, operand, script_words, unit_id, tick_count, rng)

    def _get_operand(self, state, opcode, script_words):
        """Extract operand(s) for an opcode (if any).

        Most opcodes have one operand (next word), some have none, some have multiple.
        Returns the operand value or tuple of values.
        """
        if behaviour.LENGTHS[opcode] == 1:
            return None

        operand_pc = state.pc + 1
        if operand_pc < len(script_words):
            return script_words[operand_pc]
        return None

    def _nearest_enemy_id(self, regiment, n=1, side=None, max_distance=None):
        """The n-th nearest active regiment identifier to `regiment` (1 = nearest), or None if fewer
        than n candidates remain. Euclidean distance; shared by the Target*/Attack* opcode families
        (TargetNearestEnemy, AttackNearestEnemy, AttackNthNearestEnemy, ...).

        `side`, when given, restricts candidates to that exact `rules.Side` (used by
        AttackNearestFlag40Unit for the neutral side flag 0x40, notes/neutral_units.md); otherwise any
        regiment of a different side than `regiment` is a candidate, matching this opcode family's
        original two-sided "not my side" search generalised to three sides.

        This does not model "visible" (line-of-sight) any differently from a plain nearest-enemy
        search -- the engine has no visibility/fog system -- so the *Visible* opcode variants are
        implemented identically to their non-visible counterparts, a documented simplification.
        """
        if side is not None:
            candidates = (other for other in self.battle.regiments.values()
                          if other.active and other.side == side)
        else:
            candidates = (other for other in self.battle.regiments.values()
                          if other.active and other.side != regiment.side)
        if max_distance is not None:
            candidates = (other for other in candidates
                          if _octagonal_distance(regiment, other) <= max_distance)
        enemies = sorted(candidates, key=lambda other: math.hypot(other.x - regiment.x, other.y - regiment.y))
        return enemies[n - 1].identifier if len(enemies) >= n else None

    @staticmethod
    def _unit_worth(regiment):
        """game_rules.md: unit worth = size x s_pntval x 12 artillery / 8 wizard / 4 monster / 1,
        read by AI target scoring (UnitScore)."""
        multiplier = {"art": 12, "wiz": 8, "mon": 4}.get(regiment.hud_class, 1)
        return regiment.models * regiment.points * multiplier

    def _threat_score(self, regiment, other, threat_range):
        """game_rules.md's UnitScore: worth x (range - d) / round(range / 4), octagonal distance
        d = max(|dx|, |dy|) + min(|dx|, |dy|) / 2; 0 for friends, broken (routing), CantMelee, or
        beyond range. The documented x4 ("enemy targets this unit") / x32 ("also charging") score
        multipliers collapse into a single x4 here: this engine's attack_target field does not
        distinguish "targeting" from "charging" as separate states (setting it always implies a
        charge order, Battle._advance_regiments), so the two documented cases are not distinguishable.
        Hidden units are not excluded (no bit is currently read for that here) -- a known gap.
        """
        if other.side == regiment.side or not other.active or other.routing or "CantMelee" in other.psychology:
            return 0.0
        dx, dy = other.x - regiment.x, other.y - regiment.y
        d = max(abs(dx), abs(dy)) + min(abs(dx), abs(dy)) / 2.0
        if d > threat_range:
            return 0.0
        divisor = round(threat_range / 4)
        if divisor <= 0:
            return 0.0
        score = self._unit_worth(other) * (threat_range - d) / divisor
        if other.attack_target == regiment.identifier:
            score *= 4.0
        return score

    # ===== Core control-flow opcodes =====

    def op_InitUnit(self, state, operand, script_words, unit_id, tick_count, rng):
        """InitUnit N: initialization-size flag, not a script id (128 = full/combat init, 64 =
        minimal/non-combat init; notes/mission_scripts_research.md). Must NOT touch script_id or
        pc: the unit's actual running script is set once at battle construction from its own
        set:script= value (whshr.engine.Battle.from_script) and InitUnit is simply the first
        instruction inside that script, not a request to jump elsewhere. A prior version of this
        handler wrongly treated the operand as a script id and pc reset target, which silently
        hijacked every unit onto script 128/64 (garbage or an unrelated library script) the moment
        it ran -- the cause of a real regression where no scripted enemy ever moved.
        """
        return state.pc + 1

    def op_Restart(self, state, operand, script_words, unit_id, tick_count, rng):
        """Restart: jump to the restart point (set by SetRestartPoint)."""
        state.pc = state.restart_pc
        return state.pc

    def op_SetRestartPoint(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetRestartPoint: save current PC as the restart point for Restart."""
        state.restart_pc = state.pc + 1
        return state.pc + 1

    def op_GotoScript(self, state, operand, script_words, unit_id, tick_count, rng):
        """GotoScript N: switch to script N and restart."""
        if operand is not None:
            state.script_id = operand
            state.pc = 0
        return 0

    def op_SwitchScript(self, state, operand, script_words, unit_id, tick_count, rng):
        """SwitchScript N: switch to script N after this tick completes."""
        if operand is not None:
            state.pending_switch = operand
        return state.pc + 1

    def op_IfSwitchScript(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfSwitchScript N: request switching to script N at end of tick, but only if nothing
        else has already requested a switch this tick (normal priority; game_rules.md documents
        opcodes 0x0D-0x10 together as "switch script at end of tick", 0x0F called out as
        "high priority" -- the priority ordering among 0x0D/0x0E is inferred from that framing,
        not independently confirmed)."""
        if operand is not None and state.pending_switch is None:
            state.pending_switch = operand
        return state.pc + 1

    def op_IfSwitchScriptHigh(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfSwitchScriptHigh N: request switching to script N at end of tick, overriding any
        other pending switch this tick (the "high priority" variant per game_rules.md)."""
        if operand is not None:
            state.pending_switch = operand
        return state.pc + 1

    def op_IfNotSwitchScript(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfNotSwitchScript N: request switching to script N at end of tick, unless the unit is
        already running script N. Treated as normal priority (does not override an existing
        pending switch), matching IfSwitchScript -- the exact precedence versus IfSwitchScript is
        not independently confirmed in the public notes, only that all four opcodes (0x0D-0x10)
        share the same "switch at end of tick" mechanism."""
        if operand is not None and operand != state.script_id and state.pending_switch is None:
            state.pending_switch = operand
        return state.pc + 1

    def op_GosubScript(self, state, operand, script_words, unit_id, tick_count, rng):
        """GosubScript N: call script N like a subroutine, return via ReturnGosub."""
        if operand is not None:
            state.return_stack.append((state.script_id, state.pc + 1))
            state.script_id = operand
            state.pc = 0
        return 0

    def op_ReturnGosub(self, state, operand, script_words, unit_id, tick_count, rng):
        """ReturnGosub: return from gosub, restoring script and PC."""
        if state.return_stack:
            state.script_id, state.pc = state.return_stack.pop()
        return state.pc

    def op_PushPC(self, state, operand, script_words, unit_id, tick_count, rng):
        """PushPC: push current PC for Loop to jump back to."""
        state.return_stack.append((state.pc + 1,))  # tag with tuple to distinguish from gosub
        return state.pc + 1

    @staticmethod
    def _leave_loop(state):
        """A conditional loop that ends drops its `PushPC` entry. Left in place, the next unconditional
        `Loop` of an enclosing cycle jumps back into the *inner* loop instead of its own start (BF001's
        patrols: `PushPC; MoveToNode..; PushPC; ..wait..; LoopIfFalse; ..; Loop` never left the last wait)."""
        if state.return_stack and len(state.return_stack[-1]) == 1:
            state.return_stack.pop()

    def op_Loop(self, state, operand, script_words, unit_id, tick_count, rng):
        """Loop: jump back to the PC pushed by PushPC.

        Peeks the return stack, it must NOT pop it -- PushPC runs once before the loop body and
        Loop is meant to jump back every iteration (a "while true" idiom), exactly like its
        siblings LoopIfTrue/LoopIfFalse already do correctly. A prior version popped, so the entry
        was gone after the very first jump back: the second time the loop reached Loop, the stack
        was empty and it just fell through to pc + 1 instead of looping again. Confirmed as the
        real cause of NPC peasant regiments (BF003) scattering exactly twice via
        PushPC/ScatterModelsToNode/SetWait/Wait/Loop, then freezing in place for the rest of the
        battle: the second Loop silently exited the "patrol forever" cycle after one repetition.
        """
        if state.return_stack and len(state.return_stack[-1]) == 1:
            return state.return_stack[-1][0]
        return state.pc + 1

    def op_Yield(self, state, operand, script_words, unit_id, tick_count, rng):
        """Yield: return control to the battle, resume next tick."""
        self._should_yield = True
        return state.pc + 1

    # ===== Unit flag and condition opcodes =====

    def op_SetUnitFlags(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetUnitFlags N: set bits in unit_flags (+0xB4)."""
        if operand is not None:
            state.unit_flags |= operand
        return state.pc + 1

    def op_ClearUnitFlags(self, state, operand, script_words, unit_id, tick_count, rng):
        """ClearUnitFlags N: clear bits in unit_flags."""
        if operand is not None:
            state.unit_flags &= ~operand
        return state.pc + 1

    def op_TestUnitFlags(self, state, operand, script_words, unit_id, tick_count, rng):
        """TestUnitFlags N: set cond_flags to (unit_flags & N)."""
        if operand is not None:
            state.cond_flags = state.unit_flags & operand
        return state.pc + 1

    def op_WaitUntilUnitFlags(self, state, operand, script_words, unit_id, tick_count, rng):
        """WaitUntilUnitFlags N: yield (same PC) until (unit_flags & N) is set, then fall through.

        Known limitation: unit_flags is only ever set by SetUnitFlags/ClearUnitFlags in this
        interpreter today; the engine does not yet raise flags for its own conditions (e.g. a
        "routed" bit set when combat.py starts a rout). A script that waits on a flag nothing
        currently sets (see notes/interpreter_gameplay_integration.md item 4, "generate events from
        engine conditions", still Proposed) will block here indefinitely rather than silently
        proceeding -- faithful to what is and is not wired up yet, not a bug in this opcode.
        """
        if operand is not None and (state.unit_flags & operand):
            return state.pc + 1
        self._should_yield = True
        return state.pc

    def op_SetCondFlags(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetCondFlags N: set bits in the persistent condition bit word (not the If/Loop result)."""
        if operand is not None:
            state.cond_bits |= operand
        return state.pc + 1

    def op_ClearCondFlags(self, state, operand, script_words, unit_id, tick_count, rng):
        """ClearCondFlags N: clear bits in the persistent condition bit word."""
        if operand is not None:
            state.cond_bits &= ~operand
        return state.pc + 1

    def op_TestCondFlags(self, state, operand, script_words, unit_id, tick_count, rng):
        """TestCondFlags N: result = any of the persistent bits N is set."""
        if operand is not None:
            state.cond_flags = (state.cond_bits & operand) != 0
        return state.pc + 1

    # ===== Event handling opcodes =====

    def op_GetEvent(self, state, operand, script_words, unit_id, tick_count, rng):
        """GetEvent: fetch the next event from the queue.

        `run()`'s dispatch loop must not pre-pop the queue into `current_event` on its own: this
        handler's own "queue empty" branch would then blank out an event a caller (in practice,
        `_preempt_for_pending_event`) had already correctly placed there, since by the time GetEvent
        ran the queue looked empty even though current_event was already valid. An earlier version
        of the loop did exactly that and silently discarded every event dispatched via preemption.
        """
        if state.event_queue:
            state.current_event = state.event_queue.popleft()
            state.cond_flags = 1
        else:
            state.current_event = Event()
            state.cond_flags = 0  # the handler frame's `ConsumeEvent; LoopIfTrue` ends when drained
        return state.pc + 1

    def op_ConsumeEvent(self, state, operand, script_words, unit_id, tick_count, rng):
        """ConsumeEvent: clear the current event."""
        state.current_event = Event()
        return state.pc + 1

    def op_CaseEvent(self, state, operand, script_words, unit_id, tick_count, rng):
        """CaseEvent N: skip to the matching Break if current event.code != N."""
        if operand is not None and state.current_event.code != operand:
            # Scan forward to the matching Break (simplified: just skip to next Break)
            pc = state.pc + 1
            while pc < len(script_words):
                word = script_words[pc]
                opcode = behaviour.opcode_of(word)
                if opcode == 0x6B:  # Break
                    return pc + 1
                pc += behaviour.LENGTHS[opcode] if opcode is not None else 1
        return state.pc + 1

    def op_Break(self, state, operand, script_words, unit_id, tick_count, rng):
        """Break: jump to the next label word (0x0ABC) after this instruction (behaviour.py: the operand
        0x1ABC with bit 12 cleared is the word it scans forward for).

        This ends a matched `CaseEvent` body by skipping the rest of the case chain *and* the default
        handler that follows it. Falling through instead ran the default `GosubScript 153` after every
        handled event, so e.g. BF001's assassin (case 25: `SwitchScript 3`) was switched on to the
        library's rally script 163 in the same tick and never fled."""
        wanted = (operand if operand is not None else behaviour.BREAK_LABEL) & ~0x1000
        for pc in range(state.pc + 2, len(script_words)):
            if script_words[pc] == wanted:
                return pc
        return state.pc + 2

    def op_SendEventSelf(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventSelf CODE: queue an event to self."""
        if operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="self")
        return state.pc + 1

    def op_SendEventSelfIfTrue(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventSelfIfTrue CODE: queue event to self if cond_flags is true."""
        if state.cond_flags and operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="self")
        return state.pc + 1

    def op_SendEventSelfIfFalse(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventSelfIfFalse CODE: queue event to self if cond_flags is false."""
        if not state.cond_flags and operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="self")
        return state.pc + 1

    def op_SendEventToOwnSide(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventToOwnSide CODE: broadcast event to own-side units."""
        if operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="side")
        return state.pc + 1

    def op_SendEventToOwnSideIfTrue(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventToOwnSideIfTrue CODE: broadcast event to own-side if cond_flags is true."""
        if state.cond_flags and operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="side")
        return state.pc + 1

    def op_SendEventToEnemySide(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventToEnemySide CODE: broadcast event to enemy-side units."""
        if operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="enemy")
        return state.pc + 1

    # ===== Conditional branches =====

    def op_If(self, state, operand, script_words, unit_id, tick_count, rng):
        """If: skip to else/endif if cond_flags is false."""
        if not state.cond_flags:
            pc = state.pc + 1
            depth = 1
            while pc < len(script_words) and depth > 0:
                word = script_words[pc]
                opcode = behaviour.opcode_of(word)
                if opcode == 0x6E:  # Else
                    return pc + 1
                elif opcode == 0x6F:  # EndIf
                    depth -= 1
                    if depth == 0:
                        return pc + 1
                elif opcode in (0x6C, 0x6D):  # If, IfNot
                    depth += 1
                pc += behaviour.LENGTHS[opcode] if opcode is not None else 1
        return state.pc + 1

    def op_IfNot(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfNot: skip to else/endif if cond_flags is true."""
        if state.cond_flags:
            # Same skip logic as If
            pc = state.pc + 1
            depth = 1
            while pc < len(script_words) and depth > 0:
                word = script_words[pc]
                opcode = behaviour.opcode_of(word)
                if opcode == 0x6E:  # Else
                    return pc + 1
                elif opcode == 0x6F:  # EndIf
                    depth -= 1
                    if depth == 0:
                        return pc + 1
                elif opcode in (0x6C, 0x6D):  # If, IfNot
                    depth += 1
                pc += behaviour.LENGTHS[opcode] if opcode is not None else 1
        return state.pc + 1

    def op_Else(self, state, operand, script_words, unit_id, tick_count, rng):
        """Else: skip to matching EndIf."""
        pc = state.pc + 1
        depth = 1
        while pc < len(script_words) and depth > 0:
            word = script_words[pc]
            opcode = behaviour.opcode_of(word)
            if opcode == 0x6F:  # EndIf
                depth -= 1
                if depth == 0:
                    return pc + 1
            elif opcode in (0x6C, 0x6D):  # If, IfNot
                depth += 1
            pc += behaviour.LENGTHS[opcode] if opcode is not None else 1
        return pc

    def op_EndIf(self, state, operand, script_words, unit_id, tick_count, rng):
        """EndIf: end of if/else block."""
        return state.pc + 1

    # ===== Timing and wait opcodes =====

    def op_WaitForBattleStart(self, state, operand, script_words, unit_id, tick_count, rng):
        """WaitForBattleStart: hold until battle has started (tick_count > 0).

        Must yield like Wait/WaitUntilUnitFlags while blocked -- a prior version returned the same
        pc without setting _should_yield, so the dispatch loop just re-executed this instruction
        until max_iterations (10000) was hit instead of properly ending the tick. Confirmed from a
        real trace: every unit burned ~9993-9997 identical WaitForBattleStart dispatches on tick 0
        alone. Not fatal (state.pc still ends up in the right place once tick_count > 0), but wildly
        wasteful and made the opcode trace nearly unusable for actually debugging anything else.
        """
        if tick_count == 0:
            self._should_yield = True
            return state.pc  # wait (don't advance)
        return state.pc + 1  # resume

    def op_SetWait(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetWait N: set a timer for N ticks."""
        if operand is not None:
            state.wait_duration = operand
            state.wait_remaining = operand
        return state.pc + 1

    def op_TestWait(self, state, operand, script_words, unit_id, tick_count, rng):
        """TestWait: decrement wait_remaining; set cond_flags if still waiting."""
        if state.wait_remaining > 0:
            state.wait_remaining -= 1.0
            state.cond_flags = 1 if state.wait_remaining > 0 else 0
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_Wait(self, state, operand, script_words, unit_id, tick_count, rng):
        """Wait N: hold for N ticks (yield until timer expires)."""
        if operand is not None:
            if state.wait_remaining == 0:
                state.wait_remaining = operand
        if state.wait_remaining > 0:
            state.wait_remaining -= 1.0
            self._should_yield = True  # yield to let other units run
            return state.pc
        return state.pc + 1

    def op_LoopIfTrue(self, state, operand, script_words, unit_id, tick_count, rng):
        """LoopIfTrue: jump back to pushed PC if cond_flags is true."""
        if state.cond_flags and state.return_stack and len(state.return_stack[-1]) == 1:
            return state.return_stack[-1][0]
        self._leave_loop(state)
        return state.pc + 1

    def op_LoopIfFalse(self, state, operand, script_words, unit_id, tick_count, rng):
        """LoopIfFalse: jump back to pushed PC if cond_flags is false."""
        if not state.cond_flags and state.return_stack and len(state.return_stack[-1]) == 1:
            return state.return_stack[-1][0]
        self._leave_loop(state)
        return state.pc + 1

    # ===== Targeting and threat opcodes =====

    def op_FindTarget(self, state, operand, script_words, unit_id, tick_count, rng):
        """FindTarget: find the nearest valid enemy target."""
        # TODO: implement proper targeting (check visibility, range, etc.)
        # Simplified: set cond_flags to indicate target found
        state.cond_flags = 1  # assume target found
        return state.pc + 1

    def op_FindTargetNear(self, state, operand, script_words, unit_id, tick_count, rng):
        """FindTargetNear: find nearest enemy within threat range."""
        state.cond_flags = 1  # assume target found
        return state.pc + 1

    def op_FindNewTargetNear(self, state, operand, script_words, unit_id, tick_count, rng):
        """FindNewTargetNear: find a new target, ignoring current one."""
        state.cond_flags = 1  # assume target found
        return state.pc + 1

    def op_TargetNearestEnemy(self, state, operand, script_words, unit_id, tick_count, rng):
        """TargetNearestEnemy: set current target to nearest enemy."""
        regiment = self.battle.regiments.get(unit_id)
        target_id = self._nearest_enemy_id(regiment) if regiment else None
        if target_id:
            state.current_target = (target_id, 0)
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_AttackNearestEnemy(self, state, operand, script_words, unit_id, tick_count, rng):
        """AttackNearestEnemy: find the nearest enemy and attack it (game_rules.md opcode 0xB0)."""
        return self._attack_nearest(state, unit_id, n=1)

    def op_AttackNearestVisibleEnemy(self, state, operand, script_words, unit_id, tick_count, rng):
        """AttackNearestVisibleEnemy: as AttackNearestEnemy (no visibility model, see
        _nearest_enemy_id)."""
        return self._attack_nearest(state, unit_id, n=1)

    def op_AttackNearestFlag40Unit(self, state, operand, script_words, unit_id, tick_count, rng):
        """AttackNearestFlag40Unit: attack the nearest unit carrying side flag 0x40 (neutral;
        notes/neutral_units.md's 2-bit side code, `rules.Side.NEUTRAL`)."""
        return self._attack_nearest(state, unit_id, n=1, side=Side.NEUTRAL)

    def op_AttackNthNearestEnemy(self, state, operand, script_words, unit_id, tick_count, rng):
        """AttackNthNearestEnemy N: find the N-th nearest enemy (1-based) and attack it."""
        return self._attack_nearest(state, unit_id, n=operand or 1)

    def _attack_nearest(self, state, unit_id, n, side=None):
        regiment = self.battle.regiments.get(unit_id)
        search_range = state.threat_range if state.threat_range > 0 else DEFAULT_ATTACK_SEARCH_RANGE
        target_id = (self._nearest_enemy_id(regiment, n, side=side, max_distance=search_range)
                     if regiment else None)
        if target_id:
            state.current_target = (target_id, 0)
            if not regiment.anchored:
                regiment.attack_target = target_id
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_TargetValid(self, state, operand, script_words, unit_id, tick_count, rng):
        """TargetValid: test if current target is still valid."""
        # Simplified: assume target is valid
        state.cond_flags = 1 if state.current_target else 0
        return state.pc + 1

    def op_KeepThreat(self, state, operand, script_words, unit_id, tick_count, rng):
        """KeepThreat: keep current threat (don't search for new one)."""
        return state.pc + 1

    def op_IfThreatOutweighsWorth(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfThreatOutweighsWorth: test whether the best-scoring enemy within threat_range outweighs
        this unit's own worth -- the actual decision gate behind library behaviour 15, TrackThreat
        (game_rules.md: "keep the best threat and attack it when its score exceeds the unit's
        worth"). Confirmed used by a real BF003 playthrough's Goblin Wolfriders script, in the exact
        Query 1/IfThreatOutweighsWorth/SendEventSelfIfTrue/AttackNearestFlag40Unit sequence
        game_rules.md documents behaviour 15 as using.

        Requires SetThreatRange to have set state.threat_range first; with no range set (0), or no
        regiment found for this unit, conservatively sets cond_flags to 0 (no threat) rather than
        guessing.
        """
        regiment = self.battle.regiments.get(unit_id)
        if not regiment or state.threat_range <= 0:
            state.cond_flags = 0
            return state.pc + 1
        best_score = max(
            (self._threat_score(regiment, other, state.threat_range)
             for other in self.battle.regiments.values() if other is not regiment),
            default=0.0)
        state.cond_flags = 1 if best_score > self._unit_worth(regiment) else 0
        return state.pc + 1

    def op_TargetGone(self, state, operand, script_words, unit_id, tick_count, rng):
        """TargetGone: test if target is no longer visible/alive."""
        # For now, assume target still exists
        state.cond_flags = 0
        return state.pc + 1

    def op_InRange(self, state, operand, script_words, unit_id, tick_count, rng):
        """InRange: test if current target is in weapon range."""
        # TODO: check distance to current target against weapon range
        state.cond_flags = 0  # assume out of range for now
        return state.pc + 1

    def op_IfTargetInChargeReach(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfTargetInChargeReach: test if target is close enough to charge."""
        # TODO: check distance to target (within charge reach)
        state.cond_flags = 0
        return state.pc + 1

    def op_TakeEventTarget(self, state, operand, script_words, unit_id, tick_count, rng):
        """TakeEventTarget: use the source of the current event as target."""
        if state.current_event.source:
            state.current_target = (state.current_event.source, 0)
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    # ===== Placeholder opcodes (stubs for future implementation) =====
    # These are high-priority opcodes needed by missions but not yet integrated with the battle engine.
    # Each logs a placeholder message and continues, allowing partial mission execution.

    def op_MoveToNode(self, state, operand, script_words, unit_id, tick_count, rng):
        """MoveToNode N: order an ordinary move to waypoint node N's coordinates.

        Uses Battle.nodes (the battle's own [NODES] table, whshr.script.load_battle) to resolve N
        to a real (x, y); a no-op if the battle has no such node (synthetic/nodeless battles, or an
        id the script never defines). Does not touch attack_target -- a later AttackNearestEnemy
        etc. still takes priority every tick (Battle._advance_regiments checks attack_target first),
        matching how the rest of this interpreter leaves targeting decisions to their own opcodes.

        Clears ARRIVED_FLAG and arms pending_arrival, so _update_arrival_flag can set it again once
        the regiment actually reaches this new target (see ScriptInterpreter.run).
        """
        if operand is not None:
            state.current_node = operand
            regiment = self.battle.regiments.get(unit_id)
            coords = self.battle.nodes.get(operand)
            if regiment and coords and not regiment.anchored:
                regiment.target_x, regiment.target_y = coords
                state.unit_flags &= ~ARRIVED_FLAG
                state.pending_arrival = True
        return state.pc + 1

    def op_FaceNode(self, state, operand, script_words, unit_id, tick_count, rng):
        """FaceNode N: turn to face waypoint node N (instant turn, not a movement order).

        Reuses Battle._turn_to so facing changes pivot the same way every other turn in the engine
        does (game_rules.md: "a turn always moves the unit position to keep the pivot still").
        """
        if operand is not None:
            regiment = self.battle.regiments.get(unit_id)
            coords = self.battle.nodes.get(operand)
            if regiment and coords and (coords[0] != regiment.x or coords[1] != regiment.y):
                dx, dy = coords[0] - regiment.x, coords[1] - regiment.y
                direction = round(math.atan2(dx, dy) * 512 / math.tau) % 512
                self.battle._turn_to(regiment, direction)
        return state.pc + 1

    def op_TeleportToNode(self, state, operand, script_words, unit_id, tick_count, rng):
        """TeleportToNode N: instantly move to waypoint node N (no travel time).

        Completes immediately, so ARRIVED_FLAG is set right away (no pending_arrival needed).
        """
        if operand is not None:
            state.current_node = operand
            regiment = self.battle.regiments.get(unit_id)
            coords = self.battle.nodes.get(operand)
            if regiment and coords:
                regiment.x, regiment.y = coords
                regiment.target_x = regiment.target_y = None
                state.unit_flags |= ARRIVED_FLAG
                state.pending_arrival = False
        return state.pc + 1

    def op_PlaceAtNode(self, state, operand, script_words, unit_id, tick_count, rng):
        """PlaceAtNode N: place unit at node N in formation.

        Same positional effect as TeleportToNode -- "in formation" (re-forming ranks in place) is
        not separately modeled; the regiment's own formation slots are always recomputed from its
        current models/ranks/direction (Regiment.model_positions), so there is nothing extra to do.
        Completes immediately, so ARRIVED_FLAG is set right away.
        """
        if operand is not None:
            state.current_node = operand
            regiment = self.battle.regiments.get(unit_id)
            coords = self.battle.nodes.get(operand)
            if regiment and coords and not regiment.anchored:
                regiment.x, regiment.y = coords
                state.unit_flags |= ARRIVED_FLAG
                state.pending_arrival = False
                regiment.target_x = regiment.target_y = None
        return state.pc + 1

    def op_ScatterModelsToNode(self, state, operand, script_words, unit_id, tick_count, rng):
        """ScatterModelsToNode N: wander to a randomized point near waypoint node N.

        This is the actual opcode NPC "patrol" scripts use (confirmed from a real BF003 trace: the
        peasant regiments loop SetWait 20/Wait/ScatterModelsToNode every ~20 ticks) -- not
        MoveToNode, which their scripts never call at all.

        Real per-model scatter (spreading individual models out around the node, rather than moving
        the whole regiment) is not modeled; this reuses the regiment's ordinary move order with a
        small random jitter around the node's point instead, which is what produces the wandering
        appearance when called repeatedly. SCATTER_RADIUS is a documented placeholder (nodes do
        carry their own `radius` field in the parsed .BTS data, but Battle.nodes only keeps x/y
        today, and whether that radius is even the right value for this opcode isn't confirmed).
        Deterministic: draws from Battle.rng like every other random decision in the engine.
        """
        if operand is not None:
            state.current_node = operand
            regiment = self.battle.regiments.get(unit_id)
            coords = self.battle.nodes.get(operand)
            if regiment and coords and not regiment.anchored:
                regiment.target_x = coords[0] + self.battle.rng.uniform(-SCATTER_RADIUS, SCATTER_RADIUS)
                regiment.target_y = coords[1] + self.battle.rng.uniform(-SCATTER_RADIUS, SCATTER_RADIUS)
                state.unit_flags &= ~ARRIVED_FLAG
                state.pending_arrival = True
        return state.pc + 1

    def op_ChargeTarget(self, state, operand, script_words, unit_id, tick_count, rng):
        """ChargeTarget: issue charge order to the current target.

        Refused while braced (game_rules.md "Braced": charge orders are ignored for a scripted unit
        exactly as for a player's own click), matching Battle.order_attack's player-side guard.
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment and (regiment.braced or regiment.anchored):
            return state.pc + 1
        if regiment and state.current_target:
            target_id = state.current_target[0]
            if target_id in self.battle.regiments:
                regiment.attack_target = target_id
                # Battle.tick() handles the actual charging movement
        return state.pc + 1

    def op_FireAtTarget(self, state, operand, script_words, unit_id, tick_count, rng):
        """FireAtTarget: mark the current target for shooting.

        Must NOT set regiment.attack_target: that field means "melee charge target" to both
        Battle._advance_regiments (charges the unit into melee range of it) and
        combat.resolve_shooting (which explicitly skips any unit with attack_target set, since it
        already does its own independent nearest-in-arc-and-range targeting). A prior version set
        it here too, which silently made every scripted FireAtTarget order charge the shooter into
        melee instead of holding position and shooting -- and resolve_shooting would then skip the
        unit regardless, on top of that. There is nothing else to do here in this simplified engine:
        the actual target for the shot is combat.resolve_shooting's own search, not script-directed.
        """
        return state.pc + 1

    def op_KillAllModels(self, state, operand, script_words, unit_id, tick_count, rng):
        """KillAllModels: instantly kill all models in this unit.

        Used in BF001 for conditional tutorial difficulty scaling (flag 512 check).
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            # Instant unit destruction
            regiment.models = 0
            regiment.positions = []
            regiment.melee_models = []
        return state.pc + 1

    def op_AttackTagged(self, state, operand, script_words, unit_id, tick_count, rng):
        """AttackTagged TAG: attack the unit marked with TAG.

        Example: BF001 Unit 2 uses AttackTagged 0xabc0 to hunt the tagged cargo unit.
        """
        if operand is not None:
            # Look up which unit has this tag (simplified: assume only one tagged unit)
            if hasattr(self.battle, '_unit_tags') and operand in self.battle._unit_tags:
                target_id = self.battle._unit_tags[operand]
                state.current_target = (target_id, 0)
                regiment = self.battle.regiments.get(unit_id)
                if regiment and not regiment.anchored:
                    regiment.attack_target = target_id
                state.cond_flags = 1
            else:
                state.cond_flags = 0
        return state.pc + 1

    def op_SetTag(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetTag TAG: mark this unit with a tag.

        Tags are used to identify specific units for special behavior
        (e.g., cargo in escort missions, objectives in special scenarios).
        """
        if operand is not None:
            if not hasattr(self.battle, '_unit_tags'):
                self.battle._unit_tags = {}
            self.battle._unit_tags[operand] = unit_id
        return state.pc + 1

    def op_SetParentByTag(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetParentByTag TAG: find the unit registered with TAG (SetTag) and set it as this unit's
        parent (state.parent_id), for FollowParent/SendEventToParent.

        Confirmed used by every BF003 regiment traced this session (Stickers, Wolfriders, all three
        peasant regiments each SetParentByTag another unit early in their scripts) -- exact
        real-world meaning of the parent relationship for those specific missions is not otherwise
        documented, but recording it is unambiguous and this is what FollowParent already expects.
        """
        if operand is not None:
            tags = getattr(self.battle, '_unit_tags', {})
            state.parent_id = tags.get(operand)
        return state.pc + 1

    def op_SnapModelsToFormation(self, state, operand, script_words, unit_id, tick_count, rng):
        """SnapModelsToFormation: re-form scattered models back into tight formation.

        A documented no-op here, same reasoning as PlaceAtNode: this engine has no separate
        "scattered per-model position" state to snap back from -- Regiment.model_positions() always
        recomputes every model's slot from the regiment's current anchor/models/ranks/direction, so
        formation is implicitly always current. Confirmed used once, right after ScatterModelsToNode,
        in every BF003 peasant regiment's script.
        """
        return state.pc + 1

    def op_SetBehaviour(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetBehaviour N: record which library AI behavior (e.g. 15 = TrackThreat) governs this
        unit. Does NOT invoke it.

        A prior version of this handler called LibraryBehaviors.track_threat() immediately and
        unconditionally the moment this opcode ran -- which, since SetBehaviour appears near the
        very start of a unit's script (before any SetWait/Wait/MoveToNode that should gate its
        first action), set regiment.attack_target on tick 0 regardless of what the rest of the
        script does. Battle._advance_regiments checks attack_target before an ordinary move order,
        so this silently overrode every later movement/wait instruction. Confirmed against a real
        BF003 playthrough: the reinforcement Goblin Wolfriders regiment attacked from the first
        tick instead of respecting its own SetWait 60 gate.

        There is no confirmed public documentation of exactly when/how often a declared library
        behavior is meant to run relative to a unit's own script instructions, so this is
        deliberately left as a no-op recording rather than a guessed re-implementation. A script's
        own AttackNearestEnemy/AttackNearestVisibleEnemy/FindTarget* calls (now implemented) are
        what actually drive targeting; see notes/interpreter_gameplay_integration.md.
        """
        state.behaviour_id = operand
        return state.pc + 1


    def op_React(self, state, operand, script_words, unit_id, tick_count, rng):
        """React N: display a battle message/voice with leader portrait (game_rules.md §React N).

        The actual text varies by s_race & 7; this table covers the code-level semantics only.
        PROVISIONAL: race-specific variants (e.g. "WAARRGGH!" for code 2) are not yet mapped.
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment is not None:
            msg = _REACT_MESSAGES.get(operand, f"React {operand}")
            self.battle.events.append(BattleEvent(
                f"{regiment.name}: {msg}", "react",
                regiment=unit_id, code=operand, sender=regiment.name, message=msg))
        return state.pc + 1

    def op_RemoveFromBattle(self, state, operand, script_words, unit_id, tick_count, rng):
        """RemoveFromBattle: remove unit from battle without death."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            regiment.fled = True  # mark as removed from play
        return state.pc + 1

    def op_ExcludeFromArmy(self, state, operand, script_words, unit_id, tick_count, rng):
        """ExcludeFromArmy: exclude unit from army roster (remove without death)."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            regiment.fled = True  # same effect as RemoveFromBattle
        return state.pc + 1

    def op_SetThreatRange(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetThreatRange N: set threat detection range (used by TrackThreat).

        Range in world units. Used to limit which enemies a unit considers as threats.
        Example: BF001 Unit 1 (dormant) has low threat range (40) to indicate minimal engagement.
        """
        if operand is not None:
            state.threat_range = operand
        return state.pc + 1

    def op_SetInterruptScript(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetInterruptScript N: set interrupt handler script.

        Called when the unit receives an event (e.g., being attacked, enemy spotted).
        Saves current position and switches to interrupt script.
        """
        if operand is not None:
            state.interrupt_script = operand
        return state.pc + 1

    def op_CallInterruptScript(self, state, operand, script_words, unit_id, tick_count, rng):
        """CallInterruptScript: jump into the script registered by SetInterruptScript -- a one-level
        gosub reserved for event-driven reactions (e.g. bracing when charged, game_rules.md event
        0x07 "you are being charged"). Saves (script_id, pc + 1) to interrupt_return so
        ReturnInterrupt can resume here; a no-op fall-through if nothing was ever registered.
        """
        if state.interrupt_script is not None:
            state.interrupt_return = (state.script_id, state.pc + 1)
            state.script_id = state.interrupt_script
            return 0
        return state.pc + 1

    def op_ReturnInterrupt(self, state, operand, script_words, unit_id, tick_count, rng):
        """ReturnInterrupt: end of an event handler -- return to the script CallInterruptScript
        jumped from, or apply a pending switch immediately instead if the interrupt handler itself
        requested one (game_rules.md: opcode 0x14 "end of an event handler: return to the
        interrupted script or apply a pending switch"). Falls through if neither applies (e.g. this
        opcode reached without ever going through CallInterruptScript).
        """
        if state.pending_switch is not None:
            state.script_id = state.pending_switch
            state.pending_switch = None
            state.interrupt_return = None
            return 0
        if state.interrupt_return is not None:
            script_id, pc = state.interrupt_return
            state.interrupt_return = None
            state.script_id = script_id
            return pc
        return state.pc + 1

    def op_HaltAndReform(self, state, operand, script_words, unit_id, tick_count, rng):
        """HaltAndReform: stop movement and reform in place."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            regiment.target_x = None
            regiment.target_y = None
            regiment.attack_target = None
        return state.pc + 1

    def op_ReformBlock(self, state, operand, script_words, unit_id, tick_count, rng):
        """ReformBlock: reform unit into a tight block formation."""
        # TODO: adjust regiment.ranks based on available models
        return state.pc + 1

    def op_DropTarget(self, state, operand, script_words, unit_id, tick_count, rng):
        """DropTarget: forget the current attack target (game_rules.md, scripted target and flight
        opcodes). Only a unit that is not broken and has a target acts: it clears the target and its
        braced state, and the condition is true; otherwise nothing changes and the condition is false.
        It never leaves a melee, changes orders or sends events."""
        regiment = self.battle.regiments.get(unit_id) if self.battle is not None else None
        has_target = regiment is not None and (regiment.attack_target is not None or state.current_target)
        if regiment is None or regiment.routing or not has_target:
            state.cond_flags = 0
            return state.pc + 1
        regiment.attack_target = None
        state.current_target = None
        regiment.braced = False
        regiment.braced_target = None
        state.cond_flags = 1
        return state.pc + 1

    def op_FleeAhead(self, state, operand, script_words, unit_id, tick_count, rng):
        """FleeAhead: start a rout along the unit's current facing (game_rules.md, scripted target and
        flight opcodes). It is the rout itself, so `CantBreak` does not stop it; only an anchored war
        machine refuses. The target is always cleared; the condition is true when a rout started."""
        regiment = self.battle.regiments.get(unit_id) if self.battle is not None else None
        state.cond_flags = 0
        if regiment is None:
            return state.pc + 1
        regiment.attack_target = None
        state.current_target = None
        if regiment.anchored or regiment.routing or not regiment.active:
            return state.pc + 1
        from . import combat
        angle = regiment.direction * math.tau / 512
        combat._start_rout(regiment, self.battle, flee_point=(
            regiment.x + math.sin(angle) * 1e4, regiment.y + math.cos(angle) * 1e4))
        state.cond_flags = 1
        return state.pc + 1

    def op_StoreEventInfo(self, state, operand, script_words, unit_id, tick_count, rng):
        """StoreEventInfo: remember the sender and code of the event being handled, overwriting any
        earlier one (game_rules.md, scripted target and flight opcodes)."""
        state.remembered_event = (state.current_event.source, state.current_event.code)
        return state.pc + 1

    def op_FaceModelsToTarget(self, state, operand, script_words, unit_id, tick_count, rng):
        """FaceModelsToTarget: turn the individual models, not the regiment, to face the target
        (game_rules.md, scripted target and flight opcodes). A model still walking is left alone and
        counts as "not finished"; a model at rest facing elsewhere gets its heading set instantly and
        also counts; the condition is true while any did. No target: nothing happens, condition false."""
        regiment = self.battle.regiments.get(unit_id) if self.battle is not None else None
        target = self.battle.regiments.get(regiment.attack_target) if regiment and regiment.attack_target else None
        state.cond_flags = 0
        if regiment is None or target is None or regiment.anchored:
            return state.pc + 1
        dx, dy = target.x - regiment.x, target.y - regiment.y
        distance = math.hypot(dx, dy)
        if distance < 1e-6:
            return state.pc + 1
        heading = (dx / distance, dy / distance)
        regiment.model_positions()  # seeds the per-model state
        for model in regiment.melee_models:
            if not model.at_rest:
                state.cond_flags = 1
            elif (model.heading_x, model.heading_y) != heading:
                model.heading_x, model.heading_y = heading
                state.cond_flags = 1
        return state.pc + 1

    def op_RunAway(self, state, operand, script_words, unit_id, tick_count, rng):
        """RunAway: cause unit to flee the battlefield.

        Similar to rout/panic, unit tries to leave the field.
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment and not regiment.routing and "CantBreak" not in regiment.psychology:
            # Trigger routing via combat module (_start_rout takes (regiment, battle), not the reverse)
            from . import combat
            combat._start_rout(regiment, self.battle)
        return state.pc + 1

    def op_RoutAllowed(self, state, operand, script_words, unit_id, tick_count, rng):
        """RoutAllowed: test whether this unit may currently rout (game_rules.md opcode 0xC8).

        A read-only check: true unless the regiment already routed/fled or carries CantBreak
        (the same guard whshr.combat._break_test applies before calling _start_rout).
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment and regiment.active and not regiment.routing and "CantBreak" not in regiment.psychology:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_FleeFromTarget(self, state, operand, script_words, unit_id, tick_count, rng):
        """FleeFromTarget: flee from the current target/threat.

        Starts a rout via the same combat._start_rout path as RunAway/RoutAllowed if the unit
        isn't already routing and is allowed to; once routing, Battle._advance_regiments already
        drives the per-tick flee movement generically for any routing regiment, so this becomes a
        no-op on later ticks rather than needing its own movement logic here.
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment and not regiment.routing and "CantBreak" not in regiment.psychology:
            from . import combat
            combat._start_rout(regiment, self.battle)
        return state.pc + 1

    def op_FearWhenCharged(self, state, operand, script_words, unit_id, tick_count, rng):
        """FearWhenCharged: fear/terror test on being charged (game_rules.md opcode 0x42, run on
        event 0x07 "you are being charged"). Sets cond_flags to 1 when the test fails (the unit
        should flee) -- matching event 0x07's documented handling ("fear/terror test op 0x42, then
        brace"), i.e. a script normally reacts to cond_flags=1 here by routing (e.g. via RunAway).

        Simplified relative to game_rules.md's full rule (no Dread Banner, no "already resisted
        this enemy" caching of psy bit 14 -- that state doesn't exist in this engine yet): terror
        applies whenever the charger has CauseTerror and this unit lacks Frenzy/PsyImmune; fear
        applies whenever the charger has CauseFear and this unit lacks CantBreak/Frenzy/PsyImmune,
        with a Leadership test (whshr.combat.leadership_test) deciding the outcome.
        """
        regiment = self.battle.regiments.get(unit_id)
        source_id = state.current_event.source
        charger = self.battle.regiments.get(source_id) if source_id else None
        if not regiment or not charger:
            state.cond_flags = 0
            return state.pc + 1
        immune = regiment.psychology & {"Frenzy", "PsyImmune"}
        if "CauseTerror" in charger.psychology and not immune:
            state.cond_flags = 1
        elif "CauseFear" in charger.psychology and not immune and "CantBreak" not in regiment.psychology:
            from . import combat
            state.cond_flags = 0 if combat.leadership_test(regiment.leadership, rng) else 1
        else:
            state.cond_flags = 0
        if state.cond_flags == 0:
            # game_rules.md "Braced" (flag 0x100000): a passed fear/terror test halts the unit
            # facing its charger and suppresses move/attack/turn/rank/charge/fire orders -- for
            # the player exactly like for a script -- until combat.refresh_braced_state or
            # Battle.order_halt clears it.
            regiment.target_x = regiment.target_y = None
            regiment.attack_target = None
            regiment.braced = True
            regiment.braced_target = source_id
            if (charger.x != regiment.x or charger.y != regiment.y):
                dx, dy = charger.x - regiment.x, charger.y - regiment.y
                direction = round(math.atan2(dx, dy) * 512 / math.tau) % 512
                self.battle._turn_to(regiment, direction)
        return state.pc + 1

    def op_ResetStack(self, state, operand, script_words, unit_id, tick_count, rng):
        """ResetStack: clear the return stack."""
        state.return_stack = []
        return state.pc + 1

    def op_ExecuteOrder(self, state, operand, script_words, unit_id, tick_count, rng):
        """ExecuteOrder: apply pending player order (if any)."""
        # TODO: check if player has issued an order and apply it
        # Player orders override script commands
        return state.pc + 1

    def op_RestartAfterOrder(self, state, operand, script_words, unit_id, tick_count, rng):
        """RestartAfterOrder: restart script after player order completes."""
        # ExecuteOrder applies a player order, then this restarts at the restart point
        state.pc = state.restart_pc
        return state.pc

    def op_Query(self, state, operand, script_words, unit_id, tick_count, rng):
        """Query N: ask the AI routine (cases 11-14 for threat detection)."""
        # Simplified: Query is used by FindTarget* opcodes to ask "is there a valid target?"
        # For now, set cond_flags based on operand (TODO: implement real threat scoring)
        if operand is not None:
            # Cases 11-14: threat detection queries
            # Set cond_flags to indicate whether a threat exists (simplified: always false for now)
            state.cond_flags = 0
        return state.pc + 1

    def op_IfObjective(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfObjective N: test if objective letter N is defined in the battle."""
        # TODO: check battle's objective letters (from .BTS file)
        # For now, assume objectives A-F always exist (simplified)
        if operand is not None and operand < 6:  # A=0, B=1, ..., F=5
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_IfClass(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfClass N: test if this unit's class matches N."""
        # TODO: check regiment's class from HUD_CLASS_BY_RACE_TYPE
        # For now, simplified: set cond_flags based on class
        state.cond_flags = 1  # assume matches for now
        return state.pc + 1

    def op_IfTag(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfTag TAG: test if this unit has the specified tag."""
        # TODO: implement unit tagging system
        state.cond_flags = 0  # no tags implemented yet
        return state.pc + 1

    def op_IfTagExists(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfTagExists TAG: test if any unit has this tag."""
        # TODO: implement unit tagging system
        state.cond_flags = 0  # no tags implemented yet
        return state.pc + 1

    def op_IfEventSource(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfEventSource: test if current event came from a specific source.

        Known limitation: the operand is a numeric source id from the bytecode, but
        Event.source in this engine holds a regiment identifier string (see the fix in
        SendEventSelf/etc.) -- there is no numeric-id-to-regiment mapping in this engine, so this
        comparison never matches today. Left as a documented gap rather than a guessed mapping.
        """
        if operand is not None and state.current_event.source == operand:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_IfGameMode(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfGameMode N: test current game mode (1=deployment, 2=real time)."""
        # TODO: check battle's game mode
        # For now, assume real-time mode (2)
        if operand is not None and operand == 2:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_IfBattleState(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfBattleState N: test current battle state."""
        # TODO: track battle state (0=initial, 4=in progress, 5=gate reached, etc.)
        # For now, assume state 4 (in progress)
        if operand is not None and operand == 4:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_SetBattleState(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetBattleState N: set current battle state."""
        # TODO: update global battle state
        return state.pc + 1

    def op_EnemyRouted(self, state, operand, script_words, unit_id, tick_count, rng):
        """EnemyRouted: test if any enemy unit is routing/fleeing."""
        battle = self.battle
        regiment = battle.regiments.get(unit_id)
        if regiment:
            for other_id, other in battle.regiments.items():
                if other.side != regiment.side and other.active and other.routing:
                    state.cond_flags = 1
                    return state.pc + 1
        state.cond_flags = 0
        return state.pc + 1

    def op_EnemyRoutedStatic(self, state, operand, script_words, unit_id, tick_count, rng):
        """EnemyRoutedStatic: test if a specific enemy is routing (static check)."""
        return state.pc + 1

    def op_IfBreak(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfBreak: test if this unit is broken/fleeing."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment and regiment.routing:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_IfRouted(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfRouted: test if this unit is routed/fleeing."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment and regiment.routing:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_StartPursuit(self, state, operand, script_words, unit_id, tick_count, rng):
        """StartPursuit: chase down a fleeing unit."""
        if state.current_target:
            regiment = self.battle.regiments.get(unit_id)
            if regiment and not regiment.anchored:
                regiment.attack_target = state.current_target[0]
        return state.pc + 1

    def op_ReadyToFire(self, state, operand, script_words, unit_id, tick_count, rng):
        """ReadyToFire: test if unit can shoot (not reloading)."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment and regiment.missile_range and regiment.reload_ticks <= 0:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_StampReload(self, state, operand, script_words, unit_id, tick_count, rng):
        """StampReload: manually reset reload counter (shortcut for rapid fire)."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            regiment.reload_ticks = 0
        return state.pc + 1

    def op_SpawnUnit(self, state, operand, script_words, unit_id, tick_count, rng):
        """SpawnUnit N: create Night Goblin Fanatics at current position.

        Only used in BF004_5, BF015, BF034, BF038 (fanatic battles).
        Fanatics are created with special behavior (0xD3 opcode).
        """
        # TODO: implement fanatic spawning
        # Requires creating new models at a position, which is complex
        return state.pc + 1

    def op_FollowParent(self, state, operand, script_words, unit_id, tick_count, rng):
        """FollowParent: follow a parent unit (for child units in formation)."""
        # TODO: implement parent unit tracking
        return state.pc + 1

    def op_SetClass(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetClass N: change unit class (0=Monster, 1=Infantry, 3=Archer, etc.)."""
        # TODO: modify regiment.hud_class based on unit type
        if operand is not None:
            from .engine import HUD_CLASS_BY_RACE_TYPE
            # Map class number to HUD class name
            class_names = {0: "mon", 1: "inf", 3: "arch", 15: "art", 19: "wiz"}
            regiment = self.battle.regiments.get(unit_id)
            if regiment and operand in class_names:
                regiment.hud_class = class_names[operand]
        return state.pc + 1

    def op_IfMachineDestroyed(self, state, operand, script_words, unit_id, tick_count, rng):
        """IfMachineDestroyed: test if an artillery machine is destroyed."""
        # TODO: check if specific war machine model is destroyed
        state.cond_flags = 0  # simplified: never destroyed
        return state.pc + 1

    # For any other opcode not explicitly handled, the dispatcher will raise NotImplementedError,
    # which is caught and logged by the run() method, allowing partial mission execution.
