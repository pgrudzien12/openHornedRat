# Glue script interpreter: authoritative command semantics (`[RUN]` / `[START]` scripts)

Behavioral specification of the campaign glue *script* language: what each executable command does to interpreter state, how a
script suspends and resumes, and how the four stacks (script frames, window states, callers, contexts) interact. It complements
`notes/glue_keywords.md` (which covers the *block* vocabulary of window resources) and is the input for the `GlueRuntime` of
`notes/glue_runtime_architecture.md` §4.3. Marks: ✅ read from the executable and confirmed against shipped scripts, 🟡 read from the
executable but not exercised by any shipped script (or partly traced), ⬜ open.

Sources: the observed behaviour of the glue interpreter, the window/script loaders, the context stack and the activity completion
handling of `WHSHR.EXE`; the keyword table of the same
executable; and a usage scan of all 535 `WND.DLL` resources (120 `[RUN]` scripts, 415 window/object resources). Usage counts below are
"statements / scripts" over that corpus. Section 11 lists what is still open; `python3 -m whshr glue-spec` prints the per-command
status table (`whshr/glue_spec.py`).

## 1. Model at a glance

- A **script** is a `[RUN]` resource with exactly one `[START]` block (all 120 shipped scripts). A **window** is a `[WINDOW]` resource;
  no window resource contains `[START]`, so windows never execute commands, they only declare records (`notes/glue_keywords.md`).
  `[INCLUDE]`d and `addobject`-loaded resources are windows too.
- The interpreter is a line-by-line executor over the `[START]` body. One statement per line; the command name is everything before
  the first `:` and is matched **case-insensitively and by whole name** against a fixed table. An unknown command raises an error
  message naming the line and is skipped. Block headers inside a body (`[X]`) are skipped; only `[END]` stops the run.
- There is one **current frame** (the script being run or parked) and a small amount of global state: glue status bits/mask/mode
  (§3), a *current-window-name* (`setcurwindow`), a *current window slot* (the window whose resource is being loaded), the *block
  kind* of the last loaded top-level resource (`RUN` or `WINDOW`) and four **pending requests** (§2.2).
- Scripts do not loop. They run until they hit a *suspending* command, finish, or hand control to another script. Everything that takes
  time (dialogue, animation, movies, battles, screens) is an **activity**; the script is suspended while it runs and is resumed by the
  activity's completion handler (§8).

### 1.1 Script frame

A frame is a small record copied **by value**: open resource (or file), read position, name, and a **`parked` flag**. Copying a frame
copies the read position, so a restored frame continues exactly after the line that suspended it. The interpreter clears `parked` at
the start of every run; `waitforrelease`, `waitforresume` and an animation wait (§6.4) are the only commands that raise it (§5, §6.4).
`parked` means "do not auto-resume when this frame is restored from a context (§7); only an explicit
event may resume it".

### 1.2 The four stacks ✅

| Stack | Depth | Entry | Push / pop / drop |
|---|---|---|---|
| **Script-frame stack** | 16 | copy of the current frame | `gosub` pushes; `return` pops; also pushed/popped by contexts, movies |
| **Window-state stack** | 8 | snapshot of all 8 window slots + music/palette id + open-window count | contexts of kind `RUN`, movie start/finish |
| **Caller stack** | 8 | name of the last opened top-level window resource + a small integer (its resource kind) | contexts of both kinds |
| **Context stack** | 16 | the *block kind* (`RUN`=0x13 or `WINDOW`=0xC) of the top-level resource that was current when pushed | `PushContext`, `PopContext`, `DropContext` (§7) |

Overflow: a push onto a full stack logs an error and does nothing (the caller carries on without saving); underflow on pop/drop logs an
error and does nothing. A pop of an entry whose recorded kind is neither `RUN` nor `WINDOW` logs "stack corrupt" and fails (cannot happen
with data the engine wrote itself). "Clear" resets the depth to 0 (used by `endgame`).

## 2. Running a script

### 2.1 Interpreter result and the two entry points

`interpret(frame)` reads statements until one of three things happens and returns:

| Result | When | Meaning |
|---|---|---|
| `SUSPENDED` (2) | a command set the *stop* flag | stay parked/suspended; the frame is kept |
| `ENDED` (1) | an `[END]` line | script body finished |
| `EOF` (0) | the text ran out with no `[END]` | shipped scripts never do this; nothing further happens (§2.3) |

Two callers drive it.

**`resume()`** (runs the current frame again; called by every activity completion handler):

