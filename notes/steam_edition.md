# Steam "Classic" edition — data differences from GOG v1.0 (issue #466)

Compared file by file: a GOG v1.0 installation (`$WARFB`) against the Steam edition "Warhammer: Shadow of the
Horned Rat (Classic)" (Steam app 4280870, game root = `steamapps/common/Warhammer Shadow of the Horned Rat`).
Tracking issue: [#466](https://github.com/pgrudzien12/openHornedRat/issues/466). The folder layout (no `WARFB`,
`REMOTE/` and `UPDATE/` merged into `FILE/`, new `DOCS/`, `LICENSE/`) is described in the issue and handled by
draft PR #467; this report covers what changed **inside** the files and how a reader should treat it.

Related reports: `FORMATS.md` (`.BOP` type 4 zero-RLE), `notes/music.md`, `notes/si_omni.md`, `notes/sfx.md`,
`notes/palette_selection.md`, `notes/builtin_widgets.md` (options screen), `notes/terrain_gd.md`.

## 1. Summary

| What | Kind of change | Effect | What a reader/engine should do |
|---|---|---|---|
| Data corruption across many files (§2) | ~3 500 isolated bytes `FF` → `DF` (a few → `CF`/`EF`) | sprites, speech, film audio, palettes, one SBK sample, two terrain files | repair sprite frames (§3); everything else can be read as is |
| 14 `.BOP` sprite files (§3) | 26 type-4 frames have a shortened zero run | 20 frames visibly shifted if decoded literally, 6 invisible | apply the repair rule of §3.3 (restores the GOG frames exactly), never raise on a short frame |
| `MAP1.BOP` (type 1) | 12 pixels change colour index 255 → 223 | placeholder picture only | nothing |
| 29 films `.SI` (§4) | only the embedded WAV sound streams | single-sample clicks | nothing; video streams are byte-identical |
| 399 of 567 speech `.WAV` (§4) | sample data only, same format | single-sample clicks | nothing |
| `BITMAP.DLL` (§5) | `MINDSCAPELOGO` replaced by a text disclaimer screen; 215 other bitmaps: only unused colour-table entries | the logo screen differs | nothing (load as usual) |
| `GMTXT.DLL`, `GMTXT_ORIGINAL.DLL` (§6) | the two music-mode labels | options screen wording | load `GMTXT.DLL` |
| Music (§7) | MIDI files moved; MP3 recordings added | — | see the mapping table |
| Executables and system DLLs (§8) | compatibility wrappers, MP3 music player, ini-based paths | none on data | nothing; `GAMEF.DLL` rule tables are unchanged |

## 2. The corruption pattern

Every data difference outside §5's logo, §6 and §8 has the same shape. A single byte `0xFF` in the GOG file is
`0xDF` in the Steam file (3 224 cases in the bitmap colour tables, about 3 500 elsewhere); in a few cases it is `0xCF`
or `0xEF`. File sizes never change, nothing is inserted or deleted, and no other byte value is ever altered.

- Only a tiny fraction of `0xFF` bytes is affected: 3 525 of 14 078 350 `0xFF` bytes in the affected non-DLL files.
- The affected byte is almost always the first `0xFF` of its run, and the byte before it is nearly always `0x00`,
  `0x08` or `0x40`.
- The same pattern hits unrelated formats (sprite RLE data, 16-bit PCM, RGB palettes, RIFF SoundFont samples,
  float terrain records, DIB colour tables), so it is not a deliberate edit of content. It looks like damage done
  by a conversion or packaging step. 🟡 The cause is unknown and does not matter for a reader.

