# Sprite leftovers: `SPRITE3.BTP`, legacy `.FOL` layouts, `SPELLS` maps, orphans, odd `.PAL`, patch

Report for ROADMAP 1.7 plus the "Open questions" of the `.FOL`/`.BOP` section of `FORMATS.md`.
Black-box analysis (byte statistics over **all** files of a type + visual checks of PNG renders).
Data source: GOG v1.0, `WARFB/FILE/BINARY` and `WARFB/UPDATE/BINARY` (identical, see point 6).

Scripts: `scripts/btp_leftovers.py` (CLI, one subcommand per point) and `scripts/btp_lib.py` (helpers).
Renders and text outputs: `extracted/btp_sprite_leftovers/` (game data, local only, in `.gitignore`).

```
python3 scripts/btp_leftovers.py ".../WARFB" all                  # everything, ~5 s
python3 scripts/btp_leftovers.py ".../WARFB" btp|legacy|spells|orphans|pal|patch [out_dir]
```

## Summary

| # | Question | Status | Answer in one line |
|---|---|---|---|
| 1 | `SPRITE3.BTP` = 256×256 LUT? | ✅ not a LUT | Byte-identical copy of `SPRITE3.BOP[0:65536]`: 32 frames 32×64 with 4-bit values 0..15. Developer leftover. Real colours of the 16 values: ❌ unknown |
| 2 | `HALBERD.FOL`, `ICON2.FOL`, `SPRITE3.FOL` | ✅ | Older record layouts: 12 B (`hx hy w h offset`) and 8 B (`unk16 w8 h8 offset`), frames are raw 8 bpp |
| 3 | `SPELLS.PAL` has 43 maps, nibble only 0..15 | ✅ | Map index = nibble + 16 × (number of earlier drops of the nibble); frames are grouped by map in file order |
| 4 | 84 type-2 frames without `.PAL` | ✅ what / 🟡 colours | All in `ICONSTMP.FOL`, an orphan index (no `ICONSTMP.BOP`) of an **older** `ICONS.BOP`; icon buttons with `ICONS.PAL` colours |
| 5 | `.PAL` fitting neither A nor B | ✅ | `SYS.PAL` (80 B): variant A with non-sequential indices 0–9, 246–255; placeholder colours |
| 6 | What did `UPDATE/BINARY` change? | ✅ | Nothing: all 731 common files are byte-identical |

Side findings: `FILE/BINARY` has 288 `.FOL` and 288 `.BOP`, but only **287 pairs**
(`ICONSTMP.FOL` has no `.BOP`, `SPRITE30.BOP` has no `.FOL`). `NLNHLB.PAL` has 8 maps where
maps 4–7 are a second livery. `TESTSPR.PAL` and `HALBERD.PAL` are debug palettes.

---

## 1. `SPRITE3.BTP` — not a LUT, a raw 4-bit frame strip ✅

### How it was checked (`btp` subcommand)

LUT hypothesis, tested on `lut[a][b] = byte[a*256+b]`:

| Test | Result | A blend LUT in `STANDARD.PAL` would give |
|---|---|---|
| value range | only **0..15**, 16 distinct values, **80.8 % zeros** | indices 10..245 |
| symmetry `lut[a][b] == lut[b][a]` | 43500/65536, but only 654 of them non-zero (the rest are zero = zero) | ~100 % |
| diagonal `lut[i][i] == i` | 1/256 | 236/256 |
| row 0 / column 0 | 0 / 1 non-zero | identity or constant |
| rows 0–9 and 246–255 | 746 non-zero bytes | unused (system colours) |
| nearest colour of 50 % blend, `a<=b` in 10..245 | 8 of 27966 | ~27966 |
| nearest colour of additive blend | 1 of 27966 | ~27966 |

The grayscale render at width 256 (`btp_raw_256x256_gray.png`) shows horizontal smears in an
8-column grid, which is typical of wrong stride. The file is exactly `32 × 32 × 64` bytes.