```
if no current frame is open: return
r = interpret(current)
if r == SUSPENDED:  do_pending()                         # §2.2
elif r == ENDED:
    r2 = read_remaining_blocks(current)                  # further blocks of the same resource; none exist in shipped data
    if r2 != SUSPENDED:
        close(current)                                   # frees resource, zeroes the frame
        if pending_goto: load_and_run(pending_goto)      # §2.3
        if gomissionselect_flag: release_mission_select()# §9.3
# r == EOF: nothing happens (frame stays open, pending goto ignored)
```

**`load_and_run(name, window_slot, report_missing)`** (opens a resource by name and runs it in a *local* frame; used for `res:` targets,
window opening, `addobject`, `goto`, `gosub` and script-by-name launches):

```
open `name` from the glue resource module            # missing: log (if report_missing), return "failed", change nothing
pending_goto = none; gomissionselect_flag = false    # NOTE: cleared by EVERY load, including window and object loads (§10 item 3)
first block must be [WINDOW] or [RUN]                # else an error message and the load fails
r = run all blocks (a [START] block calls interpret(local))
if r == SUSPENDED:
    current = local                                  # the new script becomes the current (parked) frame, overwriting it
    do_pending()
else:
    close(local)
    if pending_goto: load_and_run(pending_goto, same window, ...)   # tail call
    if gomissionselect_flag: release_mission_select()
```

The block kind of the loaded resource (`RUN` or `WINDOW`) is remembered as the *current block kind*; nested loads for objects
(`addobject`) restore the previous kind afterwards, `openwindow`/`opensubwindow` save and restore both the kind and the current window slot.

### 2.2 Pending requests and their order ✅

`interpret` never performs the heavy commands itself. `gocaravan*`, `encounterplaygame*`, `gosub*` and `goto*` only **record a request**
(name + variant) and stop the run. The request is honoured by whoever called `interpret`, *after* it returned:

| Request | Set by | Honoured when | Action |
|---|---|---|---|
| caravan | `gocaravan`, `iftrue/iffalsegocaravan` | result is `SUSPENDED` (checked first) | `GoCaravan(name)` (§7.3) |
| encounter battle | `encounterplaygame`, `…withdebrief` | `SUSPENDED`, after the caravan request | `PushContext(hide windows)`, clean up all windows, start the battle (§8.1) |
| gosub | `gosub`, `iftrue/iffalsegosub` | `SUSPENDED`, after the other two | push the current frame on the script-frame stack, then `load_and_run(target, current window, report_missing)` |
| goto | `goto`, `iftrue/iffalsegoto` | result is not `SUSPENDED` (script ended) | `load_and_run(target)` (tail call) |

Each request buffer is cleared at the start of `interpret` (goto/gomissionselect are cleared by `load_and_run` instead), and a
consumed request is cleared. Only one of caravan/encounter/gosub is ever pending in shipped scripts.

### 2.3 Consequences worth copying

- `goto` does **not** stop the run: lines after `goto:` still execute until a stopping command or `[END]`; the jump happens only after
  the body ends. Conditional `iftruegoto`/`iffalsegoto` *do* stop the run (result `SUSPENDED`), so the jump is **not** taken on the
  `SUSPENDED` path of `load_and_run`/`resume`: the script parks with the request still pending, and the jump happens only if that
  frame is later resumed and ends before another load clears the request (a latent original bug; 0 shipped uses, 🟡). The engine
  should log them as unsupported rather than guess.
- Ordering: if `gosub`/`gocaravan` etc. are issued from a script that never suspends otherwise, the request runs right after the
  script yields, before anything else.
- `return` inside a script that is running in a *local* frame (its very first run after `gosub`) closes and pops as usual but the
  restored caller is **not resumed** (nothing calls `resume`). Shipped subscripts never do this: every one suspends (dialogue,
  `waitforresume`, movie, `gocaravan`) before its `return`, so it always returns from a resumed frame (§4.3).

## 3. Glue status, mask and mode ✅

Three global 32-bit values (initial: **bits = 0, mask = 0xFFFFFFFF, mode = 2**), saved in the save game (bits) and not reset by
window changes:

| Command | Effect |
|---|---|
| `setgluestatusmask:<hex>` | `mask = hex value` (digits `0-9A-Fa-f`, no prefix, stops at the first non-hex char) |
| `setgluestatusmode:<n>` | `mode = n` (unused in shipped scripts 🟡) |
| `setgluestatus:` / `clrgluestatus:` | `bits \|= mask` / `bits &= ~mask` (no argument) |
| tests (`testmission`, `testobjective:<c>`, `testforunitinarmy:<n>`, `testforunitinmarch:<n>`, `debrief` result tests) | if the test is true: `bits \|= mask` else `bits &= ~mask` |

