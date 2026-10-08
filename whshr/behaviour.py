"""Unit behaviour bytecode of the mission DLLs (FILE/SCRIPT/BFxxx.DLL): loader, disassembler and checks.

Every live unit runs a behaviour script each tick (game_rules.md, "Unit behaviour scripts and events"). The scripts
are data inside the mission DLLs: DLLGetScriptPointer(id) returns a pointer to an array of 32-bit words,
ids 0..N-1 are the mission's own unit scripts and ids 100..170 a shared library (identical in all DLLs).

Encoding (from the interpreter):
- the low 16 bits of a word are compared as a signed short; bit 15 set -> opcode ``word & 0x7FFF``
  (0-231) dispatched through the handler table at VA 0x100F53A0 in GAMEF.DLL, the handler returns the
  next PC;
- 0x0ABC is a label (PC + 1); 0x80E8 ends a script (232 is past the table, the word is only a sentinel
  for the forward scans of If/Else/CaseEvent/Break);
- ``Break`` carries the operand 0x1ABC and jumps to the next 0x0ABC label; ``CaseEvent N`` skips to the
  word after the next ``Break`` when the current event code is not N.

Instruction lengths: most handlers end in ``mov ax, [pc]; add ax, n; ret``. The lengths of the 232
opcodes are shipped below as a small structural table; they were derived from the handler code and
``check()`` re-derives them from the GAMEF.DLL bytes of the local installation (see HANDLER_LENGTHS_NOTE).
No game data is stored in this module; the scripts are read from the installation at run time.
"""

import json
import struct
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from os import PathLike
from typing import Any, NamedTuple, cast
from pathlib import Path

from . import script
from .paths import Installation
from .rules import PeImage

VA_HANDLERS = 0x100F53A0      # GAMEF.DLL: 232 handler pointers
VA_PC = 0x1006D104            # GAMEF.DLL: current PC (word index, 16 bit)
OPCODE_COUNT = 232
OPCODE_FLAG = 0x8000
LABEL = 0x0ABC
BREAK_LABEL = 0x1ABC          # operand of Break: the label it jumps to, with bit 12 set
END = 0x80E8
INST_COUNT = 33000            # DLLReturnInstCount() = END, a format check
LIBRARY_IDS = range(100, 171)
PLAYER_SCRIPT = 100           # set:script=PLAYER_SCRIPT in the .BTS files

# Instruction length in words (opcode word + operands) of opcodes 0x00..0xE7, one digit each.
_LENGTHS = (
    '21111111112122222211112112211112'   # 0x00-0x1F
    '21222222222222222323222221112111'   # 0x20-0x3F
    '11122111222111111111111111111222'   # 0x40-0x5F
    '21222231112211112222111111212121'   # 0x60-0x7F
    '21211112122112432211222111221212'   # 0x80-0x9F
    '22112121231222211111222233112211'   # 0xA0-0xBF
    '32234121122432112135222121122222'   # 0xC0-0xDF
    '21111121'                           # 0xE0-0xE7
)
LENGTHS = tuple(int(c) for c in _LENGTHS)
HANDLER_LENGTHS_NOTE = {
    # Handlers whose length cannot be read from a "return PC + n" in their own code.
    0x03: 'Restart: continues at the restart point saved by InitUnit/0x05',
    0x07: 'Loop: jumps to the address pushed by PushPC',
    0x0C: 'GotoScript N: restarts at PC 0 of script N',
    0x13: 'ReturnGosub: pops script and PC',
    0x14: 'ReturnInterrupt: pops the PC or starts the pending script',
    0x1E: 'tail call of Restart',
    0x1F: 'increments the PC in place, then returns PC + 1',
    0x87: 'increments the PC in place, then returns PC + 1',
    0x6B: 'Break: scans forward to its label',
    0x6C: 'If: PC + 1 when true, otherwise a nesting-aware scan',
    0x6D: 'IfNot: PC + 1 when false, otherwise a nesting-aware scan',
    0x6E: 'Else: nesting-aware scan to the matching EndIf',
}
# Opcodes after which execution never falls through to the next word.
UNCONDITIONAL = {0x03, 0x07, 0x0C, 0x13, 0x14, 0x1E}

