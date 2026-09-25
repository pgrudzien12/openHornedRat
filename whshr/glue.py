"""Lossless, typed import of the campaign glue resources in ``WND.DLL``.

The importer is deliberately stdlib-only.  It retains the source statement
stream for diagnostics while also exposing typed window records and executable
program instructions.  Higher-level campaign reports and the runtime are
projections over these models; they must not parse the source text again.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, order=True)
class SourceLocation:
    resource: str
    line: int


@dataclass(frozen=True)
class GlueInstruction:
    command: str
    argument: str
    location: SourceLocation


@dataclass(frozen=True)
class UnknownField:
    command: str
    argument: str
    location: SourceLocation


@dataclass(frozen=True, order=True)
class MissionRef:
    """Stable identity of a mission record; battle names are not unique."""

    window: str
    record_index: int

    def __post_init__(self):
        object.__setattr__(self, "window", self.window.upper())

    @property
    def key(self):
        return f"{self.window.casefold()}.{self.record_index}"


def _value(instruction):
    if instruction.command == "set" and "=" in instruction.argument:
        key, value = instruction.argument.split("=", 1)
        try:
            return key.casefold(), int(value)
        except ValueError:
            return key.casefold(), value
    return instruction.command, instruction.argument


_ACCEPTED: dict[str, tuple[set[str], set[str]]] = {
    "POSITION": ({"x", "y", "vx", "vy", "palindex", "book"}, set()),
    "BITMAP": ({"x", "y", "timecnt", "looptimecnt", "animstartframe",
                "animrestartframe", "animstopframe", "bkindex", "depend"},
               {"setbitmap", "setmask", "gettentpos"}),
    "ANIM": ({"x", "y", "sequence", "frame", "index", "controlpanel", "bkindex"},
             {"name", "settextcolor"}),
    "TEXT": ({"x", "y", "vx", "vy", "res", "resfile", "format", "font"},
             {"settextcolor", "linked"}),
    "HOTSPOT": ({"x", "y", "vx", "vy", "res", "count", "clickres", "clickrescnt",
                 "textx", "texty", "linkid", "upsfx", "downsfx"},
                {"cursor", "altcursor", "script", "res", "setmask", "setupbitmap",
                 "setdownbitmap", "settextcolor"}),
    "MISSIONWINDOW": ({"x", "y"}, set()),
    "MISSION": ({"res", "releaseflag", "depend", "inactivedepend", "tentpos"},
                {"script", "res", "setbattlescript", "setmissionscript", "replacescript",
                 "cash", "debrief", "forceunits", "excludeunits"}),
    "MIDI": ({"volume"}, {"name"}),
    "INCLUDE": (set(), {"script"}),
    "DEMODEFAULT": ({"flag"}, {"script", "res"}),
    "LOADANDSAVEGAME": ({"x", "y", "flag"}, set()),
    "SUBWINDOW": ({"x", "y"}, {"script", "res"}),
}


@dataclass(frozen=True)
class WindowRecord:
    block_type: str
    fields: tuple[GlueInstruction, ...]
    location: SourceLocation
    mission_ref: MissionRef | None = None

    @property
    def values(self):
        """Convenience last-value projection; ``fields`` remains lossless."""
        return dict(_value(item) for item in self.fields)

    @property
    def unknown_fields(self):
        set_keys, commands = _ACCEPTED.get(self.block_type, (set(), set()))
        result = []
        for item in self.fields:
            key, _ = _value(item)
            accepted = key in set_keys if item.command == "set" else item.command in commands
            if not accepted:
                result.append(UnknownField(item.command, item.argument, item.location))
        return tuple(result)


@dataclass(frozen=True)
class PositionRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class BitmapRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class MissionRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class MissionWindowRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class SubwindowRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class AnimRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class TextRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class HotspotRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class DemoDefaultRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class LoadAndSaveGameRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class IncludeRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class MidiRecord(WindowRecord):
    pass


@dataclass(frozen=True)
class UnknownRecord(WindowRecord):
    pass


_RECORD_TYPES = {
    "POSITION": PositionRecord,
    "BITMAP": BitmapRecord,
    "MISSION": MissionRecord,
    "MISSIONWINDOW": MissionWindowRecord,
    "SUBWINDOW": SubwindowRecord,
    "ANIM": AnimRecord,
    "TEXT": TextRecord,
    "HOTSPOT": HotspotRecord,
    "DEMODEFAULT": DemoDefaultRecord,
    "LOADANDSAVEGAME": LoadAndSaveGameRecord,
    "INCLUDE": IncludeRecord,
    "MIDI": MidiRecord,
}


@dataclass(frozen=True)
class GlueProgram:
    name: str
    block_type: str
    instructions: tuple[GlueInstruction, ...]
    statements: tuple[GlueInstruction, ...] = field(repr=False)


@dataclass(frozen=True)
class WindowDefinition:
    name: str
    records: tuple[WindowRecord, ...]
    statements: tuple[GlueInstruction, ...] = field(repr=False)
    block_type: str = field(default="WINDOW", init=False)


GlueResource = GlueProgram | WindowDefinition


def _strip_comment(raw):
    cut = len(raw)
    for marker in ("//", ";"):
        found = raw.find(marker)
        if found >= 0:
            cut = min(cut, found)
    return raw[:cut].strip()


def tokenize_glue(resource_name, text):
    """Return every meaningful statement with its original line location."""
    name = str(resource_name).upper()
    statements = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw)
        if not line or line[0] in "\x1a\x1b":
            continue
        if line.startswith("[") and "]" in line:
            command, argument = line[:line.index("]") + 1].upper(), ""
        else:
            command, separator, argument = line.partition(":")
            command = command.strip().casefold()
            argument = argument.strip() if separator else ""
        statements.append(GlueInstruction(command, argument, SourceLocation(name, number)))
    return tuple(statements)


def parse_glue_resource(name, text):
    """Import one resource as a typed program or window definition."""
    name = str(name).upper()
    statements = tokenize_glue(name, text)
    first = next((item for item in statements if item.command.startswith("[")), None)
    block_type = first.command[1:-1] if first else "UNKNOWN"
    # Small synthetic fixtures and diagnostic snippets sometimes contain one
    # record without its [WINDOW] wrapper.  Keep accepting that historical
    # parser input while representing it through the same typed record model.
    if block_type in _RECORD_TYPES:
        record_type = _RECORD_TYPES[block_type]
        fields = tuple(item for item in statements if not item.command.startswith("["))
        mission_ref = MissionRef(name, 0) if block_type == "MISSION" else None
        return WindowDefinition(name, (record_type(block_type, fields, first.location, mission_ref),), statements)
    if block_type != "WINDOW":
        instructions = tuple(item for item in statements if not item.command.startswith("["))
        return GlueProgram(name, block_type, instructions, statements)

    records = []
    current_type = None
    current_location = None
    fields = []
    mission_index = 0
    for item in statements[1:]:
        if item.command.startswith("["):
            marker = item.command[1:-1]
            if marker == "END":
                if current_type is not None:
                    record_type = _RECORD_TYPES.get(current_type, UnknownRecord)
                    mission_ref = None
                    if current_type == "MISSION":
                        mission_ref = MissionRef(name, mission_index)
                        mission_index += 1
                    records.append(record_type(current_type, tuple(fields), current_location, mission_ref))
                    current_type, current_location, fields = None, None, []
                continue
            # Retain malformed nesting as separate records rather than losing it.
            if current_type is not None:
                record_type = _RECORD_TYPES.get(current_type, UnknownRecord)
                records.append(record_type(current_type, tuple(fields), current_location))
            current_type, current_location, fields = marker, item.location, []
        elif current_type is not None:
            fields.append(item)
    if current_type is not None:
        record_type = _RECORD_TYPES.get(current_type, UnknownRecord)
        records.append(record_type(current_type, tuple(fields), current_location))
    return WindowDefinition(name, tuple(records), statements)


def parse_glue_resources(texts: Mapping[str, str]):
    """Import a resource mapping exactly once in deterministic name order."""
    return {str(name).upper(): parse_glue_resource(name, text)
            for name, text in sorted(texts.items(), key=lambda pair: str(pair[0]).upper())}


_EXTERNAL_COMMANDS = {
    "playgame", "playgamewithdebrief", "encounterplaygame", "encounterplaygamewithdebrief",
    "playmovie", "iftrueplaymovie", "iffalseplaymovie", "opentroopselection", "openbook",
    "openloadgame", "opensavegame", "openoptions", "endgame", "autosave", "gomissionselect",
    "loadanimstringintocache",
}
_NOOP_COMMANDS = {"comment", "setdemodefault"}
_IMPLEMENTED_COMMANDS = {
    "addanimobject", "addmidiobject", "addobject", "addtroop", "addunit", "applyseq", "bonusadd",
    "bonusinit", "cash", "closewindow", "clrgluestatus", "debrief", "debriefwithsummary",
    "enablebook", "gocaravan", "gosub", "goto", "iffalsebonusadd", "iffalsegocaravan", "iffalsegosub",
    "iftrueaddcash",
    "iftruegocaravan", "iftruegosub", "openwindow", "opensubwindow", "playmidi", "playtext",
    "queuetoplaytext", "removeobject", "return", "set", "setbattlescript", "setcurwindow",
    "setdebrief", "setgluestatus", "setgluestatusmask", "settextalign", "settextcolor", "stopmidi",
    "tagasmission", "testforunitinarmy", "testforunitinmarch", "testmission",
    "testobjective", "unitjoinmission", "unitleavemission", "updatewindow", "waitforrelease",
    "waitforresume",
}


def diagnostic_text(resource):
    """Render a normalized, order-preserving diagnostic form of one resource."""
    lines = []
    depth = 0
    for item in resource.statements:
        if item.command == "[END]":
            depth = max(0, depth - 1)
        prefix = "  " * depth
        lines.append(prefix + item.command + (f":{item.argument}" if item.argument else ""))
        if item.command.startswith("[") and item.command != "[END]":
            depth += 1
    return "\n".join(lines)


def _status(command):
    if command in _EXTERNAL_COMMANDS:
        return "known_external"
    if command in _NOOP_COMMANDS:
        return "recognized_noop"
    if command in _IMPLEMENTED_COMMANDS:
        return "implemented"
    return "unknown"


def validate_program(program):
    """Reject an executable program containing an unclassified reachable command."""
    if not isinstance(program, GlueProgram):
        raise TypeError("only GlueProgram resources are executable")
    for instruction in program.instructions:
        if instruction.command == "set" and "=" in instruction.argument:
            key = instruction.argument.split("=", 1)[0].casefold()
            known = key in {"animseq", "tentpos", "textlines"}
        else:
            known = _status(instruction.command) != "unknown"
        if not known:
            location = instruction.location
            raise ValueError(
                f"{location.resource}:{location.line}: unsupported glue command "
                f"{instruction.command!r} ({instruction.argument!r})"
            )
    return program


def coverage_report(resources: Mapping[str, GlueResource]):
    """Return deterministic block, command and field coverage for an inventory."""
    blocks = Counter()
    commands = defaultdict(Counter)
    fields = defaultdict(Counter)
    for resource in resources.values():
        blocks[resource.block_type] += 1
        if isinstance(resource, WindowDefinition):
            for record in resource.records:
                blocks[record.block_type] += 1
                for item in record.fields:
                    if item.command == "set" and "=" in item.argument:
                        fields[record.block_type][item.argument.split("=", 1)[0].casefold()] += 1
                    else:
                        commands[record.block_type][item.command] += 1
        else:
            for item in resource.instructions:
                if item.command == "set" and "=" in item.argument:
                    fields[resource.block_type][item.argument.split("=", 1)[0].casefold()] += 1
                else:
                    commands[resource.block_type][item.command] += 1

    def entries(counter, block=None, are_fields=False):
        result = {}
        for key, count in sorted(counter.items()):
            if are_fields:
                accepted = (key in {"animseq", "tentpos", "textlines"} if block in {"RUN", "START"}
                            else key in _ACCEPTED.get(block or "", (set(), set()))[0])
                status = "implemented" if accepted else "unknown"
            elif block in _ACCEPTED:
                if block == "INCLUDE" and key == "addobject":
                    status = "recognized_noop"
                else:
                    status = "implemented" if key in _ACCEPTED[block][1] else "unknown"
            else:
                status = _status(key)
            result[key] = {"count": count, "status": status}
        return result

    return {
        "resources": len(resources),
        "blocks": dict(sorted(blocks.items())),
        "commands": {block: entries(counter, block) for block, counter in sorted(commands.items())},
        "fields": {block: entries(counter, block, True) for block, counter in sorted(fields.items())},
    }
