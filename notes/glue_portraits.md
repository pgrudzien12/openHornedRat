# Glue portraits: `[ANIM]` index → sprite set, backgrounds, palette and talk/blink animation

Behavioral spec for the speaker portraits that campaign glue windows show (Dietrich, the Commander, Carlsson, …).
Extends `notes/mission_selection.md` §9 (which described the frame, panel and buttons) and answers the questions it left
open: the `index` → file table, the `BACKALL` palette, and the mouth/blink animation. Status marks: ✅ verified (read
from the front-end code and checked against data/renders), 🟡 inferred, ⬜ unknown.

## 1. `[ANIM] set:index=N` → sprite set ✅

`index` is **not** a position in the leader-portrait category of the sprite-name table and not a name lookup. The front end
keeps one **resident portrait list** of 37 records (loaded when the glue is initialised, terminated by a `-1` marker). Each
record holds a sprite-table index (`notes/sprite_names.md`); the `[ANIM]` `index` is the position in this list.
Each record also carries two further integers: the crop-window origin used by the roster book, not by glue windows (§1.3).
The list is also what the roster book uses to find a regiment's portrait from a sprite-table index (§1.3).

The list is a small fixed table in the executable. Every entry is a leader-portrait sprite set (`.FOL/.BOP` in
`FILE/BINARY` or `UPDATE/BINARY`, 6–8 type-1 frames: frame 0 = 120×152 portrait, later frames = mouth/eye overlays),
except the last:

| Index | Sprite set | Speaker in glue windows (`name:`) |
|---|---|---|
| 0 | `CER1` | Ilmarin (`IlmarinWindow`); Ceridan in `CeridanWindow` |
| 1 | `CARL` | Carlsson |
| 2 | `COMM` | Commander |
| 3 | `SKA4` | (unused in glue) |
| 4 | `SCRI` | Dietrich, Scribe |
| 5 | `MER1` | Lt Godber |
| 6 | `DWA1` | Harkon |
| 7 | `DWA2` | Dargrimm |
| 8 | `DWA3` | (unused in glue) |
| 9 | `DWA4` | (unused in glue) |
| 10 | `GOTR` | Gotrek; `UngrunnWindow` (see §1.2) |
| 11 | `ELF1` | Galed |
| 12 | `BRIW` | Luther Flamestrike |
| 13 | `MER2` | (unused in glue) |
| 14 | `REIK` | (unused in glue) |
| 15 | `ORC2` | (unused in glue) |
| 16 | `GOB1` | (unused in glue) |
| 17 | `BERN` | Cpt Bernard |
| 18 | `CER2` | Ceridan (all other Ceridan windows) |
| 19 | `BERI` | Cpt Bernard (wounded, one window) |
| 20 | `HOLG` | Holger |
| 21 | `ENGR` | Engrol |
| 22 | `AZGU` | Azguz |
| 23 | `AMBE` | Allor |
| 24 | `GINF` | (unused in glue) |
| 25 | `RAMO` | (unused in glue) |
| 26 | `CARO` | (unused in glue) |
| 27 | `ART1` | (unused in glue) |
| 28 | `CELE` | Marius |
| 29 | `HALB` | (unused in glue) |
| 30 | `KEEL` | (unused in glue) |
| 31 | `XBOW` | (unused in glue) |
| 32 | `TREE` | (unused in glue) |
| 33 | `HAMM` | (unused in glue) |
| 34 | `IRON` | (unused in glue) |
| 35 | `KING` | Ungrunn (`UngrunnWindowBR`) |
| 36 | `BACKALL` | (the 21 background frames, see §2) |

Verification: every `name:` above matches the rendered portrait (the elf for Galed and Ceridan, the crowned dwarf king
for Ungrunn, the wounded version of Bernard for index 19, the Celestial wizard for Marius, the orange-mohawked dwarf for
Gotrek, the fire-sword figure for Luther Flamestrike, the Commander's spiked helmet, the scribe's green tunic and red book
for Dietrich). Indices 4 (`SCRI`) and 2 (`COMM`) are therefore both verified now; the earlier "Commander by name only"
note is closed.