# Opcode names from the batch 3 catalogues (agents G, opcodes 0-115, and H, 116-231; semantics in their
# reports). Unknown opcodes would print as Op<hex>. More or newer names can be merged with load_names().
OPCODE_NAMES = {
    0x00: 'InitUnit', 0x01: 'WaitForBattleStart', 0x02: 'ResetStack', 0x03: 'Restart', 0x04: 'RestartIfFalse',
    0x05: 'SetRestartPoint', 0x06: 'PushPC', 0x07: 'Loop', 0x08: 'LoopIfTrue', 0x09: 'LoopIfFalse',
    0x0A: 'RepeatStart', 0x0B: 'RepeatNext', 0x0C: 'GotoScript', 0x0D: 'SwitchScript', 0x0E: 'IfSwitchScript',
    0x0F: 'IfSwitchScriptHigh', 0x10: 'IfNotSwitchScript', 0x11: 'GosubScript', 0x12: 'CallInterruptScript',
    0x13: 'ReturnGosub', 0x14: 'ReturnInterrupt', 0x15: 'ReturnGosubIfFalse', 0x16: 'Query', 0x17: 'Yield',
    0x18: 'YieldIfTrue', 0x19: 'SkipIfTrue', 0x1A: 'SetWait', 0x1B: 'TestWait', 0x1C: 'Wait',
    0x1D: 'ExecuteOrder', 0x1E: 'RestartAfterOrder', 0x1F: 'MoveToNode', 0x20: 'FaceNode',
    0x21: 'HaltAndReform', 0x22: 'WaitWhileUnitFlags', 0x23: 'WaitUntilUnitFlags', 0x24: 'TestUnitFlags',
    0x25: 'SetUnitFlags', 0x26: 'ClearUnitFlags', 0x27: 'WaitWhileUnitFlags2', 0x28: 'WaitUntilUnitFlags2',
    0x29: 'TestUnitFlags2', 0x2A: 'SetUnitFlags2', 0x2B: 'ClearUnitFlags2', 0x2C: 'WaitWhileMoveState',
    0x2D: 'WaitUntilMoveState', 0x2E: 'SetCondFlags', 0x2F: 'ClearCondFlags', 0x30: 'TestCondFlags',
    0x31: 'SetThreatRange', 0x32: 'SetInterruptScript', 0x33: 'SetBehaviour', 0x34: 'SetTag',
    0x35: 'SetParentByTag', 0x36: 'IfTagExists', 0x37: 'AttackTagged', 0x38: 'SetTargetByTag',
    0x39: 'ReactToThreat', 0x3A: 'TakeEventTarget', 0x3B: 'DropTarget', 0x3C: 'ReacquireEventSource',
    0x3D: 'MoveToTarget', 0x3E: 'RefreshRouteToTarget', 0x3F: 'IfThreatOutweighsWorth',
    0x40: 'ReactEnemySpotted', 0x41: 'Nop', 0x42: 'FearWhenCharged', 0x43: 'IfGotoScript',
    0x44: 'IfNotGotoScript', 0x45: 'ReformBlock', 0x46: 'ReformToScriptRanks', 0x47: 'ResetModelAnimations',
    0x48: 'ScatterModelsToNode', 0x49: 'TeleportToNode', 0x4A: 'PlaceAtNode', 0x4B: 'TurnToFaceTarget',
    0x4C: 'QuarterTurnToTarget', 0x4D: 'IfTargetInChargeReach', 0x4E: 'ChargeTarget', 0x4F: 'ChargeForward',
    0x50: 'FleeFromTarget', 0x51: 'FleeAhead', 0x52: 'FleeBackward', 0x53: 'EnemyRouted',
    0x54: 'EnemyRoutedStatic', 0x55: 'SwitchOpponentInGrid', 0x56: 'TargetGone', 0x57: 'LeaveSharedGrid',
    0x58: 'StartPursuit', 0x59: 'LeaveGrid', 0x5A: 'Rally', 0x5B: 'FlankRearTest', 0x5C: 'AboutFace',
    0x5D: 'QuarterTurn', 0x5E: 'SendEventSelf', 0x5F: 'SendEventSelfIfTrue', 0x60: 'SendEventSelfIfFalse',
    0x61: 'StoreEventInfo', 0x62: 'SendEventToOwnSide', 0x63: 'SendEventToEnemySide',
    0x64: 'SendEventToOwnSideIfTrue', 0x65: 'SendEventToParent', 0x66: 'SendEventToUnitId',
    0x67: 'SnapModelsToFormation', 0x68: 'GetEvent', 0x69: 'ConsumeEvent', 0x6A: 'CaseEvent', 0x6B: 'Break',
    0x6C: 'If', 0x6D: 'IfNot', 0x6E: 'Else', 0x6F: 'EndIf', 0x70: 'ReadyToFire', 0x71: 'InArcAndRange',
    0x72: 'InRange', 0x73: 'InArc', 0x74: 'TargetValid', 0x75: 'FindThreatNear', 0x76: 'KeepThreat',
    0x77: 'FindNewThreatNear', 0x78: 'BrokenTargetInRange', 0x79: 'IsSpecialShooter', 0x7A: 'IfArtilleryManned',
    0x7B: 'FindTarget', 0x7C: 'FindTargetOfClass', 0x7D: 'FindTargetAnyRange',
    0x7E: 'FindTargetOfClassAnyRange', 0x7F: 'FindFriendTarget', 0x80: 'FindFriendTargetOfClass',
    0x81: 'FindFriendTargetAnyRange', 0x82: 'FindFriendTargetOfClassAnyRange', 0x83: 'FindNewTarget',
    0x84: 'FireAtTarget', 0x85: 'FireAt90PercentRange', 0x86: 'StampReload', 0x87: 'FireAtNode',
    0x88: 'TakeRangedEventTarget', 0x89: 'Nop1', 0x8A: 'TurningToCastMessage', 0x8B: 'KillAllModels',
    0x8C: 'RemoveFromBattle', 0x8D: 'SetActionState', 0x8E: 'PlayUnitAnimation', 0x8F: 'PlayLeaderAnimation',
    0x90: 'IfAnimationDone', 0x91: 'AttackUnitAtNode', 0x92: 'AttackNearestFlag40Unit', 0x93: 'CastPending',
    0x94: 'PendingInRangeArc', 0x95: 'PendingInRange', 0x96: 'TargetInCastArc',
    0x97: 'PendingReachesBrokenTarget', 0x98: 'ChooseEnemyAndSpell', 0x99: 'ChooseSpellForTarget',
    0x9A: 'IfEnemyPower', 0x9B: 'IfPlayerPower', 0x9C: 'ChooseEnemyAndSpellPay',
    0x9D: 'ChooseEnemyOfClassAndSpellPay', 0x9E: 'ChooseAllyAndSpellPay', 0x9F: 'ChooseAllyOfClassAndSpellPay',
    0xA0: 'SetSpellIfAffordable', 0xA1: 'SetCastPointNode', 0xA2: 'ChooseSpellForTargetPay',
    0xA3: 'TargetNearestEnemy', 0xA4: 'TargetNearestEnemyOfClass', 0xA5: 'TargetNearestAlly',
    0xA6: 'TargetNearestAllyOfClass', 0xA7: 'RetargetNearestEnemy', 0xA8: 'IfCastingAnimation',
    0xA9: 'IfCasting', 0xAA: 'DropPendingSpell', 0xAB: 'AddPlayerPower', 0xAC: 'AddEnemyPower',
    0xAD: 'SubPlayerPower', 0xAE: 'SubEnemyPower', 0xAF: 'TakeSpellEventTarget', 0xB0: 'AttackNearestEnemy',
    0xB1: 'AttackNearestVisibleEnemy', 0xB2: 'AttackNearestEnemyByAxis',
    0xB3: 'AttackNearestVisibleEnemyByAxis', 0xB4: 'AttackNearestEnemyOfClass',
    0xB5: 'AttackNearestEnemyOfClassB', 0xB6: 'AttackNthNearestEnemy', 0xB7: 'AttackNthNearestVisibleEnemy',
    0xB8: 'AttackNthNearestEnemyOfClass', 0xB9: 'AttackNthNearestEnemyOfClassB', 0xBA: 'AttackNearestAlly',
    0xBB: 'AttackNearestVisibleAlly', 0xBC: 'AttackNthNearestAlly', 0xBD: 'AttackNthNearestVisibleAlly',
    0xBE: 'AttackNearestMainEnemy', 0xBF: 'AttackNearestVisibleMainEnemy', 0xC0: 'PlaySoundAtUnit',
    0xC1: 'ShowMessage', 0xC2: 'React', 0xC3: 'PlaySound', 0xC4: 'StartUnitLoopSound',
    0xC5: 'StopUnitLoopSound', 0xC6: 'MoveUnitSound', 0xC7: 'CheckCollisions', 0xC8: 'RoutAllowed',
    0xC9: 'IfInNodeArea', 0xCA: 'IfAnyUnitInNodeArea', 0xCB: 'IfSideUnitInNodeArea', 0xCC: 'SendEventToTag',
    0xCD: 'IfClass', 0xCE: 'RunAway', 0xCF: 'IfMachineDestroyed', 0xD0: 'SetClass', 0xD1: 'IfTargetNotBroken',
    0xD2: 'IfTaggedUnitFlags', 0xD3: 'SpawnUnit', 0xD4: 'FollowParent', 0xD5: 'IfTag', 0xD6: 'IfEventSource',
    0xD7: 'ApproachTargetInReach', 0xD8: 'FanaticJump', 0xD9: 'FanaticRelease', 0xDA: 'ExcludeFromArmy',
    0xDB: 'IfGameMode', 0xDC: 'SetBattleState', 0xDD: 'IfBattleState', 0xDE: 'IfObjective', 0xDF: 'SetSide',
    0xE0: 'IfEngagedWithKind', 0xE1: 'FaceModelsToTarget', 0xE2: 'DrainEvents', 0xE3: 'IfTargetVisible',
    0xE4: 'CircleAroundTarget', 0xE5: 'ClearEvent', 0xE6: 'SetRanks', 0xE7: 'ClearAnimationRequest',
}


