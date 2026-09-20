# Data-driven campaign front end: architecture review and implementation plan

Decision record and implementation plan for replacing the current screen-specific campaign prototype with a generic interpreter of the original `WND.DLL` glue data.

The reverse engineering behind this decision is in:

- `notes/glue_keywords.md` — window-resource grammar and accepted fields;
- `notes/mission_selection.md` — window/context stacks, input, control panels and transitions;
- `notes/briefing_dialogue.md` — dialogue, speech, music and timing;
- `notes/campaign_tent.md` — `[BITMAP]` animation and `tentpos`;
- `notes/glue_portraits.md` — portrait tables and animation sequences;
- `notes/troop_selection.md` — the largest built-in campaign widget;
- `notes/campaign.md` — progression, economy, saves and debriefing;
- `notes/activity_results.md` — the activity completion channels and resume contracts;
- `notes/debrief_evaluation.md` — objective evaluators, `Result:` values and payment paths;
- `notes/builtin_widgets.md` — reinforcement, roster, save/load, options and marching-order widgets; and
- `notes/data_driven_audit.md` — the earlier audit of data accidentally copied into Python constants.

## 1. Decision

The campaign front end will be run as an interpreted program, not represented permanently as a graph of hand-authored Python scene classes.

`SceneMachine` remains the application-level coordinator for coarse modes such as the opening, the campaign front end, a movie and a battle. The original glue call stack, wait state, active windows and saved contexts belong inside one long-lived `GlueRuntime` hosted by a `GlueScene`.

The target division is:

```text
original installation                    mod packages
        |                                     |
        +---------- content repository -------+
                           |
              typed, lossless imported models
                           |
                     GlueRuntime
       program counter / calls / flags / waits / contexts
                           |
             +-------------+----------------+
             |                              |
       GlueRenderModel               external request
             |                    battle / movie / built-in UI
          GlueView                           |
             +--------------- result --------+
```

The campaign graph remains useful for reports, visualization and static validation. It becomes a projection of the lossless program model rather than the representation executed by the engine.

## 2. What is data and what must remain engine-owned

Data-driven does not mean moving every number into a content file. Values fall into three classes.

### 2.1 Original content data

Read these from `WND.DLL`, string DLLs, `BITMAP.DLL`, glue audio, army files and mission records:

- window positions and sizes;
- bitmap names, positions, frame ranges and timing fields;
- text ids, fonts, formats and colours;
- hotspot rectangles, hints, cursors, sounds and targets;
- portrait `index`, `bkindex`, `sequence` and `controlpanel` values;
- music, speech and movie cues;
- the order of commands and screens;
- mission names, briefings, battles, payments, forced/excluded units and dependency gates;
- campaign branches, roster changes and book unlocks; and
- initial values explicitly stored in the original data.

### 2.2 Original executable rules and tables

These are correctly implemented in code, but each must live in one documented compatibility module rather than being repeated by views:

- parser defaults, ignored-field behavior and command dispatch;
- window paint order, hit testing and fixed limits;
- timer, wait, pause and context-stack semantics;
- text wrapping, alignment, outline and format modes;
- font-slot, palette-slot and colour-name tables;
- transparency and palette-selection rules;
- portrait index and animation-sequence tables;
- control-panel art, label and action tables;
- portrait-frame and mission-list geometry;
- the `tentpos` coordinate table;
- built-in widget layouts and enable rules;
- caravan-mode to window-resource mapping;
- dynamic built-in resource-name rules such as `Skull<n>`; and
- original file/resource lookup conventions.

### 2.3 Open-engine policy

These are intentional engine choices and must not be presented as claims about original behavior:

- keyboard shortcuts added for accessibility;
- scaling and letterboxing policy;
- diagnostic handling of unknown commands;
- mod package precedence and schema versioning;
- cache policy; and
- whether apparent original bugs are reproduced or fixed outside vanilla-compatibility mode.

## 3. Findings in the current architecture

### 3.1 Scene replacement loses glue execution state

