# Optional Ghidra helpers (analysis only)

These scripts are **not** part of the stdlib-only tool chain in `whshr/` and `scripts/`. They were
used for the static analysis of `GAMEF.DLL`/`WHSHR.EXE` behind `notes/game_rules.md`, and are only
needed to repeat or extend that analysis.

Their output is decompiled code derived from copyrighted binaries: write it to a scratch directory,
never into the repository. Do not paste large listings into the notes; describe the logic instead.

## Setup used (September 2026, no root needed)

- Eclipse Temurin JDK 21 (`OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz`, SHA-256 checked)
  unpacked to `~/tools/jdk-21.0.12.1+1`.
- Ghidra 12.1.3 (`ghidra_12.1.3_PUBLIC_20260817.zip`, SHA-256 checked) unpacked to
  `~/tools/ghidra_12.1.3_PUBLIC`.
- Projects in `~/tools/ghidra_projects` (`gamef` for `GAMEF.DLL`, `whshr_exe` for `WHSHR.EXE`),
  created with default auto-analysis.

```sh
export JAVA_HOME=~/tools/jdk-21.0.12.1+1 PATH=~/tools/jdk-21.0.12.1+1/bin:$PATH
H=~/tools/ghidra_12.1.3_PUBLIC/support/analyzeHeadless
GAME=".../WARFB"            # the installation directory
OUT=/some/scratch/dir       # outside the repository

# one-time import and analysis (a few minutes)
$H ~/tools/ghidra_projects gamef -import "$GAME/GAMEF.DLL"

# references to strings matching a regex (code references and pointer tables)
$H ~/tools/ghidra_projects gamef -process GAMEF.DLL -noanalysis -readOnly \
   -scriptPath tools/ghidra -postScript DumpStringRefs.java '^(s_|psy_status|Cant)' $OUT/refs.txt

# decompile selected functions, or all of them into one greppable file
$H ~/tools/ghidra_projects gamef -process GAMEF.DLL -noanalysis -readOnly \
   -scriptPath tools/ghidra -postScript Decompile.java $OUT/gamef_all.c all
```

## Scripts

| Script | Arguments | Output |
|---|---|---|
| `DumpStringRefs.java` | `<regex> <output file>` | every defined string matching the regex, its references, and for pointer-table slots the probable table start with its references |
| `Decompile.java` | `<output file> all \| <address>...` | decompiled C of the functions (containing) the addresses, each headed by its entry point and callers |
