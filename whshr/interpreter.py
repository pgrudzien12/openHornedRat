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

from . import animation, behaviour, magic, nodes, visibility
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
WIZARD_CLASS = 5  # s_race class Wizard (game_rules.md section 3)
TRACK_THREAT = 15  # SetBehaviour code of the standard threat-tracking AI (notes/script_queries.md 12.1)
CAST_ONLY_TARGET_FLAG = 0x4000000  # SetUnitFlags operand: CastPending drops the target after the cast
LEAVING_BATTLE_FLAG = 0x100  # SetUnitFlags 256: the unit is leaving the battle (objective G, game_rules.md R60)
VIEW_CONE = 71  # +-50 degrees in 1/512 turn, doubled while the looker is in melee (game_rules.md visibility)
REACT_VIEW_CONE = 85  # ReactToThreat's wider +-60 degrees (notes/threat_events_nodes.md, part A 6)
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
    # The posting model's index for an animation event (notes/script_shooting.md 0: the launching model), or -1.
    model: int = -1


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
    # The "enemy I am worried about", separate from the current target, and its stored score
    # (notes/threat_events_nodes.md, part A 0).
    threat: str | None = None
    threat_score: float = 0.0
    approach_point: tuple[float, float] | None = None  # set by ReactToThreat; see op_ReactToThreat
    # Animation request: the event the models post at their animation's event step, every divisor-th
    # arrival, while the countdown runs (notes/script_animation_sound.md, 0.3).
    anim_event: int = 0
    anim_divisor: int = 0
    anim_countdown: int = 0
    loop_sound: tuple[int, int] | None = None  # (packet, effect) started by StartUnitLoopSound
    # Casting states (notes/script_animation_sound.md, 3): a spell chosen but not yet launched, and the
    # caster of an active Storm of Shemtek or Flying Bower. Set by the magic opcodes and spell effects.
    pending_spell: int | None = None
    channelling: bool = False
    # Magic aim (notes/script_magic.md 0.1): a ground point (None = unset) and whether CastPending aims at it
    # even though a current target exists.
    target_point: tuple[float, float] | None = None
    aim_at_point: bool = False
    current_node: int | None = None  # waypoint node for movement orders
    pending_arrival: bool = False  # a MoveToNode order is in flight; see
    # ScriptInterpreter._update_arrival_flag, which sets ARRIVED_FLAG on unit_flags once the
    # regiment stops moving, so a WaitUntilUnitFlags(ARRIVED_FLAG) loop can unblock
    behaviour_id: int | None = None  # periodic behaviour code declared by SetBehaviour (0 or None = none)
    behaviour_period: int = 0  # SetBehaviour's period P; 0 disables the periodic decision
    behaviour_countdown: int = 0  # updates left before the next decision (notes/deployment.md 5.3)
    charge_sound: tuple[int, int] | None = None  # (packet, effect) of the running charge sound (Query 24)
    # A passed fear test spares further fear tests until the next charge clears it (game_rules.md "Fear and
    # terror"; notes/script_grid_events.md 0).
    fear_passed: bool = False
    # The last unit this one was recorded touching, and the one-tick contact latch that stops further contact
    # events until the handler or a clear step releases it (notes/script_behaviours.md 2.1, 2.5).
    contact_record: str | None = None
    contact_latch: bool = False
    hop_counter: int = 0  # squig hops left before a rest (FanaticJump/FanaticRelease, notes/script_spawn_move.md 1)
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
        self._power: magic.PowerPools | None = None

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

    @property
    def power(self) -> magic.PowerPools:
        """The battle's power pools, rolled 1-8 each on first use (game_rules.md "Winds of magic")."""
        if self._power is None:
            self._power = magic.PowerPools.rolled(self.battle.rng)
        return self._power

    def animation_event_step(self, unit_id: str, model_index: int = -1) -> None:
        """A model of the unit reached its animation's event step: count the request down and post its
        event to the unit when the new countdown is divisible by the divisor; nothing with no request
        running (notes/script_animation_sound.md, 0.3)."""
        state = self.unit_states.get(unit_id)
        if state is None or state.anim_countdown <= 0:
            return
        state.anim_countdown -= 1
        if state.anim_divisor and state.anim_countdown % state.anim_divisor == 0:
            self.queue_event(unit_id, Event(code=state.anim_event, source=unit_id, model=model_index))

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


# React N per (code, race = s_race & 7): GMTXT id, speech packet, effect, marker ("P" not for enemy units, "E" also
# off screen). Data from notes/script_behaviours.md 3.3; the texts themselves load from the installation.
def _react_rows() -> dict[tuple[int, int], tuple[int, int, int, str]]:
    human_elf_dwarf = {
        5: (34106, 5, 10, ""), 10: (34108, 5, 3, ""), 11: (34109, 5, 4, "P"), 12: (34110, 5, 8, "P"),
        14: (34112, 5, 5, "P"), 15: (1006, 10, 0, "P"), 16: (1007, 3, 5, "P"), 19: (34115, 5, 16, ""),
    }
    rows: dict[tuple[int, int], tuple[int, int, int, str]] = {}
    for race in (0, 1, 2):
        for code, entry in human_elf_dwarf.items():
            rows[(code, race)] = entry
    rows.update({
        (1, 0): (34105, 5, 14, "P"), (1, 1): (34105, 5, 14, "P"), (1, 2): (34208, 7, 7, ""),
        (2, 0): (34102, 5, 0, "P"), (2, 1): (34102, 5, 0, "P"), (2, 2): (34102, 7, 1, ""),
        (3, 0): (34100, 5, 2, ""), (3, 1): (34101, 5, 2, ""), (3, 2): (34209, 7, 8, ""),
        (4, 0): (34103, 5, 1, ""), (4, 1): (34104, 5, 1, ""), (4, 2): (34104, 7, 2, ""),
        (6, 0): (34107, 5, 11, ""), (6, 1): (34107, 0, 0, ""), (6, 2): (34107, 0, 0, ""),
        (7, 2): (34200, 7, 5, ""), (8, 0): (34113, 5, 17, ""), (8, 2): (34202, 7, 9, ""),
        (13, 0): (34111, 5, 6, "P"), (13, 1): (34111, 5, 6, "P"), (13, 2): (34203, 7, 0, "P"),
        (17, 0): (34114, 5, 13, ""), (17, 1): (34114, 5, 13, ""), (17, 2): (34204, 7, 6, ""),
        (18, 2): (34205, 11, 1, ""), (20, 2): (34201, 16, 0, ""),
        (1, 3): (34000, 0, 0, ""), (1, 4): (34000, 0, 0, ""),
        (2, 3): (34002, 6, 4, ""), (2, 4): (34002, 6, 2, ""), (2, 5): (34302, 8, 0, ""), (2, 7): (34400, 9, 2, ""),
        (3, 3): (34001, 6, 3, ""), (3, 4): (34001, 6, 1, ""), (3, 5): (34302, 8, 3, ""), (3, 7): (34400, 9, 2, ""),
        (4, 3): (34003, 6, 9, ""), (4, 4): (34003, 6, 8, ""), (4, 5): (34301, 8, 1, ""), (4, 7): (34401, 9, 0, ""),
        (5, 3): (34004, 0, 0, ""), (5, 4): (34004, 0, 0, ""), (6, 3): (34005, 0, 0, ""), (6, 4): (34005, 0, 0, ""),
        (8, 3): (34006, 0, 0, ""), (8, 4): (34006, 0, 0, ""), (9, 5): (34300, 0, 0, ""),
        (18, 5): (34303, 15, 0, "E"),
    })
    return rows


