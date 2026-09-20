# External activity result contracts (what the glue interpreter sees when an activity ends)

Behavioral specification, from `WHSHR.EXE` and `GAMEF.DLL` (read as research input, no code reproduced) and checked against the
shipped scripts in `WND.DLL`. Builds on `notes/glue_interpreter.md` (§2 resume protocol, §7 contexts, §8 activities) and
`notes/mission_selection.md` (§4.2 panel buttons, §8.1 built-in windows); it answers "what state does the script find when it
runs again?". Marks: ✅ read from the code and consistent with shipped scripts, 🟡 read from the code but not confirmed against
data or partly traced, ⬜ open.

## 1. The channel: there is almost no return value ✅

An activity never hands a value to the interpreter. When it ends, a completion handler restores the pushed state and calls
`resume()`; the script simply continues on the next line. Everything the script can later learn comes through one of these
channels:

| Channel | Written by | Read by the script through |
|---|---|---|
| **Glue status bits** (under the current mask) | only the encounter panel button **Attack!** (§3), plus the script's own `setgluestatus` / `clrgluestatus` / test commands | `iftrue*` / `iffalse*` (`notes/glue_interpreter.md` §3) |
| **`debrief.dbf`** (`Result:` lines + unit blocks), written by the battle module | battle end (§2.1) | `testobjective:<L>`, `testmission:` (§2.3) |
| **Working files** `ARMY/MARCH/PLAY.MRC`, coffers, book flags | debrief completion (§5), troop selection Done (§4) | `testforunitinarmy`, `testforunitinmarch`, `addtroop`, … and the caravan windows |
| **Current-mission record** (battle name, mission script, debrief evaluator index `n-1`) | `setbattlescript`, `setdebrief`, `playgame…,n`, troop selection | the next activity that needs it (Defend/Attack!, troop selection Done) |

There is **no** "victory / defeat / retreat" value: the battle module reports only *"debrief written"* or *"quit"* (§2.1); win or
lose is derived afterwards from `debrief.dbf` (§2.3).

## 2. Battles

### 2.1 How a battle ends ✅ (mechanism) / 🟡 (which UI action triggers which)

The battle window carries a small result record given by the front end (name, and a *valid* word set to 1 when the window is
created). Three ways out:

1. **Normal end** — the in-battle "end battle" command (a confirmation dialog inside the battle module) writes `debrief.dbf` and
   closes the window; the record stays *valid*. This is the only path used for victory, defeat and any other conclusion: the
   battle module does not judge the outcome, it just serialises objective results and surviving / dead-or-routed units
   (`notes/campaign.md` §4.8). There is no separate retreat result: a "retreat" is whatever the objectives in the file say
   (typically objective `A` not met).
2. **Quit** — the in-battle *Abort mission?* Yes/No dialog (glue-independent string, BRTXT table 6). **Yes**: the *valid* word is
   cleared, the window closes and **no `debrief.dbf` is written**.
3. Closing the battle window from outside behaves like (2) (valid cleared).

The completion handler then does:

- *valid == 0* (quit) **and** the developer option `unrealquit` is off (never on in a normal install): show the end screen, tear
  down the glue windows and go to the **main menu** (§6.3). The script is **not** resumed and nothing is saved; the last autosave
  (slot 5) is what the player can reload. ✅
- otherwise: show the end screen chosen by the evaluator (§2.3), then run the **post-battle wrapper** (§2.2).
- With the option `nobattle` the battle is skipped and the completion handler runs at once (dev only).

### 2.2 Post-battle wrapper ✅ (mechanism; `notes/campaign.md` §5 has the bookkeeping)

Every battle end (all four `playgame*` / `encounterplaygame*` variants) first runs the same wrapper before any debrief screen:

1. Load `debrief.dbf`. **Campaign-over test**: let *L* = "the commander regiment (roster id 2) is present in the file and not
   alive". If *L* is false: the campaign is over when objective `G` **or** `Y` is present and successful. If *L* is true: over
   when objective `Z` is present and successful; otherwise the commander's counter is incremented and the file is rewritten.
   (A "present" objective is one that has a `Result:` line; "successful" is its second field = 1.)
