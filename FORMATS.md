# File formats — Warhammer: Shadow of the Horned Rat (1995, Mindscape)

Notes from reverse-engineering the game's data formats, done mostly black-box
(byte analysis + visual verification). The game logic (`GAMEF.DLL`, `WHSHR.EXE`, mission DLLs)
has not been disassembled; only static data tables in the executables and the sound library
`MSNDDS.DLL` (the `.SFX` loader) were read. This file is the reference; the full reports on the
individual formats, including how each claim was verified, are in `notes/`.

The game is installed (GOG v1.0) in a Wine prefix:
```
~/snap/steam/common/.local/share/Steam/steamapps/compatdata/3605483607/pfx/drive_c/GOG Games/Warhammer - Shadow of the Horned Rat/WARFB/
```
Game data lives in `FILE/` (`BINARY/`, `DLL/`, `MESH/`, `SCRIPT/`), `UPDATE/BINARY/` and
`REMOTE/BINARY/` (cutscenes and speech, despite the name). `UPDATE/BINARY/` is a byte-identical
copy of the top level of `FILE/BINARY/` (731 files, 0 differences); it only lacks the `GLUE/`,
`MUSIC/` and `SOUND/` subdirectories, so the lookup order UPDATE → FILE only matters for those.

Files referenced as `samples/...` or `extracted/...` are local outputs produced by the scripts
from game data; they are not part of the repository.

## Overview

| Area | Files | Status | Section here | Full report |
|---|---|---|---|---|
| Palettes | `*.PAL` | ✅ | `.PAL` | `notes/btp_sprite_leftovers.md` (odd files) |
| Sprites and backgrounds | `*.FOL/.BOP` | ✅ | `.FOL`, `.BOP` | `notes/btp_sprite_leftovers.md` |
| Unit animation layout | directional `.FOL/.BOP` | ✅ layout, 🟡 anchor y, `dir` mapping | Sprite animation layout | `notes/animations.md` |
| Script names → files | tables in `WHSHR.EXE`/`GAMEF.DLL` | ✅ | Name tables | `notes/sprite_names.md` |
| Battle and army scripts | `SCRIPT/*.BTS/.MRC` | ✅ syntax, 🟡 semantics | `.BTS`/`.MRC` | — |
| Mission objectives | `Objective:L,a,b` | ✅ letters, 🟡 numbers | Mission objectives | `notes/pe_resources.md` |
| UI bitmaps, texts, campaign glue scripts | `DLL/*.DLL` resources | ✅ extraction, 🟡 glue semantics | PE resources | `notes/pe_resources.md` |
| Fonts, front-end palettes | `*.FON`, `GLUE/*.PAL` | ✅ | Front-end fonts and palettes | `notes/fonts_glue.md` |
| Music | `MUSIC/*.MID`, `SOUND/WARINTR3.SBK` | ✅ formats, 🟡 not listened to | Music | `notes/music.md` |
| Sound effects, speech | `SOUND/**/*.SFX/.WAV`, `GLUE/SPEECH/*.WAV` | ✅ formats, 🟡 not listened to | Sound effects | `notes/sfx.md` |
| Battle 3D resources | `MESH/*/*.PBX`, `GRND.GD` | ✅ | Battle 3D resources | `notes/pbx_rnc.md`, `notes/terrain_gd.md` |
| Cutscenes | `ANIM/*.SI/.SN/.SM/.SR` | ✅ containers, 🟡 event semantics | Cutscenes | `notes/si_omni.md`, `notes/scene_scripts.md` |
| Mission logic | `SCRIPT/BFxxx.DLL` | ⬜ needs disassembly | Mission logic | — |
| Save games | `SAVE/savegame.*` | ⬜ | Other files | — |

## `.PAL` — two different formats under the same extension

**Fully reverse-engineered and visually verified.**

| Variant | Examples | How to recognize | Count in `FILE/BINARY` |
|---|---|---|---|
| **A. RGB palette** | `STANDARD`, `NIGHT`, `BKMOUNT`, `UNDERWAY`, `PANEL`, `WIND`, `RICH`; debug: `TESTSPR`, `HALBERD`, `SYS` | 4-byte records `[index,R,G,B]` with increasing indices | 10 (+19 in `GLUE/`) |
| **B. 4→8-bit color map** of a sprite | `ESHIN`, `SPARKLE`, `BAN*`, `AMBWIZ`… | size = multiple of 512, a `.FOL` with the same name sits next to it | 141 |

Size alone is not enough to tell them apart: `ESHIN.PAL` (2048 B) is also a multiple of 4, and
`TESTSPR.PAL` (1024 B) is variant A although its size is a multiple of 512 (it has no `.FOL`).
A reliable distinction comes from the index order or the frame type in `.FOL`.

### Variant A — RGB palette

See `samples/standard_pal.png`.

- No header. Data starts immediately.
- **4-byte** records: `[index: u8][R: u8][G: u8][B: u8]`.
- Indices are **sequential** and cover the range **10–245** (236 entries, 236×4 = 944 bytes
  for `STANDARD.PAL`). This matches the classic Windows 3.x/95 GDI trick: the system
  reserves indices 0–9 and 246–255 for system colors, and the application gets only
  the middle 236.
- Partial palettes need not start at 10: `PANEL.PAL` has indices 106–245,
  `RICH.PAL` 10–33, `HALBERD.PAL` 0–15. The file size is always a multiple of 4,
  and the first byte of a record is the index. An entry overrides that index of the system palette.
- The main palette for battle sprites and backgrounds is `STANDARD.PAL`.
- Indices need not be contiguous: `SYS.PAL` (80 B) holds exactly the Windows reserved slots 0–9 and
  246–255, filled with marker colours (0 = blue, 1–9 and 246–254 = magenta, 255 = white). Parsers
  must not assume a contiguous range.
- Debug palettes: `TESTSPR.PAL` (indices 0–255: reserved slots magenta, 10–105 green, 106–245 ≈
  `STANDARD.PAL`) and `HALBERD.PAL` (its first 16 entries).
- The front-end palettes in `FILE/BINARY/GLUE/` split the 236 free indices into two halves:
  `GLUE<screen>.PAL` = 10–105 and `WIND<screen>.PAL` = 106–245 (see "Front-end fonts and palettes").

Parser: `scripts/parse_pal.py`, renderer: `scripts/render_pal.py`.

### Variant B — sprite color map (4 bpp → 8-bit indices)

The file is a sequence of **512-byte maps**, without a header; number of maps = `size / 512`.
Each map has 256 two-byte entries and is indexed by the **whole packed byte**
(two pixels at once), not by a single nibble:

```c
struct ColorMap {                 // 512 bytes
    struct { uint8_t left, right; } entry[256];
};
// pixels from byte b:  left = entry[b].left  (color of nibble b>>4)
//                      right = entry[b].right (color of nibble b&15)
```

The values are indices into `STANDARD.PAL`. In practice the table is an "expansion"
of a 16-color map `m[0..15]`: `entry[b] = (m[b>>4], m[b&15])`, and `m[0] = 0` means
transparency. Unused nibbles hold a filler value (e.g. `0xcf`).
Presumably this was about speed: one lookup per byte instead of two per pixel.

Start of `SPARKLE.PAL` (map 0, so `m = [00, 6a, 6b, 6c, cf, cf, …]`):
```
0000: 00 00 00 6a 00 6b 00 6c 00 cf 00 cf ...   entry[0x00..0x0f] = (m[0], m[n])
0020: 6a 00 6a 6a 6a 6b 6a 6c 6a cf ...         entry[0x10..0x1f] = (m[1], m[n])
```

Which map a frame uses is derived from `.FOL` (see "Color map" under `.BOP`). Each map belongs
to one **group of consecutive frames**, usually one animation strip (move, attack…) quantised to
its own 16 colours; rendering a group with another group's map gives garbage colours
(`SPARKLE`: map 0 is the sparkle, map 1 the snowman). So the maps are not regiment colour
variants. The only file with spare maps is `NLNHLB.PAL`: 8 maps, the frames use 0–3, and maps
4–7 are the same halberdiers in a second livery (hypothesis: chosen by the game).