_REACT_TABLE = _react_rows()
# Leader portrait expression per React code 0-20 (all races).
_REACT_EXPRESSIONS = (0, 2, 0, 1, 4, 2, 2, 1, 2, 2, 0, 2, 2, 2, 2, 3, 2, 1, 3, 1, 2)


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

    def raise_contacts(self, contacts: list[tuple["Regiment", "Regiment"]]) -> None:
        """The collision pass with scripts running (notes/script_behaviours.md 2.2): for each touching pair, a unit
        that moved or charged this tick (PROVISIONAL stand-in for the collision re-check state) runs the
        fear-on-contact test and, unless latched, gets event 0x0B (checked) with the other unit as its contact
        record; a troops regiment touched gets the reciprocal 0x0B. Marked units are not touched at all. A latched
        unit that touches nothing any more is released. Not modelled: push-apart (the engine's own), contact
        attacks on routers, wagon event 0x27 and the latched-move rollback."""
        touching: set[str] = set()
        for first, second in contacts:
            if self._leaving(first) or self._leaving(second):
                continue
            touching.update((first.identifier, second.identifier))
            if first.melee_group is not None and first.melee_group == second.melee_group:
                continue
            for mover, other in ((first, second), (second, first)):
                if not self._rechecks(mover):
                    continue
                self._contact_fear(mover, other)
                self._record_contact(mover, other)
                if not (other.is_wagon or other.hud_class in ("art", "mon")):
                    self._record_contact(other, mover)
        for unit_id, state in self.event_bus.unit_states.items():
            if state.contact_latch and unit_id not in touching:
                state.contact_latch = False

    @staticmethod
    def _rechecks(unit: "Regiment") -> bool:
        """PROVISIONAL collision re-check state: the unit moved, charged or pursued this tick."""
        return unit.moving or bool(unit.waypoints) or unit.attack_target is not None

    def _contact_fear(self, mover: "Regiment", other: "Regiment") -> None:
        state = self.event_bus.unit_states.get(mover.identifier)
        if state is None or mover.routing or not self._hostile(mover, other) or state.fear_passed:
            return
        if not self._may_engage(mover, other, state, self.battle.rng):
            state.current_target = (other.identifier, 0)
            self.event_bus.queue_event(mover.identifier, Event(code=0x0D), checked=True)

    def _record_contact(self, unit: "Regiment", other: "Regiment") -> None:
        state = self.event_bus.unit_states.get(unit.identifier)
        if state is None or state.contact_latch:
            return
        state.contact_record = other.identifier
        self.event_bus.queue_event(unit.identifier, Event(code=0x0B), checked=True)

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

        self._periodic_behaviour(unit_id, state)
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
        """game_rules.md: unit worth = size x s_pntval x 12 artillery / 8 wizard / 4 monster / 1, by the unit's
        current class (so SetClass changes it), falling back to the HUD class when the class is unknown."""
        by_class = {4: 12, 5: 8, 6: 4}
        if regiment.unit_class is not None:
            multiplier = by_class.get(regiment.unit_class, 1)
        else:
            multiplier = {"art": 12, "wiz": 8, "mon": 4}.get(regiment.hud_class or "", 1)
        return regiment.models * regiment.points * multiplier

    @staticmethod
    def _octagonal(unit: "Regiment", other: "Regiment") -> int:
        """Integer octagonal distance, half rounded up: max(|dx|, |dy|) + ceil(min / 2)
        (notes/script_queries.md 0.3)."""
        dx, dy = abs(int(other.x - unit.x)), abs(int(other.y - unit.y))
        return max(dx, dy) + (min(dx, dy) + 1) // 2

    def _pursuing(self, other: "Regiment") -> bool:
        """Chasing a routing unit (an attack target that is broken)."""
        chased = self.battle.regiments.get(other.attack_target) if other.attack_target is not None else None
        return chased is not None and chased.routing

    def _targets(self, other: "Regiment", unit_id: str) -> bool:
        """`other`'s current target (script slot or charge target) is the unit."""
        other_state = self.event_bus.unit_states.get(other.identifier)
        return other.attack_target == unit_id or (
            other_state is not None and other_state.current_target is not None
            and other_state.current_target[0] == unit_id)

    def _threat_score(self, regiment: "Regiment", other: "Regiment | None", threat_range: float) -> int:
        """UnitScore (notes/script_queries.md 0.3): 0 for none, a unit that is not hostile, in melee, broken
        or pursuing, or with R - d <= 0; else trunc(worth x (R - d) / trunc(R / 4)), x4 when it targets this
        unit, x32 instead when it is also charging. Kept as a signed 16-bit value, so the multiplications
        wrap as in the original (PROVISIONAL: never observed in play). Hidden units are not excluded here;
        the searches filter them."""
        if (other is None or not other.active or not self._hostile(regiment, other) or other.in_melee
                or other.routing or self._pursuing(other)):
            return 0
        reach = int(threat_range) - self._octagonal(regiment, other)
        divisor = int(threat_range) // 4
        if reach <= 0 or divisor <= 0:
            return 0
        score = self._unit_worth(other) * reach // divisor
        if self._targets(other, regiment.identifier):
            charging = other.attack_target is not None and not self._pursuing(other)
            score *= 32 if charging else 4
        return ((score + 0x8000) & 0xFFFF) - 0x8000

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
        It does reset the periodic behaviour countdown (notes/deployment.md 5.3).
        """
        state.behaviour_countdown = 0
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

        The mirror of WaitUntilUnitFlags: any bit of the mask (notes/script_behaviours.md 3.2). 8 = re-forming;
        0x4000 = the catch-up re-form walk, not modelled separately (it always comes with re-forming).
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

    def op_CaseEvent(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """CaseEvent N: a matching current event runs the arm (pc + 2); otherwise a raw word scan from the operand
        finds the first Break opcode word and continues after that Break and its label operand. Not
        nesting-aware; no condition (notes/script_behaviours.md 3.1)."""
        if operand is not None and state.current_event.code == operand:
            return state.pc + 2
        break_word = behaviour.OPCODE_FLAG | 0x6B
        for pc in range(state.pc + 1, len(script_words)):
            if script_words[pc] == break_word:
                return pc + 2
        return len(script_words)

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
        """The n-th nearest search shared by AttackNearestEnemy/-Visible/-Nth/-Flag40Unit. Success queues
        event 0x04 (source = the chosen unit) to the unit itself and leaves the current target to the
        0x04 handler (TakeEventTarget), as for the rest of the family (notes/threat_events_nodes.md,
        part A 4.1). PROVISIONAL: these members keep the engine's previous whole-field n-th ordering;
        only the part A members use the report's side sets and last-in-order tie-break."""
        if self.battle.phase == "deployment":
            state.cond_flags = 0
            return state.pc + 1
        regiment = self.battle.regiments.get(unit_id)
        if regiment is None:
            state.cond_flags = 0
            return state.pc + 1
        target_id = self._nearest_enemy_id(regiment, n, side=side, visible_only=visible_only)
        if target_id:
            self.event_bus.queue_event(unit_id, Event(code=0x04, source=target_id), route="self")
            state.cond_flags = 1
        else:
            state.cond_flags = 0
        return state.pc + 1

    # ===== Threat and target search (notes/threat_events_nodes.md, part A) =====

    @staticmethod
    def _hostile(unit: "Regiment", other: "Regiment") -> bool:
        """One is in the enemy army and the other in the player army or on the allied side (part A 0)."""
        return (unit.side == Side.ENEMY) != (other.side == Side.ENEMY)

    def _eligible(self, other: "Regiment") -> bool:
        """Active, not hidden, not broken and not leaving the battle (part A 0)."""
        if not other.active or other.hidden or other.routing:
            return False
        other_state = self.event_bus.unit_states.get(other.identifier)
        return other_state is None or not other_state.unit_flags & LEAVING_BATTLE_FLAG

    @staticmethod
    def _of_class(other: "Regiment", class_operand: int) -> bool:
        """Class operand = class x 8 as in s_race; 0 means any class (part A 0)."""
        return not class_operand or other.unit_class == class_operand >> 3

    def _sees(self, looker: "Regiment", other: "Regiment", half_cone: int = VIEW_CONE) -> bool:
        """IsVisible: view cone (doubled in melee), scenery and sight edges, no range."""
        return visibility.visible(
            self.battle.formation_centre(looker), looker.direction, self.battle.formation_centre(other),
            other.bounding_radius(), half_cone * 2 if looker.in_melee else half_cone,
            self.battle.boundaries, self.battle.objects)

    def _threat_search(self, unit: "Regiment") -> str | None:
        """Nearest facing threat: the nearest eligible hostile the unit sees within trunc(3R/8),
        inclusive, first in unit order on ties; none when that unit does not see the searcher
        (no fallback). Part A 1.1."""
        radius = math.trunc(self._weapon_range(unit) * 3 / 8)
        best: "Regiment | None" = None
        best_distance = 0
        for other in self.battle.regiments.values():
            if other is unit or not self._eligible(other) or not self._hostile(unit, other):
                continue
            distance = self._distance(unit, other)
            if distance <= radius and (best is None or distance < best_distance) and self._sees(unit, other):
                best, best_distance = other, distance
        return best.identifier if best is not None and self._sees(best, unit) else None

    def op_FindThreatNear(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FindThreatNear: threat slot := the nearest facing threat, cleared when none; condition true iff
        found. The current target is untouched (part A 1.2)."""
        unit = self.battle.regiments.get(unit_id)
        state.threat = self._threat_search(unit) if unit is not None else None
        state.cond_flags = state.threat is not None
        return state.pc + 1

    def op_FindNewThreatNear(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FindNewThreatNear: store the search result only when found and different from the slot;
        condition true iff the slot changed. A failed search keeps the slot (part A 1.2)."""
        unit = self.battle.regiments.get(unit_id)
        found = self._threat_search(unit) if unit is not None else None
        changed = found is not None and found != state.threat
        if changed:
            state.threat = found
        state.cond_flags = changed
        return state.pc + 1

    def op_KeepThreat(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """KeepThreat: keep the threat while it is closer than trunc(5R/8) (strict) and sees the unit,
        else clear it; condition true iff kept. No hostility, broken or hidden re-check (part A 1.2)."""
        unit = self.battle.regiments.get(unit_id)
        threat = self.battle.regiments.get(state.threat) if state.threat is not None else None
        kept = (unit is not None and threat is not None and threat.active
                and self._distance(unit, threat) < math.trunc(self._weapon_range(unit) * 5 / 8)
                and self._sees(threat, unit))
        if not kept:
            state.threat = None
        state.cond_flags = kept
        return state.pc + 1

    def _crowded_by_friend(self, unit: "Regiment", candidate: "Regiment") -> bool:
        """An independent unit skips a candidate when another friendly unit's centre lies within its
        footprint radius + 24 of the aim point (candidate x, searcher y) -- the report's quirk.
        Not modelled: blast radii above 24 (part A 2.1 step 4)."""
        aim_x, aim_y = candidate.x, unit.y
        return any(other is not unit and other is not candidate and other.active and not self._hostile(unit, other)
                   and math.hypot(other.x - aim_x, other.y - aim_y) < other.bounding_radius() + 24
                   for other in self.battle.regiments.values())

    def _weapon_target_search(self, unit: "Regiment", class_operand: int, limited: bool) -> str | None:
        """Nearest shootable unit: eligible hostile of the class, d > 0, d <= R when limited, the
        independent crowding check; first in order on ties; no visibility or arc (part A 2.1)."""
        best: "Regiment | None" = None
        best_distance = 0
        for other in self.battle.regiments.values():
            if (other is unit or not self._eligible(other) or not self._hostile(unit, other)
                    or not self._of_class(other, class_operand)):
                continue
            distance = self._distance(unit, other)
            if distance == 0 or (limited and distance > self._weapon_range(unit)):
                continue
            if best is not None and distance >= best_distance:
                continue
            if unit.independent and self._crowded_by_friend(unit, other):
                continue
            best, best_distance = other, distance
        return best.identifier if best is not None else None

    def _find_target(self, state: UnitScriptState, unit_id: str, class_operand: int, limited: bool) -> None:
        """FindTarget family: target := the result, cleared when none; condition true iff found (part A 2.2)."""
        unit = self.battle.regiments.get(unit_id)
        found = self._weapon_target_search(unit, class_operand, limited) if unit is not None else None
        state.current_target = (found, 0) if found is not None else None
        state.cond_flags = found is not None

    def op_FindTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FindTarget: nearest shootable unit within weapon range (part A 2.2)."""
        self._find_target(state, unit_id, 0, limited=True)
        return state.pc + 1

    def op_FindTargetOfClass(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FindTargetOfClass C: as FindTarget, of class C (part A 2.2)."""
        self._find_target(state, unit_id, operand or 0, limited=True)
        return state.pc + 2

    def op_FindTargetAnyRange(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FindTargetAnyRange: nearest shootable unit, no range limit (part A 2.2)."""
        self._find_target(state, unit_id, 0, limited=False)
        return state.pc + 1

    def op_FindTargetOfClassAnyRange(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """FindTargetOfClassAnyRange C: nearest shootable unit of class C, no range limit (part A 2.2)."""
        self._find_target(state, unit_id, operand or 0, limited=False)
        return state.pc + 2

    def op_FindNewTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FindNewTarget: within weapon range; stores the result only when it differs from the current
        target, condition true iff it changed; a failed search keeps the target (part A 2.2)."""
        unit = self.battle.regiments.get(unit_id)
        found = self._weapon_target_search(unit, 0, limited=True) if unit is not None else None
        current = state.current_target[0] if state.current_target else None
        changed = found is not None and found != current
        if changed and found is not None:
            state.current_target = (found, 0)
        state.cond_flags = changed
        return state.pc + 1

    def _nearest_pick(self, unit: "Regiment", class_operand: int) -> str | None:
        """Nearest enemy over the whole field: eligible hostile of the class, no range, visibility or
        d = 0 exclusion; first in order on ties (part A 3.1)."""
        best: "Regiment | None" = None
        best_distance = 0
        for other in self.battle.regiments.values():
            if (other is unit or not self._eligible(other) or not self._hostile(unit, other)
                    or not self._of_class(other, class_operand)):
                continue
            distance = self._distance(unit, other)
            if best is None or distance < best_distance:
                best, best_distance = other, distance
        return best.identifier if best is not None else None

    def _target_nearest(self, state: UnitScriptState, unit_id: str, class_operand: int) -> None:
        unit = self.battle.regiments.get(unit_id)
        found = self._nearest_pick(unit, class_operand) if unit is not None else None
        if found is not None:
            state.current_target = (found, 0)
        state.cond_flags = found is not None

    def op_TargetNearestEnemy(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """TargetNearestEnemy: target := the nearest enemy, condition true; none keeps the target, false
        (part A 3.2)."""
        self._target_nearest(state, unit_id, 0)
        return state.pc + 1

    def op_TargetNearestEnemyOfClass(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """TargetNearestEnemyOfClass C: as TargetNearestEnemy, of class C (part A 3.2)."""
        self._target_nearest(state, unit_id, operand or 0)
        return state.pc + 2

    def op_RetargetNearestEnemy(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """RetargetNearestEnemy: store the nearest enemy only when it differs from the target; condition
        true iff it changed (part A 3.2)."""
        unit = self.battle.regiments.get(unit_id)
        found = self._nearest_pick(unit, 0) if unit is not None else None
        current = state.current_target[0] if state.current_target else None
        changed = found is not None and found != current
        if changed and found is not None:
            state.current_target = (found, 0)
        state.cond_flags = changed
        return state.pc + 1

    def _in_side_set(self, unit: "Regiment", other: "Regiment", main_only: bool) -> bool:
        """Part A 4.1 step 2. Enemy set: a player searcher takes enemy and allied units, an enemy searcher
        player and allied units, an allied searcher enemy units. Main: the opposing army only."""
        if main_only:
            return other.side == (Side.PLAYER if unit.side == Side.ENEMY else Side.ENEMY)
        if unit.side == Side.NEUTRAL:
            return other.side == Side.ENEMY
        return other.side != unit.side and other.side in (Side.PLAYER, Side.ENEMY, Side.NEUTRAL)

    def _attack_pick(self, state: UnitScriptState, unit_id: str, class_operand: int = 0, by_axis: bool = False,
                     main_only: bool = False, visible_only: bool = False) -> None:
        """The attack-the-nearest routine: false in deployment; smallest key (distance, or the signed axis
        key min(Sx - Cx, Sy - Cy)) wins, ties to the LAST in unit order; queues event 0x04 (source = the
        pick) to the unit itself and leaves the current target alone (part A 4.1)."""
        unit = self.battle.regiments.get(unit_id)
        if self.battle.phase == "deployment" or unit is None:
            state.cond_flags = False
            return
        best: "Regiment | None" = None
        best_key = 0.0
        for other in self.battle.regiments.values():
            if (other is unit or not self._eligible(other) or not self._in_side_set(unit, other, main_only)
                    or not self._of_class(other, class_operand)):
                continue
            if visible_only and not self._sees(unit, other):
                continue
            key = (min(unit.x - other.x, unit.y - other.y) if by_axis else self._distance(unit, other))
            if best is None or key <= best_key:
                best, best_key = other, key
        if best is not None:
            self.event_bus.queue_event(unit_id, Event(code=0x04, source=best.identifier))
        state.cond_flags = best is not None

    def op_AttackNearestEnemyOfClass(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """AttackNearestEnemyOfClass C (part A 4)."""
        self._attack_pick(state, unit_id, class_operand=operand or 0)
        return state.pc + 2

    def op_AttackNearestEnemyByAxis(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """AttackNearestEnemyByAxis: prefers the candidate furthest towards +X or +Y (part A 4)."""
        self._attack_pick(state, unit_id, by_axis=True)
        return state.pc + 1

    def op_AttackNearestVisibleEnemyByAxis(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """AttackNearestVisibleEnemyByAxis: the axis pick among the units the searcher sees (part A 4)."""
        self._attack_pick(state, unit_id, by_axis=True, visible_only=True)
        return state.pc + 1

    def op_AttackNearestMainEnemy(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """AttackNearestMainEnemy: nearest unit of the opposing army, allied units excluded (part A 4)."""
        self._attack_pick(state, unit_id, main_only=True)
        return state.pc + 1

    def op_AttackNearestVisibleMainEnemy(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """AttackNearestVisibleMainEnemy: as AttackNearestMainEnemy among the units it sees (part A 4)."""
        self._attack_pick(state, unit_id, main_only=True, visible_only=True)
        return state.pc + 1

    def op_AttackUnitAtNode(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """AttackUnitAtNode N: attack the building at node N (part A 5). Not modelled: buildings are not
        units in this engine, so the search never finds one and the condition is false; anchored or
        held units fail first as in the report."""
        state.cond_flags = False
        return state.pc + 2

    def op_ReactToThreat(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """ReactToThreat: switch to the stored threat when it strictly outscores the current target and the
        unit sees it within +-60 degrees (part A 6). In melee the unit withdraws, which routs it (Not
        modelled: the disengage from rolling stock or furniture). Otherwise target := threat, slot cleared,
        and the approach point -- one footprint radius out from the threat on the side the unit comes
        from -- is recorded in `approach_point` (PROVISIONAL: the engine's route is not edited; the
        attack script's own movement aims at the target). A threat charging this unit queues event 0x07
        and leaves the condition false."""
        state.cond_flags = False
        unit = self.battle.regiments.get(unit_id)
        threat = self.battle.regiments.get(state.threat) if state.threat is not None else None
        if self.battle.phase == "deployment" or unit is None or threat is None:
            return state.pc + 1
        if unit.attack_target is not None or unit.routing or unit.braced or "CantMelee" in threat.psychology:
            return state.pc + 1
        current = self.battle.regiments.get(state.current_target[0]) if state.current_target else None
        current_score = (self._threat_score(unit, current, state.threat_range)
                         if current is not None and state.threat_range > 0 else 0.0)
        if not current_score < state.threat_score or not self._sees(unit, threat, REACT_VIEW_CONE):
            return state.pc + 1
        if unit.in_melee:
            from . import combat
            combat.start_rout(unit, self.battle)
            return state.pc + 1
        state.current_target = (threat.identifier, 0)
        state.threat = None
        state.approach_point = self._approach_point(unit, threat)
        if threat.attack_target == unit_id:
            self.event_bus.queue_event(unit_id, Event(code=0x07, source=threat.identifier))
        else:
            state.cond_flags = True
        return state.pc + 1

    def _approach_point(self, unit: "Regiment", threat: "Regiment") -> tuple[float, float]:
        """One footprint radius out from the threat's centre on its front, right, rear or left side,
        whichever faces the unit (PROVISIONAL sector boundaries: 90 degrees centred on each side)."""
        relative = (self._bearing(threat, unit) - int(threat.direction)) % 512
        side = ((relative + 64) // 128) % 4 * 128 + int(threat.direction)
        angle = side * math.tau / 512
        radius = threat.bounding_radius()
        return threat.x + radius * math.sin(angle), threat.y + radius * math.cos(angle)

    def op_ReactEnemySpotted(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """ReactEnemySpotted: the "enemy sighted" bark of a unit that spotted a hidden enemy, only for units
        not in the enemy army; no condition, target or threat change (part A 7). Not modelled: the bark
        itself (no React speech table for it yet), so this is a no-op."""
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
        unit.pursuing, unit.pursuit_budget, unit.pursuit_point = False, None, None
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
        """MoveToTarget: walk to the target unit's object centre (the target point is ignored). Refused (false)
        with no target unit, while re-forming, anchored or held (notes/movement_formation.md 3.1,
        notes/script_spawn_move.md 6). The destination is fixed until re-issued or re-aimed by
        IfTargetInChargeReach/ApproachTargetInReach. PROVISIONAL: the original follows the unit and never
        ends this move by distance; this engine's ordinary arrival rule still applies (it posts no 0x34)."""
        pair = self._query_pair(state, unit_id)
        unit = pair[0] if pair else None
        state.cond_flags = False
        if pair is None or unit is None or unit.reforming or unit.anchored or unit.held or unit.routing:
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

    def op_TargetValid(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """TargetValid: is it safe to shoot at the aim point (the target's position, or the target point when
        there is no target or aim-at-point is on)? An independent unit refuses when another friendly unit's
        centre is within its footprint radius + 24 of the aim point; a crossbow unit (missile code 2) refuses
        when a non-hostile unit stands on the line of fire. No range, arc or broken test
        (target_queries.md section 3). PROVISIONAL: blast radii above 24 are not modelled, and the line test
        is "the segment passes within the unit's footprint radius"."""
        unit = self.battle.regiments.get(unit_id)
        target = self.battle.regiments.get(state.current_target[0]) if state.current_target else None
        aim = ((target.x, target.y) if target is not None and not state.aim_at_point else state.target_point)
        if unit is None or aim is None:
            state.cond_flags = False
            return state.pc + 1
        friends = [other for other in self.battle.regiments.values()
                   if other is not unit and other is not target and other.active and not self._hostile(unit, other)]
        crowded = unit.independent and any(
            math.hypot(other.x - aim[0], other.y - aim[1]) < other.bounding_radius() + 24 for other in friends)
        blocked = unit.missile_code == 2 and any(
            self._segment_distance((unit.x, unit.y), aim, (other.x, other.y)) < other.bounding_radius()
            for other in friends)
        state.cond_flags = not (crowded or blocked)
        return state.pc + 1

    @staticmethod
    def _segment_distance(start: tuple[float, float], end: tuple[float, float], point: tuple[float, float]) -> float:
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = dx * dx + dy * dy
        t = 0.0 if length == 0 else max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length))
        return math.hypot(point[0] - start[0] - t * dx, point[1] - start[1] - t * dy)

    def op_IfThreatOutweighsWorth(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """IfThreatOutweighsWorth: condition := the threat slot holds a unit whose UnitScore, recomputed now,
        is strictly above the unit's own worth. No scan, nothing else written (notes/script_queries.md 12.1)."""
        unit = self.battle.regiments.get(unit_id)
        threat = self.battle.regiments.get(state.threat) if state.threat is not None else None
        state.cond_flags = (unit is not None and threat is not None
                            and self._threat_score(unit, threat, state.threat_range) > self._unit_worth(unit))
        return state.pc + 1

    def op_TargetGone(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """TargetGone: when the current event comes from the current target: outside melee queue 0x19 to
        itself (false); in melee switch to another engaged enemy (false) or, with none, leave the grid
        (true). Any other case is false (notes/script_queries.md B5)."""
        unit = self.battle.regiments.get(unit_id)
        gone = state.current_event.source
        state.cond_flags = False
        if unit is None or state.current_target is None or gone is None or state.current_target[0] != gone:
            return state.pc + 1
        if not unit.in_melee:
            self.event_bus.queue_event(unit_id, Event(code=0x19))
        elif not self._switch_opponent(state, unit, gone):
            self._leave_grid(unit)
            state.cond_flags = True
        return state.pc + 1

    def op_TakeEventTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """TakeEventTarget (0x3A, 0x88, 0xAF; notes/script_grid_events.md 1.2). Nothing in deployment (false).
        Otherwise the pending spell always becomes the event's argument (<= 0 = none). With a source unit: refused
        (false) while the taker is charging, in melee, broken or pursuing, and by 0x3A also for a broken source;
        accepted -> braced off, target := source, aim point recorded, true. Without a source: an item-marked
        argument keeps an existing target, else target := none and target point := the event point; true.
        PROVISIONAL: the aim point goes to `approach_point` instead of replacing the final waypoint, because the
        engine starts moving when its route changes and this opcode must not start a move."""
        if self.battle.phase == "deployment":
            state.cond_flags = False
            return state.pc + 1
        event = state.current_event
        state.pending_spell = event.parameter if event.parameter > 0 else None
        unit = self.battle.regiments.get(unit_id)
        source = self.battle.regiments.get(event.source) if event.source is not None else None
        if source is not None and unit is not None:
            refuses_broken = behaviour.opcode_of(script_words[state.pc]) == 0x3A if state.pc < len(script_words) else True
            if (unit.attack_target is not None or unit.in_melee or unit.routing
                    or (refuses_broken and source.routing)):
                state.cond_flags = False
                return state.pc + 1
            unit.braced, unit.braced_target = False, None
            state.current_target = (source.identifier, 0)
            aim = self._charge_aim_point(unit, source)
            state.approach_point = (float(aim[0]), float(aim[1]))
            state.cond_flags = True
            return state.pc + 1
        item_marked = event.parameter < 0 or bool(event.parameter & 256)
        if not (item_marked and state.current_target is not None):
            state.current_target = None
            state.target_point = (float(event.x), float(event.y)) if event.x >= 0 and event.y >= 0 else None
        state.cond_flags = True
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

    def op_ScatterModelsToNode(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """ScatterModelsToNode N: send each model in formation to its own point around node id N
        (notes/scatter_models_to_node.md; corrections in notes/script_spawn_move.md 8). A model is in
        formation when it is not scattered or has arrived exactly at its scatter destination; a model still
        walking is skipped. Each scattered model also requests action 2. The condition is not written.
        Deterministic: draws from Battle.rng like every other random decision in the engine."""
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
                    model.own_request = animation.IDLE
        return state.pc + 2

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
                state.fear_passed = False  # a new charge clears it (notes/script_grid_events.md 0)
                # Battle.tick() handles the actual charging movement
        return state.pc + 1

    def op_FireAtTarget(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FireAtTarget: launch one shot now (notes/script_shooting.md 1.1) from the model that posted the current
        event (the unit centre with none) at the current target's centre, or at the target point when there is
        no live target or aim-at-point is on. No range, arc, reload or line test: those were the script's before
        the volley. A failed launch falls back to the 90 % shot; the condition is true only when the first
        launch worked. Afterwards aim-at-point is off and a unit that forgets its target after a shot drops it."""
        unit = self.battle.regiments.get(unit_id)
        state.cond_flags = False
        if unit is not None:
            point = self._shot_point(state, use_aim_flag=True)
            if point is not None:
                from . import ranged
                origin = self._launch_origin(unit, state.current_event.model)
                state.cond_flags = ranged.launch_shot(self.battle, unit, origin, point) != "failed"
                if not state.cond_flags:
                    self._launch_90(unit, origin, point)
        state.aim_at_point = False
        if state.unit_flags & CAST_ONLY_TARGET_FLAG:
            state.current_target = None
        return state.pc + 1

    def _shot_point(self, state: UnitScriptState, use_aim_flag: bool) -> tuple[float, float] | None:
        """The current target's centre (unless aim-at-point is on and consulted), else the target point."""
        target = self.battle.regiments.get(state.current_target[0]) if state.current_target else None
        if target is not None and target.active and not (use_aim_flag and state.aim_at_point):
            return target.x, target.y
        return state.target_point

    def _launch_origin(self, unit: "Regiment", model_index: int) -> tuple[float, float]:
        """The launching model's position, or the unit centre for "no model" or an index past the models."""
        positions = unit.model_positions()
        if 0 <= model_index < len(positions):
            return positions[model_index]
        return unit.x, unit.y

    def _launch_90(self, unit: "Regiment", origin: tuple[float, float], point: tuple[float, float]) -> bool:
        """Launch90 (notes/script_shooting.md 2.2): needs the +-45 degree front arc; aims exactly at
        trunc(0.9 R) along the line from the unit centre to `point` (truncating per axis)."""
        from . import ranged
        code = unit.shooting_code or unit.missile_code or 0
        weapon = ranged.WEAPONS.get(code) or ranged.SPECIAL.get(code)
        distance = int(math.hypot(point[0] - unit.x, point[1] - unit.y))
        if weapon is None or distance == 0 or not self._arc_ok(unit, point[0], point[1], 64):
            return False
        reach = weapon.reach * 9 // 10
        aim = (unit.x + int((point[0] - unit.x) * reach / distance), unit.y + int((point[1] - unit.y) * reach / distance))
        return ranged.launch_shot(self.battle, unit, origin, aim) != "failed"

    def op_FireAt90PercentRange(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """FireAt90PercentRange: Launch90 at the current target's centre (aim-at-point not consulted) or the
        target point; condition := launched. Neither the aim flag nor the target is changed
        (notes/script_shooting.md 2.1)."""
        unit = self.battle.regiments.get(unit_id)
        point = self._shot_point(state, use_aim_flag=False)
        state.cond_flags = (unit is not None and point is not None
                            and self._launch_90(unit, self._launch_origin(unit, state.current_event.model), point))
        return state.pc + 1

    def op_FireAtNode(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FireAtNode N: queue the ground-fire event 0x21 (no source, at map node N by file position) to the unit
        itself; its shooter handler takes the point and runs the one-attempt shot next tick. Condition := queued
        (notes/script_shooting.md 3). PROVISIONAL: a missing node queues nothing (false)."""
        node = operand or 0
        state.cond_flags = 0 <= node < len(self.battle.script_nodes)
        if state.cond_flags:
            area = self.battle.script_nodes[node]
            self.event_bus.queue_event(unit_id, Event(code=0x21, x=int(area.x), y=int(area.y)))
        return state.pc + 2

    def _manned(self, unit: "Regiment") -> bool:
        """Artillery class with its machine and at least 2 models (notes/script_shooting.md 0)."""
        return (unit.unit_class == 4 or unit.hud_class == "art") and unit.machine_alive and unit.models >= 2

    def op_IfArtilleryManned(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """IfArtilleryManned TAG: the unit carrying TAG (itself for a negative operand) is manned artillery
        (notes/script_shooting.md 4). PROVISIONAL: "negative" is read as the word -1 (0xFFFF), because the shipped
        tags 0xABC1/0xABC8 are themselves negative as 16-bit values."""
        tag = operand or 0
        unit_ref = unit_id if tag == 0xFFFF else self.event_bus.find_by_tag(tag)
        unit = self.battle.regiments.get(unit_ref) if unit_ref is not None else None
        state.cond_flags = unit is not None and self._manned(unit)
        return state.pc + 2

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

    def op_SnapModelsToFormation(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """SnapModelsToFormation: place every model at its current target and mark it in formation
        (notes/script_spawn_move.md 8.2). Right after a scatter that target is the scatter destination, so the
        shipped `ScatterModelsToNode; SnapModelsToFormation` pair puts the models on their scattered points at
        once; the next scatter pass then re-scatters them all."""
        regiment = self.battle.regiments.get(unit_id)
        if regiment:
            positions = regiment.model_positions()
            for index, model in enumerate(regiment.melee_models):
                if model.scatter_target is not None and index < len(positions):
                    positions[index] = model.scatter_target
                model.at_rest = True
        return state.pc + 1

    def op_SetBehaviour(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SetBehaviour CODE P: store the periodic behaviour and its period and reset the countdown, so the
        first decision comes at the next update (notes/deployment.md 5.3)."""
        state.behaviour_id = operand
        state.behaviour_period = script_words[state.pc + 2] if state.pc + 2 < len(script_words) else 0
        state.behaviour_countdown = 0
        return state.pc + 3

    def _periodic_behaviour(self, unit_id: str, state: UnitScriptState) -> None:
        """At the start of a script update: a zero countdown makes the decision due and reloads it with P
        (the behaviour itself is skipped during deployment), a positive one only counts down; P = 0
        disables it (notes/deployment.md 5.3)."""
        if not state.behaviour_period:
            return
        if state.behaviour_countdown > 0:
            state.behaviour_countdown -= 1
            return
        state.behaviour_countdown = state.behaviour_period
        if self.battle.phase != "deployment" and state.behaviour_id:
            self._run_behaviour(unit_id, state, state.behaviour_id)

    def _run_behaviour(self, unit_id: str, state: UnitScriptState, code: int) -> None:
        """One periodic run of behaviour CODE (notes/script_behaviours.md part 1): the Query case of the same
        number with its result discarded, so the condition is never written; whatever it queues is handled in
        this same update."""
        unit = self.battle.regiments.get(unit_id)
        if unit is None:
            return
        saved = state.cond_bits
        if code == 11:
            self._detect_threat(unit, state)
        elif code == 12:
            self._objective_exit_signal(unit, state)
            self._detect_threat(unit, state)
        elif code == 13:
            self._spot(unit)
        elif code == 14:
            self._threat_in_reach(unit, state)
        elif code in (15, 16, 19, 20):
            if code in (19, 20):
                self._siege_exit(unit, state, check_broken=code == 19)
            if code in (16, 20):
                self._signal_threat(unit, state)
            self._track_threat(unit_id, state)
        elif code == 21:
            self._bombard_nearest(unit, state)
        elif code == 26:
            self._doomwheel_bolts(unit)
        elif code == 27:
            self._pestilent_breath(unit)
        elif 1 <= code <= 25:
            self.op_Query(state, code, [], unit_id, 0, self.battle.rng)
        state.cond_bits = saved

    def _spot(self, unit: "Regiment") -> None:
        """Reveal every hidden unit of the opposite army this unit sees; 0x1C to the spotter (source = the
        revealed unit) and 0x1D to the revealed unit (source = the spotter), both checked
        (notes/script_behaviours.md 1.0)."""
        for other in self.battle.regiments.values():
            if other.hidden and other.active and self._hostile(unit, other) and self._sees(unit, other):
                other.hidden = False
                self.event_bus.queue_event(unit.identifier, Event(code=0x1C, source=other.identifier), checked=True)
                self.event_bus.queue_event(other.identifier, Event(code=0x1D, source=unit.identifier), checked=True)

    def _detect_threat(self, unit: "Regiment", state: UnitScriptState) -> None:
        """Code 11 (notes/script_behaviours.md 1.3): spot; unless braced, a threat that targets this unit (any
        threat for an independent unit) closer than the threat range refreshes the stored score and queues 0x03;
        otherwise only an independent unit re-picks as Query 1. Not modelled: the Doomwheel rider (leader missile
        code 13), never combined with this code in shipped data."""
        self._spot(unit)
        if unit.braced:
            return
        threat = self.battle.regiments.get(state.threat) if state.threat is not None else None
        if (threat is not None and (self._targets(threat, unit.identifier) or unit.independent)
                and self._octagonal(unit, threat) < state.threat_range):
            state.threat_score = self._threat_score(unit, threat, state.threat_range)
            self.event_bus.queue_event(unit.identifier, Event(code=0x03, source=threat.identifier))
        elif unit.independent:
            state.threat, state.threat_score = self._best_threat(unit, state.threat_range)

    def _objective_exit_signal(self, unit: "Regiment", state: UnitScriptState) -> None:
        """Code 12 step 1: inside the active node whose id field is 99 while the battle state is 4 -> 0x36."""
        node = next((node for node in self.battle.script_nodes if node.active and node.node_id == 99), None)
        if (node is not None and self.battle.mission_state == 4
                and (unit.x - node.x) ** 2 + (unit.y - node.y) ** 2 <= node.radius ** 2):
            self.event_bus.queue_event(unit.identifier, Event(code=0x36))

    def _threat_in_reach(self, unit: "Regiment", state: UnitScriptState) -> None:
        """Code 14 (notes/script_behaviours.md 1.6): 0x03 when an enemy that is not hidden or marked is closer
        than the threat range. Not modelled: test 1, the contact attacks nearby chargers make on the unit."""
        if any(other.active and not other.hidden and self._hostile(unit, other) and not self._leaving(other)
               and self._octagonal(unit, other) < state.threat_range for other in self.battle.regiments.values()):
            self.event_bus.queue_event(unit.identifier, Event(code=0x03))

    def _signal_threat(self, unit: "Regiment", state: UnitScriptState) -> None:
        """Code 16's extra step: a threat closer than the threat range queues 0x33 (source = the threat), even
        when braced."""
        threat = self.battle.regiments.get(state.threat) if state.threat is not None else None
        if threat is not None and self._octagonal(unit, threat) < state.threat_range:
            self.event_bus.queue_event(unit.identifier, Event(code=0x33, source=threat.identifier))

    def _siege_exit(self, unit: "Regiment", state: UnitScriptState, check_broken: bool) -> None:
        """Codes 19/20 step 1: battle state 4, (19: not broken), inside node index 14 -> state 5, the global
        sound 11 and 0x38 to every live unit (notes/script_behaviours.md 1.8)."""
        if (self.battle.mission_state != 4 or (check_broken and unit.routing)
                or not self._in_node_area(unit, 14)):
            return
        self.battle.mission_state = 5
        self._sound(unit.identifier, "global", 0, 11, positional=False)
        for other_id in list(self.battle.regiments):
            self.event_bus.queue_event(other_id, Event(code=0x38), checked=True)

    def _bombard_nearest(self, unit: "Regiment", state: UnitScriptState) -> None:
        """Code 21 (the BF014 Dragon): ground fire 0x21 at the nearest player- or enemy-army unit (its own army
        included, allies excluded) closer than the threat range, first on ties (notes/script_behaviours.md 1.9)."""
        best: "Regiment | None" = None
        best_distance = 0
        for other in self.battle.regiments.values():
            if other is unit or not other.active or other.side not in (Side.PLAYER, Side.ENEMY):
                continue
            distance = self._octagonal(unit, other)
            if distance < state.threat_range and (best is None or distance < best_distance):
                best, best_distance = other, distance
        if best is not None:
            self.event_bus.queue_event(unit.identifier, Event(code=0x21, x=int(best.x), y=int(best.y)),
                                       checked=True)

    def _elapsed_and_reload(self, unit: "Regiment") -> tuple[int, int]:
        """(ticks since the last reload stamp, reload time). The stamp sets `reload_ticks` to the reload time + 1
        and the engine counts it down, so elapsed = reload + 1 - reload_ticks while it runs. PROVISIONAL: the
        reload uses the unit's own Initiative and weapon, not the leader block's."""
        from . import ranged
        reload = int(ranged.reload_time(unit))
        if unit.reload_ticks <= 0:
            return reload + 1, reload
        return reload + 1 - int(unit.reload_ticks), reload

    def _stamp(self, unit: "Regiment") -> None:
        from . import ranged
        unit.reload_ticks = ranged.reload_time(unit) + 1

    def _doomwheel_bolts(self, unit: "Regiment") -> None:
        """Code 26: once reloaded, stamp and fire three bolts ahead, right and left (notes/script_behaviours.md
        1.10). Not modelled: the bolts' flight and damage; they are recorded as a battle event."""
        elapsed, reload = self._elapsed_and_reload(unit)
        if elapsed <= reload:
            return
        self._stamp(unit)
        facing = int(unit.direction) % 512
        headings = [facing, (facing + 128) % 512, (facing + 384) % 512]
        self.battle.events.append(BattleEvent(f"{unit.name} fires lightning bolts", "doomwheel_bolts",
                                              regiment=unit.identifier, headings=headings))

    def _pestilent_breath(self, unit: "Regiment") -> None:
        """Code 27: ready once elapsed > trunc(reload / (models div 4 + 1)); a full reload stamps, a partial one
        does not; the cloud goes to the unit position + (off, off) with off from two draws (the original's
        same-offset quirk, notes/script_behaviours.md 1.10). Not modelled: the spell effect; the innate cast is
        recorded as a spell event."""
        elapsed, reload = self._elapsed_and_reload(unit)
        if not elapsed > reload // (unit.models // 4 + 1):
            return
        if elapsed > reload:
            self._stamp(unit)
        heading = self.battle.rng.randrange(512)
        offset = (((self.battle.rng.randrange(360) + 180) >> 1) * heading) >> 8
        self.battle.events.append(BattleEvent(f"{unit.name} breathes pestilence", "spell", regiment=unit.identifier,
                                              spell=24, x=unit.x + offset, y=unit.y + offset))

    def _track_threat(self, unit_id: str, state: UnitScriptState) -> None:
        """Behaviour 15 (notes/script_queries.md 12.1): reveal hidden enemies in view; with no threat pick the
        best as Query 1 does; with a threat and not braced, queue 0x03 (source = the threat, stored score
        not refreshed) when its recomputed score outweighs the unit's worth, else re-pick keeping the old
        threat unless another unit scores strictly more."""
        unit = self.battle.regiments.get(unit_id)
        if unit is None:
            return
        self._spot(unit)
        threat = self.battle.regiments.get(state.threat) if state.threat is not None else None
        if threat is None:
            state.threat, state.threat_score = self._best_threat(unit, state.threat_range)
            return
        if unit.braced:
            return
        score = self._threat_score(unit, threat, state.threat_range)
        if score > self._unit_worth(unit):
            self.event_bus.queue_event(unit_id, Event(code=0x03, source=threat.identifier))
        else:
            state.threat, state.threat_score = self._best_threat(unit, state.threat_range, threat, score)

    def _best_threat(self, unit: "Regiment", threat_range: float, keep: "Regiment | None" = None,
                     keep_score: int = 0) -> tuple[str | None, int]:
        """Highest UnitScore among live units that are not hidden or marked, in unit order, first on ties,
        starting from `keep` and its score (Query 1 starts from none and 0, so a pick must score > 0)."""
        best, best_score = keep, keep_score
        for other in self.battle.regiments.values():
            if other is unit or not other.active or other.hidden or self._leaving(other):
                continue
            score = self._threat_score(unit, other, threat_range)
            if score > best_score:
                best, best_score = other, score
        return (best.identifier if best is not None else None), (best_score if best is not None else 0)

    def op_React(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """React N (notes/script_behaviours.md 3.3): the unit's race row gives a game-text id and an optional
        speech cue. Nothing without text. An enemy-army unit's reaction is dropped when marked "not for enemy
        units", else shown only when marked "also off screen" or the unit is on screen. Shown = the message
        (loaded from the installation's GMTXT by id), the leader portrait expression and the speech cue,
        non-positional. PROVISIONAL: "on screen" is read as "visible to the player and not hidden"."""
        self.react(unit_id, operand or 0)
        return state.pc + 2

    def react(self, unit_id: str, code: int) -> None:
        """React `code` for a unit outside its script too (the objectives' item pickup and retreat warning)."""
        unit = self.battle.regiments.get(unit_id)
        entry = _REACT_TABLE.get((code, unit.race if unit is not None and unit.race is not None else 0))
        if unit is None or entry is None:
            return
        text_id, packet, effect, marker = entry
        if unit.side == Side.ENEMY and (marker == "P" or (marker != "E" and (unit.hidden or not unit.visible_to_player))):
            return
        resources: dict[int, str] = getattr(self.battle, "text_resources", {}) or {}
        message = resources.get(text_id, f"GMTXT {text_id}")
        self.battle.events.append(BattleEvent(
            f"{unit.name}: {message}", "react", regiment=unit_id, code=code, sender=unit.name, message=message,
            text_id=text_id, expression=_REACT_EXPRESSIONS[code % len(_REACT_EXPRESSIONS)]))
        if packet:
            self._sound(unit_id, "play", packet, effect, positional=False)

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

    def op_ReformBlock(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """ReformBlock: re-form into a block of ranks = max(m, min(trunc(N / (sqrt N x 1.15)), N div m)) with
        m = max(1, trunc(0.75 sqrt N)); refused while fleeing, held or charging; condition not written
        (notes/script_spawn_move.md 7)."""
        unit = self.battle.regiments.get(unit_id)
        if unit is None or unit.models <= 0 or unit.routing or unit.held or unit.attack_target is not None:
            return state.pc + 1
        n = unit.models
        root = math.sqrt(n)
        smallest = max(1, int(0.75 * root))
        ranks = max(smallest, min(int(n / (root * 1.15)), n // smallest))
        self.battle.reform_to_ranks(unit, ranks)
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

    def op_FearWhenCharged(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FearWhenCharged (on event 0x07, notes/script_grid_events.md 2.1): acts only when the event's source is
        still charging and the unit is neither broken nor busy casting (else false, nothing). Then the charger
        becomes the target if the unit has none, fear-passed is cleared and the fear/terror test runs; a refusal
        queues 0x0D to the unit itself. The condition is "neither charging nor in melee", not the test result.
        Bracing is the script's (Query 7)."""
        unit = self.battle.regiments.get(unit_id)
        charger = self.battle.regiments.get(state.current_event.source or "")
        if (unit is None or charger is None or not self._charging(charger) or unit.routing
                or self._busy_casting(unit, state)):
            state.cond_flags = False
            return state.pc + 1
        if state.current_target is None:
            state.current_target = (charger.identifier, 0)
        state.fear_passed = False
        if not self._may_engage(unit, charger, state, rng):
            self.event_bus.queue_event(unit_id, Event(code=0x0D))
        state.cond_flags = unit.attack_target is None and not unit.in_melee
        return state.pc + 1

    def _charging(self, unit: "Regiment") -> bool:
        """Charging: running at an attack target, not yet fighting and not pursuing a routing unit."""
        return unit.attack_target is not None and not unit.in_melee and not self._pursuing(unit)

    def _busy_casting(self, unit: "Regiment", state: UnitScriptState) -> bool:
        """IfCasting's "is casting" (notes/script_animation_sound.md 3.2)."""
        return unit.unit_class == WIZARD_CLASS and (
            self._cast_pose_running(unit) or state.pending_spell is not None or state.channelling)

    def _may_engage(self, unit: "Regiment", enemy: "Regiment", state: UnitScriptState, rng: random.Random) -> bool:
        """MayEngage (game_rules.md "Fear and terror"): terror refuses non-Frenzy, non-PsyImmune units without a
        roll; fear (unless CantBreak/Frenzy/PsyImmune, or already passed) takes a Leadership test whose pass
        sets fear-passed. Not modelled: Dread Banners."""
        immune = bool(unit.psychology & {"Frenzy", "PsyImmune"})
        if "CauseTerror" in enemy.psychology and not immune:
            return False
        if ("CauseFear" in enemy.psychology and not immune and "CantBreak" not in unit.psychology
                and not state.fear_passed):
            from . import combat
            state.fear_passed = combat.leadership_test(unit.leadership, rng)
            return state.fear_passed
        return True

    def op_ChargeForward(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """ChargeForward: a charge with no target to the point 12 x s_rlmv straight ahead
        (notes/movement_formation.md 3.6): no fear test and no event 0x07; success clears fear-passed and
        reveals the unit (true); an anchored unit halts and re-forms (false) (notes/script_grid_events.md 3).
        PROVISIONAL: the engine has no free-charge state, so the run is an ordinary move to that point. Not
        modelled: the refusal inside a blocking boundary region."""
        unit = self.battle.regiments.get(unit_id)
        if unit is None:
            state.cond_flags = False
            return state.pc + 1
        if unit.anchored or unit.held:
            self.battle.reform_to_ranks(unit, unit.ranks)
            state.cond_flags = False
            return state.pc + 1
        reach = 12 * self._s_rlmv(unit)
        facing = int(unit.direction)
        unit.target_x = unit.x + int(_trunc_sin(facing) * reach / 256)
        unit.target_y = unit.y + int(_trunc_cos(facing) * reach / 256)
        unit.waypoints = []
        unit.hidden = False
        state.fear_passed = False
        state.cond_flags = True
        return state.pc + 1

    def op_CheckCollisions(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """CheckCollisions: the collision pass in probe mode (notes/movement_formation.md 3.10,
        notes/script_grid_events.md 4): nothing is engaged; touching an enemy runs the contact fear test (a
        refusal makes it the target and queues 0x0D). Condition: anything overlapping. PROVISIONAL: overlap is
        "centres closer than the two footprint radii" and the push-apart is left to the engine's own pass. Not
        modelled: event 0x27 for solid objects ahead. A unit leaving the battle is skipped (false)."""
        unit = self.battle.regiments.get(unit_id)
        if unit is None or state.unit_flags & LEAVING_BATTLE_FLAG:
            state.cond_flags = False
            return state.pc + 1
        touched = False
        for other in self.battle.regiments.values():
            if other is unit or not other.active:
                continue
            if math.hypot(other.x - unit.x, other.y - unit.y) >= other.bounding_radius() + unit.bounding_radius():
                continue
            touched = True
            if (self._hostile(unit, other) and not unit.routing and not self._leaving(other)
                    and not self._may_engage(unit, other, state, rng)):
                state.current_target = (other.identifier, 0)
                self.event_bus.queue_event(unit_id, Event(code=0x0D))
        state.cond_flags = touched
        if not touched:
            state.contact_latch = False
        return state.pc + 1

    def op_SwitchOpponentInGrid(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """SwitchOpponentInGrid (notes/movement_formation.md 7, notes/script_grid_events.md 5): only in melee
        (else the condition is not written). The first unit in table order that is live, not the current target,
        hostile and fighting in this unit's fight becomes the target; the models paired with the old target are
        unpaired (true). None -> false. Not modelled: the attack direction and pairing-mode resets."""
        unit = self.battle.regiments.get(unit_id)
        if unit is None or not unit.in_melee:
            return state.pc + 1
        current = state.current_target[0] if state.current_target else None
        found = next((other for other in self.battle.regiments.values()
                      if other is not unit and other.active and other.identifier != current and other.in_melee
                      and other.melee_group is not None and other.melee_group == unit.melee_group
                      and self._hostile(unit, other)), None)
        if found is not None:
            if current is not None:
                for model in unit.melee_models:
                    if model.opponent is not None and model.opponent[0] == current:
                        model.opponent = None
            state.current_target = (found.identifier, 0)
        state.cond_flags = found is not None
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

    def op_Query(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """Query N: run AI case N; it always writes the condition, and only cases 1, 3, 6, 7, 9 and 10 can
        be true (notes/script_queries.md part A); case 8 is the contact handler (notes/script_behaviours.md 2.3).
        Not modelled: case 18 (no fanatic model); it stays false."""
        cases = {1: self._query_best_threat, 3: self._query_attack_marked, 5: self._query_tell_target,
                 6: self._query_prefer_source, 7: self._query_brace, 8: self._query_contact,
                 9: self._query_assist_friend, 10: self._query_assist_threat, 17: self._query_wander,
                 22: self._query_unit_left, 23: self._query_unit_left, 24: self._query_charge_sound}
        unit = self.battle.regiments.get(unit_id)
        case = cases.get(operand or 0)
        state.cond_flags = unit is not None and case is not None and case(state, unit, rng)
        return state.pc + 2

    def _query_best_threat(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Case 1: threat slot and stored score := the best threat, cleared when none; nothing in deployment."""
        if self.battle.phase == "deployment":
            return False
        state.threat, state.threat_score = self._best_threat(unit, state.threat_range)
        return state.threat is not None

    def _query_attack_marked(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Case 3: the nearest marked, unbroken unit of the opposite army (hidden allowed, whole field, first
        on ties) -> event 0x04 to itself; true after the send attempt even if deployment refused it."""
        best: "Regiment | None" = None
        best_distance = 0
        for other in self.battle.regiments.values():
            if other.active and self._hostile(unit, other) and not other.routing and self._leaving(other):
                distance = self._octagonal(unit, other)
                if best is None or distance < best_distance:
                    best, best_distance = other, distance
        if best is None:
            return False
        self.event_bus.queue_event(unit.identifier, Event(code=0x04, source=best.identifier), checked=True)
        return True

    def _query_tell_target(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Case 5: event 0x05 to the current target, direct path; always false."""
        if state.current_target is not None:
            self.event_bus.queue_event(state.current_target[0], Event(code=0x05, source=unit.identifier))
        return False

    def _query_prefer_source(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Case 6: the event's source becomes the threat when it is not hidden and scores strictly more than
        the current threat recomputed now."""
        source = self.battle.regiments.get(state.current_event.source or "")
        if source is None or source.hidden:
            return False
        new = self._threat_score(unit, source, state.threat_range)
        threat = self.battle.regiments.get(state.threat) if state.threat is not None else None
        if not self._threat_score(unit, threat, state.threat_range) < new:
            return False
        state.threat, state.threat_score = source.identifier, new
        return True

    def _query_brace(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Case 7: an unbraced unit whose remembered event is 0x07 clears that code, targets the charger and
        braces. Not modelled: the reset of the models' movement locks."""
        remembered = state.remembered_event
        if unit.braced or remembered is None or remembered[1] != 0x07 or remembered[0] is None:
            return False
        state.remembered_event = (remembered[0], 0)
        state.current_target = (remembered[0], 0)
        unit.braced, unit.braced_target = True, remembered[0]
        return True

    def _query_contact(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Case 8, the contact handler (notes/script_behaviours.md 2.3): the only place a fight starts. Always
        false. Not modelled: the cannot-engage state (Flying Bower) and buildings, which are not units here."""
        other = self.battle.regiments.get(state.contact_record or "")
        if other is None or not other.active or other.routing:
            return False
        state.contact_latch = True
        current = state.current_target[0] if state.current_target else None
        if other.is_wagon or other.hud_class == "art":
            if other.identifier == current:
                self._engage(unit, other, counter=0, plain=True)
            elif self._hostile(unit, other):
                self._redirect(state, unit, other, current)
            return False
        if not self._hostile(unit, other) and other.identifier != current:
            state.contact_latch = False
            return False
        if unit.attack_target is not None:  # charging or pursuing
            if other.identifier != current:
                self._redirect(state, unit, other, current)
            elif not self._engage(unit, other):
                self.event_bus.queue_event(other.identifier, Event(code=0x0C, source=unit.identifier), checked=True)
        elif current is None:
            if not unit.routing:
                state.current_target = (other.identifier, 0)
                self.event_bus.queue_event(other.identifier, Event(code=0x07, source=unit.identifier), checked=True)
            state.contact_latch = False
        elif other.identifier != current:
            self.event_bus.queue_event(current, Event(code=0x1A, source=unit.identifier), checked=True)
            if not self._engage_new(unit, other):
                self.event_bus.queue_event(other.identifier, Event(code=0x0C, source=unit.identifier), checked=True)
            state.current_target = (other.identifier, 0)
            state.contact_latch = False
        elif not self._engage_new(other, unit):
            self.event_bus.queue_event(unit.identifier, Event(code=0x0C, source=unit.identifier), checked=True)
        return False

    def _redirect(self, state: UnitScriptState, unit: "Regiment", other: "Regiment", current: str | None) -> None:
        """REDIRECT: the unit charges the contacted unit instead (0x1A to the old target, 0x07 to the new one)."""
        if current is not None:
            self.event_bus.queue_event(current, Event(code=0x1A, source=unit.identifier), checked=True)
        state.current_target = (other.identifier, 0)
        unit.pursuing, unit.pursuit_budget, unit.pursuit_point = False, None, None  # it becomes a charge
        if not unit.anchored:
            unit.attack_target = other.identifier
        self.event_bus.queue_event(other.identifier, Event(code=0x07, source=unit.identifier), checked=True)
        state.contact_latch = False

    def _engage_new(self, first: "Regiment", second: "Regiment") -> bool:
        """ENGAGE_NEW(x, y): x joins y's fight when y already fights, else y joins x."""
        if second.in_melee:
            return self._engage(first, second)
        return self._engage(second, first)

    def _engage(self, joiner: "Regiment", owner: "Regiment", counter: int | None = None, plain: bool = False) -> bool:
        """ENGAGE_AS / ENGAGE_PLAIN (notes/script_behaviours.md 2.3): refused when either is broken; a joiner
        already fighting succeeds without change (the double-engagement guard); otherwise the joiner joins the
        owner's fight (or one created around the owner) with a charge counter of floor(1.5 x frontage) (0 for a
        plain engagement), targets the owner (0x1A to its old target), 0x08 goes to the owner when the joiner
        was charging, and 0x0A to both. The grid itself is built by combat.resolve_contacts."""
        if joiner.routing or owner.routing:
            return False
        if joiner.in_melee:
            return True
        joiner_state = self.event_bus.unit_states.get(joiner.identifier)
        owner_state = self.event_bus.unit_states.get(owner.identifier)
        charging = joiner.attack_target is not None
        if counter is None:
            counter = int(1.5 * joiner.frontage)
        self.battle.engage_requests.append((joiner.identifier, owner.identifier, counter))
        if joiner_state is not None:
            current = joiner_state.current_target[0] if joiner_state.current_target else None
            if current != owner.identifier:
                if current is not None:
                    self.event_bus.queue_event(current, Event(code=0x1A, source=joiner.identifier), checked=True)
                joiner_state.current_target = (owner.identifier, 0)
        if plain and owner_state is not None:
            owner_state.current_target = (joiner.identifier, 0)
        if charging and not plain:
            self.event_bus.queue_event(owner.identifier, Event(code=0x08, source=joiner.identifier), checked=True)
        self.event_bus.queue_event(owner.identifier, Event(code=0x0A, source=joiner.identifier), checked=True)
        self.event_bus.queue_event(joiner.identifier, Event(code=0x0A, source=owner.identifier), checked=True)
        joiner.in_melee = owner.in_melee = True
        return True

    def _assist(self, state: UnitScriptState, unit: "Regiment", target_id: str | None, distance: int) -> bool:
        if target_id is None or state.current_target is not None or not distance < state.threat_range:
            return False
        self.event_bus.queue_event(unit.identifier, Event(code=0x04, source=target_id), checked=True)
        return True

    def _query_assist_friend(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Case 9: the event's source F has a target T, F is closer than the threat range and the unit has no
        target -> event 0x04 (source T) to itself, true."""
        friend = self.battle.regiments.get(state.current_event.source or "")
        friend_state = self.event_bus.unit_states.get(friend.identifier) if friend is not None else None
        if friend is None:
            return False
        target = (friend_state.current_target[0] if friend_state is not None and friend_state.current_target
                  else friend.attack_target)
        return self._assist(state, unit, target, self._octagonal(unit, friend))

    def _query_assist_threat(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Case 10: as case 9 with T = the friend's threat, and the distance measured to T."""
        friend_state = self.event_bus.unit_states.get(state.current_event.source or "")
        threat = (self.battle.regiments.get(friend_state.threat)
                  if friend_state is not None and friend_state.threat is not None else None)
        if threat is None:
            return False
        return self._assist(state, unit, threat.identifier, self._octagonal(unit, threat))

    def _query_wander(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Case 17: turn by 128 - trunc(rand(512) / 2), jump (rand(4) + 4) x 12 along the new heading (the
        models stay) and re-form. Not modelled: the re-form end event 0x34 that repeats it."""
        unit.direction = (int(unit.direction) + 128 - rng.randrange(512) // 2) % 512
        step = (rng.randrange(4) + 4) * 12
        angle = unit.direction * math.tau / 512
        unit.x += step * math.sin(angle)
        unit.y += step * math.cos(angle)
        self.battle.reform_to_ranks(unit, unit.ranks)
        return False

    def _query_unit_left(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Cases 22/23: forget the event's source X as threat and parent; if X is the target, outside melee
        queue 0x19 to itself, in melee switch to another opponent in contact or leave the grid (+ 0x19)."""
        gone = state.current_event.source
        if gone is None:
            return False
        if state.threat == gone:
            state.threat = None
        if state.parent_id == gone:
            state.parent_id = None
        if state.current_target is not None and state.current_target[0] == gone:
            if not unit.in_melee or not self._switch_opponent(state, unit, gone):
                if unit.in_melee:
                    self._leave_grid(unit)
                self.event_bus.queue_event(unit.identifier, Event(code=0x19))
        return False

    def _query_charge_sound(self, state: UnitScriptState, unit: "Regiment", rng: random.Random) -> bool:
        """Case 24: start the charge sound from packet 2 unless one runs: effect 1 for Infantry and Archers,
        13 for Cavalry (PROVISIONAL: 14 for the non-Human, Elven or Dwarven races is not told apart, the
        race is not kept), none for other classes. Not modelled: stopping it when the charge ends."""
        effect = {1: 1, 3: 1, 2: 13}.get(unit.unit_class or 0)
        if state.charge_sound is None and effect is not None:
            state.charge_sound = (2, effect)
            self._sound(unit.identifier, "charge_start", 2, effect, positional=True)
        return False

    def _switch_opponent(self, state: UnitScriptState, unit: "Regiment", gone: str) -> bool:
        """In melee: the first model paired with a hostile unit other than `gone` that is still fighting gives
        the new target; pairings with `gone` are dropped. Not modelled: the reset of the pairing mode and
        attack direction."""
        for model in unit.melee_models:
            if model.opponent is None or model.opponent[0] == gone:
                continue
            other = self.battle.regiments.get(model.opponent[0])
            if other is not None and other.in_melee and self._hostile(unit, other):
                for paired in unit.melee_models:
                    if paired.opponent is not None and paired.opponent[0] == gone:
                        paired.opponent = None
                state.current_target = (other.identifier, 0)
                return True
        return False

    def _leave_grid(self, unit: "Regiment") -> None:
        from . import combat
        combat.leave_grid(self.battle, unit)

    def op_IfObjective(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfObjective N: condition := the battle file defines the objective letter with index N (1 = A ...
        7 = G); whether it is met is not tested (notes/script_queries.md B4)."""
        index = operand or 0
        state.cond_flags = 1 <= index <= 26 and chr(ord("A") + index - 1) in self.battle.objective_letters
        return state.pc + 2

    def op_IfClass(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfClass CODE: condition := the unit's class code (class x 8, race not compared) equals CODE
        (notes/script_queries.md B1)."""
        unit = self.battle.regiments.get(unit_id)
        state.cond_flags = unit is not None and unit.unit_class is not None and unit.unit_class * 8 == operand
        return state.pc + 2

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

    # ===== Animation requests, casting states and sound cues (notes/script_animation_sound.md) =====

    def _broadcast_action(self, unit: "Regiment", action: int) -> None:
        unit.script_action = action
        unit.script_action_key = unit.activity_key()

    def op_SetActionState(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SetActionState A: the figures play action A until the unit's next state change; movement is
        untouched, no event, no condition (section 2.1)."""
        unit = self.battle.regiments.get(unit_id)
        if unit is not None:
            self._broadcast_action(unit, operand or 0)
        return state.pc + 2

    def op_PlayUnitAnimation(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """PlayUnitAnimation A E D: broadcast A and request event E every D-th event step, counting down
        from the unit's model count; overwrites an older request (section 2.2). Divisor 0 is invalid and
        posts nothing. Not modelled: the walk program event step of the fanatics' family."""
        unit = self.battle.regiments.get(unit_id)
        event = script_words[state.pc + 2] if state.pc + 2 < len(script_words) else 0
        divisor = script_words[state.pc + 3] if state.pc + 3 < len(script_words) else 0
        if unit is not None:
            self._broadcast_action(unit, operand or 0)
            state.anim_event, state.anim_divisor, state.anim_countdown = event, divisor, unit.models
        return state.pc + 4

    def op_PlayLeaderAnimation(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """PlayLeaderAnimation A E: the leader (or war machine) model alone requests action A, and the
        request becomes (E, 1, 1); a unit without a leader changes nothing at all (section 2.3).
        PROVISIONAL: the engine has no leader-model identity, so the first model plays the leader."""
        unit = self.battle.regiments.get(unit_id)
        if unit is not None and (unit.has_leader or unit.anchored) and unit.melee_models:
            unit.melee_models[0].own_request = operand or 0
            event = script_words[state.pc + 2] if state.pc + 2 < len(script_words) else 0
            state.anim_event, state.anim_divisor, state.anim_countdown = event, 1, 1
        return state.pc + 3

    def op_IfAnimationDone(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfAnimationDone A: true with no countdown left; false for A = 0 or while any model is playing A
        (queued requests do not count); otherwise the request is cleared and the condition is true
        (section 2.4)."""
        unit = self.battle.regiments.get(unit_id)
        if state.anim_countdown == 0:
            state.cond_flags = True
        elif not operand or (unit is not None and any(model.action == operand for model in unit.melee_models)):
            state.cond_flags = False
        else:
            state.anim_event = state.anim_divisor = state.anim_countdown = 0
            state.cond_flags = True
        return state.pc + 2

    def op_ClearAnimationRequest(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """ClearAnimationRequest: drop the request; models finish their pose but post nothing (section 2.5)."""
        state.anim_event = state.anim_divisor = state.anim_countdown = 0
        return state.pc + 1

    def _cast_pose_running(self, unit: "Regiment | None") -> bool:
        """Some model is playing action 7, the cast pose -- which is also the shoot pose (section 3)."""
        return unit is not None and any(model.action == animation.SHOOT for model in unit.melee_models)

    def _battle_message(self, unit_id: str, text_id: int) -> None:
        """A battle message by its game-text id; the frontend loads the text from the installation."""
        unit = self.battle.regiments.get(unit_id)
        name = unit.name if unit is not None else unit_id
        self.battle.events.append(BattleEvent(f"{name}: message {text_id}", "message",
                                              regiment=unit_id, text_id=text_id))

    def op_IfCastingAnimation(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfCastingAnimation F: condition := cast pose running or channelling, any class; a pending spell
        is not tested. True with F set shows message 2014 (section 3.1)."""
        state.cond_flags = self._cast_pose_running(self.battle.regiments.get(unit_id)) or state.channelling
        if state.cond_flags and operand:
            self._battle_message(unit_id, 2014)
        return state.pc + 2

    def op_IfCasting(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfCasting R M: condition := the unit is of class Wizard and its cast pose is running, a spell is
        pending or it is channelling. True with M set shows message 2014 (section 3.2). Not modelled: R's
        re-enabling of the refused spell's magic-panel entry (no magic panel yet)."""
        unit = self.battle.regiments.get(unit_id)
        state.cond_flags = (unit is not None and unit.unit_class == WIZARD_CLASS
                            and (self._cast_pose_running(unit) or state.pending_spell is not None
                                 or state.channelling))
        message = script_words[state.pc + 2] if state.pc + 2 < len(script_words) else 0
        if state.cond_flags and message:
            self._battle_message(unit_id, 2014)
        return state.pc + 3

    def op_TurningToCastMessage(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """TurningToCastMessage F: F = 0 shows message 2010; no state, no condition (section 3.3)."""
        if not operand:
            self._battle_message(unit_id, 2010)
        return state.pc + 2

    def _sound(self, unit_id: str, kind: str, packet: int, effect: int, positional: bool) -> None:
        """Record a sound cue for the frontend; sounds never change game state (section 4)."""
        unit = self.battle.regiments.get(unit_id)
        at = (unit.x, unit.y) if positional and unit is not None else None
        self.battle.events.append(BattleEvent(f"sound {kind} {packet}/{effect}", "sound", regiment=unit_id,
                                              cue=kind, packet=packet, effect=effect, position=at))

    def op_PlaySoundAtUnit(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """PlaySoundAtUnit P E: an overlapping copy of effect E of packet P at the unit (section 4)."""
        effect = script_words[state.pc + 2] if state.pc + 2 < len(script_words) else 0
        self._sound(unit_id, "at_unit", operand or 0, effect, positional=True)
        return state.pc + 3

    def op_PlaySound(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """PlaySound P E: non-positional, not restarted while already playing (section 4)."""
        effect = script_words[state.pc + 2] if state.pc + 2 < len(script_words) else 0
        self._sound(unit_id, "play", operand or 0, effect, positional=False)
        return state.pc + 3

    def op_StartUnitLoopSound(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """StartUnitLoopSound P E F: stop the unit's loop sound, start effect E of packet P at the unit and
        keep it as the loop sound (section 4). Not modelled: the fader operand F."""
        if state.loop_sound is not None:
            self._sound(unit_id, "loop_stop", *state.loop_sound, positional=False)
        effect = script_words[state.pc + 2] if state.pc + 2 < len(script_words) else 0
        state.loop_sound = (operand or 0, effect)
        self._sound(unit_id, "loop_start", operand or 0, effect, positional=True)
        return state.pc + 4

    def op_StopUnitLoopSound(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """StopUnitLoopSound: stop the loop sound; the handle is kept, stopping again is harmless (section 4)."""
        if state.loop_sound is not None:
            self._sound(unit_id, "loop_stop", *state.loop_sound, positional=False)
        return state.pc + 1

    def op_MoveUnitSound(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """MoveUnitSound W: move the charge sound (W = 0) or loop sound (W = 1) to the unit (section 4).
        Not modelled: the engine starts no charge sound, so W = 0 finds an empty handle."""
        if operand == 1 and state.loop_sound is not None:
            self._sound(unit_id, "loop_move", *state.loop_sound, positional=True)
        return state.pc + 2

    # ===== Magic: spell choice, pending spell and casting (notes/script_magic.md) =====

    AI_ARC = 55  # the AI's spell-choice arc, 1/512 turn, strict (section 2.2)
    LAUNCH_ARC = 71  # the launch arc, +-50 degrees, strict (section 0.4, 3.6)

    def _arc_ok(self, unit: "Regiment", x: float, y: float, half: int) -> bool:
        """The bearing to (x, y) differs from the facing by less than `half`; a point on the unit passes."""
        if x == unit.x and y == unit.y:
            return True
        bearing = int(256 - 256 * math.atan2(x - unit.x, -(y - unit.y)) / math.pi) % 512
        difference = abs(int(unit.direction) - bearing) % 512
        return min(difference, 512 - difference) < half

    @staticmethod
    def _point_distance(unit: "Regiment", x: float, y: float) -> int:
        return int(math.hypot(x - unit.x, y - unit.y))

    def _pool_side(self, unit: "Regiment") -> bool:
        """True when the unit draws on the enemy pool; the player army and the allied side share the player's."""
        return unit.side == Side.ENEMY

    def _spell_point(self, state: UnitScriptState, unit: "Regiment", spell: magic.Spell,
                     target: "Regiment", rng: random.Random) -> tuple[bool, tuple[float, float] | None]:
        """Section 2.2 steps 3-4 for one list entry: (accepted, aim point or None for "aim at the target")."""
        distance = self._distance(unit, target)
        if not magic.in_range(distance, spell.code, rng):
            return False, None
        rule = spell.rule
        if rule == magic.ARC:
            return self._arc_ok(unit, target.x, target.y, self.AI_ARC), None
        if rule == magic.MADNESS:
            return self._arc_ok(unit, target.x, target.y, self.AI_ARC) and not self._maddened(target), None
        if rule == magic.AZURE:
            return distance <= 23, None
        if rule == magic.FISTS:
            return distance < 16, None
        if rule == magic.AREA:
            # Inverted rule: any non-friend within the radius rejects -- the hostile target itself always does
            # (game_rules.md "AI casting"). Not modelled: the race-pair friend table and units not counted
            # as ground units, the only exceptions.
            return False, None
        if rule == magic.FRIEND_POINT:
            friends = [other for other in self.battle.regiments.values()
                       if other is not unit and other is not target and other.active and not other.hidden
                       and not self._hostile(unit, other) and not self._leaving(other)
                       and math.hypot(other.x - target.x, other.y - target.y) <= 24]
            if not friends:
                return False, None
            friend = min(friends, key=lambda other: math.hypot(other.x - target.x, other.y - target.y))
            return True, (friend.x, friend.y)
        if rule == magic.SKITTER:
            if not distance < state.threat_range:
                return False, None
            leap = state.threat_range * 9 // 10
            dx, dy = unit.x - target.x, unit.y - target.y
            length = math.hypot(dx, dy)
            if length == 0:  # PROVISIONAL: jump straight back from the unit's facing
                angle = int(unit.direction) * math.tau / 512
                dx, dy, length = -math.sin(angle), -math.cos(angle), 1.0
            return True, (unit.x + leap * dx / length, unit.y + leap * dy / length)
        if rule == magic.DISPEL:
            # Needs an active hostile effect whose caster sees the chooser; there are no spell effects yet.
            return False, None
        return False, None  # NEVER

    def _maddened(self, target: "Regiment") -> bool:
        """Not modelled: the Madness effect, so no unit is ever maddened."""
        return False

    def _leaving(self, other: "Regiment") -> bool:
        other_state = self.event_bus.unit_states.get(other.identifier)
        return other_state is not None and bool(other_state.unit_flags & LEAVING_BATTLE_FLAG)

    def _choose_spell(self, state: UnitScriptState, unit: "Regiment", target: "Regiment", pay: bool,
                      rng: random.Random) -> bool:
        """Take the first list entry that is affordable, has no own effect active (no effects are modelled
        yet), is in range and passes its rule; set pending (and the point/aim for point spells), pay when
        asked. Failure clears the pending spell (section 2.2)."""
        pool = self.event_bus.power.get(self._pool_side(unit))
        for code in unit.spells:
            spell = magic.SPELLS[code]
            if spell.cost > pool:
                continue
            accepted, point = self._spell_point(state, unit, spell, target, rng)
            if not accepted:
                continue
            state.pending_spell = code
            if point is not None:
                state.target_point, state.aim_at_point = point, True
            if pay:
                self.event_bus.power.add(self._pool_side(unit), -spell.cost)
            return True
        state.pending_spell = None
        return False

    def _choose_enemy_and_spell(self, state: UnitScriptState, unit_id: str, class_operand: int, pay: bool,
                                rng: random.Random) -> None:
        """Target := the nearest eligible hostile of the class (no range or visibility, first in order on
        ties), then the spell choice; any failure leaves no target and no pending spell (section 2.1)."""
        unit = self.battle.regiments.get(unit_id)
        found = self._nearest_pick(unit, class_operand) if unit is not None else None
        target = self.battle.regiments.get(found) if found is not None else None
        chosen = False
        if unit is not None and target is not None:
            state.current_target = (target.identifier, 0)
            chosen = self._choose_spell(state, unit, target, pay, rng)
        if not chosen:
            state.current_target = None
            state.pending_spell = None
        state.cond_flags = chosen

    def _choose_spell_for_target(self, state: UnitScriptState, unit_id: str, pay: bool, rng: random.Random) -> None:
        """The spell choice against the current target, which stays as it is (section 2.2)."""
        unit = self.battle.regiments.get(unit_id)
        target = self.battle.regiments.get(state.current_target[0]) if state.current_target else None
        if unit is None or target is None:
            state.pending_spell = None
            state.cond_flags = False
            return
        state.cond_flags = self._choose_spell(state, unit, target, pay, rng)

    def op_ChooseEnemyAndSpellPay(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """ChooseEnemyAndSpellPay: nearest hostile, first acceptable spell, paid when chosen (section 2)."""
        self._choose_enemy_and_spell(state, unit_id, 0, True, rng)
        return state.pc + 1

    def op_ChooseEnemyOfClassAndSpellPay(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """ChooseEnemyOfClassAndSpellPay C: as ChooseEnemyAndSpellPay among class C (class x 8) (section 2)."""
        self._choose_enemy_and_spell(state, unit_id, operand or 0, True, rng)
        return state.pc + 2

    def op_ChooseEnemyAndSpell(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """ChooseEnemyAndSpell: as ChooseEnemyAndSpellPay without paying (a scripted free cast, section 0.3)."""
        self._choose_enemy_and_spell(state, unit_id, 0, False, rng)
        return state.pc + 1

    def op_ChooseSpellForTargetPay(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """ChooseSpellForTargetPay: first acceptable spell against the current target, paid (section 2.2)."""
        self._choose_spell_for_target(state, unit_id, True, rng)
        return state.pc + 1

    def op_ChooseSpellForTarget(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """ChooseSpellForTarget: as ChooseSpellForTargetPay without paying (section 2.2)."""
        self._choose_spell_for_target(state, unit_id, False, rng)
        return state.pc + 1

    def op_SetSpellIfAffordable(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """SetSpellIfAffordable CODE: when the side pool covers the cost, pending := CODE (marker bits kept,
        which make the range unlimited) and condition true; otherwise false, pending unchanged; never pays
        (section 3.1)."""
        unit = self.battle.regiments.get(unit_id)
        price = magic.cost(operand or 0)
        affordable = (unit is not None and price is not None
                      and self.event_bus.power.get(self._pool_side(unit)) >= price)
        if affordable:
            state.pending_spell = operand
        state.cond_flags = affordable
        return state.pc + 2

    def op_SetCastPointNode(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SetCastPointNode N: target := none, target point := node N (file position); no condition (3.2)."""
        state.current_target = None
        node = operand or 0
        if 0 <= node < len(self.battle.script_nodes):
            state.target_point = (self.battle.script_nodes[node].x, self.battle.script_nodes[node].y)
        return state.pc + 2

    def _launch(self, unit_id: str, unit: "Regiment", code: int, x: float, y: float, rng: random.Random) -> bool:
        """The launch checks of section 0.4: a caster (class Wizard, or a leader with the casting weapon),
        the aim point within the spell's range and the +-50 degree arc (skipped in melee), and a unit under
        the point for unit-target spells. Success records a "spell" battle event; a player-army failure
        shows message 2021. Not modelled: the spell effects themselves, the 64-effect limit and the magic
        panel entry made usable again on failure."""
        can_cast = unit.unit_class == WIZARD_CLASS or unit.shooting_code == 16
        ok = (can_cast and magic.in_range(self._point_distance(unit, x, y), code, rng)
              and (unit.in_melee or self._arc_ok(unit, x, y, self.LAUNCH_ARC)))
        if ok and code in magic.UNIT_TARGET_SPELLS:
            ok = any(other.active and self._hostile(unit, other)
                     and math.hypot(other.x - x, other.y - y) <= other.bounding_radius()
                     for other in self.battle.regiments.values())
        if ok:
            self.battle.events.append(BattleEvent(f"{unit.name} casts spell {code}", "spell", regiment=unit_id,
                                                  spell=code, x=x, y=y))
        elif unit.side == Side.PLAYER:
            self._battle_message(unit_id, 2021)
        return ok

    def op_CastPending(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """CastPending: launch the pending spell at the current target (PROVISIONAL: its unit position stands
        in for its leader figure) unless aim-at-point is on, else at the target point; condition := launched.
        Afterwards aim-at-point is off, the pending spell none, and a unit in the cast-only-target state drops
        its target. No refund on failure (section 3.3)."""
        unit = self.battle.regiments.get(unit_id)
        if state.pending_spell is None or unit is None:
            state.cond_flags = False
            return state.pc + 1
        target = self.battle.regiments.get(state.current_target[0]) if state.current_target else None
        if target is not None and not state.aim_at_point:
            aim: tuple[float, float] | None = (target.x, target.y)
        else:
            aim = state.target_point
        state.cond_flags = aim is not None and self._launch(unit_id, unit, state.pending_spell, *aim, rng)
        state.aim_at_point = False
        if state.unit_flags & CAST_ONLY_TARGET_FLAG:
            state.current_target = None
        state.pending_spell = None
        return state.pc + 1

    def op_DropPendingSpell(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """DropPendingSpell: pending := none, no refund, no condition (section 3.4). Not modelled: the magic
        panel entry made usable again."""
        state.pending_spell = None
        return state.pc + 1

    def op_IfEnemyPower(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IfEnemyPower N: condition := the enemy pool holds at least N, whatever the unit's side (3.5)."""
        state.cond_flags = self.event_bus.power.enemy >= (operand or 0)
        return state.pc + 2

    def op_AddEnemyPower(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """AddEnemyPower N: the enemy pool gains N, clamped to 0-8; no condition (section 3.5)."""
        self.event_bus.power.add(True, _signed_word(operand or 0))
        return state.pc + 2

    def op_TargetInCastArc(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """TargetInCastArc: the current target lies in the +-50 degree launch arc, also in melee; false
        without a target (section 3.6)."""
        pair = self._query_pair(state, unit_id)
        state.cond_flags = pair is not None and self._arc_ok(pair[0], pair[1].x, pair[1].y, self.LAUNCH_ARC)
        return state.pc + 2

    def op_IsSpecialShooter(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """IsSpecialShooter: condition := the unit's missile code is 14, 15 or 17 (section 3.7)."""
        unit = self.battle.regiments.get(unit_id)
        state.cond_flags = unit is not None and unit.shooting_code in (14, 15, 17)
        return state.pc + 1

    def _pending_point(self, state: UnitScriptState, unit_id: str) -> tuple["Regiment", float, float] | None:
        """The point PendingInRange* test: the current target's unit position whenever there is a target
        (even with aim-at-point on), else the target point (target_queries.md section 6)."""
        unit = self.battle.regiments.get(unit_id)
        if unit is None:
            return None
        target = self.battle.regiments.get(state.current_target[0]) if state.current_target else None
        if target is not None:
            return unit, target.x, target.y
        if state.target_point is not None:
            return unit, *state.target_point
        return None

    def _pending_in_range(self, state: UnitScriptState, unit: "Regiment", x: float, y: float,
                          rng: random.Random) -> bool:
        """Strict range of the pending spell. PROVISIONAL with no pending spell: the largest finite range
        among the unit's own spells (target_queries.md section 6)."""
        distance = self._point_distance(unit, x, y)
        if state.pending_spell is not None:
            return magic.in_range(distance, state.pending_spell, rng)
        ranges = [magic.SPELLS[code].range for code in unit.spells]
        finite = [limit for limit in ranges if limit is not None]
        return bool(finite) and distance < max(finite)

    def _pending_query(self, state: UnitScriptState, operand: int | None, unit_id: str, rng: random.Random,
                       with_arc: bool) -> None:
        located = self._pending_point(state, unit_id)
        if located is None:
            state.cond_flags = False
            return
        unit, x, y = located
        if with_arc and not unit.in_melee and not self._arc_ok(unit, x, y, self.LAUNCH_ARC):
            state.cond_flags = False
            return
        state.cond_flags = self._pending_in_range(state, unit, x, y, rng)
        if not state.cond_flags and operand:
            self._battle_message(unit_id, 2001)

    def op_PendingInRange(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """PendingInRange F: the target is within the pending spell's range; F reports a range failure with
        message 2001 (target_queries.md section 6)."""
        self._pending_query(state, operand, unit_id, rng, with_arc=False)
        return state.pc + 2

    def op_PendingInRangeArc(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """PendingInRangeArc F: as PendingInRange, and within the +-50 degree arc unless in melee
        (target_queries.md section 6)."""
        self._pending_query(state, operand, unit_id, rng, with_arc=True)
        return state.pc + 2

    def op_PendingReachesBrokenTarget(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """PendingReachesBrokenTarget: false without a target; a broken target counts only within the pending
        spell's range; any other target is true (section 5)."""
        pair = self._query_pair(state, unit_id)
        if pair is None:
            state.cond_flags = False
        else:
            unit, target = pair
            state.cond_flags = (not target.routing
                                or (state.pending_spell is not None
                                    and magic.in_range(self._distance(unit, target), state.pending_spell, rng)))
        return state.pc + 1

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

    def op_ReadyToFire(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """ReadyToFire M: false while held; false while reloading (message 2003 when M is set); an Artillery unit
        without its machine (message 2015) or with fewer than 2 models (message 2016) is false whatever M is;
        otherwise true (notes/script_shooting.md 0)."""
        unit = self.battle.regiments.get(unit_id)
        state.cond_flags = False
        if unit is None or unit.held:
            return state.pc + 2
        if unit.reload_ticks > 0:
            if operand:
                self._battle_message(unit_id, 2003)
            return state.pc + 2
        if unit.unit_class == 4 or unit.hud_class == "art":
            if not unit.machine_alive:
                self._battle_message(unit_id, 2015)
                return state.pc + 2
            if unit.models < 2:
                self._battle_message(unit_id, 2016)
                return state.pc + 2
        state.cond_flags = True
        return state.pc + 2

    def op_StampReload(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """StampReload: restart the reload now; the condition is not written (notes/script_shooting.md 0). The
        stamp is one tick longer than the reload for the strict readiness test (see ranged.launch_shot)."""
        unit = self.battle.regiments.get(unit_id)
        if unit is not None:
            from . import ranged
            unit.reload_ticks = ranged.reload_time(unit) + 1
        return state.pc + 1

    def op_FollowParent(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FollowParent D: shift the unit to D units in front of its parent with the parent's facing; the models
        keep their world positions and walk after it, and the figures are asked to idle (action 2). No parent:
        nothing. The condition is not written (notes/script_spawn_move.md 3)."""
        unit = self.battle.regiments.get(unit_id)
        parent = self.battle.regiments.get(state.parent_id) if state.parent_id is not None else None
        if unit is not None and parent is not None:
            facing = int(parent.direction) % 512
            distance = _signed_word(operand or 0)
            self._shift_anchor(unit, parent.x + ((_trunc_sin(facing) * distance) >> 8),
                               parent.y + ((_trunc_cos(facing) * distance) >> 8))
            unit.direction = facing
            self._broadcast_action(unit, animation.IDLE)
        return state.pc + 2

    @staticmethod
    def _shift_anchor(unit: "Regiment", x: float, y: float) -> None:
        """Move the unit position directly; every model keeps its world position, leaves the in-formation
        state and walks to its slot around the new position (notes/script_spawn_move.md 1)."""
        unit.model_positions()
        unit.x, unit.y = x, y
        for model in unit.melee_models:
            model.at_rest = False

    def op_SpawnUnit(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SpawnUnit TAG SCRIPT PLACE OFFSET (notes/script_spawn_move.md 2): copy the first live unit carrying
        TAG (models, stats, side, psychology), not hidden, untagged, with no target, events or behaviour, running
        SCRIPT from 0 with the spawner as parent. PLACE 1 stands it trunc(OFFSET / 2) to the spawner's side,
        faces it OFFSET + the bearing to the current event's source, then makes the wander step forward
        ((rand(4) + 4) x 12, models left behind) and re-forms. Condition: true, or false with no template.
        The copy's script starts on the next tick. Not modelled: the "inside the parent, not engageable"
        footprint state (Query 18, which ends it, is not modelled either)."""
        words = [script_words[state.pc + k] if state.pc + k < len(script_words) else 0 for k in range(1, 5)]
        tag, script, place, offset = words[0], words[1], words[2], _signed_word(words[3])
        spawner = self.battle.regiments.get(unit_id)
        template_id = self.event_bus.find_by_tag(tag)
        template = self.battle.regiments.get(template_id) if template_id is not None else None
        if spawner is None or template is None:
            state.cond_flags = False
            return state.pc + 5
        copy = self._copy_unit(template)
        self.battle.regiments[copy.identifier] = copy
        self.event_bus.unit_states[copy.identifier] = UnitScriptState(
            script_id=script, script_dll=state.script_dll, parent_id=unit_id)
        if place == 1:
            facing = int(spawner.direction) % 512
            lateral = int(offset / 2)
            copy.x = spawner.x + ((_trunc_cos(facing) * lateral) >> 8)
            copy.y = spawner.y + ((-_trunc_sin(facing) * lateral) >> 8)
            source = self.battle.regiments.get(state.current_event.source or "")
            bearing = self._bearing_from_to((spawner.x, spawner.y), (source.x, source.y)) if source else 256
            copy.direction = (offset + bearing) % 512
            copy.model_positions()
            step = (rng.randrange(4) + 4) * 12
            heading = int(copy.direction)
            self._shift_anchor(copy, copy.x + ((_trunc_sin(heading) * step) >> 8),
                               copy.y + ((_trunc_cos(heading) * step) >> 8))
            self.battle.reform_to_ranks(copy, copy.ranks)
        state.cond_flags = True
        return state.pc + 5

    def _copy_unit(self, template: "Regiment") -> "Regiment":
        """A fresh copy of a unit: same stats and side, its own model list, no orders, fight or flight state."""
        import copy as copying
        import dataclasses
        number = sum(1 for identifier in self.battle.regiments if identifier.startswith(template.identifier))
        unit = copying.copy(template)
        for spec in dataclasses.fields(unit):
            if isinstance(getattr(unit, spec.name), list):
                setattr(unit, spec.name, [])
        unit.identifier = f"{template.identifier}#spawn{number}"
        unit.hidden = False
        unit.attack_target = unit.charge_started_target = unit.braced_target = None
        unit.target_x = unit.target_y = None
        unit.turn_order_key = None
        unit.in_melee = unit.routing = unit.fled = unit.braced = unit.reforming = False
        unit.melee_group = None
        unit.melee_camp = None
        unit.script_action, unit.script_action_key = 0, None
        return unit

    def op_FanaticJump(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FanaticJump N, the squig hop (notes/script_spawn_move.md 4): D = (a + b) x 8 for two d6; heading
        towards the target +-64 (an even offset) or random on a double or with no target; facing := heading;
        the landing point, pushed out of buildings and units of the unit's own side group, becomes the unit
        position with the models left behind. N != 0 sets the hop counter. Condition not written.
        Not modelled: the projection onto blocking boundaries."""
        unit = self.battle.regiments.get(unit_id)
        if unit is None:
            return state.pc + 2
        first, second = rng.randrange(6) + 1, rng.randrange(6) + 1
        distance = (first + second) * 8
        target = self.battle.regiments.get(state.current_target[0]) if state.current_target else None
        if first == second or target is None:
            heading = (int(unit.direction) + rng.randrange(512)) % 512
        else:
            heading = (self._bearing_from_to((unit.x, unit.y), (target.x, target.y))
                       + rng.randrange(64) * 2 - 64) % 512
        unit.direction = heading
        x = unit.x + ((_trunc_sin(heading) * distance) >> 8)
        y = unit.y + ((_trunc_cos(heading) * distance) >> 8)
        own = unit.bounding_radius()
        for other in self.battle.regiments.values():
            if other is unit or not other.active or self._hostile(unit, other):
                continue
            dx, dy = x - other.x, y - other.y
            gap = math.hypot(dx, dy)
            limit = other.bounding_radius() + own / 2
            if 0 < gap < limit:
                x, y = other.x + int(dx * limit / gap), other.y + int(dy * limit / gap)
        self._shift_anchor(unit, x, y)
        if operand:
            state.hop_counter = operand & 0xFF
        return state.pc + 2

    def op_FanaticRelease(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """FanaticRelease, the squig hop landing (notes/script_spawn_move.md 5): clears CantMelee; a landing that
        wounds or touches something is true and keeps the counter; otherwise the counter drops by one (wrapping
        0 to 255) and the condition is "still non-zero". With no target, event 0x01 goes to the unit itself.
        Not modelled: the landing collision and its wounds, so every landing counts as a miss."""
        unit = self.battle.regiments.get(unit_id)
        if unit is not None:
            unit.psychology = unit.psychology - {"CantMelee"}
        state.hop_counter = (state.hop_counter - 1) & 0xFF
        state.cond_flags = state.hop_counter != 0
        if state.current_target is None:
            self.event_bus.queue_event(unit_id, Event(code=0x01))
        return state.pc + 1

    def op_SetClass(self, state: UnitScriptState, operand: int | None, script_words: Words, unit_id: str,
            tick_count: int, rng: random.Random) -> int | None:
        """SetClass CODE: false when the unit already has class code CODE; otherwise its class becomes
        CODE / 8 (race kept) and the condition is true. A crew that stops being Artillery loses its
        war-machine anchor (notes/script_queries.md B2). Not modelled: the HUD class and panel refresh."""
        unit = self.battle.regiments.get(unit_id)
        code = operand or 0
        changed = unit is not None and (unit.unit_class or 0) * 8 != code
        if unit is not None and changed:
            unit.unit_class = code >> 3
            if unit.unit_class != 4 and unit.anchored:
                unit.clear_anchor()
        state.cond_flags = changed
        return state.pc + 2

    def op_IfMachineDestroyed(self, state: UnitScriptState, operand: int | None, script_words: Words,
            unit_id: str, tick_count: int, rng: random.Random) -> int | None:
        """IfMachineDestroyed: condition := the unit has no leader model (the machine of a war machine is its
        leader), or the leader has taken all its wounds (notes/script_queries.md B3). PROVISIONAL: the engine
        keeps no leader wounds, so a leader counts as dead only when the whole unit is."""
        unit = self.battle.regiments.get(unit_id)
        state.cond_flags = unit is None or not (unit.has_leader or unit.anchored) or unit.destroyed
        return state.pc + 1

    # For any other opcode not explicitly handled, the dispatcher will raise NotImplementedError,
    # which is caught and logged by the run() method, allowing partial mission execution.