`whshr.scenes.SceneMachine` owns exactly one scene and a transition replaces it. The current campaign flow constructs `CaravanScene`, `MissionMapScene`, `BriefingScene` and `TroopSelectScene` objects. The original instead suspends a program while preserving its program counter, selected mission row, active windows and saved context.

Reconstructing a Python scene can preserve selected fields manually, but it cannot scale to the full glue state or faithfully serialize `STAX`-equivalent state.

### 3.2 The glue language is interpreted several times

The current code contains multiple lossy projections:

- `build_campaign_graph()` recognizes a small set of flow commands;
- `parse_mission_script()` recognizes a different mission-oriented subset;
- `_briefing_layout()` recognizes a briefing-oriented display subset;
- `CampaignState` manually advances selected graph actions; and
- scene handlers reimplement control-panel and hotspot transitions.

Every new screen therefore tends to add another special parser. Unsupported commands also disappear rather than remaining visible for validation.

### 3.3 Rendering is organized by named screen

`MainMenuView`, `CaravanView`, `MissionMapView` and `BriefingView` each contain part of the same glue renderer. They separately load resources, create quads, hit-test controls and reproduce layout rules. Built-in constants and per-resource data are mixed together.

The engine needs generic window primitives plus explicit renderers for the few executable-owned widgets.

### 3.4 Asset access bypasses the catalog

Campaign views open `BITMAP.DLL` directly, portrait helpers open `.FOL/.BOP/.PAL` directly, and campaign loaders repeatedly open `WND.DLL` and the string DLLs. The bitmap decoder is in `frontend/` and returns a pygame object.

As a result:

- resource-level assets do not participate in `AssetCache`;
- decoders are not fully headless;
- manifests do not describe the assets actually used;
- `SceneManifest.prefetch` is declared but not acted on; and
- a later mod cannot override a logical window or bitmap through the normal asset layer.

### 3.5 Durable campaign state and transient interpreter state are mixed

`CampaignState` is a useful summary of money, completion and the currently inferred flow/window. It is not a representation of the glue VM. Program counters, calls, flags, waits, current objects, selected rows, contexts and pending external operations need a separate runtime model.

### 3.6 External activities cannot return a result to the suspended script

A battle currently proceeds to `ResultScene`, which returns to the main menu. The mission glue program cannot suspend at `playgame*`, receive the battle result and continue through its debrief, movie, reward and caravan commands.

Movies, troop selection, books, save/load and options need the same request/result boundary.

## 4. Target components

All core types below remain stdlib-only and headlessly testable.

### 4.1 `GlueContent`

A repository of imported vanilla resources and later mod overrides:

```text
program(name) -> GlueProgram
window(name) -> WindowDefinition
string(table, id) -> str
bitmap(name) -> AssetId
font(slot) -> AssetId
speech(id) -> AssetId
music(name, device) -> AssetId
portrait(index, bkindex) -> portrait references
```

It loads each PE container once and indexes its named resources. Callers do not receive installation paths.

### 4.2 Typed imported model

Minimum types:

- `SourceLocation(resource, line)`;
- `GlueInstruction(command, argument, location)`;
- `GlueProgram(name, block_type, instructions)`;
- `WindowDefinition` with ordered bitmap, text, hotspot, portrait, MIDI, mission and include records;
- typed records for every block;
- `MissionRef(window, record_index)` as the stable identity; and
- an `UnknownField`/raw-field path so unsupported data is retained and reportable.

The importer must preserve order, duplicate statements and source locations. Analysis helpers may create dictionaries or graphs afterward.

### 4.3 `GlueRuntime`

Pure deterministic state machine containing:

- current program and program counter;
- call stack;
- glue true/false result and status mask;
- script variables such as `animseq`, `textlines` and `tentpos`;
- current mission reference and pending battle/debrief information;
- ordered active `WindowInstance` objects;
- original-style saved context stack;
- pending dialogue, animation and audio state;
- current wait reason; and
- durable `CampaignModel` reference.

Public operations should be small:

```text
start(program)
step_until_blocked() -> tuple[GlueEffect, ...]
tick(milliseconds) -> tuple[GlueEffect, ...]
handle(GlueInput) -> tuple[GlueEffect, ...]
resume(ActivityResult) -> tuple[GlueEffect, ...]
snapshot() / restore(snapshot)
```

