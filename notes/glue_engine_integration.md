# Integrating the generic glue engine, and retiring the bespoke campaign scenes

## Contents

- [Current state: two parallel pipelines](#current-state-two-parallel-pipelines)
- [The two gaps that block a real switch](#the-two-gaps-that-block-a-real-switch)
- [Proposed order of steps](#proposed-order-of-steps)
- [Open questions](#open-questions)
- [Implementation milestones](#implementation-milestones)
- [Migration rules](#migration-rules)

Plan record: where the generic `GlueScene`/`GlueView` pipeline stands after the M1-M5 work
(portraits, dialogue, music, control panel), what is missing before it can replace the older
hand-rolled campaign scenes, and the order of steps to get there. Not a status report of finished
work — see `FORMATS.md` and `ROADMAP.md` for that.

## Current state: two parallel pipelines

**Old, bespoke pipeline** (`whshr/campaign_scenes.py` + `whshr/frontend/caravan_view.py` /
`mission_map_view.py` / `briefing_view.py`):

```text
MainMenuScene -> CaravanScene -> MissionMapScene -> BriefingScene -> TroopSelectScene
```

Each scene hand-rolls its own slice of glue behaviour. `BriefingScene` has its own
`characters_visible`/`dialogue_elapsed` dialogue-typing loop and its own portrait handling,
duplicating what the generic runtime now does properly. `TroopSelectScene` is a bare stub with no
logic. This pipeline reads campaign state (coffers, missions, roster) from `CampaignState`
(`whshr/campaign_state.py`), which is real, useful, data-driven, and **not** a duplicate — it stays.

**New, general pipeline** (`whshr/glue_scene.py` + `whshr/frontend/glue_view.py`): interprets any
`[RUN]` glue program generically — dialogue, portraits, panels, music, animation, all read from
`WND.DLL`/`BITMAP.DLL`/`BRTXT` at runtime. Far more complete for what it covers than the bespoke
scenes. But it is currently reachable only through the `--glue-program` development shortcut
(`python3 -m whshr engine <installation> --glue-program <NAME>`); nothing wires it into the real
menu flow, and `GlueRuntime` does not touch `CampaignState` at all - `GlueRuntime.campaign` is
stored in `__init__` and never read anywhere else in the module.

`whshr/controlpanel.py` (frame/button geometry and BRTXT label ids) is already shared by both
pipelines and does not need touching.

## The two gaps that block a real switch

1. **Campaign state hookup.** `GlueRuntime` needs to read and write a `CampaignState` (or an
   equivalent): coffers spent on Accept, mission-taken flags, roster/army membership checks
   (`testforunitinarmy`, `testforunitinmarch`), autosave. All currently unimplemented.
2. **Cross-scene effects.** `GlueRuntime` already emits `StartBattle`/`StartDebrief`/
   `EnterCaravan` effects correctly (same shape as the `PlayMusic` effect that turned out to be
   silently unconsumed until this session's M4 work), but nothing outside `GlueView` turns them
   into a real scene `Transition` (to `BattleScene`, `ResultScene`, ...) and feeds the outcome back
   as an `ActivityResult`. Same *kind* of bug as the music one, one architectural layer up (the
   scene machine rather than one view).

## Proposed order of steps

1. **Wire cross-scene effects.** Add the effect -> `Transition` translation (likely in
   `SceneMachine` or a thin adapter next to it), so a `GlueScene` reaching `StartBattle` actually
   enters `BattleScene` and resumes correctly on return. Verify end to end with a mission script
   that has a real battle.
2. **Hook `CampaignState` into `GlueRuntime`.** Implement `testforunitinarmy`/
   `testforunitinmarch`, coffers on Accept, mission-taken tracking, autosave, using the existing
   `CampaignState`. The largest single chunk of new work in this plan.
3. **Switch the entry point.** `MainMenuScene.handle("new_campaign")` starts
   `GlueScene(<the real first flow script>, campaign=...)` instead of `CaravanScene`. Confirm the
   actual first flow-script resource name before committing to this (likely `StartCaravan`'s glue
   resource; not yet verified for this plan).
4. **Parity pass.** Run the same battery of scripts already exercised through `--glue-program`,
   but now through the real menu flow; fix whatever the old scenes handled that the new one
   doesn't yet. Troop selection's current stub status is not a regression either way - it was
   already a stub - so building it can be scheduled independently of this migration.
5. **Remove the old pipeline.** Once parity holds: delete `CaravanScene`, `MissionMapScene`,
   `BriefingScene`, their views (`CaravanView`, `MissionMapView`, `BriefingView`), their dedicated
   tests, and any code in `campaign_scenes.py`/`campaign.py` that existed only to serve them. Keep
   `CampaignState` itself.

Steps 1-2 are the real engineering work; 3-5 are comparatively mechanical once those land. Intended
to be done one step at a time with a verify-then-commit rhythm, not as one large change.

## Open questions

- ⬜ Exact resource name of the real first flow script reached by "New Campaign" (step 3).
- ⬜ Whether `CampaignState`'s current shape is the right one to read/write from inside
  `GlueRuntime`, or whether it needs a narrower read/write interface for that (step 2).
- ⬜ Whether troop selection gets built as part of this migration or scheduled separately (step 4).

## Implementation milestones

### 1. Define the campaign runtime interface

Give `GlueRuntime` a narrow interface for the campaign operations it actually needs: coffers,
mission selection and taken state, roster membership queries, battle/debrief bookkeeping, and
`autosave()`.

Adapt `CampaignState` to provide the first implementation. `autosave()` may be a no-op or retain
an in-memory snapshot until save/load is implemented; glue must still invoke it at the specified
runtime points. Add focused runtime tests for the interface and every command it serves.

### 2. Route generic external activities

Add a glue activity coordinator at the scene boundary. It consumes `GlueScene` effects and
transitions to movie, battle, debrief, caravan, or troop-selection presentation as those activities
are implemented.

When an activity finishes, route a matching `ActivityResult` back to the originating `GlueScene`.
Do not replace the glue scene or reconstruct its runtime state. A battle started by glue must return
to glue; direct battle mode may retain its standalone result flow.

### 3. Replace the bespoke briefing path

Use generic glue programs and `GlueView` for mission briefings. Verify dialogue, portraits,
animation, music, panel actions, battle entry, and return behavior through this path.

#### Interim Accept route

Before troop selection is available, Accept may launch the selected mission's existing `BattleScene`
directly. This makes generic briefings playable while deliberately deferring troop selection, mission
costs, roster updates, and mission-taken bookkeeping. Replace this route with the troop-selection
activity in milestone 6.

Delete `BriefingScene`, `BriefingView`, their routing branches, and their dedicated tests after the
generic flow covers them.

### 4. Replace map and mission selection

Drive mission selection from generic glue windows and the campaign runtime interface. Implement
mission visibility, selection, and the panel actions needed to enter the selected mission route.

Delete `MissionMapScene`, `MissionMapView`, and their dedicated tests after the equivalent generic
path is exercised end to end.

### 5. Replace caravan modes

Route `EnterCaravan` into the generic caravan presentation while preserving the parked glue runtime.
On exit, return its `ActivityResult` to that runtime. Implement the caravan modes required by the
campaign flow first.

Delete `CaravanScene`, `CaravanView`, and `CampaignState` members used only by the former caravan
projection as each corresponding generic behavior is complete.

### 6. Implement troop selection as a built-in activity

Build troop selection as a dedicated activity. It must choose a force, apply mission costs, mark the
mission taken, update roster membership, and launch the pending mission script or battle route.

If troop selection is deferred, record it as the explicit functional boundary and do not treat the
migration as complete.

### 7. Switch New Campaign

Determine the actual first flow resource from the installation. Change
`MainMenuScene.handle("new_campaign")` to start `GlueScene(program, campaign=...)`, then remove the
old campaign-chain construction and unused imports.

### 8. Verify and remove the remaining old pipeline

Exercise menu-to-battle and return-to-campaign flows through the normal entry point. Remove any
remaining bespoke campaign scenes, views, tests, imports, and compatibility-only code once no live
path uses them.

## Migration rules

- Work one milestone at a time: add focused tests, verify the real flow, then commit.
- Autosave is invoked at the correct runtime points from milestone 1, but persistent save/load is
  deferred until it has a defined implementation.
- When generic behavior replaces an old path, delete the replaced code in the same milestone once
  no live caller requires it.
- Do not keep compatibility wrappers, deprecation paths, historical-decision comments, or legacy
  comments after their code has been removed.
