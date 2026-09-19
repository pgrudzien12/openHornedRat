# Research plan: remaining agent batches

Plan for the static-analysis work that is still open after the first rules pass and the research batches
A–F (September 2026). Results so far are in `notes/game_rules.md` (open-point register in section 11); the
full agent reports are kept locally in `extracted/agent_reports/` (git-ignored, derived from the binaries).

Batches are run with three agents at a time. Each agent writes its report incrementally, so work survives a
spend-limit interruption. After a batch, its results are merged into `notes/`, `FORMATS.md`, `ROADMAP.md`
and `CLAUDE.md` before the next batch starts.

| Batch | Agents | Status | Depends on |
|---|---|---|---|
| 3 | G opcodes 0–115, H opcodes 116–231 and AI queries, I `whshr` script disassembler | ✅ done (September 2026): all 232 opcodes and 28 `AIQuery` cases, `whshr/behaviour.py` and `whshr scripts`; merged into `notes/game_rules.md` | – |
| 4 | J missions and objectives, K campaign progression and saves, L AI, pathfinding and visibility | ✅ done (September 2026): L and J (Sonnet), K (Opus); merged into `notes/game_rules.md` and `notes/campaign.md` | batch 3 ✅ |
| 5 | M animation bytecode and game events → sound/music/palette (optional) | ⬜ optional | batch 3 |
| – | small leftovers, Wine checks, engine decisions | not for agents | – |

Rough cost: about 300k tokens per agent (batches 1 and 2 used 0.9–1.0 M tokens each).

## Common brief for every agent

Give each agent this context, then its own section below.

- **Project**: hobby reverse engineering of an owned copy of "Warhammer: Shadow of the Horned Rat" (1995) for
  an open-source engine. Repository `R=/home/pawel/code/whshr-reverse-engineering`; read `CLAUDE.md`,
  `notes/game_rules.md` (and `notes/engine_architecture.md` for J/K) and the relevant earlier reports in
  `$R/extracted/agent_reports/` (A close combat, B morale and behaviour VM, C shooting, D flags and orders,
  E time and movement, F magic, and later G/H/I).
- **Game installation** (read-only): `~/snap/steam/common/.local/share/Steam/steamapps/compatdata/3605483607/pfx/drive_c/GOG Games/Warhammer - Shadow of the Horned Rat/WARFB/`.
- **Resources** (research agents only; implementation agents must not read decompiled output, see CLAUDE.md clean-room policy):
  - `$R/extracted/decompiled/gamef_all.c` and `exe_all.c`: Ghidra decompilation of all functions of
    `GAMEF.DLL` and `WHSHR.EXE`, with a header per function (`// ==== FUN_x @ addr callers:`).
  - `$R/extracted/agent_reports/fn.py` prints whole functions; `D/gamef.asm` is a full objdump of `GAMEF.DLL`.
  - `objdump -d -M intel --start-address=… --stop-address=…`.
  - `whshr/rules.py` `PeImage` (`.read`, `.u32`, `.cstring`); `.data` VA `0x100E7000` ↔ file offset
    `0x69400`, `.rdata` `0x100E6000` ↔ `0x68C00`, `.text` `0x10001000` ↔ `0x400`.
  - Text resources: `$R/extracted/pe_resources/{GMTXT,BRTXT,BKTXT}/strings.txt`.
  - Parsers: `whshr/script.py` (BTS/MRC), `whshr/campaign.py` (glue scripts), `whshr/behaviour.py`
    (`python3 -m whshr scripts <installation> [DLL] [ids…]`; catalogues `extracted/agent_reports/G/opcodes_0_115.json`,
    `H/opcodes_116_231.json`, `H/aiquery.json`, library table in `I_behaviour_tool.md`).
- **Ghidra** 12.1.3 headless (`~/tools/ghidra_12.1.3_PUBLIC`, JDK `~/tools/jdk-21.0.12.1+1`, scripts in
  `$R/tools/ghidra/`). Agents run in parallel, so an agent never opens `~/tools/ghidra_projects/*`
  directly; it copies the `.gpr` and `.rep` into its own scratch directory first.
- **Rules**:
  - Do not modify tracked files (except where a brief says so); do not install anything.
  - Write under `$R/extracted/agent_reports/` (report `<letter>_<topic>.md`, scratch in `<letter>/`).
  - **Write the report incrementally.**
  - Mark claims ✅ established (code path: address, what it reads, formula; or data consistent across all
    files), 🟡 hypothesis, or ⬜ unresolved.
  - Compare with Warhammer Fantasy Battle 4th edition where relevant.
  - No large decompiled listings; English only.
  - Final message: a compact per-question summary and the report path.

## Batch 3: behaviour bytecode catalogue and disassembler

VM facts:
- **Interpreter and handlers**: `RunUnitScript` is `FUN_1001cae0`; the handler table at `0x100F53A0` has 232
  entries.
- **Encoding**: a word with bit 15 set is an opcode; `0x0ABC` is a label and `0x80E8` ends a script. Each
  handler returns the next PC. The context record is at `0x1006D138`.