class Instruction(NamedTuple):
    offset: int
    opcode: int | None
    name: str
    operands: tuple[int, ...]


# opcode is None for pseudo instructions: name 'Label' (0x0ABC), 'End' (0x80E8) or 'Data' (any other
# word where an instruction was expected; operands = (word,)).


def load_names(paths: Iterable[str | PathLike[str]] | None, names: Mapping[int, str] | None = None) -> dict[int, str]:
    """Returns a copy of the name table updated from JSON catalogues {"<op>": {"name": ...}}."""
    table = dict(OPCODE_NAMES if names is None else names)
    for path in paths or ():
        catalogue: dict[str, Any] = json.loads(Path(path).read_text(encoding='utf-8'))
        for key, entry in catalogue.items():
            name = cast(dict[str, Any], entry).get('name') if isinstance(entry, dict) else entry
            if name:
                table[int(key, 0)] = name
    return table


def opcode_name(opcode: int, names: Mapping[int, str] | None = None) -> str:
    return (OPCODE_NAMES if names is None else names).get(opcode) or f'Op{opcode:02X}'


def opcode_of(word: int) -> int | None:
    """The opcode of an instruction word, or None."""
    return word & 0x7FFF if OPCODE_FLAG <= word < 0x10000 and (word & 0x7FFF) < OPCODE_COUNT else None


