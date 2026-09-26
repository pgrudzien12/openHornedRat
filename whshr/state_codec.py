# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""JSON encoding of the glue interpreter's runtime state, for the engine's save games.

A save holds the interpreter's own state (script frames, windows, stacks, animation counters) so a load can
continue a mission script where it stopped (``notes/save_resume.md``). The encoding is plain JSON with tagged
containers and a fixed registry of classes that may appear -- loading never constructs anything else, so a
damaged or hostile save file cannot run code (unlike a pickle).

Tags: ``{"$tuple": [...]}``, ``{"$set": [...]}``, ``{"$dict": [[key, value], ...]}`` (keys of any encodable type),
``{"$type": "Name", "fields": {...}}`` for a registered class. Plain ``list``/``str``/``int``/``float``/``bool``/``None``
stay themselves.
"""

import dataclasses
from typing import Any


class CodecError(Exception):
    """The data cannot be encoded, or names a class outside the registry."""


class Codec:
    def __init__(self, classes: list[type], skip: dict[type, frozenset[str]] | None = None) -> None:
        self.registry = {cls.__name__: cls for cls in classes}
        self.skip = skip or {}  # per class: fields that are not saved (the loader leaves the class default)

    def encode(self, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, list):
            return [self.encode(item) for item in value]
        if isinstance(value, tuple):
            return {"$tuple": [self.encode(item) for item in value]}
        if isinstance(value, (set, frozenset)):
            return {"$set": sorted((self.encode(item) for item in value), key=repr)}
        if isinstance(value, dict):
            return {"$dict": [[self.encode(key), self.encode(item)] for key, item in value.items()]}
        cls = type(value)
        if self.registry.get(cls.__name__) is not cls:
            raise CodecError(f"cannot save a {cls.__name__}")
        skipped = self.skip.get(cls, frozenset())
        names = ([field.name for field in dataclasses.fields(value)] if dataclasses.is_dataclass(value)
                 else list(vars(value)))
        return {"$type": cls.__name__,
                "fields": {name: self.encode(getattr(value, name)) for name in names if name not in skipped}}

    def decode(self, data: Any) -> Any:
        if data is None or isinstance(data, (bool, int, float, str)):
            return data
        if isinstance(data, list):
            return [self.decode(item) for item in data]
        if not isinstance(data, dict):
            raise CodecError(f"unexpected {type(data).__name__} in a save")
        if "$tuple" in data:
            return tuple(self.decode(item) for item in data["$tuple"])
        if "$set" in data:
            return {self.decode(item) for item in data["$set"]}
        if "$dict" in data:
            return {self.decode(key): self.decode(item) for key, item in data["$dict"]}
        if "$type" in data:
            cls = self.registry.get(data["$type"])
            if cls is None:
                raise CodecError(f"unknown class {data['$type']!r} in a save")
            instance = object.__new__(cls)
            if dataclasses.is_dataclass(cls):  # start from the class defaults for anything not saved
                for field in dataclasses.fields(cls):
                    if field.default is not dataclasses.MISSING:
                        object.__setattr__(instance, field.name, field.default)
                    elif field.default_factory is not dataclasses.MISSING:
                        object.__setattr__(instance, field.name, field.default_factory())
            for name, item in data["fields"].items():
                object.__setattr__(instance, name, self.decode(item))
            return instance
        raise CodecError("untagged mapping in a save")
