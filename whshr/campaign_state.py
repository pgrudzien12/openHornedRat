"""Data-driven campaign progression for the caravan's mission choices.

The original interpreter persists its active glue contexts in a save's STAX
chunk.  The engine keeps the same useful pieces explicitly: the active flow,
the current mission window, completed mission resource ids, and coffers.
"""

from copy import deepcopy
from dataclasses import dataclass, field

from .campaign import build_campaign_graph, parse_window_ui
from .glue import MissionRef
from .glue_content import GlueContent
from .paths import Installation


FIRST_FLOW = "FLOWSCRIPTBP01"
INITIAL_COFFERS = 500

# These animation objects are created by the caravan built-in, not declared by
# STARTCARAVAN. CARAVANCOMMON3 supplies the reading positions; the talking
# positions come from the built-in routine.
CARAVAN_BUILTIN_BITMAPS = (
    {"bitmap": "DietBookCell", "x": 296, "y": 260, "animstartframe": 11,
     "animstopframe": -1, "timecnt": 1, "looptimecnt": 90, "mask": "Mask"},
    {"bitmap": "ReadEyesCell", "x": 312, "y": 208, "animstartframe": 2,
     "animstopframe": -1, "timecnt": 1, "looptimecnt": 30, "mask": "Mask"},
    {"bitmap": "DietMouthCell", "x": 288, "y": 220},
    {"bitmap": "TalkEyesCell", "x": 300, "y": 200},
)

CARAVAN_MODE_WINDOWS = {
    "start": "STARTCARAVAN",
    "select": "CARAVANAFTERMISSION",
    "resume": "CARAVANAFTERENCOUNTER",
    "recruit": "CARAVANRECRUITANDRESUME",
    "recruitnospeech": "CARAVANRECRUITNOSPEECHANDRESUME",
}


def caravan_window_for_mode(mode):
    """Resolve a glue ``gocaravan`` mode to its top-level window resource."""
    mode = str(mode).casefold()
    if mode.startswith("info"):
        return "INFOCARAVAN" + mode[4:].upper()
    return CARAVAN_MODE_WINDOWS.get(mode)


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


def initial_flow(hotspots):
    """Return the flow resource selected by STARTCARAVAN's original hotspot."""
    flows = [hotspot["target"].upper() for hotspot in hotspots
             if hotspot.get("target_kind") == "res" and hotspot.get("target", "").upper().startswith("FLOWSCRIPT")]
    if len(flows) != 1:
        raise ValueError(f"STARTCARAVAN must select exactly one flow, found {flows!r}")
    return flows[0]


def start_caravan_continuation(hotspots):
    """Translate STARTCARAVAN's flow-resource target into the implemented event."""
    initial_flow(hotspots)  # Validate the original target before exposing it.
    return "open_mission_map"