## `.FOL` — frame/object table (Frame Object List?)

**Fully reverse-engineered.**

An array of **16-byte** records (number of frames = `file_size / 16`):

```c
struct FolEntry {
    uint8_t  b0, b1;     // offset 0-1  portraits: int16 x, int16 y = position of a mouth/eye
    uint8_t  b2, b3;     // offset 2-3  overlay frame inside frame 0.
                         //   Directional unit sprites: b0 = b1 = 0, b3 = anchor x in the frame,
                         //   b2 = anchor row counted from the frame bottom (probably the foot line)
    int16_t  width;      // offset 4
    int16_t  height;     // offset 6
    uint32_t bop_offset; // offset 8, offset of this frame's data in the matching .BOP
    uint8_t  kind;       // offset 12: lower nibble = frame type (1/2/4, see .BOP),
                         //            upper nibble = color map number modulo 16 (types 2 and 4, see "Color map")
    uint8_t  unk13;      // offset 13: 02 or 04, meaning unknown
    uint8_t  unk14;      // offset 14: 00 or 04, meaning unknown
    uint8_t  unk15;      // offset 15: always 40 in the standard layout
};
```

Bytes 13–15 by kind of file: directional sprites, banners, icons and spells `02 04 40`;
portraits `04 00 40`; raw tile animations (`LAVA*`, `BEAM`…) `02 00 40`. They do not affect decoding.

Most common `flags` values (bytes 12–15) across all `.FOL` files:
`04 02 04 40` (4420 frames), `24 02 04 40` (3716), `34 02 04 40` (3380), `14 02 04 40` (1408),
`01 04 00 40` (688), `02 02 04 40` (618), `01 02 04 40` (418), `01 02 00 40` (412),
then `44..f4 02 04 40` (mostly `SPELLS`).

- A frame's segment in `.BOP` starts at `bop_offset` and ends at the next
  **greater** offset from the same file (or at the end of the file). Frames need not be
  in order, and 2 frames share an offset, so the unique offsets have to be
  sorted.
- **Legacy layouts** (development leftovers, all frames raw 8 bpp, no flags): `HALBERD.FOL` and
  `SPRITE3.FOL` use 12-byte records `int16 hx, hy, w, h; uint32 bop_offset`, and `ICON2.FOL`
  uses 8-byte records `uint16 unk (0); uint8 w, h; uint32 bop_offset`. In all three the frames
  tile the `.BOP` exactly; the "counters" seen earlier in bytes 12–15 were the next record's
  offset read with the wrong record size. A standard file has `flags[3] == 0x40` in every record.
  Contents: `HALBERD` = a 96-frame halberdier + a shield, `SPRITE3` = the 4-bit halberdier of
  `SPRITE3.BTP` + a shield, a portrait and a landscape, `ICON2` = an older icon set (31 of its 49
  frames are byte-identical to `ICONS`).

`FILE/BINARY` has 288 `.FOL` and 288 `.BOP` files, but only **287 pairs**: `ICONSTMP.FOL` has no
`.BOP` (it indexes an older, 341976 B version of `ICONS.BOP`, and holds all 84 type-2 frames that
have no `.PAL` of their own; an engine should ignore it) and `SPRITE30.BOP` has no `.FOL`.
Every other `.FOL` has a counterpart with the same name: a `.BOP` with the actual pixel data.

Example: `SPARKLE.FOL` (208 bytes = 13 animation frames), each frame 32×32,
`bop_offset` grows unevenly between frames (because the data in `.BOP` is compressed
and variable-sized).

## `.BOP` — pixel data (Bitmap Of Pixels?)

**Fully reverse-engineered and visually verified.**

`.BOP` has no header: it is just concatenated frame segments, addressed from `.FOL`.
How a segment is read depends on the frame type (`kind & 0x0F`):

| Type | Segment data | Segment size | Colors | Examples | Verification |
|---|---|---|---|---|---|
| `1` | raw **8 bpp** | `w × h` | direct `STANDARD.PAL` indices | backgrounds `BACK*`, portrait `DWA4`, `ICONS` | `samples/back1.png` |
| `2` | raw **4 bpp** (2 pixels/byte) | `ceil(w/2) × h` | map from `.PAL` | large banner `BANWBRI` frame 0 | render of the Bright Wizard banner |
| `4` | **4 bpp + zero RLE** | variable | map from `.PAL` | units, effects, spells, small banners | `samples/eshin.png`, `samples/sparkle.png` |

All rows run top to bottom, pixels left to right, with no row padding apart from
the `ceil(w/2)` rounding at 4 bpp. With an odd width the last nibble of a row
is skipped (9 such frames, they decode correctly).
Color index 0 = transparent.

Verified on all 288 `.FOL`/`.BOP` pairs from `FILE/BINARY` (8354 frames):
- type 4: each of the 7279 frames decompresses to exactly `ceil(w/2) × h` bytes
  and hits `00 00` exactly at the end of its segment;
- types 1 and 2: segment size = `w × h` or `ceil(w/2) × h`;
- renders: Eshin assassins (several directions), fire bolts and fireballs
  from `SPELLS` in several rotations, a dwarf portrait with mouth frames (`DWA4`), the
  `BANWBRI` banner, the sparkle and snowman from `SPARKLE`.

Reference implementation: `scripts/render_sprites.py`.

### Compression (type 4)

First the image is packed to 4 bpp: the upper nibble is the left pixel, the lower one the right pixel,
rows are `ceil(w/2)` bytes long. Then the resulting byte stream is compressed
**for zeros only** (0 = transparent), linearly across the whole frame, ignoring row boundaries:

```
00 NN   -> NN bytes of 0x00 (NN = 1..255, longer gaps = several pairs)
00 00   -> end of frame
XX      -> (XX != 0) one literal byte = two pixels
```

Example, `SPARKLE` frame 0 (32×32, i.e. 512 packed bytes):
`00 f8 | 30 | 00 ff | 00 08 | 00 00` = 248 bytes skipped, byte `30` (a pixel
of color 3 at (16,15), the center), 255+8 skipped, end. 248+1+255+8 = 512.

Notes:
- A literal byte is never `00`, so a byte with two transparent pixels
  is always emitted as `00 01`. A byte with one transparent pixel (e.g. `30`)
  is an ordinary literal.
- Gaps are not aligned to rows: a single `00 NN` pair can cross the end of
  a row (e.g. "the rest of this row + the start of the next one").
- The encoder split gaps longer than 255 into several pairs (`00 ff 00 08`).

The earlier "skip/count/color triples and two layers" hypothesis was wrong:
the data was read as 8-bit pixels, so the `00 NN` pairs looked like triples,
and the excess bytes like a second layer. A segment has no layers.

### Color map

Types 2 and 4 turn bytes into palette indices using one 512-byte map from `<NAME>.PAL`
(variant B, described above under `.PAL`). Frames of types 2/4 are stored **grouped by map, in
increasing map order**, and the upper nibble of `kind` holds the map number **modulo 16**:

```python
wraps, prev = 0, None
for rec in fol:                       # frames of types 2 and 4 only, in file order
    n = rec.kind >> 4
    if prev is not None and n < prev:
        wraps += 1
    rec.map = n + 16 * wraps
    prev = n
```

This only matters for `SPELLS` (43 maps: frames 0–292 → maps 0–15, 293–528 → 16–31,
529–598 → 32–42). Verified structurally on all 141 files with variant B palettes (with the rule,
every map is used by exactly one contiguous group) and visually: with the plain nibble the later
spells render in the fire orange of the first maps, with the full index they show white skeletons,
blue ice and black skulls. Examples:
- `SPARKLE.PAL`: 2 maps. Frames 0–4 (sparkle) have `kind = 04`, and frames 5–12 (snowman) `14`.
- `ESHIN.PAL`: 4 maps, `kind` from `04` to `34` (the move, dead, attack and stand animations).