- **Script source**: scripts come from `SCRIPT/BFxxx.DLL` through `DLLGetScriptPointer`. Mission ids start at
  0, with 3–37 scripts per DLL; the library, ids 100–170, is identical in all 45 DLLs. `DLLReturnInstCount`
  returns 33000.
- **Names already known** (reuse them): B (control flow, events), C (shooting, decimal 104–134), D (flag
  opcodes 0x22–0x2B), E (0x33, 0xD3, 0xD8), F (casting, 147–175).

Useful leftovers of the interrupted run (local):
- `G/usage.json`: per-opcode usage by library script and mission count.
- `G/sd.py`: loader with the real mission script count per DLL.
- `G/h.py`: handler disassembly by opcode.
- `B/ops.txt`, `B/ovr.txt`: operand increments.

Earlier prototypes `B/sdis.py` and `scriptdump.py` wrongly assume 11 mission scripts per DLL.

### G: opcodes 0–115, plus R48, R49, R56, R57

- **Deliverables**:
  - `G_opcodes_0_115.md`: one row per opcode with handler, operands, UpperCamelCase name, semantics, status
    and "used by" (from `G/usage.json`), grouped by area.
  - `G/opcodes_0_115.json`: `{"<op>": {"name", "operands", "handler", "summary", "status"}}`.
- **R48**: the withdraw condition `FUN_10024710`.
- **R49**: `+0xB4 & 0x100000`, set by `AIQuery` at `0x10021703`.
- **R56**: casting in close combat, and the turn step before a cast (library scripts 132/142, `GMTXT 2010`).
- **R57**: area objects (`FUN_10017360`/`FUN_100173b0`) and movement/collision.

### H: opcodes 116–231, `AIQuery` cases, plus R53, R54, R58

- **Deliverables**:
  - `H_opcodes_116_231.md`: same table format as G.
  - `H/opcodes_116_231.json`.
  - `H/aiquery.json`: every case of `FUN_100214b0`, used by `Query N` (opcode 0x16) and by the behaviour codes
    of opcode 0x33.
- **R53**: the AI area-spell rule in `AIChooseSpell` `FUN_10013f40` (inverted?).
- **R54**: starting magic power (`battle+0x32BA0+0x528/+0x52C`), and whether Storm of Shemtek fires 2D6 or
  2D6+1 bolts.
- **R58**: the saves/flags each spell passes to `ApplyImpact` (which spells can wound regenerating models).

### I: `whshr/behaviour.py` disassembler, plus R46, R47

- **May create** `whshr/behaviour.py` and edit `whshr/__main__.py`.
- **Module**:
  - parse `DLLGetScriptPointer` of each DLL robustly, decoding the bounds and table addresses from the
    function bytes (verified on all 45 DLLs);
  - operand sizes derived from the `GAMEF.DLL` handlers, or a verified table;
  - an opcode name table, from the notes/reports plus optional JSON from G/H;
  - `disassemble()` and a text formatter.
- **`check(installation)`**:
  - no stray words in any script;
  - the library is identical in all DLLs;
  - `DLLReturnInstCount` is 33000;
  - every `set:script=N` in `FILE/SCRIPT/*.BTS` exists in its battle's DLL (`PLAYER_SCRIPT` = 100).
- **Wiring**: add the check to `python3 -m whshr check`, add a `scripts <installation> [DLL] [ids...]`
  subcommand, and run the full check.
- **Report** `I_behaviour_tool.md`: design, verification numbers, and a table of library scripts 100–170 with
  one-line descriptions.
- **R46**: the exact angular half-width formula in `ObjectOnLine` `FUN_10016fc0` (x87 code).
- **R47**: what `FUN_10001300` spawns when a doom diver lands.

After batch 3: merge the G/H JSON into the module's name table; add an opcode reference (a section of
`notes/game_rules.md` or a new `notes/behaviour_scripts.md`); update R38, R41, R44, R46–R49, R51, R53–R58.

## Batch 4: missions, campaign, AI (after batch 3)

### J: missions and objectives

Goal: what each battle's mission scripts do, and how victory and defeat are decided, so that one mission
(`BF001`, milestone M5) can run on an open engine.

- **Mission scripts**: summarise the mission scripts (ids 0…N) of every `BFxxx.DLL` with the batch 3
  disassembler: which units get which script, triggers, timers, conditions, messages.
- **Mission events**: the mission-only event codes 0x05, 0x14, 0x15, 0x33, 0x35, 0x37 (no C sender), and the
  battle phase change 0x38.
- **Spawned units**: units spawned by scripts (opcode 0xD3, hidden units, `hidden:` in the `.BTS`); explain
  the units packed in `SPRITES.PBX` but missing from the `.BTS` (20 of 44 battles).
- **Reinforcements and deployment**: reinforcements and off-map units (e.g. the crossbowmen at x = 1814 in
  `BF001`), `DeployTroops`, the deployment area, and `ns_startpos`/`NS_END` nodes and how player units reach
  them.