# ---------------------------------------------------------------- mission DLLs

def exports(image: PeImage) -> dict[str, int]:
    """{name: VA} of the export directory of a PE image."""
    pe = struct.unpack_from('<I', image.data, 0x3C)[0]
    optional = pe + 24
    rva: int = struct.unpack_from('<II', image.data, optional + 96)[0]
    if not rva:
        return {}
    base = image.image_base
    _, _, _, _, _, _, _, name_count, functions, names, ordinals = struct.unpack(
        '<IIHHIIIIIII', image.read(base + rva, 40))
    table: dict[str, int] = {}
    for i in range(name_count):
        name = image.cstring(base + image.u32(base + names + 4 * i)[0])
        ordinal = struct.unpack('<H', image.read(base + ordinals + 2 * i, 2))[0]
        table[name] = base + image.u32(base + functions + 4 * ordinal)[0]
    return table


def _defined(register: int | None) -> int:
    if register is None:
        raise ValueError('lookup reads a register before loading it')
    return register


def _run_lookup(image: PeImage, va: int, argument: int, limit: int = 64) -> tuple[str, int]:
    """Executes the tiny x86 subset used by DLLGetScriptPointer/DLLReturnInstCount for one argument.

    Returns ('table', VA) for ``mov eax, [eax*4 + VA]; ret``, ('value', n) for a constant return.
    """
    eax: int | None = None
    flags: int | None = None
    for _ in range(limit):
        code = image.read(va, 8)
        if code[:4] == b'\x8b\x44\x24\x04':                     # mov eax, [esp+4]
            eax, va = argument, va + 4
        elif code[:2] == b'\x83\xf8':                           # cmp eax, imm8
            flags, va = _defined(eax) - struct.unpack_from('<b', code, 2)[0], va + 3
        elif code[0] == 0x3D:                                   # cmp eax, imm32
            flags, va = _defined(eax) - struct.unpack_from('<i', code, 1)[0], va + 5
        elif code[0] in (0x7C, 0x7D, 0x7E, 0x7F, 0x74, 0x75):   # jl jge jle jg je jne rel8
            compared = _defined(flags)
            taken = {0x7C: compared < 0, 0x7D: compared >= 0, 0x7E: compared <= 0, 0x7F: compared > 0,
                     0x74: compared == 0, 0x75: compared != 0}[code[0]]
            va += 2 + (struct.unpack_from('<b', code, 1)[0] if taken else 0)
        elif code[:3] == b'\x8b\x04\x85' and code[7] == 0xC3:   # mov eax, [eax*4+disp32]; ret
            return 'table', struct.unpack_from('<I', code, 3)[0]
        elif code[:3] == b'\x33\xc0\xc3':                       # xor eax, eax; ret
            return 'value', 0
        elif code[0] == 0xB8 and code[5] == 0xC3:               # mov eax, imm32; ret
            return 'value', struct.unpack_from('<I', code, 1)[0]
        else:
            raise ValueError(f'{image.path.name}: unsupported instruction at {va:#x}: {code.hex()}')
    raise ValueError(f'{image.path.name}: lookup at {va:#x} does not return')