### 1.1 Which `index` values glue windows actually use ✅

Scanned over all `[ANIM]` blocks in `WND.DLL` (114 blocks): 0, 1, 2, 4, 5, 6, 7, 10, 11, 12, 17, 18, 19, 20, 21, 22, 23, 28, 35.
The others belong to regiment/leader portraits in the roster book.

### 1.2 Apparent conflicts ✅ (explained by usage)

- **Ceridan index 0 and 18.** `CeridanWindow` uses index 0 (`CER1`, the hooded man with the blue amulet); every numbered
  `Ceridan*Window` uses 18 (`CER2`, the blond elf with the same amulet). The sprite names are `Ceridan1` and `Ceridan2`, i.e.
  two portraits of the same person, and `CeridanWindow` is used by the Loren subscript (`LM_SUBSCRIPT2`), so the hooded
  portrait is deliberate there (Ceridan hooded; 🟡 the story reason).
- **Ilmarin index 0.** `IlmarinWindow` (used in `BPBrief3`) reuses the hooded `CER1` portrait. No separate Ilmarin portrait exists;
  `Ilmarin` in the sprite-name table is not present. Reuse is by design or by shortcut 🟡.
- **Ungrunn index 10 (same as Gotrek).** `UngrunnWindow` (index 10, `GOTR`) is **never opened** by any script; only
  `UngrunnWindowBR` (index 35, `KING`) is (`SZBrief5`). The index-10 window is a dead template. Do not treat it as a mapping
  error in the table.

### 1.3 Roster-book crop window ✅

The two extra integers of each record are the **x, y origin of a 72×104 crop window** inside the 120×152 frame 0 of the
set. The roster book (`notes/builtin_widgets.md` §2.3) uses the same window for the portrait and for its background, so
the face stays centred. Glue windows ignore them. A set that the roster never shows has (0, 0). All x are ≤ 47 and all y ≤ 30
(the slack of a 72×104 window in 120×152). Rendered crops of `COMM`, `GOTR`, `DWA3`, `REIK`, `BRIW`, `TREE`, `IRON`, `ELF1`
frame each face centrally with nothing cut off.

| Index | Set | X | Y |
|---|---|---|---|
| 0 | `CER1` | 0 | 0 |
| 1 | `CARL` | 0 | 0 |
| 2 | `COMM` | 26 | 6 |
| 3 | `SKA4` | 0 | 0 |
| 4 | `SCRI` | 0 | 0 |
| 5 | `MER1` | 26 | 5 |
| 6 | `DWA1` | 23 | 12 |
| 7 | `DWA2` | 25 | 17 |
| 8 | `DWA3` | 47 | 5 |
| 9 | `DWA4` | 30 | 21 |
| 10 | `GOTR` | 20 | 6 |
| 11 | `ELF1` | 29 | 5 |
| 12 | `BRIW` | 41 | 16 |
| 13 | `MER2` | 16 | 5 |
| 14 | `REIK` | 19 | 4 |
| 15 | `ORC2` | 0 | 0 |
| 16 | `GOB1` | 0 | 0 |
| 17 | `BERN` | 23 | 11 |
| 18 | `CER2` | 24 | 3 |
| 19 | `BERI` | 0 | 0 |
| 20 | `HOLG` | 26 | 20 |
| 21 | `ENGR` | 24 | 14 |
| 22 | `AZGU` | 24 | 8 |
| 23 | `AMBE` | 23 | 12 |
| 24 | `GINF` | 22 | 9 |
| 25 | `RAMO` | 23 | 7 |
| 26 | `CARO` | 23 | 6 |
| 27 | `ART1` | 35 | 16 |
| 28 | `CELE` | 24 | 5 |
| 29 | `HALB` | 17 | 8 |
| 30 | `KEEL` | 23 | 9 |
| 31 | `XBOW` | 25 | 9 |
| 32 | `TREE` | 21 | 30 |
| 33 | `HAMM` | 31 | 9 |
| 34 | `IRON` | 13 | 18 |
| 35 | `KING` | 0 | 0 |
| 36 | `BACKALL` | 0 | 0 |

