# Research and implementation boundary

Open Horned Rat is an independent engine project. It accepts behavioural and file-format
facts about the original game, not original program code or its structure.

## Research hand-off

Research may inspect a legally owned local installation, observe the running game, and use
private analysis material when needed. Its public output is a behavioural specification: a
description of what a player can observe and what an independent engine must reproduce.

Public reports may contain:

- gameplay rules, formulas, small lookup tables, and state transitions;
- documented layouts of user-supplied game-data files;
- reproducible observations, test cases, examples, and open questions.

Public reports must not contain executable addresses, internal function or data labels,
assembly, decompiler output or pseudocode, analysis-tool output, or instructions for
recovering any of them.

## Implementation

Implementers use public reports, documented game-data formats, and independent tests. They
do not use executable analysis, private research reports, disassembly, decompilation, or
source-location information as implementation input.

If a needed fact is only available in private research material, the next step is a new
public behavioural report—not implementing from that material directly.

This boundary does not restrict ordinary parsing of game data supplied by the player. The
engine needs those files at runtime, but it never ships them.