2. Campaign over → play the death movie (`death01` when *L*, `death02` otherwise), then clean up and go to the **main menu**
   (§6.3). The script is not resumed, the debrief screen is not shown. 🟡 for the exact meaning of `G`/`Y` (item B2 of
   `ROADMAP.md`); the control flow is ✅.
3. Otherwise: wounded bookkeeping, merge of the debrief into `PLAY.MRC`, clear wounded if objective `Z` succeeded, then the
   debrief screen (mode 2 for `…withdebrief`, mode 6 otherwise). On *Done* the debrief-completion handler runs (§5).

### 2.3 Objective and mission tests ✅

`Result:<L>,<success>,<a>,<b>,<c>,<d>` lines are parsed into a table indexed by letter.

- `testobjective:<L>` (first character of the argument): loads `debrief.dbf` (cached), then sets the status **true** iff a `Result`
  line for `L` exists **and** its `<success>` field is 1; a missing letter or a missing file is **false**. It uses the current
  mask like every test (`glue_interpreter.md` §3).
- `testmission:` runs the *debrief evaluator* selected by `setdebrief:n` / `playgame…,n` (index `n-1`, 42-entry table, key
  letter per entry) over the loaded file and sets the status true iff it reports the mission as won (a missing file is
  false). It then autosaves (`glue_interpreter.md` §3). The end-screen chooser uses the same evaluator with the entry's key
  letter: `A` → objective A success; `T` → the evaluator's result; `Z` → failure if objective Z present; `z` → "failure" or
  neutral screen; other → neutral screen. The seven evaluator functions themselves are **not** decoded here (item B1/B2,
  `notes/campaign.md` §8). One worked entry, the one shipped scripts reach through `testmission` (`REMission4`,
  `playgamewithdebrief:bf004_4,15` → entry 14, key `T`): won iff objective `Z` is present **and not** successful **and**
  objective `B` is present with its fourth value ≠ 0; every other combination is lost. 🟡 (decoded from one evaluator).

### 2.4 Which variant resumes what ✅

| Command | Context pushed at start | Battle ends (normal) | Script resumed by |
|---|---|---|---|
| `playgame`, `playgamewithdebrief` | none | wrapper → debrief screen (mode 6 / 2) → default handler | `resume()` inside the handler (frame was never popped: still the current frame) |
| `encounterplaygame`, `…withdebrief` | `PushContext(hide)` (script frame + windows + caller) | same screens, handler with *pop* | handler does `PopContext(1)` then `resume()` |
| panel button **Defend** / **Attack!** (§3) | as `encounterplaygame` (a push, no debrief flag) | mode 6 screen, handler with *pop* | `PopContext(1)` → `resume()` after the script's `waitforresume` |

The handler ("debrief done", both variants): pay/promote per mode (`campaign.md` §5) → merge army files → then: if the current
mission has **no mission-script name** (record `setmissionscript` empty) → `gocaravan:select`-equivalent (pushes a context and
opens the after-mission caravan; the script is not resumed); otherwise pop (encounter variants) and resume the script. The
"campaign-over" flag that could also force the caravan branch is never set by any code found, so it is always 0. ✅

## 3. Encounter windows: Attack / Evade / Defend ✅

The buttons come from `controlpanel` (`mission_selection.md` §4.2). What they do to the interpreter:

| Panel | Button | Effect before anything else | Then |
|---|---|---|---|
| 4 (Evade / Attack!) | **Evade** | none (status untouched; text drained, speech stopped, unpause) | `resume()` — the script continues after its `waitforresume` |
| 4 | **Attack!** | **`bits |= mask`** (the glue status "set" operation under the *current mask*, same as `setgluestatus:`) | start an encounter battle (named by the last `setbattlescript`; no debrief flag; `PushContext`); on return §2.4 |
| 7 | **Decline** | as Evade | `resume()` |
| 3, 8 | **Defend** / **Attack!** | none | encounter battle as above; on return `resume()` |

