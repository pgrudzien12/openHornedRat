# Fonts (`.FON`) and front-end ("glue") palettes — ROADMAP 1.6

Findings from black-box analysis of the files plus string references in `WHSHR.EXE` /
`GAMEF.DLL`, plus (§2) the front end's glue font selection and UI painting — described here as behaviour only. Everything
below was checked on **all** files of each type.

| Item | Status |
|---|---|
| `.FON` container (NE + `RT_FONTDIR`/`RT_FONT`) | ✅ Fully understood, all 12 files parse and pass consistency checks |
| FNT glyph data (FNT 2.0 and 3.0, 1-bit raster) | ✅ Fully understood, verified visually (charts of all 9 unique fonts) |
| Font number (1–6) → `.FON` file | ✅ Confirmed by static analysis: the number selects one of six literal face-name strings baked into `WHSHR.EXE`, matching each file's own `dfFace` |
| Which font is used for which UI element | 🟡 Font 2 (`PCTEXT.FON`) confirmed for the mission title, mission-list rows and control-panel buttons (§2); other elements still hypotheses from names |
| `GLUE/*.PAL` format | ✅ Variant A, all 19 files; verified visually on bitmaps from `BITMAP.DLL` |
| Which palette belongs to which screen | 🟡 7 of 10 matched exactly to bitmaps; `GAME`, `OPT`, `REND` still open |

## 1. File inventory

| Location | Files | Notes |
|---|---|---|
| `FILE/BINARY/` (top level) | `PCSUBT.FON` 12288 B, `PCTEXTA.FON` 7680 B, `PCTEXTAB.FON` 8192 B, `SPRITE3.BTP` 65536 B | the fonts are loaded by `GAMEF.DLL` (battle) as `binary\pcsubt.fon` etc. |
| `FILE/BINARY/GLUE/` | 6 × `.FON`: `GOTHTEXT` 24576, `MAPTEXT1` 9216, `PCTEXT` 7680, `PCTEXTB` 8192, `SMAPTEX1` 5632, `SUBTEXT` 12288 B; 10 × `GLUE*.PAL` (384 B each); 9 × `WIND*.PAL` (560 B each) | nothing else in this directory; loaded by `WHSHR.EXE` (front end, source path `C:\WARFB\WINDOWS\GLUE\glue.c`) |
| `UPDATE/BINARY/` | the same 3 `.FON` as `FILE/BINARY` + `SPRITE3.BTP` | the 3 fonts are **byte-identical** to `FILE` (same MD5). No `GLUE` subdirectory, so the patch changes no glue fonts or palettes |
| `REMOTE/BINARY/GLUE/SPEECH/` | 567 × `.WAV` | `WHSHR.EXE` loads them as `binary\glue\speech\b%s.wav`; audio, outside the scope of this task |

"Glue" is the developers' name for the front end: menus, caravan, campaign map, briefings
(`GlueWindow`, `GlueButtons`, `[CleanUpGlue]`, `LoadGlueScript`…).

## 2. `.FON` — Windows bitmap fonts (text ready for FORMATS.md)

**Fully understood and verified visually.** These are ordinary Windows 3.x font files:
a 16-bit **NE** executable containing only resources. No game-specific wrapper.

### Container (NE)

- `MZ` stub ("This program requires Microsoft Windows."), `e_lfanew` = `0x80`, `NE` header
  (linker 5.30, target OS 2 = Windows).
- Module name (resident name table): `FONTRES`. Description (non-resident name table):
  `FONTRES 267,28,75 : <face name>`, the same "267,28,75" in every file (aspect/resolution
  string left by the font compiler).
- Resource table (`rscAlignShift` = 9, so offsets and lengths are in 512-byte units), always
  exactly two resources:
  - `RT_FONTDIR` (type `0x8007`), name `FONTDIR`: `u16 count` (1), then per font `u16 ordinal`
    + `FONTDIRENTRY` (the first 105 bytes of the FNT header + `u32` reserved + ASCIIZ device
    name + ASCIIZ face name). It matches the FNT header in every file.
  - `RT_FONT` (type `0x8008`), id **1001**: the FNT data itself. `dfSize` gives its exact length.

### FNT header

