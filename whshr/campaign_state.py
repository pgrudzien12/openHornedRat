"""Data-driven campaign progression for the caravan's mission choices.

The original interpreter persists its active glue contexts in a save's STAX
chunk.  The engine keeps the same useful pieces explicitly: the active flow,
the current mission window, completed mission resource ids, and coffers.
"""

from dataclasses import dataclass, field


FIRST_FLOW = "FLOWSCRIPTBP01"
INITIAL_COFFERS = 500


def eligible_missions(missions, completed):
    """Return mission entries whose WND dependency gates currently pass."""
    completed = set(completed)
    return tuple(
        mission for mission in missions
        if (mission.get("depend") is None or mission["depend"] in completed)
        and (mission.get("inactivedepend") is None or mission["inactivedepend"] not in completed)
    )


@dataclass
class CampaignState:
    """The portion of original campaign state needed to populate the caravan."""

    graph: dict
    flow: str = FIRST_FLOW
    flow_step: int = 0
    mission_window: str = None
    completed: set[int] = field(default_factory=set)
    coffers: int = INITIAL_COFFERS

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

    def complete(self, mission):
        """Record a selected/completed mission and advance to its next choice window."""
        self.completed.add(mission["name_id"])
        replacement = mission.get("replacescript")
        if replacement:
            self.flow = replacement
            self._open_next_window(0)
        else:
            self._open_next_window(self.flow_step + 1)

    @classmethod
    def single_mission(cls, briefing):
        """Compatibility state for focused tests and development-only briefings."""
        mission = {"name_id": 0, "name": briefing.battle_id.name.upper(),
                   "battle": briefing.battle_id.name.upper(), "briefing": briefing}
        return cls({"flow_scripts": {FIRST_FLOW: ({"action": "add_window", "window": "TEST"},)},
                    "mission_windows": {"TEST": [mission]}})
