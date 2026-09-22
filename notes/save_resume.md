# Save / resume: how glue interpreter state is saved and restored

Behavioral specification of the glue-interpreter half of `savegame.N` (RIFF `WHSV`): what each saved value is, how a load rebuilds
the runtime, and which apparent bugs exist. It corrects and completes `notes/campaign.md` §4.2-§4.3 (container, `SHDR`, `STAX`) and builds
on `notes/glue_interpreter.md` (§1.2 stacks, §7 contexts, §9.1 autosave) and `notes/palette_selection.md`. Marks: ✅ read from the
executable and confirmed on the two local saves (`scripts/save_stax.py --check`), 🟡 read from code only, ⬜ open.

## 1. Corrected `SHDR` depth fields ✅

The four counters at `SHDR+0xCC..0xD8` are the depths of the four interpreter stacks, not the names given in `campaign.md`:

| Offset | Was called | Is | savegame.0 | savegame.5 |
|---|---|---|---|---|
| `0xCC` | `nScripts` | **window-state stack depth** (≤ 8) | 0 | 2 |
| `0xD0` | `nCalls` | **context stack depth** (≤ 16) | 2 | 4 |
| `0xD4` | `nWindows` | **caller stack depth** (≤ 8) | 2 | 4 |
| `0xD8` | `nObjects` | **script-frame stack depth** (≤ 16) | 0 | 2 |

`0xC8` is `tentpos`, `0xDC` the coffers, `0xE0`/`0xE4` glue status bits/mask, `0xE8` the campaign bonus counter (the value `bonusinit`
resets), `0x40`/`0x80` the current battle name and the current-window name (`setcurwindow`).

## 2. `STAX` layout ✅

`STAX` size = `S·(0x218A0 + 8) + C·4 + K·(0x80 + 4) + F·0xA0` with `S,C,K,F` the four depths (272 and 275 632 bytes for the two saves ✓).
In order:

| # | Array | Meaning |
|---|---|---|
| 1 | `S` × 0x218A0 | window-state snapshots: all 8 window slots (8 × 0x4314) as they were when the context was pushed |
| 2 | `S` × u32 | **open-window count** of that snapshot (index of the first free slot) |
| 3 | `S` × i32 | **palette id** active when it was pushed (`-1` = built from a bitmap, `notes/palette_selection.md`) |
| 4 | `C` × u32 | context kinds: `0x13` = `RUN` context (owns a snapshot and a script frame), `0xC` = `WINDOW` context |
| 5 | `K` × 0x80 | caller names (name of the top-level window/script that was current) |
| 6 | `K` × u32 | caller resource kind (`1` = the glue resource module; the loader maps it back to a module) |
| 7 | `F` × 0xA0 | script frames: name at `+4`, module kind at `+0x84`, read position at `+0x98`, `parked` flag at `+0x9C` |

**The two previously unidentified u32 values per saved script are the snapshot's open-window count (array 2) and its palette id (array 3).**
`savegame.5` has (3, 3) and (2, 2): three slots used per snapshot, palette 2 (`MAP`).

Only `RUN` contexts own a snapshot and a frame: `savegame.5` has kinds `[WINDOW, WINDOW, RUN, RUN]`, `S = 2`, `F = 2` — the two `WINDOW`
contexts (`MainMenu`, `StartCaravan`) own nothing, the two `RUN` contexts own snapshot/frame pairs in stack order. ✅

## 3. What the two saved frames are ✅

`savegame.5` ("Last Game", written by `autosave:`): frame 0 = flow script `FlowScriptBP01`, position 831, `parked = 1` (it ended in
`waitforrelease`); frame 1 = mission script `BPMission1`, position 733, `parked = 0` (just after its `autosave:` line, before the battle).
Snapshot 0 (map + scribe + the flow-script slot) belongs to the flow script's context, snapshot 1 (`MapWindowBp1`, `Scribe5WindowTL`,
`BPMission1`) to the mission script's context, which `autosave:` pushed for the write (§6). A script started through the window launcher
occupies a window slot **named after the script** (`FlowScriptBP01`, `BPMission1` are slot 2 of their snapshots); the slot holds no window.