Standard layout (field names as in the Windows SDK). Offsets are relative to the start of the
`RT_FONT` resource.

| Offset | Field | Offset | Field |
|---|---|---|---|
| 0 | `u16 dfVersion` (`0x200` / `0x300`) | 88 | `u16 dfPixHeight` |
| 2 | `u32 dfSize` | 90 | `u8 dfPitchAndFamily` |
| 6 | `char dfCopyright[60]` | 91 | `u16 dfAvgWidth` |
| 66 | `u16 dfType` (bit 0 = vector) | 93 | `u16 dfMaxWidth` |
| 68 | `u16 dfPoints` | 95 | `u8 dfFirstChar` |
| 70 | `u16 dfVertRes`, 72 `u16 dfHorizRes` | 96 | `u8 dfLastChar` |
| 74 | `u16 dfAscent` | 97 | `u8 dfDefaultChar` (relative to `dfFirstChar`) |
| 76 | `u16 dfInternalLeading`, 78 `u16 dfExternalLeading` | 98 | `u8 dfBreakChar` (relative) |
| 80 | `u8 dfItalic`, 81 `dfUnderline`, 82 `dfStrikeOut` | 99 | `u16 dfWidthBytes` |
| 83 | `u16 dfWeight` | 101 | `u32 dfDevice`, 105 `u32 dfFace` (offset of ASCIIZ face name) |
| 85 | `u8 dfCharSet` | 109 | `u32 dfBitsPointer`, 113 `u32 dfBitsOffset`, 117 `u8 dfReserved` |
| 86 | `u16 dfPixWidth` (0 = proportional) | 118 | FNT 3.0 only: `u32 dfFlags`, `u16 dfAspace/Bspace/Cspace`, `u32 dfColorPointer`, `u8 dfReserved1[16]` (up to 148) |

### Character table and glyph bitmaps

- Character table right after the header: at 118 (FNT 2.0, entries `u16 width, u16 offset`)
  or 148 (FNT 3.0, entries `u16 width, u32 offset`). It has
  `dfLastChar - dfFirstChar + 2` entries; the last one is a sentinel whose offset points just
  past the last bitmap.
- Offsets are relative to the start of the FNT resource. In all game fonts the bitmaps follow
  the table contiguously, in character order, with no gaps. The face name comes right after the
  bitmaps and ends exactly at `dfSize`.
- Glyph bitmap = `dfPixHeight × ceil(width / 8)` bytes, 1 bit per pixel, MSB first.
- **The bytes are stored column-major:** first byte-column 0 (glyph pixels x = 0..7) for all
  `dfPixHeight` rows, then byte-column 1 (x = 8..15) for all rows, and so on.
  - For glyphs up to 8 px wide this is the same as row order, which is why a row-major reader
    looks almost right. Wider glyphs (`W`, `M`, all of `GOTHTEXT`) come out as vertically
    squashed stripes.
  - The same layout is found in Wine's reference fonts (`sserife.fon`, `vgasys.fon` from
    Proton). FreeType's `winfnt.c` reads it the same way ("glyphs are stored in columns and not
    in rows"). So this is the normal FNT layout, not a game quirk.

```c
// pixel (x, y) of a glyph: height = dfPixHeight, bits = font + entry.offset
uint8_t b = bits[(x >> 3) * height + y];
int on = (b >> (7 - (x & 7))) & 1;
```

- Text layout: advance = glyph width, no kerning (`dfAspace/Bspace/Cspace` = 0). Characters
  outside the range map to `dfFirstChar + dfDefaultChar` = `0x80`.
- **Harmless inconsistency:** in 5 of 6 fonts `dfMaxWidth` in the header is larger than the
  widest glyph (e.g. `MAPTEXT1` 20 vs 16, `SUBTEXT` 30 vs 27), apparently a stale header.
  Use the character table.
- No vector fonts (`dfType & 1`) and no color fonts (`dfFlags & 0xE0`) in the game.

### The fonts

