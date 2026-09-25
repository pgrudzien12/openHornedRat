"""Typed logical asset IDs and safe resolution against an original installation."""

from dataclasses import dataclass
from os import PathLike
from pathlib import Path, PurePosixPath
import re

from .paths import Installation

_ID_PART = re.compile(r"^[a-z0-9_][a-z0-9_.-]*$")


@dataclass(frozen=True, order=True)
class AssetId:
    """A stable ``namespace:kind/name`` identifier independent of source filenames."""

    namespace: str
    kind: str
    name: str

    def __post_init__(self) -> None:
        if not all(_ID_PART.fullmatch(value) for value in (self.namespace, self.kind, self.name)):
            raise ValueError("asset ID parts must use lowercase letters, digits, '.', '_' or '-'")

    def __str__(self) -> str:
        return f"{self.namespace}:{self.kind}/{self.name}"

    @classmethod
    def parse(cls, value: str) -> "AssetId":
        try:
            namespace, rest = value.split(":", 1)
            kind, name = rest.split("/", 1)
        except ValueError:
            raise ValueError(f"invalid asset ID: {value!r}") from None
        return cls(namespace, kind, name)


class AssetLocator:
    """Resolves catalog paths using the original installation's Windows-compatible policy."""

    def __init__(self, installation: Installation | str | PathLike[str]) -> None:
        self.installation = installation if isinstance(installation, Installation) else Installation(installation)

    def validate(self) -> None:
        """Validate the roots required by the initial catalog without decoding game data."""
        required = (("FILE",), ("FILE", "SCRIPT"), ("FILE", "BINARY"), ("REMOTE", "BINARY", "ANIM"))
        missing = ["/".join(parts) for parts in required if self.installation.find(*parts) is None]
        if missing:
            raise FileNotFoundError(f"incomplete WARFB installation; missing: {', '.join(missing)}")

    def resolve(self, scope: str, path: str) -> Path:
        """Resolve a catalog-relative path and reject paths escaping their original scope."""
        parts = tuple(PurePosixPath(path).parts)
        if not parts or PurePosixPath(path).is_absolute() or any(part in ("..", ".") for part in parts):
            raise ValueError(f"asset path must be a non-empty relative path: {path!r}")
        if scope == "file":
            return self.installation.file_dir(*parts)
        if scope == "remote":
            return self.installation.remote_dir(*parts)
        if scope == "binary":
            return self.installation.binary_file(*parts)
        raise ValueError(f"unknown asset scope: {scope}")


def source_fingerprint(path: str | PathLike[str]) -> dict[str, int]:
    """Return the cheap source-version key used by metadata and decoded-asset caches."""
    stat = Path(path).stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
