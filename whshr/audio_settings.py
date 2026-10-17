"""Engine-owned audio levels shared by the Options window and playback views.

A new player (an engine save directory without a saved, valid level for a channel) starts that channel at 25 %;
a run without a save directory (tests, tools) plays at 100 %.
"""

import json
from os import PathLike
from pathlib import Path

LEVELS = (0, 25, 50, 75, 100)
CHANNELS = ("music", "dialogue", "effects")
NEW_PLAYER_LEVEL = 25  # every channel, until the player sets it in Options


class AudioSettings:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.values: dict[str, int] = {name: 100 for name in CHANNELS}

    def configure(self, save_dir: str | PathLike[str] | None) -> None:
        self.path = Path(save_dir) / "options.json" if save_dir is not None else None
        self.values = {name: 100 for name in CHANNELS}
        if self.path is None:
            return
        self.values = {name: NEW_PLAYER_LEVEL for name in CHANNELS}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for name in CHANNELS:
                value = raw.get(name)
                if type(value) is int and value in LEVELS:
                    self.values[name] = value
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def volume(self, name: str) -> float:
        return self.values[name] / 100.0

    def save(self, values: dict[str, int]) -> None:
        if set(values) != set(CHANNELS) or any(type(value) is not int or value not in LEVELS
                                                for value in values.values()):
            raise ValueError("invalid audio settings")
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(values, sort_keys=True) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        self.values = values.copy()


audio_settings = AudioSettings()
