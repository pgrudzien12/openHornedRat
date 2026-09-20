"""Fingerprint-invalidated in-memory cache for decoded original assets."""

from .assets import AssetId, source_fingerprint


class AssetCache:
    """Caches values by typed ID while the catalog source fingerprint remains unchanged."""

    def __init__(self):
        self._entries = {}
        self._owners = {}

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

    def acquire(self, locator, catalog, identifier, loader, owner):
        """Load a dynamic asset and retain it until ``owner`` is released."""
        value = self.get(locator, catalog, identifier, loader)
        key = AssetId.parse(identifier) if isinstance(identifier, str) else identifier
        self._owners.setdefault(owner, set()).add(key)
        return value

    def release_owner(self, owner):
        """Release assets used only by one finished scene/window/context owner."""
        candidates = self._owners.pop(owner, set())
        retained = set().union(*self._owners.values()) if self._owners else set()
        for key in candidates - retained:
            self._entries.pop(key, None)

    def release(self, identifier):
        """Release one decoded asset. Missing assets are already absent."""
        key = AssetId.parse(identifier) if isinstance(identifier, str) else identifier
        self._entries.pop(key, None)
        for identifiers in self._owners.values():
            identifiers.discard(key)

    def clear(self):
        """Release every cached decoded asset."""
        self._entries.clear()
        self._owners.clear()
