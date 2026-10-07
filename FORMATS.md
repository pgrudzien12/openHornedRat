# File formats — Warhammer: Shadow of the Horned Rat (1995, Mindscape)

Notes from reverse-engineering the game's data formats, done mostly black-box
(byte analysis + visual verification). The battle rules in `GAMEF.DLL` (unit stat layout, close
combat, morale, shooting) are documented as observable behaviour (see "Game rules" and
`notes/game_rules.md`). For the rest of the game logic (`WHSHR.EXE`, mission DLLs) only static data tables in
the executables and the sound library `MSNDDS.DLL` (the `.SFX` loader) were read. This file is the reference; the full reports on the
individual formats, including how each claim was verified, are in `notes/`.

The examples use `$WARFB` for the root of a local GOG v1.0 installation:
```
$WARFB/
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
| UI bitmaps, texts, campaign glue scripts | `DLL/*.DLL` resources | ✅ extraction, ✅ campaign flow graph | PE resources, Campaign glue | `notes/pe_resources.md`, `notes/scene_scripts.md` |
| Fonts, front-end palettes | `*.FON`, `GLUE/*.PAL` | ✅ | Front-end fonts and palettes | `notes/fonts_glue.md` |
| Music | `MUSIC/*.MID`, `SOUND/WARINTR3.SBK` | ✅ formats and full renders | Music | `notes/music.md` |
| Sound effects, speech | `SOUND/**/*.SFX/.WAV`, `GLUE/SPEECH/*.WAV` | ✅ formats and listening review | Sound effects | `notes/sfx.md` |
| Battle 3D resources | `MESH/*/*.PBX`, `GRND.GD` | ✅ | Battle 3D resources | `notes/pbx_rnc.md`, `notes/terrain_gd.md` |
| Cutscenes | `ANIM/*.SI/.SN/.SM/.SR` | ✅ containers, 🟡 event semantics | Cutscenes | `notes/si_omni.md`, `notes/scene_scripts.md` |
| Game rules: unit stats, combat, morale, shooting | `GAMEF.DLL` code and tables, `setstats` | ✅ stat layout, close combat, morale; 🟡 missile constants, some flags | Unit stat fields, Game rules | `notes/game_rules.md` |
| Mission logic, unit behaviour | `SCRIPT/BFxxx.DLL` | ✅ bytecode scripts, interpreter, all 232 opcodes, script decoder (`whshr scripts`); 🟡 per-mission semantics | Mission logic, Game rules | `notes/game_rules.md` |
| Save games, campaign files | `SAVE/savegame.*`, `ARMY/PLAY/MARCH.MRC`, `debrief.dbf` | ✅ RIFF `WHSV` container, regiment roster, embedded army files, mission availability and caravan scroll rules; 🟡 some `Result:` values | Save games and campaign files | `notes/campaign.md` |

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

**Layout reverse-engineered and verified visually; the rotation sense of `dir` is known, its zero frame and frame timing are open.**
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

Script `dir` turns clockwise from +Y (see "Coordinates" under the battle scripts) and the frame
order runs clockwise on screen too (frame 2 faces screen-right), so a north-up view uses `direction = round(dir / 64) mod 8`;
in 3D the frame is taken relative to the camera heading (`notes/battle_viewer.md`).
Open: which frame `dir = 0` selects (derived as frame 0, not observed), frame timing, some uncertain action
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
Parser: `scripts/whscript.py`, renderer: `scripts/render_battle.py`. `whshr.script.write()` is the
inverse of `whshr.script.parse()` (a node tree back to text), used to write `SAVE/ARMY.MRC` and
`SAVE/MARCH.MRC` (`whshr/roster.py`); round-tripped byte-for-byte-semantically against all 87
shipped `.BTS`/`.MRC` files and the real save's `ARMY.MRC`/`PLAY.MRC`/`MARCH.MRC`.

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
- `dir` and the fourth number of `placefurniture` take values 0…511 (max observed 504); a full turn
  is 512. **0 = +Y (north on the plan map), increasing clockwise.** Evidence: over all `BF*.BTS`,
  units face the nearest unit of another army far better under this convention (mean cosine +0.44)
  than counter-clockwise (+0.20) or with any other zero point; scenery meshes rotated this way
  match their plan-map footprints (`BF035` TwinTowers, `BF036` pipe grilles). For a mesh, local +Z
  faces `(sin a, cos a)` and local +X faces `(cos a, −sin a)` in BTS X/Y.
- **3D axes:** BTS X → mesh X, BTS Y → mesh Z, height → mesh Y (one mesh unit = 8 BTS units). This is a
  left-handed frame (as in Direct3D Retained Mode); rendering it with a right-handed camera basis
  mirrors the scene. Details: `notes/battle_viewer.md`.

### `.BTS` — sections

Order in the files: `FIELD`, `MISSIONINFO`, `DYNAMIC_LOAD`, `OBJECTS`, `SCENERY`,
`BOUNDARIES`, `UNITS` (1 or 2 sections), `NODES`.

| Section | Contents |
|---|---|
| `FIELD` | see the table below |
| `MISSIONINFO` | `DeployTroops:` (pre-battle placement phase; [`notes/deployment.md`](notes/deployment.md)), `Objective:L,a,b` (see "Mission objectives" below) |
| `DYNAMIC_LOAD` | resources to load: `loadspr:Name,n` (sprite sets, e.g. `BattleSprites` → `GENBATT`), `loadsfx:Name` (sound packages, see "Sound effects"), `loadfurn:Type` (3D scenery objects used in `SCENERY`, see "Name tables"), `NoBirds:` |
| `OBJECTS` | collision objects: `set:status` (`os_active`, `os_solid`, rarely `os_camcollide`), `x`, `y`, `z`, `radius`, `dir`. Optionally `addrectangles:=N` with `rect:x1,y1,x2,y2`, i.e. rectangles relative to the object's center, presumably rotated by `dir`. `z` is not the terrain height under the object (probably the object's own height) |
| `SCENERY` | `placefurniture:Type,x,y,dir`: trees, rocks, buildings. `Type` is resolved through the furniture table to a `.XOF` mesh in the battle's `SCENERY.PBX`. The `D_` prefix (e.g. `D_SnwWatchTower`) is the destroyed variant, with its own mesh (e.g. `TPINEL_D`) |
| `BOUNDARIES` | `AddBoundary:Name`, optional `set:status=...`, and `AddLine:x1,y1,x2,y2`. All 409 boundary entries in the 54 shipped `.BTS` files include status. Roles follow status, not the descriptive name. An entry without status remains active with its geometry but gains no movement, deployment, sight, view, or camera role from its name. `bnd_BATTLEEDGE` bounds normal unit movement and permits routed exits; `bnd_SOLID` and `bnd_INVSOLID` constrain movement regions; `bnd_DEPLOYMENT` limits pre-battle placement; `bnd_SIGHT` affects spotting; `bnd_VIEWEDGE` and `bnd_CAMEDGE` affect the view/camera. Shipped `Nav1`–`Nav8` entries carry `bnd_ACTIVE|bnd_LINE` without solid status: they can guide a multi-waypoint route but do not block contact movement. One `RiverEdge` entry is view-only. See [`notes/movement_boundaries_route_finding.md`](notes/movement_boundaries_route_finding.md). |
| `UNITS` | units (format below). Label from the comment: `; Enemy Army` (54), second section `NPC units` (27) |
| `NODES` | mission-script nodes: `set:status` (`ns_active`, `ns_startpos`, `ns_artillary`, `NS_END`), `x`, `y`, `radius`, `dir`, `id`. Active start nodes supply default player positions/facings in file order; a normal army of U regiments uses the last U of N start nodes. `NS_END` does not choose the slots, and nodes do not define the allowed placement zone. Full allocation and deployment rules: [`notes/deployment.md`](notes/deployment.md). |

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
| `Camera:45.0` | 0/45/90/135/180/270 — presumably the initial camera heading, clockwise from north (hypothesis: `BF001` = 45 matches the in-game "N ne E" compass). The battle camera itself is a perspective camera |
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

**Evaluation** ✅ (`notes/game_rules.md`, "Missions and objectives"): `GAMEF.DLL` keeps one record per objective letter,
indexed `L − 'A' + 1`, with the defined flag, flags, caption id, an evaluator function and the
numbers `a, b`. Evaluators run at battle set-up, every tick (flag `0x2`) and in a separate pass (flag `0x8`); the
first met objective with flag `0x1` ends the battle. Battle-ending letters: A, F, H, N and Z. Objective G ("Inside
the gates!", BF015/BF017) lets player units that reach an interior node leave the battle. The 26 evaluator bodies
(what each letter counts) have not been read.

### `.MRC` — army

Root `[MERCARMY]`, containing `[UNITS]` (label `; Mercinary Army` or
`; Mercenary Army (Marching Orders)`) and sometimes `[MISSIONINFO]` (`ARMY.MRC`, `SPRED.MRC`).
Loaded from `.BTS` via `loadmerc`. In the campaign the battle engine loads `SAVE/MARCH.MRC` (the regiments
selected for the next battle) instead; `FILE/SCRIPT/MARCH.MRC` is its empty stub (see "Save games and campaign
files").

### Unit (`addunit`), shared by `.BTS` and `.MRC`

```
addunit:Grudgebringer<Cavalry          name ('<'/'_' = space)
    hidden:                            invisible until spotted or placed in deployment; delayed units wait in their script
    set:whoami=2                       0 for ordinary enemies; 1..100 for named units (hypothesis: persistent campaign ID)
    set:hired=0                        0/1: mercenary paid (hypothesis)
    troopsprites:BorderHorse,0         sprite set → .FOL via the sprite table ("Name tables"); ",0" is always 0
    banner:BannerMrcCmdr,0             banner
    addmagicitem:ItemGrudgeBringer     0..n
    addspell:AmberTanglingThorn        0..n (wizards)
    set:psy_status=HateSkaven|CantBreak  psychology bits, see "Unit stat fields"
    setstats:s_side=2,12,12,4          side, orgsize, size, ranks    each line fills consecutive
    setstats:s_move=4,4,3,3,3,1,3,1,7  M WS BS S T W I A Ld          fields of one byte block,
    setstats:s_mount=1,13,3,16,13,0    mount armour weapon race points missile   see "Unit stat fields"
    setstats:s_weap=3  S_BalWeap=0  s_pntval=13  s_cmdr=0,0,4,0  s_armname=0,4   repeat fields set above
    setstats:s_armr=5                  armour code (leaders write it on its own)
    setstats:s_rlmv=…  s_lead=…        old layout in PLOT1: 9 values starting at s_rlmv / s_lead
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

### Unit stat fields (`setstats`)

**Layout ✅ (full report `notes/game_rules.md`).** Keywords map to numeric tokens. Tokens 13–39
(`s_side` … `s_banner`) are **one byte each, consecutive in token order**, and a `setstats` line writes its
values into consecutive fields starting at its key. Tokens 40–43 (`s_calualties`, `s_routed`, `s_kills`,
`s_Exp`, written as `set:`) are 16-bit fields. Evidence: all 1415 units and leaders of the scripts and save
armies decode with 32 335 values and no contradiction (`python3 -m whshr check`); the in-game panel of
Mercenary Crossbows (M4 WS3 BS4 S3 T3 W1 I3 A1 Ld7, "Crossbow 12/12") is `SAVE/PLAY.MRC`.
`python3 -m whshr rules <installation> BF001.BTS` prints the decoded units.

| Token | Field | Meaning |
|---|---|---|
| 13 | `s_side` | side and type byte (below) |
| 14, 15 | `s_orgsize`, `s_size` | original and current number of models (test files leave `orgsize` 0) |
| 16, 17 | `s_rnks`, `s_wdth` | ranks; frontage `ceil(size / ranks)` (recomputed at run time; rank bonus, charge bonus) |
| 18, 19 | `s_rkmd`, `s_spar` | runtime: ranks in the formation, front ranks at full frontage (never set by scripts) |
| 20 | `s_rlmv` | 🟡 flee movement rate (recomputed at unit set-up) |
| 21–29 | `s_move` `s_wepn` `s_bals` `s_strn` `s_tuff` `s_wnds` `s_init` `s_atks` `s_lead` | **M WS BS S T W I A Ld** |
| 30 | `s_mount` | 0 none, 1 Warhorse, 2 War Boar, 3 Giant Wolf, 4 Cave Squig (mount profiles in `GAMEF.DLL`) |
| 31 | `s_armr` | armour code: 0–5 rating (saves none, 6+, 5+, 4+, 3+, **none**), 6 regeneration (4+), 7 void, 8–13 mounted rating 1–6 (6+ … 2+); `BRTXT` 100–113 |
| 32 | `s_weap` | close combat weapon class: 0 none, 3 hand weapon, 4 two-handed (+2 S), 10 spear/halberd (+1 S) |
| 33 | `s_race` | `class × 8 + race`: race 0 Human, 1 Elven, 2 Dwarven, 3 Goblinoid, 4 Orc, 5 Skaven, 6 Peasant, 7 big; class 0 notype, 1 Infantry, 2 Cavalry, 3 Archers, 4 Artillary, 5 Wizard, 6 Monster, 7 RollingStock, 8 Special |
| 34 | `s_pntval` | ✅ points value (experience for the credited unit, `notes/casualty_bookkeeping.md` §2.2) |
| 35 | `S_BalWeap` | missile weapon: 1 bow, 2 crossbow, 5 great cannon, 6 mortar, 7 Hellblaster, 8 rock lobber, 9 Wood Elf bow, 11 cannon, 12 doom diver, 13 warp lightning, 14 breath, 15 warpfire, 16 spellcaster marker (Wyvern shaman), 17 Gyrocopter bomb/steam gun, 18 short bow, 19 longbow (artillery: on the leader) |
| 36–39 | `s_cmdr`, `s_armname`, `s_weponame`, `s_banner` | `s_weponame` = weapon name string `BRTXT 200 + n` (15 "Crossbow", 25 "Scimitar"…); the other three are always 0 |

**`s_side` byte** (token 13) is a bit field, decoded by cross-referencing it with the
`;S_RACE is …` comments in all files:
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
  The editor computes the comment from `s_race` (agrees in 879/889 units) and warned about the
  mismatch between the two fields.

**`psy_status`** (`|` flags) ✅ is a 16-bit field, bit = token − 19:
0 `CantBreak`, 1 `Frenzy`, 2 `CauseFear`, 3 `CauseTerror`, 4 `FearToGobs`, 5 `HateDwarfs`,
6 `HateGreens`, 7 `HateSkaven`, 8 `PsyImmune`, 9 `MagicResistent`, 10 `CantRally`,
11 `AlwaysPursue` (unused by the scripts), 12 `CantMelee`, 13 `CantDie`. Their effects are listed
under "Game rules".

### Parser

```
python3 scripts/whscript.py .../FILE/SCRIPT/BF001.BTS          # summary
python3 scripts/whscript.py .../FILE/SCRIPT/BF001.BTS --json   # full view (including the army from loadmerc)
python3 scripts/whscript.py --check .../FILE/SCRIPT            # all files + counters
python3 scripts/render_battle.py .../FILE/SCRIPT/BF001.BTS out.png 0.5
```

### Open questions (scripts)

- Meaning of `set:map` (`whoami` is the persistent regiment id 0–37, `notes/campaign.md`), of the stat bytes `s_cmdr`, `s_armname`, `s_banner` (always 0), and of the numbers of most objective letters. The other
  `setstats` fields are resolved (see "Unit stat fields").
- The `,N` after `troopsprites`/`banner`/`leaderportrait`/`loadspr`: 0 in all 3314 uses, and when it
  is missing (`loadspr:Wagon`) the file is not packed. Hypothesis: a colour or variant selector.
- Whether `dir = 0` selects sprite direction frame 0 (derived, not observed in the running game).
- ~~Units packed in a battle's `SPRITES.PBX` but not declared in its `.BTS`~~ ✅ resolved: every bundled file is a
  `.BTS` unit sprite or a `loadspr` entry (animated terrain, `GENBATT`) in all campaign battles; only fanatics are
  spawned at run time.

## Game rules — `GAMEF.DLL`

**Close combat, morale and shooting read from the code; full report with function addresses,
evidence and open questions: `notes/game_rules.md`.** Checked by `python3 -m whshr check`; tables
printed by `python3 -m whshr rules <installation>`. Everything below is ✅ unless marked 🟡.

- **Random numbers**: MSVC `rand()`; a D6 is `rand() % 6 + 1`.
- **Clock and time**: one tick per 100 ms timer message (at most 10 ticks/s); 19 ticks = one segment;
  segments count 10 → 1 per turn (a turn is 19 s). A unit fights its close combat
  in the segment equal to its **Initiative** (higher strikes first).
- **To hit** (`[attacker WS][defender WS]`) and **to wound** (`[S][T]`)
  are exactly the WFB 4th edition charts for values 1–10. **Save modifier** `max(0, S − 3)`.
- **Armour save** by `s_armr`: 0 none, 1 6+, 2 5+, 3 4+, 4 3+, **5 none** (table value 7, probably a
  bug), 6 regeneration 4+, 7 none, 8–13 6+, 5+, 4+, 3+, 2+, 2+. A D6 below the save + modifier fails. Regeneration (6) is a 4+ roll in close
  combat, but **regenerating models are never wounded by missiles**; an armour item turns code 5 into regeneration.
- **Attack**: A (×2 with `Frenzy`), WS +1 against a model busy fighting someone else (not monsters), S + weapon class bonus
  (two-handed +2, spear/halberd +1) +1 for the first `1.5 × frontage` attacking models after a charge. Hatred re-rolls misses in the
  first round. Mounts attack with their own profile and a fixed charge strength. Magic items of the
  leaders modify WS, S, A, armour and wounds.
- **Combat result**: kills + rank bonus `size / width − 1` (width > 3, **no +3 cap**) + attack direction
  (rear +2, flank +1), summed per side over all units on the same battle grid. No standard bonus found.
  Resolved once per turn at the grid's creation segment: first two turns after contact, then every 1–2 turns.
- **Who fights**: a model holding a cell orthogonally next to an enemy model on the combat's 17 × 17
  grid (12 units per cell); up to frontage models are placed per tick, the rest wait and wrap around.
  No rank or spear rules. Only monsters strike back immediately (per-round attack pool).
- **Movement**: M only feeds the speed stat `s_rlmv = trunc(4.8 × M + I) / 2` (the mount's M for riders); units
  move `s_rlmv × k / 16` world units per tick (k 1.8 free, 1.0 closing in, 2.5 charging, 1.5 fleeing and
  pursuing), about 9.8" per turn for M4 I3 infantry; terrain does not slow units; they wheel on a front corner. Point routes can use authored Nav lines for intermediate waypoints around movement regions, while scenery and units trigger reactive steering; overlapping friendly units and scenery
  push apart. Visibility (spotting, AI shooting and casting) needs a 100° view cone (200° in melee), no scenery on
  the line and no `SightEdge` crossing; terrain height never blocks sight. No army-level AI exists.
- **Magic**: one shared power pool of 0–8 per side, re-rolled by a random walk every 50 s of real time; spells
  cost 1–3, paid on the click, and always work if the target is in range and within ±50° of the wizard's
  facing (no casting roll, line of sight or levels). Bolts: Lightning S6 D3, Warp Lightning S5 D6, Fireball S4;
  Conflagration of Doom and Da Krunch slay models outright; Madness changes a unit's side; Sapphire Arch is a
  portal. Dispelling is a 50%/100% aura within 80 units (Dispel Magic, Mork Save Uz, Banner of Arcane
  Protection, Talisman of Obsidian). Banner of Wrath and Grudgebringer cast Lightning/Fireball once per wind.
- **Formations**: the block is the only formation (infantry, cavalry, archers, wizards, special units). Models
  stand **12 world units** apart; frontage `ceil(models / ranks)` with the leftover models in the front ranks;
  the unit position is the front-rank centre, reserved for the leader; the collision box (± frontage × 6, ± ranks × 6) is centred `(ranks − 1) × 6` behind
  it, in the middle of the block. Ranks can be changed between
  `max(1, trunc(0.75 × √models))` and `models ÷ that`. War machines use a fixed crew layout (2 × 3 or 3 × 4 by
  machine), monsters a 2 × 2, 3 × 3 or 5 × 8 cell footprint, wagons two models 22 units apart. Units have up to
  32 models (enemy median 16), usually in 4 ranks.
- **Commands**: player orders are panel buttons executed by the unit scripts. "Fight harder" (flexed arm, melee
  only) gives the focused unit +1 S and +1 Leadership for one segment; "Independent" (head icon) lets a unit
  rally, react and choose targets on its own. Withdraw routs the unit when it is not allowed.
- **Details**: mounts add their own attacks but cannot be wounded separately; there is no standard, battle standard
  or general's Leadership; units with I 20 (the Dragon, Orcs under "Ere We Go!") never strike in their own segment.
- **Leadership test**: pass if `modifier + (rand() % 11 + 2) <= Ld` of the leader (a **uniform 2–12
  roll, not 2D6**).
- **Break test**: modifier = how much the combat was lost by; a unit beaten by a fear-causing enemy
  breaks without a test (unless `CantBreak`, `Frenzy`, `PsyImmune`, Dread Banner); a unit that hates
  its enemy passes on 10 or less.
- **Panic**: a test each time the unit's losses cross another quarter of its original size, from any
  cause, with modifier `1 − remaining quarters` (easier early, harder late).
- **Fear/terror**: charging a fear-causer needs a Leadership test (failure: charge refused); when charged by
  or touching one, failure means flight. Terror-causers make non-immune units flee without a roll.
- **Flank/rear charge**: a charge into the rear arc or the rear half of a flank forces a Leadership test
  (failure: rout). `FearToGobs` is never used.
- **Rout and pursuit**: routed units run straight away from their opponent and are removed when they leave
  the table (`s_routed` counts them); their opponents pursue (not player artillery, wizards, archers) and
  inflict automatic hits in each segment of contact (🟡). Pursuit ends on a chase budget, the target
  rallying or dying, or the map edge.
- **Rally**: not with `CantRally` or at ≤ 25% strength; +1/+2 penalties by casualties; no enemy within
  160 units; first attempt a turn after the rout, then every 3 segments, **only while the player's
  "Rally!" order is on** (or the unit's independent toggle). The same order enables the test to stop
  pursuing; AI units never take it.
- **Behaviour scripts**: events (rout, charged, rally…) are queued for each unit and handled by its
  bytecode script from the mission DLL (see "Mission logic"); shouts, portraits and speech come from
  per-race `React` tables.
- **Shooting**: no to-hit chart. Archers fire ⌈models / 4⌉ projectiles per volley (artillery one) at a
  target in the 90° front arc and strictly within range, after halting and turning. Each lands at
  `rand() % (11 − BS)` scatter steps per axis (8 units per step, scaled by distance/range; +8 behind
  scenery; artillery `8 × artillery die`). Reload `(10 − I) × 18` ticks minus a weapon constant (bow 43,
  crossbow 30, longbow 39, short bow 46, Wood Elf bow 54). Ranges use **24 world units per inch** (short
  bow 16", bow 24", crossbow and longbow 30", great cannon 60"). Arrows: S3 (crossbow, Wood Elf bow S4),
  one model, 1 wound. Blast weapons hit **every model** of a unit they land in or fly into (great cannon
  S10 D6, cannon S10 D4, mortar S7 D3, rock lobber S5 D6, Hellblaster S5 within 12" else S4), and random
  models in the blast margin at S/2 for 1 wound. No moving, long-range or cover modifiers; shooting into
  close combat is allowed. Artillery misfires on a 6, then explodes on a 1. Dragon breath (D6+3 S8 hits,
  targets rout), warpfire (D6 S4) and the Doomwheel (3 random-distance bolts) use the spell effect engine.
  Battle messages come from `GMTXT` 2000–2021 ("Direct hit on the %s!", "The %s has misfired."…).

### Open questions (game rules)

Full register with evidence, next steps and priorities: `notes/game_rules.md`, section 11 (R1–R31).
The most important ones for an engine:

- How many models fight in practice once movement is simulated (R36); which orders count as a
  charge or pursuit (R32).
- Magic effects to confirm in the running game: Flamestorm and Curse of Anraheir without an end (R52); the
  meaning of objective index 7 and units leaving the battle through library script 170 (R60).
- Whether an engine should reproduce apparent bugs: armour rating 5 without a save (R11), "Ere We Go!" stopping
  close combat attacks (R5), charging monsters keeping +1 S (R33); the withdraw condition (R48).

## Mission logic — `FILE/SCRIPT/BFxxx.DLL`

Real **PE32 Win32 (i386) libraries, compiled with MSVC**, about 24–29 KB, mostly C runtime. Internal
name `dll.dll`. Exports: `DLLGetScriptPointer`, `DLLReturnInstCount`. The game loads them via
`script\%s.DLL` (message `Failed to load Script DLL %s`).

**The DLLs carry bytecode, not native logic** (✅, `notes/game_rules.md`, "Unit behaviour scripts and
events"). `DLLGetScriptPointer(id)` is a table lookup: ids from 0 → the mission's unit behaviour scripts (3–37 per DLL; `set:script=N` selects one),
ids 100–170 → a shared library that is byte-identical in all 45 DLLs. The scripts are arrays of 32-bit words
(bit 15 = opcode, `0x0ABC` label, `0x80E8` end) run for every unit each tick by an interpreter in
`GAMEF.DLL` with 232 opcodes. They handle queued events (charged, rout, rally, enemy routed…) and issue
orders; `set:script=PLAYER_SCRIPT` selects library script 100. All 232 opcodes are catalogued (`notes/game_rules.md`, section 4), so an engine can run the original scripts
instead of rewriting them. `python3 -m whshr scripts <installation> [DLL] [ids…]` prints script summaries and
listings, and the "behaviour scripts" check verifies that all 3787 scripts of the 45 DLLs decode cleanly and
that every `set:script` value exists. The shared library (ids 100–170) holds the player unit script, class
event handlers, morale layers, shooting, magic and AI behaviours; mission scripts add battle-specific cases. `DLLReturnInstCount` returns 33000 = `0x80E8`, a format check.

The campaign flow around the battles (briefings, mission choice, debriefings, movies) is not in these
DLLs either: it is the glue scripts in `WND.DLL` (see "PE resources").

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

  **Which missions a window offers** (full account in `notes/campaign.md` section 7): a
  window holds at most 5 `[MISSION]` records of `0x110` bytes each (the `MISS` layout). A record is shown
  unless it is already taken (`+0xA4`, set on troop-selection confirm); `set:depend=<res>` shows it only once
  the mission with that name id **in the same window** has been taken; `set:inactivedepend=<res>` shows it
  only while that mission is **not itself on offer** (recursive on visibility, not on completion). A name id
  absent from the window makes the gate a no-op. `set:releaseflag=1` marks the missions that resume the flow
  script — picking any other mission rebuilds the list one row shorter and leaves the player on the same map
  window.

  **The caravan scrolls**: `CARAVANCOMMON1` draws `CarScroll1/2/3` with `set:depend=4/3/2`, which on a
  `[BITMAP]` means "draw while at least N missions are on offer" (against the cached count of visible missions). So the desk shows **visible missions − 1 scrolls, capped at 3**, filling in the order
  3, 2, 1. One more scroll is baked into the background, so the shelf shows as many scrolls as missions on offer (max 4). These are the only `[BITMAP] set:depend=` in
  `WND.DLL`.

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

The front end's `GlueCreateFont(N)` selects a `.FON` by number (1–6) using these exact face
names, confirmed by static analysis, so the file column above is a fact, not a name-based guess.
Font 2 (`PCTEXT.FON`, 12 px tall, 9 px ascent) is also confirmed (not just declared in data) as
the font used to draw the campaign mission title, the mission-list scroll-row labels, and the
control-panel button labels (Brief/Accept/Caravan/…) — see `notes/fonts_glue.md` §2/§6 and
`notes/mission_selection.md` §3/§9.4.

**Front-end palettes** (`FILE/BINARY/GLUE/*.PAL`, variant A) come in pairs that together fill the
236 free indices: `GLUE<screen>.PAL` = 10–105 and `WIND<screen>.PAL` = 106–245. Comparing the colour
tables of all 717 bitmaps with every palette gives exact matches for `TITL` (title screen), `MIND`
(Mindscape logo), `END`, `CAR` (caravan), `MAP` (campaign map), `BK2` (33 regiment portraits) and
`BOOK` (magic pictures). `GLUEREND` is not referenced but matches `TROOPBOOK`; no bitmap matches
`GAME` or `OPT`. Screens drawn only from these palette files look correct, and a wrong pair gives
garbled colours.

## Music — `MUSIC/*.MID` and `SOUND/WARINTR3.SBK`

**Formats ✅; all 21 tracks rendered with FluidSynth (GM soundfont + the converted bank, one uniform
gain of 0.26 to avoid clipping); the bank parts were listened to and confirmed.** Report: `notes/music.md`. Scripts:
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

**Fully reverse-engineered, confirmed against the reader/writer in `MSNDDS.DLL`; the project owner
reviewed the effects with their stored `pitch` applied and the speech files.**
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

## Save games and campaign files — `SAVE/`

**Save format decoded, campaign rules traced** (full report with evidence: `notes/campaign.md`). Written by
`WHSHR.EXE`; a stdlib reader prototype validates both real saves.

`savegame.0`–`savegame.5` (slot 5 "Last Game" = the glue `autosave:`) are Windows RIFF files, form `WHSV`,
little-endian, with eleven chunks in fixed order:

| Chunk | Size | Contents |
|---|---|---|
| `SHDR` | 248 | `char[64]` description, `char[64]` battle script, `char[64]` current glue window, `u32` version (1), `u32` checksum (sizes of `BK01`+`BKO2`+`BK03`+`RMYI` + size of `WND.DLL`), `u32` ?, `u32` nScripts, nCalls, nWindows, nObjects, `i32` **coffers**, `u32` glue status bits and mask, `i32` bonus counter, 12 zero bytes |
| `STAX` | nScripts·0x218A8 + nCalls·4 + nWindows·0x84 + nObjects·0xA0 | glue interpreter state (script contexts, call stack, window stack, window objects): a save resumes the glue script exactly where it stopped |
| `BK01`, `BKO2`, `BK03` | 120, 16, 72 | `u32` book-page flags set by `enablebook:<book>=<page>`, `-1` terminated |
| `RMYI` | 2028 | 39 × 52-byte regiment records indexed by `whoami` (last all `-1`): keep (never disbanded), for hire, wizard, artillery, pending join, in marching orders, in army, experience at mission start, reinforcements available, base price, price per model, wounded, wounded returning |
| `RMY1`–`RMY4` | file size | verbatim `ARMY.MRC`, `PLAY.MRC`, `MARCH.MRC`, `debrief.dbf` |
| `MISS` | 272 | current mission: `u32` BRTXT name id, 4 × `char[32]` (briefing run file, briefing script, battle, mission script), 12 × `u32` ?, debrief evaluator index, `cash` type, initial and completion payments, rates A and B, 2 required objective letters, 8 × forced regiments (`whoami + 1`) at `+0xF0` |

Campaign text files (same syntax as `.MRC`):

| File | Role |
|---|---|
| `PLAY.MRC` | master roster: all 38 regiments (`whoami` 0–37), created from `SCRIPT/MAXARMY.MRC` |
| `ARMY.MRC` | the company, created from `SCRIPT/STRTARMY.MRC` |
| `MARCH.MRC` | regiments and positions for the next battle, loaded by `GAMEF.DLL` as the player army |
| `debrief.dbf` | battle result written by `GAMEF.DLL`: `[DEBRIEF]` with `[MISSIONINFO]` `Result:<letter>,<success>,<4 values>` per objective and `[UNITS]` surviving and dead/routed units |

Campaign rules in short: kills give the victim's `s_pntval` as experience; promotions at 2000/4000/6000 XP
(+1 WS, +1 S, +1 W; wizards learn a spell per 1000 XP); coffers start at 500; each `cash` type selects one of
19 balance-sheet programs (`BKTXT` 5000–5042 lines); a deployed regiment costs price per model × models, one left
in camp 10 %; routed models return, 65 % of the killed are wounded and return a mission later; regiments below
20 % are disbanded unless protected.

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