So **Attack! is the only place outside scripts that writes the status**, and it writes it *before* the battle: the bit is set
even if the battle is lost, is aborted (game exits, so moot) or ends the campaign. Evade never clears it, so scripts clear it
themselves beforehand. The convention in the data (the only shipped panel-4 user, `SZMission5`):

```
opensubwindow:res=CeridanEncounterWindow …        # panel 4
setgluestatusmask:80
clrgluestatus:                                    # bit 0x80 = "player attacked" (cleared before the wait)
setbattlescript:bf029
waitforresume:
closewindow:res=CeridanEncounterWindow …          # Evade lands here with the bit clear; Attack! lands here after the battle with it set
setgluestatusmask:80
iftruegosub:SZMission5END                         # branch only if the player attacked
```

The mask is whatever the script set last, so the button writes exactly the bit(s) the script named. The panel-3/8 buttons
(Defend/Attack in `Ambush*Window`, `HarkonEncounterWindow*`, `AzguzWindowEnc8`, `ScribeWindowEnc8`) never touch the status; the
scripts that use them (`StandardAmbush` etc.) are gated by `iffalsegosub` on a bit *they* set/cleared
(`setgluestatusmask:1`, e.g. `GMMission3`, `BPMission5`); nothing on the battle path changes it, so the gate reflects the script's
own earlier choices. 🟡 for panels 5, 6, 9, 10 (no shipped window uses 5/6/10).

## 4. Troop selection

### 4.1 Accept (entry) ✅

Panel button **Accept** (briefing, map, panel 5/7/10 variants): unpause, drain the dialogue, stop speech, stop the tune and forget
its name, `PushContext(hide)`, clean up all windows, open troop selection over `ARMY.MRC` for the current mission (mode 0). What
the push saved depends on what was current: on the map the flow script frame + the map windows (kind `RUN`); from a briefing
window only the caller (kind `WINDOW`). Panels 6/7/10 skip troop selection and start the mission script or battle directly with
the same push. Troop selection itself is in `notes/troop_selection.md`.

### 4.2 Done (leave with a force) ✅

The window's confirm button is two-step (first press → summary page; second → Done). *Done*:

- coffers and mission fee applied; the current mission is marked **taken**; `ARMY.MRC`/`PLAY.MRC` written; roster in-army and
  in-march flags recomputed; the troop window is destroyed;
- then launch: if the current mission has a **mission-script name** run that script (a fresh top-level load; it becomes the
  current script); else if it only has a battle name start that battle as `playgamewithdebrief` (§2.4, no push); else nothing.
- **No context is popped.** The contexts pushed by the Brief/Accept steps stay on the stack under the mission script; they are
  unwound later by `UnwindMission` (§6.1) when the mission script's last `gocaravan:select` caravan is left.

### 4.3 Abort (Cancel) ✅

The second button asks *Abort?* Yes/No (a message box) **unless nothing is selected**, in which case it aborts silently. Yes:
free the selection, palette back to the map palette, clean up windows, `PopContext(1)`; if the popped context is of kind
`WINDOW` (Accept was pressed in a briefing) the **caller window is re-opened by name** (the briefing); if it is of kind `RUN`
(Accept on the map) the map windows and the parked flow script are restored and the script is **not** resumed (it is still
parked). Nothing is written, the mission is not marked taken. No status bit changes.

Mode 5 (nothing affordable, selected when the roster cannot pay any mission fee) replaces Done by a "game over" path: the window
is destroyed and the game goes to the main menu (§6.3). 🟡 (bankruptcy edge; `notes/troop_selection.md`).

## 5. Debrief and movie completion ✅

| Activity | Handler does | Then |
|---|---|---|
| `debrief:n` / `debriefwithsummary:n` (modes 4 / 7) | **coffers += final payment** for the file; destroy the debrief window | `PopContext(1)`, `resume()`. *Only* the payment: no armour rewards, doubled XP, promotions or army merges (those belong to the post-battle handlers of §2.4) |
| post-battle screens of §2.4 (modes 2 / 6) | payment (mode 2 only), armour rewards, doubled XP + promotions, merge into `ARMY.MRC` (+ `MARCH.MRC` for mode 6), clear wounded | §2.4 |
| `playmovie` | close player, restore window state, pop the script-frame stack | `resume()` unconditionally |

