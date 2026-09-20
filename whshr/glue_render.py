"""Headless presentation projection for typed glue windows.

The model intentionally contains names, indexed-resource references and native
coordinates only.  A pygame/OpenGL view may consume it, but importing this
module never creates a surface or opens an original-game file.
"""

from dataclasses import dataclass

from .glue import (AnimRecord, BitmapRecord, HotspotRecord, IncludeRecord, MidiRecord, MissionRecord,
                   MissionRef, MissionWindowRecord, PositionRecord, TextRecord)


@dataclass(frozen=True)
class RenderBitmap:
    name: str
    x: int = 0
    y: int = 0
    mask: str | None = None
    animation: tuple[tuple[str, int | str], ...] = ()
    # The addanimobject/addobject resource that owns this bitmap (None for the window's own
    # [BITMAP] records); distinguishes objects that reuse the same base sprite (e.g. several
    # trail markers on one cell base) so each keeps its own current animation frame.
    object_name: str | None = None


@dataclass(frozen=True)
class RenderText:
    string_id: int | None
    table: str | None
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    font: str | None = None
    format: str | None = None
    colour: str | None = None


@dataclass(frozen=True)
class RenderHotspot:
    x: int
    y: int
    width: int
    height: int
    hint_id: int | None
    target: str | None
    cursor: str | None
    up_bitmap: str | None
    down_bitmap: str | None


@dataclass(frozen=True)
class RenderAnimation:
    name: str | None
    x: int = 0
    y: int = 0
    index: int | None = None
    bkindex: int | None = None
    controlpanel: int | None = None


@dataclass(frozen=True)
class RenderMissionList:
    x: int
    y: int
    missions: tuple[MissionRef, ...]


@dataclass(frozen=True)
class GlueRenderModel:
    name: str
    x: int
    y: int
    width: int
    height: int
    palette_id: int
    bitmaps: tuple[RenderBitmap, ...]
    texts: tuple[RenderText, ...]
    hotspots: tuple[RenderHotspot, ...]
    animations: tuple[RenderAnimation, ...]
    music: tuple[str, ...]
    mission_lists: tuple[RenderMissionList, ...] = ()


def _integer(value, default=0):
    # A ``set:res=<id>`` argument may carry a whitespace-separated human-readable label after the id
    # (e.g. ``691\t\t"The Final Battle"``), kept in the source as a comment; only the id is data.
    token = value.split(None, 1)[0] if isinstance(value, str) else value
    try:
        return int(token)
    except (TypeError, ValueError):
        return default


def _fields(record):
    values = {}
    for field in record.fields:
        if field.command == "set" and "=" in field.argument:
            key, value = field.argument.split("=", 1)
            values[key.casefold()] = _integer(value, value)
        else:
            values[field.command] = field.argument
    return values


def _included_records(content, name, seen=()):
    key = str(name).upper()
    if key in seen:
        raise ValueError(f"cyclic glue include: {' -> '.join((*seen, key))}")
    definition = content.window(key)
    for record in definition.records:
        if isinstance(record, IncludeRecord):
            targets = (field.argument for field in record.fields if field.command == "script")
            for target in targets:
                yield from _included_records(content, target, (*seen, key))
        else:
            yield record


def build_render_model(content, window, positions=None):
    """Project one runtime ``WindowInstance`` into ordered, native UI primitives.

    ``positions`` overrides an object's (x, y) by ``(window.name, object_name)`` — used for
    ``gettentpos`` objects, whose position is resolved once when added, from campaign state that
    lives outside the window's own static ``[BITMAP]`` record (notes/campaign_tent.md §3).
    """
    positions = positions or {}
    records = [(None, record) for record in _included_records(content, window.name)]
    for object_name in window.objects:
        records.extend((object_name, record) for record in _included_records(content, object_name))
    position, bitmaps, texts, hotspots, animations, music, mission_lists, missions = {}, [], [], [], [], [], [], []
    for object_name, record in records:
        values = _fields(record)
        if isinstance(record, PositionRecord):
            position = values
        elif isinstance(record, BitmapRecord) and values.get("setbitmap"):
            animation = tuple((key, value) for key, value in values.items()
                              if key not in {"setbitmap", "setmask", "x", "y"})
            x, y = positions.get((window.name, object_name), (values.get("x"), values.get("y")))
            bitmaps.append(RenderBitmap(values["setbitmap"], _integer(x), _integer(y),
                                        values.get("setmask") or None, animation, object_name))
        elif isinstance(record, TextRecord):
            texts.append(RenderText(
                _integer(values.get("res"), None) if values.get("res") is not None else None,
                values.get("resfile") or None, _integer(values.get("x")), _integer(values.get("y")),
                _integer(values.get("vx")), _integer(values.get("vy")), values.get("font") or None,
                values.get("format") or None, values.get("settextcolor") or None,
            ))
        elif isinstance(record, HotspotRecord):
            hint = values.get("res") if "res" in values and "set:res" not in values else None
            # A set:res is the hint; a later res: is the launch target. Retain both.
            hint = next((_integer(field.argument.split("=", 1)[1], None) for field in record.fields
                         if field.command == "set" and field.argument.casefold().startswith("res=")), hint)
            target = next((field.argument for field in record.fields if field.command == "res"), None)
            up_bitmap = values.get("setupbitmap") or None
            down_bitmap = values.get("setdownbitmap") or None
            hotspots.append(RenderHotspot(_integer(values.get("x")), _integer(values.get("y")),
                                          _integer(values.get("vx")), _integer(values.get("vy")), hint,
                                          target, values.get("cursor") or None, up_bitmap, down_bitmap))
        elif isinstance(record, AnimRecord):
            animations.append(RenderAnimation(values.get("name") or None, _integer(values.get("x")),
                                              _integer(values.get("y")),
                                              _integer(values.get("index"), None) if "index" in values else None,
                                              _integer(values.get("bkindex"), None) if "bkindex" in values else None,
                                              _integer(values.get("controlpanel"), None) if "controlpanel" in values else None))
        elif isinstance(record, MissionWindowRecord):
            mission_lists.append(RenderMissionList(_integer(values.get("x")), _integer(values.get("y")), ()))
        elif isinstance(record, MissionRecord) and record.mission_ref is not None:
            missions.append(record.mission_ref)
        elif isinstance(record, MidiRecord) and values.get("name"):
            music.append(values["name"])
    return GlueRenderModel(window.name, _integer(position.get("x")), _integer(position.get("y")),
                           _integer(position.get("vx")), _integer(position.get("vy")), window.palette_id,
                           tuple(bitmaps), tuple(texts), tuple(hotspots), tuple(animations), tuple(music),
                           tuple(RenderMissionList(item.x, item.y, tuple(missions)) for item in mission_lists))