All: weight 700 (bold), not italic, `dfCharSet` = 0 (**ANSI / cp1252**, Western European),
proportional, `dfFirstChar`–`dfLastChar` = `0x20`–`0xFF` (224 entries), default char `0x80`,
copyright `(c) Copyright Mindscape. 1995. All rights reserved.` (`SUBTEXT`/`PCSUBT`:
`(c)Copyright Mindscape Inc. 1995. All rights reserved`). Codes without a real glyph hold a
placeholder: a solid block, or a thin bar in `GOTHTEXT`/`SUBTEXT`.

| File | Loaded by | Face name | FNT | pt | Height | Ascent | Avg/max width | Look | Real glyphs |
|---|---|---|---|---|---|---|---|---|---|
| `GLUE/MAPTEXT1.FON` | `WHSHR.EXE` | `Warhammer Font 1` | 3.0 | 30 | 12 | 8 | 12 / 16 | serif **capitals only** | `A–Z`, accented capitals `À–ß`, `Š Œ Ÿ`; no lowercase, digits or punctuation |
| `GLUE/PCTEXT.FON` | `WHSHR.EXE` | `Warhammer Font 2` | 3.0 | 31 | 12 | 9 | 9 / 13 | light calligraphic, readable body text | letters, digits, `! " % ' ( ) + , - . / : ; = ? [ ]`, `‰ Š Œ š œ Ÿ ¡ © ¿`, `À–ÿ` (no `# $ & * < > @ \ ^ _ \` { | } ~`) |
| `GLUE/SMAPTEX1.FON` | `WHSHR.EXE` | `Warhammer Font 3` | 3.0 | 20 | 8 | 5 | 7 / 11 | small serif | letters only: `A–Z a–z`, accented `À–ÿ`, `Š Œ Ÿ`; **no digits or punctuation** |
| `GLUE/SUBTEXT.FON` | `WHSHR.EXE` | `Warhammer Font 4` | 2.0 | 13 | 22 | 17 | 12 / 27 | Times-like serif | letters, digits, `! " % ' ( ) + , - . / : ; = ? _`, `‰ Š Œ š œ Ÿ ¡ © ¿`, `À–ÿ` |
| `GLUE/GOTHTEXT.FON` | `WHSHR.EXE` | `Warhammer Font 5` | 2.0 | 25 | 40 | 32 | 16 / 41 | **blackletter (Gothic)** | complete cp1252: 196 glyphs, all of ASCII and `0xA0–0xFF` |
| `GLUE/PCTEXTB.FON` | `WHSHR.EXE` | `Warhammer Font 6` | 3.0 | 31 | 12 | 9 | 9 / 16 | bold version of `PCTEXT` | same set as `PCTEXT` |
| `PCTEXTA.FON` | `GAMEF.DLL` | `WarhammerA` | 3.0 | | | | | **same glyphs as `PCTEXT`** | |
| `PCTEXTAB.FON` | `GAMEF.DLL` | `WarhammerABold` | 3.0 | | | | | **same glyphs as `PCTEXTB`** | |
| `PCSUBT.FON` | `GAMEF.DLL` | `WarhammerSubText` | 2.0 | | | | | **same glyphs as `SUBTEXT`** | |

- The three `FILE/BINARY` fonts have glyph data (widths + bitmaps) identical to their `GLUE`
  counterparts (same hash in `fon_parse.py --check`). Only the face name, and therefore the
  file, differs. **Hypothesis:** they were renamed so that the front end and the battle engine
  can both register their fonts with `AddFontResourceA` at the same time without clashing.