`scripts/render_sprites.py` implements the rule (`colormap_indices`).

### Reference decoder (C pseudocode)

```c
// input: seg = bop + fol.bop_offset, w/h from .FOL, cmaps = contents of <NAME>.PAL
// output: out[w*h] = STANDARD.PAL indices, 0 = transparent
int type = fol.kind & 0x0F, map = fol.map /* full index, see "Color map" */, bw = (w + 1) / 2;

if (type == 1) { memcpy(out, seg, w * h); return; }

uint8_t packed[bw * h];
if (type == 2) {
    memcpy(packed, seg, bw * h);
} else {                                   // type == 4
    uint8_t *p = packed;
    for (;;) {
        uint8_t b = *seg++;
        if (b != 0) { *p++ = b; continue; }
        uint8_t n = *seg++;
        if (n == 0) break;                 // 00 00 = end of frame
        memset(p, 0, n); p += n;           // 00 NN = NN zero bytes
    }
}

const uint8_t *cm = cmaps + 512 * map;
for (int y = 0; y < h; y++)
    for (int x = 0; x < w; x++) {
        uint8_t b = packed[y * bw + x / 2];
        out[y * w + x] = cm[b * 2 + (x & 1)];
    }
```

### Open questions (sprites)

- The meaning of bytes 13–15 (`flags[1..3]`); they do not affect decoding.
- Which `SPELLS.PAL` map belongs to which spell, and when the game uses the second livery of
  `NLNHLB` (maps 4–7).
- The real colours of the raw 4-bit halberdier frames in `SPRITE3.BTP`/`SPRITE3.BOP`.
- Whether the game loads any of the leftovers (`SPRITE3.*`, `SPRITE30.BOP`, `HALBERD.*`, `ICON2.*`,
  `ICONSTMP.FOL`, `TESTSPR.PAL`, `SYS.PAL`). No string refers to them; logging file opens under
  Wine would settle it.

## Sprite animation layout (directional sets)

**Layout reverse-engineered and verified visually; the `dir` mapping and frame timing are open.**
Report: `notes/animations.md`. Export to sheets and animated GIFs: `scripts/anim_export.py`.

72 of the `.FOL/.BOP` sets are **directional sprites**: units, characters, monsters, artillery,
vehicles and animals, 6464 frames in total. They are recognised by: every frame of type 4,
bytes 13–15 = `02 04 40`, bytes 0–1 = 0, and every group a multiple of 8 frames. The other sets
are 45 portraits (frame 0 is 120×152, followed by mouth/eye overlays), 69 single frames
(backgrounds, plan maps) and the rest (banners, icons, `SPELLS`, `GENBATT`, tile animations).

- A **group** is a maximal run of frames with the same color map (see "Color map"). Each group is
  one animation strip with its own 16 colours.
- A group of `n` frames has `n / 8` phases, and `frame = group_start + phase × 8 + direction`.
  All 8 directions are stored; nothing is mirrored.

| direction | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| on screen | N (back to the viewer) | NW | W | SW | S (facing the viewer) | SE | E | NE |

Standard unit set (37 files; 11 more files with archers and wizards add a fifth group):

| frames | group | action | phases |
|---|---|---|---|
| 0–31 | 0 | move (walk/gallop) | 4 |
| 32–39 | 1 | dead (corpse; often 64×64 even for 32×64 units) | 1 |
| 40–71 | 2 | attack (melee) | 4 |
| 72–103 | 3 | stand (idle) | 4 |
| 104–111 | 4 | shoot / cast (archers and wizards only) | 1 |

Example: `ESHIN` has 104 frames = 8 directions × 13 columns (4 + 1 + 4 + 4). Other patterns are
listed in the report: artillery and wagons have an intact and a wreck group (group 1 is always the
wreck), `PEASANT` has 3 characters × 4 actions, and `WAGON`, `MORTAR`, `DOOMDIVR` and `DRAGON` have
their own layouts.

**Anchor.** In directional sets byte 3 of the record is the anchor x (≈ width / 2) and byte 2 is the
anchor row counted from the frame bottom, probably the foot line (a statistical fit only). Portraits
use bytes 0–3 as `int16 x, y` instead. 10 single frames have an anchor that differs from the rest of
their group and look shifted; an engine should use the group's majority anchor.

Verification: an automatic mask comparison (next phase vs next direction) fits `phase × 8 + direction`
in 173 of 178 multi-phase groups, and the other 5 are correct by eye; 31 sets were inspected on
labelled, anchor-aligned sheets; a group rendered with another group's map gives garbage colours.

Open: how the script `dir` (0..511) maps to the 8 directions, frame timing, some uncertain action
labels, and the layouts of the effect sets `SPELLS` and `GENBATT`.

## Leftover files: `SPRITE3.BTP`, `SPRITE30.BOP`

`SPRITE3.BTP` is **not** a lookup table: all LUT tests fail (values only 0..15, the diagonal matches
1 of 256, a 50% blend matches 8 of 27966 entries). It is a byte-identical copy of
`SPRITE3.BOP[0:65536]`: 32 raw frames of 32×64, one byte per pixel with 4-bit values
(0 = transparent), a halberdier in 8 directions × 4 walk frames. `SPRITE30.BOP` is the same strip
with frames 0–1 edited. Nothing in the executables refers to these files; like `HALBERD.*`,
`ICON2.*`, `ICONSTMP.FOL` and `TESTSPR.PAL` they are development leftovers of the 4 bpp sprite
pipeline. Report: `notes/btp_sprite_leftovers.md`.

## `.BTS` (battle) and `.MRC` (army) scripts, `FILE/SCRIPT/` directory

**Syntax fully reverse-engineered; battle layout visually verified** (see
`samples/bf001_battle.png`). The semantics of some fields are still hypotheses (marked below).
Parser: `scripts/whscript.py`, renderer: `scripts/render_battle.py`.

Contents of `FILE/SCRIPT/`: 54 × `.BTS`, 33 × `.MRC` (including `MARCH.MRC`), 45 × `.DLL`, 1 × `.DBF`.
These are **text** files, not binary data. They were generated by the developers' editor:
- `WHSHR.EXE`/`GAMEF.DLL` contain file dialog filters `script {*.bts}`, `mercs {*.mrc}`, `mesh {*.asc}`;
- every unit contains the comment `;S_RACE is Human Infantry...are you sure this is right?`,
  coming from the format string `;S_RACE is %s %s...are you sure this is right?` in the EXE;
- numbered comments `; unit N`, `;Collision Object N`, `;piece N`, `; Script Node N`.

Developer test files (not part of the campaign): `_DESTEST`, `_KFTEST`, `RLTEST`, `RLTEST1`,
`WIZTEST`, `SPRED`, `MAXARMY`, `PLOT1`. The files `B` and `DB015` have no `BFxxx` numbering
and use other battles' scripts (`bf004_1`, `bf015`), so their status is uncertain.

### Syntax (shared)

- ASCII/latin-1, CRLF line endings. Tab indentation is insignificant.
- `;` at the start of a line is a comment. A comment can also follow `[END]` (`[END]\t; end of FIELD`).
- `[NAME]` opens a section, `[END]` closes the innermost one. Root: `[BATTLESCRIPT]` or `[MERCARMY]`.
- Every other line is `command:argument` (split on the first `:`):
  - `set:key=value`: a numeric or text field; flags combined with `|` (`os_active|os_solid`);
  - `setstats:key=a,b,c`: a list of integers;
  - flag commands with an empty argument: `hidden:`, `DeployTroops:`, `NoBirds:`;
  - keys containing spaces: `Ambient light color:`, `Bank angle:`.
- Blocks (case-insensitive; the files contain both `addunit` and `AddBoundary`):
  `addunit…endunit`, `addleader…endleader` (inside a unit), `addobject…endobject`,
  `addrectangles…endrectangles` (inside an object), `addnode…endnode`, `AddBoundary…EndBoundary`.