The runtime must never import pygame or construct frontend scenes.

### 4.4 Effects and host boundary

Commands that leave the glue VM emit typed effects rather than directly importing another subsystem:

- `OpenWindow`, `CloseWindow`, `UpdateWindow`;
- `PlayMusic`, `StopMusic`, `PlaySpeech`, `StopSpeech`;
- `StartMovie`;
- `StartBattle`;
- `OpenTroopSelection`, `OpenBook`, `OpenSaveLoad`, `OpenOptions`;
- `Autosave`;
- `EnterCaravan`;
- `ShowDebrief`; and
- `EndGame`.

Effects that suspend execution carry a request id. The host later calls `resume()` with a typed result. This makes battle and built-in UI behavior testable without the frontend.

### 4.5 `GlueRenderModel` and `GlueView`

The runtime exposes presentation state, not pygame objects:

- ordered visible windows;
- resolved positions and palette selection;
- current bitmap frames;
- text runs and dialogue buffer;
- portrait frames and control panels;
- hotspots and their enabled/pressed states;
- mission-list rows; and
- cursor, tooltip and pause state.

One `GlueView` converts that model into GPU resources and translates raw input into `GlueInput`. Separate widget renderers are allowed for executable-owned controls such as the mission list, portrait control panel and troop-selection book.

### 4.6 Assets

Add resource-level logical identifiers, for example:

```text
vanilla:glue-program/flow-script-bp01
vanilla:glue-window/mainmenu
vanilla:bitmap/map
vanilla:string/brtxt
vanilla:font/glue2
vanilla:speech/b7010
vanilla:music/sighted-gm
vanilla:portrait/scri
```

PE bitmap decoding moves to a core module and returns width, height, indexed pixels and palette. Only `GlueView` converts it to an RGBA surface/texture. Dynamic assets discovered by the interpreter use runtime asset requests; `SceneManifest` remains useful for predictable coarse-scene assets but is not the complete dependency mechanism for an interpreted program.

## 5. Research gaps versus implementation gaps

Do not block implementation on low-value unknowns. Unsupported behavior must be explicit and source-located.

| System | Research status | Work still required | Blocks |
|---|---|---|---|
| Window grammar | Mostly established | Typed importer and all-resource validation | first generic window |
| Glue control flow | Established: `notes/glue_interpreter.md` (status/mask/mode, gosub/goto/return, waits, window and object commands, the four stacks, caravan entry, battle/movie/debrief/dialogue suspension and resumption); `python3 -m whshr glue-spec` reports command coverage | Implement it; open items are listed in §11 of that note | complete VM (unblocked) |
| Window/context stack | Structure and main actions established | Implement and serialize it | faithful navigation/save |
| Bitmap animation | General algorithm established | Implement data timing/frame resolution; runtime checks are polish | caravan/briefing animation |
| Portrait animation | Tables and sequences established | Implement shared animator; a few outlier overlays remain | animated dialogue |
| Dialogue | Layout and nominal timing established | Speech-progress coupling, queue behavior, ring buffer and click drain | faithful briefings |
| Music/speech | Lookup and main semantics established | Audio host/effects and pause/resume | campaign audio |
| Palette choice | Established: `notes/palette_selection.md` (one application palette; `palindex` pair on top-level open; embedded table for `-1` and full-screen pictures; system slots; verified 0 mismatches over 77 windows) | Headless `AppPalette` and runtime palette snapshots are implemented; route indexed rendering through it with `GlueView` (troop-screen icon palette remains an observation detail) | colour fidelity (unblocked) |
| Mission list | Substantially established | Built-in widget model and renderer | mission selection |
| Troop selection | Main model/layout established | Implement; research reinforcement window and a few edge flows | starting campaign battles |
| Books/options/save UI | Entry points known | Implement built-in adapters; some layouts remain | complete campaign shell |
| Debrief/economy | Established: `notes/debrief_evaluation.md` (evaluator table, `Result:` values and payment paths) | Integrate evaluator and payment state with campaign persistence | correct post-battle campaign |
| Save compatibility | Container and major state known | Runtime snapshot plus remaining `STAX` fields | original save import/export |

