# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Mission briefing projection from the shared typed glue-content repository.

Stdlib-only; the briefing scene presents this data without opening original files.
"""

from collections.abc import Mapping
from os import PathLike
from typing import Any

from .campaign import (Graph, Mission, Strings, build_campaign_graph, parse_window_portrait,
                       parse_window_ui)
from .glue import GlueProgram, GlueResource, MissionRef, parse_glue_resource, parse_glue_resources
from .glue_content import GlueContent
from .paths import Installation

TEXT_COMMANDS = ("playtext", "queuetoplaytext")


def _find_mission(campaign_graph: Graph, mission_ref: MissionRef | str) -> Mission:
    """Return the exact mission record named by its stable campaign-record key."""
    briefing_key = mission_ref.key if isinstance(mission_ref, MissionRef) else mission_ref
    for mission_list in campaign_graph["mission_windows"].values():
        for mission in mission_list:
            if mission.get("mission_ref") == mission_ref or mission.get("briefing_key") == briefing_key:
                return mission
    raise ValueError(f"no campaign mission record has briefing key {briefing_key!r}")


def _briefing_layout(wnd: Mapping[str, Any], glue_text: GlueResource | str, strings: Strings) -> dict[str, Any]:
    """Interpret the display-only part of one briefing glue program.

    This is intentionally a small, explicit subset of the glue interpreter:
    the commands which create its map, speakers, dialogue batches, and map
    overlays.  Battle/troop-selection commands stay scene transitions.
    """
    resources = (wnd if all(not isinstance(value, str) for value in wnd.values())
                 else parse_glue_resources(wnd))
    program = glue_text if not isinstance(glue_text, str) else parse_glue_resource("<briefing>", glue_text)
    map_ui: dict[str, Any] | None = None
    portraits: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    color: str | None = None
    speaker: str | None = None
    queued: list[tuple[int, str]] = []
    text_lines, tentpos, animseq = 1, None, 1
    midi: list[str] = []
    if not isinstance(program, GlueProgram):
        raise ValueError("a briefing must be a glue program, not a window")
    for instruction in program.instructions:
        command, argument = instruction.command, instruction.argument
        if command == "openwindow" and argument.lower().startswith("res="):
            map_ui = parse_window_ui(resources, argument[4:])
        elif command == "opensubwindow" and argument.lower().startswith("res="):
            name = argument[4:]
            portrait = parse_window_portrait(resources, name)
            if portrait is not None:
                portraits.append(portrait)
        elif command == "settextcolor":
            color = argument
        elif command == "playmidi":
            midi.append(argument)
        elif command == "set" and argument.startswith("textlines="):
            text_lines = int(argument[10:])
        elif command == "set" and argument.startswith("tentpos="):
            tentpos = int(argument[8:])
        elif command == "set" and argument.startswith("animseq="):
            animseq = int(argument[8:])
        elif command == "applyseq" and argument.lower().startswith("res="):
            # The preceding ``set:animseq=1`` tells the original renderer who
            # is talking.  The dialogue's own colour is still authoritative.
            speaker = argument[4:].upper()
        elif command == "addanimobject" and argument.lower().startswith("res="):
            overlay = parse_window_ui(resources, argument[4:])
            objects.append({"after_turn": len(turns), "bitmaps": overlay["bitmaps"]})
        elif command in TEXT_COMMANDS and argument.startswith("res="):
            text_id = int(argument[4:])
            text = strings.get(text_id)
            if text is not None:
                queued.append((text_id, text))
            if command == "playtext" and queued:
                # ``queuetoplaytext`` schedules individual BRTXT strings;
                # ``playtext`` starts that queue.  They are not one large
                # caption: scripts set ``textlines=2`` and the strings are
                # often complete, paragraph-length sentences.
                turns.extend({"speaker": speaker, "speaker_color": color, "lines": [line],
                              "text_id": text_id, "text_lines": text_lines, "animseq": animseq}
                             for text_id, line in queued)
                queued = []
    if map_ui is not None:
        for text in map_ui["texts"]:
            if isinstance(text.get("res"), int):
                text["text"] = strings.get(text["res"], "")
    return {"map": map_ui, "portraits": portraits, "objects": objects, "turns": turns,
            "midi": midi, "tentpos": tentpos, "text_lines": text_lines,
            "strings": strings}


def load_briefing(installation: Installation | str | PathLike[str], briefing_key: MissionRef | str,
                  content: GlueContent | None = None) -> dict[str, Any]:
    """Build a briefing from the exact mission record that opened it."""
    game = installation if isinstance(installation, Installation) else Installation(installation)
    if content is None:
        from .glue_content import GlueContent
        content = GlueContent(game)
    wnd = content.resources
    tables = {name: content.strings(name) for name in ("BRTXT", "BKTXT", "GMTXT")}
    campaign_graph = build_campaign_graph(str(game.root), wnd=wnd, string_tables=tables)
    mission = _find_mission(campaign_graph, briefing_key)
    glue_text = wnd.get((mission.get("brief_script") or "").upper(), parse_glue_resource("<empty>", ""))
    strings = tables["BRTXT"]
    layout = _briefing_layout(wnd, glue_text, strings)
    return {
        "battle": mission.get("battle", "").upper(),
        "title": mission.get("name") or mission.get("battle", "").upper(),
        # Keep the flattened form for callers which only need a transcript.
        "lines": [{"speaker_color": turn["speaker_color"], "text": line}
                  for turn in layout["turns"] for line in turn["lines"]],
        **layout,
    }
