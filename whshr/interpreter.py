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
import random
from collections import deque
from typing import TYPE_CHECKING, Any

from . import behaviour, nodes, visibility
from .battle_events import BattleEvent
from .battle_log import BattleLogger
from .rules import Side, side_of_code

if TYPE_CHECKING:
    from .engine import Battle, Regiment

Words = list[int]  # one behaviour script's instruction words
Target = tuple[str, int]  # (regiment identifier, unit id)

# Hypothesis, not a confirmed public fact (see op_MoveToNode/_update_arrival_flag): unit_flags bit
# 0x10 signals "the unit's last ordinary move order has arrived", matching the MoveToNode N;
# WaitUntilUnitFlags 16 idiom seen throughout real mission scripts. No other candidate meaning for
# that specific bit, immediately after a MoveToNode call, was found in the public notes.
ARRIVED_FLAG = 0x10

WAIT_OPCODE = 0x1C  # Wait: blocking ticks are not traced (see ScriptInterpreter.run)
# game_rules.md, unit flags: 0x200 is "in melee" -- Otto Hiln's script tests it (`TestUnitFlags 512`) and
# the wizard casting scripts refuse to cast while it is set. Mirrored from `Regiment.in_melee`.
IN_MELEE_FLAG = 0x200
REFORMING_FLAG = 0x8  # script operand of WaitWhileUnitFlags 8: the models are re-forming
BROKEN_FLAG = 0x2000  # script operand of TestUnitFlags 0x2000/0xa000: the unit is broken (routing)
INDEPENDENT_FLAG = 0x8000000  # script operand of TestUnitFlags 0x8000000: the player made the unit independent
# Script-owned busy states (SetUnitFlags2 operands of the library shooting and casting scripts), which
# ReacquireEventSource respects (notes/threat_events_nodes.md, part B 1).
CASTING_SEQUENCE_FLAG2 = 2
SHOOTING_SEQUENCE_FLAG2 = 4


REPEAT_ENTRY = 0  # tag of a RepeatStart entry on the script stack: (body start, count, tag)
COND_TRUE = 4  # the bit of the condition word that holds the true/false result


def _trunc_sin(angle: int) -> int:
    """256 x sin of an angle in 1/512 turn, truncated towards zero (the game's sine table)."""
    return int(256 * math.sin(math.tau * angle / 512))


def _trunc_cos(angle: int) -> int:
    return int(256 * math.cos(math.tau * angle / 512))