**Condition** used by every `iftrue*` (true branch) / `iffalse*` (false branch):

```
cond = (mode == 1) ? (bits & mask) == mask        # all mask bits set
     : (mode == 2) ? (bits & mask) != 0           # any mask bit set  (default)
     : mode                                        # any other mode: the mode value itself (0 = false, else true)
```

So with defaults (mask = all, mode = any) a condition means "some status bit is set". Shipped scripts set a small mask
(`setgluestatusmask:4`) and then run a test, or set/clear bits by hand (`setgluestatus:` after `setgluestatusmask:2`), so bits act as
named flags: e.g. `BMMission1` uses bit 2 to remember a choice made in an earlier script (the test/set pairs are per script;
no global naming). The condition is evaluated **at the conditional command**, not when the test ran; nothing consumes the result, so it
lives until another test/set/clear changes those bits. Usage: `setgluestatusmask` 32/24, `clrgluestatus` 11/11, `setgluestatus` 6/6,
`setgluestatusmode` 0.

`testmission:` additionally performs an **autosave** (§9.1) after setting the status (falls through in the original; ✅ confirmed at
instruction level). It evaluates the debrief evaluator index that `playgame…,<n>` / `setdebrief:<n>` stored (`n-1`) against the
current `debrief.dbf` (`notes/campaign.md` §5): true = the mission was won. If no debrief file is present the test is false.

## 4. Control flow

### 4.1 `gosub`, `iftruegosub`, `iffalsegosub` ✅ (10, 8, 3 uses)

Argument: resource name (a `[RUN]` script). Unconditional: request gosub(name) and stop. Conditional: evaluate the condition (§3); if
it holds request gosub(name) and stop, otherwise continue with the next line. On honouring (§2.2): the current frame is pushed onto the
script-frame stack (16 deep), then the target is run in a local frame.

### 4.2 `goto`, `iftruegoto`, `iffalsegoto` ✅ (3 uses of `goto`, all as the last statement)

Records the pending goto (§2.2) and, for the conditionals only, stops. The target replaces the ended script; no frame is pushed. Used as
the tail of the `ZhufbarMission` chain (`REMISSION6`, `WEMISSION145`, `WEMISSION1` → `WEMISSION145`).

### 4.3 `return` ✅ (13 uses, all in subscripts)

Closes the current script (frees the resource, zeroes the frame) and **pops the script-frame stack into the current frame**, then the
interpreter keeps reading — from the popped frame, i.e. it continues *after the `gosub` line* of the caller. If the stack is empty the
pop logs an underflow and the closed frame reads as end-of-text (the run ends with `EOF`). `return` does not stop the run and does not
touch the context stack.

