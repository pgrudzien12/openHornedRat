"""Figure capture: a readable per-tick, per-figure trace of one regiment for a short window of play.

Pressing the capture key in the battle view (F2) buffers in memory the next `CAPTURE_TICKS` battle ticks (5 s of
battle time; paused time does not count) of one regiment -- the selected one, else `DEFAULT_UNIT` -- and
then writes it in one go (pressing F2 again while it runs extends it by another 5 s) to `<log_dir>/capture-YYYYmmdd-HHMMSS-<battle>-<unit>-t<tick>.log`. Each tick lists the regiment's order
and movement state, then one line per figure: position, how far it moved this tick, the goal it walks
to (formation slot, re-form slot, scatter point or battle-grid cell) and its distance from it, speed,
facings, animation and close-combat state, plus the battle events that mention the regiment.

This is a debugging aid only: it reads the battle and never changes it, so a capture neither alters
the simulation nor the battle log replay (the capture request itself is logged as an order, which
replay re-handles as a no-op because replay runs without a log directory).
"""
import math
from datetime import datetime
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING

from . import animation, battle_grid, formation
from .rules import Side
from .skirmish_log import build_stamp

if TYPE_CHECKING:
    from .engine import Battle, ModelState, Regiment

CAPTURE_TICKS = 50  # 5 s at the 100 ms battle tick
# Debugging default when nothing is selected (user request): the player's starting cavalry regiment.
DEFAULT_UNIT = "Grudgebringer<Cavalry"

ACTION_NAMES = {
    animation.STAND: "stand", animation.IDLE: "idle", animation.WALK: "walk", animation.FIGHT: "fight",
    animation.WEAPON_READY: "ready", animation.DEAD: "dead", animation.SHOOT: "shoot",
}

Point = tuple[float, float]


def capture_unit(battle: "Battle", selected_id: str | None) -> str | None:
    """The regiment a capture should follow: the selection, else `DEFAULT_UNIT`, else the first player
    regiment (a battle without the default unit), else None."""
    if selected_id is not None and selected_id in battle.regiments:
        return selected_id
    for identifier in battle.regiments:
        if identifier.casefold() == DEFAULT_UNIT.casefold():
            return identifier
    return next((identifier for identifier, regiment in battle.regiments.items()
                 if regiment.side == Side.PLAYER), None)


def figure_goals(battle: "Battle", regiment: "Regiment") -> list[tuple[Point, str]]:
    """Where each figure is walking to and why, for display only.

    Mirrors the goal choice of the engine's per-model movement step (a battle-grid cell beats a
    scatter point, which beats the formation slot; a scatter point is ignored while the regiment has
    an order of its own; a re-forming regiment walks to its re-form slots). If the two ever disagree,
    the engine is right and this display is stale.
    """
    count = len(regiment.positions)
    if regiment.reforming and len(regiment.reform_slots) == count:
        slots = formation.place(regiment.x, regiment.y, regiment.direction, regiment.reform_slots)
        return [(point, "reform") for point in slots]
    slots = formation.place(regiment.x, regiment.y, regiment.direction,
                            formation.block_slots(regiment.models, regiment.ranks))
    busy = regiment.in_melee or regiment.routing or bool(regiment.attack_target) or regiment.moving
    goals: list[tuple[Point, str]] = []
    for index in range(count):
        model = regiment.melee_models[index] if index < len(regiment.melee_models) else None
        cell = battle_grid.cell_target(battle, regiment, index) if model is not None else None
        if cell is not None:
            goals.append((cell, "cell"))
        elif model is not None and model.scatter_target is not None and not busy:
            goals.append((model.scatter_target, "scatter"))
        elif index < len(slots):
            goals.append((slots[index], "slot"))
        else:
            goals.append((regiment.positions[index], "none"))
    return goals


def _fmt(value: float | None, digits: int = 1) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _flags(model: "ModelState") -> str:
    flags = [name for name, on in (("rest", model.at_rest), ("arrived", model.arrived), ("reserve", model.reserve))
             if on]
    if model.freeze_ticks:
        flags.append(f"freeze{model.freeze_ticks}")
    if model.rout_pause_ticks:
        flags.append(f"routpause{model.rout_pause_ticks}")
    if model.wounds_taken:
        flags.append(f"wounds{model.wounds_taken}")
    return ",".join(flags) or "-"


