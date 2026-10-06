# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Data-driven campaign progression for the caravan's mission choices.

The original interpreter persists its active glue contexts in a save's STAX
chunk.  The engine keeps the same useful pieces explicitly: the active flow,
the current mission window, completed mission resource ids, and coffers.
"""

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from os import PathLike
from typing import TYPE_CHECKING, Any

from .campaign import build_campaign_graph, parse_window_ui
from .encyclopedia import DEFAULT_KEYS
from .glue import MissionRecord, MissionRef
from .glue_content import GlueContent
from .paths import Installation
from . import roster, script
from .portraits import first_leader_speaker
from .roster import Regiment, load_company, load_master, with_hired

if TYPE_CHECKING:
    from .debrief_screen import UnitOutcome
    from .payments import CashTerms
    from .roster_book import BookModel
    from .troop_selection import Deployment

Mission = dict[str, Any]  # one mission record of a mission window (campaign.parse_mission_windows)
ObjectiveResult = tuple[bool, tuple[int, ...]]  # (met, (v1, v2, v3, v4))


FIRST_FLOW = "FLOWSCRIPTBP01"
INITIAL_COFFERS = 500

CARAVAN_MODE_WINDOWS: dict[str, str] = {
    "start": "STARTCARAVAN",
    "select": "CARAVANAFTERMISSION",
    "resume": "CARAVANAFTERENCOUNTER",
    "recruit": "CARAVANRECRUITANDRESUME",
    "recruitnospeech": "CARAVANRECRUITNOSPEECHANDRESUME",
}


RECRUIT_VARIANTS = {"CARAVANAFTERMISSION": "CARAVANAFTERMISSIONWITHRECRUIT",
                    "CARAVANAFTERENCOUNTER": "CARAVANAFTERENCOUNTERWITHRECRUIT"}


def is_caravan_window(name: str) -> bool:
    """Is ``name`` one of the caravan windows (``StartCaravan``, ``Caravan…``, ``InfoCaravan…`` and their variants)?"""
    return name.upper().startswith(("STARTCARAVAN", "CARAVAN", "INFOCARAVAN"))


def caravan_window(mode: str, recruitable: bool = False) -> str | None:
    """The caravan window a ``gocaravan:<mode>`` request names, or ``None`` for an unknown name
    (notes/glue_interpreter.md section 7.3: ``info<letters>`` names ``InfoCaravan<letters>``; an
    unknown name is resumed at once).  ``select`` and ``resume`` open their ``WithRecruit`` variant (Dietrich announces
    the new troops) when regiments are recruitable (notes/glue_interpreter.md section 7.3).  The window may still be
    missing from a given installation."""
    mode = str(mode).casefold()
    name = CARAVAN_MODE_WINDOWS.get(mode)
    if name is None and mode.startswith("info") and len(mode) > 4:
        name = "INFOCARAVAN" + mode[4:].upper()
    if recruitable and name in RECRUIT_VARIANTS:
        name = RECRUIT_VARIANTS[name]
    return name


def mission_visible(missions: Sequence[Mission], mission: Mission, taken: Iterable[int]) -> bool:
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


def eligible_missions(missions: Sequence[Mission], taken: Iterable[int]) -> tuple[Mission, ...]:
    """Return the mission entries a window offers once ``taken`` have been committed to."""
    taken = set(taken)
    return tuple(mission for mission in missions if mission_visible(missions, mission, taken))


def _record_gates(record: MissionRecord) -> dict[str, int]:
    """Return ``(name_id, gates)`` of one typed ``[MISSION]`` record (``gates``: depend/inactivedepend)."""
    entry: dict[str, int] = {}
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


def offered_refs(records: Iterable[MissionRecord], taken: Iterable[MissionRef]) -> tuple[MissionRef | None, ...]:
    """Return the ``MissionRef`` of every mission record a window offers, in window order.

    ``records`` are the window's typed ``[MISSION]`` records and ``taken`` the set of committed
    ``MissionRef``.  A taken mission is hidden; ``depend`` / ``inactivedepend`` follow
    :func:`mission_visible` (notes/mission_selection.md, notes/campaign.md section 7.2).
    """
    taken = set(taken)
    entries: list[dict[str, Any]] = []
    for record in records:
        gates: dict[str, Any] = dict(_record_gates(record))
        gates["name_id"] = gates.pop("res", None)
        gates["ref"] = record.mission_ref
        entries.append(gates)
    taken_ids = {entry["name_id"] for entry in entries if entry["ref"] in taken and entry["name_id"] is not None}
    return tuple(entry["ref"] for entry in entries
                 if entry["ref"] not in taken and mission_visible(entries, entry, taken_ids))


def initial_flow(hotspots: Iterable[Mapping[str, Any]]) -> str:
    """Return the flow resource selected by STARTCARAVAN's original hotspot."""
    flows = [hotspot["target"].upper() for hotspot in hotspots
             if hotspot.get("target_kind") == "res" and hotspot.get("target", "").upper().startswith("FLOWSCRIPT")]
    if len(flows) != 1:
        raise ValueError(f"STARTCARAVAN must select exactly one flow, found {flows!r}")
    return flows[0]


