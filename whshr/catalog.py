"""Metadata-only catalog for lazily resolving assets in an original installation."""

from dataclasses import dataclass, replace
import json
from pathlib import Path

from .assets import AssetId, AssetLocator, source_fingerprint
from .glue_fonts import GLUE_FONT_FILES

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
        record = self._by_identifier.get(asset_id)
        if record is not None:
            return record
        # Briefings are keyed by the live mission record, which is only known
        # after WND.DLL's flow has selected a mission. All use the same source
        # and decoder contract; retain that record as a dynamic template.
        if asset_id.kind == "briefing":
            template = self._by_identifier.get(AssetId(asset_id.namespace, "briefing", "_campaign"))
            if template is not None:
                return replace(template, identifier=asset_id)
        raise KeyError(asset_id)

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
        # The active mission supplies the record-specific key at runtime.
        # Keep one source template rather than inventing identities from the
        # non-unique battle-script filename.
        records.append(AssetRecord(
            AssetId("vanilla", "briefing", "_campaign"), "briefing", "file", "DLL/WND.DLL",
            "campaign-briefing", source_fingerprint(wnd_dll),
        ))

    antxt_dll = game.find("FILE", "DLL", "ANTXT.DLL")
    if antxt_dll is not None:
        records.append(AssetRecord(
            AssetId("vanilla", "text", "anim"), "text", "file", "DLL/ANTXT.DLL",
            "pe-string-table", source_fingerprint(antxt_dll),
        ))

    subtext_fon = game.find("FILE", "BINARY", "GLUE", "SUBTEXT.FON")
    if subtext_fon is not None:
        records.append(AssetRecord(
            AssetId("vanilla", "font", "subtext"), "font", "file", "BINARY/GLUE/SUBTEXT.FON",
            "warhammer-fon", source_fingerprint(subtext_fon),
        ))

    pcsubt_fon = game.find("FILE", "BINARY", "PCSUBT.FON")
    if pcsubt_fon is not None:
        records.append(AssetRecord(
            AssetId("vanilla", "font", "pcsubt"), "font", "file", "BINARY/PCSUBT.FON",
            "warhammer-fon", source_fingerprint(pcsubt_fon),
        ))

    pctexta_fon = game.find("FILE", "BINARY", "PCTEXTA.FON")
    if pctexta_fon is not None:
        records.append(AssetRecord(
            AssetId("vanilla", "font", "pctexta"), "font", "file", "BINARY/PCTEXTA.FON",
            "warhammer-fon", source_fingerprint(pctexta_fon),
        ))
    for slot, relative in GLUE_FONT_FILES.items():
        path = game.find("FILE", "BINARY", *relative.split("/"))
        if path is not None:
            records.append(AssetRecord(AssetId("vanilla", "font", f"glue{slot}"), "font", "file",
                                       f"BINARY/{relative}", "warhammer-fon", source_fingerprint(path)))

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
