# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""One detailed, human-readable log per skirmish (per battle grid), stdlib-only.

`whshr.battle_log` records the whole battle as JSON Lines for replay. This module is for the other
job: understanding and sanity-checking a *single* close combat. Every fight that forms gets its own
text file under the log directory, holding

- which regiments joined it, when, and which one owns the grid;
- an ASCII picture of the 17 x 17 cell map at every segment boundary and every strike, so the
  wrap-around, the reserves and the holes in a line are visible at a glance;
- every model's own strike rolls (target numbers, hit/wound/save, ganging-up and charge bonuses);
- the running combat-result tally and the break tests it feeds;
- and an **anomaly** line whenever the grid's invariants do not hold (`check_grid`).

The anomaly checks are the point of the file: the pairing rules in `whshr.battle_grid` are intricate
enough that a silent inconsistency (a model paired with a distant enemy, two models sharing a cell,
a reserve that never gets placed) would otherwise only show up as an odd casualty count much later.

The log also records the git branch and commit it was produced by, so a log can always be tied back
to the code that wrote it.
"""
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from . import battle_grid, combat
from .battle_events import BattleEvent
from .rules import Side

if TYPE_CHECKING:
    from .engine import Battle, Regiment

Letters = dict[str, str]  # regiment identifier -> letter

MAX_ATTACKERS_PER_MODEL = 4  # four orthogonal cells (game_rules.md 5.2)
DRIFT_LIMIT = battle_grid.CELL  # a model further than this from its own cell has drifted off it
STALE_RESERVE_SEGMENTS = 4  # a reserve still unplaced after this many segments is worth reporting


def build_stamp(root: str | PathLike[str] | None = None) -> str:
    """`branch @ commit` for the checkout this code lives in, read straight from `.git` (no subprocess)."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    git = root / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            ref = head[5:].strip()
            branch = ref.rsplit("/", 1)[-1]
            commit = (git / ref).read_text(encoding="utf-8").strip()
        else:
            branch, commit = "(detached)", head
        return f"{branch} @ {commit[:7]}"
    except OSError:
        return "(unknown build)"


def check_grid(battle: "Battle", grid: battle_grid.BattleGrid, members: Sequence["Regiment"]) -> list[str]:
    """Every way the grid's invariants can be violated, as a list of human-readable strings.

    An empty list means the grid is internally consistent: cells hold at most one live model each,
    every pairing is mutual where it should be, paired models are orthogonally adjacent, no enemy
    model has more attackers than it has sides, and no model has drifted off the cell it holds.
    """
    problems: list[str] = []
    seen_cells: dict[battle_grid.Cell, str] = {}
    attackers_per_target: dict[tuple[str, int], list[str]] = {}
    for regiment in members:
        positions = regiment.model_positions()
        if len(regiment.melee_models) != regiment.models:
            problems.append(
                f"{regiment.identifier}: {len(regiment.melee_models)} model states for "
                f"{regiment.models} models")
        for index, model in enumerate(regiment.melee_models):
            if model.cell is not None:
                if not battle_grid.in_bounds(*model.cell):
                    problems.append(f"{regiment.identifier}#{model.uid}: cell {model.cell} out of bounds")
                owner = seen_cells.get(model.cell)
                if owner is not None:
                    problems.append(
                        f"cell {model.cell} claimed by both {owner} and {regiment.identifier}#{model.uid}")
                seen_cells[model.cell] = f"{regiment.identifier}#{model.uid}"
                if grid.cells.get(model.cell) != (regiment.identifier, model.uid):
                    problems.append(
                        f"{regiment.identifier}#{model.uid}: holds cell {model.cell} but the grid records "
                        f"{grid.cells.get(model.cell)}")
                if index < len(positions):
                    wx, wy = grid.cell_world(*model.cell)
                    px, py = positions[index]
                    drift = math.hypot(wx - px, wy - py)
                    if model.arrived and drift > DRIFT_LIMIT:
                        problems.append(
                            f"{regiment.identifier}#{model.uid}: arrived but {drift:.0f} units off its cell")
            if model.arrived and model.cell is None:
                problems.append(f"{regiment.identifier}#{model.uid}: arrived without a cell")
            if model.opponent is None:
                continue
            target_id, target_uid = model.opponent
            target = battle.regiments.get(target_id)
            if target is None or not target.active:
                problems.append(f"{regiment.identifier}#{model.uid}: paired with inactive {target_id}")
                continue
            target_index = target.index_of(target_uid)
            if target_index is None:
                problems.append(
                    f"{regiment.identifier}#{model.uid}: paired with {target_id}#{target_uid}, "
                    f"which is dead ({target.models} models left)")
                continue
            if target.side == regiment.side:
                problems.append(f"{regiment.identifier}#{model.uid}: paired with friendly {target_id}")
                continue
            attackers_per_target.setdefault((target_id, target_uid), []).append(
                f"{regiment.identifier}#{model.uid}")
            target_model = target.melee_models[target_index]
            if model.cell is not None and target_model.cell is not None:
                distance = (abs(model.cell[0] - target_model.cell[0])
                            + abs(model.cell[1] - target_model.cell[1]))
                if distance != 1:
                    problems.append(
                        f"{regiment.identifier}#{model.uid}: paired with {target_id}#{target_uid} at "
                        f"Manhattan distance {distance}, not 1")
    for (target_id, target_uid), attackers in attackers_per_target.items():
        if len(attackers) > MAX_ATTACKERS_PER_MODEL:
            problems.append(
                f"{target_id}#{target_uid}: {len(attackers)} attackers ({', '.join(attackers)}), "
                f"more than the {MAX_ATTACKERS_PER_MODEL} orthogonal cells allow")
    return problems


