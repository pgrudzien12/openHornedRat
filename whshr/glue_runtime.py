"""Pure, deterministic interpreter for typed ``[RUN]`` glue programs.

This module deliberately has no frontend imports.  It implements the shared
script-state boundary described by ``notes/glue_interpreter.md``; a host turns
its effects into windows, audio, movies, battles, or built-in widgets and later
calls :meth:`GlueRuntime.resume`.
"""

from copy import deepcopy
from dataclasses import dataclass, field

from .glue import GlueInstruction


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
    debrief_index: int = 0
    palette_id: int = 0
    context_stack: list[ContextSnapshot] = field(default_factory=list)
    wait_reason: str | None = None
    pending: PendingRequest | None = None
    next_request_id: int = 1
    trace: list[InstructionTrace] = field(default_factory=list)


class GlueRuntime:
    """Execute programs from one :class:`~whshr.glue_content.GlueContent` repository."""

    MAX_CALL_DEPTH = 16
    MAX_WINDOWS = 8
    MAX_CONTEXT_DEPTH = 16

    def __init__(self, content, campaign=None, speech_enabled=True):
        self.content = content
        self.campaign = campaign
        self.speech_enabled = speech_enabled
        self.state = GlueRuntimeState()

    def start(self, program):
        """Start a fresh named program and run until it blocks or ends."""
        self.state = GlueRuntimeState(current=ScriptFrame(str(program).upper()))
        return self.step_until_blocked()

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
        return ()

    def handle(self, input_):
        """Resume a parked script when its explicit wait event arrives."""
        if not isinstance(input_, GlueInput):
            raise TypeError("handle expects GlueInput")
        if input_.kind == "dialogue-drain" and self.state.pending is not None and self.state.pending.kind == "dialogue":
            self.state.pending = None
            return (StopSpeech(), *self.step_until_blocked())
        expected = self.state.wait_reason
        if expected is None or input_.kind != expected:
            return ()
        self.state.wait_reason = None
        if self.state.current is not None:
            self.state.current.parked = False
        return self.step_until_blocked()

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
        elif command in ("waitforrelease", "waitforresume"):
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
            effects.append(Autosave())
        elif command == "setdebrief":
            self._set_debrief(argument)
        elif command in ("debrief", "debriefwithsummary", "iftruedebrief", "iffalsedebrief",
                         "iftruedebriefwithsummary", "iffalsedebriefwithsummary"):
            if self._conditional(command):
                self._request_debrief(command, argument, effects)
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
        effects.append(OpenWindow(name, parent, palette))

    def _close_window(self, argument, effects):
        name = self._resource_argument(argument)
        self.state.windows = [window for window in self.state.windows if window.name != name]
        effects.append(CloseWindow(name))

    def _add_object(self, argument, animated, effects):
        name = self._resource_argument(argument)
        target = next((window for window in self.state.windows if window.name == self.state.current_window_name), None)
        if target is None or not name:
            return
        try:
            self.content.window(name)
        except (KeyError, TypeError):
            return
        target.objects.append(name)
        effects.append(UpdateWindow(target.name))
        if animated:
            self.state.wait_reason = "animation-finished"
            self.state.current.parked = True

    def _remove_object(self, argument, effects):
        target = next((window for window in self.state.windows if window.name == self.state.current_window_name), None)
        if target is None:
            return
        if argument.casefold() == "bitmap" and target.objects:
            target.objects.pop()
        effects.append(UpdateWindow(target.name))

    def _dialogue(self, argument, queued, effects):
        string_id = self._parse_resource_id(argument)
        if string_id is None:
            return
        if queued and not self.speech_enabled:
            return
        self._request("dialogue", effects, string_id=string_id, queued=queued)

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
