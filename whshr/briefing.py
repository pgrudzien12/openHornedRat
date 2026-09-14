"""Mission briefing text: title and spoken lines for one battle, from the campaign glue scripts.

Reuses whshr.campaign's WND.DLL glue-script parser rather than re-deriving the campaign flow.
Stdlib-only; the briefing scene presents this data without opening any original file itself.
"""

from .campaign import build_campaign_graph, load_wnd_rcdata, parse_glue_lines
from .legacy import module
from .paths import Installation

TEXT_COMMANDS = ("playtext", "queuetoplaytext")


def _find_mission(campaign_graph, battle):
    """Return the first mission window entry whose battle matches, case-insensitively."""
    battle = battle.upper()
    for mission_list in campaign_graph["mission_windows"].values():
        for mission in mission_list:
            if (mission.get("battle") or "").upper() == battle:
                return mission
    raise ValueError(f"no campaign mission references battle {battle!r}")


def _spoken_lines(glue_text, strings):
    """Yield {speaker_color, text} for every playtext/queuetoplaytext command, in script order."""
    color = None
    for command, argument in parse_glue_lines(glue_text):
        if command == "settextcolor":
            color = argument
        elif command in TEXT_COMMANDS and argument.startswith("res="):
            text = strings.get(int(argument[4:]))
            if text is not None:
                yield {"speaker_color": color, "text": text}


def load_briefing(installation, battle):
    """Build the title and spoken briefing lines for one battle from the original campaign scripts."""
    game = installation if isinstance(installation, Installation) else Installation(installation)
    campaign_graph = build_campaign_graph(str(game.root))
    mission = _find_mission(campaign_graph, battle)
    wnd = load_wnd_rcdata(game.file_dir("DLL", "WND.DLL"))
    glue_text = wnd.get((mission.get("brief_script") or "").upper(), "")
    strings = module("pe_missions").load_strings(str(game.file_dir("DLL", "BRTXT.DLL")))
    return {
        "battle": battle.upper(),
        "title": mission.get("name") or battle.upper(),
        "lines": list(_spoken_lines(glue_text, strings)),
    }
