"""Fingerprint-invalidated in-memory cache for decoded original assets."""

from .assets import AssetId, source_fingerprint


class AssetCache:
    """Caches values by typed ID while the catalog source fingerprint remains unchanged."""

    def __init__(self):
        self._entries = {}

    def get(self, locator, catalog, identifier, loader):
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

    def release(self, identifier):
        """Release one decoded asset. Missing assets are already absent."""
        key = AssetId.parse(identifier) if isinstance(identifier, str) else identifier
        self._entries.pop(key, None)

    def clear(self):
        """Release every cached decoded asset."""
        self._entries.clear()