- In names, `<` and `_` stand for a space: `Grudgebringer<Cavalry`, `Hiln's_Guard`, `Cmdr._Bernhardt`.
- Boundary names and paths are not normalized (`Cameraedge`, `Battlefield edge`, `\bf001.mrc`,
  `\Bf012.mrc`), so compare them case-insensitively and look up files the same way.

**Counters:** `set:count` in `[UNITS]`, `[SCENERY]`, `[BOUNDARIES]` and `[NODES]`, as well as
`set:Lines` (total of `AddLine`), match the contents in 83/87 files. The only exceptions are
test files (`ARMY.MRC`, `RLTEST.BTS/.MRC`, `SPRED.BTS`). **`[OBJECTS] set:count` never
equals the number of `addobject` blocks** (in 25/54 files = objects + all units,
in the rest it deviates by −8…+9). An engine should ignore it and count the blocks.

### Coordinate system

- World units. `[FIELD] set:x/y` = battlefield size (from 1280 to 2960 on each axis).
  `BattleEdge` is usually a rectangle inset by 16 from the edges.
- **The Y axis grows up the plan map** (as in mathematics, not as in an image). The plan map
  (`loadplanmap`, e.g. `MAP001`, 196×216 px for a 1600×1760 field, scale ≈ 1:8.16 on both axes)
  covers exactly the whole field. Verified on `BF001` and `BF005`: only after flipping Y
  do the collision circles lie on trees and rocks, and the boundaries run along the river, cliffs
  and forest edge.
- Coordinates can go beyond the field (`CameraEdge` reaches −300; in `BF001` the crossbowmen stand
  at x=1814 with a field width of 1600 — hypothesis: reinforcements arriving later).
- `dir` and the fourth number of `placefurniture` take values 0…511 (max observed 504).
  **Hypothesis:** a full turn = 512. The zero point and direction of rotation are unverified.

### `.BTS` — sections

Order in the files: `FIELD`, `MISSIONINFO`, `DYNAMIC_LOAD`, `OBJECTS`, `SCENERY`,
`BOUNDARIES`, `UNITS` (1 or 2 sections), `NODES`.

| Section | Contents |
|---|---|
| `FIELD` | see the table below |
| `MISSIONINFO` | `DeployTroops:` (the player deploys the troops), `Objective:L,a,b` (see "Mission objectives" below) |
| `DYNAMIC_LOAD` | resources to load: `loadspr:Name,n` (sprite sets, e.g. `BattleSprites` → `GENBATT`), `loadsfx:Name` (sound packages, see "Sound effects"), `loadfurn:Type` (3D scenery objects used in `SCENERY`, see "Name tables"), `NoBirds:` |
| `OBJECTS` | collision objects: `set:status` (`os_active`, `os_solid`, rarely `os_camcollide`), `x`, `y`, `z`, `radius`, `dir`. Optionally `addrectangles:=N` with `rect:x1,y1,x2,y2`, i.e. rectangles relative to the object's center, presumably rotated by `dir`. `z` is not the terrain height under the object (probably the object's own height) |
| `SCENERY` | `placefurniture:Type,x,y,dir`: trees, rocks, buildings. `Type` is resolved through the furniture table to a `.XOF` mesh in the battle's `SCENERY.PBX`. The `D_` prefix (e.g. `D_SnwWatchTower`) is the destroyed variant, with its own mesh (e.g. `TPINEL_D`) |
| `BOUNDARIES` | `AddBoundary:Name` + `AddLine:x1,y1,x2,y2`, i.e. named polylines. Names: `BattleEdge` (field boundary), `ViewEdge`, `SightEdge`, `CameraEdge`, `DeploymentArea`/`Merc Deployment` (deployment zone), `Nav1…NavN` (navigation obstacles along impassable terrain), terrain ones: `CliffsEdge`, `RiverEdge`, `WallsEdge`, `Hedge`, `LakeEdge`… |
| `UNITS` | units (format below). Label from the comment: `; Enemy Army` (54), second section `NPC units` (27) |
| `NODES` | nodes for the mission script: `set:status` (`ns_active`, `ns_startpos`, `NS_END`), `x`, `y`, `radius`, `dir`, `id` (usually 0; also 1–13 and 99). Chains of `ns_startpos` lead to the deployment zone. **Probably each `NS_END` is the target position of one player unit**: in 41/44 campaign battles the number of `NS_END` nodes = the number of player units, and there are usually a few more `ns_startpos` nodes. But only in 8/44 do the units from `.MRC` stand exactly on these nodes, so the positions in `.MRC` are usually not starting positions. 501 of 547 player units have `hidden:`, which fits the army being brought onto the field by the script or by deployment (statistics: `scripts/battle_atlas.py`) |

`[FIELD]`:

| Field | Meaning |
|---|---|
| `set:x`, `set:y` | battlefield size |
| `set:map` | 17, 18, 19, 34, 35, 49, 50 — meaning unknown |
| `loadmerc:\bf001.mrc` | player army (`.MRC`). In 29 battles this is **another** battle's file (e.g. `BF006–BF008` → `bf001.mrc`), presumably because the army carries over through the campaign |
| `loadmesh:bf001` | directory `FILE/MESH/BF001/` (terrain and 3D resources, see below) |
| `loadpal:standard` | RGB palette: `standard`, `bkmount`, `underway`, `night` |
| `loadScript:bf001` | mission logic `FILE/SCRIPT/BF001.DLL` (test files use `bf003`) |
| `loadplanmap:MAP001` | plan map, frame 0 of `MAP001.FOL/.BOP` (type 1, 8 bpp) |
| `loadportbg:BACK14` | portrait background |
| `Ambient light color`, `Position`, `Bank angle` | floats; almost always zeros (test values 1,2,3… in 2 files) |
| `Camera:45.0` | 0/45/90/135/180/270 — presumably the initial camera rotation |
| `set:vx`, `set:vy`, `set:zoom` | only in 1 file; presumably the initial view |

### Mission objectives (`Objective:L,a,b`)

**The letter is solved** (report: `notes/pe_resources.md`, script: `scripts/pe_missions.py`).
With `i = L − 'A'`, string `33000 + i` in `GMTXT.DLL` is the objective caption shown in battle, and
strings `1001 + i` / `2001 + i` in `BKTXT.DLL` are the failure / success lines of the debriefing.
The captions agree with the briefing of every mission checked, for example:

| Letter | Caption | Battles |
|---|---|---|
| A | Eliminate the enemy | 47 battles |
| B, C | placeholders `A_MASTER`, `C_MASTER`; debriefing: villagers saved / buildings destroyed | BF003 (Protect Schnappleburg), BF004_x… |
| D | Protect the wagons | BF005, BF006 (Escort to Holst) |
| E | Leave no survivors | BF007, BF025 (Patrol) |
| I | Ambush. | BF026, BF029–031, BF042 |
| N | Get past the Dragon | BF014 |
| O | Capture Guy Gourard | BF009 |
| Q | Protect the forest | BF024 |
| S | Capture Hiln. | BF001 |
| T | Rescue Ilmarin. | BF010 |
| W | Destroy the enemy artillery. | BF017, BF027 |
| Z | "Silent Stay alive!" (hidden loss condition) | 50 battles |

Captions starting with "Silent" are apparently not shown to the player. **The numbers are partly
solved**, checked on all 54 `.BTS`:
- `A`: `a, b` = total men and number of enemy regiments (39/47 exact);
- `Z`: men and regiments of the player army from `loadmerc` (40/50; the misses are battles with NPC
  allies or reinforcements);
- `B`: `b` = villagers, i.e. NPC men (9/11); `D`: `b` = the number of wagons.

The numbers look like a snapshot that the editor wrote when saving. For `K`, `X`, `R`, `I`, `P`, `V`
they are unknown.

### `.MRC` — army

