# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Cutscene text: the speech subtitles typed under the film, the caption page before it, and the film's fades.

Speech subtitles follow notes/cutscene_subtitles.md: each speech event track takes one of two subtitle blocks
under the film at its first record and keeps it until its last; the text is typed in step with the records'
``current_tick`` into a two-line block that scrolls up when a word does not fit.
"""

import bisect
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

Rgb = tuple[int, int, int]

# notes/cutscene_subtitles.md 3.1: the speaker field only picks the colour.
SPEAKER_COLORS: dict[int, Rgb] = {
    0: (0, 0, 0), 1: (255, 255, 255), 2: (255, 0, 0), 3: (0, 255, 0), 4: (0, 0, 255),
    5: (255, 255, 0), 6: (255, 0, 255), 7: (0, 255, 255),
}
DEFAULT_SUBTITLE_COLOR: Rgb = (255, 255, 255)
SUBTITLE_BLOCKS = 2  # upper and lower (notes/cutscene_subtitles.md 1)


def subtitle_color(speaker: int) -> Rgb:
    """The subtitle colour of an event speaker field."""
    return SPEAKER_COLORS.get(speaker, DEFAULT_SUBTITLE_COLOR)


@dataclass(frozen=True)
class SpeechTrack:
    """One speech event track: its (joined) text, colour slot, tick range and record times."""

    text_id: int
    text: str
    speaker: int
    first_tick: int
    last_tick: int
    times: tuple[float, ...]  # record times in seconds, ascending
    ticks: tuple[int, ...]  # each record's current_tick

    @property
    def start_seconds(self) -> float:
        return self.times[0]

    @property
    def end_seconds(self) -> float:
        """The time of the clearing record (current_tick = last_tick), or past the last record if it has none."""
        return self.times[-1] if self.ticks[-1] >= self.last_tick else float("inf")

    def visible_count(self, elapsed_seconds: float) -> int | None:
        """Characters typed at ``elapsed_seconds`` (notes/cutscene_subtitles.md 3.2); None before the first record
        or from the clearing record on."""
        index = bisect.bisect_right(self.times, elapsed_seconds) - 1
        if index < 0:
            return None
        tick = self.ticks[index]
        if tick >= self.last_tick:
            return None
        span = self.last_tick - self.first_tick - 1
        if span <= 0:
            return len(self.text)
        return max(0, min(len(self.text), len(self.text) * (tick - self.first_tick) // span))


def speech_tracks(media: Mapping[str, Any], strings: Mapping[int, str]) -> tuple[SpeechTrack, ...]:
    """The film's speech tracks with known text, in start order. Rows are (time_ms, text id, speaker, first, current,
    last[, extra]); a six-field track joins ``extra`` further ids with no separator (notes/cutscene_subtitles.md 4)."""
    tracks: list[SpeechTrack] = []
    for entry in media.get("objects", {}).values():
        event = entry.get("evt")
        rows = event.get("rows", ()) if event else ()
        if not event or event.get("fields") not in (5, 6) or not rows:
            continue
        text_id, speaker, first, _, last = (int(value) for value in rows[0][1:6])
        text = strings.get(text_id)
        if text is None:
            continue
        if event.get("fields") == 6:
            text += "".join(strings.get(text_id + offset, "") for offset in range(1, int(rows[0][6]) + 1))
        tracks.append(SpeechTrack(text_id, text, speaker, first, last,
                                  tuple(row[0] / 1000 for row in rows), tuple(int(row[4]) for row in rows)))
    return tuple(sorted(tracks, key=lambda track: (track.start_seconds, track.text_id)))


def teleprompter_lines(text: str, count: int, fits: Callable[[str], bool]) -> tuple[str, str]:
    """The (top, bottom) lines of a block after typing ``text[:count]`` (notes/cutscene_subtitles.md 2, 3.3).

    Typing starts on the bottom line. Before the first letter of a word, the bottom line plus that whole word is
    measured; if it does not fit, the space before the word is the break: the bottom line moves up (the old top
    line is dropped) and the word starts a new bottom line."""
    top, bottom = "", ""
    for index in range(count):
        char = text[index]
        if not char.isspace() and (index == 0 or text[index - 1].isspace()) and bottom:
            end = index
            while end < len(text) and not text[end].isspace():
                end += 1
            if not fits(bottom + text[index:end]):
                top, bottom = bottom.rstrip(), ""
        bottom += char
    return top, bottom


@dataclass(frozen=True)
class BlockText:
    """What one subtitle block shows: its colour and its two lines."""

    color: Rgb
    top: str
    bottom: str


class SpeechSubtitles:
    """The two subtitle blocks over time (notes/cutscene_subtitles.md 1, 4).

    A track takes the first free block (upper first) at its first record and frees it at its clearing record; a
    track that finds both busy is not shown (never happens in the shipped films)."""

    def __init__(self, media: Mapping[str, Any], strings: Mapping[int, str]) -> None:
        self.tracks = speech_tracks(media, strings)
        self.blocks: dict[int, int] = {}  # track index -> block (0 upper, 1 lower)
        busy_until = [float("-inf")] * SUBTITLE_BLOCKS
        for index, track in enumerate(self.tracks):
            free = next((block for block in range(SUBTITLE_BLOCKS) if busy_until[block] <= track.start_seconds),
                        None)
            if free is not None:
                self.blocks[index] = free
                busy_until[free] = track.end_seconds

    def at(self, elapsed_seconds: float, fits: Callable[[str], bool]) -> tuple[BlockText | None, ...]:
        """Each block's text at ``elapsed_seconds`` (None: hidden). ``fits`` tells whether a line fits the block."""
        shown: list[BlockText | None] = [None] * SUBTITLE_BLOCKS
        for index, block in self.blocks.items():
            track = self.tracks[index]
            count = track.visible_count(elapsed_seconds)
            if count is not None:
                top, bottom = teleprompter_lines(track.text, count, fits)
                shown[block] = BlockText(subtitle_color(track.speaker), top, bottom)
        return tuple(shown)


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

    Both fades darken the picture by subtracting a fixed amount from every red, green and blue component of the
    film's colours (clamped at 0), not by scaling them. ``AnimDone`` (one field, 98, 96 ... 0 every 125 ms) sets the
    film's sound volume to its value and subtracts 5 more per record, so both fade out together at the end.
    ``Fade (10, 10)`` marks the moment from which a skip fades out quickly instead of cutting; the first ``AnimDone``
    record removes that mark again. The skip fade is ten steps run back to back: step ``k`` subtracts 16 more and
    then sets the volume to ``(11 - k) * 10`` %."""

    ANIM_DONE_DARKEN = 5
    SKIP_FADE_STEPS = 10
    SKIP_FADE_DARKEN = 16
    # The steps have no timer of their own (one repaint each); the engine shows one per 60 Hz display frame.
    SKIP_FADE_STEP_SECONDS = 1 / 60

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

    def _records(self, elapsed_seconds: float) -> int:
        """How many ``AnimDone`` records have been reached by ``elapsed_seconds``."""
        return sum(1 for time, _ in self.anim_done if time <= elapsed_seconds)

    def volume(self, elapsed_seconds: float) -> int:
        """The film's volume percentage at ``elapsed_seconds``: 100 until AnimDone's first record."""
        reached = self._records(elapsed_seconds)
        return self.anim_done[reached - 1][1] if reached else 100

    def darken(self, elapsed_seconds: float) -> int:
        """How much has been subtracted from every film colour component by ``elapsed_seconds``."""
        return self.ANIM_DONE_DARKEN * self._records(elapsed_seconds)

    def skip_fades(self, elapsed_seconds: float) -> bool:
        """Whether a skip at ``elapsed_seconds`` fades out: past the Fade marker and before the end fade began."""
        return (self.fade_mark is not None and elapsed_seconds >= self.fade_mark
                and self._records(elapsed_seconds) == 0)

    @classmethod
    def skip_step(cls, step: int) -> tuple[int, int]:
        """The extra darkening and the volume after skip-fade step ``step`` (1 ... 10)."""
        return cls.SKIP_FADE_DARKEN * step, (cls.SKIP_FADE_STEPS + 1 - step) * 10
