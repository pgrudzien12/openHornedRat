"""Leader-portrait pop-up shown for battle reactions (notes/react_portrait.md sections 3-4).

The portrait rectangle of the command panel shows the compass until a reaction is shown; it then switches to the
reacting unit for 25 ticks. One pop-up at a time: reactions that arrive meanwhile keep their text and speech but
do not replace the portrait or restart the timer. The face is always frame 0 of the portrait sheet; two overlay
layers animate on top of it (eyes blinking in a loop, a mouth sequence chosen by the expression and played once).
"""
from __future__ import annotations

from dataclasses import dataclass

POPUP_TICKS = 25
MAX_EXPRESSION = 4  # expressions above this are ignored (not present in shipped data)

Sequence = tuple[tuple[int, int], ...]  # (frame, ticks) runs


def _runs(*frames: int | tuple[int, int]) -> Sequence:
    return tuple(item if isinstance(item, tuple) else (item, 1) for item in frames)


# Mouth sequences per expression, keyed by sheet frame count (8, 7 or 6); each ends on frame 1 and then holds
# (notes/react_portrait.md section 4). Any frame count above 8 uses the 8-frame set, below 7 the 6-frame set.
_MOUTH: dict[int, tuple[Sequence, ...]] = {
    8: (_runs((3, 1), (5, 3), (1, 1)),
        _runs(5, 3, 6, 4, 1),
        _runs(1, 4, 3, 6, 5, 3, 1),
        _runs(1, 3, 5, 4, 6, 4, 5, 6, 3, 1, 5, 3, 1),
        _runs((3, 1), (4, 5), (1, 1))),
    7: (_runs((3, 1), (4, 4), (1, 1)),
        _runs((5, 1), (3, 1), (1, 1), (4, 4), (1, 1)),
        _runs((3, 1), (4, 4), (5, 1), (3, 1), (1, 1), (5, 1), (1, 1)),
        _runs(1, 3, 5, 4, 3, 4, 1, 5, 3, 5, 4, 3, 1),
        _runs((3, 1), (4, 5), (1, 1))),
    6: (_runs((1, 1), (3, 4), (1, 1)),
        _runs((4, 1), (1, 1), (3, 4), (4, 1), (1, 1)),
        _runs((3, 1), (1, 1), (3, 4), (1, 1), (4, 1), (3, 4), (1, 1)),
        _runs(1, 4, 1, 3, 4, 3, 1, 4, 3, 1, 4, 3, 1, 4, 3, 1),
        _runs((1, 1), (3, 5), (1, 1))),
}
EYES_OPEN = 2


def _eyes(closed: int, *open_ticks: int) -> Sequence:
    runs: list[tuple[int, int]] = []
    for index, ticks in enumerate(open_ticks):
        runs.append((EYES_OPEN, ticks))
        if index < len(open_ticks) - 1:
            runs.append((closed, 2))
    return tuple(runs)


def _eye_loop(expression: int, closed: int) -> Sequence:
    """Blink loop: expressions 0 and 4 use one blink pattern, 1-3 another; each blink is 2 closed ticks."""
    if expression in (0, 4):
        pattern = (2, 5, 11)
    else:
        pattern = (2, 6, 2, 9, 11)
    return _eyes(closed, *pattern[:-1]) + ((closed, 2), (EYES_OPEN, pattern[-1]))


def _sheet_set(frame_count: int) -> int:
    return 8 if frame_count >= 8 else 7 if frame_count == 7 else 6


def _frame_at(sequence: Sequence, age: int, loop: bool) -> int:
    total = sum(ticks for _, ticks in sequence)
    if loop:
        age %= total
    elif age >= total:
        return sequence[-1][0]
    for frame, ticks in sequence:
        if age < ticks:
            return frame
        age -= ticks
    return sequence[-1][0]


def overlay_frames(expression: int, frame_count: int, age: int) -> tuple[int, int]:
    """(eyes frame, mouth frame) of a portrait sheet with `frame_count` frames, `age` ticks after the pop-up began."""
    expression = max(0, min(MAX_EXPRESSION, expression))
    closed = frame_count - 1
    eyes = _frame_at(_eye_loop(expression, closed), age, loop=True)
    mouth = _frame_at(_MOUTH[_sheet_set(frame_count)][expression], age, loop=False)
    return eyes, mouth


@dataclass
class PortraitPopup:
    """The pop-up state: idle (the compass shows) or counting down for one reacting unit."""

    unit_id: str | None = None
    expression: int = 0
    ticks_left: int = 0
    age: int = 0

    @property
    def active(self) -> bool:
        return self.unit_id is not None and self.ticks_left > 0

    def offer(self, unit_id: str, expression: int) -> bool:
        """Show `unit_id`'s portrait unless one is already up or the expression is ignored; True if it started."""
        if self.active or not 0 <= expression <= MAX_EXPRESSION:
            return False
        self.unit_id, self.expression, self.ticks_left, self.age = unit_id, expression, POPUP_TICKS, 0
        return True

    def tick(self) -> None:
        if not self.active:
            return
        self.ticks_left -= 1
        self.age += 1
        if self.ticks_left <= 0:
            self.unit_id = None
