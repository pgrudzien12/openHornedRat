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

Deployment-specific script scheduling, attack restrictions, preserved state and shipped
mission examples are documented in [deployment.md §5](../deployment.md#5-deployment-time-and-starting-battle).
The exact periodic AI period, countdown initialization and reload timing are published in
[deployment.md §5.3](../deployment.md#53-periodic-ai-countdown-exact-timing-handoff).
These rules are required when adding a deployment phase; treat mission choreography state
separately from the screen's deployment/normal-play phase.

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

## BF001 chain: what the scripts do and how the engine reads them

Observable behaviour, from the script data and play tests (issue [#143](https://github.com/pgrudzien12/openHornedRat/issues/143)
tracks the four opcodes that are still unspecified):

1. Hiln's Guard idles until an enemy is inside its own threat range (240), then tells its whole side
   (event 17). The default handler answers by raising a persistent gate bit (16) that the Clanrat
   reinforcements and the assassin Sleaquit wait for.
2. Sleaquit then hunts Otto Hiln (same side; the tag Otto sets on himself). Otto's script kills him as soon
   as he is in melee (unit flag `0x200`), which the engine mirrors from `Regiment.in_melee`.
3. The three Clanrat regiments march to script nodes 8 and 9 and patrol between them. Their explicit nearest-enemy searches have no search-radius
   cutoff; periodic threat decisions separately use their configured threat range.

Engine decisions (each one covered by a test):

- **One condition word.** `SetCondFlags`/`ClearCondFlags`/`TestCondFlags` and the true/false result read by
  `If`/`LoopIf*`/`YieldIfTrue`/`SkipIfTrue`/`IfGotoScript` are the same 16-bit word (bit 2 is the result), and the
  condition is reset at every tick start ([unit_script_control.md](../unit_script_control.md)). An earlier
  two-register split (result vs. bit word) is superseded; the engine's `cond_flags` is now a view of bit 2.
- **Node numbers are positions in `[NODES]`, counted from 0.** The `id` field is 0 for almost every node and
  is not a key. Evidence for base 0: only counting from 0 gives BF001's Hiln's Guard a patrol beside its own
  camp instead of the east map edge, and the Clanrats a route from their spawn towards the player.
- **Nearest-enemy search has no radius cutoff.** The earlier provisional threat-range/300-unit
  filter is superseded. Plain nearest ranking uses whole-unit Euclidean distance; visible
  variants add visibility, not a radius. Hidden/broken and other excluded targets remain
  ineligible, and deployment refuses the attack instruction. Full rules and acceptance
  examples: [game_rules.md](../game_rules.md#scripted-nearest-enemy-search-range-and-failure-rules).
- **Scripted same-side fights.** Same-side engagement is refused unless the target is the unit's current
  opponent (game_rules.md, engagement rules), so a scripted opponent may be a friend. The attacker fights on
  a camp of its own (`Side.DUEL`) for that fight, so tallies, break tests and the grid's adjacency check tell
  the two apart. The player's own orders never name a same-side target.

- **`Break` jumps to its label** (the next `0x0ABC` word after its operand), so a matched `CaseEvent` body skips the
  rest of the case chain and the default handler behind it. Falling through ran the default handler after every
  handled event and overrode scripted switches.
- **Event 0x19 "opponent gone"** is queued to a unit that leaves a fight because every opponent it had is
  destroyed or off the field (not merely routing: the rout event decides between pursuit and a new opponent).
- **`DropTarget`, `FleeAhead`, `StoreEventInfo`, `FaceModelsToTarget`** follow `game_rules.md`, "Scripted target and
  flight opcodes". `StoreEventInfo` fills the remembered-event slot; its only reader, the brace query
  (`Query 7`), is not implemented yet, so bracing still comes from `FearWhenCharged`.

Result in a headless BF001 run (player cavalry sent into Hiln's Guard's range): Otto dies about tick 353, Sleaquit
routs at once, runs along the bearing of node 5 and leaves the field by the east edge.

Still open here: the three Clanrat regiments ordered to the same node block each other around it (each is held
off by the other two, ~35 units from a node with radius 16) and never reach it; flag 8 (routed) that `WaitWhileUnitFlags` waits on is not raised by anything yet; `Query 7`.
