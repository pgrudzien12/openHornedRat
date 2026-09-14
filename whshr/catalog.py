"""Metadata-only catalog for lazily resolving assets in an original installation."""

from dataclasses import dataclass
import json
from pathlib import Path

from .assets import AssetId, AssetLocator, source_fingerprint

CATALOG_VERSION = 1


@dataclass(frozen=True)
class AssetRecord:
    """One logical asset mapped to an original relative path and a decoder contract."""

    identifier: AssetId
    kind: str
    scope: str
    path: str
    decoder: str
    fingerprint: dict


class AssetCatalog:
    """Deterministic logical-ID index; records refer to original files, never copied data."""

    def __init__(self, records):
        ordered = tuple(sorted(records, key=lambda record: str(record.identifier)))
        identifiers = [record.identifier for record in ordered]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("asset catalog has duplicate logical IDs")
        self.records = ordered
        self._by_identifier = {record.identifier: record for record in ordered}

    def get(self, identifier):
        asset_id = AssetId.parse(identifier) if isinstance(identifier, str) else identifier
        return self._by_identifier[asset_id]

    def resolve(self, installation, identifier):
        """Resolve an asset through the same original-install lookup policy as its decoder."""
        record = self.get(identifier)
        return AssetLocator(installation).resolve(record.scope, record.path)

    def to_dict(self):
        return {
            "version": CATALOG_VERSION,
            "assets": [{
                "identifier": str(record.identifier),
                "kind": record.kind,
                "scope": record.scope,
                "path": record.path,
                "decoder": record.decoder,
                "fingerprint": record.fingerprint,
            } for record in self.records],
        }

    @classmethod
    def from_dict(cls, data):
        if data.get("version") != CATALOG_VERSION:
            raise ValueError(f"unsupported catalog version: {data.get('version')!r}")
        return cls(AssetRecord(
            AssetId.parse(record["identifier"]), record["kind"], record["scope"], record["path"],
            record["decoder"], record["fingerprint"],
        ) for record in data["assets"])


def _files(directory, suffix):
    if directory is None:
        return ()
    return sorted(
        (path for path in directory.iterdir() if path.is_file() and path.suffix.casefold() == suffix),
        key=lambda path: path.name.casefold(),
    )


def build(installation):
    """Index currently supported lazy asset roots without decoding or exporting game data."""
    locator = AssetLocator(installation)
    game = locator.installation
    locator.validate()
    records = []

    for path in _files(game.find("FILE", "SCRIPT"), ".bts"):
        records.append(AssetRecord(
            AssetId("vanilla", "battle", path.stem.casefold()), "battle", "file",
            f"SCRIPT/{path.name}", "battle-script", source_fingerprint(path),
        ))
    for path in _files(game.find("REMOTE", "BINARY", "ANIM"), ".si"):
        stem = path.stem.casefold()
        fingerprint = source_fingerprint(path)
        records.append(AssetRecord(
            AssetId("vanilla", "cutscene", stem), "cutscene", "remote",
            f"BINARY/ANIM/{path.name}", "omni-si", fingerprint,
        ))
        # Same source file, rebuilt into playable Smacker/WAV media instead of the raw object tree.
        records.append(AssetRecord(
            AssetId("vanilla", "cutscene", f"{stem}-media"), "cutscene-media", "remote",
            f"BINARY/ANIM/{path.name}", "omni-si-media", fingerprint,
        ))

    wnd_dll = game.find("FILE", "DLL", "WND.DLL")
    if wnd_dll is not None:
        # Phase 1 only needs the first campaign battle's briefing; extend this per known mission.
        records.append(AssetRecord(
            AssetId("vanilla", "briefing", "bf001"), "briefing", "file", "DLL/WND.DLL",
            "campaign-briefing", source_fingerprint(wnd_dll),
        ))

    standard = game.find("UPDATE", "BINARY", "STANDARD.PAL") or game.find("FILE", "BINARY", "STANDARD.PAL")
    if standard is not None:
        records.append(AssetRecord(
            AssetId("vanilla", "palette", "standard"), "palette", "binary", "STANDARD.PAL",
            "rgb-palette", source_fingerprint(standard),
        ))
    return AssetCatalog(records)


def write(installation, output):
    """Build and write a reproducible metadata index; callers choose a local cache destination."""
    catalog = build(installation)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog.to_dict(), indent=2) + "\n", encoding="utf-8")
    return catalog


def read(path):
    """Load a previously generated metadata-only catalog."""
    return AssetCatalog.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