@dataclass
class CampaignState:
    """The portion of original campaign state needed to populate the caravan."""

    graph: dict
    flow: str = FIRST_FLOW
    flow_step: int = 0
    mission_window: str = None
    completed: set[int] = field(default_factory=set)
    coffers: int = INITIAL_COFFERS
    army_units: set[int] = field(default_factory=set)
    march_units: set[int] = field(default_factory=set)
    reinforcements: dict[int, int] = field(default_factory=dict)
    selected_mission: MissionRef | None = None
    taken_missions: set[MissionRef] = field(default_factory=set)
    autosave_state: object = field(default=None, repr=False, compare=False)
    tentpos: int = 0
    hotspots: tuple[dict, ...] = ()
    caravan_bitmaps: tuple[dict, ...] = ()
    caravan_uis: dict[str, dict] = field(default_factory=dict, repr=False, compare=False)
    caravan_continuation: str | None = None
    hints: dict[int, str] = field(default_factory=dict)
    content: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self.mission_window is None:
            self._open_next_window(0)

    def add_cash(self, amount):
        self.coffers += int(amount)

    def is_unit_in_army(self, unit_id):
        return int(unit_id) in self.army_units

    def is_unit_in_march(self, unit_id):
        return int(unit_id) in self.march_units

    def add_reinforcements(self, unit_id, count):
        unit_id = int(unit_id)
        self.reinforcements[unit_id] = self.reinforcements.get(unit_id, 0) + int(count)

    def join_mission(self, unit_id):
        self.march_units.add(int(unit_id))

    def leave_mission(self, unit_id):
        self.march_units.discard(int(unit_id))

    def select_mission(self, mission):
        self.selected_mission = mission

    def mark_mission_taken(self, mission):
        self.taken_missions.add(mission)

    def autosave(self, runtime_state):
        self.autosave_state = deepcopy(runtime_state)

    @property
    def missions(self):
        return eligible_missions(self.graph["mission_windows"].get(self.mission_window, ()), self.completed)

    def _open_next_window(self, start):
        steps = self.graph["flow_scripts"].get(self.flow, ())
        for index in range(start, len(steps)):
            if steps[index]["action"] == "set_tentpos":
                self.tentpos = steps[index]["pos"]
            if steps[index]["action"] == "add_window":
                self.flow_step = index
                self.mission_window = steps[index]["window"]
                return
        raise ValueError(f"flow {self.flow!r} has no mission window at or after step {start}")

    @property
    def scroll_count(self):
        return caravan_scroll_count(len(self.missions))

    @property
    def caravan_bitmap_specs(self):
        """Window data plus the animation objects created by the caravan built-in."""
        specs = {bitmap["bitmap"].casefold(): bitmap for bitmap in CARAVAN_BUILTIN_BITMAPS}
        specs.update({bitmap.get("bitmap", "").casefold(): bitmap for bitmap in self.caravan_bitmaps})
        return specs

    @property
    def caravan_background(self):
        """The active caravan window's first bitmap is its painted backdrop."""
        return next((bitmap["bitmap"] for bitmap in self.caravan_bitmaps if "bitmap" in bitmap), None)

    def activate_caravan_mode(self, mode):
        """Install the selected caravan window's projected controls and artwork."""
        window = caravan_window_for_mode(mode)
        ui = self.caravan_uis.get(window) if window else None
        if ui is None:
            return False
        self.hotspots = tuple(ui["hotspots"])
        self.caravan_bitmaps = tuple(ui["bitmaps"])
        return True

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
    def from_installation(cls, installation, content=None):
        game = installation if isinstance(installation, Installation) else Installation(installation)
        content = content or GlueContent(game)
        wnd = content.resources
        tables = {name: content.strings(name) for name in ("BRTXT", "BKTXT", "GMTXT")}
        hints = tables["BRTXT"]
        caravan_uis = {}
        for window in set(CARAVAN_MODE_WINDOWS.values()):
            caravan_uis[window] = parse_window_ui(wnd, window)
        for mode in ("infobpc", "inforea", "inforec", "infowed", "infosza", "infoszb", "infoene",
                     "infoena", "infola", "infolb", "infobma"):
            window = caravan_window_for_mode(mode)
            caravan_uis[window] = parse_window_ui(wnd, window)
        caravan_ui = caravan_uis["STARTCARAVAN"]
        hotspots = tuple(caravan_ui["hotspots"])
        return cls(build_campaign_graph(str(game.root), wnd=wnd, string_tables=tables),
                   flow=initial_flow(hotspots), hotspots=hotspots,
                   caravan_bitmaps=tuple(caravan_ui["bitmaps"]), caravan_uis=caravan_uis,
                   caravan_continuation=start_caravan_continuation(hotspots), hints=hints, content=content)

    @classmethod
    def single_mission(cls, briefing):
        """Compatibility state for focused tests and development-only briefings."""
        mission = {"name_id": 0, "name": briefing.battle_id.name.upper(),
                   "battle": briefing.battle_id.name.upper(), "briefing_key": "test.0", "briefing": briefing}
        return cls({"flow_scripts": {FIRST_FLOW: ({"action": "add_window", "window": "TEST"},)},
                    "mission_windows": {"TEST": [mission]}}, caravan_continuation="open_mission_map")
