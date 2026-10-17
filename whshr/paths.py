"""Case-insensitive access to the Windows-era game installation layout."""

from pathlib import Path
from os import PathLike


# Folders the Steam "Classic" edition moved, relative to BINARY: original location -> where its files live there
# (notes/steam_edition.md §7: General MIDI tracks in MUSIC/MIDI/GEN, FM tracks in MUSIC/MIDI).
MOVED_BINARY_FOLDERS: dict[tuple[str, ...], tuple[tuple[str, ...], ...]] = {
    ("MUSIC",): (("MUSIC", "MIDI", "GEN"), ("MUSIC", "MIDI")),
}


class Installation:
    """A WARFB directory with UPDATE/BINARY taking precedence over FILE/BINARY.

    Two layouts are supported (notes/steam_edition.md): the GOG/CD one, with ``FILE/``, ``REMOTE/`` (films and
    speech) and ``UPDATE/`` (patched data), and the Steam "Classic" edition's, which merges all three into ``FILE/`` and
    keeps the MIDI music one folder deeper (:data:`MOVED_BINARY_FOLDERS`). Lookups below try the original location
    first, so a GOG installation resolves exactly as before.
    """

    def __init__(self, root: str | PathLike[str]) -> None:
        self.root = Path(root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"installation directory does not exist: {self.root}")

    @staticmethod
    def _child(directory: Path, name: str) -> Path | None:
        try:
            return next(entry for entry in directory.iterdir() if entry.name.casefold() == name.casefold())
        except StopIteration:
            return None

    def find(self, *parts: str) -> Path | None:
        """Return the actual path matching parts case-insensitively, or None."""
        current = self.root
        for part in parts:
            current = self._child(current, part)
            if current is None:
                return None
        return current

    def require(self, *parts: str) -> Path:
        """Return a case-insensitively resolved path or raise FileNotFoundError."""
        path = self.find(*parts)
        if path is None:
            raise FileNotFoundError(f"{'/'.join(parts)} not found under {self.root}")
        return path

    def file_dir(self, *parts: str) -> Path:
        return self.require("FILE", *parts)

    def remote_find(self, *parts: str) -> Path | None:
        """``REMOTE/<parts>``, or ``FILE/<parts>`` in a layout that merged REMOTE into FILE; None if neither exists."""
        return self.find("REMOTE", *parts) or self.find("FILE", *parts)

    def remote_dir(self, *parts: str) -> Path:
        path = self.remote_find(*parts)
        if path is None:
            raise FileNotFoundError(f"REMOTE/{'/'.join(parts)} not found under {self.root}")
        return path

    def music_dir(self) -> Path:
        """The folder holding the General MIDI music: BINARY/MUSIC, or BINARY/MUSIC/MIDI/GEN in the Steam edition."""
        for parts in (("MUSIC",), *MOVED_BINARY_FOLDERS[("MUSIC",)]):
            try:
                folder = self.binary_dir(*parts)
            except FileNotFoundError:
                continue
            if any(child.suffix.casefold() == ".mid" for child in folder.iterdir()):
                return folder
        return self.binary_dir("MUSIC")

    def binary_dirs(self) -> list[Path]:
        """Existing BINARY directories in load precedence order."""
        return [path for path in (self.find("UPDATE", "BINARY"), self.find("FILE", "BINARY")) if path]

    def binary_dir(self, *parts: str) -> Path:
        """Resolve a path below the preferred BINARY tree (then where a known layout moved it)."""
        candidates = [parts]
        for original, alternatives in MOVED_BINARY_FOLDERS.items():
            if parts[:len(original)] == original and len(parts) > len(original):
                candidates.extend(moved + parts[len(original):] for moved in alternatives)
        for candidate in candidates:
            for binary in self.binary_dirs():
                path: Path | None = binary
                for part in candidate:
                    assert path is not None
                    path = self._child(path, part)
                    if path is None:
                        break
                if path is not None:
                    return path
        raise FileNotFoundError(f"BINARY/{'/'.join(parts)} not found under {self.root}")

    def binary_file(self, *parts: str) -> Path:
        return self.binary_dir(*parts)

