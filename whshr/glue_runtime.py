"""Pure, deterministic interpreter for typed ``[RUN]`` glue programs.

This module deliberately has no frontend imports.  It implements the shared
script-state boundary described by ``notes/glue_interpreter.md``; a host turns
its effects into windows, audio, movies, battles, or built-in widgets and later
calls :meth:`GlueRuntime.resume`.
"""

from copy import deepcopy
from dataclasses import dataclass, field

from .campaign_runtime import CampaignRuntime
from .glue_animation import GlueBitmapAnimator
from .glue import AnimRecord, BitmapRecord, GlueInstruction, MissionRecord, MissionRef
from .portraits import PortraitAnimator

# notes/briefing_dialogue.md §3.5, "no speech / no audio device" fallback path (§7 point 9): the
# engine has no WAV playback yet, so dialogue always uses the fixed no-speech pacing rather than
# following a speech clip's playback position.
DIALOGUE_CHAR_MILLISECONDS = 50  # 1 character / 2 ticks at the nominal 25 ms tick
DIALOGUE_HOLD_MILLISECONDS = 750  # 30 ticks held after typing completes, no speech

# Glue's gettentpos position table; notes/campaign_tent.md §3.
TENT_POSITIONS = ((405, 332), (405, 332), (405, 332), (452, 316), (405, 332), (410, 346), (415, 349),
                  (367, 288), (367, 288), (508, 215), (351, 309), (416, 243), (462, 209), (493, 194),
                  (505, 195), (285, 187), (261, 159), (285, 187), (276, 238), (192, 214), (244, 269))


@dataclass(frozen=True)
class GlueInput:
    kind: str
    target: str | None = None


@dataclass(frozen=True)
class ActivityResult:
    request_id: int
    kind: str
    completed: bool = True


@dataclass(frozen=True)
class OpenWindow:
    name: str
    parent: str | None
    palette_id: int


@dataclass(frozen=True)
class CloseWindow:
    name: str


@dataclass(frozen=True)
class UpdateWindow:
    name: str


@dataclass(frozen=True)
class StartMovie:
    request_id: int
    movie: str
    fade: bool = False


@dataclass(frozen=True)
class StartBattle:
    request_id: int
    battle: str
    debrief_index: int
    with_debrief: bool
    encounter: bool


@dataclass(frozen=True)
class StartDialogue:
    request_id: int
    string_id: int
    queued: bool


@dataclass(frozen=True)
class EnterCaravan:
    request_id: int
    mode: str


@dataclass(frozen=True)
class StartDebrief:
    request_id: int
    mode: int
    debrief_index: int
    summary: bool


@dataclass(frozen=True)
class PlayMusic:
    name: str


@dataclass(frozen=True)
class StopMusic:
    pass


@dataclass(frozen=True)
class StopSpeech:
    pass


@dataclass(frozen=True)
class Autosave:
    pass


@dataclass(frozen=True)
class EndGame:
    pass


@dataclass(frozen=True)
class Diagnostic:
    location: str
    message: str


GlueEffect = (OpenWindow | CloseWindow | UpdateWindow | StartMovie | StartBattle | StartDialogue |
              EnterCaravan | StartDebrief | PlayMusic | StopMusic | StopSpeech | Autosave | EndGame | Diagnostic)


@dataclass
class ScriptFrame:
    program: str
    pc: int = 0
    parked: bool = False


@dataclass
class WindowInstance:
    name: str
    parent: str | None
    palette_id: int
    objects: list[str] = field(default_factory=list)


@dataclass
class PendingRequest:
    request_id: int
    kind: str
    restore_context: bool = False


@dataclass
class RuntimeAnimation:
    window_name: str
    animator: GlueBitmapAnimator
    notify_on_stop: bool = False
    object_name: str = ""
    notified: bool = False


@dataclass
class ContextSnapshot:
    """A saved RUN context, kept independently from the script call stack."""

    kind: str
    current: ScriptFrame | None
    call_stack: list[ScriptFrame]
    windows: list[WindowInstance]
    current_window_name: str
    palette_id: int


@dataclass(frozen=True)
class InstructionTrace:
    location: str
    command: str
    argument: str