Files affected by this pattern (all others listed in the issue's "identical" groups are byte-identical):

| Files | Bytes changed | Where |
|---|---|---|
| 14 `.BOP` (`AMBWIZ`, `BLACKORC`, `DWHEEL`, `GIANT`, `GRTCWAG`, `GRTSWORD`, `MAP1`, `PACKMAST`, `PEASANT`, `ROCKLOB`, `SPELLS`, `TREEMAN`, `TROLL`, `WYVERN`) | 1–67 per file | zero-run lengths in type-4 frames (§3); `MAP1`: pixel bytes |
| `TESTSPR.PAL` | 76 | colour bytes of an unused leftover palette (FORMATS.md: no string refers to it) |
| `GLUE/WINDGAME.PAL`, `GLUE/WINDOPT.PAL`, `GLUE/GLUEREND.PAL` | 67, 31, 7 | only the pure-green `(0,255,0)` marker entries become `(0,223,0)` etc. These entries are the unused marker slots of `notes/fonts_glue.md`, and palette ids 7/8 and `GLUEREND` are unreachable (`notes/palette_selection.md` §6) |
| 29 `ANIM/*.SI` (all but `DEATH01`) | 954 in total | inside the WAV sound streams only (§4) |
| 399 `GLUE/SPEECH/*.WAV` | 2 267 in total (median 3, max 64 per file) | sample data only, never the header |
| `SOUND/WARINTR3.SBK` | 1 | inside the `smpl` sample data |
| `MESH/BF004/GRND.GD`, `MESH/BF008/GRND.GD` | 1 each | the anchor x (BF004) or z (BF008) of one triangle record goes from 510 to 446; that triangle's slope along that axis is 0 (BF004) or about 1e-12 (BF008), so the height it gives is unchanged (difference < 1e-5 world units) |
| `BITMAP.DLL` | 3 224 | colour-table entries only (§5) |

## 3. Sprites (`.BOP` type 4)

### 3.1 What changed

In each affected frame, one or more zero-run pairs `00 FF` became `00 DF` (or `00 CF`). The run is then 32 (or 48)
bytes shorter, every following byte of the frame lands 32 (48) packed bytes earlier, and the frame unpacks to fewer
than `ceil(w/2) × h` bytes. Frame records in the `.FOL` files are byte-identical to GOG.

All 26 affected frames (frame numbers are `.FOL` record indices; "short by" is in packed bytes):

| File | Frame(s) | Size | Short by | Decoded literally |
|---|---|---|---|---|
| `AMBWIZ` | 39 | 64×64 | 32 | shifted up one row from the run on (334 pixels differ) |
| `BLACKORC` | 83, 91 | 64×64 | 32 each | shifted up one row |
| `DWHEEL` | 4 | 128×128 | 64 (two runs) | shifted up one row |
| `GIANT` | 53, 65 | 128×128 | 32 each | **half-row shift: the lower part of the figure is cut and wrapped 64 pixels sideways** (7 000–8 700 pixels differ) |
| `GRTCWAG` | 2, 7 | 128×128 | 32 each | half-row shift |
| `GRTSWORD` | 79 | 64×64 | 32 | invisible (the run is the frame's trailing gap) |
| `PACKMAST` | 60 | 32×64 | 32 | shifted up two rows |
| `PEASANT` | 235 | 32×64 | 32 | shifted up two rows |
| `ROCKLOB` | 29 | 128×128 | 32 | half-row shift |
| `SPELLS` | 237, 293 | 64×64, 32×64 | 32 each | shifted up one / two rows |
| `SPELLS` | 230, 596, 597, 598 | 64×64, 128×128 | 32 … 960 | invisible (all damaged runs are in the trailing gap) |
| `TREEMAN` | 39, 55, 59, 81 | 128×128 | 32 each | half-row shift |
| `TROLL` | 41, 71, 84 | 64×128 | 48, 32, 32 | shifted up 1.5 / 1 / 1 rows |
| `WYVERN` | 30 | 128×128 | 32 | invisible (trailing gap) |

So 20 frames look broken if decoded literally, and 6 do not change at all once the missing tail is filled with
transparency. The damaged frames are spread over unit animations (dead, attack and stand groups) and a few spell
frames; there is no sign that the change was meant as an artwork fix.

🟡 How the Steam edition itself draws these 20 frames was not observed in a running game. Its executables carry
the same sprite code as GOG (§8), so it presumably shows them shifted the same way.

### 3.2 Why a repair is possible

The original encoder writes a gap longer than 255 bytes as several pairs, `00 FF 00 FF … 00 NN`
(`FORMATS.md`, "Compression (type 4)"), and it never writes two zero-run pairs in a row otherwise. Checked on all
14 558 type-4 frames of GOG's `FILE/BINARY` and `UPDATE/BINARY`: **a zero run shorter than 255 is never directly
followed by another zero run** (the end marker `00 00` does not count as a run). Every damaged run in the Steam
files breaks this rule, because the damaged byte was always one of those 255-runs that continue a long gap.

### 3.3 Decoder rule

1. Tokenise the segment as before: `XX` (≠ 0) = literal byte, `00 NN` = NN zero bytes, `00 00` = end.
2. **Repair:** a zero-run pair whose length is below 255 and which is *immediately followed by another zero-run
   pair* (not by `00 00`) counts as 255.
3. Unpack into the packed 4 bpp buffer. If the result is shorter than `ceil(w/2) × h`, fill the rest with zero bytes
   (transparent); if it is longer, ignore the excess. Never raise.

Results on the Steam edition: with step 2, all 7 279 type-4 frames of the 287 `FILE/BINARY` sets unpack
**byte-identical to GOG**, including all 26 damaged frames. The rule changes no frame that was already correct,
and it never fires on GOG data. Step 3 alone (padding without step 2) is enough for the 6 invisible cases, but
leaves the 20 shifted frames broken.

If an engine prefers to be faithful to the Steam files rather than to the artwork, it skips step 2. We recommend
the repair: the change is accidental damage, and the repaired frames match the other edition exactly.

### 3.4 Test vectors

All for a frame of width 64, height 16: `ceil(64/2) = 32` packed bytes per row, 512 bytes in total. "Non-zero
packed bytes" lists `(row, byte in row) = value`; all other packed bytes are 0. The packed byte `12` is a pixel of
colour nibble 1 followed by one of nibble 2.

| # | Segment bytes | Note | Unpacked length before padding (no repair / repair) | Non-zero packed bytes, no repair | Non-zero packed bytes, with repair |
|---|---|---|---|---|---|
| A | `00 FF 00 FF 00 01 12 00 00` | GOG-shaped | 512 / 512 | (15, 31) = `12` | (15, 31) = `12` |
| A1 | `00 DF 00 FF 00 01 12 00 00` | first run damaged | 480 / 512 | (14, 31) = `12` (row 15 empty) | (15, 31) = `12` |
| A2 | `00 FF 00 CF 00 01 12 00 00` | second run damaged (`CF`) | 464 / 512 | (14, 15) = `12` | (15, 31) = `12` |
| B | `12 00 FF 00 FF 00 01 00 00` | GOG-shaped, trailing gap | 512 / 512 | (0, 0) = `12` | (0, 0) = `12` |
| B1 | `12 00 DF 00 FF 00 01 00 00` | damaged trailing gap | 480 / 512 | (0, 0) = `12` (same image after padding) | (0, 0) = `12` |
| C | `00 DF 12 00 FF 00 21 00 00` | a genuine 223-run followed by a literal: must **not** be repaired | 512 / 512 | (6, 31) = `12` | (6, 31) = `12` |
| D | `12 34 00 10 00 00` | data ends early, no damage signature | 18 / 18 | (0, 0) = `12`, (0, 1) = `34`; rest padded transparent | same |

## 4. Films and speech

- **Films (`.SI`).** Container structure, chunk layout, object tree and every Smacker video stream are identical to
  GOG; the 29 changed films differ only inside their WAV sound streams (954 bytes in all; `DEATH01` is unchanged).
  The Omni and Smacker readers need no change.
- **Speech (`GLUE/SPEECH/*.WAV`).** The same 567 files exist. Format unchanged (564 files PCM 22 050 Hz mono
  16-bit, 3 files 11 025 Hz 8-bit), headers identical. In 399 files a few samples are damaged: in 16-bit PCM a
  high byte `FF` → `DF` turns a quiet sample such as −248 into −8 440 (a single-sample click at about −12 dBFS); a
  low byte `FF` → `DF` changes the sample by only 32. The WAV reader needs no change.
- 🟡 A player could remove the clicks (e.g. replace a lone sample that jumps by about 8 192 from both neighbours
  with their mean), but nothing requires it. Copying the GOG files is not an option for a Steam-only user.

## 5. `BITMAP.DLL`

- Same size, same 717 bitmap resources with the same names and dimensions.
- **`MINDSCAPELOGO`** (640×480): the Mindscape logo picture is replaced by a black screen with a few lines of
  white text, a disclaimer about the game's depiction of the Warhammer setting. It is shown wherever the logo
  picture is shown (palette id 4 path, `notes/palette_selection.md` §1). The engine loads it as usual and needs no
  change; it just shows the edition's own screen. (Its DIB header also has zero pixels-per-metre fields; ignore them.)
- **215 other bitmaps:** only colour-table entries change, all of them marker colours (pure green, magenta, white
  or one light cyan entry). Checked: **none of the changed entries is used by any pixel of its bitmap**, so no
  bitmap looks different. An engine that copies a whole colour table into the screen palette (the full-screen
  picture path) gets slightly different values in slots that the picture does not use.

## 6. `GMTXT.DLL` and `GMTXT_ORIGINAL.DLL`

All three files (GOG `GMTXT.DLL`, Steam `GMTXT.DLL`, Steam `GMTXT_ORIGINAL.DLL`) have the same 25 string blocks.
24 blocks are identical. The only difference is in the options-screen music labels, strings **36061** and
**36062** (the multi-state hotspot `linkid` 36060 of `notes/builtin_widgets.md`; 36060 "off" is unchanged):

| Music state (`s`, `notes/builtin_widgets.md`) | GOG `GMTXT.DLL` | Steam `GMTXT.DLL` and `GMTXT_ORIGINAL.DLL` |
|---|---|---|
| 0 (36060) | off | off (same) |
| 1 (36061) | FM MIDI on | "MIDI" on |
| 2 (36062) | General MIDI on | "CD" on |

The two Steam files differ from each other in a single letter's capitalisation in string 36062. Neither file
corresponds byte-for-byte to GOG's; both are the edition's relabelled options text. **The engine should load
`GMTXT.DLL`** (the file name the game uses on both editions) and ignore `GMTXT_ORIGINAL.DLL`. If the engine keeps
its own FM/General MIDI music modes on a Steam install, these two labels will not describe them; either use the
edition's MP3 tracks for those states (§7) or label the states from the engine's own table.

## 7. Music

The MIDI files are unchanged, but they moved and were split by family:

| GOG location | Steam location |
|---|---|
| `FILE/BINARY/MUSIC/<TRACK>.MID` (General MIDI, 21 files) | `FILE/BINARY/MUSIC/MIDI/GEN/<TRACK>.MID` |
| `FILE/BINARY/MUSIC/<TRACK>FM.MID` (FM, 19 files) | `FILE/BINARY/MUSIC/MIDI/<TRACK>FM.MID` |
| `FILE/BINARY/SOUND/WARINTR3.SBK` | same path (one damaged sample byte, §2) |

So a lookup that only falls back from `MUSIC/` to `MUSIC/MIDI/` finds the FM files but **not** the General MIDI
ones, which are one level deeper in `MUSIC/MIDI/GEN/`.

New: 42 MP3 files in `FILE/BINARY/MUSIC/` (44.1 kHz stereo, 128 kbit/s), two per General MIDI track name. Names
are the General MIDI track names, never the FM names (`GENERIC`, not `GENERIFM`):

- `<TRACK>.MP3`: a recording of that track's General MIDI arrangement. Its length is the `.MID` length of
  `notes/music.md` plus a 2–7 s release tail, and it follows the General MIDI length where GM and FM differ
  (`SCRIBE`, `TACTICAL`, `WIN`, `TITLE`).
- `<TRACK>CD.MP3`: the edition's "CD" version. For 7 tracks it is byte-identical to `<TRACK>.MP3`; for the other 14
  it is a different recording with a different length. 🟡 What it was made from is not known.
- 🟡 (from the labels and the file names; not observed in a running game) In the Steam edition, music state 1 ("MIDI", formerly FM MIDI) plays `<TRACK>.MP3` and state 2 ("CD", formerly
  General MIDI) plays `<TRACK>CD.MP3`, where `<TRACK>` is the General MIDI name the game asks for.

| Track (`.MID` name) | FM file | `<TRACK>.MP3` s | `<TRACK>CD.MP3` s | CD same as plain? | GM `.MID` length s |
|---|---|---|---|---|---|
| `BATTLE` | `BATTLEFM` | 226 | 271 | no | 219.4 |
| `COMBAT` | `COMBATFM` | 222 | 232 | no | 216.0 |
| `DEAD` | `DEADFM` | 29 | 29 | yes | 24.0 |
| `DWARF` | `DWARFFM` | 158 | 173 | no | 153.6 |
| `FOREST` | `FORESTFM` | 124 | 140 | no | 122.2 |
| `GENERIC` | `GENERIFM` | 83 | 83 | yes | 78.5 |
| `IMPERIAL` | `IMPERIFM` | 146 | 146 | yes | 141.5 |
| `INTRO3` | `INTRO3FM` | 91 | 91 | yes | 86.2 |
| `LOOKIN2` | `LOOKINFM` | 184 | 184 | yes | 182.4 |
| `LOOKING` | `LOOKINFM` | 185 | 185 | yes | 182.4 |
| `LOSE` | `LOSEFM` | 149 | 145 | no | 144.0 |
| `ORC` | `ORCFM` | 137 | 137 | yes | 132.5 |
| `SCRIBE` | `SCRIBEFM` | 169 | 166 | no | 164.2 |
| `SIGHTED` | `SIGHTEFM` | 245 | 239 | no | 242.4 |
| `SKAVEN` | `SKAVENFM` | 146 | 151 | no | 143.6 |
| `TACTICAL` | `TACTICFM` | 140 | 140 | no | 134.4 |
| `TENSE` | `TENSEFM` | 138 | 140 | no | 134.4 |
| `TITLE` | `TITLEFM` | 281 | 241 | no | 279.2 |
| `VICTORY` | none | 77 | 108 | no | 72.0 |
| `WIN` | `WINFM` | 145 | 108 | no | 143.4 |
| `WINTIT` | `WINTITFM` | 92 | 167 | no | 90.0 |

The set is the same 21 tracks as the General MIDI files; there are no extra tracks. Cutscene music inside the
`.SI` films (`RIFF MIDS`, `notes/si_omni.md`) is unchanged and has no MP3 counterpart. 🟡 Whether the edition's
film playback swaps in MP3 for that embedded music was not checked.

## 8. Executables and system DLLs

None of these is read by the engine except `GAMEF.DLL` (rule tables) and `WHSHR.EXE` (name tables); for those two
the data the engine reads is unchanged.

- `WHSHR.EXE`: same size; the only change is that it imports a compatibility wrapper DLL (`RTFIX.dll`, new) in
  place of a Windows graphics library. Name tables unchanged.
- `GAMEF.DLL`: same size, one byte differs. It changes the folder from which the march file `MARCH.MRC` is read,
  and only when the developer command-line switch `xxx` is given. No effect on normal play, and **all rule tables
  are unchanged**, so `whshr rules` reads the same values from either edition.
- `MINDSYS.DLL` (replaced): takes its settings from a `warhammer.ini` next to the game instead of the registry, and
  resolves the game-data and save folders (`FILE`, `SAVE`) itself.
- `MIDI.DLL` (replaced): an MP3 music player (it ships with a `LICENSE/` folder for its audio library), with the
  name mapping of §7.
- `WING32.dll`, `RLCORE.dll`, `RL/*`, `RLDDF.DLL`: replaced or patched graphics/compatibility libraries.
- `SAVE/ARMY.MRC`, `SAVE/PLAY.MRC`: identical to GOG; `SAVE/steam_autocloud.vdf` is Steam's cloud-save marker.
- `DOCS/` holds the manual (PDF) and the Windows help file; `SCRIPT/*.DLL`, `WND.DLL`, the string DLLs other than
  `GMTXT.DLL`, all `.BTS`/`.MRC`, `.PBX`, `.FON`, `.SFX` and sound-effect WAVs are byte-identical to GOG.

## 9. Open items

- 🟡 How the running Steam game draws the 20 shifted frames (§3.1). It only matters for a "faithful to Steam" mode.
- 🟡 Origin of the `<TRACK>CD.MP3` recordings, and whether film music is also replaced by MP3 (§7).
- 🟡 Click removal in speech and film audio (§4) is optional and not specified.