Priority research remains the register in `ROADMAP.md`. The evaluator research is complete; its integration is now implementation work. Unused ornament fields and machine-dependent historical timer speed do not block the VM.

## 6. Incremental implementation plan

Each phase must leave the existing battle path usable. Old campaign scenes may coexist temporarily, but new glue behavior must be implemented in the shared path.

A phase is not complete until its code, tests and affected documentation agree. The implementing agent must evolve the test suite with the production architecture, perform the documentation audit in §8, and remove or rewrite stale tests and design text as part of the same change.

### Phase 0 — Establish regression fixtures (implemented)

Deliverables:

- Choose a small representative fixture set: `MAINMENU`, `STARTCARAVAN`, one flow, one mission window, one briefing, one encounter and one mission script.
- Record the expected parsed structure and command trace from the real installation without committing proprietary content.
- Add an all-535-resource inventory test that reports block, command and field coverage.
- Mark commands as `implemented`, `recognized_noop`, `known_external`, or `unknown`; never silently drop an instruction.

Exit criteria:

- Every resource parses to EOF.
- Every statement has a source location.
- The coverage report is deterministic and unknown reachable commands fail a focused runtime test with a useful diagnostic.

### Phase 1 — Lossless typed importer (implemented)

Deliverables:

- Introduce the typed program and window models.
- Replace `parse_glue_lines()` consumers with projections over the typed model.
- Retain `build_campaign_graph()` as a projection so existing CLI reports continue to work.
- Preserve `MissionRef(window, record_index)` throughout campaign and briefing lookup.

Exit criteria:

- Existing graph/mission tests still pass.
- All 535 resources parse through the new importer.
- Round-trip diagnostic output preserves statement order and arguments.
- No new runtime code parses raw glue text itself.

### Phase 2 — Headless resource repository and asset cleanup (implemented)

Deliverables:

- Add `GlueContent` with one-time indexes for WND, bitmap and string resources.
- Move DIB decoding from `frontend/glue_bitmap.py` into a stdlib module.
- Add resource-level asset IDs/loaders for windows, bitmaps and string tables.
- Route portraits through the asset layer.
- Add dynamic cache acquisition; document ownership and release behavior.
- Either implement manifest prefetch or remove the unsupported claim until it exists.

Exit criteria:

- No campaign view opens an original file directly.
- Bitmap and window loading are testable without pygame.
- Repeated requests do not reparse the containing DLL.
- A synthetic namespace can override one bitmap and one window in a test.

### Phase 3 — Generic static window renderer

Deliverables:

- Build `GlueRenderModel` for `[POSITION]`, ordered `[BITMAP]`, `[TEXT]`, `[HOTSPOT]`, `[ANIM]`, `[MIDI]` and `[INCLUDE]`.
- Build reusable bitmap, text, hotspot, portrait-frame and control-panel renderers.
- Centralize executable-owned tables: colours, text formats, frame geometry, control panels, portrait index and `tentpos`.
- Render `MAINMENU` entirely from its window definition.

Exit criteria:

- The main menu has no resource names or rectangles in `MainMenuView`.
- A second unrelated window renders through the same code.
- Includes preserve original draw and hit-test order.
- Headless tests validate the render model; screenshot tests cover only final presentation.

### Phase 4 — Core glue VM and navigation (runtime foundation implemented)

Implement in vertical slices:

1. window/object commands and `setcurwindow`;
2. `gosub`, `goto`, `return`, conditionals and status flags;
3. `waitforrelease`, `waitforresume` and input release;
4. context push/pop/unwind built-ins;
5. mission selection and mission-record activation; and
6. caravan entry modes.

Deliverables:

- `GlueRuntime`, `GlueRuntimeState`, typed input/effects, status control flow, windows, waits, activity requests, context snapshots and deterministic instruction tracing are implemented headlessly.
- Snapshot/restore tests cover the current wait and activity boundary; remaining blocking states will be added with their hosts.
- `GlueScene` and `GlueView` hosting the runtime.