**`SPRITE3.BTP == SPRITE3.BOP[0:65536]`**, byte for byte. `SPRITE3.FOL` (see point 2) describes
frames 0–31 as 32×64 at offsets `0, 0x800, …, 0xF800`, so the BTP is these 32 frames.
Rendered with stride 32 (`btp_as_32x64_frames_gray.png`) it shows a **halberdier: 8 directions ×
4 walk frames**, clean silhouettes, halberd and helmet clearly visible.

`FILE` and `UPDATE` copies are identical.

`SPRITE30.BOP` (65536 B, no `.FOL`) is the same data with two frames edited: frame 0 blanked and its
first row filled with value 1, frame 1 blanked except 2 pixels (767 differing bytes, frames 2–31
identical). It looks like a leftover of an encoder/loader test.

`grep -a -i` over all `*.EXE`/`*.DLL` of the installation finds no `btp`, `sprite3`, `sprite30`,
`testspr`, `iconstmp` or `sys.pal` strings. The game builds names from identifiers
(`NulnHalberdiers`, `SpellSprites`…), so absence of a string is not proof, but nothing points
to these files being loaded. **Hypothesis:** `SPRITE3.*`, `SPRITE30.BOP`, `HALBERD.*`, `TESTSPR.PAL`
are development leftovers of the 4 bpp sprite pipeline.

### What the 16 values mean ❌

Not solved. The values are colour slots of a 16-colour sprite (value 0 = transparent), i.e. the
same 4-bit plane that the final format stores packed in `.BOP` type 2/4. Attempts:
- `HALBERD.PAL` (16 entries 0–15) is a placeholder palette (0 = blue, 1–9 = magenta,
  10–15 = green), not real colours.
- No `NLNHLB` frame (compressed Nuln Halberdiers) equals any of the 32 frames as a nibble plane
  (best agreement 1574–1721 of 2048 pixels), so its map cannot be proven to apply.
- Per-value vote against the best-matching `HALBERD` 8 bpp frames gives no consistent colour
  (every value mostly votes for indices 207/119/117), so these are different drawings, not a
  quantised copy.

`sprite3_frames00-31_4bit_standin.png` uses `NLNHLB.PAL` map 0 as a **stand-in** only, for viewing.

### Ready for `FORMATS.md`

> ### `SPRITE3.BTP` (and `SPRITE30.BOP`)
> Not a lookup table. 65536 B = 32 frames of 32×64, raw, one byte per pixel with values 0..15
> (0 = transparent), row-major. Byte-identical to `SPRITE3.BOP[0:65536]`, i.e. frames 0–31 of
> `SPRITE3.FOL` (a halberdier, 8 directions × 4 frames). `SPRITE30.BOP` is the same strip with
> frames 0–1 edited. No references in the executables; most likely development leftovers of the
> 4 bpp sprite pipeline. The engine does not need them. The real colours of the 16 values are unknown.

---

## 2. Legacy `.FOL` layouts: `HALBERD`, `SPRITE3`, `ICON2` ✅

### Detection over all 288 `.FOL` files (`legacy` subcommand)

- **285 files**: standard 16-byte record (all have `flags[3] == 0x40` and type 1/2/4).
- **2 files** (`HALBERD`, `SPRITE3`): 12-byte records.
- **1 file** (`ICON2`): 8-byte records.

The 12 and 8 byte layouts were accepted only if the frames tile the `.BOP` **exactly**: every
offset equals the end of the previous frame (`w*h`, raw 8 bpp), and the last frame ends at the
`.BOP` size. None of the three files fits the other layouts.

```c
struct FolEntry12 {        // HALBERD.FOL, SPRITE3.FOL
    int16_t  hotspot_x;    // always 0
    int16_t  hotspot_y;    // always 0
    int16_t  width;
    int16_t  height;
    uint32_t bop_offset;   // raw 8 bpp, width*height bytes, no compression, no flags
};

struct FolEntry8 {         // ICON2.FOL
    uint16_t unk;          // always 0 (probably hotspot, too small to tell)
    uint8_t  width;
    uint8_t  height;
    uint32_t bop_offset;   // raw 8 bpp, STANDARD.PAL
};
```

