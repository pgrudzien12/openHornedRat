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

- [ ] **GEI7b — Troop selection view (P0 + P1).** Render the real regiment-select and
  marching-order pages (`notes/troop_selection.md` §2-§5): background, rows, buttons, status
  text/colours, and P1 reordering (click-to-pick-up/drop, not live drag-and-drop).

- [ ] **GEI7c — Bankruptcy page (P5).** Render `notes/troop_selection.md` §7 and route the forced
  regiments over-budget case to it at open.

- [ ] **GEI7d — Roster book.** The separate "Army Records" window opened by Ctrl+click during
  selection (`notes/troop_selection.md` §8): stat/info pages, hire/fire, reinforcements. Shared
  later by the caravan's own book hotspots (part of GEI9's deferred books).

- [ ] **GEI7e — Durable roster and marching order.** Write `ARMY.MRC`/`MARCH.MRC` and persist
  reinforcements instead of only updating in-memory `CampaignState`; belongs with GEI14's save/load
  persistence model rather than GEI7's in-memory commit.

- [ ] **GEI8 — Debrief activity.** Present `StartDebrief`, apply the payment and result effects,
  and resume the requesting Glue runtime.

- [ ] **GEI9 — Generic post-mission caravan modes.** Route `EnterCaravan` to the requested
  generic caravan window while retaining the parked runtime. Implement the campaign-required
  modes first: post-mission, resume, and recruitment. Add books, options, save/load UI, and
  dialogue close-ups only when their underlying activities exist.

- [ ] **GEI10 — Campaign mission progression.** Apply `depend` and `inactivedepend` to generic
  mission rows; advance the campaign for release and replacement paths; rebuild the offered list
  after mission commitment.

- [ ] **GEI11 — Remaining scene boundary effects.** Route `EndGame` to the main menu and retain
  battle logging and seed configuration when Glue starts a battle.

- [ ] **GEI12 — Remaining campaign commands.** Implement `addunit`, `cash`, bonus counters,
  book flags, `testmission`, `testobjective`, and `gomissionselect`. Explicitly reject reachable
  commands that remain unsupported.

- [ ] **GEI13 — Remaining interpreter behavior.** Complete `replacescript`, mission release,
  remaining built-in object behavior, and the documented deferred `goto` behavior.

- [ ] **GEI14 — Persistent save/load.** Define save/load semantics, then replace the in-memory
  autosave snapshot with durable persistence.

- [ ] **GEI15 — Retire legacy map and briefing code.** Delete `MissionMapScene`,
  `MissionMapView`, `BriefingScene`, and `BriefingView` after their generic equivalents cover
  every live entry, exit, and return path.

## Implementation findings

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

## Working rules

- Implement tasks in checklist order unless a dependency is explicitly changed in this document.
- Add focused tests and verify the real flow before checking off a task and committing it.
- Delete a replaced scene, view, state projection, and dedicated tests in the same task once no
  live caller needs them.
- Do not retain compatibility wrappers, deprecated routes, or historical-decision comments.
- Keep save/load deferred until its persistence model is defined; autosave must still occur at its
  interpreter-defined points.
