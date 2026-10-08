# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Pure, deterministic interpreter for typed ``[RUN]`` glue programs.

This module deliberately has no frontend imports.  It implements the shared
script-state boundary described by ``notes/glue_interpreter.md``; a host turns
its effects into windows, audio, movies, battles, or built-in widgets and later
calls :meth:`GlueRuntime.resume`.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .campaign_runtime import CampaignRuntime
from .campaign_state import caravan_window
from .debrief_rules import STATUS_BIT_VICTORY_WITHOUT_C, STATUS_BIT_VICTORY_WITH_C, Evaluation, evaluate
from .glue_animation import GlueBitmapAnimator
from .glue import AnimRecord, BitmapRecord, GlueInstruction, MissionRecord, MissionRef
from .glue_content import GlueContent
from .speech import clip_milliseconds
from .portraits import PORTRAIT_SPRITES, SPEAKER_INDEX, PortraitAnimator

# notes/briefing_dialogue.md §3.5, "no speech / no audio device" fallback path (§7 point 9): the
# engine has no WAV playback yet, so dialogue always uses the fixed no-speech pacing rather than
# following a speech clip's playback position.
DIALOGUE_CHAR_MILLISECONDS = 50  # 1 character / 2 ticks at the nominal 25 ms tick
DIALOGUE_HOLD_MILLISECONDS = 750  # 30 ticks held after typing completes, no speech
DIALOGUE_SPEECH_HOLD_MILLISECONDS = 200  # 8 ticks held after the clip ends (notes/briefing_dialogue.md §3.5)

