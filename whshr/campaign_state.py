"""Data-driven campaign progression for the caravan's mission choices.

The original interpreter persists its active glue contexts in a save's STAX
chunk.  The engine keeps the same useful pieces explicitly: the active flow,
the current mission window, completed mission resource ids, and coffers.
"""

from dataclasses import dataclass, field

from .campaign import build_campaign_graph, load_wnd_rcdata, parse_window_hotspots
from .legacy import module
from .paths import Installation


FIRST_FLOW = "FLOWSCRIPTBP01"
INITIAL_COFFERS = 500


def mission_visible(missions, mission, taken):
    """Is ``mission`` offered in its window right now?

    ``taken`` holds the name ids of missions already committed to.  ``depend`` and
    ``inactivedepend`` refer to other missions of the *same* window; an id that is not
    in the window makes the gate a no-op (``notes/campaign.md`` section 7.2).
    """
    if mission["name_id"] in taken:
        return False
    for key in ("depend", "inactivedepend"):
        target_id = mission.get(key)
        if not target_id:
            continue
        target = next((other for other in missions if other["name_id"] == target_id), None)
        if target is None:
            return True
        return target_id in taken if key == "depend" else not mission_visible(missions, target, taken)
    return True


def eligible_missions(missions, taken):
    """Return the mission entries a window offers once ``taken`` have been committed to."""
    taken = set(taken)
    return tuple(mission for mission in missions if mission_visible(missions, mission, taken))


def caravan_scroll_count(mission_count):
    """Scrolls on Dietrich's desk: ``CarScroll3/2/1`` carry ``depend`` 2/3/4 (section 7.4)."""
    return min(max(mission_count - 1, 0), 3)


@dataclass
class CampaignState:
    """The portion of original campaign state needed to populate the caravan."""

    graph: dict
    flow: str = FIRST_FLOW
    flow_step: int = 0
    mission_window: str = None
    completed: set[int] = field(default_factory=set)
    coffers: int = INITIAL_COFFERS
    hotspots: tuple[dict, ...] = ()
    hints: dict[int, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.mission_window is None:
            self._open_next_window(0)

    @property
    def missions(self):
        return eligible_missions(self.graph["mission_windows"].get(self.mission_window, ()), self.completed)

    def _open_next_window(self, start):
        steps = self.graph["flow_scripts"].get(self.flow, ())
        for index in range(start, len(steps)):
            if steps[index]["action"] == "add_window":
                self.flow_step = index
                self.mission_window = steps[index]["window"]
                return
        raise ValueError(f"flow {self.flow!r} has no mission window at or after step {start}")

    @property
    def scroll_count(self):
        return caravan_scroll_count(len(self.missions))

    @property
    def map_portrait_window(self):
        """The data-defined portrait sub-window opened by the active flow."""
        steps = self.graph["flow_scripts"].get(self.flow, ())[:self.flow_step + 1]
        for step in reversed(steps):
            if step["action"] == "open_subwindow":
                return self.graph.get("portrait_windows", {}).get(step["window"])
        return None

    def complete(self, mission):
        """Record a chosen mission.

        A ``replacescript`` switches flow.  Otherwise the mission is marked taken and the
        player stays on the same map window, with one row fewer, unless the mission has
        ``releaseflag`` or nothing is left on offer.
        """
        self.completed.add(mission["name_id"])
        replacement = mission.get("replacescript")
        if replacement:
            self.flow = replacement
            self._open_next_window(0)
        elif mission.get("releaseflag") or not self.missions:
            self._open_next_window(self.flow_step + 1)

    def hotspot(self, hint_id):
        """Return the original hotspot that advertises ``hint_id``."""
        return next((hotspot for hotspot in self.hotspots if hotspot.get("res") == hint_id), None)

    def hint(self, hint_id, *format_args):
        text = self.hints.get(hint_id, "")
        return text % format_args if format_args else text

    @classmethod
    def from_installation(cls, installation):
        game = installation if isinstance(installation, Installation) else Installation(installation)
        wnd = load_wnd_rcdata(game.file_dir("DLL", "WND.DLL"))
        hints = module("pe_missions").load_strings(str(game.file_dir("DLL", "BRTXT.DLL")))
        return cls(build_campaign_graph(str(game.root)),
                   hotspots=tuple(parse_window_hotspots(wnd, "STARTCARAVAN")), hints=hints)

    @classmethod
    def single_mission(cls, briefing):
        """Compatibility state for focused tests and development-only briefings."""
        mission = {"name_id": 0, "name": briefing.battle_id.name.upper(),
                   "battle": briefing.battle_id.name.upper(), "briefing": briefing}
        return cls({"flow_scripts": {FIRST_FLOW: ({"action": "add_window", "window": "TEST"},)},
                    "mission_windows": {"TEST": [mission]}})
