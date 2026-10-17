"""Battlefield MIDI ownership, deployment playback and ordinary pause (notes/battle_music.md)."""

import pygame

from ..audio_settings import audio_settings
from ..music_source import music_track
from . import music_player
from ..paths import Installation

COMPLETION_INTERVAL = 2.5  # report §2: completion is polled independently of simulation ticks


class BattleMusic:
    """Own the shared music channel until battlefield departure. Missing audio stays silent for this entry.

    The current engine has a common volume control and GM playback only; GM/FM arrangement selection
    remains unmodelled. Setting volume to zero suspends the prepared tune rather than discarding it.
    """

    def __init__(self, installation: Installation | None) -> None:
        self.loaded = False
        self.started = False
        self.suspended = False
        self.closed = False
        self.completion_elapsed = 0.0
        self.volume = -1.0
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            # Replacement precedes asset lookup: a missing battle tune must not leave campaign music playing.
            music_player.forget()
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            if installation is None:
                return
            path = music_track(installation, "BATTLE")
            pygame.mixer.music.load(str(path))
            self.loaded = True
        except (OSError, pygame.error):
            self.release()
            return
        self.update(0.0, paused=False)

    def update(self, seconds: float, *, paused: bool) -> None:
        """Apply pause and volume changes; poll completion only while playback is enabled and unpaused."""
        if self.closed or not self.loaded:
            return
        try:
            volume = audio_settings.volume("music")
            if volume != self.volume:
                pygame.mixer.music.set_volume(volume)
                self.volume = volume
            if paused or volume == 0:
                if self.started and not self.suspended:
                    pygame.mixer.music.pause()
                    self.suspended = True
                return
            if not self.started:
                pygame.mixer.music.play()
                self.started = True
            elif self.suspended:
                pygame.mixer.music.unpause()
                self.suspended = False
            self.completion_elapsed += seconds
            if self.completion_elapsed >= COMPLETION_INTERVAL:
                self.completion_elapsed %= COMPLETION_INTERVAL
                if not pygame.mixer.music.get_busy():
                    pygame.mixer.music.play()
        except pygame.error:
            # Device failure must not interrupt gameplay. Retry only on a fresh battlefield entry (§4).
            self.release()

    def release(self) -> None:
        """Stop and release before departure; repeated cleanup cannot stop the next scene's tune."""
        if self.closed:
            return
        self.closed = True
        self.loaded = False
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except pygame.error:
            pass