Lookup: the roster book searches this list linearly for the sprite-table index stored in the regiment's leader block; the
match position gives the window. Without a match: no portrait, the background window defaults to (25, 5), and the regiment's
banner is drawn at full size in the box instead (🟡: how often this happens with shipped `.MRC` data).

## 2. `bkindex` and the background frames ✅

- The background is **frame `bkindex` of `BACKALL`** (21 frames of 120×152, sprite-table entry `AllBGs`), drawn under the
  portrait's frame 0 with palette index 0 of the portrait transparent. Values used in glue: 0–19 (frame 15 for Dietrich).
- ✅ The frame number is exactly `bkindex`: the executable adds a base offset to it, but that offset is a constant 0 that nothing writes
  (checked by searching for writers), and the set is selected by the fixed sprite-table entry `AllBGs`. No per-scene, day/night or
  campaign-state offset exists. (The key is stored per `[ANIM]` block; a `[BITMAP]` `set:bkindex` is an unrelated repaint flag,
  `notes/campaign_tent.md` §5.6.)
- Frames 0–14 and 18–20 are landscapes, buildings and stone or hill backdrops; 15 is a red stage curtain; **16 and 17 are the two halves of a wooden
  interior** with a shelf and a bottle (left and right of an arch), used as single backgrounds by Commander, Carlsson,
  Dargrimm, Harkon, Cpt Bernard, Azguz, Holger (16) and Ceridan, Ilmarin, Engrol, Cpt Bernard (17).

### 2.1 Palette ✅

`STANDARD.PAL` alone is right for every portrait and for `BACKALL` frames 0–15 and 18–20. **Frames 16 and 17 need the map
screen palette**: `GLUEMAP.PAL` (indices 10–105) plus `WINDMAP.PAL` (106–245) merged over `STANDARD.PAL` (i.e. the
`palindex=2` pair used by every map window). Evidence: those frames use palette indices 28–241 and 77 % / 85 % of their pixels
land on the 100 entries where the map pair differs from `STANDARD`, while no portrait frame and no other `BACKALL` frame
uses any of those entries. Rendered with the map pair they are a natural brown interior; with the caravan, book, roster or
title pairs they are wrong (yellow, grey-green, pink). Because portrait windows sit on map windows, the engine should
composite portraits with the **window's palette** (`[POSITION] palindex` → screen pair, `notes/fonts_glue.md`), not with a
fixed `STANDARD.PAL`. The portraits themselves render identically under either.

## 3. Animation: sequences, ticks and frames ✅

### 3.1 State per `[ANIM]` block

Each portrait has two independent animation **slots**: **mouth** and **eyes**. Each slot plays a *sequence* chosen from a
per-kind table and stops or loops it. The frame shown is the sprite set's frame number given by the sequence step
(frame 0 is the full portrait and is not a step frame). Two table kinds exist: index 3 (`SKA4`) uses its own kind 3 tables
(not needed by any glue window); **every other glue index uses kind 5**, described here.

Kind 5 frame roles (checked visually on `SCRI` and `COMM`; overlays are opaque and repaint the whole mouth/eye rectangle
at the position stored in the frame record, so nothing has to be cleared):

| Frame | Role | Size (`SCRI`) at |
|---|---|---|
| 1 | mouth **closed** | 44×26 at (40, 84) |
| 3, 4, 5, 6 | mouth open, increasing shapes | same |
| 2 | eyes **open** | 32×5 at (47, 69) |
| 7 | eyes **closed** (blink) | same |

(`COMM`: mouth 36×27 at (43, 64), eyes 28×4 at (45, 52).) Position and size are read from the frame record, not from a table.

### 3.2 Sequence language ✅

A sequence is a list of `(frame, duration)` steps followed by a control word. Each step shows `frame` for **`duration + 1`
ticks** (the first step is shown immediately when the sequence starts). Controls: `stop` (hold the last frame forever), `loop`
(restart at the first step with no gap), `goto sequence n`, and `hide` (an unused variant that draws nothing for a period).
The tables below only use `loop`.