# Glue's gettentpos position table; notes/campaign_tent.md §3.
TENT_POSITIONS: tuple[tuple[int, int], ...] = ((405, 332), (405, 332), (405, 332), (452, 316), (405, 332), (410, 346), (415, 349),
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
    window: str = ""


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
class SpeechOverlay:
    """One overlay animation that plays on Dietrich's portrait while a click speech runs (notes/native-windows.md §14.3.3)."""
    bitmap: str  # base name; frame k is ``<bitmap><k>``
    x: int
    y: int
    start_cell: int  # cells count down from here to 0 and wrap
    loop_steps: int  # extra 50 ms steps after cell 0


# Click-speech name -> its (eyes, mouth or book) overlay pair.  Cell sizes, positions and timing: notes/native-windows.md §14.3.2-§14.5.
# PROVISIONAL: the loop pause of every overlay except the talking eyes is not observed and assumed 0 (§14.11).
SPEECH_OVERLAYS: dict[str, tuple[SpeechOverlay, ...]] = {
    "DietrichSpeech": (SpeechOverlay("TalkEyesCell", 300, 200, 1, 60), SpeechOverlay("DietMouthCell", 288, 220, 5, 0)),
    "DietrichRead": (SpeechOverlay("ReadEyesCell", 312, 208, 1, 0), SpeechOverlay("DietBookCell", 296, 260, 11, 0)),
}
SPEECH_OVERLAY_TIMECNT = 2  # steps between cells: each cell shows for 3 steps = 150 ms


@dataclass(frozen=True)
class HotspotSpeech:
    """A clicked hotspot speaks ``count`` consecutive text lines starting at ``string_id`` (``clickres``)."""
    string_id: int
    count: int


@dataclass(frozen=True)
class PlaySpeech:
    """Start the recording of one text line (``B<string_id>.WAV``), replacing any clip still playing
    (notes/briefing_dialogue.md §3.2)."""
    string_id: int


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


# Panel actions of the encounter windows (whshr.controlpanel): resume, attack with a status bit, battle.
ENCOUNTER_ACTIONS = frozenset({"encounter_evade", "encounter_attack_status", "encounter_battle"})


@dataclass(frozen=True)
class Diagnostic:
    location: str
    message: str


@dataclass(frozen=True)
class MissionSelectRequested:
    """The run ended with the ``gomissionselect`` flag raised: the host performs the mission release step
    (notes/glue_interpreter.md §9.3) instead of falling back to a blank map."""


GlueEffect = (OpenWindow | CloseWindow | UpdateWindow | StartMovie | StartBattle | StartDialogue |
              EnterCaravan | StartDebrief | PlayMusic | HotspotSpeech | PlaySpeech | StopMusic | StopSpeech |
              Autosave | EndGame | MissionSelectRequested | Diagnostic)


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
    mode: str = ""  # the caravan mode a caravan request was made for


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
    battle_script: str = ""  # the current-mission record's battle name (setbattlescript)
    text_align: int = 0  # settextalign: left 0, centre 1, right 2 (notes/briefing_dialogue.md)
    # A battle started without a mission script (a record with only a battle name) ends in the
    # after-mission caravan instead of resuming a script (notes/activity_results.md §2.4).
    caravan_after_battle: bool = False
    selected_mission: MissionRef | None = None
    debrief_index: int = 0
    battle_with_debrief: bool = False  # the pending battle request is a *withdebrief* one (paid, mode 2)
    palette_id: int = 0
    context_stack: list[ContextSnapshot] = field(default_factory=list)
    animations: list[RuntimeAnimation] = field(default_factory=list)
    wait_reason: str | None = None
    pending: PendingRequest | None = None
    next_request_id: int = 1
    trace: list[InstructionTrace] = field(default_factory=list)
    dialogue_window_name: str = ""
    dialogue_lines: tuple[tuple[str, str], ...] = ()  # (text, colour) pairs, oldest first; notes/briefing_dialogue.md §3.3
    dialogue_text: str = ""
    dialogue_line_colour: str = "black"  # colour the current line was queued under
    dialogue_typed: int = 0
    dialogue_ms: float = 0
    dialogue_clip_ms: float = 0.0  # length of the current line's recording; 0 = none, the line is paced by its text
    gomissionselect_pending: bool = False  # raised by ``gomissionselect``; notes/glue_interpreter.md §9.3
    pending_goto: str = ""  # target recorded by ``goto``; run when the script ends (notes/glue_interpreter.md 2.2, 4.2)
    dialogue_colour: str = "black"  # live settextcolor value, applies to the *next* queued line
    speech_lines: tuple[int, ...] = ()  # string ids still to speak after the current hotspot speech line
    speech_active: bool = False  # a hotspot click speech is typing or holding its current line
    speech_overlays: dict[str, GlueBitmapAnimator] = field(default_factory=dict[str, GlueBitmapAnimator])  # running eyes/mouth animators by bitmap base name
    object_positions: dict[tuple[str, str], tuple[int, int]] = field(default_factory=dict[tuple[str, str], tuple[int, int]])
    portrait_animators: dict[str, PortraitAnimator] = field(default_factory=dict[str, PortraitAnimator])
    # window name -> (resident-list position, set name) chosen for an `index=-1` block when it was built
    portrait_speakers: dict[str, tuple[int, str]] = field(default_factory=dict[str, tuple[int, str]])
    paused: bool = False
    waits_passed: int = 0  # waitforrelease commands reached so far, to resume a flow at the saved step


class GlueRuntime:
    """Execute programs from one :class:`~whshr.glue_content.GlueContent` repository."""

    MAX_CALL_DEPTH = 16
    MAX_WINDOWS = 8
    MAX_CONTEXT_DEPTH = 16

    def __init__(self, content: GlueContent, campaign: CampaignRuntime | None = None,
                 speech_enabled: bool = True) -> None:
        self.content = content
        self.campaign = campaign
        self.speech_enabled = speech_enabled
        self.state = GlueRuntimeState()

    def start(self, program: str) -> tuple[GlueEffect, ...]:
        """Start a fresh named program and run until it blocks or ends."""
        self.state = GlueRuntimeState(current=ScriptFrame(str(program).upper()))
        return self.step_until_blocked()

    def continue_with(self, program: str) -> tuple[GlueEffect, ...]:
        """Run a replacement flow inside the windows the current one built (the parked frame is dropped)."""
        self.state.current = ScriptFrame(str(program).upper())
        self.state.call_stack.clear()
        self.state.wait_reason = None
        self.state.waits_passed = 0
        return self.step_until_blocked()

    def start_window(self, window: str) -> tuple[GlueEffect, ...]:
        self.state = GlueRuntimeState()
        effects: list[GlueEffect] = []
        self._open_window(f"res={str(window).upper()}", False, effects)
        return tuple(effects)

    def step_until_blocked(self) -> tuple[GlueEffect, ...]:
        effects: list[GlueEffect] = []
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

    def tick(self, milliseconds: float) -> tuple[GlueEffect, ...]:
        if milliseconds < 0:
            raise ValueError("tick duration must not be negative")
        if self.state.paused:
            # §3.2/§3.6.4: the timer handler does nothing while paused - no typing, no animation.
            return ()
        effects: list[GlueEffect] = []
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
        for animator in self.state.speech_overlays.values():
            animator.tick(milliseconds)
        if completed and self.state.wait_reason == "animation-finished":
            self.state.wait_reason = None
            if self.state.current is not None:
                self.state.current.parked = False
            effects.extend(self.step_until_blocked())
        if self.state.pending is not None and self.state.pending.kind == "dialogue":
            effects.extend(self._advance_dialogue(milliseconds))
        elif self.state.speech_active:
            effects.extend(self._advance_speech(milliseconds))
        return tuple(effects)

    def _speech_effects(self, string_id: int) -> tuple[GlueEffect, ...]:
        return (PlaySpeech(string_id),) if self.speech_enabled else ()

    def _advance_speech(self, milliseconds: float) -> tuple[GlueEffect, ...]:
        """Type and hold the current hotspot speech line, then the next one, then clear the box."""
        if not self._step_line(milliseconds):
            return ()
        return self._skip_speech_line()

    def stop_speech(self) -> tuple[GlueEffect, ...]:
        """Cut off a hotspot speech that is still running (its clip and its text), e.g. when the caravan is left."""
        if not self.state.speech_active:
            return ()
        self._end_speech()
        return (StopSpeech(),)

    def _skip_speech_line(self) -> tuple[GlueEffect, ...]:
        """The player clicked through the current hotspot speech line: its clip stops and the next line starts at once
        (its recording and its text), or the box clears after the last one."""
        if self.state.speech_lines:
            (next_id, *rest) = self.state.speech_lines
            self.state.speech_lines = tuple(rest)
            self._queue_dialogue_line(next_id)
            return self._speech_effects(next_id)
        self._end_speech()
        return (StopSpeech(),)

    def _end_speech(self) -> None:
        """The run is over: the overlays are removed and the plain backdrop shows (§14.3.3)."""
        self.state.speech_active = False
        self.state.speech_lines = ()
        self.state.speech_overlays = {}
        self._clear_dialogue()

    def _step_line(self, milliseconds: float) -> bool:
        """Advance the line on screen; True once it has been typed and held and the next thing may start.

        With a recording the typed part follows the playback (notes/briefing_dialogue.md §3.5) and the line ends
        a short hold after the clip, so a following line never cuts the clip off; without one the text sets the pace."""
        state = self.state
        text = state.dialogue_text
        state.dialogue_ms += milliseconds
        clip = state.dialogue_clip_ms
        if clip > 0:
            state.dialogue_typed = max(state.dialogue_typed, min(len(text), int(len(text) * state.dialogue_ms / clip)))
            return state.dialogue_ms >= clip + DIALOGUE_SPEECH_HOLD_MILLISECONDS
        if state.dialogue_typed < len(text):
            while state.dialogue_typed < len(text) and state.dialogue_ms >= DIALOGUE_CHAR_MILLISECONDS:
                state.dialogue_ms -= DIALOGUE_CHAR_MILLISECONDS
                state.dialogue_typed += 1
            if state.dialogue_typed < len(text):
                return False
            state.dialogue_ms = min(state.dialogue_ms, DIALOGUE_HOLD_MILLISECONDS)
        return state.dialogue_ms >= DIALOGUE_HOLD_MILLISECONDS

    def _hotspot_speech(self, argument: str | None) -> tuple[GlueEffect, ...]:
        """Speak a clicked hotspot's ``clickres`` lines (``"<first id>:<count>[:<name>]"``); a click is ignored
        while a script dialogue or an earlier click speech is still running (notes/native-windows.md §14.3.3)."""
        if self.state.speech_active:
            return ()
        if self.state.pending is not None and self.state.pending.kind == "dialogue":
            return ()
        first, count, *rest = str(argument).split(":")
        try:
            first, count = int(first), int(count)
        except ValueError:
            return ()
        if count < 1:
            return ()
        self.state.dialogue_colour = "red"  # Dietrich's colour, kept after the run like the original (§14.3.3)
        self.state.variables["textlines"] = 2
        self.state.speech_overlays = self._start_speech_overlays(rest[0] if rest else "")
        self.state.speech_active = True
        self.state.speech_lines = tuple(range(first + 1, first + count))
        self._queue_dialogue_line(first)
        return (HotspotSpeech(first, count), *self._speech_effects(first))

    @staticmethod
    def _start_speech_overlays(name: str) -> dict[str, GlueBitmapAnimator]:
        """Start the eyes and mouth (or book) animators of click speech ``name``, each showing its first cell at once."""
        animators: dict[str, GlueBitmapAnimator] = {}
        for overlay in SPEECH_OVERLAYS.get(name, ()):
            animator = GlueBitmapAnimator({
                "bitmap": overlay.bitmap, "animstartframe": overlay.start_cell, "animstopframe": -1,
                "timecnt": SPEECH_OVERLAY_TIMECNT, "looptimecnt": overlay.loop_steps})
            animator.delay = 0
            animator.step()
            animators[overlay.bitmap] = animator
        return animators

    def _advance_dialogue(self, milliseconds: float) -> tuple[GlueEffect, ...]:
        """Type the pending line, hold it, then resolve the dialogue and resume (§3.5)."""
        if not self._step_line(milliseconds):
            return ()
        self.state.dialogue_ms = 0
        self.state.pending = None
        return (StopSpeech(), *self.step_until_blocked())

    def handle(self, input_: GlueInput) -> tuple[GlueEffect, ...]:
        """Resume a parked script when its explicit wait event arrives."""
        if not isinstance(input_, GlueInput):  # pyright: ignore[reportUnnecessaryIsInstance]
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
        if input_.kind == "dialogue-drain" and self.state.speech_active:
            return self._skip_speech_line()
        if input_.kind == "hotspot-speech":
            return self._hotspot_speech(input_.target)
        if input_.kind == "panel-action":
            return self._panel_action(input_.target)
        expected = self.state.wait_reason
        if expected is None or input_.kind != expected:
            return ()
        self.state.wait_reason = None
        if self.state.current is not None:
            self.state.current.parked = False
        return self.step_until_blocked()

    def start_battle(self, battle: str, debrief: int | str | None = None) -> tuple[GlueEffect, ...]:
        """Start ``battle`` outside any script: the play-game step of a mission record that names no mission
        script.  With a ``debrief`` number it is a *withdebrief* battle, so the debrief (and its payment)
        follows it exactly as after a scripted one; afterwards the caravan opens (``gocaravan:select``)."""
        battle = str(battle).upper()
        if not battle or self.state.pending is not None and self.state.pending.kind == "battle":
            return ()
        self.state.paused = False
        effects: list[GlueEffect] = []
        if self.state.pending is not None and self.state.pending.kind == "dialogue":
            self.state.pending = None
            self._clear_dialogue()
            effects.append(StopSpeech())
        effects.append(StopMusic())
        if debrief:
            self._request_battle("playgamewithdebrief", f"{battle},{debrief}", effects)
        else:
            self._request_battle("playgame", battle, effects)
        self.state.caravan_after_battle = True
        return tuple(effects)

    def _visible_mission(self, key: str | None) -> MissionRef | None:
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

    def _test_unit_membership(self, command: str, argument: str, effects: list[GlueEffect]) -> None:
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

    def _add_unit(self, argument: str, effects: list[GlueEffect]) -> None:
        unit_id = self._parse_int(argument.split(";")[0].strip(), None)
        if unit_id is None:
            effects.append(Diagnostic("addunit", f"invalid unit id {argument!r}"))
        elif self.campaign is None or not hasattr(self.campaign, "mark_pending_join"):
            effects.append(Diagnostic("addunit", "campaign runtime is unavailable"))
        else:
            self.campaign.mark_pending_join(unit_id)

    def _set_status(self, value: bool) -> None:
        if value:
            self.state.status_bits |= self.state.status_mask
        else:
            self.state.status_bits &= ~self.state.status_mask

    def _test_result(self, command: str, argument: str, effects: list[GlueEffect]) -> None:
        """``testobjective:<L>`` / ``testmission:`` (notes/debrief_evaluation.md section 5): a letter is met only
        when the latest battle result has it; a missing result counts as false, as a missing debrief file does."""
        if command == "testobjective":
            letter = argument.strip()[:1]
            campaign = self.campaign
            record = (campaign.objective(letter)
                      if letter and campaign is not None and hasattr(campaign, "objective") else None)
            met = bool(record and record[0])
            if record is None:
                effects.append(Diagnostic(command, f"no battle result for objective {letter!r}: treated as not met"))
        else:
            met = self._mission_victory(effects)
        self._set_status(met)
        if command == "testmission":
            if self.campaign is not None:
                self.campaign.autosave(self.snapshot())
            effects.append(Autosave())

    def _mission_victory(self, effects: list[GlueEffect]) -> bool:
        """The T-result of the current mission's debrief evaluator over the latest battle result
        (notes/debrief_evaluation.md sections 4-5).  A no-battle flawless result is a win by definition."""
        campaign = self.campaign
        if getattr(campaign, "flawless_result", False):
            return True
        results = getattr(campaign, "objective_results", None)
        if not results:
            effects.append(Diagnostic("testmission", "no battle result to evaluate: treated as lost"))
            return False
        evaluation = evaluate(self.state.debrief_index, results)
        self.apply_evaluation_status(evaluation)
        return evaluation.victory

    def apply_evaluation_status(self, evaluation: Evaluation) -> None:
        """The last mission's evaluator refreshes two status bits whenever it runs (notes/debrief_evaluation.md 5)."""
        if evaluation.entry.kind == 7:
            bits = STATUS_BIT_VICTORY_WITH_C | STATUS_BIT_VICTORY_WITHOUT_C
            self.state.status_bits = (self.state.status_bits & ~bits) | evaluation.status_bits

    def _bonus(self, command: str, argument: str, effects: list[GlueEffect]) -> None:
        """``bonusadd:<n>,<L>`` adds value ``n`` (1-4) of objective ``L`` to the bonus counter;
        ``bonussubtract`` subtracts it (notes/campaign.md section 2.5)."""
        number, _, letter = argument.partition(",")
        number, letter = self._parse_int(number.strip(), 0), letter.strip()[:1]
        if not 1 <= number <= 4 or not letter:
            effects.append(Diagnostic(command, f"invalid bonus argument {argument!r}"))
            return
        campaign = self.campaign
        if campaign is None or not hasattr(campaign, "bonus_adjust"):
            effects.append(Diagnostic(command, "campaign runtime is unavailable"))
            return
        record = campaign.objective(letter)
        if record is None:
            effects.append(Diagnostic(command, f"no battle result for objective {letter!r}: the counter is unchanged"))
            return
        sign = -1 if command == "bonussubtract" else 1
        campaign.bonus_adjust(sign * record[1][number - 1])

    def _enable_book(self, argument: str, effects: list[GlueEffect]) -> None:
        book, index = self._parse_assignment(argument)
        if book is None or index is None:
            effects.append(Diagnostic("enablebook", f"invalid book entry {argument!r}"))
        elif self.campaign is None or not hasattr(self.campaign, "enable_book"):
            effects.append(Diagnostic("enablebook", "campaign runtime is unavailable"))
        else:
            self.campaign.enable_book(book, index)

    def _add_cash(self, argument: str, effects: list[GlueEffect]) -> None:
        amount = self._parse_int(argument, None)
        if amount is None:
            effects.append(Diagnostic("addcash", f"invalid amount {argument!r}"))
        elif self.campaign is None:
            effects.append(Diagnostic("addcash", "campaign runtime is unavailable"))
        else:
            self.campaign.add_cash(amount)

    def _add_reinforcements(self, argument: str, effects: list[GlueEffect]) -> None:
        unit_id, count = self._parse_assignment(argument)
        if unit_id is None or count is None:
            effects.append(Diagnostic("addtroop", f"invalid reinforcement {argument!r}"))
        elif self.campaign is None:
            effects.append(Diagnostic("addtroop", "campaign runtime is unavailable"))
        else:
            self.campaign.add_reinforcements(unit_id, count)

    def _change_mission_unit(self, argument: str, joins: bool, effects: list[GlueEffect]) -> None:
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

    def resume(self, result: ActivityResult) -> tuple[GlueEffect, ...]:
        """Complete one host activity; values never implicitly set glue status."""
        if not isinstance(result, ActivityResult):  # pyright: ignore[reportUnnecessaryIsInstance]
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
        if result.kind == "battle" and self.state.caravan_after_battle and not pending.restore_context:
            self.state.caravan_after_battle = False
            effects: list[GlueEffect] = []
            self._request("caravan", effects, restore_context=True, mode="select")
            return tuple(effects)
        return self.step_until_blocked()

    def open_caravan(self, mode: str) -> tuple[GlueEffect, ...]:
        """Park the finished script again and open the caravan window of ``mode`` on top of it
        (notes/activity_results.md section 6.2); empty when the request could not be made."""
        effects: list[GlueEffect] = []
        self._request("caravan", effects, restore_context=True, mode=mode)
        return tuple(effects)

    def snapshot(self) -> GlueRuntimeState:
        return deepcopy(self.state)

    def restore(self, snapshot: GlueRuntimeState) -> None:
        if not isinstance(snapshot, GlueRuntimeState):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("snapshot must be GlueRuntimeState")
        self.state = deepcopy(snapshot)

    def push_context(self, *, hide: bool = False) -> bool:
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

    def push_window_frame(self, window_name: str) -> bool:
        """Keep a window that opened a flow on the context stack, without restoring anything when it is popped
        (a hotspot's WINDOW frame: the main menu stays under the start caravan, notes/native-windows.md §7.3.1)."""
        if len(self.state.context_stack) >= self.MAX_CONTEXT_DEPTH:
            return False
        self.state.context_stack.append(ContextSnapshot("WINDOW", None, [], [], window_name, self.state.palette_id))
        return True

    def pop_context(self, *, show: bool = True) -> str | None:
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

    def drop_context(self) -> str | None:
        """Discard one saved context without restoring it (the autosave rule)."""
        return self.state.context_stack.pop().kind if self.state.context_stack else None

    def unwind_to_run(self) -> str | None:
        """Restore contexts until a RUN context is found, as mission release does."""
        while self.state.context_stack:
            kind = self.pop_context()
            if kind == "RUN":
                return kind
        return None

    def _execute(self, instruction: GlueInstruction, effects: list[GlueEffect]) -> None:
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
            if self.state.current is not None:
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
                    # Only a request (notes/glue_interpreter.md 2.3): the run goes on and the jump happens when the
                    # script ends, unless a resource load clears it first (quirk 3).
                    self.state.pending_goto = self._resource_argument(argument).upper()
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
        elif command == "gomissionselect":
            self.state.gomissionselect_pending = True
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
        elif command == "addunit":
            self._add_unit(argument, effects)
        elif command in ("testobjective", "testmission"):
            self._test_result(command, argument, effects)
        elif command == "bonusinit":
            if self.campaign is not None and hasattr(self.campaign, "bonus_init"):
                self.campaign.bonus_init()
            else:
                effects.append(Diagnostic("bonusinit", "campaign runtime is unavailable"))
        elif command in ("bonusadd", "bonussubtract", "iftruebonusadd", "iffalsebonusadd"):
            if self._conditional(command):
                self._bonus(command, argument, effects)
        elif command == "setbattlescript":
            self.state.battle_script = argument.strip().upper()
        elif command == "settextalign":
            self.state.text_align = {"left": 0, "center": 1, "right": 2}.get(argument.strip().casefold(), 0)
        elif command == "enablebook":
            self._enable_book(argument, effects)
        elif command == "addmidiobject":
            effects.append(PlayMusic(argument.strip()))
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
                mode = argument.strip().casefold()
                if mode == "start":
                    self._request("caravan", effects, mode=mode)
                elif caravan_window(mode) is None:
                    # notes/glue_interpreter.md section 7.3: an unknown name is logged and the script goes on
                    effects.append(Diagnostic(self._location(instruction), f"unknown caravan {argument!r}"))
                else:
                    self._request("caravan", effects, restore_context=True, mode=mode)
        elif command == "endgame":
            self._clear_for_endgame()
            effects.append(EndGame())
        elif command in {"tagasmission", "comment", "pause", "setdemodefault", "loadanimstringintocache", "queuetext"}:
            return
        else:
            effects.append(Diagnostic(self._location(instruction), f"unsupported command {command!r}"))

    def _clear_pending_requests(self) -> None:
        """Every resource load (window, object or script) clears the pending goto and the gomissionselect flag
        (notes/glue_interpreter.md 10, quirk 3)."""
        self.state.pending_goto = ""
        self.state.gomissionselect_pending = False

    def _finish_frame(self, effects: list[GlueEffect]) -> None:
        self.state.current = None
        if self.state.pending_goto:
            # The target replaces the ended script as a tail call (no frame is pushed); loading it clears the
            # gomissionselect flag, so the goto wins (notes/glue_interpreter.md 2.1).
            target, self.state.pending_goto = self.state.pending_goto, ""
            self.state.gomissionselect_pending = False
            self.state.current = ScriptFrame(target)
            return
        if self.state.gomissionselect_pending:
            # The flag only fires the mission release step once the run truly ends (no window, wait or
            # pending request left to resume it); a resource load clears it first (quirk 3), but shipped
            # scripts always put the command last, so this is where it fires.
            self.state.gomissionselect_pending = False
            effects.append(MissionSelectRequested())

    def _return(self, effects: list[GlueEffect]) -> None:
        if self.state.call_stack:
            self.state.current = self.state.call_stack.pop()
        else:
            self.state.current = None
            effects.append(Diagnostic("return", "script-frame stack underflow"))

    def _gosub(self, argument: str, effects: list[GlueEffect]) -> None:
        if len(self.state.call_stack) >= self.MAX_CALL_DEPTH:
            effects.append(Diagnostic("gosub", "script-frame stack overflow"))
            return
        target = self._resource_argument(argument)
        try:
            self.content.program(target.upper())
        except (KeyError, TypeError):
            pass  # a target that cannot be opened changes nothing (the frame then reports the missing resource)
        else:
            self._clear_pending_requests()
        if self.state.current is not None:
            self.state.call_stack.append(deepcopy(self.state.current))
        self.state.current = ScriptFrame(target.upper())

    def _open_window(self, argument: str, child: bool, effects: list[GlueEffect]) -> None:
        name = self._resource_argument(argument)
        if not name or len(self.state.windows) >= self.MAX_WINDOWS:
            return
        try:
            definition = self.content.window(name)
        except (KeyError, TypeError):
            return
        self._clear_pending_requests()  # a failed load changes nothing (notes/glue_interpreter.md 2.1)
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
            self.state.portrait_animators[name] = PortraitAnimator(int(anim.values.get("sequence", 1)))
            self.state.portrait_speakers.pop(name, None)
            self.portrait_index(name, anim.values.get("index"))
        effects.append(OpenWindow(name, parent, palette))

    def portrait_index(self, window_name: str, index: Any) -> Any:
        """Resident-list position a window's portrait block shows.

        ``index=-1`` is the current commander (notes/glue_portraits.md §1.4): resolved once when the
        window is built and kept while it is open.
        """
        try:
            index = int(index)
        except (TypeError, ValueError):
            return index
        if index != SPEAKER_INDEX:
            return index
        chosen = self.state.portrait_speakers.get(window_name)
        if chosen is None:
            speaker = getattr(self.campaign, "current_speaker", None)
            position = self.content.resolve_speaker_position(speaker)
            chosen = self.state.portrait_speakers[window_name] = (position, PORTRAIT_SPRITES[position])
        return chosen[0]

    def _close_window(self, argument: str, effects: list[GlueEffect]) -> None:
        name = self._resource_argument(argument)
        self.state.windows = [window for window in self.state.windows if window.name != name]
        # the text of a window that is gone, or of a scene with no window left, is not shown any more
        if self.state.dialogue_text and (name == self.state.dialogue_window_name
                                         or (not self.state.windows and not self.state.context_stack)):
            self._clear_dialogue()
        self.state.portrait_animators.pop(name, None)
        self.state.portrait_speakers.pop(name, None)
        effects.append(CloseWindow(name))

    def _add_object(self, argument: str, animated: bool, effects: list[GlueEffect]) -> None:
        name = self._resource_argument(argument)
        target = next((window for window in self.state.windows if window.name == self.state.current_window_name), None)
        if target is None or not name:
            return
        try:
            definition = self.content.window(name)
        except (KeyError, TypeError):
            return
        self._clear_pending_requests()
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
            if self.state.current is not None:
                self.state.current.parked = True

    def _remove_object(self, argument: str, effects: list[GlueEffect]) -> None:
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

    def _wait_already_released(self) -> bool:
        check = getattr(self.campaign, "wait_already_released", None)
        frame = self.state.current
        return bool(check and frame is not None and not self.state.call_stack
                    and check(frame.program, self.state.waits_passed))

    def _has_mission_list(self, name: str) -> bool:
        try:
            return any(isinstance(record, MissionRecord) for record in self.content.window(name).records)
        except (KeyError, TypeError):
            return False

    def _selection_offered(self) -> bool:
        """Is the selected mission still in a mission list on screen and not yet taken?"""
        ref = self.state.selected_mission
        if ref is None or not self._mission_offered(ref):
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

    def _mission_offered(self, ref: MissionRef) -> bool:
        """Is ``ref`` on offer in its window under the campaign's taken set and its depend gates?"""
        offered = getattr(self.campaign, "offered_missions", None)
        if offered is None:
            return True
        try:
            records = self.content.window(ref.window).records
        except (KeyError, TypeError):
            return True
        return ref in offered([record for record in records if isinstance(record, MissionRecord)])

    def refresh_selection(self) -> None:
        """Rebuild the selection after the offered list changed: a mission that is no longer on
        offer is dropped and the first offered row on screen is selected instead."""
        self._select_first_mission()

    def _select_first_mission(self) -> None:
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

    def _dialogue(self, argument: str, queued: bool, effects: list[GlueEffect]) -> None:
        string_id = self._parse_resource_id(argument)
        if string_id is None:
            return
        if queued and not self.speech_enabled:
            return
        self._queue_dialogue_line(string_id)
        self._request("dialogue", effects, string_id=string_id, queued=queued)
        effects.extend(self._speech_effects(string_id))

    def _queue_dialogue_line(self, string_id: int) -> None:
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
        self.state.dialogue_clip_ms = clip_milliseconds(getattr(self.content, "installation", None), string_id) if self.speech_enabled else 0.0
        self.state.dialogue_line_colour = self.state.dialogue_colour
        self.state.dialogue_typed = 0
        self.state.dialogue_ms = 0

    def _request_movie(self, argument: str, fade: bool, effects: list[GlueEffect]) -> None:
        self._request("movie", effects, restore_context=True, movie=argument, fade=fade)

    def _request_battle(self, command: str, argument: str, effects: list[GlueEffect]) -> None:
        parts = [part.strip() for part in argument.split(",")]
        battle = parts[0].upper() if parts else ""
        if len(parts) > 1 and self._parse_int(parts[1], 0):
            self._set_debrief(parts[1])
        self.state.current_battle = battle
        self.state.battle_with_debrief = command.endswith("withdebrief")
        encounter = command.startswith("encounter")
        self._request("battle", effects, restore_context=encounter, battle=battle,
                      debrief_index=self.state.debrief_index,
                      with_debrief=command.endswith("withdebrief"), encounter=encounter)

    def _request_debrief(self, command: str, argument: str, effects: list[GlueEffect]) -> None:
        self._set_debrief(argument)
        summary = command.endswith("withsummary")
        self._request("debrief", effects, restore_context=True,
                      mode=7 if summary else 4, summary=summary,
                      debrief_index=self.state.debrief_index)

    def _set_debrief(self, value: str) -> None:
        number = self._parse_int(value, 0)
        if number:
            self.state.debrief_index = number - 1

    def _request(self, kind: str, effects: list[GlueEffect], restore_context: bool = False, **details: Any) -> None:
        if restore_context and not self.push_context(hide=True):
            effects.append(Diagnostic(kind, "context stack overflow"))
            return
        request_id = self.state.next_request_id
        self.state.next_request_id += 1
        self.state.pending = PendingRequest(request_id, kind, restore_context, details.get("mode", "") if kind == "caravan" else "")
        if kind == "movie":
            effects.append(StartMovie(request_id, details["movie"], details["fade"]))
        elif kind == "battle":
            effects.append(StartBattle(request_id, details["battle"], details["debrief_index"],
                                       details["with_debrief"], details["encounter"]))
        elif kind == "dialogue":
            effects.append(StartDialogue(request_id, details["string_id"], details["queued"]))
        elif kind == "caravan":
            merge = getattr(self.campaign, "merge_pending_joins", None)
            if callable(merge):
                merge()  # the caravan picks up the regiments ``addunit`` flagged (notes/campaign.md §2.4)
            recruitable = bool(getattr(self.campaign, "recruitable", lambda: False)())
            window = (caravan_window(details["mode"], recruitable) or "") if restore_context else ""
            try:
                self.content.window(window)
            except (KeyError, TypeError):
                window = (caravan_window(details["mode"]) or "") if window else ""  # no WithRecruit variant: the plain one
                try:
                    self.content.window(window)
                except (KeyError, TypeError):
                    window = ""  # the installation lacks this window: the host resolves the request at once
            effects.append(EnterCaravan(request_id, details["mode"], window))
            if window:  # the parked runtime stays below; the caravan window is on top
                self._open_window(f"res={window}", False, effects)
                self.state.current_window_name = window  # its text (Dietrich's speech) belongs to it; the pop restores the script's
        elif kind == "debrief":
            effects.append(StartDebrief(request_id, details["mode"], details["debrief_index"], details["summary"]))

    def _set_variable(self, instruction: GlueInstruction) -> None:
        if "=" not in instruction.argument:
            return
        key, value = instruction.argument.split("=", 1)
        if key.casefold() in {"animseq", "textlines", "tentpos", "x", "y", "step", "timecnt"}:
            self.state.variables[key.casefold()] = self._parse_int(value, 0)

    def _conditional(self, command: str) -> bool:
        if not command.startswith(("iftrue", "iffalse")):
            return True
        condition = self._condition()
        return condition if command.startswith("iftrue") else not condition

    def _condition(self) -> bool:
        if self.state.status_mode == 1:
            return (self.state.status_bits & self.state.status_mask) == self.state.status_mask
        if self.state.status_mode == 2:
            return bool(self.state.status_bits & self.state.status_mask)
        return bool(self.state.status_mode)

    @staticmethod
    def _resource_argument(argument: str) -> str:
        return argument.split("=", 1)[1].strip() if argument.casefold().startswith("res=") else argument.strip()

    @staticmethod
    def _parse_resource_id(argument: str) -> int | None:
        value = GlueRuntime._resource_argument(argument)
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_int(value: Any, default: int | None) -> Any:
        try:
            return int(str(value), 10)
        except ValueError:
            return default

    @staticmethod
    def _parse_assignment(value: str) -> tuple[int | None, int | None]:
        if "=" not in value:
            return None, None
        unit_id, count = value.split("=", 1)
        return GlueRuntime._parse_int(unit_id.strip(), None), GlueRuntime._parse_int(count.strip(), None)

    @staticmethod
    def _parse_hex(value: str) -> int:
        digits = ""
        for char in value.strip():
            if char.casefold() in "0123456789abcdef":
                digits += char
            else:
                break
        return int(digits, 16) if digits else 0

    @staticmethod
    def _location(instruction: GlueInstruction) -> str:
        return f"{instruction.location.resource}:{instruction.location.line}"

    def _clear_for_endgame(self) -> None:
        self.state.current = None
        self.state.call_stack.clear()
        self.state.windows.clear()
        self.state.context_stack.clear()
        self.state.pending = None
        self.state.wait_reason = None
        self.state.portrait_animators.clear()
        self.state.portrait_speakers.clear()
        self._clear_dialogue()

    def _clear_dialogue(self) -> None:
        self.state.speech_lines = ()
        self.state.speech_active = False
        self.state.dialogue_lines = ()
        self.state.dialogue_text = ""
        self.state.dialogue_typed = 0
        self.state.dialogue_ms = 0

    def _panel_action(self, action: str | None) -> tuple[GlueEffect, ...]:
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
        if action in ENCOUNTER_ACTIONS:
            return self._encounter_action(action)
        self.state.paused = False
        effects: list[GlueEffect] = []
        if self.state.pending is not None and self.state.pending.kind == "dialogue":
            self.state.dialogue_typed = len(self.state.dialogue_text)
            self.state.dialogue_ms = 0
            self.state.pending = None
            effects.append(StopSpeech())
        effects.append(Diagnostic("panel", f"{action!r} is not yet implemented"))
        if self.state.current is not None and not self.state.current.parked:
            effects.extend(self.step_until_blocked())
        return tuple(effects)

    def _selected_battle_name(self) -> str:
        """The battle of the selected mission record: the fallback when no setbattlescript ran."""
        mission = self.state.selected_mission or getattr(self.campaign, "selected_mission", None)
        if mission is None:
            return ""
        try:
            return str(self.content.mission(mission).values.get("setbattlescript", "")).strip().upper()
        except (KeyError, TypeError, AttributeError):
            return ""

    def _encounter_action(self, action: str) -> tuple[GlueEffect, ...]:
        """Encounter-window buttons (notes/activity_results.md section 3).

        Evade/Decline resume the parked script. Attack! (panel 4) sets the status bits under the
        current mask first. Attack!/Defend then start an encounter battle: a pushed context, no
        debrief, and when it ends the script resumes after its ``waitforresume``.
        """
        pending = self.state.pending
        if pending is not None and pending.kind != "dialogue":
            return ()
        self.state.paused = False
        effects: list[GlueEffect] = []
        if pending is not None:
            self.state.dialogue_typed = len(self.state.dialogue_text)
            self.state.dialogue_ms = 0
            self.state.pending = None
            effects.append(StopSpeech())
        if self.state.current is not None and not self.state.current.parked:
            effects.extend(self.step_until_blocked())
        if self.state.wait_reason != "panel-resume" or self.state.current is None:
            return tuple(effects)  # the click only drained the text: the script is not waiting yet
        self.state.wait_reason = None
        self.state.current.parked = False
        if action == "encounter_evade":
            return (*effects, *self.step_until_blocked())
        if action == "encounter_attack_status":
            self.state.status_bits |= self.state.status_mask
        battle = self.state.battle_script or self._selected_battle_name()
        if not battle:
            effects.append(Diagnostic("panel", "no battle is named for the encounter"))
            return (*effects, *self.step_until_blocked())
        effects.append(StopMusic())
        self._request_battle("encounterplaygame", battle, effects)
        return tuple(effects)

    def _panel_abort(self) -> tuple[GlueEffect, ...]:
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
        self.state.portrait_speakers.clear()
        self._clear_dialogue()
        popped = self.pop_context()
        effects: list[GlueEffect] = [StopSpeech(), StopMusic()]
        if popped is None:
            effects.append(EndGame())
        return tuple(effects)
