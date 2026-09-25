"""Case-insensitive access to the Windows-era game installation layout."""

from pathlib import Path
from os import PathLike


class Installation:
    """A WARFB directory with UPDATE/BINARY taking precedence over FILE/BINARY."""

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

    def remote_dir(self, *parts: str) -> Path:
        return self.require("REMOTE", *parts)

    def binary_dirs(self) -> list[Path]:
        """Existing BINARY directories in load precedence order."""
        return [path for path in (self.find("UPDATE", "BINARY"), self.find("FILE", "BINARY")) if path]

    def binary_dir(self, *parts: str) -> Path:
        """Resolve a path below the preferred BINARY tree."""
        for binary in self.binary_dirs():
            path = binary
            for part in parts:
                path = self._child(path, part)
                if path is None:
                    break
            if path is not None:
                return path
        raise FileNotFoundError(f"BINARY/{'/'.join(parts)} not found under {self.root}")

    def binary_file(self, *parts: str) -> Path:
        return self.binary_dir(*parts)