Root `[MERCARMY]`, containing `[UNITS]` (label `; Mercinary Army` or
`; Mercenary Army (Marching Orders)`) and sometimes `[MISSIONINFO]` (`ARMY.MRC`, `SPRED.MRC`).
Loaded from `.BTS` via `loadmerc`. `MARCH.MRC` is present both in `FILE/SCRIPT/` and in `SAVE/`,
so it is presumably the current state of the army in the campaign.

### Unit (`addunit`), shared by `.BTS` and `.MRC`

```
addunit:Grudgebringer<Cavalry          name ('<'/'_' = space)
    hidden:                            optional: hidden at start (hypothesis)
    set:whoami=2                       0 for ordinary enemies; 1..100 for named units (hypothesis: persistent campaign ID)
    set:hired=0                        0/1: mercenary paid (hypothesis)
    troopsprites:BorderHorse,0         sprite set → .FOL via the sprite table ("Name tables"); ",0" is always 0
    banner:BannerMrcCmdr,0             banner
    addmagicitem:ItemGrudgeBringer     0..n
    addspell:AmberTanglingThorn        0..n (wizards)
    set:psy_status=HateSkaven|CantBreak  psychology from the tabletop rules, see below
    setstats:s_side=2,12,12,4          see below
    setstats:s_move=4,4,3,3,3,1,3,1,7  profile M WS BS S T W I A Ld
    setstats:s_mount=1,13,3,16,13,0    s_mount[0] = 1 for cavalry, 0 for infantry; the rest unknown
    setstats:s_weap=3  S_BalWeap=0  s_pntval=13  s_cmdr=0,0,4,0  s_armname=0,4   (not exactly known; s_pntval ≈ points value)
    setstats:s_armr=5                  armor (only on some units and leaders)
    setstats:s_rlmv=…  s_lead=…        rare (6 units, 9 numbers)
    set:s_calualties=0 s_routed=0 s_kills=0 s_Exp=0   campaign state/experience
    ;S_RACE is Human Cavalry...are you sure this is right?
    addleader:Cmdr._Bernhardt          optional leader
        leaderportrait:Commander,0     (VoidType,0 = no portrait)
        troopsprites:… setstats:s_move=… s_armr=… s_weap=… s_armname=…
    endleader:
    set:dir=0  set:x=1097  set:y=645
    set:script=PLAYER_SCRIPT           or a number (0..27): AI script instance from the mission DLL (hypothesis, cf. the DLLReturnInstCount export)
endunit:
```

**`s_move` = the tabletop Warhammer profile** (M, WS, BS, S, T, W, I, A, Ld). Confirmation:
Clanrats `5,3,3,3,3,1,4,1,5` is exactly the Clanrat profile from the rulebook; human infantry has `4,3,3,3,3,1,3,1,7`.

**`s_side = [type, size, initial_size, ?]`.**
- `s_side[1] == s_side[2]` in 829/869 units. Following the order of names in `GAMEF.DLL`
  (`s_rnks s_size s_orgsize s_side`) these are presumably the current and initial unit strength.
- `s_side[3]` takes values 1–7; hypothesis: number of ranks.
- `s_side[0]` is a bit field. Decoded by cross-referencing it with the `;S_RACE is …` comments
  in all files:
  - bit 7 (`0x80`) = **enemy side**: all Skaven, Orcs and Goblins, as well as human enemies (`129` = Human Infantry);
  - bit 6 (`0x40`) = presumably the neutral/NPC side: `RollingStock` (wagons), `Peasant`, allies;
  - bits 0–5 = unit type (dominant label):

| code | type | code | type | code | type |
|---|---|---|---|---|---|
| 0 | monster | 7 | Skaven (infantry/wizards/monsters) | 14 | Peasant |
| 1 | Human Infantry | 8 | Orc Infantry | 15–17 | Human Artillery |
| 2 | Human Cavalry | 9 | Orc Cavalry | 18 | Orc Artillery |
| 3 | Human Archers | 10 | Orc Archers | 19 | Human Wizard |
| 4 | Dwarven Infantry | 11 | Goblinoid (infantry, wizards, artillery, monsters) | | |
| 5 | Dwarven Archers | 12 | Goblinoid Cavalry | | |
| 6 | Elven | 13 | Goblinoid Archers | | |

  The S_RACE comment does not always match the code (e.g. code 3 is sometimes "Human Cavalry").
  The editor apparently computed it from another field (`s_race`) and warned about the mismatch.

**`psy_status`** (`|` flags): `HateGreens`, `HateSkaven`, `HateDwarfs`, `FearToGobs`,
`CauseFear`, `CauseTerror`, `Frenzy`, `CantBreak`, `CantRally`, `CantMelee`, `CantDie`,
`PsyImmune`, `MagicResistent`. These are the psychology rules from tabletop Warhammer.

### Parser

```
python3 scripts/whscript.py .../FILE/SCRIPT/BF001.BTS          # summary
python3 scripts/whscript.py .../FILE/SCRIPT/BF001.BTS --json   # full view (including the army from loadmerc)
python3 scripts/whscript.py --check .../FILE/SCRIPT            # all files + counters
python3 scripts/render_battle.py .../FILE/SCRIPT/BF001.BTS out.png 0.5
```

### Open questions (scripts)

- Meaning of `set:map`, `whoami`, `s_side[3]`, `s_mount[1..]`, `s_cmdr`, `s_armname`, `s_weap`,
  `S_BalWeap`, and of the numbers of most objective letters.
- The `,N` after `troopsprites`/`banner`/`leaderportrait`/`loadspr`: 0 in all 3314 uses, and when it
  is missing (`loadspr:Wagon`) the file is not packed. Hypothesis: a colour or variant selector.
- The zero point of `dir` and whether a full turn is 512.
- Units packed in a battle's `SPRITES.PBX` but not declared in its `.BTS` (20 of 44 campaign battles).
  Hypothesis: the mission DLL spawns them.

## Mission logic — `FILE/SCRIPT/BFxxx.DLL`

Real **PE32 Win32 (i386) libraries, compiled with MSVC**, about 24–29 KB, mostly
C runtime. Internal name `dll.dll`. Exports: `DLLGetScriptPointer`, `DLLReturnInstCount`.
The game loads them via `script\%s.DLL` (message `Failed to load Script DLL %s`).
Hypothesis: `DLLGetScriptPointer` returns a table of AI/trigger functions, and units refer
to them via `set:script=N`. **To be investigated by disassembly** (e.g. Ghidra).
An open engine would have to rewrite these scripts by hand. The campaign flow around the battles
(briefings, mission choice, debriefings, movies) is not native code but text: the glue scripts in
`WND.DLL` (see "PE resources").

## Name tables (script names → files)

**Reverse-engineered; every name used by a campaign file resolves.** Report: `notes/sprite_names.md`,
builder: `scripts/spritemap_build.py` (writes `extracted/sprite_names/map.json`).

The CamelCase names in the scripts are resolved through two arrays of fixed-size records in the
`.data` section of `WHSHR.EXE` (image base `0x400000`). `GAMEF.DLL` contains the same two tables
byte for byte (only 12 code pointers differ, because of relocation). `BITMAP.DLL` plays no part.

```c
struct SpriteName {          // 64 B; 220 records at VA 0x5AA808 (file offset 0x65408)
    uint32_t runtime0;       // 0 in the file
    char     name[16];       // name used in scripts, NUL-padded
    char     file[16];       // 8.3 base name of NAME.FOL/.BOP/.PAL ("" = no 2D sprite)
    uint8_t  runtime[28];    // 0 in the file, filled at load time
};

#pragma pack(1)
struct FurnitureName {       // 60 B; 402 records at VA 0x5ADF08, right after the sprite table
    uint32_t runtime0;
    uint8_t  flags;          // groups: trees, buildings, rocks, roads, hedges... (meaning: hypothesis)
    char     name[16];       // name used in loadfurn/placefurniture
    char     file[16];       // 8.3 base name of a 3D mesh FILE.XOF in MESH/<battle>/SCENERY.PBX
    uint8_t  pad;
    uint16_t dims[4];        // small numbers, only for buildings/tents/bridges; meaning unknown
    uint16_t pad2;
    uint32_t code[3];        // function pointers for 12 animated objects (mills, crypt, portcullis...)
};
```