@dataclass
class CampaignState:
    """The portion of original campaign state needed to populate the caravan."""

    graph: dict[str, Any]
    flow: str = FIRST_FLOW
    # Every flow the campaign has run, oldest first, ending with ``flow``: a replacement flow carries
    # on inside the map its predecessors built, so resuming replays the chain (notes/mission_selection.md §10).
    flow_history: list[str] = field(default_factory=list)
    flow_step: int = 0
    mission_window: str | None = None
    completed: set[int] = field(default_factory=set)
    coffers: int = INITIAL_COFFERS
    army_units: set[int] = field(default_factory=set)
    march_units: set[int] = field(default_factory=set)
    march_order: tuple[int, ...] = ()
    reinforcements: dict[int, int] = field(default_factory=dict)
    selected_mission: MissionRef | None = None
    taken_missions: set[MissionRef] = field(default_factory=set)
    book_flags: dict[int, set[int]] = field(default_factory=dict)
    autosave_state: Any = field(default=None, repr=False, compare=False)
    tentpos: int = 0
    hints: dict[int, str] = field(default_factory=dict)
    content: GlueContent | None = field(default=None, repr=False, compare=False)
    company: tuple[Regiment, ...] = field(default_factory=tuple[Regiment, ...])
    # Every regiment of the campaign in its fresh state (``PLAY.MRC``'s starting content): the source that
    # ``addunit``/``unitjoinmission`` copy a regiment from into the company (notes/campaign.md §2.4, §4.4).
    master: tuple[Regiment, ...] = field(default_factory=tuple[Regiment, ...], repr=False, compare=False)
    # The portrait set of the first marching regiment with a leader portrait (notes/glue_portraits.md
    # §1.4); recomputed only when the marching roster is loaded, None until then.
    current_speaker: str | None = None
    # Optional lower-case sprite name -> portrait set override; default is read from the installation.
    portrait_sets: dict[str, str] | None = field(default=None, repr=False, compare=False)
    # Roster flag "pending join" set by the glue ``addunit`` (notes/campaign.md section 3.2). The copy into the
    # army happens when the after-mission caravan is entered; the engine does not merge yet.
    pending_join: set[int] = field(default_factory=set)
    # Bonus counter of the payment programs (glue ``bonus*``, notes/campaign.md section 2.5).
    bonus_counter: int = 0
    # The latest battle's objective records: letter -> (met, (v1, v2, v3, v4)), the ``Result:`` lines of
    # notes/debrief_evaluation.md section 2.1. Empty until a battle writes its result.
    objective_results: dict[str, ObjectiveResult] = field(default_factory=dict[str, ObjectiveResult])
    # The payment terms (whshr.payments.CashTerms) of the mission being played, and whether its final
    # payment was already credited; both are reset when the next mission's troop selection opens.
    mission_cash: "CashTerms | None" = field(default=None, repr=False, compare=False)
    mission_paid: bool = False
    # True while ``objective_results`` is the no-battle mode's flawless win (whshr.payments.flawless_results).
    flawless_result: bool = False
    # What each marching regiment (by whoami) came out of the latest played battle with; empty when no battle was
    # played (no-battle mode), in which case the debrief shows every marching regiment unharmed.
    battle_outcome: "dict[int, UnitOutcome]" = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.flow_history or self.flow_history[-1] != self.flow:
            self.flow_history.append(self.flow)
        if self.mission_window is None:
            self._open_next_window(0)

    def add_cash(self, amount: int) -> None:
        self.coffers += int(amount)

    def begin_mission(self, terms: "CashTerms | None") -> None:
        """A new mission starts: remember its payment terms, forget the previous battle result."""
        self.mission_cash = terms
        self.mission_paid = False
        self.objective_results = {}
        self.flawless_result = False
        self.battle_outcome = {}

    def is_unit_in_army(self, unit_id: int) -> bool:
        return int(unit_id) in self.army_units

    def is_unit_in_march(self, unit_id: int) -> bool:
        return int(unit_id) in self.march_units

    def add_reinforcements(self, unit_id: int, count: int) -> None:
        unit_id = int(unit_id)
        self.reinforcements[unit_id] = self.reinforcements.get(unit_id, 0) + int(count)

    def join_mission(self, unit_id: int) -> None:
        """``unitjoinmission``: the regiment is copied into the company (always hired) and marches."""
        unit_id = int(unit_id)
        self.march_units.add(unit_id)
        joined = self._join_company(unit_id, hired=True)
        if joined:
            self._sync_army()

    def leave_mission(self, unit_id: int) -> None:
        """``unitleavemission``: the regiment leaves the company and the march; its master record stays."""
        unit_id = int(unit_id)
        self.march_units.discard(unit_id)
        if any(regiment.whoami == unit_id for regiment in self.company):
            self.company = tuple(regiment for regiment in self.company if regiment.whoami != unit_id)
            self._sync_army()

    def _join_company(self, unit_id: int, hired: bool) -> bool:
        """Copy ``unit_id`` from the master roster into the company; only a hired flag is updated when it is
        already there. Returns whether the company changed."""
        present = next((regiment for regiment in self.company if regiment.whoami == unit_id), None)
        if present is not None:
            if hired and not present.hired:
                self.company = tuple(with_hired(regiment, True) if regiment.whoami == unit_id else regiment
                                     for regiment in self.company)
                return True
            return False
        source = next((regiment for regiment in self.master if regiment.whoami == unit_id), None)
        if source is None:
            return False
        joined = with_hired(source, hired)
        self.company = tuple(sorted((*self.company, joined), key=lambda regiment: regiment.whoami))
        return True

    def _sync_army(self) -> None:
        self.army_units = {regiment.whoami for regiment in self.company if regiment.hired}

    def merge_pending_joins(self) -> tuple[int, ...]:
        """The after-mission caravan copies every ``addunit`` regiment into the company (notes/campaign.md §2.4):
        hired at once unless the roster marks it *for hire*, in which case it waits in the recruit book.
        Ids the master roster does not know stay pending."""
        merged: list[int] = []
        for unit_id in sorted(self.pending_join):
            source = next((regiment for regiment in self.master if regiment.whoami == unit_id), None)
            if source is None:
                continue
            self._join_company(unit_id, hired=not source.row.for_hire)
            self.pending_join.discard(unit_id)
            merged.append(unit_id)
        if merged:
            self._sync_army()
        return tuple(merged)

    def recruitable(self) -> bool:
        """Is a regiment for hire waiting in the company? It decides only whether ``select``/``resume`` open their
        ``WithRecruit`` window (Dietrich announcing the men seeking work); reinforcements that replace losses are
        irrelevant to it. 🟡 the original's exact test is not recorded (notes/glue_interpreter.md section 7.3)."""
        return any(not regiment.hired and regiment.row.for_hire for regiment in self.company)

    def leave_caravan(self) -> None:
        """Leaving a recruit caravan drops every regiment that was not hired and clears unused reinforcements
        (notes/campaign.md §2.4)."""
        self.company = tuple(regiment for regiment in self.company if regiment.hired)
        self.reinforcements.clear()
        self._sync_army()

    def apply_army_book(self, model: "BookModel") -> None:
        """Army Records Done: save company changes and append new hires to the existing march
        (notes/native-windows.md §10.3.6)."""
        if model.dirty:
            self.company = tuple(with_hired(regiment, model.hired[whoami]) for whoami, regiment in model.company.items())
            self.reinforcements = dict(model.ledger.available)
            self._sync_army()
        if model.pays:
            self.coffers = model.coffers
            if model.dirty:
                prior_order = self.ordered_march_units
                additions = tuple(whoami for whoami in model.selection if whoami not in self.march_units)
                self.march_units.update(additions)
                self.march_order = (*prior_order, *additions)

    def abort_army_book(self, model: "BookModel") -> None:
        """Army Records Abort: nothing is written, but a paying book already charged every click, so its coffers
        stay (notes/builtin_widgets.md §2.3 quirk)."""
        if model.pays:
            self.coffers = model.coffers

    def rename_commander(self, name: str) -> None:
        """The name prompt's OK: the leader of the commander's regiment takes ``name`` (notes/native-windows.md
        §7.3.1 step 6). The master roster is read-only and keeps its shipped name (open question of §7.3.1)."""
        self.company = tuple(roster.with_leader_name(regiment, name)
                             if regiment.whoami == roster.ALWAYS_FORCED_WHOAMI else regiment
                             for regiment in self.company)

    @property
    def commander_name(self) -> str:
        """The leader name of the commander's regiment (the name prompt's default text)."""
        return next((regiment.leader_name or "" for regiment in self.company
                     if regiment.whoami == roster.ALWAYS_FORCED_WHOAMI), "")

    @property
    def ordered_march_units(self) -> tuple[int, ...]:
        retained = tuple(dict.fromkeys(whoami for whoami in self.march_order if whoami in self.march_units))
        additions = sorted(self.march_units - set(retained), key=lambda whoami: (self._march_rank(whoami), whoami))
        return (*retained, *additions)

    def marching_army(self) -> script.View | None:
        """Current selected regiments in marching order, with no writes to the installation."""
        by_whoami = {regiment.whoami: regiment for regiment in self.company}
        units = [script.unit_view(regiment.raw) for whoami in self.ordered_march_units
                 if (regiment := by_whoami.get(whoami)) is not None and regiment.raw is not None]
        if not units:
            return None
        return {"armies": [{"label": "Player marching army", "count": len(units), "units": units}]}

    def _march_rank(self, whoami: int) -> int:
        return next((index for index, regiment in enumerate(self.company) if regiment.whoami == whoami), len(self.company))

    def mark_pending_join(self, unit_id: int) -> None:
        self.pending_join.add(int(unit_id))

    def objective(self, letter: str) -> ObjectiveResult | None:
        """The ``(met, values)`` record of an objective letter, or ``None`` when the battle did not define it."""
        return self.objective_results.get(str(letter).upper()[:1])

    def bonus_init(self) -> None:
        self.bonus_counter = 0

    def bonus_adjust(self, delta: int) -> None:
        self.bonus_counter += int(delta)

    def enable_book(self, book: int, index: int) -> None:
        """Unlock a book/encyclopedia page (glue ``enablebook``, notes/campaign.md §4.4)."""
        self.book_flags.setdefault(int(book), set()).add(int(index))

    def select_mission(self, mission: MissionRef) -> None:
        self.selected_mission = mission

    def mark_mission_taken(self, mission: MissionRef) -> None:
        self.taken_missions.add(mission)

    def commit_troop_selection(self, deployment: "Deployment") -> None:
        """Apply a confirmed troop_selection.Deployment; notes/troop_selection.md §5.3."""
        self.coffers += deployment.money_delta
        self.march_units = set(deployment.units)
        self.march_order = tuple(deployment.units)
        self.army_units = set(deployment.hired)
        # Point 5: regiments that were not hired leave the company, unused reinforcements are cleared.
        self.company = tuple(with_hired(regiment, True) for regiment in self.company if regiment.whoami in deployment.hired)
        self.reinforcements.clear()
        by_whoami = {regiment.whoami: regiment for regiment in self.company}
        self.refresh_speaker([by_whoami[whoami] for whoami in deployment.units if whoami in by_whoami])

    def refresh_speaker(self, marching_regiments: Sequence[Regiment]) -> None:
        """Recompute the current speaker from the marching roster, in file order (§1.4 items 1-2)."""
        if self.portrait_sets is None:
            installation = getattr(self.content, "installation", None)
            try:
                from .battlefield import resource_files
                self.portrait_sets = resource_files(installation, {"portraits"}) if installation else {}
            except (FileNotFoundError, OSError, ValueError, KeyError):
                self.portrait_sets = {}
        self.current_speaker = first_leader_speaker(
            [regiment.leader_portrait for regiment in marching_regiments], self.portrait_sets)

    def autosave(self, runtime_state: object) -> None:
        self.autosave_state = deepcopy(runtime_state)

    @property
    def missions(self) -> tuple[Mission, ...]:
        return eligible_missions(self.graph["mission_windows"].get(self.mission_window, ()), self.completed)

    def _open_next_window(self, start: int) -> None:
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
    def map_portrait_window(self) -> dict[str, Any] | None:
        """The data-defined portrait sub-window opened by the active flow."""
        steps = self.graph["flow_scripts"].get(self.flow, ())[:self.flow_step + 1]
        for step in reversed(steps):
            if step["action"] == "open_subwindow":
                return self.graph.get("portrait_windows", {}).get(step["window"])
        return None

    def offered_missions(self, records: Iterable[MissionRecord]) -> tuple[MissionRef | None, ...]:
        """The refs of the typed mission ``records`` of one window that are on offer now."""
        return offered_refs(records, self.taken_missions)

    def is_mission_taken(self, mission_ref: MissionRef) -> bool:
        """Has this mission already been committed to or finished (so it is no longer offered)?"""
        return mission_ref in self.taken_missions

    def wait_already_released(self, flow: str, ordinal: int) -> bool:
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

    def _anything_offered(self) -> bool:
        """Does the current mission window still offer a row?  Keyed by mission record, because the
        same name id recurs in several windows (a finished one must not hide another window's row)."""
        if self.content is not None and self.mission_window is not None:
            try:
                records = [record for record in self.content.window(self.mission_window).records
                           if isinstance(record, MissionRecord)]
            except (KeyError, TypeError):
                records = None
            if records is not None:
                return bool(self.offered_missions(records))
        return any(mission.get("mission_ref") not in self.taken_missions for mission in self.missions)

    def complete(self, mission: Mission) -> tuple[str | None, bool]:
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

    def repair_stalled_flow(self) -> bool:
        """Finish a mission that was committed to but never released, when that leaves the map with nothing to offer.

        A save made in an after-mission caravan before the fix kept the mission hidden (taken) while the flow had
        not moved on, so a load stalled on an empty map. Completing the taken mission is exactly what leaving
        that caravan would have done. Returns True when something was completed."""
        if self._anything_offered():
            return False
        for mission in self.graph["mission_windows"].get(self.mission_window, ()):
            reference = mission.get("mission_ref")
            if reference in self.taken_missions and mission.get("name_id") not in self.completed:
                try:
                    self.complete(mission)
                except ValueError:  # no later window: nothing to advance to
                    return False
                return True
        return False

    def complete_mission(self, mission_ref: MissionRef) -> tuple[str | None, bool]:
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

    def hint(self, hint_id: int, *format_args: Any) -> str:
        text = self.hints.get(hint_id, "")
        return text % format_args if format_args else text

    @classmethod
    def from_installation(cls, installation: Installation | str | PathLike[str],
                          content: GlueContent | None = None) -> "CampaignState":
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
        try:
            master = load_master(game)
        except (FileNotFoundError, OSError, ValueError):
            master = ()
        return cls(build_campaign_graph(str(game.root), wnd=wnd, string_tables=tables),
                   flow=initial_flow(hotspots), hints=hints, content=content, company=company,
                   master=master, book_flags={0: set(DEFAULT_KEYS)})

    @classmethod
    def single_mission(cls, briefing: Any) -> "CampaignState":
        """Compatibility state for focused tests and development-only briefings."""
        mission = {"name_id": 0, "name": briefing.battle_id.name.upper(),
                   "battle": briefing.battle_id.name.upper(), "briefing_key": "test.0", "briefing": briefing}
        return cls({"flow_scripts": {FIRST_FLOW: ({"action": "add_window", "window": "TEST"},)},
                    "mission_windows": {"TEST": [mission]}})