def _compare_constants(image: PeImage, va: int, limit: int = 64) -> set[int]:
    """Immediate operands of the comparisons in a lookup function (the id range boundaries)."""
    constants: set[int] = set()
    for offset in range(limit):
        code = image.read(va + offset, 5)
        if code[:2] == b'\x83\xf8':
            constants.add(struct.unpack_from('<b', code, 2)[0])
        elif code[0] == 0x3D:
            constants.add(struct.unpack_from('<i', code, 1)[0])
        if code[:3] == b'\x33\xc0\xc3':
            break
    return constants


def script_ranges(image: PeImage, va: int) -> list[tuple[int, int, int]]:
    """Decodes DLLGetScriptPointer: [(first id, end id, table VA)] with pointer = [table + 4*id]."""
    bounds = sorted({0, 0x8000} | {c for c in _compare_constants(image, va) if 0 <= c <= 0x8000})
    ranges: list[tuple[int, int, int]] = []
    for first, end in zip(bounds, bounds[1:]):
        low, high = _run_lookup(image, va, first), _run_lookup(image, va, end - 1)
        if low != high:
            raise ValueError(f'{image.path.name}: ids {first}..{end - 1} take different paths')
        if low[0] == 'table':
            ranges.append((first, end, low[1]))
        elif low[1] != 0:
            raise ValueError(f'{image.path.name}: ids {first}..{end - 1} return a constant {low[1]:#x}')
    return ranges


def _instruction_length(words: Sequence[int], pc: int) -> int:
    opcode = opcode_of(words[pc])
    return 1 if opcode is None else LENGTHS[opcode]


def _read_words(image: PeImage, va: int, count: int) -> tuple[int, ...]:
    try:
        return image.u32(va, count)
    except ValueError:              # near the end of the section
        return image.u32(va, 1)


def read_script(image: PeImage, va: int, stop: int | None = None, limit: int = 0x4000) -> list[int]:
    """Reads one script: up to and including its END word, or up to ``stop`` (the start of the next script).

    Scripts are stored one after another; a few library scripts (152-156, ending in ReturnGosub) have no
    END word and are followed directly by the next script, sometimes after a 0 word.
    """
    words: list[int] = []
    pc = 0
    while pc < limit:
        if stop is not None and va + 4 * pc >= stop:
            if va + 4 * pc > stop:
                raise ValueError(f'{image.path.name}: script at {va:#x} overlaps the script at {stop:#x}')
            return words[:pc]
        if pc >= len(words):
            words.extend(_read_words(image, va + 4 * len(words), pc + 16 - len(words)))
        if words[pc] == END:
            return words[:pc + 1]
        pc += _instruction_length(words, pc)
    raise ValueError(f'{image.path.name}: script at {va:#x} has no end marker')