- The code uses GDI: `AddFontResourceA`, `CreateFontIndirectA`, `EnumFontFamiliesA`,
  `RemoveFontResourceA`. `WHSHR.EXE` selects fonts by number (it reports "Font %d not
  found"/"not loaded" errors), which fits the face names `Warhammer Font 1..6`.
- **Font number → file, confirmed ✅.** This is not just a naming coincidence: selecting font `N`
  looks `N` up in a fixed-size table of font records (one per registered `.FON`) and builds a
  `LOGFONTA` whose face name is one of the six literal strings `"Warhammer Font 1"`…`"Warhammer
  Font 6"` found in `WHSHR.EXE`, in that numeric order, before calling `CreateFontIndirectA`. Those
  strings are the exact `dfFace` values read out of the six `GLUE/*.FON` files themselves
  (`fon_parse.py`), so the mapping is fixed by the files' own embedded face names, not guessed from
  filenames:

  | Font # | Face name (in the `.FON` file) | File |
  |---|---|---|
  | 1 | `Warhammer Font 1` | `GLUE/MAPTEXT1.FON` |
  | 2 | `Warhammer Font 2` | `GLUE/PCTEXT.FON` |
  | 3 | `Warhammer Font 3` | `GLUE/SMAPTEX1.FON` |
  | 4 | `Warhammer Font 4` | `GLUE/SUBTEXT.FON` |
  | 5 | `Warhammer Font 5` | `GLUE/GOTHTEXT.FON` |
  | 6 | `Warhammer Font 6` | `GLUE/PCTEXTB.FON` |

  (`PCTEXTA.FON`/`PCTEXTAB.FON`/`PCSUBT.FON` are `GAMEF.DLL`'s own copies, registered under
  different face names `WarhammerA`/`WarhammerABold`/`WarhammerSubText` for the battle engine, not
  reachable through this glue-side numbering.)
- **Hypotheses about use (from names only, not checked in game):**
  - `MAPTEXT1`/`SMAPTEX1`: campaign map labels. The printed labels on the `MAP` bitmap use a
    similar capital serif style.
  - `SUBTEXT`/`PCSUBT`: subtitles for speech and cutscenes.
  - `GOTHTEXT`: headings and titles.
  - `PCTEXT`/`PCTEXTB`: general UI text, regular and bold.
- **Confirmed by static analysis (§6):** font 2 = `PCTEXT.FON` (12px height, 9px ascent, ~9/13px
  avg/max glyph width) is the font `WHSHR.EXE`'s built-in painters use for the mission title, the
  mission-list scroll-row labels, and the control-panel button labels (Brief/Accept/Caravan/etc.) —
  all three request font number 2.
- Languages: the accented Latin-1 letters (`ÄÖÜß`, `éèêàç`, `ñ`…) suggest the fonts were
  prepared for German/French/Spanish/Italian versions. The punctuation gaps (no `#`, `&`, `@`,
  and no digits at all in the map fonts) show which characters the game text actually needs.

### Rendering: how glyphs reach the screen

**Confirmed for the front end (`WHSHR.EXE`), behaviour only.**

- Creating font N does not build a fresh `LOGFONTA` from scratch. At startup the game
  enumerates its own installed raster fonts (`EnumFontsA`/`EnumFontFamiliesA` with the
  `"Warhammer Font N"` face names) and, in the enumeration callback, copies the **exact
  `LOGFONTA` GDI reports back for that already-installed resource** (including its native
  `lfHeight`) into a small per-font table. Font creation later looks up that table by
  index or by face-name string compare and passes the stored, unmodified `LOGFONTA` straight
  to `CreateFontIndirectA`. There is no separate, hand-picked `lfHeight` value chosen by the
  game — it always requests the font at exactly the pixel size the raster resource itself
  reports. **This rules out GDI raster-font stretching (question 3): the requested size always
  matches the native size, so `StretchBlt`-style row/column duplication never comes into play
  for these fonts.**
- If the named font resource is not found (not registered/loaded), font creation fails
  outright and logs an error — there is no fallback to a system TrueType font by charset or
  typeface (question 4). The lookup is a plain table/string match against the game's own six
  `"Warhammer Font N"` resources, nothing else.
- Text is drawn with plain, ordinary GDI calls: `SelectObject` the font so created, `SetBkMode(TRANSPARENT)`, `SetTextColor(...)`, then `TextOutA(hdc, x, y,
  text, len)`. This pattern repeats at every text-drawing call site checked (button/tab
  labels, mission scroll-row labels, mission title). There is no custom glyph-blit routine,
  no lookup table indexed by neighboring glyph bits, no blend/grey edge color, and no
  supersampling or blur pass anywhere near these call sites (question 2) — the game hands the
  1-bpp raster glyph straight to `TextOutA` and lets GDI's ordinary raster-font path put it on
  the (palettized, 8-bpp) screen DC.
- **Conclusion:** the original game renders this UI text as a plain, aliased, pixel-exact
  bit-blit of the `.FON` glyph bitmaps — the same crisp "on/off" pixels the `.FON` file itself
  stores, with GDI requested at the font's native size. There is **no antialiasing, dithering,
  edge-softening or bitmap stretching anywhere in this path** (questions 1–3 answered
  negatively). Any perceived difference in crispness between the original (under Wine/Proton)
  and the from-scratch engine is therefore not explained by a missing AA/smoothing technique
  in the original — it must have another cause outside this note's scope (the engine
  currently substitutes SDL's own antialiased system font instead of decoding the real `.FON`
  glyphs at all, which is a materially different rendering path already noted as a known
  placeholder in the engine).