The "values growing like counters" in bytes 12–15 of FORMATS.md were simply the `bop_offset` of
the **next** record, read with the wrong record size.

### Contents (checked visually)

| File | Records | `.BOP` | Contents | Render |
|---|---|---|---|---|
| `HALBERD` | 97 = 96 × 32×64 + 1 × 16×24 | 196992 B, exact | 8 bpp halberdier (`STANDARD.PAL` indices, no values 1–9 or 246–255): 6 rows × 16 frames (walk and halberd attack, many directions) + small shield with a red/yellow emblem | `halberd.png` |
| `SPRITE3` | 35: 32 × 32×64, 16×24, 128×176, 120×152 | 106688 B, exact | frames 0–31: 4-bit halberdier (= `SPRITE3.BTP`, point 1); 32: the same shield (**byte-identical to `HALBERD` frame 96**); 33: portrait of a commander in a gold frame (white turban with a ruby); 34: mountain landscape | `sprite3_frames32-34_8bpp.png` |
| `ICON2` | 49: 60×60, 60×64, 52×52, 44×44, 32×48, 20×20, 44×52 | 132352 B, exact | gold command buttons (move, attack, shoot, magic, formation, retreat, hourglass, arrows), unit panel icons, 6 armour icons (tunic, mail, plate ± shield) | `icon2.png` |

`ICON2` is an older icon set: 31 of 49 frames are **byte-identical** to decoded `ICONS` frames
(indices 0–13, 35–40, 42–47, 60–64). The others are earlier versions of buttons (60×60, 44×44,
20×20) or are missing from `ICONS` (the armour icons, 44×52).

`HALBERD.PAL` is not used by `HALBERD.BOP` (8 bpp in `STANDARD.PAL`). It is the first 64 B of
`TESTSPR.PAL` (see point 5).

### Ready for `FORMATS.md` (replaces the "Exceptions" bullet)

> - Legacy layouts (development leftovers, all frames raw 8 bpp, no flags):
>   `HALBERD.FOL`, `SPRITE3.FOL` use 12-byte records `int16 hx, hy, w, h; uint32 bop_offset`;
>   `ICON2.FOL` uses 8-byte records `uint16 unk(0); uint8 w, h; uint32 bop_offset`. In all three
>   the frames tile the `.BOP` exactly. Detect the layout by `flags[3] == 0x40` (16 B) or by
>   exact tiling (12/8 B).

---

## 3. `SPELLS.PAL`: 43 maps with a 4-bit field ✅

### Rule

Frames using colour maps (types 2 and 4) are stored **grouped by map, in increasing map order**.
The high nibble of `kind` is the map number **modulo 16**. The real map index is:

```python
wraps, prev = 0, None
for rec in fol:                      # types 2 and 4 only, in file order
    n = rec.kind >> 4
    if prev is not None and n < prev:
        wraps += 1
    rec.map = n + 16 * wraps
    prev = n
```

In `SPELLS` the nibble runs 0..15, 0..15, 0..10, which gives exactly 43 contiguous groups for the
43 maps (frames 0–292 → maps 0–15, 293–528 → 16–31, 529–598 → 32–42). The engine can also keep a
running "map group" counter; both are equivalent here.

### Verification

- **Structural, all files** (`spells` subcommand, 141 `.FOL` with a variant B `.PAL`):
  - 139 files: `max(nibble)+1 == number of maps` and the rule gives the same (no wrap);
  - `SPELLS`: nibble max 15, rule max **42 = 43 maps − 1**, all 43 maps used, groups contiguous;
  - `NLNHLB`: 8 maps, only 0–3 used (see below).

  Without the rule, maps 16–42 (27 of 43, 22016 B file) would never be used. With it, every map is
  used exactly by one contiguous group.