The sprite table is grouped into contiguous categories, and each command looks names up in its own
category (`Engrol` is both a troop and a portrait):

| Indices | Category | Used by |
|---|---|---|
| 0 | `VoidType` = none | `troopsprites`, `banner`, `leaderportrait` |
| 1–3 | effects: `BattleSprites` → `GENBATT`, `SpellSprites` → `SPELLS`, `Sparkle` | `loadspr` |
| 4–78 | troops (`MercCaptain` → `MCCAPT` … `RockLobber` → `ROCKLOB`) | `troopsprites`, `loadspr` |
| 79–122 | leader portraits (`Commander` → `COMM`, `EshinAss` → `SKA4` …) | `leaderportrait` |
| 123 | `AllBGs` → `BACKALL` | ? |
| 124–186 | banners (`BannerMrcCmdr` → `BANMC` …) | `banner` |
| 187–214 | animated terrain tiles (`u_water`, `Lava*`, `BFK_*`, `TorFlam`, `Beam`) | `loadspr` |
| 215–219 | placeholders `PlanMap`, `PortBG`, `VoidBin`, `Buttons` → `icons`, `Portrait` | engine |

- A name always means the whole `.FOL`; there are no frame ranges. File names are not always derived
  from the name (`BorderSwordMen` → `BODYGRD`, `Marius` → `CELE`) and case is inconsistent, so match
  files case-insensitively.
- `loadplanmap` and `loadportbg` take the 8.3 file name directly.
- Furniture records 1–52 are missile and spell effects (`Arrows*`, `Explosion1..8`…) whose meshes
  are packed into almost every `SCENERY.PBX`.

Verification: all names from all 87 scripts were resolved (the few unresolved names occur only in
developer test files); the meshes predicted from `loadfurn` equal the contents of `SCENERY.PBX`
exactly in all 44 campaign battles; the sprite sets predicted from the `.BTS` are all present in
`SPRITES.PBX` in 36 of 44 battles; renders of `ClanRats`, `BorderHorse`, `EshinAssassin`, `MercXbow`,
two banners and the `Commander` portrait match their names.

## PE resources — `FILE/DLL/*.DLL`, `WHSHR.EXE`

**Extraction ✅ (1669 resources); glue script semantics 🟡.** Report: `notes/pe_resources.md`.
Scripts: `scripts/pe_resources.py` (PE resource directory parser), `scripts/pe_extract.py`
(to PNG/JSON/TXT), `scripts/pe_missions.py` (missions table, objective checks).

| File | Resources | Contents |
|---|---|---|
| `BITMAP.DLL` (10.9 MB) | 717 × `RT_BITMAP` | full-screen UI (title, main menu, loading, defeat), the caravan hub, the campaign map with route animation cells, book pages and ornaments, 79 encyclopedia portraits, buttons |
| `WND.DLL` | 535 × `RT_RCDATA` | **text scripts of the campaign "glue" language** (originally `.wnd`/`.run` files) |
| `GMTXT.DLL` | 184 strings | battle messages, spell and item names, profile abbreviations, objective captions (33000+), regiment shouts |
| `BRTXT.DLL` | 708 strings | mission names (601–691), campaign chapters (500–507), map labels, briefing dialogue (`B × 1000 + 10k + j`), voice-line labels (9500+) |
| `BKTXT.DLL` | 422 strings + 79 × `RT_RCDATA` | races, roster, debriefing lines (1000+/2000+ per objective letter), balance sheet, credits; 79 encyclopedia texts `<NAME>TEXT`, 72 of which pair with a `<NAME>PIC` portrait |
| `ANTXT.DLL` | 107 strings | cutscene subtitles, `M × 1000 + k` (M = movie number) |
| `DLGGMTXT.DLL`, `WHSHR.EXE` | dialogs, menus, cursors, icons | the Win32 "Warhammer Options" dialog, debug menus, named cursors (`SWORDCURSOR`…) |
| `GMCUR.DLL` | 4 cursors | 32×32 battle cursors |
| `GAMEF.DLL` | none | — |

- **Bitmaps** are uncompressed 8 bpp DIBs with a full 256-entry palette (verified size formula on all
  717). Index 0 = (0,0,255) blue is the colour key. Resource names are the ones used by the glue
  scripts (`setbitmap:Caravan` → `CARAVAN`; animations are numbered frames `NAME1..N`).
- **Strings** use the standard Win32 block layout. Text markup in `GMTXT`: `@@(fN)` = font N,
  `@@(cN)` = colour N, `_` = space.
- **Glue scripts** (`WND.DLL`) use the same syntax family as `.BTS`: `[SECTION]…[END]`,
  `command:argument`, `set:key=value`. `[WINDOW]` sections describe screens (`[POSITION]`, `[BITMAP]`,
  `[TEXT]`, `[HOTSPOT]`, `[ANIM]`, `[MIDI]`); `[RUN]`/`[START]` sections are scripts (`openwindow`,
  `playtext`, `playmidi`, `playmovie`, `setbattlescript`, `encounterplaygamewithdebrief`, `addtroop`,
  `unitjoinmission`, `testobjective`, `iftrue*`/`iffalse*`, `gosub`/`goto`, `autosave`…). Name
  prefixes are campaign chapters (`BP` Border Princes, `RE` Revenge, `BM` Black Mountains, `WE` Worlds
  Edge, `SZ` Zhufbar, `EN` Nuln, `GM` Grey Mountains, `L` Loren). A `[MISSION]` block ties a mission
  together:

  ```
  [MISSION]
      set:res=601                 mission name: BRTXT 601 "Protect Schnappleburg"
      res:BPBrief1                briefing script
      setbattlescript:bf003       battle FILE/SCRIPT/BF003.BTS
      setmissionscript:BPMission1 script that runs the battle
      cash:1,100,400,50,25,A      hypothesis: type, advance, completion fee, per unit, penalty, paying objectives
  [END]
  ```

  `python3 scripts/pe_missions.py <WARFB>` prints the full mission ↔ battle ↔ briefing table.

## Front-end fonts and palettes

**Fully reverse-engineered and verified visually.** Report: `notes/fonts_glue.md`. Scripts:
`scripts/fon_parse.py`, `scripts/fon_glue_palettes.py`.

**`.FON`** files are ordinary Windows 3.x bitmap fonts: a 16-bit NE executable with one
`RT_FONTDIR` and one `RT_FONT` resource (id 1001) in FNT 2.0 or 3.0 format. Glyph bitmaps are
1 bpp, `dfPixHeight × ceil(width / 8)` bytes, and **stored column by column** (all rows of byte
column 0, then byte column 1…), as in Windows' own fonts; a row-major reader turns glyphs wider
than 8 px into stripes. All fonts are bold, cp1252, proportional, characters 0x20–0xFF.

| File | Face name | Look |
|---|---|---|
| `GLUE/MAPTEXT1.FON` | Warhammer Font 1 | serif capitals only |
| `GLUE/PCTEXT.FON`, `GLUE/PCTEXTB.FON` | Warhammer Font 2 / 6 | body text, regular / bold |
| `GLUE/SMAPTEX1.FON` | Warhammer Font 3 | small serif, letters only |
| `GLUE/SUBTEXT.FON` | Warhammer Font 4 | Times-like serif |
| `GLUE/GOTHTEXT.FON` | Warhammer Font 5 | blackletter, the only complete character set |
| `PCTEXTA.FON`, `PCTEXTAB.FON`, `PCSUBT.FON` (battle, `GAMEF.DLL`) | WarhammerA, WarhammerABold, WarhammerSubText | the same glyphs as `PCTEXT`, `PCTEXTB`, `SUBTEXT` under other face names |

