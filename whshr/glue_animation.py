# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Deterministic 50 ms animation state for glue ``[BITMAP]`` records."""

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any


STEP_MILLISECONDS = 50


@dataclass(frozen=True)
class AnimationUpdate:
    bitmap: str
    redrawn: bool
    finished: bool = False


class GlueBitmapAnimator:
    """Advance one bitmap using the original descending-frame state machine."""

    def __init__(self, spec: Mapping[str, Any]) -> None:
        self.base = spec["bitmap"]
        self.current = int(spec.get("animstartframe", -1))
        self.restart = int(spec.get("animrestartframe", self.current))
        if "animstopframe" in spec:
            self.stop = int(spec["animstopframe"])
        elif "animstartframe" in spec:
            # A start frame with no stop frame (e.g. the Mark*Object cross markers, Cross8 S=7)
            # reveals that one frame on its first step and then holds it (notes/campaign_tent.md
            # §5.3): it is not the same as an explicit S == E, which is static from the start.
            self.stop = self.current - 1
        else:
            self.stop = self.current  # both absent: S = E, static, draws the literal base name
        self.period = int(spec.get("timecnt", 0))
        self.loop_delay = int(spec.get("looptimecnt", 0))
        self.delay = self.period
        self._millisecond_remainder = 0
        self._timer_remainder = 0
        self.drawn_name = self.base

    @property
    def finished(self) -> bool:
        return self.current == self.stop

    @property
    def display_name(self) -> str:
        """The resource a renderer should show before and after the first timer step."""
        return self.drawn_name

    def tick(self, milliseconds: float) -> AnimationUpdate:
        """Apply one original-style animation step at most, returning its update."""
        if milliseconds < 0:
            raise ValueError("tick duration must not be negative")
        elapsed = self._millisecond_remainder + int(milliseconds)
        self._timer_remainder += elapsed // 25
        self._millisecond_remainder = elapsed % 25
        if self._timer_remainder < 2:
            return AnimationUpdate(self.drawn_name, False)
        self._timer_remainder &= 1  # Late timer messages do not catch up multiple frames.
        return self.step()

    def step(self) -> AnimationUpdate:
        if self.current == self.stop:
            return AnimationUpdate(self.drawn_name, False, True)
        if self.delay > 0:
            self.delay -= 1
            return AnimationUpdate(self.drawn_name, False)
        if self.current != -1:
            self.drawn_name = re.sub(r"\d+$", "", self.base) + str(self.current)
        frame = self.drawn_name
        extra = 0
        if self.current >= 0:
            self.current -= 1
            if self.current < 0:
                if self.stop == -1:
                    self.current = self.restart
                    extra = self.loop_delay
                else:
                    self.current = -1
        self.delay = self.period + extra
        return AnimationUpdate(frame, True)
