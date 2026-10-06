"""Best-effort playback of named missile cues from a user's installed MISSILE.SFX packet."""
from __future__ import annotations

from typing import Any

import pygame

from ..audio import parse_sfx
from ..paths import Installation


LAUNCH_TERMS = {
    1: "ShootArrow", 2: "Arrow", 5: "Cannon", 6: "Mortar", 7: "Cannon",
    8: "Rock", 9: "ShootArrow", 11: "Cannon", 12: "Doom", 17: "Mortar",
    18: "ShootArrow", 19: "ShootArrow",
}


class MissileSounds:
    def __init__(self, installation: Installation | None, loaded: bool) -> None:
        self.effects: dict[str, tuple[pygame.mixer.Sound, ...]] = {}
        if installation is None or not loaded:
            return
        packet = (installation.find("UPDATE", "BINARY", "SOUND", "MISSILE", "MISSILE.SFX")
                  or installation.find("FILE", "BINARY", "SOUND", "MISSILE", "MISSILE.SFX"))
        if packet is None:
            return
        try:
            decoded = parse_sfx(packet.read_bytes())
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            raw_effects: dict[str, Any] = {}
            for effect in decoded.get("effects", ()):
                name = effect.get("name")
                wav = effect.get("wav")
                if not isinstance(name, str) or not isinstance(wav, str):
                    continue
                path = (installation.find("UPDATE", "BINARY", "SOUND", "MISSILE", wav)
                        or installation.find("FILE", "BINARY", "SOUND", "MISSILE", wav))
                if path is not None:
                    raw_effects[name.casefold()] = (effect, pygame.mixer.Sound(str(path)))
            for name, (effect, sound) in raw_effects.items():
                members = effect.get("list_names")
                if members:
                    self.effects[name] = tuple(raw_effects[member.casefold()][1]
                                               for member in members if isinstance(member, str)
                                               and member.casefold() in raw_effects)
                else:
                    self.effects[name] = (sound,)
        except (OSError, ValueError, pygame.error):
            self.effects.clear()

    def play(self, code: int, *, impact: bool = False) -> None:
        term = "Explosion" if impact else LAUNCH_TERMS.get(code, "")
        if not term:
            return
        sounds = next((effect for name, effect in self.effects.items() if term.casefold() in name), ())
        for sound in sounds:
            sound.play()