- **Visual**: `spells_maps16-29_top_nibble_bottom_extended.png` and
  `spells_maps30-42_top_nibble_bottom_extended.png` show the same frame with map `n % 16` (top) and
  map `n` (bottom). The nibble-only row turns almost everything the fire orange of the first maps
  (orange skeletons, an orange cloud of skulls, a demon head in orange). The extended row gives
  coherent, distinct effects: **white skeletons** (undead summon), grey tornado with sand, blue ice
  shards, blue-white lightning, green spikes, green thorn cloud, red/green/blue sparkles, **black
  skulls**, a black demon head with red eyes, green/grey clouds. `spells_all_43_maps_extended.png`:
  one sample frame per map, all plausible.

Identical maps (probably the same effect used by several spells/schools):
`5=42, 6=35, 9=13, 16=17, 21=22=23, 26=36, 29=37, 30=31`.

The correct map is **stored in the file**, not chosen by the game. Which map belongs to which spell
(school of magic) still needs the spell table from the executables (ROADMAP 1.4).

### `NLNHLB.PAL`: extra maps (🟡 hypothesis)

8 maps, nibbles used 0–3. Maps 0–3 are identical, maps 4–7 are identical, and 4–7 differ from 0–3
in 5 entries (`m[7], m[10], m[12], m[14], m[15]`). Render `nlnhlb_top_maps0-3_bottom_maps4-7.png`:
the same halberdiers with orange/red tabard and plume (maps 0–3) vs green/blue (maps 4–7).
**Hypothesis:** a second livery (e.g. a second regiment or player colour) selected by the game with
an offset of +4 maps. It is the only file with unused maps.

### Ready for `FORMATS.md` (section "Color map" + decoder)

> The map number is `kind >> 4` **modulo 16**: frames of types 2/4 appear grouped by map in increasing
> order, so the full index is `nibble + 16 × (number of times the nibble decreased so far)`.
> This matters only for `SPELLS` (43 maps: frames 0–292 → 0–15, 293–528 → 16–31, 529–598 → 32–42),
> verified structurally on all 141 files and visually (white skeletons, blue ice, black skulls…
> instead of uniform orange). `NLNHLB.PAL` has 8 maps but uses 0–3; maps 4–7 are a second livery
> (hypothesis: chosen by the game).

Note: `scripts/render_sprites.py` currently uses `kind >> 4`, so `SPELLS` frames 293–598 render
with wrong colours.

---

## 4. The 84 type-2 frames without a `.PAL`: `ICONSTMP.FOL` ✅ / 🟡

### Which file

`orphans` subcommand: across all 16-byte `.FOL` without a `<NAME>.PAL`, only **`ICONSTMP`** has
type 2/4 frames: **84 × type 2 + 86 × type 1**, `kind` always `02` (map 0). All other files without
a `.PAL` (backgrounds, maps, portraits…) are type 1 only.

### What it is

- `ICONSTMP.FOL` has **no `ICONSTMP.BOP`** (the only `.FOL` without a `.BOP`).
- Its records tile a stream of exactly **341976 B** without gaps. `ICONS.FOL` tiles the real
  `ICONS.BOP` (410786 B) the same way.
- The first 16 records are identical to `ICONS.FOL` (w, h, offset, kind); after that the offsets
  diverge.
- LCS alignment on (w, h, kind) matches 147/170 records to `ICONS.FOL` (63 of 84 type-2 frames).
  Unmatched: 60×160, two 60×60, six 44×52, twelve 28×20, plus 640×8 and 2×296 type-1 strips.

So `ICONSTMP.FOL` is the index of an **earlier, smaller version of `ICONS.BOP`** (TMP = temporary),
left behind after the icon set was rebuilt.

### Visual check

- `iconstmp_type2_naive_on_icons_bop.png` (ICONSTMP offsets applied to today's `ICONS.BOP` with
  `ICONS.PAL`): first ~17 buttons correct, then shifted, sheared garbage.
- `iconstmp_type2_relinked_to_icons.png` (each record replaced with its aligned `ICONS` record):
  clean gold buttons (move, attack, shoot, magic, formations, turn, halt, flags, rooster, spyglass,
  hourglass, spanner, rewind/forward), digits 1–8, unit panel buttons.

The colour map is almost certainly `ICONS.PAL`: same frames, and `ICONS.FOL` also uses `kind = 02`
(map 0) for them. The 21 unmatched type-2 frames cannot be decoded, because their data is not in any
file (🟡).

