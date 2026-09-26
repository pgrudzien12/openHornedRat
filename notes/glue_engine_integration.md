# Generic Glue engine integration

## Contents

- [Ordered implementation checklist](#ordered-implementation-checklist)
- [Implementation findings](#implementation-findings)
- [Working rules](#working-rules)

This checklist is the implementation order for the generic `GlueScene` / `GlueView` campaign path.
Each identifier is permanent: mark its checkbox when its stated outcome is verified; do not move or
renumber later work.

## Ordered implementation checklist

- [x] **GEI1 — Generic window presentation.** Render Glue windows from game resources: bitmaps,
  text, hotspots, portraits, dialogue timing, music, control panels, static bitmap animation, and
  runtime-created animated objects.

- [x] **GEI2 — Campaign runtime boundary.** Give `GlueRuntime` access to campaign coffers,
  army/march membership, reinforcements, selected mission identity, taken-mission storage, and an
  in-memory autosave snapshot. Implement `testforunitinarmy`, `testforunitinmarch`, `addcash`,
  `iftrueaddcash`, `addtroop`, `unitjoinmission`, `unitleavemission`, mission selection, and
  autosave through that boundary.

- [x] **GEI3 — Generic mission selection baseline.** Render `[MISSIONWINDOW]` rows, select the
  first available row by default, wrap its `BRTXT` title, show payment only when both `cash`
  payment values exist, and enter the selected generic briefing.

- [x] **GEI4 — Generic briefing and battle handoff.** Render generic briefings, preserve the
  parked map while a nested briefing is active, start a configured battle, and resume the same
  `GlueScene` after battle completion. Accept deliberately starts the battle directly until GEI7.

- [x] **GEI5 — Initial generic caravan.** Start New Campaign in `STARTCARAVAN`; render its
  animated candle, lamp, book, and eyes sprites, BRTXT hover hints, mission-count-dependent
  `CarScroll` records, mission entry, and Abort-to-menu. Delete the replaced caravan scene, view,
  state projection, and tests.

- [x] **GEI5a — Surface interpreter diagnostics.** Drain `Diagnostic` effects in the
  frontend (currently dropped by `glue_view.py`'s `take_effects` loop) and log them so an
  unsupported command, invalid argument, or stack fault during a live session is visible
  instead of silently swallowed.

- [x] **GEI6 — Reusable movie activity.** Generalize the working A1 playback into a reusable
  movie scene/view. Route `StartMovie`, support its fade flag, and resume the requesting Glue
  runtime with an `ActivityResult` when playback ends or is skipped.

- [x] **GEI7 — Troop selection core flow.** Replace briefing Accept's direct-battle route with a
  headless `TroopSelection` model (`notes/troop_selection.md` §10) and `TroopSelectionScene`:
  load the company roster (GEI7a), compute P0 rows/pricing/limit and P1 marching order, and on
  Done commit costs, roster flags and mission-taken state to `CampaignState`, then launch the
  selected battle or continuation. Present it with a placeholder view (scoped down from the full
  spec; GEI7b-GEI7e below cover the deferred parts).

- [x] **GEI7a — Company roster loading.** Give `CampaignState` an initial unit roster: parse
  `STRTARMY.MRC` for a new campaign (`whshr/roster.py`, `notes/campaign.md` §3.1/§4.5) into unit
  records with stats, price-per-model, `forHire`, and `whoami`, keyed the same way
  `testforunitinarmy`/`testforunitinmarch` already key `army_units`/`march_units`. Prerequisite
  for GEI7's pricing and forced/excluded regiment rules.

- [x] **GEI7b — Troop selection view (P0 + P1).** Render the real regiment-select and
  marching-order pages (`notes/troop_selection.md` §2-§5): background, rows, buttons, status
  text/colours, and P1 reordering (click-to-pick-up/drop; the picked row following the cursor
  visually is GEI7f).

- [x] **GEI7c — Bankruptcy page (P5).** Render `notes/troop_selection.md` §7 and route the forced
  regiments over-budget case to it at open.

- [x] **GEI7d — Selection roster book.** The separate "Army Records" window opened by Ctrl+click
  during selection (`notes/troop_selection.md` §8): stat/info pages and the no-coffers-change
  Hire/Fire variant. Caravan book hotspots, reinforcement controls, and durable roster writes
  remain deferred to their separately scoped work.

- [x] **GEI7e — Durable roster and marching order.** Write `ARMY.MRC`/`MARCH.MRC` (notes/troop_selection.md
  §5.3 points 3, 5) on troop-selection Done. Reinforcements still have no standalone-file home in the
  original (only `savegame.N`'s `RMYI` chunk carries them) and stay in-memory pending GEI14's writer.

- [x] **GEI7g — Caravan roster book, hiring and reinforcements.** (issue #145) The caravan's `ArmyBook` and
  `HireOnlyArmyBook` hotspots open the Army Records screen on the caravan's company; hiring in the paying
  variant charges the coffers, and the reinforcement sub-window (notes/builtin_widgets.md §2.4) is available in
  every hire-capable variant. Regiments join the company from a master roster (see the findings). Persisting the
  reinforcement pool is still GEI14's.

- [x] **GEI7f — Troop sel ection view carried-item tracking.** The picked-up P1 regiment visually
  follows the cursor (`notes/troop_selection.md` §5.2: "the strip... follows the cursor"). The
  interaction itself stays click-to-pick-up/click-to-drop, matching the original's own hint text
  (`BRTXT 315`: "click to pick up, click again to drop") rather than switching to a continuous
  mouse-button-held drag, which the spec never documents.

- [ ] **GEI8 — Debrief activity.** (issue #123) Present `StartDebrief`, apply the payment and result effects,
  and resume the requesting Glue runtime.

- [x] **GEI9 — Generic post-mission caravan modes.** (issue #120) Route `EnterCaravan` to the requested
  generic caravan window while retaining the parked runtime. Implement the campaign-required
  modes first: post-mission, resume, and recruitment. Add books, options, save/load UI, and
  dialogue close-ups only when their underlying activities exist.
  *Implemented:* the request pushes the parked script, opens the mode's caravan window (`select`, `resume`,
  `recruit*`, `info<letters>`; unknown names resume at once) and the hotspot's own `res` decides the exit
  (`UnwindMission` finishes the script and releases the mission on the map, `PopAndResume` resumes it);
  other hotspots stay inert with a diagnostic. `select`/`resume` open their `...WithRecruit` window when
  `CampaignState.recruitable()` holds (GEI7g: an unhired regiment for hire waits in the company; reinforcements that
  replace losses play no part; 🟡 the original's exact test is not recorded), falling back to the plain
  window when the installation lacks the variant. Dietrich speaks only when clicked (the `DietrichSpeech` hotspot's `clickres` lines, in red; `clickrescnt` counts the
  lines after the first); the caravan is the current window while open so its text is drawn. Spoken lines (click speech and script
  `playtext`) now play their recording (`B<id>.WAV`, `whshr/speech.py`): the runtime emits `PlaySpeech` per line when speech
  is on, the view plays it and a new line replaces the previous clip. The originals' RIFF size fields are wrong, so the PCM is
  rewritten with correct headers. Text still advances on its own timer, not on the clip length (a middle line can be cut
  short by up to about 0.3 s; the notes say the original follows the audio).

- [x] **GEI10 — Campaign mission progression.** (issue #124) Apply `depend` and `inactivedepend` to generic
  mission rows; advance the campaign for release and replacement paths; rebuild the offered list
  after mission commitment.

- [ ] **GEI11 — Remaining scene boundary effects.** (issue #125) Route `EndGame` to the main menu and retain
  battle logging and seed configuration when Glue starts a battle.

- [ ] **GEI12 — Remaining campaign commands.** (issue #126) Implement `addunit`, `cash`, bonus counters,
  book flags, `testmission`, `testobjective`, and `gomissionselect`. Explicitly reject reachable
  commands that remain unsupported.

- [ ] **GEI13 — Remaining interpreter behavior.** (issue #127) Complete `replacescript`, mission release,
  remaining built-in object behavior, and the documented deferred `goto` behavior.

- [ ] **GEI14 — Persistent save/load.** (issue #128) Define save/load semantics, then replace the in-memory
  autosave snapshot with durable persistence.
  **Done so far (player saves):** the Load/Save dialog of `notes/builtin_widgets.md` §6 (`whshr/load_save_scene.py`,
  `whshr/frontend/load_save_view.py`), reached from the main menu (Load) and the start caravan (Save), and the engine's own
  save format (`whshr/savegame.py`). One JSON file per slot (`slot0.json`..`slot5.json`) in the save directory, written
  atomically (temporary file, then rename). It stores the *campaign* only: flow chain and step, mission window, taken and
  completed missions, coffers, army/march sets, reinforcements, book pages, bonus counter, objective results and the company
  as `.MRC` text (experience, hired flag and model counts included). A load rebuilds a fresh campaign of the installation,
  overwrites it with the saved fields and opens the start caravan; the flow chain replays from there, exactly as when
  the caravan's map button is used (`GlueScene._map_program`). Not saved: the interpreter's window/script stacks
  (the original resumes a parked script; the engine always resumes at the caravan).
  **Still open:** `autosave:`/`testmission` still keep only the in-memory snapshot and never write slot 5 ("Last Game"),
  so the Load dialog lists that slot but it stays empty; saving from a script-launched caravan
  (`GlueScene._leave_caravan`) is wired but resumes at the start caravan, not at that caravan; the caption texts of the
  dialog ("Empty", "Enter Save Description", default description) are engine-supplied (`PROVISIONAL` in `load_save_scene.py`).

- [ ] **GEI15 — Retire legacy map and briefing code.** (issue #129) Delete `MissionMapScene`,
  `MissionMapView`, `BriefingScene`, and `BriefingView` after their generic equivalents cover
  every live entry, exit, and return path.

## Implementation findings

- GEI10: the offered mission rows of a window are computed per mission record (`MissionRef`), never by
  name id across windows: the same ids (601, 615, 628...) recur in many windows. The map view, the
  runtime's mission selection and the flow advance all use one predicate (taken hides; `depend` needs
  the named same-window mission taken; `inactivedepend` needs it not on offer). Only four shipped
  windows carry gates (`MISSIONENWINDOW`, `MISSIONLWINDOW`, `MISSIONL3WINDOW` whose gate names a mission
  outside the window, `MISSIONSZWINDOW`). A mission is taken at troop selection's Done, so aborting from
  the briefing or troop selection leaves it offered; after commitment the list is rebuilt and the
  selection moves to the first offered row. Walking every flow completes without an empty map; a chapter's
  last window ends with the flow script running on.

- The initial caravan is a top-level generic window; its mission hotspot starts a flow program.
  Later caravan transitions are interpreter activities and need GEI9 rather than another
  entry-point shortcut.
- Static `[BITMAP]` animation fields are executable presentation data. Rendering must respect
  `animstartframe`, timing, and loop fields instead of loading only the base bitmap.
- `CarScroll` records use `depend` as a count gate against currently available missions. This is
  separate from the mission dependency rules implemented in GEI10.
- A mission title is not the briefing resource name: `set:res` supplies the `BRTXT` title while
  `res` / `script` supplies the briefing program.
- Mission payment is optional. A `cash` record without both payment values produces no payment
  line.
- `--glue-program` starts only `[RUN]` resources and does not synthesize the parent windows or
  state a continuation script expects. A black screen can therefore mean missing context rather
  than missing rendering. A `...WINDOW` resource is not a standalone program.
- Returning from a battle or nested briefing must reuse the existing `GlueScene`; recreating it
  loses its selected mission, windows, and interpreter position.
- GEI7's core flow is entirely front-end-owned (notes/troop_selection.md §9: "nothing on this
  screen is placed by WND.DLL scripts"), so it is not a `GlueRuntime` activity/effect like
  `StartBattle`/`StartMovie`. `GlueScene.handle()` routes Accept directly to a
  `Transition(TroopSelectionScene(...), ...)` instead, and `TroopSelectionScene` calls the new
  `GlueScene.start_battle(battle)` (queues a `StartBattle` effect on the parked scene) before
  transitioning back to it; `SceneMachine._start_glue_battle` then picks it up on the next tick,
  same as any other queued battle.
- A `GlueScene` with no `CampaignState` (development `--glue-program` runs, and tests) has no
  company either: `TroopSelectionScene` mirrors the original's own mode-0 rule (notes/troop_selection.md
  §1.1, "if the file cannot be loaded... skip the screen and run Done immediately") and starts the
  battle directly rather than crashing or silently doing nothing.
- GEI7b is a native `TroopSelectionView` (`whshr/frontend/troop_selection_view.py`), registered
  in the scene-view registry rather than a `GlueView` extension: TroopBook is a built-in screen,
  not a WND.DLL resource. It uses the BOOK palette and runtime `BITMAP.DLL`/`BKTXT`/`BRTXT` resources.
  P0/P1 use body font slot 2, while the heading font remains confined to later debrief/bankruptcy
  pages. P0 uses the model's canonical price/status/selection state;
  P1 uses click-to-pick-up and click-to-drop events. `TroopSelectionScene` owns P0 paging and the
  P1 viewport/reorder state, keeping the view presentation-only. `Regiment` now retains the
  weapon, armour, and banner fields from the runtime-loaded MRC; the view resolves the two text
  ids and resolves a banner resource through the game's banner sprite-name table before rendering
  its documented second-frame (16×24) marker. P1's documented scroll zones advance the owned viewport at 250 ms while held, and only
  the row currently under a picked-up regiment uses the drop-target scroll art.
- `whshr/roster.py`'s `load_company()` takes an optional pre-built `roster` mapping so its MRC-merge
  logic is testable without a real `WHSHR.EXE` PE image; only `static_roster()` (the RMYI reader)
  needs the real installation, consistent with `rules.py`'s untested-at-unit-level `PeImage` reads
  (verified instead by `scripts/roster_check.py` against the real game, notes/campaign.md §4.5).
- `IntroScene`/`IntroView` (boot-time A1 playback) generalized to `MovieScene`/`MovieView`
  (`whshr/campaign_scenes.py`, `whshr/frontend/movie_view.py`): a `MovieScene` completes into
  either a fixed `successor` (boot flow) or a parked `glue_scene` resumed with an
  `ActivityResult` (glue `playmovie`). `SceneMachine._start_glue_movie` (`whshr/scenes.py`)
  routes a `GlueScene`'s queued `StartMovie` effect the same way `_start_glue_battle` already
  routed `StartBattle`.
- GEI7c uses the same runtime-loaded `TroopBook` bitmap and BOOK palette as P0/P1.  P5 centres
  `BKTXT 601` at `50 + 8H` in glue font slot 4 and places the two formatted monetary messages
  beneath it in slot 2.  The displayed available coffer amount is `coffers + prepaid`, matching
  the documented bankruptcy comparison and P0's coffer line; the required amount is the price of
  the still-living forced regiments.  P5 creates only Done.  Until the specification resolves its
  campaign-ending destination, Done returns to the parked `GlueScene`, with no commitment or
  battle effect.
- GEI7d adds `ArmyRecordsScene` and its native `ArmyRecordsView`, using `ArmyBook`, palette 9,
  glue body/heading fonts, named regiment pictures, and named BKTXT RCDATA descriptions from the
  original installation at runtime. The roster merge retains `s_Exp` separately from `s_pntval`,
  so the book's Experience line does not reuse the rank/points value; its selection-mode cost line
  always shows the documented price and retainer pair. Ctrl-click routes a valid displayed P0 or P1 row to that
  scene without performing the row action. The book parks and later resumes the same selection
  scene, so its P0 page and P1 ordering state survive. Its Hire/Fire action changes only the
  `TroopSelection` model: `forHire` controls enablement, hire appends a selection when capacity
  permits, fire deselects, and a full selection leaves a newly hired regiment unselected without
  a refusal sound or coffer change. Done keeps the in-memory changes; Abort restores the book-open
  hired snapshot and removes any cancelled hire from the selection. Caravan economy and
  reinforcement UI were not added here (GEI7g); ARMY/MARCH file writes are GEI7e.
- GEI7g (issue #145): `CampaignState` now carries a **master roster** (`master`, the fresh-campaign content of
  `SCRIPT/MAXARMY.MRC`, i.e. the original's `PLAY.MRC`) next to the company (`ARMY.MRC`). Without it there was
  nothing to hire: the starting company holds two regiments. `addunit` flags a regiment and the next caravan
  request (any `gocaravan`) copies it in, hired at once unless its roster row says *for hire* (then it waits in
  the recruit book, `hired = 0`; 🟡 the exact moment of the merge is inferred from notes/campaign.md §2.4);
  `unitjoinmission` copies a regiment in (hired) and adds it to the march, `unitleavemission` removes it.
  Leaving a recruit caravan by `PopAndResume` drops unhired regiments and clears unused reinforcements;
  troop-selection Done does the same (notes/troop_selection.md §5.3 point 5).
  The caravan book is a `RosterBook` model (pure, `whshr/roster_book.py`); the selection book keeps using
  `TroopSelection`; both expose the same small interface (`BookModel`) and share the `ReinforcementLedger`
  (`whshr/reinforcements.py`). Done applies hired flags, model counts, the pool, and (paying variant) the coffers
  and the marching list to the campaign and rewrites the company file (unhired regiments included, `hired=0`);
  Abort applies only the coffers of a paying book (the documented quirk). Two engine choices the specification
  leaves open: Abort also **reverts** men taken as reinforcements and the pool (the notes only say the hired
  flags are restored), and the offer counts only present models because wounded/away men are not tracked yet
  (GEI8). The paying variant's marching list starts as the always-forced commander only and Done rewrites the
  march from it, as documented; troop selection rebuilds the selection anyway.
- GEI7e added `script.write()`, a generic inverse of `script.parse()` (any `.BTS`/`.MRC` node
  tree back to text), rather than a roster-specific serializer: round-tripped against all 87
  shipped `.BTS`/`.MRC` files plus the real `SAVE/ARMY.MRC`/`PLAY.MRC`/`MARCH.MRC`, byte-for-byte
  semantic equality (field order is normalised; only decorative comments other than a section's
  own label, already discarded by `parse()`, are not reproduced). `roster.Regiment` keeps the raw
  `addunit` node (`raw`) precisely so a write reuses that verbatim node (leader block, spells,
  items, sprites, AI script, deployment `x`/`y`, all of it) with only `set:hired` replaced,
  instead of reconstructing a unit from the trimmed fields `Regiment` exposes for display — the
  narrower model would silently drop everything it doesn't track. `CampaignState.commit_troop_selection`
  calls `roster.write_company`/`write_march` only when `self.save_dir` is set, so tests and other
  save-dir-less callers stay a pure in-memory commit.
- Engine saves never go into the original installation (owner decision, not a spec finding): they
  write to the engine's own directory (`SceneAssets.save_dir`: `--save-dir`, else `OSH_SAVE_DIR`, else the
  per-user data directory of the platform, `whshr/user_dirs.py`), threaded from `app.run`/`game.scene_context` down to
  `CampaignState.save_dir`. The engine keeps no save-format compatibility promise toward the
  original either; the `.MRC` text grammar is reused in `write_company`/`write_march` because it
  is already required for reading, not as a compatibility commitment (CLAUDE.md "Engine rule:
  saves are the engine's own, not the original's").
- GEI7f, first version: including the raw pointer in `refresh()`'s diffed state made every
  `MOUSEMOTION` event trigger a full `_p1()` rebuild (every visible row's bitmaps/labels
  recreated as new GPU textures) while dragging, which dropped FPS to ~0. Fixed by decoupling the
  carried regiment from that rebuild: `_build_carried_regiment` draws it once, at `y=0`, into a
  separate `carried_quads`/`carried_labels` pair, so the stored position *is* an offset from the
  row's own origin; `draw()`'s new `_draw_carried` repositions those same GPU objects from the
  live pointer every frame (cheap: no texture recreation, no `refresh()`). `refresh()` no longer
  considers the raw pointer at all — only `hover_march_index` (still row-granular, for the
  drop-target highlight) triggers a rebuild, at the same cadence as before GEI7f.
- P1 pick-up/drop also moved from `MOUSEBUTTONUP` to `MOUSEBUTTONDOWN`, matching notes/troop_selection.md
  §5.2's own wording ("pressing on a row picks that regiment up"; drop is the symmetric second
  press). P0's toggle and both pages' Ctrl+click book-open stay on release; only march_order's
  plain row click moved, so the `MOUSEBUTTONUP` row loop no longer has a pickup/drop branch (it
  would otherwise double-fire on the release of the same click).

## Working rules

- Implement tasks in checklist order unless a dependency is explicitly changed in this document.
- Add focused tests and verify the real flow before checking off a task and committing it.
- Delete a replaced scene, view, state projection, and dedicated tests in the same task once no
  live caller needs them.
- Do not retain compatibility wrappers, deprecated routes, or historical-decision comments.
- Keep save/load deferred until its persistence model is defined; autosave must still occur at its
  interpreter-defined points.