**Tick = one glue timer message.** The application runs a 25 ms timer and forwards each timer message to every open glue
window; a window advances its animations **once per message that finds at least 25 ms elapsed** (it does not catch up
with several ticks if a message is late). So the nominal tick is 25 ms; on real Windows the timer granularity stretches this
(about 31 ms on NT-family systems, 55 ms on Windows 9x), so the original's speed was machine dependent. An engine should use
25 ms as the unit unless a timing measurement says otherwise. The timer is slowed to 500 ms while the main window is
minimised, and animations do not advance while either of two front-end flags is set ✅: the **paused** flag (toggled by the
Pause/Resume button, which also pauses the music) and a **glue busy** flag that is raised while windows are being built, cleaned
up, started or shut down and restored afterwards. The same two flags gate the `[BITMAP]` animation step (`notes/campaign_tent.md`
§5.3), which uses a 2-tick (50 ms) step where the portrait sequences use the one-tick unit above.

### 3.3 Sequence tables (kind 5), durations are the stored values (shown `duration+1` ticks)

Mouth slot:

| Seq | Contents | Loop length |
|---|---|---|
| 0 | 27 steps of frames 1,3,4,5,6 with durations 1–2 | 78 ticks (1.95 s) |
| **1** | 36 steps, frames 1,3,4,5,6, durations 1–2 (frame 6 lasts 2 ticks, the others 3, frame 1 mostly 3) | **104 ticks (2.60 s)** |
| **2** | frame 1, duration 1 (closed mouth, loops in place) | 2 ticks |
| 3 | 42 steps, same frames | 122 ticks (3.05 s) |

Eye slot:

| Seq | Contents | Loop length |
|---|---|---|
| 0, 4 | eyes open 49/41/44 ticks (+1), blink (frame 7) 1 (+1) each, three cycles | 143 ticks (3.58 s) |
| **1, 2, 3** | eyes open 49/36/40/46/22/44 (+1), blink frame 7 duration 1 (+1) each, six cycles | **255 ticks (6.38 s)** |

Talking mouth patterns look pseudo-random but are **fixed sequences**, not generated: sequence 1 starts
1,4,6,5,3,4,1,4,3,4,1,4,6,4,1,3,5,3,… (frame, each 2 or 3 ticks; frame 6 is the 2-tick one), then loops. Blink = frame 7 for
2 ticks (50 ms nominal) after 22–50 ticks (~0.6–1.3 s) of open eyes.

### 3.4 What `sequence`, `frame`, `animseq` and `applyseq` do ✅

- **`[ANIM] set:sequence=N`**: the sequence number both slots start with when the window is created. Values in data: 1 (114
  blocks), 0 (1), 2 (1). So a portrait starts **talking** (mouth sequence 1, eyes sequence 1) until a script stops it.
- **`set:animseq=N`** (script): sets the glue variable holding the "next sequence" number. Only **1 (170 uses) and 2 (304 uses)**
  occur.
- **`applyseq:res=<window>`** (script): for **every** `[ANIM]` block of the named window, copies that number into the block
  and restarts both slots with it. `animseq` 1 → talking (mouth sequence 1, eyes sequence 1); `animseq` 2 → stopped (mouth
  sequence 2 = closed mouth held, eyes sequence 2 = the same blink loop as 1, so **the eyes keep blinking while stopped**).
- **`set:frame=N`** ✅ code, ✅ art: selects an **ornamental border set** for the portrait window from a table of four entries. Entries 0, 1
  and 2 are three gold ornament sets of 8 pieces each (four corners, top and bottom edge, left and right edge), drawn from sprite frames
  181–188, 189–196 and 197–204 of the `ICONS` sprite set (viewed: gilded corners with skulls, chains and thorn work); entry 3 is an
  **empty list, so nothing is drawn**. Every shipped block (115) uses 3, so the ornaments are never shown and the plain `FRAME*` bitmap
  border applies (`notes/mission_selection.md` §9.3). Offsets of the pieces inside the window (top-left corner, then edges):

  | Set | Pieces as `(x, y)`: TL, top edge, TR, left edge, right edge, BL, bottom edge, BR |
  |---|---|
  | 0 | (0,0) (20,0) (96,0) (0,48) (116,32) (0,148) (28,156) (100,132) |
  | 1 | (0,0) (24,0) (100,0) (0,32) (112,36) (0,148) (24,156) (100,148) |
  | 2 | (0,0) (28,0) (96,0) (0,44) (112,36) (0,144) (28,160) (96,144) |

  The role of each piece is read from the rendered sheet 🟡 and the window-relative origin of the ornaments was not traced. An
  engine can ignore this key (only 3 occurs) and must not treat it as a pose or frame number.