@dataclass
class GlueRuntimeState:
    current: ScriptFrame | None = None
    call_stack: list[ScriptFrame] = field(default_factory=list)
    windows: list[WindowInstance] = field(default_factory=list)
    status_bits: int = 0
    status_mask: int = 0xFFFFFFFF
    status_mode: int = 2
    variables: dict[str, int] = field(default_factory=lambda: {"animseq": 1, "textlines": 1, "tentpos": 0})
    current_window_name: str = ""
    current_battle: str = ""
    # A battle started without a mission script (a record with only a battle name) ends in the
    # after-mission caravan instead of resuming a script (notes/activity_results.md §2.4).
    caravan_after_battle: bool = False
    selected_mission: MissionRef | None = None
    debrief_index: int = 0
    palette_id: int = 0
    context_stack: list[ContextSnapshot] = field(default_factory=list)
    animations: list[RuntimeAnimation] = field(default_factory=list)
    wait_reason: str | None = None
    pending: PendingRequest | None = None
    next_request_id: int = 1
    trace: list[InstructionTrace] = field(default_factory=list)
    dialogue_window_name: str = ""
    dialogue_lines: tuple = ()  # (text, colour) pairs, oldest first; notes/briefing_dialogue.md §3.3
    dialogue_text: str = ""
    dialogue_line_colour: str = "black"  # colour the current line was queued under
    dialogue_typed: int = 0
    dialogue_ms: int = 0
    dialogue_colour: str = "black"  # live settextcolor value, applies to the *next* queued line
    object_positions: dict = field(default_factory=dict)
    portrait_animators: dict = field(default_factory=dict)
    paused: bool = False
    waits_passed: int = 0  # waitforrelease commands reached so far, to resume a flow at the saved step