class ScriptDll:
    """One SCRIPT/BFxxx.DLL: the script tables and DLLReturnInstCount."""

    def __init__(self, path: str | PathLike[str]) -> None:
        self.path = Path(path)
        self.image = PeImage(path)
        table = exports(self.image)
        self.lookup_va = table['DLLGetScriptPointer']
        self.inst_count = _run_lookup(self.image, table['DLLReturnInstCount'], 0)[1]
        self.ranges = script_ranges(self.image, self.lookup_va)
        self.pointers: dict[int, int] = {}
        for first, end, table_va in self.ranges:
            for script_id in range(first, end):
                self.pointers[script_id] = self.image.u32(table_va + 4 * script_id)[0]

    @property
    def mission_ids(self) -> list[int]:
        return sorted(i for i in self.pointers if i not in LIBRARY_IDS)

    def scripts(self, ids: Iterable[int] | None = None) -> dict[int, list[int]]:
        """{script id: [words]}: each list ends with the END word or where the next script starts."""
        starts = sorted(set(self.pointers.values()))
        result: dict[int, list[int]] = {}
        for script_id in (sorted(self.pointers) if ids is None else ids):
            va = self.pointers[script_id]
            stop = next((s for s in starts if s > va), None)
            result[script_id] = read_script(self.image, va, stop)
        return result


def script_dlls(installation: str | PathLike[str]) -> list[Path]:
    directory = Installation(installation).file_dir('SCRIPT')
    return sorted(p for p in directory.iterdir() if p.suffix.upper() == '.DLL')


# ---------------------------------------------------------------- disassembly

def disassemble(words: Sequence[int], names: Mapping[int, str] | None = None) -> list[Instruction]:
    """Linear disassembly: [Instruction(offset, opcode, name, operands)]."""
    out: list[Instruction] = []
    pc = 0
    while pc < len(words):
        word = words[pc]
        opcode = opcode_of(word)
        if word == END:
            out.append(Instruction(pc, None, 'End', ()))
            break
        if word == LABEL:
            out.append(Instruction(pc, None, 'Label', ()))
            pc += 1
        elif opcode is None:
            out.append(Instruction(pc, None, 'Data', (word,)))
            pc += 1
        else:
            length = LENGTHS[opcode]
            out.append(Instruction(pc, opcode, opcode_name(opcode, names), tuple(words[pc + 1:pc + length])))
            pc += length
    return out


def stray_words(instructions: Iterable[Instruction]) -> list[Instruction]:
    """Data words that are not dead padding right after an unconditional transfer (or other padding)."""
    stray: list[Instruction] = []
    dead = False
    for instruction in instructions:
        if instruction.name == 'Data':
            if not dead:
                stray.append(instruction)
            continue
        dead = instruction.opcode in UNCONDITIONAL
    return stray


def _operand(value: int) -> str:
    signed = value - (1 << 32) if value & 0x80000000 else value
    return str(signed) if -4096 < signed < 4096 else f'{value:#x}'


def format_script(words: Sequence[int], names: Mapping[int, str] | None = None, script_id: int | None = None) -> str:
    """Text listing with label targets and If/Else nesting."""
    instructions = disassemble(words, names)
    lines = [] if script_id is None else [f'script {script_id}:']
    depth = 0
    for ins in instructions:
        if ins.name in ('EndIf', 'Else'):
            depth = max(0, depth - 1)
        indent = '  ' * depth
        if ins.name == 'Label':
            text = f'L{ins.offset}:'
        elif ins.name in ('End', 'Data'):
            text = f"{indent}{ins.name}" + (f' {ins.operands[0]:#x}' if ins.operands else '')
        elif ins.opcode == 0x6B and ins.operands:
            # Break clears bit 12 of its operand and scans forward from the next word for that value.
            wanted = ins.operands[0] & ~0x1000
            target = next((i for i in range(ins.offset + 2, len(words)) if words[i] == wanted), None)
            where = '?' if target is None else (f'L{target}' if wanted == LABEL else f'word {target}')
            text = f'{indent}{ins.name} -> {where}'
            if ins.operands[0] != BREAK_LABEL:
                text += f' (operand {_operand(ins.operands[0])})'
        else:
            text = f"{indent}{ins.name}" + ''.join(f' {_operand(v)}' for v in ins.operands)
            if ins.opcode == 0x19 and ins.operands:
                text += f'  -> {ins.offset + 2 + ins.operands[0]}'
        lines.append(f'{ins.offset:5d}  {text}')
        if ins.name in ('If', 'IfNot', 'Else'):
            depth += 1
    return '\n'.join(lines)


