# Cutscene side files `.SN/.SM/.SR` and speech (ROADMAP 3.3 + 3.4)

Report on `REMOTE/BINARY/ANIM/*.SN`, `*.SM`, `*.SR` (30 scenes × 3 files) and the link between
cutscenes, the `GLUE/SPEECH/*.WAV` recordings and the texts in `ANTXT.DLL`. Black-box analysis
(bytes + cross-checks), no disassembly. The `.SI` containers were not extracted: only the
4-byte tag and fixed header fields at offsets given by `.SM` were read, to verify `.SM`.

## Status

| Item | Status |
|---|---|
| `.SN` (object name table) | ✅ Fully decoded, every byte accounted for in 30/30 files |
| `.SM` (SI index: object, time, offset) | ✅ Fully decoded, 25,696 records match the `.SI` headers exactly (tag, object id, time) |
| `.SR` (SI build/interleave list) | ✅ Structure fully decoded (30/30 files, all bytes); 🟡 in 3 scenes SR lists 1–2 more data chunks than ended up in `.SI` |
| Object kinds (video / sound / music / speech / subtitle / fade / animdone) | ✅ from names, paths and SI object type, consistent in all scenes |
| Scene ↔ campaign glue script (`playmovie:A9`) | ✅ 27/30 scenes in `WND.DLL` glue scripts; `A1` (`binary\anim\a1`, hypothesis: intro) and `DEATH01/02` referenced from `WHSHR.EXE` |
| Speech `A*.WAV` ↔ scene ↔ text | ✅ 63 of 64 numbered `A*.WAV` are used by a scene; number == string id in `ANTXT.DLL` (64/64) |
| Speech `B*.WAV` ↔ text | 🟡 489/502 numbered `B*.WAV` have a string with the same id in `BRTXT.DLL` (battle/glue lines, not cutscenes) |
| Contents of `.evt` chunks (subtitle timing?), MxCh flag semantics beyond split/end | ❌ Not examined (inside `.SI`, another task) |

## Format description (ready to paste into FORMATS.md)

### Cutscenes — `REMOTE/BINARY/ANIM/`

30 scenes: `A1`–`A27` (without `A19`, `A21`; with `A12B`, `A16A`, `A16B`, `A18B`) and `DEATH01`,
`DEATH02`. Each scene is four files with the same name:

| File | Content |
|---|---|
| `.SI` | Mindscape Omni container `RIFF MxSt` (objects `MxOb`, chunks `MxCh`, 64 KB blocks) |
| `.SN` | object name table (id → name) |
| `.SM` | index of the `.SI` file: where each object header and each chunk is, and at what time |
| `.SR` | list written by the SI build tool: source files and the order their chunks were interleaved |

`WHSHR.EXE` opens scenes by name (`binary\anim\a1` + `.si`) and has no reference to `.sr/.sm/.sn`,
but the Omni runtime `OMNI000R.DLL` (in the game directory) contains the strings `.sm`, `.sn`, `.sr`
next to `MxStreamer`, `MxStreamer::GoTo(const char*)`, `MxStreamChunk` (string order:
`MxDSfile, MxDSMarker, MxDSRequest, MxDSMapRequestToMarker, .sr, MxDSProvider, .si, .sm, MxStreamer, .sn`). **Hypothesis:** the Omni
streamer loads them next to the `.SI`: `.SM` as a seek index (object/time → offset), `.SN` to look up
objects by name, `.SR` maybe for debugging/rebuilding. Either way they give a complete description
of a scene without parsing `.SI`.
All integers are little-endian.

#### `.SN` — object names

```c
struct SN {
    uint32_t count;                 // number of objects
    struct {
        uint32_t id;                // 0..count-1, in order; == SI object id
        uint32_t len;               // name length including the NUL
        char     name[len];         // "A9_Stream", "Scene9AnimA9", "Fanfare01_A9_WAV", ...
    } obj[count];
};
```

