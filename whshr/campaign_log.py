"""Campaign session logging: JSON Lines recording, stdlib-only (no frontend import).

`notes/engine_architecture.md`, "Campaign session log" documents the format. One JSON object per
line, each carrying `time` (wall-clock UTC, informational) and `type`. Like `whshr.battle_log`, it
never crashes the game: `CampaignLogger(path=None)` is a no-op recorder and any `OSError` opening or
writing the file disables it silently. It only observes -- the scene machine, the scene asset access
and `GlueScene` call it at points that run identically without it.

Deliberately NOT logged: pointer/key events, redraws, frame counts, animation progress, dialogue
typing progress, and (unless `trace_glue` is on) per-instruction glue traces.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

FORMAT_VERSION = 1
TRACE_ENV = "WHSHR_TRACE_GLUE"


def default_log_path(log_dir, when=None):
    """`<log_dir>/campaign-YYYYmmdd-HHMMSS.jsonl`."""
    when = when or datetime.now()
    return Path(log_dir) / f"campaign-{when:%Y%m%d-%H%M%S}.jsonl"


def format_diagnostic(location, message):
    """Same text the frontend prints to stderr for a glue diagnostic."""
    return f"glue: {location}: {message}"


class CampaignLogger:
    """Appends JSON Lines rows to `path`, flushing after every write. `path=None` is a no-op recorder.

    `trace_glue=True` (environment `WHSHR_TRACE_GLUE`) additionally writes one `glue_instruction` row
    per executed glue instruction -- high volume, off by default.
    """

    def __init__(self, path=None, trace_glue=None):
        self.path = Path(path) if path is not None else None
        self.trace_glue = bool(os.environ.get(TRACE_ENV)) if trace_glue is None else trace_glue
        self._file = None
        self.enabled = False
        self._last = None
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._file = open(self.path, "w", encoding="utf-8")
                self.enabled = True
            except OSError:
                self._file = None
                self.enabled = False

    def write(self, type_, **fields):
        """One row. A row identical to the previous one (apart from `time`) is dropped."""
        if not self.enabled:
            return
        row = {"type": type_, **fields}
        try:
            key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
            if key == self._last:
                return
            self._last = key
            row["time"] = datetime.now(timezone.utc).isoformat()
            self._file.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str))
            self._file.write("\n")
            self._file.flush()
        except (OSError, TypeError, ValueError):
            self.enabled = False
            self.close()

    def close(self):
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
        self.enabled = False

    # -- session -----------------------------------------------------------------------------
    def session_start(self, **options):
        self.write("session_start", format_version=FORMAT_VERSION, options=options)

    def session_end(self, reason, **fields):
        self.write("session_end", reason=reason, **fields)

    # -- scene machine -----------------------------------------------------------------------
    def scene_change(self, old, new, reason):
        self.write("scene_change", **{"from": _scene_name(old), "to": _scene_name(new), "reason": reason})
        if old is not None and _is_battle(old):
            self.write("battle_result", **_battle_fields(old), result=_battle_result(old))

    def scene_entered(self, scene):
        """Called once the scene's `enter` ran (a battle's own log path exists only from then on)."""
        if _is_battle(scene):
            self.write("battle_start", **_battle_fields(scene))

    def quit(self, reason):
        self.write("quit", reason=reason)

    def asset_failed(self, identifier, error):
        self.write("asset_failed", asset=str(identifier), error=f"{type(error).__name__}: {error}")


def _scene_name(scene):
    return type(scene).__name__ if scene is not None else None


def _is_battle(scene):
    return hasattr(scene, "battle_id") and hasattr(scene, "logger")


def _battle_fields(scene):
    logger = getattr(scene, "logger", None)
    path = getattr(logger, "path", None)
    return {"battle": str(scene.battle_id), "battle_log": str(path) if path is not None else None}


def _battle_result(scene):
    battle = getattr(scene, "battle", None)
    result = getattr(battle, "result", None)
    return str(result) if result is not None else None


def campaign_summary(campaign):
    """Small comparable summary of a `CampaignState` (None when there is none)."""
    if campaign is None:
        return None
    return {
        "coffers": campaign.coffers, "flow": campaign.flow, "flow_step": campaign.flow_step,
        "mission_window": campaign.mission_window,
        "completed": sorted(campaign.completed), "army": len(campaign.army_units),
        "march": len(campaign.march_units),
    }


class GlueWatcher:
    """Turns the state changes of one `GlueRuntime` into rows.

    `GlueScene` calls `update(runtime, effects)` after every runtime call (start, input, activity
    result, tick) with the effects it produced. Everything logged is a change compared with the
    previous call, so a wait lasting a million frames is one `wait_started` and one `wait_resolved`,
    and a tick that changes nothing writes nothing. Script enter/return rows are derived from the call
    stack observed at those points, so a subroutine that starts and finishes within one run of the
    interpreter is not seen (use `WHSHR_TRACE_GLUE` for that).
    """

    def __init__(self, logger, scene_name, campaign=None):
        self.logger = logger
        self.scene_name = scene_name
        self.campaign = campaign
        self._stack = []
        self._wait = None
        self._pending = None
        self._mission = None
        self._summary = campaign_summary(campaign)
        self._trace_seen = 0

    def update(self, runtime, effects=()):
        try:
            self._update(runtime, effects)
        except Exception:  # logging must never change behaviour
            self.logger.enabled = False

    def _update(self, runtime, effects):
        log, state = self.logger, runtime.state
        if not log.enabled:
            return
        if log.trace_glue:
            self._trace(state)
        stack = [frame.program for frame in state.call_stack]
        if state.current is not None:
            stack.append(state.current.program)
        common = 0
        while common < min(len(stack), len(self._stack)) and stack[common] == self._stack[common]:
            common += 1
        for depth in range(len(self._stack) - 1, common - 1, -1):
            log.write("script_return", program=self._stack[depth], depth=depth)
        for depth in range(common, len(stack)):
            log.write("script_enter", program=stack[depth], depth=depth)
        self._stack = stack
        for effect in effects:
            self._effect(runtime, effect)
        pending = (state.pending.request_id, state.pending.kind) if state.pending is not None else None
        if pending != self._pending:
            if self._pending is not None:
                log.write("wait_resolved", kind=self._pending[1], request_id=self._pending[0])
            self._pending = pending
        # The parked instruction (program and position) tells two consecutive waits of the same kind apart.
        wait = ((state.wait_reason, stack[-1] if stack else None, state.current.pc if state.current else None)
                if state.wait_reason is not None else None)
        if wait != self._wait:
            if self._wait is not None:
                log.write("wait_resolved", kind=self._wait[0], program=self._wait[1])
            if wait is not None:
                log.write("wait_started", kind=wait[0], program=wait[1])
            self._wait = wait
        mission = state.selected_mission
        if mission != self._mission:
            self._mission = mission
            if mission is not None:
                log.write("mission_selected", window=mission.window, record_index=mission.record_index)
        summary = campaign_summary(self.campaign)
        if summary != self._summary:
            log.write("campaign_state", before=self._summary, after=summary)
            self._summary = summary

    def _trace(self, state):
        if self._trace_seen > len(state.trace):
            self._trace_seen = 0
        for item in state.trace[self._trace_seen:]:
            self.logger.write("glue_instruction", location=item.location, command=item.command,
                              argument=item.argument)
        self._trace_seen = len(state.trace)

    def _effect(self, runtime, effect):
        log, name = self.logger, type(effect).__name__
        if name == "Diagnostic":
            log.write("diagnostic", text=format_diagnostic(effect.location, effect.message),
                      location=effect.location)
        elif name == "OpenWindow":
            log.write("screen_load", window=effect.name, parent=effect.parent, palette=effect.palette_id,
                      scene=self.scene_name, program=self._program(runtime),
                      location=self._open_location(runtime, effect.name), **self._assets(runtime, effect.name))
        elif name == "CloseWindow":
            log.write("window_closed", window=effect.name)
        elif name in ("StartMovie", "StartBattle", "StartDialogue", "EnterCaravan", "StartDebrief"):
            kind = "caravan" if name == "EnterCaravan" else name[5:].lower()
            log.write("activity_request", kind=kind, **vars(effect))
        elif name == "HotspotSpeech":
            log.write("hotspot_speech", string_id=effect.string_id, count=effect.count)
        elif name in ("PlayMusic", "StopMusic", "Autosave", "EndGame"):
            log.write("glue_effect", effect=name, **vars(effect))

    @staticmethod
    def _program(runtime):
        return runtime.state.current.program if runtime.state.current is not None else None

    @staticmethod
    def _open_location(runtime, window):
        for item in reversed(runtime.state.trace[-200:]):
            if item.command in ("openwindow", "opensubwindow") and item.argument.split("=")[-1].upper() == window.upper():
                return item.location
        return None

    @staticmethod
    def _assets(runtime, window):
        """Bitmaps and music named by the window definition (empty when it cannot be read)."""
        bitmaps, music = [], []
        try:
            for record in runtime.content.window(window).records:
                for item in record.fields:
                    if item.command == "setbitmap":
                        bitmaps.append(item.argument)
                    elif "midi" in item.command or "midi" in item.argument.split("=")[0].lower():
                        music.append(item.argument)
        except Exception:
            pass
        return {"bitmaps": bitmaps, "music": music}