The compatibility scene flow is intentionally still the host.  The next vertical slice is to put the static renderer in front of this runtime, then route one complete caravan/map path through it; no existing campaign transition is removed before that path is manually testable.

Exit criteria:

- New Campaign reaches the first mission list by executing `StartCaravan` and `FlowScriptBP01` rather than constructing Python screen transitions.
- Caravan → map → caravan restores the same interpreter/window state.
- No special case names `FLOWSCRIPTBP01`, `STARTCARAVAN` or `MISSIONBP01WINDOW` in runtime control flow.

### Phase 5 — Shared animation, dialogue and audio

Deliverables:

- Generic `[BITMAP]` animator using script frame ranges and timing fields.
- Portrait animator using the established sequence tables.
- Dialogue buffer with `playtext`/`queuetoplaytext`, speech-on/off behavior, timing, click drain and pause.
- Music/speech effects with pause/resume/stop semantics.

Exit criteria:

- Candle, lamp, tent, trail and briefing overlays use one bitmap animator.
- Every briefing uses one dialogue implementation.
- Speaker animation is selected by `applyseq`, not by briefing-specific code.
- Headless timing tests cover voiced and unvoiced dialogue.

### Phase 6 — External activities and campaign resumption

Deliverables:

- Request/result protocol for movies, battles and built-in screens.
- Battle result returned to the suspended mission program.
- Movie completion returned to the suspended program.
- Troop-selection model and view from `notes/troop_selection.md`.
- Mission commitment, roster and coffers updated only at the correct original step.

Exit criteria:

- A selected mission can run briefing → troop selection → battle → result/debrief → movie/caravan without returning to the main menu.
- Aborting briefing or troop selection restores the expected saved context.
- Tests inject fake movie/battle results without creating a frontend.

### Phase 7 — Remaining built-in widgets and save support

Deliverables:

- Debrief and economy evaluator integration.
- Books, reinforcement selection, save/load and options adapters.
- Runtime snapshot in the open-engine save format.
- Original save import mapped into `CampaignModel` and compatible glue runtime state where established.

Exit criteria:

- Every reachable vanilla campaign glue command is implemented or an intentional documented no-op.
- A save at a map, briefing wait and post-battle flow resumes deterministically.
- Full campaign-flow tests can replace battle simulation with predetermined results and reach each ending.

### Phase 8 — Remove compatibility scaffolding

After equivalent paths pass:

- remove screen-specific campaign transitions from `campaign_scenes.py`;
- remove `MainMenuView`, `CaravanView`, `MissionMapView` and `BriefingView` or reduce them to generic widget components;
- delete the obsolete briefing view in `frontend/menu_view.py`;
- make graph builders and briefing transcript helpers projections of `GlueContent`; and
- update architecture documentation and tests to name `GlueScene` as the campaign owner.

## 7. Testing strategy

Use three complementary levels.

### The test suite migrates with every phase

Testing is implementation work in every phase, not a final stabilization task. An agent changing a glue or campaign subsystem must in the same change:

1. add focused tests for each new typed model, parser rule, runtime instruction, effect, renderer rule or host adapter;
2. move behavioral coverage from named-screen tests into shared glue/runtime tests as the generic implementation takes ownership of that behavior;
3. retain end-to-end tests for representative screens as integration fixtures, without making their resource names or layouts the architecture under test;
4. rewrite tests whose assertions encode the outgoing screen-specific design;
5. remove obsolete screen-specific tests when their production classes or paths are removed, unless they still verify user-visible behavior through the new generic path;
6. keep reusable battle, asset, campaign-model and decoder tests independent of the glue migration; and
7. run the affected focused tests plus the complete suite before declaring a phase complete.

Tests must not preserve deprecated classes, compatibility helpers or stale architecture solely to keep old assertions passing. Preserve required behavior, then express it against the current public boundary. When a temporary compatibility path must remain between phases, label its tests as transitional and delete or migrate them in the phase that removes that path.

### Importer conformance

