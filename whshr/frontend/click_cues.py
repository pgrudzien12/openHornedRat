"""Shared glue button and hotspot cues (notes/native-windows.md §1.1)."""

import io

import pygame

from ..audio_settings import audio_settings
from ..paths import Installation
from ..speech import load_speech

_speech_sound: pygame.mixer.Sound | None = None


def set_speech_sound(sound: pygame.mixer.Sound | None) -> None:
    """Track the speech clip across view changes so button cues cannot cover it."""
    global _speech_sound
    _speech_sound = sound


def play_click_cue(installation: Installation | None, cue: int, *, speech_playing: bool = False,
                   speech_enabled: bool = True) -> None:
    """Play a glue speech cue when dialogue audio is available and idle."""
    if (installation is None or cue <= 0 or not speech_enabled or speech_playing
            or audio_settings.volume("dialogue") == 0):
        return
    try:
        if _speech_sound is not None and _speech_sound.get_num_channels() > 0:
            return
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        data = load_speech(installation, cue)
        if data is None:
            return
        sound = pygame.mixer.Sound(io.BytesIO(data))
        sound.set_volume(audio_settings.volume("dialogue"))
        sound.play()
    except pygame.error:
        pass