- Confidence: high for "plain `TextOutA`, no stretching, no fallback font, no custom
  blit/AA" (directly confirmed at the enumeration/`CreateFontIndirectA`/`TextOutA` call
  sites); the one residual uncertainty is whether *some* other, not-yet-located screen in the
  game routes text through a different painter than the three checked here — the pattern was
  consistent everywhere it was checked, so this is considered unlikely but not exhaustively
  proven for every screen.

## 3. `FILE/BINARY/GLUE/*.PAL` — front-end palettes (text ready for FORMATS.md)

**Format fully understood (variant A); screen assignment partly verified.**

- All 19 files are **variant A** (records `[index, R, G, B]`, sequential indices, no header).
- They come in two families that together cover exactly the 236 application colors
  `10..245`:

| Family | Files | Size | Indices | Entries |
|---|---|---|---|---|
| `GLUE<screen>.PAL` | `BK2 BOOK CAR END GAME MAP MIND OPT REND TITL` (10) | 384 B | **10–105** | 96 |
| `WIND<screen>.PAL` | `BK2 BOOK CAR END GAME MAP MIND OPT TITL` (9) | 560 B | **106–245** | 140 |

- `WIND*` uses the same index range as the battle `PANEL.PAL`. `WINDBK2` and `WINDMAP` equal
  `STANDARD.PAL`/`PANEL.PAL` at 136 of 140 indices (`WINDBOOK` at 134). So the upper range is
  mostly the shared UI/"window" color set, with small changes per screen.
- `WHSHR.EXE` lists both families in the same order, `book, map, car, mind, end, titl, game,
  opt, bk2` (plus `binary\standard.pal` twice). They are loaded by index
  (`[SetWinGPalette] Palette %d loaded`). There is also `[SetWinGPaletteFromDIB]`, so some
  screens take their palette from the bitmap itself.
- `GLUEREND.PAL` is **not referenced** by `WHSHR.EXE`, and there is no `WINDREND.PAL`.
- No two files are identical. Near-duplicates:
  - `GLUEEND`/`GLUETITL` differ at 2 indices (27, 50);
  - `WINDEND`/`WINDTITL` differ at 2 (244, 245);
  - `WINDBK2`/`WINDMAP` differ at 4 (238–241);
  - `WINDBOOK` differs from both at 10 indices.
- `WINDGAME` (84 entries), `WINDOPT` (44) and `GLUEREND` (40) contain long runs of pure green
  `(0,255,0)`. **Hypothesis:** unused slots filled with a marker color.

### Which screen uses which palette (verified against `BITMAP.DLL`)

The 717 bitmaps in `FILE/DLL/BITMAP.DLL` (8 bpp DIBs) were grouped by color table, and each
table was compared entry by entry with every `GLUE*`/`WIND*` file (`fon_glue_palettes.py --dib`).

| Palette pair | Exact match (100% / 100%) with | Meaning (name-based for `BK2`) |
|---|---|---|
| `TITL` | `TITLESCREEN` | title screen |
| `MIND` | `MINDSCAPELOGO` | Mindscape logo |
| `END` | `ENDSCREEN` | end screen |
| `CAR` | `CARAVAN`, `READBACKGROUNDPIC`, `TALKBACKGROUNDPIC`, `DIETBOOKCELL*`, `CARCANDLECELL*` (42 bitmaps) | caravan (hub with the advisor, candle animation, books) |
| `MAP` | `MAP`, `MAPBORDER0`, `MAPTITLE`, `FRAMEPANEL*`, `FRAMELEFT`… (16) | campaign map. `LOADSAVEWINDOW*`: GLUE 100%, WIND 98% |
| `BK2` | 33 regiment portraits `*PIC` (`GRUDGEBRINGERS2PIC`, `TREEMANPIC`…) | "book 2", probably the troop roster |
| `BOOK` | `BRIGHT/AMBER/CELESTIALMAGICPIC`. Magic item pictures `BANOF*PIC`, `ARMOF*PIC`: GLUE 94%, WIND 100% | books (magic, items) |
| `REND` (GLUE only) | GLUE part matches `TROOPBOOK`, `RINGMARK`, `*ATABUP` tabs 100% (WIND part: `WINDBOOK` 92%) | unreferenced leftover, apparently for the troop book |
| `GAME`, `OPT` | **none** | hypothesis: in-game menu / options screen |