Object 0 is always the root `<Scene>_Stream` (no file of its own). Names end in a kind suffix:
`_WAV`, `_EVT`, `_MID`, `_SPK` (speech, e.g. `Thanquol1_A2_WAV_SPK`, `A13010_A13_SPK`).
A few names were copied from another scene and not renamed (`A14` has root `A13_Stream`,
`A20` has `A16b_Stream`, `DEATH02` has `Death_01_Stream`, `A3` has `A3010_A2_EVT`), so the name
is not a reliable scene key; the file name is.

#### `.SM` — index of `.SI`

```c
struct SM {
    uint32_t count;
    struct {                        // 12 bytes
        uint32_t object_id;         // id from .SN
        int32_t  time;              // -2 = object header (MxOb), -1 = header/format chunk, >=0 = time in ms
        uint32_t si_offset;         // offset of "MxOb"/"MxCh" in the .SI file
    } rec[count];                   // sorted by si_offset
};
```

- File size = `4 + 12 × count` in 30/30 files.
- `time == -2`: exactly one record per `.SN` object; `.SI` contains `MxOb` at the offset,
  with the same name (at `offset+16`) and the same id right after the name.
- Otherwise `.SI` contains `MxCh` at the offset, with `u16 flags, u32 object_id, i32 time, u32 length`
  after the size field, where object_id and time equal the `.SM` record (25,696/25,696).
- Observed chunk flags: `0x10` = chunk split at a 64 KB `.SI` block boundary (the continuation
  starts exactly at a multiple of `0x10000` and repeats id and time), `0x02` = end of object's data
  (one per file, plus one for object 0 = end of the whole scene; its time is the scene length).
- Time step: all video and subtitle chunks are 125 ms apart → **video runs at 8 fps**
  (e.g. A9: 120 frames, 0…14,875 ms).

#### `.SR` — build/interleave list

```c
struct SR {
    uint32_t count;
    struct {
        char     path[];            // "scene09\a9.smk", "music\imperifm.mid", "musicawe\imperial.mid"
                                    // NUL-terminated, zero-padded to a multiple of 4 bytes
        uint32_t file;              // source file index 0..n-1
        int32_t  seq;               // -2 declaration, -1 header chunk, -3 end, >=0 number of the data chunk
        uint32_t a;                 // seq == -2: SI object id (from .SN); otherwise 0xdddddddd
        uint32_t b;                 // seq == -2: 0xfffffffe;              otherwise 0xdddddddd
    } rec[count];
};
```

- `0xdddddddd` is the MSVC debug heap "dead land" fill, so these fields were simply never written.
- The file starts with the declarations of all source files (`seq = -2`, in order `file = 0..n-1`),
  giving `file index → path → SI object id`. Objects without a file (`_Stream`, the MIDI group
  `Music_*_MID`) are not declared.
- Then come records in the order their data was written to `.SI`: for each file exactly one `-1`
  (always its first record), data `0, 1, 2…` without gaps, and exactly one `-3`.
- The order of these records is the same as the `MxCh` order in `.SM` (after dropping the `0x10`
  continuations at block boundaries, and object 0) in 27/30 scenes. In `A18`, `A18B` (`.smk`: SR 340/239,
  SI 338/237) and `A25` (`.smk` 350 vs 349; `musicawe\win.mid` 1 data chunk vs 0) SR lists
  chunks that are missing from `.SI`. Hypothesis: the tool dropped empty chunks.
- So `.SR` maps an `.SI` object to the **original file name** (`scene09\a9.smk`, `Hrswlk01.wav`),
  which `.SN` does not contain.

#### Scene contents (all 30 scenes)