def assign_letters(members: Sequence["Regiment"], letters: Mapping[str, str] | None = None) -> Letters:
    """One letter per regiment, kept stable as more units join the fight: a regiment kept in `letters`
    never changes letter, and newcomers take the next free one."""
    letters = dict(letters or {})
    for regiment in sorted(members, key=lambda r: r.identifier):
        if regiment.identifier in letters:
            continue
        letters[regiment.identifier] = chr(ord("A") + len(letters))
    return letters


def render_grid(battle: "Battle", grid: battle_grid.BattleGrid, members: Sequence["Regiment"],
                letters: Mapping[str, str] | None = None) -> str:
    """The cell map as ASCII: one letter per regiment, in its own case when the model is fighting and
    in the other case while it is still walking into its cell."""
    letters = assign_letters(members, letters)
    rows: list[str] = []
    header = "    " + "".join(f"{col % 10}" for col in range(battle_grid.GRID_SIZE))
    rows.append(header)
    for row in range(battle_grid.GRID_SIZE):
        line: list[str] = []
        for col in range(battle_grid.GRID_SIZE):
            occupant = grid.cells.get((row, col))
            if occupant is None:
                line.append(".")
                continue
            identifier, uid = occupant
            regiment = battle.regiments.get(identifier)
            base = letters.get(identifier, "?")
            is_player = regiment is not None and regiment.side == Side.PLAYER
            letter = base if is_player else base.lower()
            index = regiment.index_of(uid) if regiment is not None else None
            if regiment is None or index is None:
                line.append("?")  # a cell still held by a model that no longer exists
                continue
            model = regiment.melee_models[index]
            fighting = model.arrived and model.opponent is not None
            # A fighting model shows in its side's own case; one still walking in shows in the other.
            line.append(letter if fighting else (letter.lower() if is_player else letter.upper()))
        rows.append(f"{row:3d} " + "".join(line))
    legend = ", ".join(
        f"{letters[r.identifier] if r.side == Side.PLAYER else letters[r.identifier].lower()}={r.identifier}"
        f"{'' if r.side == Side.PLAYER else f' ({r.side.value})'}"
        for r in sorted(members, key=lambda r: r.identifier) if r.identifier in letters)
    rows.append(f"    legend: {legend}  "
                f"(a model still walking into its cell shows in the opposite case)")
    return "\n".join(rows)


