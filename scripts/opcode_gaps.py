#!/usr/bin/env python3
"""Which behaviour-script opcodes the interpreter still lacks, weighted by how often shipped scripts use them.

    WARFB=/path/to/WARFB .venv/bin/python scripts/opcode_gaps.py [installation]

Prints, most used first, every opcode without an `op_<Name>` handler in `whshr.interpreter.ScriptInterpreter`
(use count and number of mission DLLs), then the missing opcodes no shipped script uses, then handlers whose
body still says TODO / placeholder / simplified. Reads the user's own installation; writes nothing.
"""

import collections
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whshr import behaviour  # noqa: E402
from whshr.interpreter import ScriptInterpreter  # noqa: E402


def main(argv: list[str]) -> int:
    installation = argv[1] if len(argv) > 1 else os.environ.get("WARFB")
    if not installation:
        print("usage: opcode_gaps.py [installation]  (or set WARFB)", file=sys.stderr)
        return 2
    names = {o: behaviour.opcode_name(o) for o in range(len(behaviour.LENGTHS))}
    missing = {n for n in names.values() if not hasattr(ScriptInterpreter, "op_" + n)}
    uses: collections.Counter[str] = collections.Counter()
    dlls: dict[str, set[str]] = collections.defaultdict(set)
    for path in behaviour.script_dlls(installation):
        for words in behaviour.ScriptDll(path).scripts().values():
            for instruction in behaviour.disassemble(words):
                if instruction.opcode is not None:
                    uses[instruction.name] += 1
                    dlls[instruction.name].add(path.name)
    print(f"{len(missing)} of {len(names)} opcodes have no handler\n\nMISSING, used by shipped scripts:")
    for name, count in uses.most_common():
        if name in missing:
            print(f"{count:6d} {len(dlls[name]):3d} DLLs  {name}")
    print("\nMISSING, never used:", ", ".join(sorted(missing - set(uses))))
    source = Path(ScriptInterpreter.__module__.replace(".", "/") + ".py")
    text = (Path(__file__).resolve().parent.parent / source).read_text()
    partial = [m.group(1) for m in re.finditer(r"    def (op_\w+)\(.*?(?=\n    def |\Z)", text, re.S)
               if re.search(r"TODO|placeholder|stub|for now|simplif|PROVISIONAL", m.group(0), re.I)]
    print("\nHandlers marked partial/provisional:", ", ".join(partial))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