## 4. Load procedure ✅

1. Read the chunks in order; restore `ARMY.MRC`, `PLAY.MRC`, `MARCH.MRC`, `debrief.dbf` from `RMY1..4`; restore book flags, roster
   (`RMYI`), current mission (`MISS`).
2. Set: battle name, current-window name, `tentpos`, the four stack depths, coffers, the bonus counter.
3. Status: mask := all ones; clear; mask := saved bits; set; mask := saved mask. Net effect bits = saved bits, mask = saved mask.
4. For each of the `F` saved frames whose module kind is non-zero: re-open the resource **by name** from that module (frame text
   handles are rebuilt; the saved read position and `parked` flag are kept; a frame with kind 0 is left dead).
5. If a `MARCH.MRC` exists, rebuild the marching list from it.
6. Front end (load button of the save/load window): clean up all windows, `PopContext(show)`; if the popped kind is `WINDOW`, re-open the
   caller by name; **otherwise `resume()` the popped frame** (whatever its `parked` flag: `resume` clears it). A load therefore continues
   the script right after the line that suspended it (after `autosave:` for slot 5). The same path runs after a successful save.

The runtime-state mapping for the open engine: `contexts[]` (kind, snapshot, palette id, window count, caller name+kind) + `frames[]`
(script name, module, position, parked) + status + `tentpos` + coffers + bonus counter + files. Nothing else of the interpreter needs saving.

## 5. Mission "taken" flags ✅

The per-mission *taken* flag lives in the **mission records of the map window's mission list**, that is inside the window-state
snapshots (`snapshot 0`: record 601 `taken = 0`), and in the current mission (`MISS`, `taken = 1` once the player committed).
The release step copies the current mission over the selected record (`notes/mission_selection.md` §8.1). There is no separate
persistent list: **a mission list that is not inside a saved snapshot is not saved**. Saves are taken only where the map's context
exists (autosave pushes; the save dialog runs on top of a caravan context), which is why every shipped save works.

## 6. Autosave and saves ✅

`autosave:` writes the four working files, pushes a `RUN` context (windows not hidden), writes slot 5 with description "Last Game",
drops the context and re-shows the windows; `testmission` does the same. A user save from the caravan writes the same structure with
the caravan's contexts on the stacks. Description text and slot rules: `notes/builtin_widgets.md`.

## 7. Apparent bugs and vanilla mode 🟡

| Behaviour | Effect | Recommendation |
|---|---|---|
| The header checksum (`0xC4`) is recomputed on load but its result is discarded | corrupt/foreign saves load | vanilla import: accept; engine format: write a real checksum |
| A saved palette id of `-1` is reloaded as `STANDARD` | wrong colours only if a context is pushed while a `palindex -1` window is current; no shipped script does | keep the saved palette instead |
| A frame whose module kind is 0 is not reloaded | dead frame | never produced by shipped saves |
| Stale pointers (HWND, bitmap handles, palettes) are stored inside snapshots | ignored: windows are recreated on pop | do not store them; store window records only |
| Load resumes unconditionally after the pop | a `parked = 1` flow script resumes into its `waitforrelease` (re-parks) | reproduce |
| `testmission` autosaves | slot 5 is overwritten by the branch test | reproduce |

## 8. Open items
> **Tracked on GitHub**: these open items are tracked as issue #31 (`topic:campaign-glue`). Kept here for
> reference; a follow-up pass (issue #45) will verify nothing was lost in the move.


- ⬜ The remaining item/army-file relationships (`RMYI` fields against `ARMY.MRC`/`PLAY.MRC`, item lists) are covered only by `notes/campaign.md` §3-§4.5.
- 🟡 The load-then-resume rule was read from code; no run confirmed it (only two saves exist, both from the first mission).
- ⬜ Saves taken deeper in the campaign (three or more script frames, `gosub` frames on the stack) would confirm the frame/context pairing rule.
