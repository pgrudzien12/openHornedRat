# `.SI` — Mindscape Omni stream containers (cutscenes) — ROADMAP 3.1 + 3.2

Files: `REMOTE/BINARY/ANIM/*.SI`: 30 files, 133 MB (`A1`…`A27`, `A12B`, `A16A/B`, `A18B`,
`DEATH01/02`). Scripts: `scripts/si_omni.py` (container + extraction), `scripts/si_smacker.py`
(pure-Python Smacker video decoder, used because ffmpeg/ffprobe are not installed).
Output: `extracted/si/<SI>/` (122 MB, not for distribution) with `extracted/si/INDEX.md`.

## Status

| Item | Status |
|---|---|
| RIFF/chunk structure (`MxSt`, `MxHd`, `MxOb`, `MxDa`, `MxCh`, `pad `) | ✅ all 30 files, every byte accounted for, no unknown chunk types |
| Object tree `MxOb` (types, names, times, source files, media fields) | ✅ layout / 🟡 meaning of a few constant fields |
| Chunk reassembly (split chunks, header chunk, end-of-stream) | ✅ all 25 071 chunks, 1 241 split chunks (2 493 pieces) |
| Smacker films `.smk` | ✅ rebuilt byte-consistent (header tables = data), frames decoded and viewed |
| Sounds `.wav` (355 objects) | ✅ valid PCM WAV; 43/67 speech lines sample-identical to `GLUE/SPEECH` |
| MIDI music (`RIFF MIDS` → `.mid`) | ✅ converted; 10/17 unique tracks event-identical to `FILE/BINARY/MUSIC/*.MID` |
| Event tracks `EVT` (127) | 🟡 structure ✅, meaning of the fields partly a hypothesis |

## Format description (ready to paste into FORMATS.md)

The Omni engine (`OMNI000R.DLL`) is the same family as LEGO Island (1997), but this is an
**older version, 1.0** (LEGO Island is 2.2): no `MxOf` offset table, no 3D vectors in objects,
different top-level nesting. All integers are little-endian. Chunks follow RIFF rules
(size excludes the 8-byte header, odd sizes are padded by 1 byte relative to the chunk start).

### Chunk tree

```
RIFF 'MxSt'                          size = file size - 8
  LIST 'MxSt'
    MxHd  (8 B)                      u32 version = 0x00010000 (1.0), u32 = 0x100 (unknown; the same in all 30)
    MxSt
      MxOb                           root object (ParallelAction), children nested inside it
      LIST 'MxDa'                    data: MxCh chunks and 'pad ' chunks, in 64 KB buffers
    pad                              fills the file up to a multiple of 64 KB (all 30 files are)
```

**64 KB buffers.** The data list is written in buffers of 0x10000 B. A chunk that does not fit
is split (see `MxCh` flag `0x10`), and the rest of a buffer is filled with a `pad ` chunk.
If fewer than 8 bytes remain (no room for a chunk header), the writer leaves **garbage bytes**
(old buffer contents) and continues at the next 64 KB boundary. That happens 3 times in the
30 files (A13: 4 B, A18: 2 B, A25: 1 pad byte + 4 B). A reader must skip to the next buffer
when it sees an unknown FourCC less than 8 bytes before a boundary.

### `MxOb` — object

```c
struct MxOb {                       // chunk payload
    uint16 type;                    // 3 Anim, 4 Sound, 7 ParallelAction, 8 Event, 9 SelectAction
    cstr   source_name;             // always "" (LEGO: presenter/source name)
    uint32 unk14;                   // 0; 1 for all Event objects and one Sound (Drip_A24_WAV)
    cstr   extra;                   // always "" (one byte more than LEGO 2.2; parsed as empty string)
    cstr   name;                    // "Scene11AnimA11", "Cannon01_A11_WAV", "A11010_A11_SPK"...
    uint32 id;                      // 0..n-1, dense; MxCh.object_id refers to it
    uint32 flags;                   // 2 for almost all; 0 SelectAction; 1 for looping music
    int32  start_ms;                // start time relative to the parent
    int32  duration_ms;
    uint32 loops;                   // 1; 5 for the looping films A9/A17; 0 = forever (music)
    // --- containers (type 7 ParallelAction, 9 SelectAction):
    LIST 'MxCh' {
        [type 9 only: cstr variable ("MIDIType"); u32 n; n x cstr choices ("MIDI1","MIDI2")]
        [otherwise:   u32 n]
        n x chunk 'MxOb' (child)    // padded like RIFF chunks
    }
    // --- leaves (types 3, 4, 8):
    cstr   file;                    // original source path: "scene11\a11.smk", "music\intro3fm.mid"
    uint32 leaf_index;              // 0,1,2... running index of leaf objects in the file
    uint32 unk_a;                   // always 0
    uint32 unk_b;                   // always 0
    uint32 fps;                     // 8 for SMK and EVT (= 125 ms ticks), 1 for WAV/MID
    char   format[4];               // " SMK", " WAV", " MID", " EVT"
    uint32 palette_mgmt;            // always 1 (LEGO: paletteManagement)
    int32  sustain;                 // -1 for SMK (hold the last frame?), 0 otherwise
    // type 4 (Sound) only:
    uint32 volume;                  // 5..100
};
```