### Ready for `FORMATS.md` (replaces the "84 frames of type 2" bullet)

> - `ICONSTMP.FOL` (the only `.FOL` without a `.BOP`) holds the 84 type-2 frames without their own
>   `.PAL`. It is an orphan index of an older 341976 B version of `ICONS.BOP`: the first 16 records
>   equal `ICONS.FOL`, 147/170 align by size and type, colours come from `ICONS.PAL`. The engine
>   should ignore it. Similarly `SPRITE30.BOP` has no `.FOL`, so there are 287 real `.FOL`/`.BOP` pairs.

---

## 5. The odd `.PAL`: `SYS.PAL` ✅ (+ `TESTSPR.PAL`, `HALBERD.PAL`)

`pal` subcommand, classification of all 151 `.PAL`:

| Class | Count | Files |
|---|---|---|
| B (colour maps, size multiple of 512) | 141 | sprite maps |
| A, sequential indices | 8 | `BKMOUNT, HALBERD, NIGHT, PANEL, RICH, STANDARD, UNDERWAY, WIND` |
| A, sequential **and** a multiple of 512 | 1 | `TESTSPR` (1024 B = 256 × 4, indices 0–255) |
| A, increasing indices with a gap | 1 | **`SYS`** (80 B) |

(FORMATS.md said 9 A + 141 B + 1 other. The 9 A include `TESTSPR`, which as a 1024 B file also
looked like B. Nothing uses it as B: it has no `.FOL`.)

### `SYS.PAL`

Same 4-byte format as variant A (`index, R, G, B`), but the indices are **0–9 and 246–255**:
exactly the 20 colours Windows reserves (the complement of the 10–245 range of the game palettes).
Colours: index 0 = `00 00 ff`, 1–9 and 246–254 = `ff 00 ff` (magenta), 255 = `ff ff ff`.
These are not the real Windows static colours but **markers**, so a developer tool could show at a
glance that a bitmap uses reserved slots. The parser for variant A works as is, as long as it does
not assume sequential indices (`load_rgb_palette` in `render_sprites.py` does not).

### `TESTSPR.PAL` and `HALBERD.PAL` (debug palettes)

- `TESTSPR.PAL`: 256 entries. 0 = blue, 1–9 = magenta, 10–105 = green (`00 ff 00`, one entry
  `2b ff 27`), 106–245 = real game colours (129/140 equal to `STANDARD.PAL`, differing: 190, 191,
  198, 230–237), 246–254 = magenta, 255 = `bb ff ff`. So "system slots" and the range 10–105 are
  masked, and only the 106–245 range (= `PANEL.PAL`/`WIND.PAL`) is shown in real colours.
- `HALBERD.PAL` = first 64 B of `TESTSPR.PAL` (entries 0–15). Placeholder, not the colours of
  `HALBERD.BOP`.

Renders: `sys_pal_16x16.png`, `testspr_pal_16x16.png` (absent indices dark grey).

### Ready for `FORMATS.md` (replaces "1 file does not fit either variant")

> `SYS.PAL` (80 B) is variant A with non-sequential indices 0–9 and 246–255 (the Windows reserved
> colours), filled with marker colours (magenta, 0 = blue, 255 = white). `TESTSPR.PAL` (1024 B,
> indices 0–255) is a debug palette: reserved slots magenta, 10–105 green, 106–245 ≈ `STANDARD.PAL`.
> `HALBERD.PAL` is its first 16 entries. Variant A parsers must not assume sequential indices.

---

## 6. `UPDATE/BINARY` vs `FILE/BINARY` ✅

`patch` subcommand (recursive, names compared case-insensitively):

- `FILE/BINARY`: 911 files; `UPDATE/BINARY`: 731 files.
- Only in `FILE`: 180 files, all in subdirectories `GLUE/` (25: `.PAL`, `.FON`), `MUSIC/` (40 `.MID`),
  `SOUND/` (115). Only in `UPDATE`: none.