- all 535 resources parse;
- every byte/line is classified;
- include cycles and missing resources report their chain;
- accepted-but-ignored fields are tested per block type; and
- command/field coverage cannot regress silently.

### Headless runtime behavior

- instruction trace for representative scripts;
- calls, returns and conditional branches;
- waits and resumptions;
- context push/pop with selected mission row and active windows;
- animation frame progression at boundary ticks;
- voiced/unvoiced dialogue;
- mission visibility, money and completion; and
- snapshot/restore equality.

Prefer tests using synthetic glue resources. Installation-backed checks may verify aggregate counts and hashes but must skip cleanly when the game is absent.

### End-to-end adapters

- fake host: deterministic movie, troop and battle results;
- real runtime frontend: screenshots and input translation;
- optional Wine comparisons only for open questions that block compatibility; and
- a campaign traversal test that explores branches with predetermined outcomes.

## 8. Guardrails

- Do not add another screen-specific glue parser.
- Do not key a campaign item by battle filename; use `MissionRef`.
- Do not discard unknown statements during import.
- Do not let core decoders return pygame/zengl objects.
- Do not let views open installation files.
- Do not encode original English strings as fallbacks.
- Do not move executable-owned compatibility tables into content merely to call them “data-driven.”
- Do not design the public mod format as a direct serialization of the original glue VM. Vanilla glue is a compatibility input; the normalized mod contract remains a later, versioned interface.

### Documentation is part of the change

Every agent implementing a phase or rewriting one of these systems is responsible for finding all documentation and design text affected by the change. Before considering the work complete, the agent must:

1. search `README.md`, `ROADMAP.md`, `FORMATS.md`, `docs/`, `notes/`, `CLAUDE.md`, nearby module docstrings and relevant tests for the old component names, architecture and behavior;
2. update the authoritative document with the current design and verified behavior;
3. remove stale sections, obsolete proposed designs and instructions that no longer apply;
4. merge still-useful facts into the current section instead of retaining a historical account beside it;
5. update or remove links that point to deleted or superseded sections; and
6. include the documentation audit in the phase's exit criteria and review summary.

Design documents describe the architecture contributors should build now. They must not accumulate “old approach”, “superseded plan”, migration-history or changelog passages unless that history is required to explain a still-active compatibility constraint. Git history is the record of discarded designs.

This requirement applies incrementally: an agent need not rewrite unrelated documentation, but owns every stale reference made obsolete by its change.

The same ownership rule applies to the test suite under §7: affected tests must describe the current architecture, and outdated screen-specific coverage must be migrated or removed rather than retained as implementation history.

## 9. Current implementation boundary

`whshr.glue` is the stdlib-only implementation of Phases 0–1. It imports all 535 resources into `GlueProgram` or `WindowDefinition`, retains the normalized statement stream with `SourceLocation`, represents every window block with a typed ordered record, keeps duplicates and `UnknownField` diagnostics, and assigns every mission a `MissionRef(window, record_index)`. `coverage_report()` deterministically classifies every shipped block, command and field; `python3 -m whshr check <WARFB>` rejects an incomplete or newly unclassified inventory.

The campaign graph, window UI projection, mission-script report and briefing layout consume those typed resources. `parse_glue_lines()` remains only as a compatibility projection and has no production consumers.

`whshr.glue_content` implements Phase 2. One shared lazy `GlueContent` instance indexes WND programs/windows, string tables and bitmap resources, caches decoded indexed bitmaps and portraits, and supports non-destructive resource/bitmap/string overlays. The catalog exposes dynamic `glue-window`, `glue-program`, `bitmap` and `string` IDs; `AssetCache.acquire()`/`release_owner()` provide ownership for future runtime-discovered assets. Campaign views receive decoded content and no longer open installation files. `SceneManifest.prefetch` remains an inactive hint, documented as such until a measured scheduler exists.

The next implementation slice is Phase 3: add the headless `GlueRenderModel`, centralize the remaining compatibility tables, and make `MAINMENU` plus one unrelated window render through shared primitives. Runtime behavior remains on the existing campaign scenes until the generic renderer and VM replace it in later vertical slices.
