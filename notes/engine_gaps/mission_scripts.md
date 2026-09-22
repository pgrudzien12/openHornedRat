# Gap: mission scripts & scripted events

**Symptom**: `whshr/ai.py` is a from-scratch 36-line rule ("hold until a player regiment is within a fixed
distance, then shoot or charge the nearest one"). It explicitly does not run the original's per-unit
behaviour bytecode, so a mission's actual choreography (patrols, ambush waits, scripted reinforcements,
retreats to a rally node, "assist a friend" calls) never happens. Every battle plays out as a generic
brawl instead of following its `.BTS`/`SCRIPT/BFxxx.DLL` design.

## Known facts

All of this is already public in `notes/game_rules.md` §"Unit behaviour scripts and events" and
§"Missions and objectives":

- The mission DLLs are pure bytecode data (not native code): a 232-opcode instruction set, catalogued in
  full, with a working disassembler (`python3 -m whshr scripts`, implemented in `whshr/behaviour.py`).
  Ids 0–37ish per DLL are mission-specific unit scripts; ids 100–170 are a shared library identical across
  all 45 DLLs (morale, orders, targeting, class-specific handlers).
- Per-unit runtime state needed to execute a script: current script id, program counter, a small return
  stack, an interrupt script, a pending-switch flag, current event, and a 128-record event queue/pool
  (14-byte records: recipient, code, source, parameter, x, y, link). The event table (36 codes) and their
  default library handling are listed in game_rules.md's event table.
- Spawning at runtime is minimal and catalogued: only Night Goblin Fanatics are created live (opcode
  0xD3, in BF004_5/BF015/BF034/BF038); everything else exists from battle start. `hidden:` units exist but
  are invisible/untargetable until spotted or scripted to appear (delayed reinforcements = hidden units
  whose script waits on a timer, e.g. BF001's three Clanrat Warriors after 150 ticks).
- AI coordination beyond one unit's own script comes only from event 0x13 ("a friendly unit attacks" →
  look for a target) and from mission scripts assigning "attack the n-th nearest enemy" (opcodes 176–191).
  There is no army-level AI in the original either — `whshr/ai.py`'s simplicity is not itself the gap; the
  missing choreography is.

## Open questions

- Per-mission walkthroughs (what each of the 45 DLLs' mission scripts actually choreograph) exist only as
  private research notes so far (referenced as "private research notes" in game_rules.md's objectives
  section) beyond the BF001 summary already made public. **Before implementing beyond BF001**, each
  mission that's brought online needs its own public walkthrough section (which nodes, which timers, which
  events, in plain behavioural terms) added to game_rules.md or here.
- Whether an engine-side bytecode interpreter (reading the opcode tables as data, per `ROADMAP.md`'s Phase
  5 "never execute `SCRIPT/BFxxx.DLL` as native code" rule) or a hand-rewritten per-mission script (4.5,
  "readable DSL") is the right target for M5 is an open engine design decision, not a research question —
  ROADMAP.md leaves both options open pending 4.1/4.5.

## Implementation notes

- A generic bytecode interpreter (reading the catalogued opcode table, one instance of runtime state per
  unit) is the only approach that scales past BF001 without rewriting 45 missions by hand; a hand-rewritten
  script is reasonable as a first playable slice for BF001 only (M5).
- The interpreter needs: an event bus per unit + per side (matching the original's "queue to self / own
  side / enemy side" primitives), a node/waypoint table from the `.BTS` (already parsed), and hooks into
  `whshr/combat.py`/`whshr/engine.py` for the handful of C-side effects the scripts call into (rout, charge,
  shoot, cast — already implemented for the simplified rules).
- `whshr/ai.py`'s placeholder `ENGAGE_DISTANCE` rule should be replaced by the interpreter driving standard
  library behaviour 15 (`TrackThreat`) for AI-controlled units, once threat scoring (already documented in
  game_rules.md's "Routes, collisions and visibility" section) is ported.
