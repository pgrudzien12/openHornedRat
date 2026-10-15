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


# notes/pe_resources.md "ANTXT": the strings of movie M are M x 1000 + k; k = 10, 20 ... are speech lines and
# k = 100, 101 ... narration captions; +510 is an alternative version's speech. PROVISIONAL: the captions are taken
# as k = 100..499, and a caption a film's own event track already times (13100 in A13) is left to the subtitles.
CAPTION_OFFSETS = range(100, 500)
_MOVIE_NUMBER = re.compile(r"a(\d+)[a-z]?", re.IGNORECASE)


def movie_number(movie: str) -> int | None:
    """The movie number M of a numbered cutscene name ("A12b" -> 12); None for the unnumbered ones (DEATH01)."""
    match = _MOVIE_NUMBER.fullmatch(movie.strip())
    return int(match.group(1)) if match else None


def timed_text_ids(media: Mapping[str, Any]) -> set[int]:
    """The string ids a film's event tracks already show as timed subtitles."""
    ids: set[int] = set()
    for entry in media.get("objects", {}).values():
        event = entry.get("evt")
        rows = event.get("rows", ()) if event else ()
        if event and event.get("fields") in (5, 6) and rows:
            ids.add(rows[0][1])
    return ids


def narration_caption_ids(movie: str, strings: Mapping[int, str], media: Mapping[str, Any]) -> tuple[int, ...]:
    """The narration captions shown as a text page before film ``movie``, in id order.

    The user's observation of the original: almost every cutscene starts with a text page, then the film. The
    captions are in no film's event track and no glue script names them, so they are found by the movie number.
    PROVISIONAL for the films whose numbering is irregular (A12b, A16a/b, A18B, A20, A27): every film of a number
    gets that number's captions."""
    number = movie_number(movie)
    if number is None:
        return ()
    timed = timed_text_ids(media)
    first, last = number * 1000 + CAPTION_OFFSETS.start, number * 1000 + CAPTION_OFFSETS.stop
    return tuple(sorted(text_id for text_id in strings if first <= text_id < last and text_id not in timed))


def narration_text(movie: str, strings: Mapping[int, str], media: Mapping[str, Any]) -> str:
    """The text page before a film: its captions joined as they are stored (each fragment ends in its own space)."""
    return "".join(strings[text_id] for text_id in narration_caption_ids(movie, strings, media)).strip()