| Kind | Recognised by | SI type (`u16` at `MxOb+8`) | Count |
|---|---|---|---|
| root stream | `<Scene>_Stream`, no file | 7 | 30 |
| video | `.smk` (Smacker), `Scene<N>AnimA<N>` | 3 | 30 (one per scene) |
| sound effect | `.wav` in `scene<N>\` | 4 | 288 |
| speech | `.wav` named `aNNNNN`/`bNNNN`, or name with `_SPK` | 4 | 67 |
| music | group `Music_<S>_MID` (type 9, no file) containing `music\*fm.mid` (FM synth) and `musicawe\*.mid` (AWE32) | 4 | 27 groups, 27 FM + 29 AWE |
| subtitle event | `.evt` named like the speech line (`a9010.evt`, `e1010.evt`) | 8 | 67 |
| `fade.evt`, `animdone.evt` | fixed names in every scene | 8 | 30 + 30 |

- **Hypothesis (strong):** `aNNNNN.evt` are subtitle events. Every speech WAV has a matching `.evt`
  object starting at the same ms, and its chunks run every 125 ms for ~2 s longer than the speech.
  `WHSHR.EXE` has `[ATGEventCallback] Subtitle DONE(%d)(%d)(%#x)(%s)`, `ATGMovieSubTitle`,
  `[ATGEventCallback] FADE` and `Stream DONE`, and the glue scripts call `loadanimstringintocache:<id>`
  (text id) before `playmovie`. A9 and DEATH01/02 have only `.evt` (text without voice).
- The `MIDIType`/`MIDI1`/`MIDI2` strings in `.SI` and in `WHSHR.EXE` suggest the game picks FM or AWE32
  music from the group depending on the sound card.

### Speech and texts

- **Numbering:** `A<scene><line>` where line has 3 digits: `A1010`…`A1050` = scene 1 lines 010–050,
  `A13031` = continuation of line 030. **The number equals the string id in `FILE/DLL/ANTXT.DLL`**
  (`1010 'Wizard: Prepare to die, sewer fiend!'`), including the speaker name before the colon.
- `ANTXT` ids `N100…N103` (e.g. `1100–1102`, `16600–16601`, `27100–27103`) have no recordings:
  these are narrator captions for scene group N ("Meanwhile in Skavenblight…").
  `30000`, `31000`, `31010` are the texts of the `DEATH01/02` events ("You were killed in battle.").
- The speech numbering follows the **text** numbering, not the file name: `A18`/`A18B` contain lines
  `A19010`, `A19020`, and `A20` contains `A21010`, `A21020` (there are no scenes A19/A21).
  `A23` reuses the battle line `b9592.wav` (`Merc1_A23_WAV_SPK`).
- `A*.WAV` in `GLUE/SPEECH` (64 numbered + `A_NO1`): 63 are used by some `.SI`. Not used: `A9010`
  (A9 only has the subtitle event), `A25020` (text "Dwarf 2: We've done what had to be done…" exists,
  but `A25` has no such object) and `A_NO1`.
- `A3` `Waaargh.wav` (`UrgatWaagh1_A3_WAV_SPK`) is speech with no counterpart in `SPEECH`.
- Duration: speech WAV in `SPEECH` minus the chunk time span of the same object in `.SI` = +0.05…+5.8 s
  (so the SI chunks cover the recording, but the sizes of the chunk data differ from the `SPEECH` WAV data;
  the embedded copy is probably encoded differently, not checked).
- `B*.WAV` (502): `binary\glue\speech\b%s.wav` in `WHSHR.EXE`. 489 have a string with the same id in
  `BRTXT.DLL` (e.g. `B1010` = "Dietrich: My Lord, we have been approached…", `B9500` = "Fire!").
  Not matched: `B1`, `B3`, `B4`, `B9`, `B12034`, `B4324`, `B4324A`, `B5910`, `BMISC1–4`, `FART`
  (letter suffixes such as `B1070A` count as matched by number). These are battle and campaign
  lines, not cutscene lines.
- Portraits: the scenes are full Smacker videos, so there is no `leaderportrait` link inside them.
  The speaker is known only from the text prefix (`Thanquol:`, `Urgat:`, `Carlsson:`, `Ceridan:`,
  `Dargrimm:`, `Ungrunn:`, `Galed:`, `Emperor:`…). Linking B lines to portraits is not done yet.

### Place of scenes in the campaign

From `extracted/pe_resources/WND/rcdata/*.txt` (glue scripts, output of `scripts/pe_extract.py`):
`loadanimstringintocache:<text id>` … `playmovie:<scene>` (also `iftrueplaymovie`/`iffalseplaymovie`
after `setgluestatusmask`/`testobjective`, i.e. alternative endings):

- `A2` BPMISSION1 (and FLOWSCRIPTECTS demo), `A3` BPMISSION3, `A4`+`A5` BPMISSION5, `A6` BPMISSION9,
  `A7` BPMISSION13/14/15, `A8` BPMISSION14/15, REMISSION6/7/8, `A9` BPMISSION15B, REMISSION6, WEMISSION145;
- `A10` ZHUFBARMISSION, `A11` ZHUFBARMISSION3, `A12`/`A12b` BPMISSION15B (`iffalse`/`iftrue`),
  `A13` SZMISSION2, `A14`+`A15`+`A16a` SZMISSION5, `A16b` EN4_SUBSCRIPT0, `A17` ENMISSION4;
- `A18`/`A18B` GMMISSION3 (`iftrue`/`iffalse`), `A20` LMISSION3, `A22`+`A24` LASTMISSION,
  `A23` LM_SUBSCRIPT1, endings `A25` (mask 8000), `A26` (4000), `A27` (2000 + `testobjective:Z`) LASTMISSION;
- `A1`: `binary\anim\a1` in `WHSHR.EXE` (intro); `death01`/`death02` in `WHSHR.EXE` (defeat / fleeing).

## Summary table

`Length` = time of the end chunk of object 0. Objects = video/sound/music (FM+AWE)/speech/subtitle/other events.

| Scene | SN/SM/SR records | Length | Video frames | Objects | Speech (GLUE/SPEECH) | Glue scripts |
|---|---|---|---|---|---|---|
| A1 | 63/1627/1502 | 96.5 s | 722 | 1/46/2/5/5/2 | A1010 (2.6s), A1020 (4.9s), A1030 (6.3s), A1040 (7.4s), A1050 (10.1s) | - (intro) |
| A2 | 21/1002/905 | 56.4 s | 400 | 1/12/2/1/1/2 | A2010 (27.8s) | BPMISSION1, FLOWSCRIPTECTS |
| A3 | 17/793/741 | 43.9 s | 300 | 1/7/2/2/1/2 | A3010 (28.8s), Waaargh.wav (not in SPEECH) | BPMISSION3 |
| A4 | 16/1151/1062 | 58.9 s | 420 | 1/5/2/2/2/2 | A4010 (11.1s), A4020 (33.6s) | BPMISSION5 |
| A5 | 17/704/643 | 43.9 s | 300 | 1/8/2/1/1/2 | A5010 (16.8s) | BPMISSION5 |
| A6 | 39/1332/1295 | 66.4 s | 482 | 1/16/2/8/8/2 | A6010 (18.5s), A6020 (9.5s), A6030 (2.1s), A6040 (8.0s), A6050 (1.2s), A6060 (11.0s), A6070 (2.2s), A6080 (3.2s) | BPMISSION9 |
| A7 | 46/1126/1092 | 56.0 s | 398 | 1/29/2/5/5/2 | A7010 (4.6s), A7020 (4.8s), A7030 (7.0s), A7040 (10.3s), A7050 (4.2s) | BPMISSION13, BPMISSION14, BPMISSION15 |
| A8 | 17/549/509 | 28.8 s | 180 | 1/8/2/1/1/2 | A8010 (18.8s) | BPMISSION14, BPMISSION15, REMISSION6, REMISSION7, REMISSION8 |
| A9 | 11/328/319 | 18.8 s | 120 | 1/3/2/0/1/2 | - (text 9010 only) | BPMISSION15B, REMISSION6, WEMISSION145 |
| A10 | 11/679/628 | 36.2 s | 240 | 1/2/2/1/1/2 | A10010 (26.1s) | ZHUFBARMISSION |
| A11 | 11/236/231 | 14.5 s | 67 | 1/5/0/1/1/2 | A11010 (5.1s) | ZHUFBARMISSION3 |
| A12 | 9/706/682 | 41.2 s | 286 | 1/0/2/1/1/2 | A12010 (33.9s) | BPMISSION15B |
| A12B | 9/618/597 | 36.2 s | 246 | 1/0/2/1/1/2 | A12510 (28.6s) | BPMISSION15B |
| A13 | 29/2986/2894 | 162.2 s | 1249 | 1/1/2/11/10/2 | A13010 (6.7s), A13020 (6.4s), A13030 (34.3s), A13031 (8.3s), A13040 (2.8s), A13050 (28.9s), A13060 (2.1s), A13070 (15.7s), A13080 (3.2s), A13090 (25.1s), A13100 (15.3s) | SZMISSION2 |
| A14 | 10/1102/1065 | 64.4 s | 466 | 1/0/2/2/1/2 | A14010 (35.5s), A14011 (20.6s) | SZMISSION5 |
| A15 | 16/660/643 | 36.9 s | 246 | 1/3/2/3/3/2 | A15010 (0.7s), A15020 (18.1s), A15030 (3.5s) | SZMISSION5 |
| A16A | 26/1648/1519 | 81.1 s | 600 | 1/13/2/3/3/2 | A16010 (9.6s), A16020 (33.5s), A16030 (21.4s) | SZMISSION5 |
| A16B | 11/748/688 | 38.6 s | 260 | 1/2/2/1/1/2 | A16510 (29.4s) | EN4_SUBSCRIPT0 |
| A17 | 9/218/200 | 18.8 s | 100 | 1/2/2/0/0/2 | - (caption 17100 only) | ENMISSION4 |
| A18 | 48/886/848 | 48.6 s | 338 | 1/33/2/4/4/2 | A18010 (3.3s), A18020 (5.5s), A19010 (6.5s), A19020 (3.4s) | GMMISSION3 |
| A18B | 32/636/605 | 36.1 s | 237 | 1/19/2/3/3/2 | A18010 (3.3s), A19010 (6.5s), A19020 (3.4s) | GMMISSION3 |
| A20 | 25/1061/1007 | 59.1 s | 425 | 1/12/2/3/3/2 | A20010 (1.5s), A21010 (6.4s), A21020 (25.5s) | LMISSION3 |
| A22 | 11/641/618 | 35.9 s | 230 | 1/2/2/1/1/2 | A22010 (25.9s) | LASTMISSION |
| A23 | 21/305/281 | 19.9 s | 110 | 1/11/2/2/1/2 | A23010 (2.0s), B9592 (0.7s) | LM_SUBSCRIPT1 |
| A24 | 18/1673/1612 | 90.2 s | 673 | 1/5/2/3/3/2 | A24010 (52.4s), A24020 (1.1s), A24030 (22.5s) | LASTMISSION |
| A25 | 14/748/711 | 49.9 s | 349 | 1/5/2/1/1/2 | A25010 (17.5s) | LASTMISSION |
| A26 | 14/494/480 | 36.0 s | 239 | 1/5/2/1/1/2 | A26010 (7.3s) | LASTMISSION |
| A27 | 29/487/444 | 35.1 s | 232 | 1/22/2/0/0/2 | - (captions 27100–27103) | LASTMISSION |
| DEATH01 | 12/274/266 | 16.2 s | 80 | 1/6/1/0/1/2 | - (text 30000) | WHSHR.EXE `death01` |
| DEATH02 | 13/278/270 | 16.2 s | 80 | 1/6/1/0/2/2 | - (texts 31000, 31010) | WHSHR.EXE `death02` |

## How it was verified

- `scene_dump.py --check` on all 30 scenes: 0 errors.
  - `.SN/.SM/.SR` parsed to the last byte; `.SR` padding is always zero; ids `0..n-1`.
  - `.SR`: declaration `b == 0xfffffffe` and `a < count(.SN)`; all other records have `a == b == 0xdddddddd`;
    for each file one `-1` (first), one `-3`, data `0..n-1`; the path is the same in every record of a file.
  - `.SM`: sorted by offset; one `-2` per `.SN` object; `.SI` headers at each offset agree with id/name/time
    (25,696 records).
  - Per object: number of SR data records == number of SI data chunks, except the 4 cases listed above (notes).
- Order of SR records == order of chunks in `.SM` in 27/30 scenes (scratch analysis, `difflib`).
- Frame rate: every consecutive time difference for video (10,080) and subtitle chunks (8,133) is 125 ms.
- Speech: `wave` on all 567 files (564 × 22,050 Hz 16-bit mono, 3 × 11,025 Hz 8-bit), paths from `.SR`
  compared with the file names; texts compared with `extracted/pe_resources/ANTXT/strings.json`
  (e.g. A18: `A18010` "Galed: You are surrounded!…" at 9,875 ms; `A19020` "Galed: We will escort you…").
- Glue scripts: grep of `playmovie`/`loadanimstringintocache` in `extracted/pe_resources/WND/rcdata`.
  The text ids loaded before each `playmovie` are the speech/subtitle ids of that scene, with three
  exceptions: `A20` loads only `20010` (the scene also has `21010`, `21020`), `A25` loads `25020`
  (not in the scene), and the shared `A18`/`A18B` block loads `18020` (only in `A18`).

## Scripts

`scripts/scene_dump.py` (Python 3 stdlib; texts and glue links read files from `scripts/pe_extract.py`
if they exist in `extracted/pe_resources/`):

```
python3 scripts/scene_dump.py ".../WARFB" A9                      # structure of one scene
python3 scripts/scene_dump.py ".../WARFB" A18 --json              # JSON on stdout
python3 scripts/scene_dump.py ".../WARFB" --json-all extracted/scene_scripts
python3 scripts/scene_dump.py ".../WARFB" --check                 # verification of all scenes
python3 scripts/scene_dump.py ".../WARFB" --table                 # the summary table above
```

API: `read_sn/read_sm/read_sr(path)`, `load_scene(warfb, name)` (objects with kind, path, SI offset/type,
first/last data chunk time, end time, speech file + duration, text), `check_scene`.

Output: `extracted/scene_scripts/<SCENE>.json` (30 files; game data, not for distribution).

## Open questions
> **Tracked on GitHub**: these open items are tracked as issue #42 (`topic:cutscenes`). Kept here for
> reference; a follow-up pass (issue #45) will verify nothing was lost in the move.


- Contents of `.evt` chunks (20/24/4/8 B): subtitle trigger / text id? To be checked by whoever extracts `.SI`.
- Meaning of the `u16` SI type values (3/4/7/8/9) and of the remaining `MxOb` header fields: `.SI` task (ROADMAP 3.1).
- Why `.SR` in A18/A18B/A25 lists chunks missing from `.SI` (empty frames? build tool limit?).
- Whether the embedded speech WAVs are identical to `GLUE/SPEECH` (the sizes differ; different sample rate/format?).
- `A25020` and `A9010.WAV` have recordings but no voice object in any scene. Unused, or played by the glue
  outside the movie?
- Linking `B*.WAV` lines to portraits (`leaderportrait`, portrait sprites) and to missions (the 13 unmatched
  B files).
- How `OMNI000R.DLL` uses `.SN/.SM/.SR` (the extensions are in its strings; details need disassembly
  or a Wine file-access trace, e.g. `WINEDEBUG=+file`).

## Proposed ROADMAP.md changes

- Table row "Cutscenes": `.SR/.SM/.SN` ✅ (side files decoded: names, SI index, source list); `.SI` remains ⬜/🟡.
- 3.3 → 🟡: "`.SN/.SM/.SR` decoded (`scripts/scene_dump.py`, `notes/scene_scripts.md`); scene = 1 Smacker
  video at 8 fps + sounds + FM/AWE music + speech with subtitle events; order and timing known from `.SM`.
  Remaining: `.evt` contents and playback (depends on 3.1)."
- 3.4 → 🟡: "`A*.WAV` = cutscene lines, number == `ANTXT.DLL` string id (63/64 placed in scenes with timing);
  `B*.WAV` = battle/glue lines, number == `BRTXT.DLL` string id (489/502). Remaining: speaker → portrait, B lines → missions."
- New item under Phase 1 or 4.2: the glue scripts (`WND.DLL` rcdata) define when scenes play
  (`playmovie`, `iftrueplaymovie` + `setgluestatusmask`), which is useful for the campaign flow (M6).