class FigureCapture:
    """One running capture; feed it every battle tick with `observe` until `done`."""

    def __init__(self, log_dir: str | PathLike[str], battle_asset: str, battle: "Battle", unit_id: str,
                 ticks: int = CAPTURE_TICKS, when: datetime | None = None) -> None:
        self.unit_id = unit_id
        self.start_tick = battle.update_count
        self.remaining = ticks
        stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in f"{battle_asset}-{unit_id}".lower())
        self.path = Path(log_dir) / f"capture-{stamp}-{safe}-t{self.start_tick}.log"
        self.lines: list[str] = []  # buffered in memory; written to `path` in one go by `close`
        self.written = False
        self._previous: dict[int, Point] = {}  # figure uid -> position on the previous captured tick
        regiment = battle.regiments[unit_id]
        self._write(f"figure capture of {regiment.name} ({unit_id}) in battle {battle_asset}")
        self._write(f"build: {build_stamp()}")
        self.last_tick = self.start_tick
        self._range_line = len(self.lines)  # filled in by `close`, once extensions are known
        self._write("")
        self._write(f"side {regiment.side.value}, speed/tick {regiment.speed_per_tick:.2f}")
        self._write("figure columns: #index uid  pos x,y  moved  goal(kind) x,y  dist  speed budget  "
                    "facing drawn  action(pc)  cell opponent  flags")
        self._write("")
        self._write_tick(battle, [])

    @property
    def done(self) -> bool:
        return self.remaining <= 0

    @property
    def running(self) -> bool:
        return not self.done

    def extend(self, battle: "Battle", ticks: int = CAPTURE_TICKS) -> None:
        """Pressing the capture key again on a running capture lengthens it by another `ticks`."""
        if self.done:
            return
        self.remaining += ticks
        self._write(f"-- capture extended at tick {battle.update_count} by {ticks} ticks")

    def _write(self, text: str) -> None:
        self.lines.append(text)

    def observe(self, battle: "Battle") -> None:
        """Call once per battle tick, after `Battle.tick`."""
        if self.done:
            return
        regiment = battle.regiments.get(self.unit_id)
        events = [str(event) for event in battle.events if self._mentions(event, regiment)]
        self._write_tick(battle, events)
        self.remaining -= 1
        if self.remaining <= 0:
            self._write("end of capture")
            self.close()

    def _mentions(self, event: object, regiment: "Regiment | None") -> bool:
        data = getattr(event, "data", {})
        for value in data.values():
            if value == self.unit_id or (isinstance(value, (list, tuple, set)) and self.unit_id in value):
                return True
        return regiment is not None and regiment.name in str(event)

    def _write_tick(self, battle: "Battle", events: list[str]) -> None:
        self.last_tick = battle.update_count
        regiment = battle.regiments.get(self.unit_id)
        if regiment is None:
            self._write(f"tick {battle.update_count}: regiment gone")
            return
        target = (f"{_fmt(regiment.target_x)},{_fmt(regiment.target_y)}"
                  if regiment.target_x is not None else "-")
        states = [name for name, on in (
            ("active", regiment.active), ("walking", regiment.walking), ("moving", regiment.moving),
            ("reforming", regiment.reforming), ("walk_back", regiment.reforming and regiment.reform_walk_back),
            ("in_melee", regiment.in_melee), ("routing", regiment.routing),
            ("fled", regiment.fled), ("pursuing", regiment.pursuing), ("free_charging", regiment.free_charging),
            ("independent", regiment.independent), ("hidden", regiment.hidden)) if on]
        self._write(f"== tick {battle.update_count} (combat tick {battle.tick_count}, phase {battle.phase}"
                    f"{', paused' if battle.paused else ''})")
        self._write(f"   anchor {regiment.x:.1f},{regiment.y:.1f} dir {regiment.direction:.1f} "
                    f"models {regiment.models} ranks {regiment.ranks} [{' '.join(states) or '-'}]")
        self._write(f"   target {target} waypoints {[(round(x), round(y)) for x, y in regiment.waypoints]} "
                    f"attack {regiment.attack_target or '-'} turn {regiment.turn_order_key or '-'}/"
                    f"{regiment.turn_mode or '-'} route_speed {regiment.route_speed:.2f} "
                    f"route_pause {regiment.route_pause_ticks} melee_touching {sorted(regiment.melee_touching)}")
        if not regiment.positions:
            # Figures are placed on the regiment's first movement step; placing them here would draw
            # from the battle-wide stagger sequence and change the battle.
            self._write("   figures not placed yet")
        goals = figure_goals(battle, regiment)
        for index, ((x, y), model) in enumerate(zip(regiment.positions, regiment.melee_models)):
            before = self._previous.get(model.uid)
            moved = math.dist(before, (x, y)) if before is not None else None
            self._previous[model.uid] = (x, y)
            (gx, gy), kind = goals[index] if index < len(goals) else ((x, y), "none")
            leader = "L" if model.uid == regiment.leader_uid else " "
            opponent = f"{model.opponent[0]}#{model.opponent[1]}" if model.opponent else "-"
            self._write(
                f"   #{index:<2}{leader}u{model.uid:<5} {x:7.1f},{y:7.1f}  {_fmt(moved, 2):>5}  "
                f"{kind}:{gx:.1f},{gy:.1f} {math.dist((x, y), (gx, gy)):6.2f}  "
                f"{model.current_speed:5.2f} {model.distance_budget:5.2f}  "
                f"{_fmt(model.drawn_facing, 0):>3}  "
                f"{ACTION_NAMES.get(model.action, str(model.action))}({model.action_pc})  "
                f"{model.cell or '-'} {opponent}  {_flags(model)}")
        for text in events:
            self._write(f"   event: {text}")

    def close(self) -> None:
        """Stop capturing and write the buffered capture to disk once. A capture cut short (battle
        over, scene left) is written as far as it got; an unwritable log directory is ignored."""
        self.remaining = 0
        if self.written:
            return
        self.written = True
        self.lines[self._range_line] = (f"ticks {self.start_tick}..{self.last_tick} "
                                        "(battle update count; 100 ms each)")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        except OSError:
            pass