**Front-end palettes** (`FILE/BINARY/GLUE/*.PAL`, variant A) come in pairs that together fill the
236 free indices: `GLUE<screen>.PAL` = 10–105 and `WIND<screen>.PAL` = 106–245. Comparing the colour
tables of all 717 bitmaps with every palette gives exact matches for `TITL` (title screen), `MIND`
(Mindscape logo), `END`, `CAR` (caravan), `MAP` (campaign map), `BK2` (33 regiment portraits) and
`BOOK` (magic pictures). `GLUEREND` is not referenced but matches `TROOPBOOK`; no bitmap matches
`GAME` or `OPT`. Screens drawn only from these palette files look correct, and a wrong pair gives
garbled colours.

## Music — `MUSIC/*.MID` and `SOUND/WARINTR3.SBK`

**Formats ✅; no full render has been listened to yet.** Report: `notes/music.md`. Scripts:
`scripts/music_midi.py`, `scripts/music_sf2.py`, `scripts/music_sbk2sf2.py`, `scripts/music_render.py`.

- The music is **standard MIDI** (SMF format 1): 21 compositions, each as a General MIDI file
  (`INTRO3.MID`) and an FM file for OPL cards named with the first 6 characters + `FM`
  (`INTRO3FM.MID`, `SIGHTEFM.MID`); `VICTORY` has no FM version. `MIDI.DLL` picks the variant.
- `WARINTR3.SBK` is a **SoundFont 1.0** user bank for the AWE32 (not SoundFont 2) with only
  **3 presets**: two choirs (programs 52, 54) and `WarBrass` (57). The MIDI files select them with bank
  select CC0 = 1; every other instrument and all drums came from the AWE32's 1 MB GM ROM, which the game
  does not ship.
- SoundFont 1.0 differs from 2.0 in a few chunks: a `snam` sample-name chunk, 16-byte sample headers
  with no sample rate or root key, empty modulator chunks. The rate (44100 Hz) and the root key
  (generator 55, in cents) were established by pitch measurement. `music_sbk2sf2.py` converts the bank
  to SF2 for FluidSynth; the filter, modulation-envelope and LFO settings are dropped because their
  SF1 units are unknown.
- Where the tracks play (16 of 21 located): `title` main menu, `generic` campaign map, `sighted` start
  of a mission, `combat` ambushes, `scribe` caravan screens, `win`/`lose` debriefings, and one track per
  race for the cutscenes; `battle`, `forest`, `lookin2`, `tense` and `victory` are not located.

## Sound effects — `.SFX` and WAV

**Fully reverse-engineered, confirmed against the reader/writer in `MSNDDS.DLL`; not listened to.**
Report: `notes/sfx.md`. Scripts: `scripts/sfx_parse.py`, `scripts/sfx_wavstats.py`.

A `.SFX` file is a package of named effects that refer to external WAV files; it contains no audio.

```
"RIFF" u32 total_size      // = the whole file size (not size - 8)
"MSFX"
"INFO" u32 4    { u16 n_samples; u16 n_sfx; }
"SFX " u32 60*n_sfx  SfxRecord[n_sfx]
"SMP " u32 0             // empty in the current format
"LIST" u32 n             // for LIST effects: 1-based effect indices, each list ended by a u32 0
"NAME" u32 n             // n_samples NUL-terminated WAV paths
"SFID" u32 n             // n_sfx NUL-terminated effect names
00 × 18..20              // writer slack
```

```c
struct SfxRecord {             // 60 B
    uint32_t unk00;            // 0xFFFFFFFF
    uint32_t priority;         // 0..80
    uint32_t unk08, unk0c;
    uint16_t flags;            // 0x01 INTERRUPTABLE, 0x02 LOOP, 0x04 LIST, 0x08 RANDOM, 0x10 3D
    uint16_t unk12;
    uint32_t unk14;
    uint32_t pitch;            // playback rate in Hz (11025 = original rate)
    uint32_t volume;           // 0..127
    uint32_t pan;              // 0..127, 64 = centre
    uint16_t param_a, param_b; // overwritten by SoundPlace; hypothesis: 3D parameters
    uint32_t unk28;            // 911
    uint32_t unk2c, unk30;
    uint32_t list_count;       // LIST effects only
    uint32_t sample;           // 0-based index into NAME
};
```

- A LIST effect plays its members in order, or randomly with RANDOM (e.g. `SFX_Fire_ShootArrow` = bow
  shot + arrow flight; `CompoundFight` = random sword clashes and silence). One WAV often serves several
  effects at different `pitch` values (man/woman/boy death cries).
- The stored WAV paths are the developers' absolute paths; only the file name counts, looked up in the
  package's directory. `GAMEF.DLL` has a table of the 17 `loadsfx` names with their directories
  (`buttonfx`, `Battle2`, `spells`, `missile`, `HumBtl`, `OrcBtl`, `DwrfBtl`, `Skaven`, `Monster`,
  `Retreat`, `Zhufbar`, `Dragon`, `PortCul`, `MoleMach`, `Hiln`, `HelpUs`, `Peasant`); all 15 names
  used by `.BTS` files resolve.
- WAV files: 96 effects in `FILE/BINARY/SOUND/` (PCM mono 8-bit, 11025 Hz, 2.5 min; 4 unused) and
  567 speech files in `REMOTE/BINARY/GLUE/SPEECH/` (mostly 22050 Hz 16-bit mono, 48 min). **548 speech
  files have a wrong RIFF size field**, so a reader must walk the chunks. `Z.SFX` is a truncated
  leftover; `RETREAT.SFX` comes from an older editor version but still loads.

## Battle 3D resources — `FILE/MESH/<BATTLE>/`

**Fully reverse-engineered.** Reports: `notes/pbx_rnc.md`, `notes/terrain_gd.md`. Scripts:
`scripts/pbx_rnc.py`, `scripts/pbx_extract.py`, `scripts/gd_render.py`.

Each battle directory (`loadmesh`) holds `GRND.GD`, `GRND.PBX`, `SCENERY.PBX` and `SPRITES.PBX`
(45 directories; `BF004/` only has an old-format `GRND.PBX` and is used by no script).

### `.PBX` — RNC-compressed resource container

A `.PBX` file is a `0x01` byte followed by **exactly one RNC ProPack block** (method 2) up to the end
of the file. Verified on all 133 files: both CRCs match and the container parses with no leftover bytes.

RNC header, 18 bytes, big-endian: `"RNC"`, `u8 method` (2), `u32 unpacked size`, `u32 packed size`,
`u16 CRC-16 of the unpacked data`, `u16 CRC-16 of the packed data`, `u8 leeway`, `u8 chunk count`.
CRC is CRC-16/ARC (reflected polynomial `0xA001`, initial value 0). Method 2 bit stream (bits read
MSB-first, a new bit byte fetched only when the previous one is used up, raw bytes read from the same
stream in between; the stream starts with 2 skipped bits):

```
0              literal: copy 1 raw byte
10 x [1 y]     n = 4 + x; if the next bit is 1: n = 2*(n-1) + y  (6..9)
               n == 9: literal run of (4 bits)*4 + 12 raw bytes
               else:   match of length n, distance = OFFSET
110 B          match of length 2, distance = B + 1
1110           match of length 3, distance = OFFSET
1111 B         B != 0: match of length B + 8, distance = OFFSET
               B == 0: end of chunk, then 1 bit (more chunks); the bit buffer is not reset
OFFSET:        hi = 0
               if bit: hi = bit
                       if bit: hi = (hi<<1 | bit) | 4;  if !bit: hi = hi<<1 | bit
                       elif hi == 0: hi = bit + 2
               distance = (hi << 8 | raw byte) + 1
```

The unpacked container (little-endian) has a 32-byte header (`magic 0xC8457560`, `version 207`, 0,
`mesh_count`, `file_count`, `texture_count`, total texture pixel bytes, total palette bytes), then
the embedded files, the textures, the meshes, the mesh names and a directory at the end (offset
arrays; both name lists sorted case-insensitively). The full structures are in `notes/pbx_rnc.md`.

