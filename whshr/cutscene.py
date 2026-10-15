# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Timed text cues decoded from Omni cutscene event tracks.

The event tracks advance at the cutscene's fixed 8 Hz cadence.  They identify a
string resource and give the complete display interval, but do not contain
per-character timestamps.  ``SubtitleTimeline`` therefore reveals characters
evenly through most of that recorded interval, then keeps completed text on
screen for a short reading hold.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


# The event track's speaker field is a stable slot (2, 3 or 4), not a random
# value.  The original subtitles use the corresponding primary display color.
SPEAKER_COLORS: dict[int, tuple[int, int, int]] = {3: (0, 255, 0), 4: (0, 0, 255), 2: (255, 0, 0)}
DEFAULT_SUBTITLE_COLOR: tuple[int, int, int] = (255, 255, 255)


def subtitle_color(speaker: int) -> tuple[int, int, int]:
    """Return the original-style RGB subtitle color for an event speaker slot."""
    return SPEAKER_COLORS.get(speaker, DEFAULT_SUBTITLE_COLOR)


@dataclass(frozen=True)
class SubtitleCue:
    """One line of cutscene text and its original 125 ms display interval."""

    text_id: int
    text: str
    speaker: int
    start_seconds: float
    reveal_end_seconds: float
    end_seconds: float

    def text_at(self, elapsed_seconds: float) -> str:
        """Return the typewritten portion visible at ``elapsed_seconds``."""
        if elapsed_seconds < self.start_seconds or elapsed_seconds >= self.end_seconds:
            return ""
        duration = self.reveal_end_seconds - self.start_seconds
        progress = min(1.0, (elapsed_seconds - self.start_seconds) / duration)
        # Keep the first glyph visible on the event's first frame, then reveal
        # uniformly through the recorded speech/subtitle lifetime.
        count = min(len(self.text), max(1, int(progress * len(self.text)) + 1))
        return self.text[:count]


class SubtitleTimeline:
    """Resolve active subtitle cues from ``process_si`` media and ANTXT strings."""

    TICK_SECONDS = 0.125
    REVEAL_FRACTION = 0.8
    READING_HOLD_SECONDS = 1.0

    def __init__(self, media: Mapping[str, Any], strings: Mapping[int, str]) -> None:
        cues: list[SubtitleCue] = []
        for entry in media.get("objects", {}).values():
            event = entry.get("evt")
            rows = event.get("rows", ()) if event else ()
            # Speech event rows are (time_ms, string id, speaker, first,
            # current, last[, flag]).  Fade/animation events have fewer fields.
            if not event or event.get("fields") not in (5, 6) or not rows:
                continue
            text_id, speaker = rows[0][1:3]
            text = strings.get(text_id)
            if text is None:
                continue
            if event.get("fields") == 6:
                # notes/cutscene_narration.md 4.4: a six-field track's last field counts further ids joined to it
                extra = int(rows[0][-1])
                text += "".join(strings.get(text_id + offset, "") for offset in range(1, extra + 1))
            start = rows[0][0] / 1000
            source_end = (rows[-1][0] / 1000) + self.TICK_SECONDS
            cues.append(SubtitleCue(
                text_id, text, speaker, start,
                start + (source_end - start) * self.REVEAL_FRACTION,
                source_end + self.READING_HOLD_SECONDS,
            ))
        self.cues = tuple(sorted(cues, key=lambda cue: (cue.start_seconds, cue.text_id)))

    def current(self, elapsed_seconds: float) -> SubtitleCue | None:
        """Return the newest active cue; dialogue overlaps replace older text."""
        active = [cue for cue in self.cues
                  if cue.start_seconds <= elapsed_seconds < cue.end_seconds]
        return active[-1] if active else None

    def text_at(self, elapsed_seconds: float) -> str:
        cue = self.current(elapsed_seconds)
        return cue.text_at(elapsed_seconds) if cue else ""


