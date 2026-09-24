"""Data-driven campaign progression for the caravan's mission choices.

The original interpreter persists its active glue contexts in a save's STAX
chunk.  The engine keeps the same useful pieces explicitly: the active flow,
the current mission window, completed mission resource ids, and coffers.
"""

from copy import deepcopy
from dataclasses import dataclass, field

from .campaign import build_campaign_graph, parse_window_ui
from .glue import MissionRecord, MissionRef
from .glue_content import GlueContent
from .paths import Installation
from . import roster
from .roster import load_company


FIRST_FLOW = "FLOWSCRIPTBP01"
INITIAL_COFFERS = 500

CARAVAN_MODE_WINDOWS = {
    "start": "STARTCARAVAN",
    "select": "CARAVANAFTERMISSION",
    "resume": "CARAVANAFTERENCOUNTER",
    "recruit": "CARAVANRECRUITANDRESUME",
    "recruitnospeech": "CARAVANRECRUITNOSPEECHANDRESUME",
}


def caravan_window(mode):
    """The caravan window a ``gocaravan:<mode>`` request names, or ``None`` for an unknown name
    (notes/glue_interpreter.md section 7.3: ``info<letters>`` names ``InfoCaravan<letters>``; an
    unknown name is resumed at once).  The window may still be missing from a given installation."""
    mode = str(mode).casefold()
    name = CARAVAN_MODE_WINDOWS.get(mode)
    if name is None and mode.startswith("info") and len(mode) > 4:
        name = "INFOCARAVAN" + mode[4:].upper()
    return name


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


def _record_gates(record):
    """Return ``(name_id, gates)`` of one typed ``[MISSION]`` record (``gates``: depend/inactivedepend)."""
    entry = {}
    for field_ in record.fields:
        if field_.command != "set" or "=" not in field_.argument:
            continue
        key, value = field_.argument.split("=", 1)
        key = key.strip().casefold()
        if key in ("res", "depend", "inactivedepend"):
            try:
                entry[key] = int(value.split(None, 1)[0])
            except (ValueError, IndexError):
                pass
    return entry


def offered_refs(records, taken):
    """Return the ``MissionRef`` of every mission record a window offers, in window order.

    ``records`` are the window's typed ``[MISSION]`` records and ``taken`` the set of committed
    ``MissionRef``.  A taken mission is hidden; ``depend`` / ``inactivedepend`` follow
    :func:`mission_visible` (notes/mission_selection.md, notes/campaign.md section 7.2).
    """
    taken = set(taken)
    entries = []
    for record in records:
        gates = _record_gates(record)
        gates["name_id"] = gates.pop("res", None)
        gates["ref"] = record.mission_ref
        entries.append(gates)
    taken_ids = {entry["name_id"] for entry in entries if entry["ref"] in taken and entry["name_id"] is not None}
    return tuple(entry["ref"] for entry in entries
                 if entry["ref"] not in taken and mission_visible(entries, entry, taken_ids))


def initial_flow(hotspots):
    """Return the flow resource selected by STARTCARAVAN's original hotspot."""
    flows = [hotspot["target"].upper() for hotspot in hotspots
             if hotspot.get("target_kind") == "res" and hotspot.get("target", "").upper().startswith("FLOWSCRIPT")]
    if len(flows) != 1:
        raise ValueError(f"STARTCARAVAN must select exactly one flow, found {flows!r}")
    return flows[0]


