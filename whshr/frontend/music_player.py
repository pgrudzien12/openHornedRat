"""The looping front-end tune on pygame's music channel, replayed from the new recording when the music source changes.

Glue screens, the debrief and the credits loop one tune each (notes/briefing_dialogue.md §2.1). This module remembers
which track loops and from which source (whshr.music_source), so closing Options after a source change restarts
that track from the chosen recording instead of waiting for the next tune. The battlefield owns the channel on its
own terms (whshr.frontend.battle_music) and calls :func:`forget` when it takes it over.
"""

from dataclasses import dataclass

import pygame

from ..audio_settings import audio_settings
from ..music_source import MusicSource, music_source_setting, music_track
from ..paths import Installation


@dataclass(frozen=True)
class _Looping:
    installation: Installation
    track: str
    source: MusicSource


_looping: _Looping | None = None


def play_looping(installation: Installation, track: str) -> None:
    """Load and loop ``track`` from the chosen source. Raises FileNotFoundError or pygame.error like pygame does."""
    global _looping
    source = music_source_setting.source
    pygame.mixer.music.load(str(music_track(installation, track, source)))
    pygame.mixer.music.set_volume(audio_settings.volume("music"))
    pygame.mixer.music.play(loops=-1)
    _looping = _Looping(installation, track, source)


def forget() -> None:
    """The looping tune stopped or another owner took the channel."""
    global _looping
    _looping = None


def looping_track() -> str | None:
    return _looping.track if _looping is not None else None


def follow_source_change() -> None:
    """Replay the looping tune if the music source changed since it started; a missing file leaves silence."""
    if _looping is None or _looping.source is music_source_setting.source or not pygame.mixer.get_init():
        return
    try:
        play_looping(_looping.installation, _looping.track)
    except (FileNotFoundError, pygame.error):
        forget()