- **Objective index 7 and leaving units** (R60): `IfObjective n` (opcode 222) in library scripts 100/101/152 selects
  threat mode 12, the allied side and, on event 0x36, library script 170 (teleport to node 24, remove from the
  battle); establish which letter index 7 is and what the behaviour means in the battles that define it.
- **Objectives**: the `Objective:L,a,b` evaluation code (find where objective states are set and read in
  `GAMEF.DLL`), the meaning of the numbers for letters other than A/Z (roadmap 1.8), and battle end
  conditions.
- **Debrief link**: how results reach the debriefing (`BKTXT` 1001+/2001+ lines, "Mission was a success!",
  percentages such as "We slaughtered %d%% of the enemy").
- **Deliverables**: `J_missions.md` with a per-battle table (script roles, objectives, triggers, spawns) and
  the objective/victory rules.

### K: campaign progression and save games

Goal: the rules between battles and the save format (roadmap 4.4, milestone M6).

- **Experience**: how `s_Exp` and `s_kills` turn into improvements ("2x Experience Points Awarded", "%s
  Receive +1 Armour rating", `BKTXT` 5021/5022), which stats can rise and at what thresholds, and the
  leaders.
- **Economy**: payments, penalties and bonuses (`BKTXT` 5000–5042: initial/completion payment, villagers,
  buildings, wagons killed, Skaven killed bonus, bolt holes…), coffers, costs of hiring and of replacing
  casualties (`hired`, `s_pntval`?).
- **Troops and items**: joining and leaving troops (glue commands `addtroop`, `unitjoinmission`,
  `unitleavemission`, in `WND.DLL`, see `whshr/campaign.py`); magic item awards; `whoami` (persistent unit
  id?).
- **Files**: the roles and formats of `SAVE/ARMY.MRC`, `MARCH.MRC`, `PLAY.MRC`, `debrief.dbf`,
  `savegame.0` (~39 KB) and `savegame.5` (~316 KB); `autosave`.
- **Where to look**: mostly `WHSHR.EXE` (front end and glue interpreter: `exe_all.c`) and the debrief code of
  `GAMEF.DLL`.
- **Deliverables**: `K_campaign.md` (rules with evidence) and a save/army file format description suitable
  for `FORMATS.md`. A `whshr` reader with a check is optional, if the format is established.

### L: AI, pathfinding and visibility

Goal: what an engine needs for movement and AI beyond batch 2 (milestone M3).

- **Movement orders and routes**: `ExecuteGoto` `FUN_1002a950` ("point not reachable" → React 0x0E),
  waypoints `FUN_1002a6c0`, route finding around `Nav*` boundaries and objects; region masks
  (`FUN_10015c60`, `FUN_10015bd0`, `FUN_10015d20`; `bnd_*` flags); collisions between units and with
  `OBJECTS` (`FUN_100289d0`); formation changes and re-forming.
- **Visibility**: hidden units and spotting (`FUN_10016ca0`, events 0x1C/0x1D, unit flag `0x80000`),
  `SightEdge`/`ViewEdge` boundaries, and whether terrain height (`GRND.GD`) affects line of sight for spotting,
  shooting or magic.
- **AI decisions**: target selection and threat scoring (`DetectThreat` `FUN_10021f80`, `PickBestTarget`
  `FUN_10022280`, `FUN_10022330`, unit worth `+0x33E`), using the `AIQuery` catalogue from batch 3;
  army-level AI (is there any beyond per-unit scripts?); AI deployment.
- **Deliverables**: `L_ai_pathfinding.md` with pseudo-code of the route finder, collision handling, spotting
  and target selection.

## Batch 5 (optional)

### M: animation bytecode and game events → presentation

- **Animation bytecode**: the per-object scripts in `GAMEF.DLL` `.data` `0x100E70F0–0x100E86A8` (tables
  `0x100E8B88`, `0x100E86A8`, 59 opcodes at `0x100E7000`; R43). Name the opcodes and map animations
  (fire event 21, model death 23, `ApplyImpact` 52) to the sprite animation layout of `notes/animations.md`.
- **Presentation by event**: sound effect indices, battle music choice (`battle`, `tense`, `victory`…) and
  runtime palette per screen, by game event (roadmap 4.6; `React` sound table `0x100F5A10`, `SoundPlay`
  callers).
- **Deliverables**: `M_animation_events.md` and JSON tables for an engine.

## Not for agents

**Small leftovers**, better finished directly in a session:
- R35: placements outside the 17 × 17 grid;
- R41: remaining event codes;
- R44: unit flag `0x100`;
- R45: the fanatic spawn trigger;
- R52: static part of the never-ending spells;
- R54, R55: small magic questions, if not done by H;
- R36: a movement/pairing simulation.

**Wine checks** (`notes/game_rules.md` section 11.6):
- Do Flamestorm and Curse of Anraheir ever end?
- How often do AI wizards cast area spells?
- Do the Dragon and Orcs under "Ere We Go!" ever strike in close combat?
- Casualties on an armour-5 leader.
- How many models fight in practice.

**Engine decisions** for the project owner: whether to reproduce apparent original bugs (R11 armour rating 5,
R33 charging monsters keeping +1 S, "Ere We Go!" setting Initiative 20).