@dataclass
class CampaignState:
    """The portion of original campaign state needed to populate the caravan."""

    graph: dict
    flow: str = FIRST_FLOW
    # Every flow the campaign has run, oldest first, ending with ``flow``: a replacement flow carries
    # on inside the map its predecessors built, so resuming replays the chain (notes/mission_selection.md §10).
    flow_history: list[str] = field(default_factory=list)
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
    hints: dict[int, str] = field(default_factory=dict)
    content: object = field(default=None, repr=False, compare=False)
    company: tuple = field(default_factory=tuple)
    # The engine's own save directory (never the original installation's SAVE/, GEI7e); None
    # (e.g. focused tests, --glue-program runs) means troop selection stays in-memory only.
    save_dir: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if not self.flow_history or self.flow_history[-1] != self.flow:
            self.flow_history.append(self.flow)
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

    def commit_troop_selection(self, deployment):
        """Apply a confirmed troop_selection.Deployment; notes/troop_selection.md §5.3."""
        self.coffers += deployment.money_delta
        self.march_units = set(deployment.units)
        self.army_units = set(deployment.hired)
        if self.save_dir is not None:
            # notes/troop_selection.md §5.3 points 3, 5: durable ARMY.MRC/MARCH.MRC, written to
            # the engine's own save directory, never the original installation
            # (notes/glue_engine_integration.md GEI7e). Reinforcements have no standalone-file
            # home in the original either (only the savegame.N RIFF's RMYI chunk carries them,
            # notes/campaign.md §4.5), so they stay in-memory until GEI14 defines that writer.
            hired = {whoami: whoami in self.army_units for whoami in {r.whoami for r in self.company}}
            roster.write_company(self.save_dir, self.company, hired)
            roster.write_march(self.save_dir, deployment.units, self.company)

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
    def map_portrait_window(self):
        """The data-defined portrait sub-window opened by the active flow."""
        steps = self.graph["flow_scripts"].get(self.flow, ())[:self.flow_step + 1]
        for step in reversed(steps):
            if step["action"] == "open_subwindow":
                return self.graph.get("portrait_windows", {}).get(step["window"])
        return None

    def offered_missions(self, records):
        """The refs of the typed mission ``records`` of one window that are on offer now."""
        return offered_refs(records, self.taken_missions)

    def is_mission_taken(self, mission_ref):
        """Has this mission already been committed to or finished (so it is no longer offered)?"""
        return mission_ref in self.taken_missions

    def wait_already_released(self, flow, ordinal):
        """Was the ``ordinal``-th (0-based) ``waitforrelease`` of ``flow`` already passed?

        A flow script restarted at the campaign's saved position replays its set-up and skips the
        parks the campaign has moved beyond (``flow_step`` is the step of the window now offered),
        so the map comes back on the current mission window (notes/mission_selection.md section 3).
        """
        if flow in self.flow_history[:-1]:
            return True
        if flow != self.flow:
            return False
        steps = self.graph["flow_scripts"].get(flow, ())
        waits = [index for index, step in enumerate(steps) if step["action"] == "wait_player_choice"]
        return ordinal < len(waits) and waits[ordinal] < self.flow_step

    def _anything_offered(self):
        """Does the current mission window still offer a row?  Keyed by mission record, because the
        same name id recurs in several windows (a finished one must not hide another window's row)."""
        if self.content is not None:
            try:
                records = [record for record in self.content.window(self.mission_window).records
                           if isinstance(record, MissionRecord)]
            except (KeyError, TypeError):
                records = None
            if records is not None:
                return bool(self.offered_missions(records))
        return bool(self.missions)

    def complete(self, mission):
        """Record a chosen mission and say how the flow continues.

        A ``replacescript`` switches flow.  Otherwise the mission is marked taken and the
        player stays on the same map window, with one row fewer, unless the mission has
        ``releaseflag`` or nothing is left on offer.  Returns ``(replacement, released)``:
        the replacement flow name (or None) and whether the parked flow script resumes.
        """
        self.completed.add(mission["name_id"])
        if mission.get("mission_ref") is not None:
            self.taken_missions.add(mission["mission_ref"])
        replacement = mission.get("replacescript")
        if replacement:
            self.flow = replacement
            self.flow_history.append(replacement)
            self._open_next_window(0)
            return replacement, False
        if mission.get("releaseflag") or not self._anything_offered():
            self._open_next_window(self.flow_step + 1)
            return None, True
        return None, False

    def complete_mission(self, mission_ref):
        """Complete the mission a glue ``MissionRef`` names (the mission release step,
        notes/activity_results.md §6.1); see :meth:`complete`.  An unknown reference is ignored."""
        for window in self.graph["mission_windows"].values():
            for mission in window:
                if mission.get("mission_ref") == mission_ref and "name_id" in mission:
                    try:
                        return self.complete(mission)
                    except ValueError:  # the flow has no later window: let the parked script decide
                        return None, True
        return None, False

    def hotspot(self, hint_id):
        """Return the original hotspot that advertises ``hint_id``."""
        return next((hotspot for hotspot in self.hotspots if hotspot.get("res") == hint_id), None)

    def hint(self, hint_id, *format_args):
        text = self.hints.get(hint_id, "")
        return text % format_args if format_args else text

    @classmethod
    def from_installation(cls, installation, content=None, save_dir=None):
        game = installation if isinstance(installation, Installation) else Installation(installation)
        content = content or GlueContent(game)
        wnd = content.resources
        tables = {name: content.strings(name) for name in ("BRTXT", "BKTXT", "GMTXT")}
        hints = tables["BRTXT"]
        hotspots = tuple(parse_window_ui(wnd, "STARTCARAVAN")["hotspots"])
        try:
            company = load_company(game)
        except (FileNotFoundError, OSError, ValueError):
            # Focused scene tests can supply a minimal installation without STRTARMY.MRC/WHSHR.EXE.
            company = ()
        return cls(build_campaign_graph(str(game.root), wnd=wnd, string_tables=tables),
                   flow=initial_flow(hotspots), hints=hints, content=content, company=company,
                   save_dir=save_dir)

    @classmethod
    def single_mission(cls, briefing):
        """Compatibility state for focused tests and development-only briefings."""
        mission = {"name_id": 0, "name": briefing.battle_id.name.upper(),
                   "battle": briefing.battle_id.name.upper(), "briefing_key": "test.0", "briefing": briefing}
        return cls({"flow_scripts": {FIRST_FLOW: ({"action": "add_window", "window": "TEST"},)},
                    "mission_windows": {"TEST": [mission]}})
