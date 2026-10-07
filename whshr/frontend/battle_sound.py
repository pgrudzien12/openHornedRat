"""Playback of the battle's sound cues (`sound` battle events) from the user's installed `.SFX` packets.

A cue names a packet slot and a 0-based effect index (notes/script_animation_sound.md §4, notes/sfx.md "Packet
table"). Each effect plays its WAV at the effect's `pitch` (a playback rate: the same WAV serves several effects at
different pitches) and `volume`; a `LIST` effect plays its members in turn, or one at random with `RANDOM`, and a
`LOOP` effect repeats until its handle is stopped.

PROVISIONAL engine choices: every cue is non-positional (no distance or stereo model yet; `MoveUnitSound` is a
no-op), and the race packets 3-9 are treated as always loaded (notes/sfx.md hypothesis: the game loads them for
the armies present), besides the battle's own `loadsfx` packets.
"""
from __future__ import annotations

from array import array
from collections.abc import Iterable, Mapping, Sequence
import random
from typing import Any, Protocol
import wave

import pygame

from ..audio import parse_sfx
from ..paths import Installation

# notes/sfx.md "Packet table": slot -> (loadsfx name, directory under BINARY/SOUND).
PACKETS: dict[int, tuple[str, tuple[str, ...]]] = {
    1: ("buttonfx", ()), 2: ("Battle2", ("BATTLE",)), 3: ("spells", ("SPELLS",)), 4: ("missile", ("MISSILE",)),
    5: ("HumBtl", ("RACE",)), 6: ("OrcBtl", ("RACE",)), 7: ("DwrfBtl", ("RACE",)), 8: ("Skaven", ("RACE",)),
    9: ("Monster", ("RACE",)), 10: ("Retreat", ("SPECIAL",)), 11: ("Zhufbar", ("SPECIAL",)),
    12: ("Dragon", ("SPECIAL",)), 13: ("PortCul", ("SPECIAL",)), 14: ("MoleMach", ("SPECIAL",)),
    15: ("Hiln", ("SPECIAL",)), 16: ("HelpUs", ("SPECIAL",)), 17: ("Peasant", ("SPECIAL",)),
}
ALWAYS_LOADED = frozenset(range(3, 10))  # PROVISIONAL, see the module docstring
ROOTS = (("UPDATE", "BINARY", "SOUND"), ("FILE", "BINARY", "SOUND"))
HANDLES = {"charge_start": "charge", "charge_stop": "charge", "loop_start": "loop", "loop_stop": "loop"}


class Channel(Protocol):
    def get_busy(self) -> bool: ...
    def stop(self) -> None: ...
    def queue(self, sound: Any) -> None: ...


def resample(samples: Sequence[int], channels: int, ratio: float) -> array[int]:
    """Nearest-frame resampling of interleaved 16-bit samples: `ratio` > 1 plays faster and higher."""
    frames = len(samples) // channels
    out: array[int] = array("h")
    if ratio <= 0 or frames == 0:
        return out
    for index in range(int(frames / ratio)):
        start = int(index * ratio) * channels
        out.extend(samples[start:start + channels])
    return out


def members(effect: Mapping[str, Any], effects: Sequence[Mapping[str, Any]], rng: random.Random) -> list[int]:
    """The effect indices one play of `effect` sounds, in order (one at random for a RANDOM list)."""
    names = effect.get("list_names")
    if not names:
        return [int(effect["index"])]
    by_name = {str(e.get("name", "")).casefold(): int(e["index"]) for e in effects}
    found = [by_name[str(name).casefold()] for name in names if str(name).casefold() in by_name]
    if not found:
        return []
    if "RANDOM" in (effect.get("flag_names") or ()):
        return [rng.choice(found)]
    return found


