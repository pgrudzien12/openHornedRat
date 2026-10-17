"""Which recording of a music track plays: the MIDI file, or one of the Steam edition's MP3 recordings.

An engine extension. The Steam "Classic" edition ships two MP3 recordings per General MIDI track next to the MIDI
files (notes/steam_edition.md §7): ``<TRACK>.MP3``, a recording of the General MIDI arrangement, and
``<TRACK>CD.MP3``, the edition's "CD" version (the same file for 7 of the 21 tracks). Other editions have no MP3
music, so the choice exists only where the installation has it (:func:`has_mp3_music`); everywhere else, and for a
track whose recording is missing, the MIDI file plays as before.

The choice is a player setting saved as ``music.json`` in the engine's save directory. A new player, and a run
without a save directory, starts on MIDI.
"""

import json
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

from .paths import Installation


@dataclass(frozen=True)
class MusicSource:
    name: str  # the saved identifier
    label: str  # the Options window's text
    suffix: str  # appended to the track name; "" with extension ".MID" is the MIDI file
    extension: str


MIDI = MusicSource("midi", "MIDI", "", ".MID")
MP3 = MusicSource("mp3", "MP3", "", ".MP3")
CD = MusicSource("cd", "CD", "CD", ".MP3")
SOURCES = (MIDI, MP3, CD)
BY_NAME = {source.name: source for source in SOURCES}


def has_mp3_music(installation: Installation | None) -> bool:
    """True if the installation ships MP3 recordings of its music (the Steam edition does; GOG does not)."""
    if installation is None:
        return False
    try:
        folder = installation.binary_dir("MUSIC")
    except FileNotFoundError:
        return False
    return any(child.suffix.casefold() == ".mp3" for child in folder.iterdir())


class MusicSourceSetting:
    """The current source, persisted as ``music.json`` in the engine's save directory."""

    def __init__(self) -> None:
        self.path: Path | None = None
        self.source = MIDI

    def configure(self, save_dir: str | PathLike[str] | None) -> None:
        self.path = Path(save_dir) / "music.json" if save_dir is not None else None
        self.source = MIDI
        if self.path is None:
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.source = BY_NAME.get(raw.get("source"), MIDI)
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def save(self, source: MusicSource) -> None:
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"source": source.name}) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        self.source = source


music_source_setting = MusicSourceSetting()


def music_track(installation: Installation, track: str, source: MusicSource | None = None) -> Path:
    """The file to play for the General MIDI track name ``track`` (e.g. ``BATTLE``, ``sighted``).

    Uses the chosen source's recording when the installation has it, else the MIDI file; raises FileNotFoundError
    if neither exists.
    """
    chosen = music_source_setting.source if source is None else source
    if chosen is not MIDI:
        try:
            return installation.binary_file("MUSIC", f"{track}{chosen.suffix}{chosen.extension}")
        except FileNotFoundError:
            pass
    return installation.binary_file("MUSIC", f"{track}.MID")