# ---------------------------------------------------------------- lengths from GAMEF.DLL

_PC_LOADS = {b'\x66\xa1' + struct.pack('<I', VA_PC): 0}   # mov ax, [pc]
_PC_LOADS.update({b'\x66\x8b' + bytes([modrm]) + struct.pack('<I', VA_PC): reg
                  for reg, modrm in ((1, 0x0D), (2, 0x15), (3, 0x1D), (6, 0x35), (7, 0x3D))})
_PC_PREINCREMENT = b'\x66\xff\x05' + struct.pack('<I', VA_PC)   # inc word [pc]


def handler_returns(gamef):
    """Re-derives the 'return PC + n' increments of every handler from GAMEF.DLL.

    Recognises ``mov r16, [pc]`` followed (after pops or ``add esp, imm8``) by ``add r16, imm8``,
    ``inc r16`` or ``ret``, within the handler's bytes up to the next handler or int3 padding.
    Returns {opcode: (set of increments, pre-incremented)}.
    """
    handlers = gamef.u32(VA_HANDLERS, OPCODE_COUNT)
    starts = sorted(set(handlers))
    result = {}
    for opcode, start in enumerate(handlers):
        following = [s for s in starts if s > start]
        size = min((following[0] if following else start + 0x1000) - start, 0x1000)
        code = gamef.read(start, size)
        padding = code.find(b'\xc3\xcc\xcc')
        if padding >= 0:
            code = code[:padding + 1]
        increments = set()
        for i in range(len(code) - 6):
            reg = _PC_LOADS.get(code[i:i + 6]) if code[i + 1] == 0xA1 else _PC_LOADS.get(code[i:i + 7])
            if reg is None:
                continue
            j = i + (6 if code[i + 1] == 0xA1 else 7)
            while j < len(code):
                if 0x58 <= code[j] <= 0x5F:
                    j += 1
                elif code[j:j + 2] == b'\x83\xc4':
                    j += 3
                else:
                    break
            if code[j:j + 3] == bytes([0x66, 0x83, 0xC0 + reg]):
                increments.add(code[j + 3])
            elif reg == 0 and code[j:j + 2] == b'\x66\x05':                 # add ax, imm16
                increments.add(struct.unpack_from('<H', code, j + 2)[0])
            elif code[j:j + 3] == bytes([0x66, 0x81, 0xC0 + reg]):         # add r16, imm16
                increments.add(struct.unpack_from('<H', code, j + 3)[0])
            elif code[j:j + 2] == bytes([0x66, 0x40 + reg]):
                increments.add(1)
            elif code[j:j + 1] == b'\xc3':
                increments.add(0)
        result[opcode] = (increments, code.startswith(_PC_PREINCREMENT))
    return result


def check_lengths(gamef):
    """Compares LENGTHS with the handler code; returns (failures, number of opcodes confirmed)."""
    failures, confirmed = [], 0
    for opcode, (increments, preincrement) in handler_returns(gamef).items():
        derived = max(increments - {0}, default=0) + preincrement
        if derived == LENGTHS[opcode]:
            confirmed += 1
        elif opcode not in HANDLER_LENGTHS_NOTE:
            failures.append(f'opcode {opcode:#04x}: handler returns {sorted(increments)}'
                            f'{" after a PC increment" if preincrement else ""}, table {LENGTHS[opcode]}')
    return failures, confirmed


# ---------------------------------------------------------------- checks

