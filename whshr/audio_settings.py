"""Engine-owned audio levels shared by the Options window and playback views."""

import json
from os import PathLike
from pathlib import Path

LEVELS = (0, 25, 50, 75, 100)
CHANNELS = ("music", "dialogue", "effects")


class AudioSettings:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.values: dict[str, int] = {name: 100 for name in CHANNELS}

    def configure(self, save_dir: str | PathLike[str] | None) -> None:
        self.path = Path(save_dir) / "options.json" if save_dir is not None else None
        self.values = {name: 100 for name in CHANNELS}
        if self.path is None:
            return
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
