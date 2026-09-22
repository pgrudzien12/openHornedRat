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
import struct
from collections import deque

from . import behaviour


@dataclass
class Event:
    """A 14-byte behaviour event record (game_rules.md, "Unit behaviour scripts and events")."""
    recipient: int = 0  # unit identifier (ignored by the queue: events are posted to units directly)
    code: int = 0  # event code 0x00..0x23 (36 codes enumerated in game_rules.md event table)
    source: int = 0  # sender's unit identifier
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
    cond_flags: int = 0  # condition flags for If/IfNot branching
    threat_range: int = 0  # set by SetThreatRange; used by threat scoring

    # Timing (SetWait, TestWait, Wait)
    wait_remaining: float = 0.0  # ticks left in current Wait
    wait_duration: float = 0.0  # saved duration for TestWait checks

    # Current order and target (set by FindTarget*, AttackTarget, etc.)
    current_target: tuple | None = None  # (regiment_id, unit_id) for attack/movement orders
    current_node: int | None = None  # waypoint node for movement orders

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
                    if other and other.player == regiment.player:
                        unit_state.event_queue.append(event)
        elif route == "enemy":
            # Broadcast to all units on the opposite side
            regiment = self.battle.regiments.get(recipient_id)
            if regiment:
                for unit_id, unit_state in self.unit_states.items():
                    other = self.battle.regiments.get(unit_id)
                    if other and other.player != regiment.player:
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
        if not regiment or regiment.player or not regiment.active:
            return

        # Find best threat (nearest active enemy)
        best_threat = None
        best_distance = float('inf')

        for other_id, other in battle.regiments.items():
            if other.player == regiment.player or not other.active:
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


