"""Fingerprint-invalidated in-memory cache for decoded original assets."""

from collections.abc import Callable, Hashable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .assets import AssetId, AssetLocator, source_fingerprint

if TYPE_CHECKING:
    from .catalog import AssetCatalog, AssetRecord

Loader = Callable[["AssetRecord", Path], Any]  # (catalog record, resolved source path) -> decoded asset
Owner = Hashable  # any hashable scene/window/context token


class AssetCache:
    """Caches values by typed ID while the catalog source fingerprint remains unchanged."""

    def __init__(self) -> None:
        self._entries: dict[AssetId, tuple[dict[str, int], Any]] = {}
        self._owners: dict[Owner, set[AssetId]] = {}

    def get(self, locator: AssetLocator, catalog: "AssetCatalog", identifier: AssetId | str, loader: Loader) -> Any:
        """Return a cached asset or call ``loader(record, resolved_path)`` to produce it."""
        record = catalog.get(identifier)
        key = record.identifier
        path = catalog.resolve(locator.installation, key)
        version = source_fingerprint(path)
        cached = self._entries.get(key)
        if cached is not None and cached[0] == version:
            return cached[1]
        value = loader(record, path)
        self._entries[key] = (version, value)
        return value

    def acquire(self, locator: AssetLocator, catalog: "AssetCatalog", identifier: AssetId | str, loader: Loader,
                owner: Owner) -> Any:
        """Load a dynamic asset and retain it until ``owner`` is released."""
        value = self.get(locator, catalog, identifier, loader)
        key = AssetId.parse(identifier) if isinstance(identifier, str) else identifier
        self._owners.setdefault(owner, set()).add(key)
        return value

    def release_owner(self, owner: Owner) -> None:
        """Release assets used only by one finished scene/window/context owner."""
        candidates = self._owners.pop(owner, set())
        retained: set[AssetId] = set()
        for owned in self._owners.values():
            retained |= owned
        for key in candidates - retained:
            self._entries.pop(key, None)

    def release(self, identifier: AssetId | str) -> None:
        """Release one decoded asset. Missing assets are already absent."""
        key = AssetId.parse(identifier) if isinstance(identifier, str) else identifier
        self._entries.pop(key, None)
        for identifiers in self._owners.values():
            identifiers.discard(key)

    def clear(self) -> None:
        """Release every cached decoded asset."""
        self._entries.clear()
        self._owners.clear()