| File | Contents |
|---|---|
| `GRND.PBX` | 2–11 ground textures (64×64) + one terrain mesh `grnd.xof` |
| `SCENERY.PBX` | 21–89 textures + 37–69 meshes: trees (two crossed flat quads), rocks, buildings with destroyed variants, bridges, and effect meshes shared by all battles (arrows, spears, fire, lightning, 8 explosion frames) |
| `SPRITES.PBX` | `.bop/.fol/.pal` sets, byte-identical to the files in `BINARY/`: `GENBATT` plus the units and banners of the battle's `.BTS` |

- **Textures** are named `*.gif` but are serialized Reality Lab `D3DRMIMAGE` images: 8-bit indices with
  a per-texture 256-colour RGB palette, 32 or 64 px, plus a flag that appears on trees, flames and
  arrows, where rendering black as transparent gives clean silhouettes (hypothesis), and a
  representative colour.
- **Meshes** (`*.xof`) are Reality Lab meshes: `u32 nverts, nnormals`, vertices and normals as float
  triples (Y up), triangles with vertex/normal index pairs, a texture index per face and a UV pair per
  vertex. **1 mesh unit = 8 script units**, mesh X = script x, mesh Z = script y.

### `GRND.GD` — terrain height field

Always 196608 bytes, no header: **64 × 64 cells × 2 triangles × 24-byte record**, little-endian.
Verified on all 45 files; the relief matches the plan maps of 9 battles (the BF009 lake is a pit under
the lake, rivers are the lowest ground, rocky bands are cliffs, the BF036 dungeon walls are traced
exactly).

```c
struct GdTriangle {          // 24 B
    float32 gx;              // dh/dx: plane slope along x
    float32 gz;              // dh/dz: plane slope along z
    float32 x;               // anchor point of the plane (GD units)
    float32 h;               // height at the anchor
    float32 z;
    uint32  diag;            // 0 = unused cell; 1 or 2 = which diagonal splits the cell
};
// cell (cx, cz): A = record 2*(cz*64+cx), anchored at (cx*10, cz*10);
//                B = record 2*(cz*64+cx)+1, anchored at ((cx+1)*10, (cz+1)*10)
// height of triangle t at (X, Z) = t.h + t.gx*(X - t.x) + t.gz*(Z - t.z)
// with u = X - cx*10, v = Z - cz*10: diag 1: u >= v -> A, else B;  diag 2: u + v <= 10 -> A, else B
```

- A cell is 10 GD units; **1 GD unit = 8 world units**, GD x = world x, GD z = world y, same origin.
  Only an nx × nz rectangle starting at cell (0, 0) is used (usually a few cells more than the field);
  the row stride stays 64.
- There are no texture coordinates or materials. The height scale (×8, like the horizontal axes) is a
  hypothesis to be checked against the game. `GRND.GD` and `grnd.xof` describe the same terrain at the
  same scale; presumably one is the height field for the game logic and the other the rendered mesh.

## Cutscenes — `REMOTE/BINARY/ANIM/`

**Containers and side files fully reverse-engineered; event semantics partly a hypothesis.** Reports:
`notes/si_omni.md`, `notes/scene_scripts.md`. Scripts: `scripts/si_omni.py` (container and
extraction), `scripts/si_smacker.py` (pure-Python Smacker decoder), `scripts/scene_dump.py`.

30 scenes (`A1`–`A27` with `A12B`, `A16A/B`, `A18B`; `DEATH01/02`), each as four files:

| File | Content |
|---|---|
| `.SI` | Mindscape **Omni 1.0** container (an older version of the LEGO Island format) |
| `.SN` | object name table: `u32 count`, then `u32 id, u32 len, char name[len]` per object |
| `.SM` | index of the `.SI`: `u32 count`, then `u32 object_id, i32 time, u32 si_offset` (time −2 = object header, −1 = format chunk, else ms); all 25,696 records match the `.SI` |
| `.SR` | the build tool's source list: path, file index, sequence number (−2 declaration with the object id, −1 header, −3 end, 0..n data chunks); unused fields hold the MSVC debug fill `0xdddddddd` |

`.SI` chunk tree (RIFF rules, little-endian):

```
RIFF 'MxSt'
  LIST 'MxSt'
    MxHd  (8 B)          u32 version 0x00010000, u32 0x100
    MxSt
      MxOb               root object; child objects nested inside
      LIST 'MxDa'        MxCh data chunks and 'pad ' chunks, written in 64 KB buffers
    pad                  up to a multiple of 64 KB
```

- `MxOb` objects: `u16 type` (3 film, 4 sound, 7 parallel group, 8 event track, 9 select), name, id,
  flags, start and duration in ms, loop count; leaves also carry the original source path
  (`scene11\a11.smk`), fps and a format tag (` SMK`, ` WAV`, ` MID`, ` EVT`). A type 9 object chooses a
  child by a variable: every scene picks `music\xxxfm.mid` or `musicawe\xxx.mid` by `MIDIType`.
- `MxCh` chunks: `u16 flags` (0x02 end of stream, 0x10 split piece), `u32 object_id`, `i32 time`
  (−1 = stream header), `u32 length`, data. A chunk that crosses a 64 KB boundary is split into
  pieces; in 3 places the writer left 1–4 garbage bytes before a boundary, which a reader must skip.
- Streams: **Smacker** films (`SMK2`, 640×272, no audio, one chunk per frame, always 125 ms apart, so
  the engine plays them at **8 fps** whatever the Smacker header says); **WAV** sound (PCM, 1 s per
  chunk); **MIDI** as a Windows `RIFF MIDS` stream file (10 of 17 tracks identical to
  `FILE/BINARY/MUSIC`); **EVT** event tracks: `Fade`, `AnimDone` (a fade-out after the film) and speech
  events `(speech_id, speaker, first_tick, current_tick, last_tick)` in 125 ms ticks, probably for
  subtitles.
- Speech numbering: `A*.WAV` in `GLUE/SPEECH` = cutscene lines, and the number is the string id in
  `ANTXT.DLL` including the speaker name (64/64; 63 are placed in scenes with exact start times).
  `B*.WAV` = battle and campaign lines, the number is the string id in `BRTXT.DLL` (489/502).
- 27 scenes are started by the glue scripts (`playmovie`, `iftrueplaymovie`), `A1` (intro) and
  `DEATH01/02` by `WHSHR.EXE`.

## Other files

- **Save games** `SAVE/savegame.0` and `savegame.5` (binary): unexplored.
- `SAVE/debrief.dbf` and `FILE/SCRIPT/*.DBF`: INI-like text (`[DEBRIEF]`, `[MISSIONINFO]`), same
  syntax family as `.BTS`; not analysed in detail.
- `SAVE/ARMY.MRC`, `MARCH.MRC`, `PLAY.MRC`: the army state in the `.MRC` format.

## Name dictionary (`samples/identifiers.txt`)

1006 unique CamelCase identifiers extracted with `strings` from
`WHSHR.EXE` and `GAMEF.DLL`. These are the developers' internal names linking abbreviated
8.3 file names (e.g. `BANORC1`) to a readable meaning (`BannerOrc1`), as well as
full names of spells, units, buildings etc. that do not appear directly in the file
names on disk. Very useful as a reference point for further work.

Example categories:
- Wizard spells: `AmberCurseOfAnraheir`, `BrightFireball`, `CelestialLightning`,
  `CelestialStormOfShemtek`, `AmberFlockOfDoom`...
- Units/characters: `AmberWizard`, `BrightWizard`, `CelestialWizard`, `GreySeer`,
  `BlackOrcs`, `ArraBoyz`, `BigUns`...
- Buildings/terrain: `AverlandKeep1`–`8`, `AngRoofHouse`, `BalconyHouse`,
  `BlackCaveEnt/Left/Mid`...
- Banners (factions): the `Banner*` family (Dwarf, Orc, Skaven, Empire, Elf, Troll...).