- The largest group (511 small animation cells `AM1CELL*`, `RE6CELL*`…) and 12 others
  (`SCROLL0/1`, `FRAMEBUTTON*`) match `GLUEMAP` 100% and `WINDBOOK` 91%.
- Bitmaps with their own palettes that match nothing (mean per-channel difference 43–81):
  `OPTIONSCREEN`, `MOREOPTIONSCREEN`, `OPTIONSCREENDEMO`, `GAMESTARTSCREEN`, `GAMEENDSCREEN*`,
  `DEADSCREEN`, `PLACEA6/7`, enemy portraits (`DOOMWHEELPIC`, `SEERPIC`…), `ARMYBOOK`/`ENCYBOOK`
  (GLUEREND 95%). These presumably use `SetWinGPaletteFromDIB`.

**Visual check:** `fon_glue_palettes.py --render` draws a bitmap with colors taken **only** from
`STANDARD.PAL` + `GLUE<x>.PAL` + `WIND<x>.PAL`, ignoring the DIB's own color table.
- `TITLESCREEN`+`TITL`, `CARAVAN`+`CAR` and `MAP`+`MAP` come out with correct colors: gold
  logo, candle-lit caravan interior, parchment map.
- Negative control: `TITLESCREEN`+`CAR` gives a green background and garbled logo colors.
- A line of `GOTHTEXT.FON` text drawn over the title and caravan screens looks right: this is
  the "rendered menu text" check from the roadmap.

## 4. How it was verified

- `fon_parse.py --check FILE/BINARY UPDATE/BINARY` checks all 12 `.FON` files:
  - NE resource table, and the `RT_FONTDIR` entry equal to the FNT header;
  - glyph offsets contiguous, sentinel = end of bitmaps, face name ending at `dfSize`;
  - bitmaps inside the resource, glyph widths ≤ `dfMaxWidth`.

  Result: 0 problems. Glyph hashes show the 3 renamed duplicates and the identical `UPDATE` copies.
- Character charts of all 9 fonts (`extracted/fonts_glue/font_*.png`) viewed one by one: every
  glyph readable, accented letters in the cp1252 positions. The first attempt used row-major
  order; wide glyphs came out as stripes, which is how the column-major layout was found.
- The column-major layout was checked on Wine's reference fonts (Proton `share/wine/fonts`) and
  in FreeType's `src/winfonts/winfnt.c`.
- Palettes: index ranges, sequential order and file sizes checked for all 19 files; strips viewed
  (`glue_palettes.png`); DIB color-table comparison and renders as described above.

## 5. Scripts

```
# fonts (NE + FNT parser, charts, text)
python3 scripts/fon_parse.py ".../WARFB/FILE/BINARY/GLUE/GOTHTEXT.FON"                # header dump
python3 scripts/fon_parse.py ".../GLUE/GOTHTEXT.FON" --chart gothtext.png 3            # character chart
python3 scripts/fon_parse.py ".../GLUE/SUBTEXT.FON" --text "Grudgebringers" out.png 3  # one line of text
python3 scripts/fon_parse.py --check ".../WARFB/FILE/BINARY" ".../WARFB/UPDATE/BINARY"  # all fonts

# glue palettes
python3 scripts/fon_glue_palettes.py ".../WARFB" extracted/fonts_glue/glue_palettes.png 4   # table + strips
python3 scripts/fon_glue_palettes.py ".../WARFB" --dib                                      # match BITMAP.DLL
python3 scripts/fon_glue_palettes.py ".../WARFB" --render TITLESCREEN TITL out.png "Shadow of the Horned Rat"
```