The debrief commands install their own completion handler *instead of* the default one, so no path pays twice; whether a `cash`
program itself double-counts a reward is a separate question (⬜, `notes/campaign.md` §2.5, item B3). A movie leaves the status
untouched and does not touch the context stack (frame and window state only).

## 6. Return modes of the built-in windows and caravans ✅ (code) — consolidated

All built-ins first clean up the current windows. `k` = kind of the popped context (`RUN` script frame, `WINDOW` caller-only).

| Built-in | Pops | If `k = WINDOW` | If `k = RUN` | Resumes the script? |
|---|---|---|---|---|
| `PopContext`, `PopContextCheckResume` | 2 (the first discarded, the second restored) | re-open the caller window by name | frame restored | **only if** not paused **and** the restored frame's `parked` flag is 0 (a script parked in `waitforrelease` / `waitforresume` stays parked) |
| `NullWnd` | 1 | re-open the caller | frame restored | no |
| `UnwindMission` | until a script frame whose windows contain a mission list is restored (frames without one are cleaned and popped again); stops if the stack empties | (dropped) | mission release step (§6.1) | via the release step, only if `releaseflag` or nothing visible remains |
| `PopAndResume` | 2, plus caravan-leave housekeeping (unhired regiments removed from `ARMY.MRC`, unused reinforcements cleared) | | | **always** (continues after the script's `gocaravan:`) |
| `AbortGame` | Yes: to the main menu; No: 1 and reopen | | | no |
| `OptionsDialogDone` | apply options, then as `PopContext` | | | as `PopContext` |
| `ArmyBook`, `HireOnlyArmyBook`, `MagicBook`, `EncyclopediaBook`, `Credits` | open on top (push by the launcher); their close handlers pop 1 and reopen the caller (or restore the frame) | | | no (the launcher's frame keeps its `parked` flag) |

### 6.1 Mission release step ✅ (`campaign.md` §7.5)
The *result* of a mission reaches the flow script's mission list here, not through the interpreter: the current mission record
is copied over the selected record, visible rows recounted, the list rebuilt. The flow script (parked in `waitforrelease`) is
resumed only when the selected record has `releaseflag` or nothing visible remains.

### 6.2 `gocaravan` result
`gocaravan:<name>` suspends the script; how it comes back depends on the caravan window's own exit hotspot (built-in above):
`select`/`resume` caravans → `UnwindMission`; `recruit*` and `info…` caravans → `PopAndResume`; `CaravanSelectMission` (map's
Caravan button) → `PopContext`. Unknown names resume the script immediately (`glue_interpreter.md` §7.3).

### 6.3 Main-menu exits
Game over (§2.2), quit-battle (§2.1), bankruptcy (§4.3), `AbortGame` Yes and `endgame:` all end at the main menu after clearing the
context, caller, window-state and script-frame stacks or popping down to the `MainMenu` window. A script is never resumed from
these exits.

## 7. Open items

1. ⬜ Seven evaluator functions and 42 table entries (only entry 14 decoded); meaning of every `Result:` value; objectives `G`, `Y`,
   `Z` as defeat conditions and commander-death interplay (`ROADMAP.md` B1–B2). Needed for exact `testmission` and end screens.
2. 🟡 What in the battle UI raises the "end battle" command (victory/defeat auto-detection vs. a player command); the interpreter
   contract does not depend on it.
3. 🟡 Whether a stale `Result:` record from an earlier battle survives when the new `debrief.dbf` lacks that letter (affects
   `testobjective` between two battles in one script).
4. ⬜ Save/load UI and options dialog return behaviour, the reinforcement sub-window, roster-book variants, marching order effect
   on deployment (built-in widget item B4; not traced here).
5. ⬜ Runtime confirmation (Wine) of Attack! setting the bit before the battle and of Abort on troop selection reopening the
   briefing; the code reading is unambiguous.