The `SelectAction` layout is exactly the one read by `MxDSSelectAction::Deserialize` in the
LEGO Island decompilation (variable name, count, choice strings, then one child per choice);
the engine picks the child whose choice equals the variable's value. Here every film has one:
`Music_<scene>_MID` selects on `MIDIType` between `MIDI1` = `music\xxxfm.mid` (FM synth
arrangement) and `MIDI2` = `musicawe\xxx.mid` (General MIDI/AWE32 arrangement).

Type numbers 3/4/7/8/9 were named by what they contain; the SelectAction layout is confirmed
against the decompilation, the other names follow LEGO Island's naming.

### `MxCh` — data chunk

```c
struct MxCh {                       // chunk payload
    uint16 flags;                   // 0x02 end of stream, 0x10 split piece
    uint32 object_id;               // MxOb.id
    int32  time_ms;                 // -1 = stream header chunk; otherwise presentation time
    uint32 length;                  // data length (for the first split piece: length of the whole chunk)
    uint8  data[];                  // chunk size - 14
};
```

Every leaf stream is: **one header chunk** (`time = -1`, may be empty), then data chunks in time
order, then **one end-of-stream chunk** (`flags = 2`, no data, `time` = end time). The root
ParallelAction only has an end-of-stream chunk (at the length of the whole scene); the
SelectAction has no chunks at all. Streams are interleaved by time.

**Split chunks:** a chunk that crosses a 64 KB boundary is written as 2–3 pieces with flag `0x10`.
The first piece's `length` is the length of the whole chunk (larger than its data); the
following pieces have `length` = their own data length. Join pieces with the same `object_id`
until the total is reached. Verified on all 1 241 split chunks (2 493 pieces).

### Stream contents by format

| Format | Objects | Header chunk | Data chunks | Rebuilt file |
|---|---|---|---|---|
| ` SMK` (Anim) | 30 | Smacker header (104 B) + frame size table + frame type table + Huffman trees (= `104 + 5·n + TreesSize`, checked) | one chunk = one Smacker frame, every 125 ms | header + frames = valid `.smk` |
| ` WAV` (Sound) | 355 | 24 B: `WAVEFORMAT` (16 B, PCM) + u32 data size of the original file + u32 `44` (hypothesis: original header size) | raw PCM, 1 s per chunk (`time` step 1000) | `RIFF WAVE` with that `fmt ` |
| ` MID` (Sound) | 56 | empty (0 B) | one chunk: a complete `RIFF 'MIDS'` file | `.mids` as is + converted `.mid` (SMF format 0) |
| ` EVT` (Event) | 127 | 12 B: u32 record count, u32 fields per record, u32 fps (8) | one record (`fields` × u32) per 125 ms tick | `.evt.json` |

**Smacker.** All 30 films are `SMK2`, **640×272**, no audio tracks (sound is carried by the
separate WAV objects), no Y-interlace/doubling. The frame-rate field varies (7.81, 8, 10,
11.76 fps) but the Omni chunks are always 125 ms apart and `MxOb.fps` = 8, so **the engine
plays every film at 8 fps** regardless of the Smacker header. Films with `loops = 5` (A9: 24
frames, A17: 20 frames, both with a ring frame) store the frames **again for every loop**:
`f0…f(n−1)`, then `(ring, f1…f(n−1))` × (loops − 1); `si_omni.py` checks this and writes
one pass.