class BattleSounds:
    """Loads packets on first use and plays the battle's `sound` events."""

    def __init__(self, installation: Installation | None, loaded: Iterable[str], rng: random.Random | None = None) -> None:
        self.installation = installation
        names = {str(name).casefold() for name in loaded}
        self.available = {slot for slot, (name, _) in PACKETS.items() if name.casefold() in names} | ALWAYS_LOADED
        self.rng = rng or random.Random()
        self.packets: dict[int, list[dict[str, Any]] | None] = {}
        self.sounds: dict[tuple[int, int], Any] = {}
        self.channels: dict[tuple[int, int], Channel] = {}  # the last channel of each non-overlapping effect
        self.handles: dict[tuple[str, str], Channel] = {}  # (regiment, "charge" | "loop") -> its loop channel
        self.enabled = installation is not None and self._init_mixer()

    @staticmethod
    def _init_mixer() -> bool:
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            return True
        except pygame.error:
            return False

    def handle(self, events: Iterable[Any]) -> None:
        for event in events:
            if getattr(event, "kind", None) == "sound":
                self.cue(event.data)

    def cue(self, data: Mapping[str, Any]) -> None:
        kind = str(data.get("cue", "play"))
        packet, effect = int(data.get("packet") or 0), int(data.get("effect") or 0)
        handle = HANDLES.get(kind)
        key = (str(data.get("regiment", "")), handle) if handle else None
        if kind in ("loop_stop", "charge_stop"):
            channel = self.handles.pop(key, None) if key else None
            if channel is not None:
                channel.stop()
            return
        if kind == "loop_move" or not self.enabled or packet not in self.available:
            return
        if kind in ("play", "global"):
            running = self.channels.get((packet, effect))
            if running is not None and running.get_busy():
                return  # PlaySound does not restart an effect that is still playing
        if key is not None:
            previous = self.handles.pop(key, None)
            if previous is not None:
                previous.stop()
        channel = self._play(packet, effect, loop=key is not None)
        if channel is None:
            return
        self.channels[(packet, effect)] = channel
        if key is not None:
            self.handles[key] = channel

    def _play(self, packet: int, index: int, loop: bool) -> Channel | None:
        effects = self._effects(packet)
        if effects is None or not 0 <= index < len(effects):
            return None
        effect = effects[index]
        repeat = -1 if loop and "LOOP" in (effect.get("flag_names") or ()) else 0
        sounds = [sound for sound in (self._sound(packet, member) for member in members(effect, effects, self.rng))
                  if sound is not None]
        if not sounds:
            return None
        channel = sounds[0].play(loops=repeat)
        if channel is not None:
            for sound in sounds[1:]:
                channel.queue(sound)
        return channel

    def _effects(self, packet: int) -> list[dict[str, Any]] | None:
        if packet not in self.packets:
            self.packets[packet] = self._load_packet(packet)
        return self.packets[packet]

    def _directory(self, packet: int) -> list[tuple[str, ...]]:
        _, sub = PACKETS[packet]
        return [(*root, *sub) for root in ROOTS]

    def _load_packet(self, packet: int) -> list[dict[str, Any]] | None:
        if self.installation is None or packet not in PACKETS:
            return None
        name = PACKETS[packet][0]
        for directory in self._directory(packet):
            path = self.installation.find(*directory, name + ".SFX")
            if path is not None:
                try:
                    return list(parse_sfx(path.read_bytes()).get("effects", ()))
                except (OSError, ValueError):
                    return None
        return None

    def _sound(self, packet: int, index: int) -> Any:
        key = (packet, index)
        if key not in self.sounds:
            self.sounds[key] = self._load_sound(packet, index)
        return self.sounds[key]

    def _load_sound(self, packet: int, index: int) -> Any:
        effects = self._effects(packet)
        if effects is None or self.installation is None or not 0 <= index < len(effects):
            return None
        effect = effects[index]
        wav = effect.get("wav")
        if not isinstance(wav, str):
            return None
        path = next((found for directory in self._directory(packet)
                     if (found := self.installation.find(*directory, wav)) is not None), None)
        if path is None:
            return None
        try:
            with wave.open(str(path), "rb") as stream:
                rate = stream.getframerate()
            sound = pygame.mixer.Sound(str(path))
            pitch = int(effect.get("pitch") or rate)
            mixer = pygame.mixer.get_init()
            if pitch != rate and mixer is not None and abs(mixer[1]) == 16:
                sound = pygame.mixer.Sound(buffer=resample(array("h", sound.get_raw()), mixer[2], pitch / rate))
            sound.set_volume(min(1.0, max(0.0, int(effect.get("volume") or 100) / 100)))
            return sound
        except (OSError, EOFError, wave.Error, pygame.error):
            return None