# notes/cutscene_narration.md 2.2: the narration page of each film, as (first ANTXT id, number of further ids), keyed
# by the film number (the digits after the leading "A"; letters after them are ignored). A film number with no row
# (A9, A14, DEATH01/02 = 0) has no page. Row 21 belongs to no film: 21100-21101 are never shown.
NARRATION_CAPTIONS: dict[int, tuple[int, int]] = {
    1: (1100, 2), 2: (2100, 0), 3: (3100, 2), 4: (4100, 0), 5: (5100, 0), 6: (6100, 0), 7: (7100, 1),
    8: (8100, 2), 10: (10100, 0), 11: (11100, 0), 12: (12100, 0), 13: (13200, 0), 15: (15100, 0),
    16: (16100, 0), 17: (17100, 0), 18: (18100, 1), 20: (20100, 0), 21: (21100, 1), 22: (22100, 1),
    23: (23100, 1), 24: (24100, 0), 25: (25100, 0), 26: (26100, 0), 27: (27100, 3),
}
# notes/cutscene_narration.md 2.1: the one name exception, film 16 with "B" right after the number (A16b).
A16B_CAPTIONS = (16600, 1)
_MOVIE_NAME = re.compile(r"a(\d+)(.?)", re.IGNORECASE)


def movie_number(movie: str) -> int:
    """The film number (notes/cutscene_narration.md 2.1): "A12b" -> 12; 0 for a name without one (DEATH01)."""
    match = _MOVIE_NAME.match(movie.strip())
    return int(match.group(1)) if match else 0


def narration_caption_ids(movie: str) -> tuple[int, ...]:
    """The ANTXT ids of the page shown before film ``movie``, chosen from its name alone."""
    match = _MOVIE_NAME.match(movie.strip())
    number = int(match.group(1)) if match else 0
    row = A16B_CAPTIONS if number == 16 and match and match.group(2).casefold() == "b" else NARRATION_CAPTIONS.get(number)
    if row is None:
        return ()
    first, extra = row
    return tuple(range(first, first + extra + 1))


def narration_text(movie: str, strings: Mapping[int, str]) -> str:
    """The page text: its captions concatenated with no separator (each continued fragment ends in its own space,
    notes/cutscene_narration.md 3); leading white space is skipped when wrapping."""
    return "".join(strings.get(text_id, "") for text_id in narration_caption_ids(movie))


class FilmFades:
    """A film's own fade events (notes/cutscene_narration.md 4.3).

    ``AnimDone`` (one field, 98, 96 ... 0 every 125 ms) sets the film's sound volume to that percentage and darkens
    the picture with it, so both fade out together at the end. ``Fade (10, 10)`` marks the moment from which a skip
    fades out quickly instead of cutting."""

    SKIP_FADE_STEPS = 10
    # PROVISIONAL: the report gives ten short steps but not their length.
    SKIP_FADE_STEP_SECONDS = 0.05

    def __init__(self, media: Mapping[str, Any]) -> None:
        anim_done: list[tuple[float, int]] = []
        fade_marks: list[float] = []
        for entry in media.get("objects", {}).values():
            event = entry.get("evt")
            rows = event.get("rows", ()) if event else ()
            if not event or not rows:
                continue
            if event.get("fields") == 1:
                anim_done.extend((row[0] / 1000, int(row[1])) for row in rows)
            elif event.get("fields") == 2:
                fade_marks.append(rows[0][0] / 1000)
        self.anim_done = tuple(sorted(anim_done))
        self.fade_mark: float | None = min(fade_marks) if fade_marks else None

    def level(self, elapsed_seconds: float) -> int:
        """The volume/brightness percentage at ``elapsed_seconds``: 100 until AnimDone's first record."""
        level = 100
        for time, value in self.anim_done:
            if time > elapsed_seconds:
                break
            level = value
        return level

    def skip_fades(self, elapsed_seconds: float) -> bool:
        """Whether a skip at ``elapsed_seconds`` fades out (past the Fade marker) rather than cutting."""
        return self.fade_mark is not None and elapsed_seconds >= self.fade_mark
