"""The battle's control piece: the gate whose own animation drives the battle state.

Behaviour source: notes/bf015_gate_npc_column.md Q1 (and notes/battle_end_objectives.md 5.1). Scripts write the
battle state (`SetBattleState`); a gate piece answers a request (2 = open, 5 = shut) with its animation and sets the
end state itself. The piece steps once per battle tick, after the units, so scripts later in the tick that wrote the
request still read it, and the end state is read from the following tick on. Gate and door pieces have no footprint.

Not modelled: the mole hole (BF040, a mesh-swap sequence whose length is not in the report); its state is left to the
scripts.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

SWING_FRAMES = 16  # both swinging-door animations show 16 frames (1.2 "Timing")
SWING_HOLD = 3  # each frame is held for 3 steps
SWING_END = 49  # the end state comes 49 steps after the first frame: 15 x 3 holds + the end marker + the report
SWING_TURN_PER_FRAME = 1 / 63  # frame k = k / 63 of a full turn
PORTCULLIS_STEPS = 30  # a counter run to 30; the door moves on the first 29
PORTCULLIS_LIFT = 10.0  # mesh units straight up when open


@dataclass(frozen=True)
class Door:
    """A door piece the control piece creates and hangs at its hinge (piece frame, y up, mesh units)."""

    name: str
    hinge: tuple[float, float, float]
    sense: int  # the door turns by sense x angle about the up axis (the two doors mirror each other)


SWINGING: dict[str, tuple[Door, Door]] = {
    "zhufwallent": (Door("ZhufWallDoorL", (2.5, 0.0, -5.0), -1), Door("ZhufWallDoorR", (17.5, 0.0, -5.0), 1)),
    "niteunderwayent": (Door("NiteUnderwayDrL", (-15.0, 0.0, 2.5), -1), Door("NiteUnderwayDrR", (15.0, 0.0, 2.5), 1)),
}
PORTCULLIS: dict[str, Door] = {"portcullisent": Door("PortcullisDoor", (0.0, 0.0, 0.0), 0)}
MOLE_HOLES = frozenset({"molehole0", "molehole8"})


@dataclass
class ControlPiece:
    """The first gate-type furniture piece of the battle file and its animation progress."""

    name: str
    x: float
    y: float
    direction: int
    kind: str  # "swing", "portcullis" or "mole"
    count: int = 0  # steps since the running animation started
    opening: bool = True  # which way the last animation ran

    @property
    def initial_state(self) -> int:
        """The state the piece sets at load: 1 (closed, idle) for gates, 0 for the mole hole."""
        return 0 if self.kind == "mole" else 1

    def step(self, state: int) -> int:
        """One display step: answer a request or advance the running animation; returns the new battle state."""
        if self.kind == "swing":
            if state in (2, 5):  # start, show the first frame, and enter the running state in the same step
                self.count, self.opening = 0, state == 2
                return state + 1
            if state in (3, 6):
                self.count += 1
                return state + 1 if self.count >= SWING_END else state
        elif self.kind == "portcullis":
            if state in (2, 5):  # 1.3: 2 -> 3 (opening); 5 -> 7 at once (closing), 6 once shut
                self.count, self.opening = 0, state == 2
                return 3 if state == 2 else 7
            if state in (3, 7):
                self.count += 1
                if self.count >= PORTCULLIS_STEPS:
                    return 4 if state == 3 else 6
        return state

    def swing_frame(self) -> int:
        """Opening frame 0..15 the doors show (0 closed, 15 fully open)."""
        frame = min(self.count // SWING_HOLD, SWING_FRAMES - 1)
        return frame if self.opening else SWING_FRAMES - 1 - frame

    def door_turn(self) -> float:
        """The doors' swing as a fraction of a full turn (stepped: frame / 63)."""
        return self.swing_frame() * SWING_TURN_PER_FRAME

    def portcullis_lift(self) -> float:
        """Height of the portcullis door above its closed position, in mesh units (linear over 29 steps)."""
        moved = min(self.count, PORTCULLIS_STEPS - 1) * PORTCULLIS_LIFT / (PORTCULLIS_STEPS - 1)
        return moved if self.opening else PORTCULLIS_LIFT - moved

    def doors(self) -> tuple[Door, ...]:
        key = self.name.casefold()
        if key in SWINGING:
            return SWINGING[key]
        if key in PORTCULLIS:
            return (PORTCULLIS[key],)
        return ()


def from_scenery(scenery: Iterable[Mapping[str, Any]]) -> ControlPiece | None:
    """The battle's control piece, or None when its furniture has no gate-type piece."""
    for item in scenery:
        name = str(item.get("name", ""))
        key = name.casefold()
        kind = ("swing" if key in SWINGING else "portcullis" if key in PORTCULLIS
                else "mole" if key in MOLE_HOLES else None)
        if kind is not None:
            return ControlPiece(name, float(item.get("x") or 0), float(item.get("y") or 0),
                                int(item.get("dir") or 0) % 512, kind)
    return None