def check(installation):
    """Decodes every script of every mission DLL and cross-checks the battles. Prints one summary line."""
    game = Installation(installation)
    failures = []
    length_failures, confirmed = check_lengths(PeImage(game.require('GAMEF.DLL')))
    failures += length_failures
    library, dlls, totals = None, {}, Counter()
    for path in script_dlls(game.root):
        dll = ScriptDll(path)
        dlls[path.name.casefold()] = dll
        if dll.inst_count != INST_COUNT:
            failures.append(f'{path.name}: DLLReturnInstCount {dll.inst_count}')
        ids = dll.mission_ids
        if ids != list(range(len(ids))) or not ids or not set(LIBRARY_IDS) <= set(dll.pointers):
            failures.append(f'{path.name}: unexpected script ids {sorted(dll.pointers)}')
        scripts = dll.scripts()
        for script_id, words in scripts.items():
            instructions = disassemble(words)
            totals['scripts'] += 1
            totals['words'] += len(words)
            totals['instructions'] += sum(i.opcode is not None for i in instructions)
            data = [i for i in instructions if i.name == 'Data']
            totals['padding'] += len(data)
            stray = stray_words(instructions)
            failures += [f'{path.name} script {script_id}: stray word {i.operands[0]:#x} at {i.offset}'
                         for i in stray]
            if words[-1] != END:
                totals['open'] += 1
                code = [i for i in instructions if i.name not in ('Data', 'Label')]
                if not code or code[-1].opcode not in UNCONDITIONAL:
                    failures.append(f'{path.name} script {script_id}: falls through into the next script')
        lib = {i: scripts[i] for i in LIBRARY_IDS if i in scripts}
        if library is None:
            library = lib
        elif lib != library:
            failures.append(f'{path.name}: library scripts differ from {next(iter(dlls.values())).path.name}')
    references = 0
    for bts in sorted(p for p in game.file_dir('SCRIPT').iterdir() if p.suffix.upper() == '.BTS'):
        battle = script.load_battle(str(bts), with_merc=False)
        name = battle['field']['script']
        values = _script_values(bts)
        if name is None:
            totals['no_dll'] += 1       # not a battle (e.g. PLOT1.BTS): nothing to resolve against
            continue
        dll = dlls.get(name.casefold()) or dlls.get(f'{name}.dll'.casefold())
        totals['battles'] += 1
        if dll is None:
            failures.append(f'{bts.name}: loadScript {name!r} not found')
            continue
        for value in values:
            references += 1
            script_id = PLAYER_SCRIPT if value.upper() == 'PLAYER_SCRIPT' else int(value, 0)
            if script_id not in dll.pointers:
                failures.append(f'{bts.name}: set:script={value} not in {dll.path.name}')
    for failure in failures[:20]:
        print(f'  {failure}')
    if failures:
        print(f'  behaviour scripts: {len(failures)} failures')
    else:
        print(f"  behaviour scripts: {len(dlls)} DLLs, {totals['scripts']} scripts ({totals['open']} without "
              f"END), {totals['words']} words, {totals['instructions']} instructions, no stray words "
              f"({totals['padding']} padding); library {len(library)} scripts identical; InstCount {INST_COUNT}; "
              f"{confirmed}/{OPCODE_COUNT} lengths read from the handlers; {references} set:script values in "
              f"{totals['battles']} battles resolved ({totals['no_dll']} BTS without loadScript)")
    return not failures


def _script_values(path):
    """Distinct set:script= values of the unit blocks of a .BTS file."""
    values = set()

    def walk(node):
        value = node['set'].get('script')
        if value is not None and node['kind'] in ('addunit', 'addleader'):
            values.add(str(value).strip())
        for child in node['children']:
            walk(child)
    walk(script.parse(str(path)))
    return values


# ---------------------------------------------------------------- command line

def _find_dll(installation, name):
    path = Path(name)
    if path.exists():
        return path
    for candidate in script_dlls(installation):
        if candidate.name.casefold() in (name.casefold(), f'{name}.dll'.casefold()):
            return candidate
    raise FileNotFoundError(name)


def main(installation, dll=None, ids=None, name_files=None):
    names = load_names(name_files)
    if dll is None:
        for path in script_dlls(installation):
            item = ScriptDll(path)
            scripts = item.scripts()
            mission_words = sum(len(scripts[i]) for i in item.mission_ids)
            library_words = sum(len(scripts[i]) for i in LIBRARY_IDS)
            print(f'{path.name:12s} mission scripts {len(item.mission_ids):2d} ({mission_words:5d} words), '
                  f'library {len(LIBRARY_IDS)} ({library_words} words)')
        return 0
    item = ScriptDll(_find_dll(installation, dll))
    selected = [int(i, 0) for i in ids] if ids else sorted(item.pointers)
    for script_id, words in item.scripts(selected).items():
        print(format_script(words, names, script_id))
        print()
    return 0