- Nothing ties the mouth to the speech audio or to `playtext`: the scripts start and stop talking explicitly
  (`set:animseq=1; applyseq; queuetoplaytext…; playtext…; set:animseq=2; applyseq`, see `BPBrief1`), and the mouth follows
  the fixed sequence for as long as `animseq` is 1. There is no amplitude analysis.

### 3.5 Adjacent finding (dialogue pacing, not fully traced 🟡)

The text of a `playtext` line is revealed in step with the **playback position of the speech WAV** (fraction played) when a
speech file `glue/speech/b<id>.wav` exists and speech is enabled; otherwise a timer-based reveal is used. This is separate
from the portrait animation.

## 4. What the engine should read from data and what belongs in a small table

**From data (per window):** window `[POSITION]` (x, y), `[ANIM]` `index`, `bkindex`, `controlpanel`, `settextcolor`, `sequence`;
the script commands `set:animseq` and `applyseq:res=<window>`; the window's `palindex` (→ screen palette pair).

**Small tables in code (front-end constants, cite this note):**

1. `index` → sprite set: the 37-row list in §1 (one module; unused rows may stay, they cost nothing). The current
   `PORTRAIT_SPRITES = {4: "SCRI"}` can be filled from it; index 36 is `BACKALL`.
2. Kind-5 sequences and the tick unit (25 ms): the tables in §3.3, with the frame roles of §3.1. Kind 3 (`SKA4`) is not
   needed by any glue window.
3. Frame-role mapping (1 closed mouth, 2 open eyes, 3–6 open mouth, 7 closed eyes).

**Not needed from the table:** overlay positions and sizes (read from the sprite set's frame records), background frame
(= `bkindex`), palette (window's `palindex` pair merged over `STANDARD.PAL`).

**Suggested engine behaviour:** `PortraitAnimator` per block: `mouth` and `eyes` sequences, `apply(seq)` restarts both, `advance(ticks)`
advances by 25 ms units; a scene event `applyseq` (from the parsed script, not from dialogue timing) switches talking/stopped;
the view draws frame 0, then the current mouth overlay, then the current eye overlay, at the frame records' positions. Tests:
`applyseq` 1 gives the mouth frames 1,4,6,5,… at 3,3,2,3 ticks; `animseq` 2 gives frame 1 held and a blink of frame 7 for
2 ticks after 50 ticks; the first eye blink after applying sequence 1 comes after 50 ticks.

## 5. Corrections to `notes/mission_selection.md` §9

- §9.2 "index is not the position in the leader-portrait category … table not found" → found (§1 above); Commander → `COMM` is
  verified.
- §9.2 "BACKALL may need its own palette 🟡" → frames 16/17 need the window's map screen palette pair (§2.1).
- §9.1 `sequence`/`frame`/`animseq` rows → §3.4 (`frame` has no known effect; only `animseq` 1/2 occur; timing is 25 ms ticks).
- `frame=3` = "no ornaments" (§3.4). The two extra integers per resident-list record stay ⬜.

## 6. Open questions
> **Tracked on GitHub**: these open items are tracked as issue #29 (`topic:campaign-glue`). Kept here for
> reference; a follow-up pass (issue #45) will verify nothing was lost in the move.


- ⬜ The story reason for `CeridanWindow` and `IlmarinWindow` using the hooded portrait (§1.2) and whether the two extra
  integers in each resident-list record are the roster book's per-portrait offsets.
- ✅ Pause flags identified (§3.2); ✅ `set:frame` = ornament set, 3 = none (§3.4).
- ⬜ The machine-dependent real tick length (needs a timing capture in the running original).
- 🟡 Whether kind 3 (`SKA4`) is ever shown by a glue window (no `[ANIM]` uses index 3).
