# `SkipIfTrue` (opcode 0x19) — behaviour of the unit-script conditional skip

Public implementation report. Complements "Unit behaviour scripts and events" in `game_rules.md` and the
library walkthrough in `dwarf_behavior_library.md` (script 162). Describes observable behaviour only.

## Encoding

Two words: the opcode word, then one operand word `N` (a signed count of **words**). It is the only
conditional *forward-skip by distance* opcode; the other conditionals use pushed addresses or labels (see below).

## Behaviour

1. **Condition read.** It reads the unit's **persistent condition bit** — the same bit that `SetCondFlags 4`,
   `ClearCondFlags`, `TestCondFlags`, `TestWait`, and the result-producing opcodes (`Find*`, `Test*`, `Attack*`,
   `FaceModelsToTarget`, `FleeAhead`, ...) write, and that `LoopIfTrue`, `LoopIfFalse`, `YieldIfTrue`, `If` and
   `IfNot` read. There is no separate "result register".
2. **Condition true:** continue at `pc + 2 + N`, where `pc` is the word index of the `SkipIfTrue` opcode itself.
   Equivalently: `N` counts the words **after** the two-word instruction, so the operand word is *not* part of the
   skipped span; `N = 0` is a no-op, `N = 1` skips exactly one following word.
3. **Condition false:** nothing happens; continue at `pc + 2`.
4. **The condition is neither consumed nor changed** (true stays true, false stays false), so later
   `LoopIfTrue`/`If`/`YieldIfTrue` still see it.
5. The count is raw words, not instructions: a skipped instruction of length 2 needs `N = 2`.

## Worked example — library script 162 (identical in every mission DLL)

```
word 0   FleeFromTarget          (1 word)
word 1   SkipIfTrue 1            (2 words: 1, 2)
word 3   FleeAhead               (1 word)     <- the skipped word
word 4   PushPC
word 5   Yield
word 6   Loop
word 7   End
```

`1 + 2 + 1 = 4`, so the true case lands on `PushPC` (word 4) and skips only `FleeAhead`; the false case
executes `FleeAhead` at word 3, then falls into `PushPC`. (The disassembler already prints this as `-> 4`.)

What the condition is here (from the behaviour of `FleeFromTarget`):
- **No current target:** the unit prints a debug message, performs the `FleeAhead` behaviour itself (rout along
  its facing, target cleared) and the condition is left **true** → `SkipIfTrue` skips the explicit `FleeAhead`
  (avoids a double start).
- **With a target:** the unit routs directly away from the target (bearing + 180°), the target is cleared and the
  condition is left **false** → `SkipIfTrue` does *not* skip, so `FleeAhead` then runs too and restarts the rout
  along the unit's current facing. This is what the data does; whether the original designers intended that
  override is unknown (🟡 intent), but the behaviour is as stated.

## Edge cases

- **No bounds or label checks.** The skip is plain word arithmetic: it may jump over `0x0ABC` labels and over the
  `0x80E8` end word without special treatment (unlike `If`/`Else`, which scan forward nesting-aware and stop at
  the end word). A skip that lands beyond the end of the script is not handled by the opcode; this never occurs in
  shipped data (🟡 consequence untested).
- **Negative `N`** would be added as a signed value (backward jump); not used by any shipped script.
- A landing point in the middle of a multi-word instruction would read an operand as an opcode; shipped data
  lands only on instruction boundaries.
- **Usage census:** exactly one use in all shipped scripts — library script 162, operand 1. None in any
  mission-specific script.

## Related opcodes (by name/code)

Same condition bit, different transfer mechanism: `LoopIfTrue` 0x08 and `LoopIfFalse` 0x09 (jump to the
`PushPC` address), `YieldIfTrue` 0x18, `If` 0x6C / `IfNot` 0x6D (nesting-aware forward scan to `Else`/`EndIf`).
No other opcode skips by a fixed word distance; `Break` 0x6B jumps to the next label and `CaseEvent` 0x6A skips
past the next `Break`.