`return` is the only way back from `gosub`. A script that reaches `[END]` without `return` does **not** return to its caller (it ends;
the caller's frame stays on the stack, a leak the original has and shipped data avoids).

## 5. Waiting and parking ✅

| Command | Effect on the frame | Resumed by |
|---|---|---|
| `waitforrelease:` (18/10) | `parked = 1`, stop | mission-list release (§9.3): the caravan is left and the selected record has `releaseflag = 1` (or nothing visible remains) |
| `waitforresume:` (8/7) | `parked = 1`, stop | a control-panel button of the window the script opened: **Evade / Decline** (`controlpanel` 4 slot 0, 7 slot 0) calls `resume()` directly; **Defend / Attack!** (`controlpanel` 3, 4, 8) start a battle instead, and that battle's completion pops the context the button pushed and calls `resume()` (`notes/mission_selection.md` §4.2) |
| `pause:` | (no case; ignored) | - |

The two commands are **identical inside the interpreter**; what differs is the code that later calls `resume()` (mission release vs.
control-panel buttons). The engine can model both as a wait on an *event id* (`mission-release`, `panel-resume`) and route the UI
event to the parked script. `resume()` clears `parked` at the start of the run, so the flag only matters for the automatic resume in
`PopContext` (§7.2). The battle that Defend/Attack! start is the one named by the last `setbattlescript:<bf>` (or, for a mission
without one, the mission record's battle name); `playgame:<bf>` names its own.

## 6. Windows and objects ✅

State: 8 **window slots** (name, parent slot, HWND, record arrays: bitmaps, mission list, texts, hotspots, dialogue ring buffer of
1 KiB, music name, palette id) and a **window count** (index of the first free slot). The *current window slot* is the slot whose
resource is being loaded or whose script is running; `setcurwindow` sets an independent **current window name** used by object commands.

| Command | Argument | Effect |
|---|---|---|
| `openwindow:res=<name>` (78/78) | window resource | Save (block kind, current slot). `load_and_run` the resource into slot `count` (parent none). Then the application palette is selected from the window's `palindex` (`notes/palette_selection.md` §2), before the window is created. On success: name copied into the slot, `count++`, real window created and painted (immediately; unless in the "no windows" mode). On failure (resource missing or not a `[WINDOW]`): nothing changes, the script continues. Restore (kind, current slot). **Does not suspend.** |
| `opensubwindow:res=<name>` (154/88) | window resource | Same, but the new window is a **child** of the **first open top-level window** (the lowest slot that has no parent and a live window; not the current slot): its parent link points there, its palette id is copied from that parent, and it is created as a child window. A child never changes the application palette (`notes/palette_selection.md`). |
| `closewindow:res=<name>` (97/45) | window name | For each of slots 0-7 whose stored name equals `name` (**exact, case-sensitive** compare of the spelling used by `openwindow`): destroy the window and free its records. If the closed slot is the **last** used one (`slot == count-1`) then `count--` (only once: holes below stay). Unknown name: no-op. |
| `setcurwindow:res=<name>` (394/99) | window name | Copy `name` into the *current window name*. No lookup, no window change, never fails. |
| `updatewindow:` (3/3) | - | Invalidate and repaint the **current window slot** (not the `setcurwindow` window). |
| `applyseq:res=<name>` (469) | window name | Start the portrait mouth/eye sequence given by `set:animseq` on window `name`'s anim record (`notes/glue_portraits.md`). Never suspends. |
| `addobject:res=<name>` (40/27) | resource name | Only if `key` is `res`. Find the slot whose name equals the current window name; `load_and_run(name, slot, report_missing)` **into that slot** (its blocks append records: bitmaps drawn after existing ones, missions, texts, hotspots). After loading: if the slot's bitmap count changed, recompute the scroll/mission layout; then refresh the mission list. |
| `addanimobject:res=<name>` (182/76) | resource name | Same as `addobject`. Then, if the **last added bitmap has a finite stop frame** (`animstopframe ≥ 0`), mark it **notify-on-stop** and **suspend** with `parked = 1` (§6.4). Looping bitmaps (`animstopframe = -1`) never suspend. |
| `removeobject:bitmap` (0) | - | Remove the last bitmap of the current window (count-1, repaint its rectangle). |
| `removeobject:mission` (30/…) | - | Clear the mission-list widget of the current window (whole record zeroed). |
| `removeobject:midi` (1) | - | Stop and discard the tune and clear the window's music name. |
| `addmidiobject:<tune>` | tune name (whole text after `:`) | Copy the name into the current window slot and start it (once). 🟡 unused |

Other keys after `:` in `addobject`/`addanimobject`/`removeobject` (`bitmap`, `mission`, `midi`) are matched against a small
key-name table; a key that does not fit the command is ignored.

### 6.1 Current-window bookkeeping

`load_and_run` records the window slot it loads into as the *current window slot* for the duration of the load; `openwindow` /
`opensubwindow` restore the previous slot afterwards, `addobject` restores it too. The current window *name* is never restored.

### 6.2 What `addobject` cannot do

An `[INCLUDE]` block containing `addobject:` is ignored (one authoring slip, `MAPWINDOWMSZHUFBAR`). `addobject` outside `[START]` is
never executed (windows do not run commands).

### 6.3 Failure modes

`openwindow` of a name that is not a resource returns to the script silently (a debug warning). Nothing in shipped data depends on it.

### 6.4 Animation wait ✅

The bitmap animation tick (25 ms base, `set:timecnt` in 50 ms units) checks each bitmap: when its current frame equals its stop frame
and its notify flag is set, the flag is cleared and the tick reports "a waiting animation finished"; the timer handler then calls
`resume()`. So `addanimobject` of a `-1`-looping bitmap continues immediately, of a bitmap with a stop frame the script continues
when the animation reaches that frame (the stop-frame numbers are in `notes/campaign_tent.md` §5.2). `parked` is set, so a
context pop does not auto-resume it.

## 7. Contexts: push, pop, drop, unwind ✅

### 7.1 `PushContext(hide)`

```
kind = current block kind (RUN or WINDOW)
if context stack full: log, return
context[depth] = kind
if kind == RUN:   push current frame on the script-frame stack; push window state (snapshot of all 8 slots, tune, count),
                  and if hide: hide every window; push caller
else:             push caller only
depth += 1
```

### 7.2 `PopContext(show)`

```
kind = context[depth-1]
current block kind = kind
if kind == RUN:   pop the script-frame stack into the current frame; restore window state (recreate windows, show them if `show`);
                  pop caller
elif kind == WINDOW: pop caller only
else: log "stack corrupt", return 0
depth -= 1; return kind
```

Windows restored by a `RUN` pop are recreated from the snapshot (records, bitmaps, mission lists, anim state are all kept, the
dialogue buffer is not). The 8 saved states and the 16 contexts are independent counters.

Handlers that pop then decide about the script:

- *Return-to-window* handlers (hotspot "back", dialogue click after `waitforresume`): `PopContext(show=1)`; if the popped kind is `WINDOW`
  they re-open the window named by the **caller** (run it by name); if it is `RUN` and the game is not paused and the restored
  frame's `parked` flag is 0, they call `resume()`. A `RUN` frame with `parked = 1` waits for its own event. ✅ (`notes/mission_selection.md`
  §10 "PopContext")
- *Activity completions* (movie, debrief, encounter battle) pop the exact context they pushed, then `resume()` unconditionally.
- *Unwind to script* (mission release): pop repeatedly (`PopContext(1)`) until the popped kind is `RUN` (each `WINDOW` entry just
  drops its caller); if the stack empties first, stop. ✅

### 7.3 `GoCaravan(name)` (`gocaravan`, `iftruegocaravan`, `iffalsegocaravan`) ✅ (47/41, 1/1, 2/2)

The pending caravan request runs when the script suspended (§2.2). Matching is case-insensitive:

| `name` | PushContext(hide=1)? | Clean up all windows | Resource opened |
|---|---|---|---|
| `select` | yes | yes | `CaravanAfterMission`, or `CaravanAfterMissionWithRecruit` when regiments are recruitable (the pending recruits are merged into `ARMY.MRC` first) |
| `resume` | yes | yes | `CaravanAfterEncounter` / `CaravanAfterEncounterWithRecruit` (same test) |
| `recruit` | yes | yes | `CaravanRecruitAndResume` (after merging pending recruits into `ARMY.MRC`) |
| `recruitnospeech` | yes | yes | `CaravanRecruitNoSpeechAndResume` (same merge) |
| `start` | no | yes | `StartCaravan` (new game: nothing to return to) |
| `infoBPC`, `infoREA`, `infoREC`, `infoBMA`, `infoWED`, `infoSZA`, `infoSZB`, `infoENE`, `infoLA`, `infoLB` | yes | yes | `InfoCaravan` + the letters (`InfoCaravanBPC` …) |
| `infoENA` | yes | yes | `InfoCaravanENA` after the same recruit merge |
| anything else | no | no | log; the script is **resumed immediately** |

`ARMY.MRC` is re-read from the working copy each time, before the name is examined. The caravan window is a top-level `WINDOW`: it becomes the current window
and the *context stack* holds the suspended `RUN` context below it. Leaving the caravan (the mission map, the `Done` hotspot)
pops it as in §7.2.

**Conditional entry.** `iftruegocaravan:x` requests the caravan only if the condition holds; otherwise the run continues with the next
line (no stop). `iffalsegocaravan` is the negation. Example `REMISSION4`: `testmission:` (sets the status and autosaves) then
`iftruegocaravan:infoREC` / `iffalsegocaravan:select`. `testmission` sets the *mission-won* bit; the script picks the caravan variant
from it.

## 8. External activities: suspension and resumption

Every activity command sets the stop flag; the script frame stays as the current frame with `parked = 0`, so the completion handler
resumes it. The columns below show whether the command pushes a context first.

### 8.1 Battles ✅ (`playgame` 5, `playgamewithdebrief` 9, `encounterplaygame` 4, `encounterplaygamewithdebrief` 8)

Argument `name[,n]`: battle file name (up to the comma); if `n ≠ 0` it sets the debrief evaluator index `n-1` (the same field
`setdebrief:n` and `testmission` use). `iftrue/iffalse` forms: none.

| Command | Context pushed | On battle end |
|---|---|---|
| `playgame` | no | debrief screen (mode 6, default callback) → `DoDebriefingDone(pop=0)` |
| `playgamewithdebrief` | no | debrief screen (mode 2) → `DoDebriefingDone(0)` |
| `encounterplaygame` | yes (`RUN`, windows hidden, all windows cleaned) | debrief screen (mode 6) → `DoDebriefingDone(pop=1)` |
| `encounterplaygamewithdebrief` | yes | debrief screen (mode 2) → `DoDebriefingDone(1)` |

The encounter forms are *requests* (§2.2), so they run after the script suspended; the plain forms start the battle at once. With the
`nobattle` command-line option the battle is skipped and the completion handler runs immediately. After the battle the same
cursor/screen bookkeeping runs, then the debrief screen. If the battle module reports a Quit (it clears its "valid" flag and writes no `debrief.dbf`) and the `unrealquit` option is unset, the game returns to the main menu and the script is not resumed (`notes/activity_results.md`).

`DoDebriefingDone(pop)`: pays out/promotes (`notes/campaign.md` §5), deletes the transient files, then: if there is no mission
script name for the current mission (the `setmissionscript` name of the selected `[MISSION]`; the campaign-over flag that could also
force this branch is never set by anything found, 🟡) → `GoCaravan("select")`; else if `pop` → `PopContext(1)`; then `resume()` the
script. This is why `playgamewithdebrief` inside a mission script continues with the next line after the
debrief, and why `testmission` after it can read the freshly written `debrief.dbf`.

🟡 The difference between debrief-screen modes 2 and 6 (and 4/7 for `debrief`/`debriefwithsummary`) is only partly characterised
(`notes/campaign.md` §5 describes the balance sheet); the interpreter-side effect is fully specified above.

### 8.2 Debrief commands ✅ (`debrief` 6/5, `debriefwithsummary` 6/6; conditional forms unused 🟡)

`debrief:<n>` / `debriefwithsummary:<n>` sets the evaluator index `n-1` (if `n ≠ 0`), `PushContext(hide=1)`, cleans up all windows and
shows the debrief screen (mode 4 / 7) over `debrief.dbf`; on completion it applies the coffers total, closes the screen,
`PopContext(1)` and `resume()`. `iftruedebrief`, `iffalsedebrief`, `iftruedebriefwithsummary`, `iffalsedebriefwithsummary` behave the
same but only when the condition (§3) holds; otherwise the run continues.
`setdebrief:<n>` sets the evaluator index only (24/17 uses).

### 8.3 Movies ✅ (`playmovie` 29/22, `iftrueplaymovie` 5/3, `iffalseplaymovie` 2/2; fade variants unused 🟡)

Argument: cutscene name (`A2`, `A16a` … `notes/scene_scripts.md`). Effect: copy the **current frame** to the script-frame stack,
`PushContext`-like save of the window state (windows hidden), clean up all windows, then:

- name starts with `Place` (case-insensitive; none shipped): show a timed placeholder;
- otherwise play the film from the `anim` folder full-width in the strip `x=0, y=96, 640×272`; if movie playback is not
  available, skip straight to the completion.

Completion (`DoRunContinueAfterMovie` / `AfterPlaceHolder`): close the player, restore the window state, pop the script-frame stack, `resume()`.
The `withfade` variants also start a screen fade-out first. Conditional forms play only when the condition holds; otherwise the
run continues (no stop).

### 8.4 Dialogue ✅ (`playtext` 187/66, `queuetoplaytext` 157/48; `queuetext` unused 🟡)

Argument `res=<id>` (glue string table id). Text is appended to the ring buffer of the **first window slot**; speech
`glue/speech/b<id>.wav` is loaded only if speech is enabled.

- `playtext`: load the speech, append the text, **start** the dialogue state machine, suspend (`parked = 0`).
- `queuetext`: append, do not start, do not suspend.
- `queuetoplaytext`: if speech is enabled (`nospeech` option off): behaves like `playtext`; else: append and continue (silent skip
  of the dialogue, no suspend).

A dialogue completion (all queued text shown and speech finished, or a click that fast-forwards the queue) calls `resume()`.
Details of timing, ring buffer and click drain: `notes/briefing_dialogue.md` §3.

**Click during a voiced line** ✅ (code reading): the drain runs on the left mouse button **release** (not the press), in a window that
still has dialogue pending (text queued or lines still being shown). If the release did not launch a hotspot action, the dialogue
step is run repeatedly with every per-line delay forced to zero until the whole queue is consumed, so all remaining text of that
`playtext`/`queue*` batch appears at once (not just the current line). If the text queue is then empty but the speech clip is still
playing, the clip is stopped. If the queue ended a wait, `resume()` follows immediately. A release over a hotspot while text is pending
does **not** launch the hotspot (it only drains); a hotspot that has a `clickres` line plays that canned speech instead and does not
drain. Keyboard keys and the right button do nothing. Consequence for the engine: one click always finishes the current voiced line
*and* any lines queued behind it, and the script continues in the same event. `loadanimstringintocache:<id>` (~20 uses)
only warms a 16-entry string cache and has **no observable effect**; an engine may ignore it.

### 8.5 `endgame:` ✅ (2/2)

Cleans up all windows, clears all four stacks (contexts, callers, window states, script frames), stops the music and returns to the title
menu (or exits when started in a special mode). Does not stop the interpreter; the calls that follow are harmless.

## 9. Campaign-state commands (interpreter side; semantics in the named notes)

| Command | Effect | Detail |
|---|---|---|
| `addtroop:<who>=<n>` | `reinforcements[who] += n` | `notes/campaign.md` §2.4 |
| `addunit:<who>` | roster flag *pending join* = 1 | `campaign.md` §3.2 |
| `unitjoinmission:<who>` / `unitleavemission:<who>` | move a regiment into / out of the mission force | `campaign.md` §3.2 |
| `testforunitinarmy:<who>` / `testforunitinmarch:<who>` | status test (§3) on the roster's in-army / in-march flags | `campaign.md` §3.2 |
| `testobjective:<letter>` | status test on the letter's result in `debrief.dbf` | `campaign.md` §5 |
| `cash:type,a,b,c,d,letters` | store payment program on the current mission record | `campaign.md` §2.5 |
| `setbattlescript:<bf>` | current mission's battle file name | `campaign.md` §5 |
| `addcash:<n>` / `iftrueaddcash:<n>` | coffers += n (unconditional / if condition) | `campaign.md` §2.5 |
| `bonusinit:` / `bonusadd:<n>[,x]` / `bonussubtract:<n>` / `iftruebonusadd` / `iffalsebonusadd` | campaign bonus counters | `campaign.md` §2.5 |
| `enablebook:<kind>=<index>` | sets an encyclopedia/book flag (kinds 0-2) | `campaign.md` §4.4 |
| `set:<key>=<n>` (script form) | store a script variable: `animseq` (sequence used by later `applyseq`), `textlines` (dialogue line count), `tentpos` (tent position read by `gettentpos`); `x`, `y`, `step`, `timecnt` are also accepted and stored (unused). Any other key is ignored | `glue_keywords.md` §4 |
| `tagasmission:` (45/45) | **no-op** in the retail build (a test-harness marker); ignore | - |
| `replacescript:<Flow>` | clean up all windows, then `load_and_run` the named resource (`FlowScript…`) as the new current script (a parked frame of the old script is discarded) | `mission_selection.md` §8.1 |
| `playmidi:<tune>` / `stopmidi:` | remember tune + play once (the remembered tune restarts on `PopContext`), stop and forget | `briefing_dialogue.md` §2 |
| `setmidivolume`, `setwavvolume`, `settextalign:<left\|center\|right>`, `settextcolor:<name>`, `setdemodefault`, `comment` | UI state / no effect; `setdemodefault` is inert | `glue_keywords.md` |
| `autosave:` | see §9.1 | |
| `gomissionselect:` | see §9.3 | |

### 9.1 `autosave:` ✅ (56/46) and the save-point rule

Writes the four working files (`ARMY`, `MARCH`, `PLAY`, `debrief`) and then saves slot 5 ("Last Game") with the interpreter
state: it does `PushContext(hide=0)` first so the **saved state contains the current script frame** (position after the `autosave` line),
the window states and caller, writes the file, then `DropContext` (pop without restoring) and re-shows the windows. The save
therefore resumes *at the line after `autosave:`* with the same windows open. `testmission` performs the same routine after setting
the status.

### 9.2 `setcurwindow` then object commands

Object commands act on the slot whose stored name equals the current window name (**exact, case-sensitive**; the names are the spellings written in the scripts). If several slots share a name the **first** slot wins. Resource lookup by name (`openwindow`, `addobject`, `gosub`, …) is case-insensitive.

### 9.3 `gomissionselect:` ✅ (2/2) and mission release

`gomissionselect:` only raises the *gomissionselect* flag (it does not stop the run). When the current load/resume ends without suspension
(the script `[END]`s), the runner performs the **mission release step**, which is the built-in `UnwindMission` action of
`notes/mission_selection.md` §8.1: pop contexts until a script frame whose windows contain a mission list is restored, apply the mission
result to the list and resume the flow script only if the selected record has `releaseflag` or nothing visible remains
(`notes/campaign.md` §7.5). The only scripts using the command (`SZMission5`, `WEMission2`) put it last, so the flag survives to the
end of the run.

## 10. Quirks to replicate (all confirmed unless noted)

1. `tagasmission` is a no-op; `testmission` autosaves.
2. `goto` does not stop the run; the jump happens at the end of the script.
3. **Every** resource load (windows, objects, scripts) clears the pending goto and the gomissionselect flag. A `goto:`/`gomissionselect:`
   followed by `openwindow`/`addobject` in the *same* script would lose the request; shipped scripts never do that (the three
   `goto`s and two `gomissionselect`s are the last statements, or are followed only by `[END]`).
4. `queuetoplaytext` degrades to a silent text append (and no wait) when speech is disabled.
5. Conditions test *status bits under a mask*; there is no separate result register (§3).
6. `openwindow`, `opensubwindow`, `addobject` failures are silent.
7. Two commands raise `parked` for very different reasons: waits for user actions; the animation wait raises it to keep a popped
   context from auto-resuming it.
8. `closewindow` shrinks the window count only when the closed slot is the last one.
9. Unknown commands and unknown blocks are reported (message box in the original) and skipped; the engine should log and continue.

## 11. Coverage over the 535 resources and open items

`python3 -m whshr glue-spec` combines `coverage_report` (usage) with the registry in `whshr/glue_spec.py`. State at writing:

| Group | Commands | Status |
|---|---|---|
| control flow | `gosub`, `iftruegosub`, `iffalsegosub`, `goto`, `return`, `iftruegoto`, `iffalsegoto` | ✅ §4 (conditional gotos unused) |
| wait / park | `waitforrelease`, `waitforresume` | ✅ §5 |
| status | `setgluestatus`, `clrgluestatus`, `setgluestatusmask`, `setgluestatusmode`, tests | ✅ §3 |
| windows/objects | `openwindow`, `opensubwindow`, `closewindow`, `updatewindow`, `setcurwindow`, `addobject`, `removeobject`, `addanimobject`, `applyseq` | ✅ §6 |
| contexts / caravan | `gocaravan` (+ conditional), `tagasmission` | ✅ §7 (no-op noted) |
| activities | `playgame*`, `encounterplaygame*`, `playmovie*`, `debrief*`, `playtext`, `queuetoplaytext`, `endgame` | ✅ interpreter side; debrief screen modes 🟡 |
| campaign state | `addtroop`, `unitjoin/leavemission`, `cash`, `bonus*`, `addcash`, `enablebook`, `testfor*`, `testobjective`, `gomissionselect` | delegated to `notes/campaign.md` / `notes/mission_selection.md` |

Open items, in order of usefulness to a `GlueRuntime`:

1. **Debrief-screen modes 2/4/6/7** — what each panel shows and applies belongs in `notes/campaign.md` §5; the interpreter side
   (which context is pushed, who resumes) is fully specified in §8.
2. Result contracts, evaluators and built-in windows are now in `notes/activity_results.md`, `notes/debrief_evaluation.md` and `notes/builtin_widgets.md`.
3. **Hotspot launcher table** — documented per panel and per built-in window in `notes/mission_selection.md` §4.2 and §8.1; no
   complete per-hotspot table over all 112 hotspot blocks exists, but the interpreter does not depend on it.
4. Never exercised by shipped `[RUN]` scripts (specified from code only, cheap to implement, not testable): `iftruegoto`,
   `iffalsegoto` (broken in the original, §2.3), `setgluestatusmode`, `queuetext`, `playmoviewithfade` and its conditionals,
   `iftruedebrief` and the other three debrief conditionals, `pause`, `removeobject:bitmap`, `addcash`, `bonussubtract`,
   `iftruebonusadd`, `setmidivolume`, `setwavvolume`, `replacescript` (only used as a `[MISSION]` key in shipped data).
5. `whshr/glue.py` lists a command `stopspeech` as implemented; the executable has no such command (it would be reported as an unknown
   instruction and skipped) and no script uses it. It can be dropped from the importer's vocabulary.