class SkirmishLogger:
    """Opens one text file per fight under `log_dir`; a no-op when `log_dir` is None."""

    def __init__(self, log_dir: str | PathLike[str] | None = None, battle_asset: str = "battle",
                 when: datetime | None = None) -> None:
        self.log_dir = Path(log_dir) if log_dir is not None else None
        self.battle_asset = battle_asset
        self.stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
        self.files: dict[str, TextIO] = {}  # fight id -> open text file
        self.opened_tick: dict[str, int] = {}
        self.reserve_since: dict[tuple[str, str], tuple[int, bool]] = {}  # (fight id, regiment id) -> segment its reserves were first stuck
        self.letters: dict[str, Letters] = {}  # fight id -> {regiment id: letter}, stable for the life of the fight
        self.anomalies = 0
        self.paths: dict[str, Path] = {}

    def _open(self, battle: "Battle", group_id: str, members: Sequence["Regiment"]) -> TextIO | None:
        if self.log_dir is None:
            return None
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in self.battle_asset.lower())
        path = self.log_dir / f"skirmish-{self.stamp}-{safe}-{group_id}.log"
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            handle = open(path, "w", encoding="utf-8")
        except OSError:
            return None
        self.files[group_id] = handle
        self.paths[group_id] = path
        return handle

    def _write(self, group_id: str, text: str) -> None:
        handle = self.files.get(group_id)
        if handle is None:
            return
        try:
            handle.write(text + "\n")
            handle.flush()
        except OSError:
            self.files.pop(group_id, None)

    def observe(self, battle: "Battle") -> None:
        """Call once per tick, after `Battle.tick`: opens, updates and closes skirmish files."""
        if self.log_dir is None:
            return
        absolute_segment, turn, segment = combat.segment_state(battle.tick_count)
        live: dict[str, list["Regiment"]] = {}
        for regiment in battle.regiments.values():
            if (regiment.in_melee and regiment.melee_group is not None and regiment.melee_group in battle.fights
                    and regiment.active):
                live.setdefault(regiment.melee_group, []).append(regiment)
        for group_id in sorted(live):
            members = sorted(live[group_id], key=lambda r: r.identifier)
            grid = battle.fights.get(group_id, {}).get("grid")
            if grid is None:
                continue
            if group_id not in self.files:
                self._open(battle, group_id, members)
                self._write_opening(battle, group_id, grid, members)
                self.opened_tick[group_id] = battle.tick_count
            self._observe_fight(battle, group_id, grid, members, turn, segment, absolute_segment)
        for group_id in list(self.files):
            if group_id not in live:
                self._close(battle, group_id)

    def _write_opening(self, battle: "Battle", group_id: str, grid: battle_grid.BattleGrid,
                       members: Sequence["Regiment"]) -> None:
        self._write(group_id, f"skirmish {group_id} of battle {self.battle_asset}")
        self._write(group_id, f"build: {build_stamp()}")
        self._write(group_id, f"grid owner: {grid.owner_id} "
                              f"(frame x={grid.x:.1f} y={grid.y:.1f} dir={grid.direction})")
        self._write(group_id, "participants:")
        for regiment in members:
            side = regiment.side.value
            self._write(group_id,
                        f"  {regiment.identifier:<16} {side:<6} {regiment.models:3d} models "
                        f"ranks {regiment.ranks} frontage {regiment.front_rank_models()}  "
                        f"WS{regiment.ws} S{regiment.strength} T{regiment.toughness} "
                        f"I{regiment.initiative} A{regiment.attacks} Ld{regiment.leadership} "
                        f"armour {regiment.armour}")
        self._write(group_id, "")

    def _observe_fight(self, battle: "Battle", group_id: str, grid: battle_grid.BattleGrid,
                       members: Sequence["Regiment"], turn: int, segment: int, absolute_segment: int) -> None:
        strikes = [e for e in battle.events
                   if e.kind == "melee_strike" and e.data.get("fight") == group_id]
        tests = [e for e in battle.events
                 if e.kind in ("leadership_test", "rout_start") and
                 (e.data.get("fight") == group_id or
                  any(e.data.get("regiment") == r.identifier for r in members))]
        for event in strikes:
            self._write_strike(battle, group_id, event, turn, segment)
        for event in tests:
            self._write(group_id, f"[tick {battle.tick_count:5d} turn {turn} seg {segment}] {event}")
        interesting = strikes or tests
        if interesting or battle.tick_count % combat.SEGMENT_TICKS == 0:
            self._write(group_id,
                        f"grid @ tick {battle.tick_count} (turn {turn} segment {segment})")
            self.letters[group_id] = assign_letters(members, self.letters.get(group_id))
            self._write(group_id, render_grid(battle, grid, members, self.letters[group_id]))
            self._write(group_id, self._occupancy_line(battle, members))
            self._write(group_id, "")
        self._check(battle, group_id, grid, members, turn, segment, absolute_segment)

    @staticmethod
    def _occupancy_line(battle: "Battle", members: Sequence["Regiment"]) -> str:
        parts: list[str] = []
        for regiment in members:
            placed = sum(1 for m in regiment.melee_models if m.cell is not None)
            fighting = len(battle_grid.fighting_models(battle, regiment))
            reserves = sum(1 for m in regiment.melee_models if m.reserve)
            parts.append(f"{regiment.identifier}: {regiment.models} alive, {placed} placed, "
                         f"{fighting} fighting, {reserves} reserve")
        return "    " + " | ".join(parts)

    def _write_strike(self, battle: "Battle", group_id: str, event: BattleEvent, turn: int, segment: int) -> None:
        data = event.data
        self._write(group_id,
                    f"[tick {battle.tick_count:5d} turn {turn} seg {segment}] "
                    f"{data['attacker']} strikes {data['defender']}: "
                    f"{data['fighting']} models fighting, {data['kills']} killed "
                    f"(+{data['rank_bonus']} rank, +{data['direction_bonus']} dir); "
                    f"tally {data['tally']}")
        for model in data.get("attacks", []):
            rolls = ", ".join(
                f"{r['hit']}"
                + (f"/{r['wound']}" if r["wound"] is not None else "")
                + (f"/{r['save']}" if r["save"] is not None else "")
                + f" {r['result']}"
                for r in model["rolls"])
            bonuses: list[str] = []
            if model.get("gang_bonus"):
                bonuses.append("+1 WS gang")
            if model.get("charge_bonus"):
                bonuses.append("+1 S charge")
            suffix = f" [{', '.join(bonuses)}]" if bonuses else ""
            self._write(group_id,
                        f"    model #{model['model']} vs {model['target']}#{model['target_model']}: "
                        f"need {model['hit_need']}+/{model['wound_need']}+/save {model['save_need']}+"
                        f"{suffix} -> {rolls}")

    def _check(self, battle: "Battle", group_id: str, grid: battle_grid.BattleGrid, members: Sequence["Regiment"],
               turn: int, segment: int, absolute_segment: int) -> None:
        for problem in check_grid(battle, grid, members):
            self.anomalies += 1
            self._write(group_id, f"!! ANOMALY [tick {battle.tick_count} turn {turn} "
                                  f"seg {segment}] {problem}")
        self._note_saturation(battle, group_id, members, turn, segment, absolute_segment)

    def _note_saturation(self, battle: "Battle", group_id: str, members: Sequence["Regiment"], turn: int,
                         segment: int, absolute_segment: int) -> None:
        """Models stuck as reserves are normal once the grid saturates (there are only about
        2 x (width + depth) cells next to an enemy), so this is a note, never an anomaly. It is still
        worth seeing: it is the difference between "the unit is losing" and "most of it never fought"."""
        for regiment in members:
            key = (group_id, regiment.identifier)
            stuck = sum(1 for m in regiment.melee_models if m.reserve)
            if not stuck:
                self.reserve_since.pop(key, None)
                continue
            first, reported = self.reserve_since.setdefault(key, (absolute_segment, False))
            # Once per streak, not once per tick: a segment spans many ticks, and the streak only
            # ends when the unit gets its models placed (which resets the entry above).
            if reported or absolute_segment - first < STALE_RESERVE_SEGMENTS:
                continue
            self.reserve_since[key] = (first, True)
            self._write(group_id,
                        f"   note [tick {battle.tick_count} turn {turn} seg {segment}] "
                        f"{regiment.identifier}: {stuck} of {regiment.models} models have had no "
                        f"free cell for {STALE_RESERVE_SEGMENTS} segments (grid saturated)")

    def _close(self, battle: "Battle", group_id: str) -> None:
        opened = self.opened_tick.get(group_id)
        duration = battle.tick_count - opened if opened is not None else 0
        self._write(group_id, f"skirmish {group_id} ended at tick {battle.tick_count} "
                              f"after {duration} ticks")
        handle = self.files.pop(group_id, None)
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass

    def close(self, battle: "Battle | None" = None) -> None:
        for group_id in list(self.files):
            if battle is not None:
                self._close(battle, group_id)
            else:
                handle = self.files.pop(group_id, None)
                if handle is not None:
                    try:
                        handle.close()
                    except OSError:
                        pass