def _signed_word(value: int) -> int:
    """Interpret a 16-bit script word as a signed number."""
    return value - 0x10000 if value & 0x8000 else value


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

    Fields follow the per-unit script state described in game_rules.md (script id, PC, flags, ...).
    Each unit has exactly one live state, which the interpreter updates each tick.
    """
    # Script execution
    script_id: int = 100  # current script (0..37 for mission, 100..170 for library)
    pc: int = 0  # program counter (word index into the script)
    restart_pc: int = 0  # saved by InitUnit/SetRestartPoint, restored by Restart
    return_stack: list[tuple[int, ...]] = field(default_factory=list[tuple[int, ...]])  # (script_id, pc) pairs for gosub/return

    # Event handling
    current_event: Event = field(default_factory=Event)  # the event being processed this tick
    event_queue: deque[Event] = field(default_factory=lambda: deque[Event](maxlen=128))  # pending events
    interrupt_script: int | None = None  # set by SetInterruptScript; called by CallInterruptScript
    pending_switch: int | None = None  # set by SwitchScript; applied after event handling

    # Unit state (flags set by SetUnitFlags, SetCondFlags, etc.)
    unit_flags: int = 0  # primary unit flag bits (game_rules.md)
    unit_flags2: int = 0  # secondary unit flag bits (game_rules.md)
    # One persistent 16-bit condition word (notes/unit_script_control.md): bit 2 (COND_TRUE) is the truth
    # result read by If/IfNot/LoopIf*/SkipIfTrue/..., written by Test*/Find*/GetEvent; the other bits
    # (pending switch 8, script flag 0x10, switches refused 0x20) are set by SetCondFlags and friends.
    cond_bits: int = 0
    threat_range: int = 0  # set by SetThreatRange; used by threat scoring
    # The single "remembered event" slot of StoreEventInfo (game_rules.md, scripted target and flight
    # opcodes): (sender regiment identifier, event code) of the event last stored, or None.
    remembered_event: tuple[str | None, int] | None = None

    # Timing (SetWait, TestWait, Wait)
    wait_remaining: float = 0.0  # ticks left in current Wait
    wait_duration: float = 0.0  # saved duration for TestWait checks
    waiting_for_start: bool = False
    wait_last_update: int | None = None

    # Current order and target (set by FindTarget*, AttackTarget, etc.)
    current_target: Target | None = None  # (regiment_id, unit_id) for attack/movement orders
    current_node: int | None = None  # waypoint node for movement orders
    pending_arrival: bool = False  # a MoveToNode order is in flight; see
    # ScriptInterpreter._update_arrival_flag, which sets ARRIVED_FLAG on unit_flags once the
    # regiment stops moving, so a WaitUntilUnitFlags(ARRIVED_FLAG) loop can unblock
    behaviour_id: int | None = None  # declared by SetBehaviour; recorded only, not auto-run
    # (see op_SetBehaviour -- there is no confirmed public evidence for when/how often a declared
    # library behaviour like 15/TrackThreat actually gets invoked versus a unit's own script opcodes
    # driving targeting directly, so nothing currently acts on this field automatically)
    parent_id: str | None = None  # set by SetParentByTag; the regiment this unit follows/reports to
    tag: int = 0  # runtime-only 16-bit tag set by SetTag, 0 = no tag (notes/threat_events_nodes.md, part B 0.1)

    # Interrupt handling (SetInterruptScript/CallInterruptScript/ReturnInterrupt)
    interrupt_return: tuple[int, int] | None = None  # (script_id, pc) to resume after ReturnInterrupt, set by
    # CallInterruptScript; None when not currently inside an interrupt call
    last_attack_target: str | None = None  # this unit's own attack_target as of the last tick, used
    # by ScriptInterpreter.raise_charge_events to detect a *fresh* charge (event 0x07) rather than
    # re-raising it every tick the same charge continues

    # Script metadata (loaded once at init)
    script_dll: behaviour.ScriptDll | None = None  # for script lookup

    @property
    def cond_flags(self) -> int:
        """The condition result (bit 2 of the condition word) as 0/1."""
        return 1 if self.cond_bits & COND_TRUE else 0

    @cond_flags.setter
    def cond_flags(self, value: object) -> None:
        self.cond_bits = (self.cond_bits | COND_TRUE) if value else (self.cond_bits & ~COND_TRUE)


class EventBus:
    """Per-side event routing (self, own-side, enemy-side broadcasts)."""

    def __init__(self, battle: "Battle") -> None:
        self.battle = battle
        self.unit_states: dict[str, UnitScriptState] = {}  # {unit_identifier: UnitScriptState}

    def is_live(self, unit_id: str) -> bool:
        """A scripted unit still in the battle: not destroyed, not routed off the field and not removed
        by a script. Routed, hidden and off-field-waiting units are live (notes/threat_events_nodes.md,
        part B 0.1)."""
        regiment = self.battle.regiments.get(unit_id)
        return unit_id in self.unit_states and regiment is not None and regiment.active

    def find_by_tag(self, tag: int) -> str | None:
        """The first live unit in unit-table order carrying `tag`; tag 0 never matches (part B 0.1)."""
        if not tag:
            return None
        return next((unit_id for unit_id in self.battle.regiments
                     if self.is_live(unit_id) and self.unit_states[unit_id].tag == tag), None)

    def queue_event(self, recipient_id: str, event: Event, route: str = "self", checked: bool = False) -> None:
        """Queue an event to a recipient or broadcast to a side (notes/threat_events_nodes.md, part B 0.2).

        route: "self" (single recipient), "side" (own-side broadcast), "enemy" (enemy-side broadcast).
        Records go to the head of each recipient's LIFO queue and are dropped for a recipient that is not
        live. `checked` sends (and both broadcasts) are also refused during the deployment phase.
        Broadcast sides split units by the enemy side alone: neutral units share the player's side.
        """
        if (checked or route != "self") and self.battle.phase == "deployment":
            return
        if route == "self":
            if self.is_live(recipient_id):
                self.unit_states[recipient_id].event_queue.append(event)
            return
        regiment = self.battle.regiments.get(recipient_id)
        if regiment is None:
            return
        sender_enemy = regiment.side == Side.ENEMY
        same = route == "side"
        for unit_id, unit_state in self.unit_states.items():
            other = self.battle.regiments.get(unit_id)
            if other and self.is_live(unit_id) and ((other.side == Side.ENEMY) == sender_enemy) == same:
                unit_state.event_queue.append(event)


class LibraryBehaviors:
    """Standard library behaviors (scripts 100-170) that are used across missions.

    Behavior 15 (TrackThreat) is the primary AI for 290+ missions:
    Keep the best threat and attack when its score exceeds the unit's worth.
    """

    def __init__(self, interpreter: "ScriptInterpreter") -> None:
        self.interpreter = interpreter

    def track_threat(self, unit_id: str, state: UnitScriptState, tick_count: int, rng: random.Random) -> None:
        """Behavior 15: TrackThreat AI - seek and attack best threat.

        Threat score = worth × (range − distance) / round(range / 4)
        Only attack if score > unit's worth (simplified: always attack if threat found).
        Distance metric: octagonal (max(|dx|, |dy|) + min(|dx|, |dy|) / 2).
        """
        battle = self.interpreter.battle
        if battle.phase == "deployment":
            return
        battle.refresh_visibility()
        regiment = battle.regiments.get(unit_id)
        if not regiment or regiment.side == Side.PLAYER or not regiment.active:
            return

        # Find best threat (nearest active, different-side regiment): a script that assigns this
        # library behaviour to a neutral unit has already made the targeting decision explicitly, so
        # this is not gated by rules.hostile_sides.
        best_threat: str | None = None
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
_REACT_MESSAGES: dict[int, str] = {
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

    def __init__(self, battle: "Battle", event_bus: EventBus, script_dll: behaviour.ScriptDll,
                 logger: BattleLogger | None = None) -> None:
        self.battle = battle
        self.event_bus = event_bus
        self.script_dll = script_dll
        self.behaviors = LibraryBehaviors(self)
        self.logger = logger  # whshr.battle_log.BattleLogger, or None; see write_opcode
        self._reported_gaps: set[tuple[str, int, int]] = set()  # (unit_id, script_id, opcode): a missing/broken opcode already
        # surfaced as a BattleEvent once, so a tight retry loop doesn't spam the same complaint
        # every tick for the rest of the battle.

    def _state_snapshot(self, unit_id: str, state: UnitScriptState) -> dict[str, Any]:
        """A small, JSON-safe snapshot of the fields opcodes actually change, for write_opcode."""
        regiment = self.battle.regiments.get(unit_id)
        return {
            "pc": state.pc, "script_id": state.script_id, "cond_flags": state.cond_flags,
            "unit_flags": state.unit_flags, "pending_switch": state.pending_switch,
            "current_target": list(state.current_target) if state.current_target else None,
            "wait_remaining": state.wait_remaining,
            "attack_target": regiment.attack_target if regiment else None,
        }

    def _update_arrival_flag(self, unit_id: str, state: UnitScriptState) -> None:
        """If a MoveToNode order is in flight (state.pending_arrival) and the
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
        if not state.pending_arrival:
            return
        regiment = self.battle.regiments.get(unit_id)
        if regiment is not None and not regiment.moving:
            state.unit_flags |= ARRIVED_FLAG
            state.pending_arrival = False

    def _mirror_engine_flags(self, unit_id: str, state: UnitScriptState) -> None:
        """Copy engine-owned conditions into the script's unit flags, so scripts see what the battle
        knows: IN_MELEE_FLAG follows `Regiment.in_melee` (raised and cleared as the fight starts and ends)."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment is None:
            return
        if regiment.in_melee:
            state.unit_flags |= IN_MELEE_FLAG
        else:
            state.unit_flags &= ~IN_MELEE_FLAG
        if regiment.hidden:
            state.unit_flags |= 0x80000
        else:
            state.unit_flags &= ~0x80000
        # Re-forming (8): models are walking to new slots; scripts hold with WaitWhileUnitFlags 8 after a
        # re-form. Broken (0x2000): the unit is routing (notes/movement_formation.md, sections 9 and 4).
        if regiment.reforming:
            state.unit_flags |= REFORMING_FLAG
        else:
            state.unit_flags &= ~REFORMING_FLAG
        if regiment.routing:
            state.unit_flags |= BROKEN_FLAG
        else:
            state.unit_flags &= ~BROKEN_FLAG
        # Independent: the library handler re-forms a non-independent player unit instead of
        # counter-attacking (notes/threat_events_nodes.md, part B 1).
        if regiment.independent:
            state.unit_flags |= INDEPENDENT_FLAG
        else:
            state.unit_flags &= ~INDEPENDENT_FLAG
        # "Halted": scripts wait on it (WaitUntilUnitFlags 16) to learn a move, turn or charge is over
        # (notes/movement_formation.md, section 1.3). It holds while the unit has nothing to do and is
        # dropped as soon as it travels, turns, charges or routes.
        if self._is_idle(regiment):
            state.unit_flags |= ARRIVED_FLAG
        elif not regiment.in_melee:
            state.unit_flags &= ~ARRIVED_FLAG

    @staticmethod
    def _is_idle(regiment: "Regiment") -> bool:
        return not (regiment.moving or regiment.waypoints or regiment.attack_target is not None
                    or regiment.turn_order_key is not None or regiment.routing or regiment.in_melee)

    def raise_charge_events(self) -> None:
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
    def _preempt_for_pending_event(state: UnitScriptState) -> None:
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

    def run(self, unit_id: str, state: UnitScriptState, tick_count: int, rng: random.Random) -> UnitScriptState:
        """Execute one unit's script for one tick.

        Returns the state after execution. Modifies state in-place.
        """
        # The condition never carries across a tick boundary (notes/unit_script_control.md section 1).
        state.cond_flags = False
        self._advance_wait_timer(state, tick_count)
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

            # A Wait that is still counting down is the default state of an idle unit: one identical
            # record per tick per unit buried the interesting lines. The record where the wait ends
            # (pc advances) is still written.
            still_waiting = opcode == WAIT_OPCODE and state.pc == pc_before and state.script_id == script_before
            if self.logger is not None and self.logger.trace_scripts and not still_waiting:
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

    def _report_gap(self, unit_id: str, script_id: int, opcode: int, reason: str) -> None:
        """Surface a missing/broken opcode as a battle event, once per (unit, script, opcode)."""
        key = (unit_id, script_id, opcode)
        if key in self._reported_gaps:
            return
        self._reported_gaps.add(key)
        name = behaviour.opcode_name(opcode)
        self.battle.events.append(BattleEvent(
            f"{unit_id}: script {script_id} opcode {name} ({opcode:#04x}) {reason}; skipped.",
            "script_gap", unit=unit_id, script_id=script_id, opcode=opcode, opcode_name=name))

    def _dispatch(self, state: UnitScriptState, opcode: int, script_words: Words, unit_id: str, tick_count: int,
                  rng: random.Random) -> int | None:
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

    def _get_operand(self, state: UnitScriptState, opcode: int, script_words: Words) -> int | None:
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

    def _nearest_enemy_id(self, regiment: "Regiment", n: int = 1, side: Side | None = None,
                          visible_only: bool = False) -> str | None:
        """Whole-field nearest search; positive n wraps through eligible units (game_rules.md)."""
        candidates = [other for other in self.battle.regiments.values()
                      if other.active and not (other.hidden or other.routing or other.held)
                      and (other.side == side if side is not None else other.side != regiment.side)]
        if visible_only:
            candidates = [other for other in candidates if visibility.visible(
                self.battle.formation_centre(regiment), regiment.direction,
                self.battle.formation_centre(other), other.bounding_radius(),
                142 if regiment.in_melee else 71, self.battle.boundaries, self.battle.objects)]
        enemies = sorted(candidates, key=lambda other: math.trunc(math.hypot(
            other.x - regiment.x, other.y - regiment.y)))
        return enemies[(max(1, n) - 1) % len(enemies)].identifier if enemies else None

    @staticmethod
    def _unit_worth(regiment: "Regiment") -> int:
        """game_rules.md: unit worth = size x s_pntval x 12 artillery / 8 wizard / 4 monster / 1,
        read by AI target scoring (UnitScore)."""
        multiplier = {"art": 12, "wiz": 8, "mon": 4}.get(regiment.hud_class or "", 1)
        return regiment.models * regiment.points * multiplier

    def _threat_score(self, regiment: "Regiment", other: "Regiment", threat_range: float) -> float:
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

    def op_InitUnit(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_Restart(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """Restart: jump to the restart point (set by SetRestartPoint)."""
        state.pc = state.restart_pc
        return state.pc

    def op_SetRestartPoint(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetRestartPoint: save current PC as the restart point for Restart."""
        state.restart_pc = state.pc + 1
        return state.pc + 1

    def op_GotoScript(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """GotoScript N: switch to script N and restart."""
        if operand is not None:
            state.script_id = operand
            state.pc = 0
        return 0

    def op_SwitchScript(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SwitchScript N: switch to script N after this tick completes."""
        if operand is not None:
            state.pending_switch = operand
        return state.pc + 1

    def op_IfSwitchScript(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfSwitchScript N: request switching to script N at end of tick, but only if nothing
        else has already requested a switch this tick (normal priority; game_rules.md documents
        opcodes 0x0D-0x10 together as "switch script at end of tick", 0x0F called out as
        "high priority" -- the priority ordering among 0x0D/0x0E is inferred from that framing,
        not independently confirmed)."""
        if operand is not None and state.pending_switch is None:
            state.pending_switch = operand
        return state.pc + 1

    def op_IfSwitchScriptHigh(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfSwitchScriptHigh N: request switching to script N at end of tick, overriding any
        other pending switch this tick (the "high priority" variant per game_rules.md)."""
        if operand is not None:
            state.pending_switch = operand
        return state.pc + 1

    def op_IfNotSwitchScript(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfNotSwitchScript N: request switching to script N at end of tick, unless the unit is
        already running script N. Treated as normal priority (does not override an existing
        pending switch), matching IfSwitchScript -- the exact precedence versus IfSwitchScript is
        not independently confirmed in the public notes, only that all four opcodes (0x0D-0x10)
        share the same "switch at end of tick" mechanism."""
        if operand is not None and operand != state.script_id and state.pending_switch is None:
            state.pending_switch = operand
        return state.pc + 1

    def op_GosubScript(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """GosubScript N: call script N like a subroutine, return via ReturnGosub."""
        if operand is not None:
            state.return_stack.append((state.script_id, state.pc + 1))
            state.script_id = operand
            state.pc = 0
        return 0

    def op_ReturnGosub(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ReturnGosub: return from gosub, restoring script and PC."""
        if state.return_stack:
            state.script_id, state.pc = state.return_stack.pop()
        return state.pc

    def op_PushPC(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """PushPC: push current PC for Loop to jump back to."""
        state.return_stack.append((state.pc + 1,))  # tag with tuple to distinguish from gosub
        return state.pc + 1

    @staticmethod
    def _leave_loop(state: UnitScriptState) -> None:
        """A conditional loop that ends drops its `PushPC` entry. Left in place, the next unconditional
        `Loop` of an enclosing cycle jumps back into the *inner* loop instead of its own start (BF001's
        patrols: `PushPC; MoveToNode..; PushPC; ..wait..; LoopIfFalse; ..; Loop` never left the last wait)."""
        if state.return_stack and len(state.return_stack[-1]) == 1:
            state.return_stack.pop()

    def op_Loop(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_Yield(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """Yield: return control to the battle, resume next tick."""
        self._should_yield = True
        return state.pc + 1

    # ===== Unit flag and condition opcodes =====

    def op_SetUnitFlags(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetUnitFlags N: set bits in unit_flags."""
        if operand is not None:
            state.unit_flags |= operand
            if operand & 0x80000:
                regiment = self.battle.regiments.get(unit_id)
                if regiment is not None:
                    regiment.hidden = True
        return state.pc + 1

    def op_ClearUnitFlags(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ClearUnitFlags N: clear bits in unit_flags."""
        if operand is not None:
            state.unit_flags &= ~operand
            if operand & 0x80000:
                regiment = self.battle.regiments.get(unit_id)
                if regiment is not None:
                    regiment.hidden = False
        return state.pc + 1

    def op_TestUnitFlags(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """TestUnitFlags N: set cond_flags to (unit_flags & N)."""
        if operand is not None:
            state.cond_flags = state.unit_flags & operand
        return state.pc + 1

    def op_WaitUntilUnitFlags(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_WaitWhileUnitFlags(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """WaitWhileUnitFlags N: yield (same PC) while any bit of N is set in unit_flags, then fall through.

        The mirror of WaitUntilUnitFlags. Scripts use it with 8 ("routed") to hold a formation back
        until the unit has rallied (notes/mission_walkthroughs_BF010.md). PROVISIONAL: "any bit" vs
        "all bits" of a multi-bit mask (the library also passes 0x4008) is not documented publicly.
        """
        if operand is not None and (state.unit_flags & operand):
            self._should_yield = True
            return state.pc
        return state.pc + 2

    def op_SetUnitFlags2(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetUnitFlags2 N: set bits in the secondary unit flag word (game_rules.md, control opcodes)."""
        if operand is not None:
            state.unit_flags2 |= operand
        return state.pc + 2

    def op_ClearUnitFlags2(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ClearUnitFlags2 N: clear bits in the secondary unit flag word."""
        if operand is not None:
            state.unit_flags2 &= ~operand
        return state.pc + 2

    def op_TestUnitFlags2(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """TestUnitFlags2 N: the condition result is whether any bit of N is set in the secondary word."""
        if operand is not None:
            state.cond_flags = (state.unit_flags2 & operand) != 0
        return state.pc + 2

    def op_WaitUntilUnitFlags2(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """WaitUntilUnitFlags2 N: yield (same PC) until a bit of N is set in the secondary word."""
        if operand is not None and (state.unit_flags2 & operand):
            return state.pc + 2
        self._should_yield = True
        return state.pc

    def op_WaitWhileUnitFlags2(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """WaitWhileUnitFlags2 N: yield (same PC) while a bit of N is set in the secondary word."""
        if operand is not None and (state.unit_flags2 & operand):
            self._should_yield = True
            return state.pc
        return state.pc + 2

    def op_YieldIfTrue(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """YieldIfTrue: end this unit's tick when the condition result is true; otherwise continue."""
        if state.cond_flags:
            self._should_yield = True
        return state.pc + 1

    def op_SkipIfTrue(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SkipIfTrue N: when the condition result is true, skip the N words that follow this
        two-word instruction (resume at pc + 2 + N); otherwise continue at pc + 2.

        N counts raw words, not instructions, and is signed. The condition is neither consumed nor
        changed. No label or end-of-script checks (notes/skip_if_true.md).
        """
        if operand is not None and state.cond_flags:
            return state.pc + 2 + _signed_word(operand)
        return state.pc + 2

    def op_IfGotoScript(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfGotoScript N: when the condition is true, switch at once to script N (word 0, same tick).

        Stack, restart point, wait timer and condition stay untouched, exactly like GotoScript; unlike
        the SwitchScript family it records no pending switch (notes/unit_script_control.md section 6).
        """
        if operand is not None and state.cond_flags:
            return self.op_GotoScript(state, operand, script_words, unit_id, tick_count, rng)
        return state.pc + 2

    def op_IfNotGotoScript(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfNotGotoScript N: GotoScript N when the condition is false."""
        if operand is not None and not state.cond_flags:
            return self.op_GotoScript(state, operand, script_words, unit_id, tick_count, rng)
        return state.pc + 2

    def op_RepeatStart(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """RepeatStart N: push the body start (pc + 2) and the count N; the body is the words up to RepeatNext.

        The two entries share the script stack with PushPC and Gosub, so repeats nest and sit inside
        loops (notes/unit_script_control.md section 3). N = 0 wraps to 65536 iterations.
        """
        if operand is None:
            return state.pc + 2
        state.return_stack.append((state.pc + 2, operand & 0xFFFF, REPEAT_ENTRY))
        return state.pc + 2

    def op_RepeatNext(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """RepeatNext: count down; jump back to the body start while it is non-zero, else drop the entry."""
        if not state.return_stack or len(state.return_stack[-1]) != 3:
            return state.pc + 1  # unbalanced repeat: treated as an error, falls through
        body_start, count, _ = state.return_stack.pop()
        count = (count - 1) & 0xFFFF
        if count:
            state.return_stack.append((body_start, count, REPEAT_ENTRY))
            return body_start
        return state.pc + 1

    def op_DrainEvents(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """DrainEvents: discard every queued event unhandled; the last one taken (the oldest) stays as
        the current event, unconsumed. The condition becomes true if anything was drained, else nothing
        changes (notes/unit_script_control.md section 4)."""
        if state.event_queue:
            while state.event_queue:
                state.current_event = state.event_queue.pop()
            state.cond_flags = True
        return state.pc + 1

    def op_ClearEvent(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ClearEvent: forget the current event only; the queue and the condition are untouched."""
        state.current_event = Event()
        return state.pc + 1

    def op_Nop(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """Nop: do nothing."""
        return state.pc + 1

    op_Nop1 = op_Nop

    def op_SetCondFlags(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetCondFlags M: OR M into the condition word; with bit 15 set, replace the word with M & 0x7FFF."""
        if operand is not None:
            state.cond_bits = (operand & 0x7FFF) if operand & 0x8000 else (state.cond_bits | operand)
        return state.pc + 2

    def op_ClearCondFlags(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ClearCondFlags M: clear the bits of M in the condition word (bit 15 is not special)."""
        if operand is not None:
            state.cond_bits &= ~operand
        return state.pc + 2

    def op_TestCondFlags(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """TestCondFlags M: the condition becomes whether any bit of M is set (tested before the update)."""
        if operand is not None:
            state.cond_flags = (state.cond_bits & operand) != 0
        return state.pc + 2

    # ===== Event handling opcodes =====

    def op_GetEvent(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """GetEvent: fetch the next event from the queue.

        `run()`'s dispatch loop must not pre-pop the queue into `current_event` on its own: this
        handler's own "queue empty" branch would then blank out an event a caller (in practice,
        `_preempt_for_pending_event`) had already correctly placed there, since by the time GetEvent
        ran the queue looked empty even though current_event was already valid. An earlier version
        of the loop did exactly that and silently discarded every event dispatched via preemption.
        """
        if state.event_queue:
            state.current_event = state.event_queue.pop()  # LIFO: the most recent event first
            state.cond_flags = 1
        else:
            state.current_event = Event()
            state.cond_flags = 0  # the handler frame's `ConsumeEvent; LoopIfTrue` ends when drained
        return state.pc + 1

    def op_ConsumeEvent(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ConsumeEvent: release the current event; the condition becomes "more events are queued"."""
        state.current_event = Event()
        state.cond_flags = bool(state.event_queue)
        return state.pc + 1

    def op_CaseEvent(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_Break(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_SendEventSelf(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SendEventSelf CODE: queue an event to self."""
        if operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="self")
        return state.pc + 1

    def op_SendEventSelfIfTrue(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SendEventSelfIfTrue CODE: queue event to self if cond_flags is true."""
        if state.cond_flags and operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="self")
        return state.pc + 1

    def op_SendEventSelfIfFalse(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SendEventSelfIfFalse CODE: queue event to self if cond_flags is false."""
        if not state.cond_flags and operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="self")
        return state.pc + 1

    def op_SendEventToOwnSide(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SendEventToOwnSide CODE: broadcast event to own-side units."""
        if operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="side")
        return state.pc + 1

    def op_SendEventToOwnSideIfTrue(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SendEventToOwnSideIfTrue CODE: broadcast event to own-side if cond_flags is true."""
        if state.cond_flags and operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="side")
        return state.pc + 1

    def op_SendEventToEnemySide(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SendEventToEnemySide CODE: broadcast event to enemy-side units."""
        if operand is not None:
            event = Event(code=operand, source=unit_id)
            self.event_bus.queue_event(unit_id, event, route="enemy")
        return state.pc + 1

    # ===== Conditional branches =====

    def op_If(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_IfNot(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_Else(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_EndIf(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """EndIf: end of if/else block."""
        return state.pc + 1

    # ===== Timing and wait opcodes =====

    def op_WaitForBattleStart(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """WaitForBattleStart: hold until the deployment phase is explicitly confirmed.

        Must yield like Wait/WaitUntilUnitFlags while blocked -- a prior version returned the same
        pc without setting _should_yield, so the dispatch loop just re-executed this instruction
        until max_iterations (10000) was hit instead of properly ending the tick. Confirmed from a
        real trace: every unit burned ~9993-9997 identical WaitForBattleStart dispatches on tick 0
        alone. Not fatal (state.pc still ends up in the right place once tick_count > 0), but wildly
        wasteful and made the opcode trace nearly unusable for actually debugging anything else.
        """
        state.waiting_for_start = self.battle.phase == "deployment"
        if state.waiting_for_start:
            self._should_yield = True
            return state.pc  # wait (don't advance)
        return state.pc + 1  # resume

    def op_SetWait(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetWait N: set a timer for N ticks."""
        if operand is not None:
            state.wait_duration = operand
            state.wait_remaining = operand
            state.wait_last_update = None
        return state.pc + 1

    @staticmethod
    def _advance_wait_timer(state: UnitScriptState, update: int) -> None:
        if state.wait_remaining > 0 and state.wait_last_update != update:
            state.wait_remaining = max(0.0, state.wait_remaining - 1)
            state.wait_last_update = update

    def op_TestWait(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """TestWait: decrement wait_remaining; set cond_flags if still waiting."""
        self._advance_wait_timer(state, tick_count)
        state.cond_flags = 1 if state.wait_remaining > 0 else 0
        return state.pc + 1

    def op_Wait(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """Wait N: hold for N ticks (yield until timer expires)."""
        if operand is not None:
            if state.wait_remaining == 0:
                state.wait_remaining = operand
        self._advance_wait_timer(state, tick_count)
        if state.wait_remaining > 0:
            self._should_yield = True  # yield to let other units run
            return state.pc
        return state.pc + 1

    def op_LoopIfTrue(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """LoopIfTrue: jump back to pushed PC if cond_flags is true."""
        if state.cond_flags and state.return_stack and len(state.return_stack[-1]) == 1:
            return state.return_stack[-1][0]
        self._leave_loop(state)
        return state.pc + 1

    def op_LoopIfFalse(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """LoopIfFalse: jump back to pushed PC if cond_flags is false."""
        if not state.cond_flags and state.return_stack and len(state.return_stack[-1]) == 1:
            return state.return_stack[-1][0]
        self._leave_loop(state)
        return state.pc + 1

    # ===== Targeting and threat opcodes =====

    def op_FindTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """FindTarget: find the nearest valid enemy target."""
        # TODO: implement proper targeting (check visibility, range, etc.)
        # Simplified: set cond_flags to indicate target found
        state.cond_flags = 1  # assume target found
        return state.pc + 1

    def op_FindTargetNear(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """FindTargetNear: find nearest enemy within threat range."""
        state.cond_flags = 1  # assume target found
        return state.pc + 1

    def op_FindNewTargetNear(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """FindNewTargetNear: find a new target, ignoring current one."""
        state.cond_flags = 1  # assume target found
        return state.pc + 1

    def op_TargetNearestEnemy(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """TargetNearestEnemy: set current target to nearest enemy."""
        regiment = self.battle.regiments.get(unit_id)
        target_id = self._nearest_enemy_id(regiment) if regiment else None
        if target_id:
            state.current_target = (target_id, 0)
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_AttackNearestEnemy(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """AttackNearestEnemy: find the nearest enemy and attack it (game_rules.md opcode 0xB0)."""
        return self._attack_nearest(state, unit_id, n=1)

    def op_AttackNearestVisibleEnemy(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """Whole-field nearest search restricted by the view cone and unobstructed sight."""
        return self._attack_nearest(state, unit_id, n=1, visible_only=True)

    def op_AttackNearestFlag40Unit(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """AttackNearestFlag40Unit: attack the nearest unit carrying side flag 0x40 (neutral;
        notes/neutral_units.md's 2-bit side code, `rules.Side.NEUTRAL`)."""
        return self._attack_nearest(state, unit_id, n=1, side=Side.NEUTRAL)

    def op_AttackNthNearestEnemy(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """AttackNthNearestEnemy N: find the N-th nearest enemy (1-based) and attack it."""
        return self._attack_nearest(state, unit_id, n=operand or 1)

    def op_AttackNthNearestVisibleEnemy(self, state: UnitScriptState, operand: int | None, script_words: Words,
                                      unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """Select a wrapped n-th target among enemies passing sight checks."""
        return self._attack_nearest(state, unit_id, n=operand or 1, visible_only=True)

    def _attack_nearest(self, state: UnitScriptState, unit_id: str, n: int, side: Side | None = None,
                        visible_only: bool = False) -> int | None:
        if self.battle.phase == "deployment":
            state.cond_flags = 0
            return state.pc + 1
        regiment = self.battle.regiments.get(unit_id)
        if regiment is None:
            state.cond_flags = 0
            return state.pc + 1
        target_id = self._nearest_enemy_id(regiment, n, side=side, visible_only=visible_only)
        if target_id:
            state.current_target = (target_id, 0)
            if not regiment.anchored:
                regiment.attack_target = target_id
            self.event_bus.queue_event(unit_id, Event(code=0x04, source=target_id), route="self")
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    # ===== Formation, rally and grid opcodes (notes/movement_formation.md, Part B) =====

    def _may_reform(self, unit: "Regiment") -> bool:
        """Re-form requests are refused while routing, held or charging, and for a unit with no models."""
        return unit.models > 0 and not (unit.routing or unit.held or unit.attack_target is not None)

    def op_ReformToScriptRanks(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """ReformToScriptRanks: re-form at once to the rank count the battle file asks for (clamped).
        Refused while routing, held or charging; a unit in a fight keeps its block until it leaves.
        Does not halt the unit and does not write the condition."""
        unit = self.battle.regiments.get(unit_id)
        if unit is not None and self._may_reform(unit) and not unit.in_melee:
            self.battle.reform_to_ranks(unit, unit.script_ranks)
        return state.pc + 1

    def op_SetRanks(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SetRanks N: re-form to N ranks (not clamped to the model count, only to 1-8), with the refusals of
        ReformToScriptRanks. The unit's script rank count is unchanged. The original defers the layout to
        the next movement update; running it at once is equivalent for the scripts that Yield after it."""
        unit = self.battle.regiments.get(unit_id)
        if operand is not None and unit is not None and self._may_reform(unit) and not unit.in_melee:
            self.battle.reform_to_ranks(unit, operand, formation_clamp=False)
        return state.pc + 2

    def op_ResetModelAnimations(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """ResetModelAnimations: stagger the models: each one pauses 2 to 32 ticks (even values, from its
        own stagger number) before it walks, so a re-forming unit falls into line one model at a time."""
        unit = self.battle.regiments.get(unit_id)
        if unit is not None:
            unit.model_positions()  # seeds the per-model state
            for model in unit.melee_models:
                model.freeze_ticks = (model.stagger & 15) * 2 + 2
        return state.pc + 1

    def op_Rally(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """Rally: stop being broken, charging, pursuing or braced; halt and re-form to the script's rank
        count. While the unit is held the opcode yields without advancing and tries again next tick.
        Does not leave the grid, change the target or facing, or write the condition."""
        unit = self.battle.regiments.get(unit_id)
        if unit is None:
            return state.pc + 1
        unit.routing = False
        unit.rally_next_segment = None
        unit.flee_x = unit.flee_y = None
        unit.attack_target = None
        unit.charge_started_target = None
        unit.braced = False
        unit.braced_target = None
        unit.target_x = unit.target_y = None
        unit.waypoints.clear()
        unit.turn_order_key = None
        unit.model_positions()
        for model in unit.melee_models:
            model.freeze_ticks = 0
        if unit.held:
            self._should_yield = True
            return state.pc
        if unit.models > 0 and not unit.in_melee:
            self.battle.reform_to_ranks(unit, unit.script_ranks)
        return state.pc + 1

    def op_FlankRearTest(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FlankRearTest: inside a charge event handler, a charge from behind or into the rear half of a
        flank needs a Leadership test (no modifier). Failing it queues a rout event to the unit and writes
        false; otherwise (no test needed, or passed, or no sender) the condition is true."""
        unit = self.battle.regiments.get(unit_id)
        sender = self.battle.regiments.get(state.current_event.source or "")
        state.cond_flags = True
        if unit is None or sender is None or self._attack_direction(sender, unit) not in (1, 5, 2, 3):
            return state.pc + 1
        from . import combat
        if not combat.leadership_test(unit.leadership, rng):
            state.cond_flags = False
            self.event_bus.queue_event(unit_id, Event(code=0x0C, source=unit_id), "self")
        return state.pc + 1

    def op_LeaveSharedGrid(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """LeaveSharedGrid: leave the fight's grid. The condition says whether the unit was on one. The
        opponent learns on the next pairing pass; the target, orders and facing are kept."""
        unit = self.battle.regiments.get(unit_id)
        was_on_grid = unit is not None and unit.in_melee
        if unit is not None and was_on_grid:
            from . import combat
            combat.leave_grid(self.battle, unit)
        state.cond_flags = was_on_grid
        return state.pc + 1

    def op_LeaveGrid(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """LeaveGrid: LeaveSharedGrid without writing the condition."""
        unit = self.battle.regiments.get(unit_id)
        if unit is not None and unit.in_melee:
            from . import combat
            combat.leave_grid(self.battle, unit)
        return state.pc + 1

    def op_IfEngagedWithKind(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """IfEngagedWithKind MASK: true when the unit is in a fight with a map object of that kind. Every
        shipped script asks for buildings and furniture, which this engine never fights, so it is false."""
        state.cond_flags = False
        return state.pc + 2

    # ===== Movement and facing (notes/movement_formation.md, Part A) =====

    @staticmethod
    def _s_rlmv(unit: "Regiment") -> float:
        """The unit's movement stat, recovered from its free-movement speed (as Regiment.charge_reach does)."""
        from .engine import MOVING_FREELY_K
        return unit.speed_per_tick * 16 / MOVING_FREELY_K

    @staticmethod
    def _fold(angle: float) -> int:
        """Absolute angular difference folded into 0..256."""
        difference = abs(int(angle)) % 512
        return min(difference, 512 - difference)

    def _object_centre(self, unit: "Regiment") -> tuple[float, float]:
        return self.battle.formation_centre(unit)

    def _start_point_move(self, unit: "Regiment", goal: tuple[float, float], follows_unit: bool = False) -> None:
        """An ordinary move to a point: a new plan replaces any charge, turn order or earlier destination.
        A unit starting from rest first snaps 90/180 degrees towards it (game_rules.md, real time and movement)."""
        was_moving = unit.moving
        unit.waypoints.clear()
        unit.attack_target = None
        unit.charge_started_target = None
        unit.turn_order_key = None
        self.battle.set_point_route(unit, (float(goal[0]), float(goal[1])))
        unit.route_follows_unit = follows_unit
        if not was_moving:
            heading = round(math.atan2(goal[0] - unit.x, goal[1] - unit.y) * 512 / math.tau) % 512
            self.battle.snap_move_start(unit, heading)

    def op_MoveToTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """MoveToTarget: walk to the target's object centre. Refused (false) with no target, while the
        unit is re-forming or anchored. The destination is fixed until re-issued or re-aimed by
        IfTargetInChargeReach/ApproachTargetInReach: the unit does not track the target.

        PROVISIONAL: the original never ends this move by distance (it follows a unit until contact);
        this engine's ordinary arrival rule still applies.
        """
        pair = self._query_pair(state, unit_id)
        unit = pair[0] if pair else None
        state.cond_flags = False
        if pair is None or unit is None or unit.reforming or unit.anchored or unit.routing:
            return state.pc + 1
        self._start_point_move(unit, self._object_centre(pair[1]), follows_unit=True)
        state.cond_flags = True
        return state.pc + 1

    def op_RefreshRouteToTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """Refresh a multi-leg route when the direct path clears, or a single leg becomes blocked."""
        pair = self._query_pair(state, unit_id)
        if pair is None:
            state.cond_flags = False
            return state.pc + 1
        unit, target = pair
        if unit.target_x is None:
            return state.pc + 1
        from . import navigation
        goal = self._object_centre(target)
        crosses = navigation.first_crossing((unit.x, unit.y), goal,
                                            self.battle.navigation_boundaries) is not None
        if (crosses and not unit.waypoints) or (not crosses and unit.waypoints):
            self.battle.set_point_route(unit, goal)
            state.cond_flags = True
        return state.pc + 1

    def op_TurnToFaceTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """TurnToFaceTarget: a turn order towards the target; it stops any movement. False when the turn
        needed is 16 or less, or the unit is fleeing or anchored; true when a turn started."""
        pair = self._query_pair(state, unit_id)
        state.cond_flags = False
        if pair is None:
            return state.pc + 1
        unit, target = pair
        goal = self._bearing(unit, target)
        if self._fold(goal - unit.direction) <= 16 or unit.routing or unit.anchored:
            return state.pc + 1
        unit.target_x = unit.target_y = None
        unit.waypoints.clear()
        unit.attack_target = None
        self.battle.begin_script_turn(unit, goal)
        state.cond_flags = True
        return state.pc + 1

    def _instant_turn(self, unit: "Regiment", quarter_turns: int) -> None:
        """An instant turn about the block centre by `quarter_turns` x 128 (the unit stops; scripts re-issue
        a move). Refused while fleeing or anchored, and for a half turn also while re-forming."""
        if unit.routing or unit.anchored or (abs(quarter_turns) == 2 and unit.reforming):
            return
        unit.target_x = unit.target_y = None
        unit.turn_order_key = None
        goal = (unit.direction + 128 * quarter_turns) % 512
        if unit.turns_on_the_spot:
            unit.direction = goal
        else:
            self.battle.snap_move_start(unit, goal)  # pivots about the block centre and swaps ranks and frontage

    def op_QuarterTurnToTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """QuarterTurnToTarget: false when the target is within 64 of the facing; otherwise an instant
        quarter turn (65..192 off) or half turn (more) and true, even if the turn itself was refused."""
        pair = self._query_pair(state, unit_id)
        state.cond_flags = False
        if pair is None:
            return state.pc + 1
        unit, target = pair
        goal = self._bearing(unit, target)
        off = self._fold(goal - unit.direction)
        if off <= 64:
            return state.pc + 1
        if off > 192:
            self._instant_turn(unit, 2)
        else:
            clockwise = (goal - unit.direction) % 512 < 256
            self._instant_turn(unit, 1 if clockwise else -1)
        state.cond_flags = True
        return state.pc + 1

    def op_AboutFace(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """AboutFace: instant half turn; the condition is not written."""
        unit = self.battle.regiments.get(unit_id)
        if unit is not None:
            self._instant_turn(unit, 2)
        return state.pc + 1

    def op_QuarterTurn(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """QuarterTurn N: instant quarter turn, clockwise for operand 0x20 and anticlockwise otherwise."""
        unit = self.battle.regiments.get(unit_id)
        if unit is not None:
            self._instant_turn(unit, 1 if operand == 0x20 else -1)
        return state.pc + 2

    def op_CircleAroundTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """CircleAroundTarget: an ordinary move to the point 16/512 of a turn further round the target at the
        unit's current range (about 11 degrees clockwise). Condition: the move was accepted."""
        pair = self._query_pair(state, unit_id)
        state.cond_flags = False
        if pair is None:
            return state.pc + 1
        unit, target = pair
        if unit.reforming or unit.anchored or unit.routing:
            return state.pc + 1
        angle = (self._bearing(target, unit) + 16) % 512
        distance = self._distance(unit, target)
        goal = (target.x + math.floor(_trunc_sin(angle) * distance / 256),
                target.y + math.floor(_trunc_cos(angle) * distance / 256))
        self._start_point_move(unit, goal)
        state.cond_flags = True
        return state.pc + 1

    # --- charge aim point and reach ---

    def _attack_direction(self, charger: "Regiment", target: "Regiment") -> int:
        """The eight-way attack direction of `charger` against `target` (notes/movement_formation.md, 5):
        0/4 charger in front, 1/5 behind, 2/6 left flank (rear/front half), 3/7 right flank (rear/front half)."""
        diagonal = int(256 * math.atan(max(target.frontage, 1) / max(target.ranks, 1)) / math.pi)
        relative = (self._bearing_from_to((charger.x, charger.y), self._object_centre(target))
                    - int(target.direction)) % 512
        if relative < diagonal:
            return 1
        if relative <= 128:
            return 2
        if relative <= 256 - diagonal:
            return 6
        if relative < 256:
            return 0
        if relative < 256 + diagonal:
            return 4
        if relative < 384:
            return 7
        if relative <= 512 - diagonal:
            return 3
        return 5

    def _charge_aim_point(self, unit: "Regiment", target: "Regiment") -> tuple[float, float]:
        """The point a charge aims at: the target's object centre, pushed out by its bounding radius to the
        FAR side for block formations (war machines, monsters and wagons are aimed at their centre).
        notes/target_queries.md section 5.1 and notes/movement_formation.md section 5."""
        centre = self._object_centre(target)
        if target.hud_class in ("art", "mon") or target.is_wagon:
            return centre
        radius = int(target.bounding_radius())
        side = self._attack_direction(unit, target) % 4  # 0 front, 1 rear, 2 left flank, 3 right flank
        aim = (int(target.direction) + (256, 0, 128, -128)[side]) % 512
        return centre[0] + int(_trunc_sin(aim) * radius / 256), centre[1] + int(_trunc_cos(aim) * radius / 256)

    @staticmethod
    def _bearing_from_to(start: tuple[float, float], end: tuple[float, float]) -> int:
        return int(256 - 256 * math.atan2(end[0] - start[0], -(end[1] - start[1])) / math.pi) % 512

    def op_IfTargetInChargeReach(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfTargetInChargeReach: true when the charge aim point is within 12 x s_rlmv of the target's
        bounding circle and nothing prevents a charge now. Side effect, even when false: the unit's
        destination becomes the aim point (not while charging, so a running charge is not hijacked).

        Not modelled: route obstruction, friendly units in the way and blocked ground (no route planner).
        """
        pair = self._query_pair(state, unit_id)
        state.cond_flags = False
        if pair is None:
            return state.pc + 1
        unit, target = pair
        if unit.reforming:
            return state.pc + 1
        aim = self._charge_aim_point(unit, target)
        charging = unit.attack_target is not None
        if not charging and not unit.in_melee:
            unit.target_x, unit.target_y = float(aim[0]), float(aim[1])
        heading = self._bearing_from_to((unit.x, unit.y), aim)
        if (self._fold(heading - unit.direction) >= 32 or charging or unit.in_melee
                or target.attack_target is not None):
            return state.pc + 1
        reach = int(math.hypot(aim[0] - unit.x, aim[1] - unit.y)) - int(target.bounding_radius())
        state.cond_flags = reach < 12 * self._s_rlmv(unit)
        return state.pc + 1

    def op_ApproachTargetInReach(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """ApproachTargetInReach: re-aim the unit's destination at the charge aim point; the condition is
        whether the target is within the unit's threat range (octagonal distance)."""
        pair = self._query_pair(state, unit_id)
        state.cond_flags = False
        if pair is None:
            return state.pc + 1
        unit, target = pair
        aim = self._charge_aim_point(unit, target)
        unit.target_x, unit.target_y = float(aim[0]), float(aim[1])
        dx, dy = abs(target.x - unit.x), abs(target.y - unit.y)
        state.cond_flags = max(dx, dy) + math.ceil(min(dx, dy) / 2) < state.threat_range
        return state.pc + 1

    # ===== Target and range queries (notes/target_queries.md) =====

    def _query_pair(self, state: UnitScriptState, unit_id: str) -> tuple["Regiment", "Regiment"] | None:
        """The unit's regiment and its current target regiment, or None when either is missing.

        The target is always the current target, never the event source. This engine keeps no fire-order
        target point, so the "no target unit" fallback of InArcAndRange has nothing to fall back to.
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment is None or state.current_target is None:
            return None
        target = self.battle.regiments.get(state.current_target[0])
        return (regiment, target) if target is not None else None

    @staticmethod
    def _distance(unit: "Regiment", target: "Regiment") -> int:
        """Centre-to-centre Euclidean distance, truncated."""
        return int(math.hypot(target.x - unit.x, target.y - unit.y))

    @staticmethod
    def _bearing(unit: "Regiment", target: "Regiment") -> int:
        """Bearing from the unit to the target in 1/512 turn, 0 = +Y, clockwise, truncated."""
        return int(256 - 256 * math.atan2(target.x - unit.x, -(target.y - unit.y)) / math.pi) % 512

    def _in_arc(self, unit: "Regiment", target: "Regiment", half_width: int = 64) -> bool:
        """The circular difference between facing and bearing is strictly below `half_width`."""
        difference = abs(int(unit.direction) - self._bearing(unit, target)) % 512
        return min(difference, 512 - difference) < half_width

    @staticmethod
    def _weapon_range(unit: "Regiment") -> float:
        """Strict weapon range; a unit without a missile weapon has range 0 and is never in range."""
        return unit.missile_range or 0

    def op_InArc(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """InArc: the target lies within +-45 degrees of the unit's facing (false without a target)."""
        pair = self._query_pair(state, unit_id)
        state.cond_flags = pair is not None and self._in_arc(*pair)
        return state.pc + 2

    def op_InRange(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """InRange: the target is strictly inside weapon range. The operand only selects the player
        failure message in the original and never changes the result."""
        pair = self._query_pair(state, unit_id)
        state.cond_flags = pair is not None and self._distance(*pair) < self._weapon_range(pair[0])
        return state.pc + 2

    def op_InArcAndRange(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """InArcAndRange: arc first (skipped when the target stands exactly on the unit), then range."""
        pair = self._query_pair(state, unit_id)
        if pair is None:
            state.cond_flags = False
        else:
            unit, target = pair
            on_top = unit.x == target.x and unit.y == target.y
            state.cond_flags = ((on_top or self._in_arc(unit, target))
                                and self._distance(unit, target) < self._weapon_range(unit))
        return state.pc + 2

    def op_BrokenTargetInRange(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """BrokenTargetInRange: true when the target is not broken; a broken target counts only in range."""
        pair = self._query_pair(state, unit_id)
        if pair is None:
            state.cond_flags = False
        else:
            unit, target = pair
            state.cond_flags = (not target.routing) or self._distance(unit, target) < self._weapon_range(unit)
        return state.pc + 1

    def op_IfTargetNotBroken(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfTargetNotBroken: the target exists and is not routing."""
        pair = self._query_pair(state, unit_id)
        state.cond_flags = pair is not None and not pair[1].routing
        return state.pc + 1

    def op_IfTargetVisible(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfTargetVisible: line of sight to the target with the unit treated as facing it, so only
        scenery blocks the view (no cone, no range limit, no visible turn)."""
        pair = self._query_pair(state, unit_id)
        if pair is None:
            state.cond_flags = False
        else:
            unit, target = pair
            heading = math.atan2(target.x - unit.x, target.y - unit.y) * 512 / math.tau
            state.cond_flags = visibility.visible(
                self.battle.formation_centre(unit), heading, self.battle.formation_centre(target),
                target.bounding_radius(), 256, self.battle.boundaries, self.battle.objects)
        return state.pc + 1

    def op_TargetValid(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """TargetValid: test if current target is still valid."""
        # Simplified: assume target is valid
        state.cond_flags = 1 if state.current_target else 0
        return state.pc + 1

    def op_KeepThreat(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """KeepThreat: keep current threat (don't search for new one)."""
        return state.pc + 1

    def op_IfThreatOutweighsWorth(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_TargetGone(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """TargetGone: test if target is no longer visible/alive."""
        # For now, assume target still exists
        state.cond_flags = 0
        return state.pc + 1

    def op_TakeEventTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_MoveToNode(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_FaceNode(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """FaceNode N: turn to face waypoint node N (instant turn, not a movement order).

        Reuses Battle.turn_to so facing changes pivot the same way every other turn in the engine
        does (game_rules.md: "a turn always moves the unit position to keep the pivot still").
        """
        if operand is not None:
            regiment = self.battle.regiments.get(unit_id)
            coords = self.battle.nodes.get(operand)
            if regiment and coords and (coords[0] != regiment.x or coords[1] != regiment.y):
                dx, dy = coords[0] - regiment.x, coords[1] - regiment.y
                direction = round(math.atan2(dx, dy) * 512 / math.tau) % 512
                self.battle.turn_to(regiment, direction)
        return state.pc + 1

    def op_TeleportToNode(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_PlaceAtNode(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_ScatterModelsToNode(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ScatterModelsToNode N: send each model in formation to its own point around node id N.

        notes/scatter_models_to_node.md: N is a node `id` (Battle.script_nodes), not a list position;
        successive models alternate between the active nodes sharing that id, each getting a
        destination within the node's own radius (whshr.nodes.scatter_destinations). The regiment's
        position, order and formation slots are untouched; each model walks there on its own
        (Battle._advance_models) and stays until the next scatter or SnapModelsToFormation.

        Which models count as "in formation": the report leaves models that are still wandering
        alone. A model that has reached its destination is treated as available again, because the
        patrol scripts (e.g. BF003) snap only once, before their loop, yet are seen to wander
        continuously -- a provisional reading, listed in the report's open points.
        Deterministic: draws from Battle.rng like every other random decision in the engine.
        """
        if operand is not None:
            state.current_node = operand
            regiment = self.battle.regiments.get(unit_id)
            if regiment and not regiment.anchored:
                regiment.model_positions()  # seed the per-model states
                available = [model for model in regiment.melee_models
                             if model.scatter_target is None or model.at_rest]
                destinations = nodes.scatter_destinations(self.battle.script_nodes, operand, len(available),
                                                          self.battle.rng)
                for model, (_node, point) in zip(available, destinations):
                    model.scatter_target = point
                    model.at_rest = False
        return state.pc + 1

    def op_ChargeTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_FireAtTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_KillAllModels(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_AttackTagged(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """AttackTagged TAG: attack the unit marked with TAG.

        Example: BF001 Unit 2 uses AttackTagged 0xabc0 to hunt the tagged cargo unit.
        """
        if operand is not None:
            target_id = self.event_bus.find_by_tag(operand)
            if target_id is not None:
                state.current_target = (target_id, 0)
                regiment = self.battle.regiments.get(unit_id)
                if regiment and not regiment.anchored:
                    regiment.attack_target = target_id
                state.cond_flags = 1
            else:
                state.cond_flags = 0
        return state.pc + 1

    def op_SetTag(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetTag TAG: give this unit TAG, replacing any older tag, unless a live unit (itself included)
        already carries it; then nothing happens (notes/threat_events_nodes.md, part B 0.1)."""
        if operand is not None and self.event_bus.find_by_tag(operand) is None:
            state.tag = operand
        return state.pc + 2

    def op_SetParentByTag(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetParentByTag TAG: parent := the live unit carrying TAG now, or none when there is no such
        unit. The link is stored, not re-resolved when tags change later (notes/threat_events_nodes.md,
        part B 0.1)."""
        if operand is not None:
            state.parent_id = self.event_bus.find_by_tag(operand)
        return state.pc + 2

    def op_SnapModelsToFormation(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SnapModelsToFormation: bring scattered models back into formation.

        Clears every model's ScatterModelsToNode destination (notes/scatter_models_to_node.md), so
        each walks back to its own formation slot. Used right after the first ScatterModelsToNode in
        every BF003 peasant regiment's script.
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            for model in regiment.melee_models:
                model.scatter_target = None
        return state.pc + 1

    def op_SetBehaviour(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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


    def op_React(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """React N: display a battle message/voice with leader portrait (game_rules.md §React N).

        The actual text varies by s_race & 7; this table covers the code-level semantics only.
        PROVISIONAL: race-specific variants (e.g. "WAARRGGH!" for code 2) are not yet mapped.
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment is not None:
            msg = _REACT_MESSAGES.get(operand or 0, f"React {operand}")
            self.battle.events.append(BattleEvent(
                f"{regiment.name}: {msg}", "react",
                regiment=unit_id, code=operand, sender=regiment.name, message=msg))
        return state.pc + 1

    def op_RemoveFromBattle(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """RemoveFromBattle: remove unit from battle without death."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            regiment.fled = True  # mark as removed from play
        return state.pc + 1

    def op_ExcludeFromArmy(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ExcludeFromArmy: exclude unit from army roster (remove without death)."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            regiment.fled = True  # same effect as RemoveFromBattle
        return state.pc + 1

    def op_SetThreatRange(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetThreatRange N: set threat detection range (used by TrackThreat).

        Range in world units. Used to limit which enemies a unit considers as threats.
        Example: BF001 Unit 1 (dormant) has low threat range (40) to indicate minimal engagement.
        """
        if operand is not None:
            state.threat_range = operand
        return state.pc + 1

    def op_SetInterruptScript(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetInterruptScript N: set interrupt handler script.

        Called when the unit receives an event (e.g., being attacked, enemy spotted).
        Saves current position and switches to interrupt script.
        """
        if operand is not None:
            state.interrupt_script = operand
        return state.pc + 1

    def op_CallInterruptScript(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_ReturnInterrupt(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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

    def op_HaltAndReform(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """HaltAndReform: stop movement and reform in place."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            regiment.target_x = None
            regiment.target_y = None
            regiment.attack_target = None
        return state.pc + 1

    def op_ReformBlock(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ReformBlock: reform unit into a tight block formation."""
        # TODO: adjust regiment.ranks based on available models
        return state.pc + 1

    def op_DropTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """DropTarget: forget the current attack target (game_rules.md, scripted target and flight
        opcodes). Only a unit that is not broken and has a target acts: it clears the target and its
        braced state, and the condition is true; otherwise nothing changes and the condition is false.
        It never leaves a melee, changes orders or sends events."""
        regiment = self.battle.regiments.get(unit_id)
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

    def op_FleeAhead(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """FleeAhead: start a rout along the unit's current facing (game_rules.md, scripted target and
        flight opcodes). It is the rout itself, so `CantBreak` does not stop it; only an anchored war
        machine refuses. The target is always cleared; the condition is true when a rout started."""
        self._flee_along(state, unit_id, 0)
        return state.pc + 1

    def _flee_along(self, state: UnitScriptState, unit_id: str, turn: int) -> None:
        """Start a rout along the unit's facing plus `turn` (1/512 turn); the target is always cleared."""
        regiment = self.battle.regiments.get(unit_id)
        state.cond_flags = 0
        if regiment is None:
            return
        regiment.attack_target = None
        state.current_target = None
        if regiment.anchored or regiment.routing or not regiment.active:
            return
        from . import combat
        heading = (regiment.direction + turn) % 512
        angle = heading * math.tau / 512
        combat.start_rout(regiment, self.battle, flee_point=(
            regiment.x + math.sin(angle) * 1e4, regiment.y + math.cos(angle) * 1e4))
        regiment.direction = heading  # the flight heading is taken instantly, without a pivot
        state.cond_flags = 1

    def op_FleeBackward(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FleeBackward: FleeAhead in the opposite direction (facing + 256). The condition is always true,
        even when an anchored war machine refuses to move (notes/movement_formation.md, 3.7)."""
        self._flee_along(state, unit_id, 256)
        state.cond_flags = 1
        return state.pc + 1

    def op_StoreEventInfo(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """StoreEventInfo: remember the sender and code of the event being handled, overwriting any
        earlier one (game_rules.md, scripted target and flight opcodes)."""
        state.remembered_event = (state.current_event.source, state.current_event.code)
        return state.pc + 1

    def op_FaceModelsToTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """FaceModelsToTarget: turn the individual models, not the regiment, to face the target
        (game_rules.md, scripted target and flight opcodes). A model still walking is left alone and
        counts as "not finished"; a model at rest facing elsewhere gets its heading set instantly and
        also counts; the condition is true while any did. No target: nothing happens, condition false."""
        regiment = self.battle.regiments.get(unit_id)
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

    def op_RunAway(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """RunAway: cause unit to flee the battlefield.

        Similar to rout/panic, unit tries to leave the field.
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment and not regiment.routing and "CantBreak" not in regiment.psychology:
            # Trigger routing via combat module (start_rout takes (regiment, battle), not the reverse)
            from . import combat
            combat.start_rout(regiment, self.battle)
        return state.pc + 1

    def op_RoutAllowed(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """RoutAllowed: test whether this unit may currently rout (game_rules.md opcode 0xC8).

        A read-only check: true unless the regiment already routed/fled or carries CantBreak
        (the same guard whshr.combat._break_test applies before calling start_rout).
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment and regiment.active and not regiment.routing and "CantBreak" not in regiment.psychology:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_FleeFromTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """FleeFromTarget: flee from the current target/threat.

        Starts a rout via the same combat.start_rout path as RunAway/RoutAllowed if the unit
        isn't already routing and is allowed to; once routing, Battle._advance_regiments already
        drives the per-tick flee movement generically for any routing regiment, so this becomes a
        no-op on later ticks rather than needing its own movement logic here.
        """
        regiment = self.battle.regiments.get(unit_id)
        if regiment and not regiment.routing and "CantBreak" not in regiment.psychology:
            from . import combat
            combat.start_rout(regiment, self.battle)
        return state.pc + 1

    def op_FearWhenCharged(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
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
                self.battle.turn_to(regiment, direction)
        return state.pc + 1

    def op_ResetStack(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ResetStack: clear the return stack."""
        state.return_stack = []
        return state.pc + 1

    def op_ExecuteOrder(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ExecuteOrder: apply pending player order (if any)."""
        # TODO: check if player has issued an order and apply it
        # Player orders override script commands
        return state.pc + 1

    def op_RestartAfterOrder(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """RestartAfterOrder: restart script after player order completes."""
        # ExecuteOrder applies a player order, then this restarts at the restart point
        state.pc = state.restart_pc
        return state.pc

    def op_Query(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """Query N: ask the AI routine (cases 11-14 for threat detection)."""
        # Simplified: Query is used by FindTarget* opcodes to ask "is there a valid target?"
        # For now, set cond_flags based on operand (TODO: implement real threat scoring)
        if operand is not None:
            # Cases 11-14: threat detection queries
            # Set cond_flags to indicate whether a threat exists (simplified: always false for now)
            state.cond_flags = 0
        return state.pc + 1

    def op_IfObjective(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfObjective N: test if objective letter N is defined in the battle."""
        # TODO: check battle's objective letters (from .BTS file)
        # For now, assume objectives A-F always exist (simplified)
        if operand is not None and operand < 6:  # A=0, B=1, ..., F=5
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_IfClass(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfClass N: test if this unit's class matches N."""
        # TODO: check regiment's class from HUD_CLASS_BY_RACE_TYPE
        # For now, simplified: set cond_flags based on class
        state.cond_flags = 1  # assume matches for now
        return state.pc + 1

    def op_IfTag(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfTag TAG: condition := this unit's own tag equals TAG (notes/threat_events_nodes.md, part B 0.1)."""
        state.cond_flags = operand is not None and state.tag == operand
        return state.pc + 2

    def op_IfTagExists(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfTagExists TAG: condition := a live unit carries TAG (notes/threat_events_nodes.md, part B 0.1)."""
        state.cond_flags = operand is not None and self.event_bus.find_by_tag(operand) is not None
        return state.pc + 2

    def op_SetTargetByTag(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SetTargetByTag TAG: target := the live unit carrying TAG, condition true; none found leaves the
        target unchanged, condition false. No range, side, visibility or broken test, no event and no
        route (notes/threat_events_nodes.md, part B 6)."""
        target_id = self.event_bus.find_by_tag(operand or 0)
        if target_id is not None:
            state.current_target = (target_id, 0)
        state.cond_flags = target_id is not None
        return state.pc + 2

    def op_SendEventToTag(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SendEventToTag TAG CODE: checked send of CODE (source = this unit) to the live unit carrying
        TAG, of any side, possibly itself; nothing when none (notes/threat_events_nodes.md, part B 3)."""
        recipient = self.event_bus.find_by_tag(operand or 0)
        if recipient is not None and state.pc + 2 < len(script_words):
            self.event_bus.queue_event(recipient, Event(code=script_words[state.pc + 2], source=unit_id),
                                       checked=True)
        return state.pc + 3

    def op_SendEventToParent(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SendEventToParent CODE: queue CODE (source = this unit) to the stored parent, also during
        deployment; dropped when there is no parent or it is no longer live
        (notes/threat_events_nodes.md, part B 2)."""
        if state.parent_id is not None and operand is not None:
            self.event_bus.queue_event(state.parent_id, Event(code=operand, source=unit_id))
        return state.pc + 2

    def op_SendEventToUnitId(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SendEventToUnitId WHOAMI CODE: queue CODE (source = this unit) to the first live unit in table
        order whose set:whoami byte equals WHOAMI; no deployment check (notes/threat_events_nodes.md,
        part B 4)."""
        wanted = (operand or 0) & 0xFF
        recipient = next((other for other, regiment in self.battle.regiments.items()
                          if regiment.whoami == wanted and self.event_bus.is_live(other)), None)
        if recipient is not None and state.pc + 2 < len(script_words):
            self.event_bus.queue_event(recipient, Event(code=script_words[state.pc + 2], source=unit_id))
        return state.pc + 3

    def op_ReacquireEventSource(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """ReacquireEventSource P: when the current event came from the current target and the unit is not
        charging, in melee, or busy with a shooting or casting sequence, send itself (checked) event 0x39
        if P is set and the unit is not independent, else 0x04, with the target as source. Leaves the
        condition alone (notes/threat_events_nodes.md, part B 1)."""
        source = state.current_event.source
        regiment = self.battle.regiments.get(unit_id)
        if (source is None or regiment is None or state.current_target is None
                or state.current_target[0] != source):
            return state.pc + 2
        busy = state.unit_flags2 & (SHOOTING_SEQUENCE_FLAG2 | CASTING_SEQUENCE_FLAG2)
        if regiment.attack_target is not None or regiment.in_melee or busy:
            return state.pc + 2
        code = 0x39 if operand and not regiment.independent else 0x04
        self.event_bus.queue_event(unit_id, Event(code=code, source=source), checked=True)
        return state.pc + 2

    def op_SetSide(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SetSide V: the unit's side becomes the one V's side bits name (shipped: 64 = neutral/allied).
        Script, target, parent, tag and other units' targeting of it are unchanged; every rule reads the
        new side from now on (notes/threat_events_nodes.md, part B 5). Not modelled: V's low bits, which
        would alter the unit type code (no shipped operand has any), and the furniture side bit."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment is not None and operand is not None and not operand & 0x20:
            regiment.side = side_of_code(operand)
        return state.pc + 2

    def _in_node_area(self, regiment: "Regiment", node: int) -> bool:
        """The regiment's centre lies in the circle of `[NODES]` entry `node` (0-based file position):
        dx^2 + dy^2 <= radius^2, inclusive and untruncated; `dir` and status are ignored, and a missing
        node is never entered (notes/threat_events_nodes.md, part C 1-2 and 4.4)."""
        if not 0 <= node < len(self.battle.script_nodes):
            return False
        area = self.battle.script_nodes[node]
        return (regiment.x - area.x) ** 2 + (regiment.y - area.y) ** 2 <= area.radius ** 2

    def _units_in_battle(self) -> list[tuple[str, "Regiment"]]:
        """Every unit not destroyed, fled off the field or removed by a script, in unit-table order;
        hidden, broken and engaged units included (notes/threat_events_nodes.md, part C 3)."""
        return [(unit_id, regiment) for unit_id, regiment in self.battle.regiments.items() if regiment.active]

    def op_IfInNodeArea(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfInNodeArea N: condition := the running unit is in node N's area (notes/threat_events_nodes.md,
        part C 4.1)."""
        regiment = self.battle.regiments.get(unit_id)
        state.cond_flags = regiment is not None and self._in_node_area(regiment, operand or 0)
        return state.pc + 2

    def op_IfAnyUnitInNodeArea(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfAnyUnitInNodeArea N: condition := any unit in the battle, of any side and in any state, the
        running unit included, is in node N's area (notes/threat_events_nodes.md, part C 4.2)."""
        state.cond_flags = any(self._in_node_area(regiment, operand or 0)
                               for _, regiment in self._units_in_battle())
        return state.pc + 2

    def op_IfSideUnitInNodeArea(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfSideUnitInNodeArea SIDE N EXCLUDE: condition := a unit of the absolute side code SIDE (low
        byte: 0 player, 64 allied, 128 enemy; low five bits set never match) that shows none of the
        EXCLUDE unit-flag states (as TestUnitFlags reads them) is in node N's area
        (notes/threat_events_nodes.md, part C 4.3). Not modelled: building pseudo-units (side 32), which
        are not regiments here."""
        side_code = (operand or 0) & 0xFF
        node = script_words[state.pc + 2] if state.pc + 2 < len(script_words) else -1
        exclude = script_words[state.pc + 3] if state.pc + 3 < len(script_words) else 0
        wanted = side_of_code(side_code) if side_code in (0, 0x40, 0x80) else None
        found = False
        for other_id, regiment in self._units_in_battle():
            if regiment.side != wanted or not self._in_node_area(regiment, node):
                continue
            other_state = self.event_bus.unit_states.get(other_id)
            if exclude and other_state is not None:
                self._mirror_engine_flags(other_id, other_state)
                if other_state.unit_flags & exclude:
                    continue
            elif exclude & BROKEN_FLAG and regiment.routing:
                continue
            found = True
            break
        state.cond_flags = found
        return state.pc + 4

    def op_IfEventSource(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfEventSource: test if current event came from a specific source.

        Known limitation: the operand is a numeric source id from the bytecode, but
        Event.source in this engine holds a regiment identifier string (see the fix in
        SendEventSelf/etc.) -- there is no numeric-id-to-regiment mapping in this engine, so this
        comparison never matches today. Left as a documented gap rather than a guessed mapping.
        """
        state.cond_flags = 0
        return state.pc + 1

    def op_IfGameMode(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfGameMode N: test current game mode (1=deployment, 2=real time)."""
        if operand == (1 if self.battle.phase == "deployment" else 2):
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_IfBattleState(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfBattleState N: test current battle state."""
        if operand is not None and operand == self.battle.mission_state:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_SetBattleState(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetBattleState N: set current battle state."""
        if operand is not None:
            self.battle.mission_state = operand
        return state.pc + 1

    def op_EnemyRouted(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """EnemyRouted: test if any enemy unit is routing/fleeing."""
        battle = self.battle
        regiment = battle.regiments.get(unit_id)
        if regiment:
            for other in battle.regiments.values():
                if other.side != regiment.side and other.active and other.routing:
                    state.cond_flags = 1
                    return state.pc + 1
        state.cond_flags = 0
        return state.pc + 1

    def op_EnemyRoutedStatic(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """EnemyRoutedStatic: test if a specific enemy is routing (static check)."""
        return state.pc + 1

    def op_IfBreak(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfBreak: test if this unit is broken/fleeing."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment and regiment.routing:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_IfRouted(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfRouted: test if this unit is routed/fleeing."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment and regiment.routing:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_StartPursuit(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """StartPursuit: chase down a fleeing unit."""
        if state.current_target:
            regiment = self.battle.regiments.get(unit_id)
            if regiment and not regiment.anchored:
                regiment.attack_target = state.current_target[0]
        return state.pc + 1

    def op_ReadyToFire(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """ReadyToFire: test if unit can shoot (not reloading)."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment and regiment.missile_range and regiment.reload_ticks <= 0:
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    def op_StampReload(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """StampReload: manually reset reload counter (shortcut for rapid fire)."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            regiment.reload_ticks = 0
        return state.pc + 1

    def op_SpawnUnit(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SpawnUnit N: create Night Goblin Fanatics at current position.

        Only used in BF004_5, BF015, BF034, BF038 (fanatic battles).
        Fanatics are created with special behavior (0xD3 opcode).
        """
        # TODO: implement fanatic spawning
        # Requires creating new models at a position, which is complex
        return state.pc + 1

    def op_FollowParent(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """FollowParent: follow a parent unit (for child units in formation)."""
        # TODO: implement parent unit tracking
        return state.pc + 1

    def op_SetClass(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """SetClass N: change unit class (0=Monster, 1=Infantry, 3=Archer, etc.)."""
        # TODO: modify regiment.hud_class based on unit type
        if operand is not None:
            # Map class number to HUD class name
            class_names = {0: "mon", 1: "inf", 3: "arch", 15: "art", 19: "wiz"}
            regiment = self.battle.regiments.get(unit_id)
            if regiment and operand in class_names:
                regiment.hud_class = class_names[operand]
        return state.pc + 1

    def op_IfMachineDestroyed(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str, tick_count: int,
            rng: random.Random) -> int | None:
        """IfMachineDestroyed: test if an artillery machine is destroyed."""
        # TODO: check if specific war machine model is destroyed
        state.cond_flags = 0  # simplified: never destroyed
        return state.pc + 1

    # For any other opcode not explicitly handled, the dispatcher will raise NotImplementedError,
    # which is caught and logged by the run() method, allowing partial mission execution.