- Common: 731 (288 `.BOP`, 288 `.FOL`, 151 `.PAL`, 3 `.FON`, 1 `.BTP`). **Byte-different: 0.**
  Same letter case of names.
- `REMOTE/BINARY` (687 files: `ANIM/`, `GLUE/SPEECH/`) has no path in common with `FILE/BINARY`.

So in this GOG installation the patch **changed nothing** in the sprite/palette data. `UPDATE/BINARY`
is a full copy of the top level of `FILE/BINARY`. There are no "old vs new" frames to compare.
Hypothesis: the original 1995 patch replaced some of these files, and the GOG release ships the
patched versions in both places. The executables may still differ from the retail CD (not checked).

### Ready for `FORMATS.md` / `ROADMAP.md`

> `UPDATE/BINARY` (731 files) is byte-identical to the top level of `FILE/BINARY`; it lacks only the
> `GLUE/`, `MUSIC/`, `SOUND/` subdirectories. Checks done on `FILE` are therefore valid for `UPDATE`.
> The lookup order UPDATE → FILE still matters for the subdirectories (they only exist in `FILE`).

---

## Open questions

1. Real colours of the 4-bit values in `SPRITE3.BTP` / `SPRITE3` frames 0–31 (no matching map).
   Low priority, since these are leftovers.
2. Which map in `SPELLS.PAL` belongs to which spell/school (needs the `SpellSprites` table in
   `GAMEF.DLL`/`WHSHR.EXE`, ROADMAP 1.4).
3. `NLNHLB.PAL` maps 4–7: when does the game use the second livery? Do other units get colour
   variants some other way (e.g. a different `.PAL` or a map offset in the unit table)?
4. The 12-byte `hotspot` and 8-byte `unk` fields are always 0, so their meaning cannot be derived
   from these files.
5. Whether the executables load any of `SPRITE3.*`, `SPRITE30.BOP`, `HALBERD.*`, `ICON2.*`,
   `ICONSTMP.FOL`, `TESTSPR.PAL`, `SYS.PAL` (no string found; confirm by logging file opens under Wine).

## Proposed changes

### `FORMATS.md`

- `.PAL` section: replace "1 file does not fit either variant" with the `SYS.PAL` / `TESTSPR.PAL`
  text from point 5.
- `.FOL` section: replace the "Exceptions" bullet with the legacy layouts from point 2; state that
  the pair count is 287 (+ `ICONSTMP.FOL`, `SPRITE30.BOP` orphans).
- "Color map": add the modulo-16 rule from point 3; in the reference decoder replace
  `map = fol.kind >> 4` with the extended index.
- Open questions: remove the items for SPELLS 43 maps, 84 type-2 frames, the odd `.PAL`, legacy
  `.FOL` layouts and "UPDATE not tested"; add questions 1–3 above.
- New short section for `SPRITE3.BTP` (text from point 1).

### `ROADMAP.md`

- Terrain table row "`SPRITE3.BTP` table": change to ✅ "not a LUT; a copy of 32 frames of
  `SPRITE3.BOP` (developer leftover)", type "raw 4-bit".
- 1.7: mark ✅ and replace the task with "done: not a LUT (notes/btp_sprite_leftovers.md)".
- The sentence "`UPDATE/BINARY` is a full copy of `FILE/BINARY` with fixes" → "byte-identical copy
  of the top level of `FILE/BINARY` (no subdirectories); in the GOG version the patch changes nothing".
- Phase 0 `whshr check`: include the map index rule and the legacy layout detection; skip
  `ICONSTMP.FOL` and `SPRITE30.BOP` explicitly.
- 1.4 (names → files): add "map ↔ spell mapping for `SPELLS.PAL` (43 maps) and use of `NLNHLB` maps 4–7".

### `scripts/render_sprites.py` (owner's decision; not edited here)

- Use the extended map index (`btp_lib.extended_map_indices`); today `SPELLS` frames 293–598 get
  wrong colours.
- Refuse or special-case files with legacy layouts (`HALBERD`, `SPRITE3`, `ICON2`) and `ICONSTMP`
  (no `.BOP`).