API: `fon_parse.load_fon(path)` → `.fonts[0]` with `.hdr`, `.face`, `.glyphs`,
`.pixel(code, x, y)`, `.render(text)`. `fon_glue_palettes.read_pal()`, `glue_pals()`, `dib()`.
`fon_parse.tiny_text()` is a 3×5 label font for debug images.

Outputs (local only, `extracted/` is git-ignored):
- `extracted/fonts_glue/font_<NAME>.png`: 9 charts;
- `text_GOTHTEXT.png`;
- `glue_palettes.png`: 19 palettes + `STANDARD`/`PANEL` + 9 merged pairs;
- `verify_TITLESCREEN_TITL.png`, `verify_TITLESCREEN_CAR_wrong.png`, `verify_CARAVAN_CAR.png`,
  `verify_MAP_MAP.png`, `verify_MINDSCAPELOGO_MIND.png`.

## 6. Open questions
> **Historical questions:** issue #33 is closed. These notes preserve the findings; the remaining unknowns are not standing research tasks. Reopen a focused issue only when a shipped feature or reproducible defect needs an answer.


- ✅ Which font number is used for the mission-list/button UI elements not declared via `[TEXT]
  set:font=`. Resolved for the front end (`WHSHR.EXE`, behaviour only): both the
  mission-list row painter (draws each row's `Scroll0`/`Scroll1` bitmap plus the `BRTXT` mission
  name/payment label) and the shared control-panel button-label painter (used for Brief/Accept/Caravan and every other button label) both request font
  number 2, i.e. font 2 = `PCTEXT.FON`. This is the same font number already used by
  the mission title and town-name `[TEXT]` blocks (`set:font=2`, grep-confirmed in the WND.DLL glue
  scripts), so all three UI elements — mission title, mission-list rows, and button labels — render
  in `PCTEXT.FON`'s 12px-tall / 9px-ascent glyphs (see the font table in §2). Colors are set
  per-call (`SetTextColor`) rather than being fixed to the font. Other UI font numbers (colors for
  each specific screen) remain unconfirmed; only font 2's usage for these three elements was
  checked.
- Which screens use `GLUEGAME`/`WINDGAME` and `GLUEOPT`/`WINDOPT`: no bitmap in `BITMAP.DLL`
  matches them. Maybe bitmaps in `WND.DLL` or the `.SI` cutscene files, or palettes left over
  from an older version of the option screens.
- Why `GLUEREND.PAL` exists (unreferenced, but exact for `TROOPBOOK`), and whether the game
  applies it under another name.
- The exact rule for palettes: when `SetWinGPalette` (GLUE+WIND files) is used and when
  `SetWinGPaletteFromDIB`. Also what happens to indices 0–9/246–255 (Windows system colors).
- The meaning of the odd `dfVertRes`/`dfHorizRes` values (e.g. 240/205, 28/75). Probably
  font-editor artifacts, with no effect on rendering.

## 7. Proposed changes

**ROADMAP.md**
- Terrain map row "Fonts, UI palettes": status ⬜ → ✅, kind "FON = standard NE/FNT (column-major
  glyphs); PAL = variant A, GLUE 10–105 + WIND 106–245".
- Task 1.6: mark ✅ (format + visual check done). Add a follow-up line: "🟡 screen→palette
  mapping for `GAME`/`OPT`/`REND` and font number→UI element (needs screenshot or 4.2)".
- Task 1.1 (PE bitmaps): the front-end bitmaps need the matching `GLUE+WIND` pair or their own
  DIB palette. `fon_glue_palettes.py --dib` gives the mapping.

**FORMATS.md**
- Replace the two bullets on `windbk2.pal…` and `.FON` in "Other files (unexplored)" with
  sections 2 and 3 of this note. The existing bullet also names `PCTEXT.FON` as if it were in
  `FILE/BINARY`; it is in `GLUE`, while `FILE/BINARY` holds `PCTEXTA`/`PCTEXTAB`/`PCSUBT`.
- In the variant A description, add that the `GLUE` palettes are split into 10–105 and 106–245.