class ScriptInterpreter:
    """Executes one unit's behaviour script for one tick.

    Maintains per-unit state (script_id, PC, return stack, event queue) and dispatches 232 opcodes
    to handler methods. Integrates with the battle engine for effects (charging, shooting, morale).

    Handlers follow the pattern: def op_<name>(self, state, operand) -> int (new PC).
    The new PC is returned, allowing control-flow opcodes (goto, gosub, loops) to manipulate it.
    For opcodes that fall through, handlers return pc + instruction_length.
    """

    def __init__(self, battle, event_bus, script_dll):
        self.battle = battle
        self.event_bus = event_bus
        self.script_dll = script_dll
        self.behaviors = LibraryBehaviors(self)

    def run(self, unit_id: str, state: UnitScriptState, tick_count: int, rng):
        """Execute one unit's script for one tick.

        Returns the state after execution. Modifies state in-place.
        """
        if state.script_dll is None:
            state.script_dll = self.script_dll

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

            # Check for event: if there is one, enter event handling
            if not state.current_event.code and state.event_queue:
                state.current_event = state.event_queue.popleft()

            # Check if this is an event handling frame (GetEvent called)
            # For now, simplified: just run the script, real implementation branches on CaseEvent
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
            try:
                new_pc = self._dispatch(state, opcode, script_words, unit_id, tick_count, rng)
                state.pc = new_pc if new_pc is not None else state.pc + behaviour.LENGTHS[opcode]
            except NotImplementedError as e:
                # Log missing opcodes but continue (safe for partial implementation)
                # print(f"Unit {unit_id}: unimplemented opcode {opcode:02X} ({behaviour.opcode_name(opcode)})")
                state.pc += behaviour.LENGTHS[opcode]
            except Exception as e:
                # Catastrophic handler error: log and continue
                # print(f"Unit {unit_id}: error in opcode {opcode:02X}: {e}")
                state.pc += behaviour.LENGTHS[opcode]

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

    # ===== Core control-flow opcodes =====

    def op_InitUnit(self, state, operand, script_words, unit_id, tick_count, rng):
        """InitUnit N: initialize the unit's script state. N is typically 64 or 128."""
        state.script_id = operand if operand is not None else 100
        state.pc = 0
        state.restart_pc = 0
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

    def op_Loop(self, state, operand, script_words, unit_id, tick_count, rng):
        """Loop: jump back to the PC pushed by PushPC."""
        if state.return_stack and len(state.return_stack[-1]) == 1:
            return state.return_stack.pop()[0]
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

    def op_SetCondFlags(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetCondFlags N: set bits in cond_flags (for If/IfNot)."""
        if operand is not None:
            state.cond_flags |= operand
        return state.pc + 1

    def op_ClearCondFlags(self, state, operand, script_words, unit_id, tick_count, rng):
        """ClearCondFlags N: clear bits in cond_flags."""
        if operand is not None:
            state.cond_flags &= ~operand
        return state.pc + 1

    def op_TestCondFlags(self, state, operand, script_words, unit_id, tick_count, rng):
        """TestCondFlags N: test if any cond_flags match N."""
        if operand is not None:
            state.cond_flags = (state.cond_flags & operand) != 0
        return state.pc + 1

    # ===== Event handling opcodes =====

    def op_GetEvent(self, state, operand, script_words, unit_id, tick_count, rng):
        """GetEvent: fetch the next event from the queue."""
        if state.event_queue:
            state.current_event = state.event_queue.popleft()
        else:
            state.current_event = Event()
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
        """Break: jump to the next label (matching CaseEvent)."""
        # The operand is the label to jump to (0x1ABC encodes the label address)
        # For now, simplified: skip to next instruction after the current opcode
        return state.pc + 1

    def op_SendEventSelf(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventSelf CODE: queue an event to self."""
        if operand is not None:
            event = Event(code=operand, source=int(unit_id) if unit_id.isdigit() else 0)
            self.event_bus.queue_event(unit_id, event, route="self")
        return state.pc + 1

    def op_SendEventSelfIfTrue(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventSelfIfTrue CODE: queue event to self if cond_flags is true."""
        if state.cond_flags and operand is not None:
            event = Event(code=operand, source=int(unit_id) if unit_id.isdigit() else 0)
            self.event_bus.queue_event(unit_id, event, route="self")
        return state.pc + 1

    def op_SendEventSelfIfFalse(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventSelfIfFalse CODE: queue event to self if cond_flags is false."""
        if not state.cond_flags and operand is not None:
            event = Event(code=operand, source=int(unit_id) if unit_id.isdigit() else 0)
            self.event_bus.queue_event(unit_id, event, route="self")
        return state.pc + 1

    def op_SendEventToOwnSide(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventToOwnSide CODE: broadcast event to own-side units."""
        if operand is not None:
            event = Event(code=operand, source=int(unit_id) if unit_id.isdigit() else 0)
            self.event_bus.queue_event(unit_id, event, route="side")
        return state.pc + 1

    def op_SendEventToOwnSideIfTrue(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventToOwnSideIfTrue CODE: broadcast event to own-side if cond_flags is true."""
        if state.cond_flags and operand is not None:
            event = Event(code=operand, source=int(unit_id) if unit_id.isdigit() else 0)
            self.event_bus.queue_event(unit_id, event, route="side")
        return state.pc + 1

    def op_SendEventToEnemySide(self, state, operand, script_words, unit_id, tick_count, rng):
        """SendEventToEnemySide CODE: broadcast event to enemy-side units."""
        if operand is not None:
            event = Event(code=operand, source=int(unit_id) if unit_id.isdigit() else 0)
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
        """WaitForBattleStart: hold until battle has started (tick_count > 0)."""
        if tick_count == 0:
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
        return state.pc + 1

    def op_LoopIfFalse(self, state, operand, script_words, unit_id, tick_count, rng):
        """LoopIfFalse: jump back to pushed PC if cond_flags is false."""
        if not state.cond_flags and state.return_stack and len(state.return_stack[-1]) == 1:
            return state.return_stack[-1][0]
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
        state.cond_flags = 1
        return state.pc + 1

    def op_TargetValid(self, state, operand, script_words, unit_id, tick_count, rng):
        """TargetValid: test if current target is still valid."""
        # Simplified: assume target is valid
        state.cond_flags = 1 if state.current_target else 0
        return state.pc + 1

    def op_KeepThreat(self, state, operand, script_words, unit_id, tick_count, rng):
        """KeepThreat: keep current threat (don't search for new one)."""
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
        """MoveToNode N: move to waypoint node N (TODO: integrate with movement)."""
        if operand is not None:
            state.current_node = operand
        return state.pc + 1

    def op_FaceNode(self, state, operand, script_words, unit_id, tick_count, rng):
        """FaceNode N: turn to face waypoint node N (TODO: integrate with movement)."""
        return state.pc + 1

    def op_ChargeTarget(self, state, operand, script_words, unit_id, tick_count, rng):
        """ChargeTarget: charge the current target (TODO: integrate with combat)."""
        return state.pc + 1

    def op_FireAtTarget(self, state, operand, script_words, unit_id, tick_count, rng):
        """FireAtTarget: shoot at the current target (TODO: integrate with combat)."""
        return state.pc + 1

    def op_KillAllModels(self, state, operand, script_words, unit_id, tick_count, rng):
        """KillAllModels: instantly remove all models from this unit (TODO: integrate with combat)."""
        # Used in BF001 for conditional tutorial difficulty scaling
        return state.pc + 1

    def op_AttackTagged(self, state, operand, script_words, unit_id, tick_count, rng):
        """AttackTagged TAG: attack the unit marked with TAG (TODO: implement tagging)."""
        return state.pc + 1

    def op_SetTag(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetTag TAG: mark this unit with a tag (TODO: implement tagging)."""
        return state.pc + 1

    def op_SetBehaviour(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetBehaviour N: set explicit behavior (e.g., 15=TrackThreat).

        Instead of gosub to library script, applies the behavior inline.
        Behavior 15 (TrackThreat) is the most common.
        """
        if operand == 15:  # TrackThreat
            self.behaviors.track_threat(unit_id, state, tick_count, self.battle.rng)
        return state.pc + 1

    def op_React(self, state, operand, script_words, unit_id, tick_count, rng):
        """React N: display a battle message (1="Engage!", 2="CHARGE!", etc.)."""
        # TODO: call frontend to display message
        # Messages: 1="Engage!", 2="CHARGE!", 3="Destroy them!", 4="Retreat!", etc.
        return state.pc + 1

    def op_SetThreatRange(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetThreatRange N: set threat detection range (used by TrackThreat)."""
        if operand is not None:
            state.threat_range = operand
        return state.pc + 1

    def op_SetInterruptScript(self, state, operand, script_words, unit_id, tick_count, rng):
        """SetInterruptScript N: set interrupt handler script."""
        if operand is not None:
            state.interrupt_script = operand
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
        """IfEventSource: test if current event came from a specific source."""
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

    # For any other opcode not explicitly handled, the dispatcher will raise NotImplementedError,
    # which is caught and logged by the run() method, allowing partial mission execution.