**WAV.** Formats: 22050 Hz 16-bit mono (156 unique files), 11025 Hz 8-bit mono (90),
22222 Hz 8-bit mono (7), 22050 Hz 8-bit (1). The embedded PCM is usually 1–15 bytes shorter
than the "data size" in the header (the converter apparently dropped an incomplete last
block); for looping ambience (e.g. `Fire02`, 30 s) the size field equals the stream length.

**MIDS.** `fmt ` = u32 time format (ticks per quarter: 384 or 120), u32 max buffer (4096),
u32 flags (0 = events carry a stream id). `data` = u32 block count, then blocks of
u32 tick start, u32 byte count, `MIDSEVENT`s (u32 delta, u32 stream id, u32 event;
event >> 24: 0 short message, 1 tempo, 0x80 flag = long event with padded data).
This is the Windows MCI stream-buffer format (`midiStreamOut`).

**EVT** (three kinds, by field count):
- `Fade_<scene>_EVT` (2 fields, 30×): one record `(10, 10)` at 4000 ms. Hypothesis: fade parameters.
- `AnimDone_<scene>_EVT` (1 field, 30×): starts when the film ends, 50 records `98, 96 … 0`,
  i.e. a fade-out over 6.25 s. The root stream ends when this ends.
- Speech events (5 fields, 65×; 6 fields with extra `1`, 2×), named `E1010_A1_EVT`,
  `A11010_A11_EVT`, `Thanquol1_A22_EVT_SPK`…:
  `(speech_id, speaker, first_tick, current_tick, last_tick[, 1])`, with times in **ticks
  of 125 ms since scene start**, not film frames (A9's track reaches tick 80 in a 24-frame film).
  Verified on all 67: `speech_id` = the number of the speech WAV (`1010` → `a1010.wav`,
  `11010` → `A11010.wav`); `first_tick` = `start/125` (+0: 44, +1: 21); `(last−first+1)·125` ≈
  that WAV's duration (±3 ticks in 53/63); records every 125 ms from the object's start;
  `current_tick` counts up from `first_tick` to `last_tick−1`, stays there for about 15 ticks,
  and only the last record has `current_tick = last_tick`. `speaker` ∈ {2, 3, 4}. Hypothesis:
  drives subtitles and/or a "who is talking" marker (the talking faces are animated in the
  film itself, see A13).

## How it was verified

- `si_omni.py --check` on all 30 files: RIFF sizes = file sizes; the sum of all chunks, pads,
  padding bytes and the 3 garbage gaps = file size (every byte covered); only the chunk types
  listed above; every MxOb parses to exactly its chunk size; object ids dense 0..n−1; every
  leaf object has a header chunk and an end-of-stream chunk; no stream without an object;
  every split chunk joins to exactly its declared length.
- **Smacker**: for all 30 films the header chunk length equals `104 + 5·frames + TreesSize`
  and every data chunk length equals the frame size table entry (`& ~3`). Frames decoded with
  `si_smacker.py` and viewed (see below). Since frames are deltas, clean images deep into the
  films (A13 frame 1248, A1 frame 721) are a strong check of both the rebuild and the decoder.
- **WAV**: all 254 unique files open with Python's `wave` module. 67 speech lines also exist in
  `REMOTE/BINARY/GLUE/SPEECH`: same format in all; header data size equals the GLUE file's data
  size in 63/66; PCM sample-identical over the common length in 43 (the files differ only by a
  few trailing bytes); 24 have different samples (e.g. the A1 intro lines, A10010), so those are
  different edits/takes.
- **MIDI**: converted `.mid` files compared event by event with `FILE/BINARY/MUSIC/*.MID`
  (17 unique tracks): 10 identical (all notes, controllers, tempo, same ticks); `IMPERIAL`,
  `SKAVEN`: same notes and timing (division 384 vs 480, deviation ≤ 0.002 quarter notes), some
  channels remapped (drums on channel 9 vs 8); `IMPERIFM`, `ORCFM`, `SKAVENFM`: same note
  sequence and timing, different velocities; `DWARFFM`: same length and event count, 328 notes
  differ. Identical results for 10 tracks rule out a converter error, so these are different
  revisions of the arrangements.
- Structural checks of the EVT fields as listed above (all 127 tracks).

### What the films show (contact sheets, `extracted/si/png/*_sheet.png`)

| SI | Content |
|---|---|
| A11 | Cave with a dwarf fortress; a gunner aims a handgun, a soldier watches (cannon sounds) |
| A1 | **Game intro**: tower at night in a thunderstorm, a sorcerer writing by candlelight, a shadowy rat figure, a sorcerer casting with glowing hands, a scroll/map, lightning, the "Warhammer: Shadow of the Horned Rat" title |
| A2 | Skaven lair in green light: city under the moon, machinery, a hooded Grey Seer |
| A9 | Looping 3 s shot: armoured knight raising his arms under a town gate (loops 5×) |
| A13 | Dialogue: blond elf in green cloak and a dwarf king on his throne; the king's face and gestures change (10 speech lines) |
| A18 | Forest: a dark rider, three knights with lances (fade), a group of elves and men |
| DEATH01 | Graveyard hill at night, moon, bats (game over, `dead.mid`) |

So the `.SI` films are the **story cutscenes/briefings** between missions and the intro,
640×272 letterboxed, 8 fps, with separately mixed sound effects, speech and FM/GM music.

## Scripts

```
python3 scripts/si_omni.py --check   ".../WARFB/REMOTE/BINARY/ANIM"        # all 30: OK/BAD + summary
python3 scripts/si_omni.py --list    ".../WARFB/REMOTE/BINARY/ANIM/A11.SI" # object tree
python3 scripts/si_omni.py --extract ".../WARFB/REMOTE/BINARY/ANIM" extracted/si
python3 scripts/si_smacker.py extracted/si/A11/Scene11AnimA11.smk extracted/si/png/A11 0 33 66
python3 scripts/si_smacker.py extracted/si/A13/Scene13AnimA13.smk extracted/si/png/A13 --sheet 9
```

`--extract` writes per SI: `<ObjectName>.smk/.wav/.evt.json`, `<ObjectName>_<source>.mid` +
`<ObjectName>.mids` (raw), `objects.json` (the full object tree with media info), and
`extracted/si/INDEX.md` (one row per object: type, name, source, start, duration, output
file, details). Identical content (e.g. `thundr01.wav` used by 10 objects) is written once;
later objects point to it (`= file` in the index). Runtime: under 1 s for all 30 files.

With ffmpeg available (not installed here) the films can be checked independently:
```
ffprobe extracted/si/A1/Scene1AnimA1.smk
ffmpeg -i extracted/si/A1/Scene1AnimA1.smk -vf "select=eq(n\,100)" -frames:v 1 a1_100.png
ffmpeg -r 8 -i extracted/si/A13/Scene13AnimA13.smk a13.mp4       # play at the engine's 8 fps
```

## Summary table

| SI | size | film | film s | scene s | sounds (WAV) | speech tracks (EVT) | EVT | music (GM, FM) |
|---|---|---|---|---|---|---|---|---|
| A1 | 13.3 MB | a1.smk | 90.2 | 96.5 | 51 | 5 | 7 | intro3, intro3fm |
| A2 | 8.4 MB | a2.smk | 50.0 | 56.4 | 13 | 1 | 3 | skaven, skavenfm |
| A3 | 5.7 MB | a3.smk | 37.5 | 43.9 | 9 | 1 | 3 | skaven, skavenfm |
| A4 | 8.6 MB | a4.smk | 52.5 | 58.9 | 7 | 2 | 4 | orc, orcfm |
| A5 | 4.8 MB | a5.smk | 37.5 | 43.9 | 9 | 1 | 3 | lose, losefm |
| A6 | 3.1 MB | a6.smk | 60.2 | 66.4 | 24 | 8 | 10 | dwarf, dwarffm |
| A7 | 6.7 MB | a7.smk | 49.8 | 56.0 | 34 | 5 | 7 | skaven, skavenfm |
| A8 | 3.1 MB | a8.smk | 22.5 | 28.8 | 9 | 1 | 3 | orc, orcfm |
| A9 | 1.1 MB | a9.smk (24 fr. × 5 loops) | 15.0 | 18.8 | 3 | 1 | 3 | imperial, imperifm |
| A10 | 4.2 MB | a10.smk | 30.0 | 36.2 | 3 | 1 | 3 | lose, losefm |
| A11 | 0.9 MB | a11.smk | 8.4 | 14.5 | 6 | 1 | 3 | — |
| A12 | 1.8 MB | a12.smk | 35.8 | 41.2 | 1 | 1 | 3 | dwarf, dwarffm |
| A12B | 1.5 MB | a12b.smk | 30.8 | 36.2 | 1 | 1 | 3 | dwarf, dwarffm |
| A13 | 7.2 MB | a13.smk | 156.1 | 162.2 | 12 | 10 | 12 | imperial, imperifm |
| A14 | 2.8 MB | a14.smk | 58.2 | 64.4 | 2 | 1 | 3 | imperial, imperifm |
| A15 | 2.2 MB | a15.smk | 30.8 | 36.9 | 6 | 3 | 5 | imperial, imperifm |
| A16A | 10.6 MB | a16a.smk | 75.0 | 81.1 | 16 | 3 | 5 | imperial, imperifm |
| A16B | 4.7 MB | a16b.smk | 32.5 | 38.6 | 3 | 1 | 3 | imperial, imperifm |
| A17 | 1.6 MB | a17.smk (20 fr. × 5 loops) | 12.5 | 18.8 | 2 | 0 | 2 | orc, orcfm |
| A18 | 4.8 MB | a18.smk | 42.5 | 48.6 | 37 | 4 | 6 | dwarf, dwarffm |
| A18B | 3.3 MB | a18b.smk | 29.9 | 36.1 | 22 | 3 | 5 | dwarf, dwarffm |
| A20 | 6.6 MB | a20.smk | 53.1 | 59.1 | 15 | 3 | 5 | skaven, skavenfm |
| A22 | 3.5 MB | a22.smk | 28.8 | 35.9 | 3 | 1 | 3 | skaven, skavenfm |
| A23 | 2.8 MB | a23.smk | 13.8 | 19.9 | 13 | 1 | 3 | wintit, wintitfm |
| A24 | 6.0 MB | a24.smk | 84.1 | 90.2 | 8 | 3 | 5 | skaven, skavenfm |
| A25 | 5.8 MB | a25.smk | 43.8 | 49.9 | 6 | 1 | 3 | win, winfm |
| A26 | 2.8 MB | a26.smk | 29.9 | 36.0 | 6 | 1 | 3 | win, winfm |
| A27 | 4.5 MB | a27.smk | 29.0 | 35.1 | 22 | 0 | 2 | lose, losefm |
| DEATH01 | 0.6 MB | dead.smk | 10.0 | 16.2 | 6 | 1 | 3 | dead |
| DEATH02 | 0.6 MB | dead.smk | 10.0 | 16.2 | 6 | 2 | 4 | dead |

Totals: 30 films (640×272, 8 fps, 9 904 unique frames ≈ 20.6 min), 355 sound objects (254 unique
WAV), 67 speech tracks, 56 MIDI objects (17 unique tracks), 127 EVT tracks.
Per-object details: `extracted/si/INDEX.md` and `extracted/si/<SI>/objects.json`.

## Connections to other files (for 3.3/3.4, not investigated here)

- `.SN` contains the MxOb names of the matching `.SI` in id order (`A11_Stream`,
  `Scene11AnimA11`, …), mixed with binary fields (it starts with the object count), so it is not
  a plain string list. `.SR` contains the same source paths as `MxOb.file` (`scene11\a11.smk`).
- Speech: the speech WAVs inside `.SI` correspond to `REMOTE/BINARY/GLUE/SPEECH/<number>.WAV`
  (67 lines, 24 of them different edits). Tracks `A9010` (A9) have their speech **only** in
  `GLUE/SPEECH`; `A30000`, `A31000`, `A31010` (DEATH01/02) have EVT tracks but no WAV anywhere.
  `speech_id` in EVT records is a candidate key for subtitle text.
- Music: the MIDI tracks are the same as `FILE/BINARY/MUSIC/*.MID` (FM) and the AWE/GM
  versions (`musicawe\`), selected by the `MIDIType` variable (FM vs AWE32 setup).

## Open questions
> Issue #41 tracks the EVT speaker, subtitle, and fade behavior needed for generic playback.
> The other unknowns below are historical notes, not part of that issue; the broad backlog
> audit (issue #45) is closed.


- `MxHd` second u32 (`0x100`), `MxOb.unk14` (1 for Events), `unk_a/unk_b` (always 0),
  `palette_mgmt` (always 1), `sustain` (−1 for films), `flags` (2 vs 0/1), WAV header field `44`.
- EVT behavior tracked by #41: what `speaker` 2/3/4 means, why speech tracks last 15 ticks
  past the line, and what the `Fade` record `(10, 10)` does. Needs subtitles/texts (1.1)
  or watching the game under Wine.
- Historical EVT unknown: the 6th field `1` (A13030, A14010).
- The exact frame timing: whether the engine really ignores the Smacker frame rate (the chunk
  times say 125 ms for all films; A1/A27 headers say 85 ms per frame).
- Why 24 speech lines differ from their `GLUE/SPEECH` counterparts, and which version the game
  uses in cutscenes (the embedded one, presumably).
- The decoder only does SMK2/SMK4 video (SMK4 modes untested; all films are SMK2) and no audio.

## Playtesting: intro never ends (September 2026)

A player report ("intro should stop and progress... instead it just loops") was investigated
against the in-engine intro (`whshr.campaign_scenes.IntroScene`, `whshr.smacker.frame_index_at`,
`whshr.frontend.intro_view.IntroView`). Reproduced directly against the real A1 assets
(`whshr.game.scene_context` + `IntroScene.enter`/`update`, no frontend/GPU involved):
`omni_duration_seconds` returns exactly 96.5 s (matching the table above) and `smk.nframes` is 722
(90.25 s of video at the verified 125 ms cadence); ticking `IntroScene.update` in 10 ms steps (as
the real engine's fixed-step clock does) transitions to `MainMenuScene` at exactly `t = 96.5`, never
before and never looping. `Smacker.decode_to` already clamps to `nframes - 1` and only rewinds when
asked to go *backwards*, so a monotonically growing elapsed time cannot make it restart either.

The one gap found: `frame_index_at` itself was unbounded (`intro_view.IntroView._sync` did the
`min(..., nframes - 1)` clamp locally, untested by stdlib tests since it lives in the
pygame-dependent frontend). Moved the clamp into `frame_index_at` itself (`frame_count=None` keeps
it unbounded when a caller has no frame count) so `IntroView._sync` now reads
`frame_index_at(elapsed, self.smk.nframes)`, and the clamp — "past the last frame, hold it, never
wrap" — is covered directly by `tests/test_smacker.py`. If the reported loop still reproduces after
this, it is not in the scene/video pipeline verified here; the next suspect would be the frontend's
own frame pacing (`whshr/frontend/app.py`, out of this fix's ownership) — note that its
`FixedStepClock` (`whshr/clock.py`) caps catch-up steps at `MAX_STEPS_PER_FRAME * FIXED_STEP = 0.25 s`
per rendered frame and *drops* (not defers) any remainder, so a manual `--frame-time` capture above
0.25 s (e.g. the `--frame-time 0.5` suggested for verification) advances scene time at half rate,
not the real per-frame elapsed time; verify with `--frame-time <= 0.25` instead (this repo used 0.1).

## Proposed changes to ROADMAP.md

- Map of the installation: "Films/cutscenes" → `🟡` (container ✅, films ✅, EVT semantics open);
  note the contents: *Smacker 640×272 8 fps + WAV + MIDS music + event tracks*.
- 3.1 → ✅ (`scripts/si_omni.py`, format in FORMATS.md). Verification: all 30 files, full byte
  coverage, films/sounds/music rebuilt.
- 3.2 → ✅ (`scripts/si_smacker.py` pure-Python decoder, frames viewed; ffmpeg optional).
  For the engine: play at 125 ms per frame, mix WAV objects at their `start`, choose FM/GM MIDI
  by setting.
- 3.3: `.SI` already carries the scene timeline (object start/duration/loops, fade EVTs). What
  remains for `.SR/.SM/.SN` is how scenes are chosen and chained in the campaign.
- 3.4: new input: 67 speech EVT tracks give `speech_id` → speaker slot → timing in the scene;
  compare with `GLUE/SPEECH` and subtitle strings.
- New small task: "EVT field semantics (speaker, fade)", size S, verify by watching the
  cutscenes under Wine.