class GlueRuntime:
    """Execute programs from one :class:`~whshr.glue_content.GlueContent` repository."""

    MAX_CALL_DEPTH = 16
    MAX_WINDOWS = 8
    MAX_CONTEXT_DEPTH = 16

    def __init__(self, content, campaign: CampaignRuntime | None = None, speech_enabled=True):
        self.content = content
        self.campaign = campaign
        self.speech_enabled = speech_enabled
        self.state = GlueRuntimeState()

    def start(self, program):
        """Start a fresh named program and run until it blocks or ends."""
        self.state = GlueRuntimeState(current=ScriptFrame(str(program).upper()))
        return self.step_until_blocked()

    def continue_with(self, program):
        """Run a replacement flow inside the windows the current one built (the parked frame is dropped)."""
        self.state.current = ScriptFrame(str(program).upper())
        self.state.call_stack.clear()
        self.state.wait_reason = None
        self.state.waits_passed = 0
        return self.step_until_blocked()

    def start_window(self, window):
        self.state = GlueRuntimeState()
        effects = []
        self._open_window(f"res={str(window).upper()}", False, effects)
        return tuple(effects)

    def step_until_blocked(self):
        effects = []
        while self.state.current is not None and self.state.pending is None and self.state.wait_reason is None:
            frame = self.state.current
            try:
                instructions = self.content.program(frame.program).instructions
            except (KeyError, TypeError) as error:
                effects.append(Diagnostic(frame.program, str(error)))
                self._finish_frame(effects)
                continue
            if frame.pc >= len(instructions):
                self._finish_frame(effects)
                continue
            instruction = instructions[frame.pc]
            frame.pc += 1
            self.state.trace.append(InstructionTrace(
                self._location(instruction), instruction.command, instruction.argument,
            ))
            self._execute(instruction, effects)
        return tuple(effects)

    def tick(self, milliseconds):
        if milliseconds < 0:
            raise ValueError("tick duration must not be negative")
        if self.state.paused:
            # §3.2/§3.6.4: the timer handler does nothing while paused - no typing, no animation.
            return ()
        effects = []
        completed = False
        for animator in self.state.portrait_animators.values():
            animator.advance(milliseconds)
        for animation in self.state.animations:
            update = animation.animator.tick(milliseconds)
            # A finite animation ends holding its last frame (notes/campaign_tent.md §5.3); the
            # RuntimeAnimation stays in state.animations so a renderer keeps finding that held
            # frame under the object's identity, instead of falling back to its (non-bitmap) base
            # name once the object stops needing per-tick updates. `notified` fires the parked
            # script's wait-release exactly once, so an old completed animation cannot later
            # masquerade as the completion of a different, still-running one.
            if update.finished and animation.notify_on_stop and not animation.notified:
                animation.notified = True
                completed = True
        if completed and self.state.wait_reason == "animation-finished":
            self.state.wait_reason = None
            if self.state.current is not None:
                self.state.current.parked = False
            effects.extend(self.step_until_blocked())
        if self.state.pending is not None and self.state.pending.kind == "dialogue":
            effects.extend(self._advance_dialogue(milliseconds))
        return tuple(effects)

    def _advance_dialogue(self, milliseconds):
        """Type the pending line, hold it, then resolve the dialogue and resume (§3.5)."""
        text = self.state.dialogue_text
        self.state.dialogue_ms += milliseconds
        if self.state.dialogue_typed < len(text):
            while self.state.dialogue_typed < len(text) and self.state.dialogue_ms >= DIALOGUE_CHAR_MILLISECONDS:
                self.state.dialogue_ms -= DIALOGUE_CHAR_MILLISECONDS
                self.state.dialogue_typed += 1
            if self.state.dialogue_typed < len(text):
                return ()
            self.state.dialogue_ms = min(self.state.dialogue_ms, DIALOGUE_HOLD_MILLISECONDS)
        if self.state.dialogue_ms < DIALOGUE_HOLD_MILLISECONDS:
            return ()
        self.state.dialogue_ms = 0
        self.state.pending = None
        return (StopSpeech(), *self.step_until_blocked())

    def handle(self, input_):
        """Resume a parked script when its explicit wait event arrives."""
        if not isinstance(input_, GlueInput):
            raise TypeError("handle expects GlueInput")
        if input_.kind == "mission-select":
            selected = self._visible_mission(input_.target)
            if selected is not None:
                self.state.selected_mission = selected
                if self.campaign is not None:
                    self.campaign.select_mission(selected)
            return ()
        if input_.kind == "dialogue-drain" and self.state.pending is not None and self.state.pending.kind == "dialogue":
            self.state.dialogue_typed = len(self.state.dialogue_text)  # fast-forward, §3.6.2
            self.state.dialogue_ms = 0
            self.state.pending = None
            return (StopSpeech(), *self.step_until_blocked())
        if input_.kind == "panel-action":
            return self._panel_action(input_.target)
        expected = self.state.wait_reason
        if expected is None or input_.kind != expected:
            return ()
        self.state.wait_reason = None
        if self.state.current is not None:
            self.state.current.parked = False
        return self.step_until_blocked()

    def start_battle(self, battle):
        battle = str(battle).upper()
        if not battle or self.state.pending is not None and self.state.pending.kind == "battle":
            return ()
        self.state.paused = False
        effects = []
        if self.state.pending is not None and self.state.pending.kind == "dialogue":
            self.state.pending = None
            self._clear_dialogue()
            effects.append(StopSpeech())
        effects.append(StopMusic())
        self._request_battle("playgame", battle, effects)
        self.state.caravan_after_battle = True
        return tuple(effects)

    def _visible_mission(self, key):
        """Find a mission advertised by an active window without reparsing glue."""
        if key is None:
            return None
        for window in reversed(self.state.windows):
            for name in (window.name, *reversed(window.objects)):
                try:
                    records = self.content.window(name).records
                except (KeyError, TypeError):
                    continue
                for record in records:
                    if isinstance(record, MissionRecord) and record.mission_ref is not None:
                        if (record.mission_ref.key == str(key).casefold()
                                and self._mission_offered(record.mission_ref)):
                            return record.mission_ref
        return None

    def _test_unit_membership(self, command, argument, effects):
        unit_id = self._parse_int(argument, None)
        if unit_id is None:
            effects.append(Diagnostic(command, f"invalid unit id {argument!r}"))
            return
        method = "is_unit_in_army" if command == "testforunitinarmy" else "is_unit_in_march"
        if self.campaign is None:
            effects.append(Diagnostic(command, "campaign runtime is unavailable"))
            self.state.status_bits &= ~self.state.status_mask
            return
        if getattr(self.campaign, method)(unit_id):
            self.state.status_bits |= self.state.status_mask
        else:
            self.state.status_bits &= ~self.state.status_mask

    def _add_cash(self, argument, effects):
        amount = self._parse_int(argument, None)
        if amount is None:
            effects.append(Diagnostic("addcash", f"invalid amount {argument!r}"))
        elif self.campaign is None:
            effects.append(Diagnostic("addcash", "campaign runtime is unavailable"))
        else:
            self.campaign.add_cash(amount)

    def _add_reinforcements(self, argument, effects):
        unit_id, count = self._parse_assignment(argument)
        if unit_id is None or count is None:
            effects.append(Diagnostic("addtroop", f"invalid reinforcement {argument!r}"))
        elif self.campaign is None:
            effects.append(Diagnostic("addtroop", "campaign runtime is unavailable"))
        else:
            self.campaign.add_reinforcements(unit_id, count)

    def _change_mission_unit(self, argument, joins, effects):
        command = "unitjoinmission" if joins else "unitleavemission"
        unit_id = self._parse_int(argument, None)
        if unit_id is None:
            effects.append(Diagnostic(command, f"invalid unit id {argument!r}"))
        elif self.campaign is None:
            effects.append(Diagnostic(command, "campaign runtime is unavailable"))
        elif joins:
            self.campaign.join_mission(unit_id)
        else:
            self.campaign.leave_mission(unit_id)

    def resume(self, result):
        """Complete one host activity; values never implicitly set glue status."""
        if not isinstance(result, ActivityResult):
            raise TypeError("resume expects ActivityResult")
        pending = self.state.pending
        if pending is None:
            raise ValueError("no activity is pending")
        if (pending.request_id, pending.kind) != (result.request_id, result.kind):
            raise ValueError("activity result does not match the pending request")
        self.state.pending = None
        if pending.restore_context:
            self.pop_context()
        if not result.completed and result.kind == "battle":
            self._clear_for_endgame()
            return (EndGame(),)
        if result.kind == "battle" and self.state.caravan_after_battle:
            self.state.caravan_after_battle = False
            effects = []
            self._request("caravan", effects, restore_context=True, mode="select")
            return tuple(effects)
        return self.step_until_blocked()

    def snapshot(self):
        return deepcopy(self.state)

    def restore(self, snapshot):
        if not isinstance(snapshot, GlueRuntimeState):
            raise TypeError("snapshot must be GlueRuntimeState")
        self.state = deepcopy(snapshot)

    def push_context(self, *, hide=False):
        """Save the current RUN state for an activity or built-in widget.

        The snapshot deliberately includes windows and the script frame, but is
        separate from ``call_stack``: ``gosub``/``return`` and UI navigation
        have different original limits and lifetimes.
        """
        if len(self.state.context_stack) >= self.MAX_CONTEXT_DEPTH:
            return False
        self.state.context_stack.append(ContextSnapshot(
            "RUN", deepcopy(self.state.current), deepcopy(self.state.call_stack),
            deepcopy(self.state.windows), self.state.current_window_name, self.state.palette_id,
        ))
        if hide:
            self.state.windows.clear()
        return True

    def pop_context(self, *, show=True):
        """Restore the most recent RUN context, returning its kind or ``None``."""
        if not self.state.context_stack:
            return None
        snapshot = self.state.context_stack.pop()
        if snapshot.kind != "RUN":
            return snapshot.kind
        self.state.current = deepcopy(snapshot.current)
        self.state.call_stack = deepcopy(snapshot.call_stack)
        self.state.windows = deepcopy(snapshot.windows)
        self.state.current_window_name = snapshot.current_window_name
        self.state.palette_id = snapshot.palette_id
        return snapshot.kind

    def drop_context(self):
        """Discard one saved context without restoring it (the autosave rule)."""
        return self.state.context_stack.pop().kind if self.state.context_stack else None

    def unwind_to_run(self):
        """Restore contexts until a RUN context is found, as mission release does."""
        while self.state.context_stack:
            kind = self.pop_context()
            if kind == "RUN":
                return kind
        return None

    def _execute(self, instruction, effects):
        command, argument = instruction.command, instruction.argument
        if command == "set":
            self._set_variable(instruction)
        elif command == "setgluestatusmask":
            self.state.status_mask = self._parse_hex(argument)
        elif command == "setgluestatusmode":
            self.state.status_mode = self._parse_int(argument, self.state.status_mode)
        elif command == "setgluestatus":
            self.state.status_bits |= self.state.status_mask
        elif command == "clrgluestatus":
            self.state.status_bits &= ~self.state.status_mask
        elif command == "waitforrelease" and self._wait_already_released():
            self.state.waits_passed += 1
        elif command in ("waitforrelease", "waitforresume"):
            if command == "waitforrelease":
                self.state.waits_passed += 1
            self.state.wait_reason = "mission-release" if command == "waitforrelease" else "panel-resume"
            self.state.current.parked = True
        elif command in ("gosub", "iftruegosub", "iffalsegosub"):
            if self._conditional(command):
                self._gosub(argument, effects)
        elif command == "return":
            self._return(effects)
        elif command in ("goto", "iftruegoto", "iffalsegoto"):
            if self._conditional(command):
                if command != "goto":
                    effects.append(Diagnostic(self._location(instruction), "conditional goto is unsupported"))
                    self.state.wait_reason = "conditional-goto"
                else:
                    self.state.current = ScriptFrame(argument.upper())
        elif command in ("openwindow", "opensubwindow"):
            self._open_window(argument, command == "opensubwindow", effects)
        elif command == "closewindow":
            self._close_window(argument, effects)
        elif command == "setcurwindow":
            self.state.current_window_name = self._resource_argument(argument)
        elif command in ("updatewindow", "applyseq"):
            name = self._resource_argument(argument) if argument else self.state.current_window_name
            if command == "applyseq" and name in self.state.portrait_animators:
                self.state.portrait_animators[name].apply(self.state.variables.get("animseq", 1))
            effects.append(UpdateWindow(name))
        elif command in ("addobject", "addanimobject"):
            self._add_object(argument, command == "addanimobject", effects)
        elif command == "removeobject":
            self._remove_object(argument, effects)
        elif command == "playmidi":
            effects.append(PlayMusic(argument))
        elif command == "stopmidi":
            effects.append(StopMusic())
        elif command == "autosave":
            if self.campaign is not None:
                self.campaign.autosave(self.snapshot())
            effects.append(Autosave())
        elif command in ("testforunitinarmy", "testforunitinmarch"):
            self._test_unit_membership(command, argument, effects)
        elif command in ("addcash", "iftrueaddcash"):
            if command == "addcash" or self._condition():
                self._add_cash(argument, effects)
        elif command == "addtroop":
            self._add_reinforcements(argument, effects)
        elif command == "unitjoinmission":
            self._change_mission_unit(argument, True, effects)
        elif command == "unitleavemission":
            self._change_mission_unit(argument, False, effects)
        elif command == "setdebrief":
            self._set_debrief(argument)
        elif command in ("debrief", "debriefwithsummary", "iftruedebrief", "iffalsedebrief",
                         "iftruedebriefwithsummary", "iffalsedebriefwithsummary"):
            if self._conditional(command):
                self._request_debrief(command, argument, effects)
        elif command == "settextcolor":
            self.state.dialogue_colour = argument.strip().casefold()
        elif command in ("playtext", "queuetoplaytext"):
            self._dialogue(argument, command == "queuetoplaytext", effects)
        elif command in ("playmovie", "playmoviewithfade", "iftrueplaymovie", "iffalseplaymovie"):
            if self._conditional(command):
                self._request_movie(argument, command.endswith("withfade"), effects)
        elif command in ("playgame", "playgamewithdebrief", "encounterplaygame", "encounterplaygamewithdebrief"):
            self._request_battle(command, argument, effects)
        elif command in ("gocaravan", "iftruegocaravan", "iffalsegocaravan"):
            if self._conditional(command):
                mode = argument.casefold()
                self._request("caravan", effects, restore_context=mode != "start", mode=mode)
        elif command == "endgame":
            self._clear_for_endgame()
            effects.append(EndGame())
        elif command in {"tagasmission", "comment", "pause", "setdemodefault", "loadanimstringintocache", "queuetext"}:
            return
        else:
            effects.append(Diagnostic(self._location(instruction), f"unsupported command {command!r}"))

    def _finish_frame(self, effects):
        self.state.current = None

    def _return(self, effects):
        if self.state.call_stack:
            self.state.current = self.state.call_stack.pop()
        else:
            self.state.current = None
            effects.append(Diagnostic("return", "script-frame stack underflow"))

    def _gosub(self, argument, effects):
        if len(self.state.call_stack) >= self.MAX_CALL_DEPTH:
            effects.append(Diagnostic("gosub", "script-frame stack overflow"))
            return
        target = self._resource_argument(argument)
        self.state.call_stack.append(deepcopy(self.state.current))
        self.state.current = ScriptFrame(target.upper())

    def _open_window(self, argument, child, effects):
        name = self._resource_argument(argument)
        if not name or len(self.state.windows) >= self.MAX_WINDOWS:
            return
        try:
            definition = self.content.window(name)
        except (KeyError, TypeError):
            return
        position = next((record.values for record in definition.records if record.block_type == "POSITION"), {})
        parent = next((window.name for window in self.state.windows if window.parent is None), None) if child else None
        palette = (next((window.palette_id for window in self.state.windows if window.name == parent), 0)
                   if child else int(position.get("palindex", 0)))
        if not child:
            self.state.palette_id = palette
        instance = WindowInstance(name, parent, palette)
        self.state.windows.append(instance)
        self._select_first_mission()
        anim = next((record for record in definition.records if isinstance(record, AnimRecord)), None)
        if anim is not None:
            self.state.portrait_animators[name] = PortraitAnimator(anim.values.get("sequence", 1))
        effects.append(OpenWindow(name, parent, palette))

    def _close_window(self, argument, effects):
        name = self._resource_argument(argument)
        self.state.windows = [window for window in self.state.windows if window.name != name]
        self.state.portrait_animators.pop(name, None)
        effects.append(CloseWindow(name))

    def _add_object(self, argument, animated, effects):
        name = self._resource_argument(argument)
        target = next((window for window in self.state.windows if window.name == self.state.current_window_name), None)
        if target is None or not name:
            return
        try:
            definition = self.content.window(name)
        except (KeyError, TypeError):
            return
        target.objects.append(name)
        self._select_first_mission()
        effects.append(UpdateWindow(target.name))
        last_bitmap = next((record for record in reversed(definition.records) if isinstance(record, BitmapRecord)), None)
        stop_frame = last_bitmap.values.get("animstopframe", -1) if last_bitmap is not None else -1
        if last_bitmap is not None and "gettentpos" in last_bitmap.values:
            # Resolved once, here, not re-evaluated later if tentpos changes (notes/campaign_tent.md §3).
            index = self._parse_int(self.state.variables.get("tentpos", 0), 0)
            if 0 <= index < len(TENT_POSITIONS):
                self.state.object_positions[(target.name, name)] = TENT_POSITIONS[index]
        if animated and last_bitmap is not None:
            spec = {"bitmap": last_bitmap.values.get("setbitmap", ""), **last_bitmap.values}
            self.state.animations.append(RuntimeAnimation(target.name, GlueBitmapAnimator(spec),
                                                          self._parse_int(stop_frame, -1) >= 0, name))
        if animated and self._parse_int(stop_frame, -1) >= 0:
            self.state.wait_reason = "animation-finished"
            self.state.current.parked = True

    def _remove_object(self, argument, effects):
        target = next((window for window in self.state.windows if window.name == self.state.current_window_name), None)
        if target is None:
            return
        if argument.casefold() == "bitmap" and target.objects:
            target.objects.pop()
        elif argument.casefold() == "mission":
            # Drop the mission list the flow added last (notes/campaign.md section 7.5).
            for index in range(len(target.objects) - 1, -1, -1):
                if self._has_mission_list(target.objects[index]):
                    del target.objects[index]
                    break
            if self.state.selected_mission is not None and not self._selection_offered():
                self.state.selected_mission = None
        effects.append(UpdateWindow(target.name))

    def _wait_already_released(self):
        check = getattr(self.campaign, "wait_already_released", None)
        frame = self.state.current
        return bool(check and frame is not None and not self.state.call_stack
                    and check(frame.program, self.state.waits_passed))

    def _has_mission_list(self, name):
        try:
            return any(isinstance(record, MissionRecord) for record in self.content.window(name).records)
        except (KeyError, TypeError):
            return False

    def _selection_offered(self):
        """Is the selected mission still in a mission list on screen and not yet taken?"""
        ref = self.state.selected_mission
        if not self._mission_offered(ref):
            return False
        for window in self.state.windows:
            for name in (window.name, *window.objects):
                try:
                    records = self.content.window(name).records
                except (KeyError, TypeError):
                    continue
                if any(isinstance(record, MissionRecord) and record.mission_ref == ref for record in records):
                    return True
        return False

    def _mission_offered(self, ref):
        """Is ``ref`` on offer in its window under the campaign's taken set and its depend gates?"""
        offered = getattr(self.campaign, "offered_missions", None)
        if offered is None:
            return True
        try:
            records = self.content.window(ref.window).records
        except (KeyError, TypeError):
            return True
        return ref in offered([record for record in records if isinstance(record, MissionRecord)])

    def refresh_selection(self):
        """Rebuild the selection after the offered list changed: a mission that is no longer on
        offer is dropped and the first offered row on screen is selected instead."""
        self._select_first_mission()

    def _select_first_mission(self):
        if self.state.selected_mission is not None:
            if self._selection_offered():
                return
            self.state.selected_mission = None
        for window in self.state.windows:
            for name in (window.name, *window.objects):
                try:
                    records = self.content.window(name).records
                except (KeyError, TypeError):
                    continue
                for record in records:
                    if (isinstance(record, MissionRecord) and record.mission_ref is not None
                            and self._mission_offered(record.mission_ref)):
                        self.state.selected_mission = record.mission_ref
                        if self.campaign is not None:
                            self.campaign.select_mission(record.mission_ref)
                        return

    def _dialogue(self, argument, queued, effects):
        string_id = self._parse_resource_id(argument)
        if string_id is None:
            return
        if queued and not self.speech_enabled:
            return
        self._queue_dialogue_line(string_id)
        self._request("dialogue", effects, string_id=string_id, queued=queued)

    def _queue_dialogue_line(self, string_id):
        """Scroll the previous line into history and start typing the next one (§3.3 ring buffer).

        A colour change means a new speaker (briefings set a distinct settextcolor per speaker,
        e.g. Dietrich red / the Commander green); the box clears instead of scrolling a mismatched
        colour's leftover line up alongside the new speaker's, matching the original's behaviour.
        """
        try:
            text = self.content.string("BRTXT", string_id)
        except KeyError:
            text = ""
        speaker_changed = self.state.dialogue_text and self.state.dialogue_colour != self.state.dialogue_line_colour
        if speaker_changed:
            history = ()
        else:
            limit = max(1, self._parse_int(self.state.variables.get("textlines", 1), 1))
            previous = (self.state.dialogue_text, self.state.dialogue_line_colour) if self.state.dialogue_text else None
            combined = (*self.state.dialogue_lines, previous) if previous else self.state.dialogue_lines
            history = combined[-(limit - 1):] if limit > 1 else ()
        self.state.dialogue_lines = history
        self.state.dialogue_window_name = self.state.current_window_name
        self.state.dialogue_text = text
        self.state.dialogue_line_colour = self.state.dialogue_colour
        self.state.dialogue_typed = 0
        self.state.dialogue_ms = 0

    def _request_movie(self, argument, fade, effects):
        self._request("movie", effects, restore_context=True, movie=argument, fade=fade)

    def _request_battle(self, command, argument, effects):
        parts = [part.strip() for part in argument.split(",")]
        battle = parts[0].upper() if parts else ""
        if len(parts) > 1 and self._parse_int(parts[1], 0):
            self._set_debrief(parts[1])
        self.state.current_battle = battle
        encounter = command.startswith("encounter")
        self._request("battle", effects, restore_context=encounter, battle=battle,
                      debrief_index=self.state.debrief_index,
                      with_debrief=command.endswith("withdebrief"), encounter=encounter)

    def _request_debrief(self, command, argument, effects):
        self._set_debrief(argument)
        summary = command.endswith("withsummary")
        self._request("debrief", effects, restore_context=True,
                      mode=7 if summary else 4, summary=summary,
                      debrief_index=self.state.debrief_index)

    def _set_debrief(self, value):
        number = self._parse_int(value, 0)
        if number:
            self.state.debrief_index = number - 1

    def _request(self, kind, effects, restore_context=False, **details):
        if restore_context and not self.push_context(hide=True):
            effects.append(Diagnostic(kind, "context stack overflow"))
            return
        request_id = self.state.next_request_id
        self.state.next_request_id += 1
        self.state.pending = PendingRequest(request_id, kind, restore_context)
        if kind == "movie":
            effects.append(StartMovie(request_id, details["movie"], details["fade"]))
        elif kind == "battle":
            effects.append(StartBattle(request_id, details["battle"], details["debrief_index"],
                                       details["with_debrief"], details["encounter"]))
        elif kind == "dialogue":
            effects.append(StartDialogue(request_id, details["string_id"], details["queued"]))
        elif kind == "caravan":
            effects.append(EnterCaravan(request_id, details["mode"]))
        elif kind == "debrief":
            effects.append(StartDebrief(request_id, details["mode"], details["debrief_index"], details["summary"]))

    def _set_variable(self, instruction):
        if "=" not in instruction.argument:
            return
        key, value = instruction.argument.split("=", 1)
        if key.casefold() in {"animseq", "textlines", "tentpos", "x", "y", "step", "timecnt"}:
            self.state.variables[key.casefold()] = self._parse_int(value, 0)

    def _conditional(self, command):
        if not command.startswith(("iftrue", "iffalse")):
            return True
        condition = self._condition()
        return condition if command.startswith("iftrue") else not condition

    def _condition(self):
        if self.state.status_mode == 1:
            return (self.state.status_bits & self.state.status_mask) == self.state.status_mask
        if self.state.status_mode == 2:
            return bool(self.state.status_bits & self.state.status_mask)
        return bool(self.state.status_mode)

    @staticmethod
    def _resource_argument(argument):
        return argument.split("=", 1)[1].strip() if argument.casefold().startswith("res=") else argument.strip()

    @staticmethod
    def _parse_resource_id(argument):
        value = GlueRuntime._resource_argument(argument)
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_int(value, default):
        try:
            return int(str(value), 10)
        except ValueError:
            return default

    @staticmethod
    def _parse_assignment(value):
        if "=" not in value:
            return None, None
        unit_id, count = value.split("=", 1)
        return GlueRuntime._parse_int(unit_id.strip(), None), GlueRuntime._parse_int(count.strip(), None)

    @staticmethod
    def _parse_hex(value):
        digits = ""
        for char in value.strip():
            if char.casefold() in "0123456789abcdef":
                digits += char
            else:
                break
        return int(digits, 16) if digits else 0

    @staticmethod
    def _location(instruction):
        return f"{instruction.location.resource}:{instruction.location.line}"

    def _clear_for_endgame(self):
        self.state.current = None
        self.state.call_stack.clear()
        self.state.windows.clear()
        self.state.context_stack.clear()
        self.state.pending = None
        self.state.wait_reason = None
        self.state.portrait_animators.clear()
        self._clear_dialogue()

    def _clear_dialogue(self):
        self.state.dialogue_lines = ()
        self.state.dialogue_text = ""
        self.state.dialogue_typed = 0
        self.state.dialogue_ms = 0

    def _panel_action(self, action):
        """Dispatch a control-panel button by the action name whshr.controlpanel assigns its slot.

        Only "toggle_pause" and "abort_briefing" (panel 1's Pause and Abort) map onto behaviour
        this runtime already has; every other action reaches into a scene/flow this engine does
        not build yet (troop selection, caravan, the Options dialog, encounter battles) and is
        reported rather than silently doing nothing.
        """
        if action == "toggle_pause":
            self.state.paused = not self.state.paused
            return ()
        if action == "abort_briefing":
            return self._panel_abort()
        self.state.paused = False
        effects = []
        if self.state.pending is not None and self.state.pending.kind == "dialogue":
            self.state.dialogue_typed = len(self.state.dialogue_text)
            self.state.dialogue_ms = 0
            self.state.pending = None
            effects.append(StopSpeech())
        effects.append(Diagnostic("panel", f"{action!r} is not yet implemented"))
        if self.state.current is not None and not self.state.current.parked:
            effects.extend(self.step_until_blocked())
        return tuple(effects)

    def _panel_abort(self):
        """Panel slot 0 for controlpanel 1/5/6/7 (notes/mission_selection.md §4.2): Abort.

        Unpause, stop audio, end the running script, destroy its windows, and restore the parked
        map if one was pushed (real flow); with nothing pushed (e.g. a standalone dev-shortcut
        run) there is nothing to return to, so this behaves like endgame instead.
        """
        self.state.paused = False
        self.state.current = None
        self.state.call_stack.clear()
        self.state.windows.clear()
        self.state.pending = None
        self.state.wait_reason = None
        self.state.portrait_animators.clear()
        self._clear_dialogue()
        popped = self.pop_context()
        effects = [StopSpeech(), StopMusic()]
        if popped is None:
            effects.append(EndGame())
        return tuple(effects)
