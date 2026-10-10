# `.SFX` sound-effect packages and WAV files (ROADMAP 1.3)

## Status

| Item | Status |
|---|---|
| `.SFX` container (`RIFF` / `MSFX`, chunks, sizes) | ✅ fully decoded, all 18 files, confirmed against the reader/writer code in `MSNDDS.DLL` |
| Effect record (60 B): sample, volume, pitch, pan, priority, flags, lists | ✅ field meaning taken from `ImportSFXpackage` debug output code |
| Record fields `param_a/param_b` (+36/+38) | 🟡 copied to the runtime SFX and overwritten by `SoundPlace`; exact meaning unknown |
| `loadsfx:` name → `.SFX` file → WAV | ✅ table in `GAMEF.DLL`, all 15 names used by `.BTS` resolve |
| WAV files (663) | ✅ all valid PCM, statistics below |
| Listening review | ✅ project owner reviewed effects with their `pitch` applied and the speech files |
| When the game plays which effect (unit events, spells) | ❌ game code (`GAMEF.DLL`), not investigated |

## Where the knowledge comes from

Two independent sources, which agree:

1. **Byte analysis** of all 18 `.SFX` files.
2. **Disassembly** (`objdump -d`) of the Mindscape sound library `MSNDDS.DLL`, which exports
   `ImportSFXpackage`, `ExportSFXpackage`, `VirtualizeFilePath`, `SoundPlay`, `SoundPlace`… Its debug
   strings name every field (`"SFX %d-%02d plays sample %d (%s), at volume %d, pitch %d, pan %d, with
   priority %d."`, `" LOOP"`, `" LIST"`, `" RANDOM"`, `" 3D"`, `" INTERRUPTABLE"`), so the offsets
   below were read from the code that prints them, not guessed. The same DLL contains an editor API
   (`PackageAddSfx`, `ExportSFXpackage`, `"typedef enum tagSFX_%s"`): the `.SFX` files were written
   by an in-house SFX editor built on this library.

## Format description (ready to paste into FORMATS.md)

### `.SFX` — sound-effect package (`RIFF` / `MSFX`)

**Fully decoded and verified on all 18 files.** Reader/writer: `MSNDDS.DLL`
(`ImportSFXpackage`/`ExportSFXpackage`). Parser: `scripts/sfx_parse.py`.

A package is a list of named effects (SFX) that refer to external WAV files (samples). The audio
data is **not** inside the `.SFX` file.

```
"RIFF" u32 total_size      // = FILE SIZE (includes the 8-byte header, unlike standard RIFF)
"MSFX"
"INFO" u32 4    { u16 n_samples; u16 n_sfx; }
"SFX " u32 60*n_sfx  SfxRecord[n_sfx]
"SMP " u32 0             // always empty in the current format (see RETREAT.SFX)
"LIST" u32 n             // list data for LIST effects, u32[]
"NAME" u32 n             // n_samples null-terminated WAV paths, one after another
"SFID" u32 n             // n_sfx null-terminated effect names, one after another
00 × (20 - pad bytes)    // writer slack, see below
```

- Chunks always come in this order. The reader looks them up by tag (`RIFF_ChunkFind`).
- An odd-sized chunk is followed by one pad byte (standard RIFF word alignment).
- The writer allocates `84 + size(SFX) + size(SMP) + size(LIST) + size(NAME) + size(SFID)` bytes:
  12 (RIFF+MSFX) + 12 (INFO) + 5 × 8 (chunk headers) + **20 bytes of slack**. Pad bytes are taken
  out of the slack, so a file ends with 18–20 zero bytes. The `RIFF` size field is this total.

```c
struct SfxRecord {             // 60 bytes, little-endian
    uint32_t unk00;            // +0   writer always stores 0xFFFFFFFF; ignored by the reader
    uint32_t priority;         // +4   0..80 (UI clicks 2, battle sounds 8-14, Hum_Complete 80)
    uint32_t unk08, unk0c;     // +8   writer stores 0; ignored
    uint16_t flags;            // +16  see below
    uint16_t unk12;            // +18  never written by the exporter (uninitialised stack: 0x0040 or 0)
    uint32_t unk14;            // +20  writer stores 0; ignored
    uint32_t pitch;            // +24  playback rate in Hz; 11025 = original rate of the samples
    uint32_t volume;           // +28  0..127 (values up to 113 seen)
    uint32_t pan;              // +32  0..127, 64 = centre
    uint16_t param_a, param_b; // +36  copied to the runtime SFX, overwritten by SoundPlace (hypothesis: 3D/placement parameters)
    uint32_t unk28;            // +40  writer stores constant 0x38F (911); ignored
    uint32_t unk2c;            // +44  writer stores 0; reader treats non-zero like the LIST flag
    uint32_t unk30;            // +48  writer stores 0; ignored
    uint32_t list_count;       // +52  number of list entries (LIST effects only)
    uint32_t sample;           // +56  0-based index into NAME
};
```

`flags` (bit values as stored in the file; the library remaps them internally):

| Bit | Name (debug string) | Seen on |
|---|---|---|
| `0x01` | `INTERRUPTABLE` | `SFX_Click1/2` (button down/up) |
| `0x02` | `LOOP` | `FightLoop1-3`, `BurningBuilding`, `SFX_Cast_Wind1/2`, `Mole_Motor`… (12) |
| `0x04` | `LIST` | `SFX_Fire_ShootArrow`, `CompoundFight` |
| `0x08` | `RANDOM` | `CompoundFight` (with `LIST`) |
| `0x10` | `3D` | `SFX_Gallop1/2` (with `LOOP`) |

Flag combinations in the 103 effects of the 17 packages: none 85, `LOOP` 12, `INTERRUPTABLE` 2,
`LOOP|3D` 2, `LIST` 1, `LIST|RANDOM` 1.

**`LIST` chunk.** For every effect with the `LIST` flag (in record order) the chunk holds
`list_count` × u32 **1-based effect indices** followed by a u32 `0` separator. The reader subtracts 1,
skips members outside `1..n_sfx` ("Bogus list member") and skips the separator without checking it.
The writer emits a list only when `list_count > 1`. A list effect plays its members (in order, or
randomly with `RANDOM`) instead of its own `sample`. Examples:
- `MISSILE`: `SFX_Fire_ShootArrow` = [`SFX_Fire_Archer`, `SFX_Fire_Arrow`] (bow shot, then arrow flight).
- `BATTLE2`: `CompoundFight` = 13 random picks from `Sword1-5` and `TheSoundOfSilence`.

**`NAME` paths.** They are the developers' absolute paths, e.g.
`D:\WarFB\Windows\ROOT\FILE\BINARY\SOUND\RACE\B9512.wav`, `D:\WARFB\ROOT\...`, `C:\WARFB\...`.
`VirtualizeFilePath` first tries the path as stored. If that fails, it joins the virtual path set by the
game with the **file name + extension only**. The game sets the virtual path to the packet's directory
from the `GAMEF.DLL` table, so **only the file name counts**, looked up in the packet's directory.
Proof: `RETREAT.SFX` stores `...\SOUND\RACE\Retreat1.wav`, but the file exists only in `SOUND\SPECIAL\`.
`fmt `/`data` of the WAV are read by the same RIFF helper, and the format tag is forced to PCM.

**Effect names (`SFID`)** are for the editor/debug output (`"typedef enum tagSFX_%s"` suggests the
game code uses a generated enum of indices). `SoundPlay` works on (packet slot, effect index).

### Packet table in `GAMEF.DLL` (`loadsfx:` names)

An array of 84-byte entries at file offset `0x783c8`: `char name[9]; char dir[71]; int32 tail`
(`tail` = -1; hypothesis: runtime packet slot). Entry 0 is `void`. The file is `<dir><name>.sfx`, the
WAVs are `<dir><file name>`. Error message for an unknown name: `sfx type %s not found line %d`.

| Slot | `loadsfx` name | Directory | Effects | Used by `.BTS` |
|---|---|---|---|---|
| 1 | `buttonfx` | `binary\sound\` | 4 | 49 |
| 2 | `Battle2` | `binary\sound\battle\` | 16 | 49 |
| 3 | `spells` | `binary\sound\spells\` | 16 | 2 (test: `DB015`, `WIZTEST`) |
| 4 | `missile` | `binary\sound\missile\` | 8 | 2 (test) |
| 5 | `HumBtl` | `binary\sound\race\` | 18 | 3 (test: + `RLTEST`) |
| 6 | `OrcBtl` | `binary\sound\race\` | 11 | 3 (test) |
| 7 | `DwrfBtl` | `binary\sound\race\` | 10 | 3 (test) |
| 8 | `Skaven` | `binary\sound\race\` | 4 | 0 |
| 9 | `Monster` | `binary\sound\race\` | 3 | 0 |
| 10 | `Retreat` | `binary\sound\special\` | 1 | 4 (`BF012`, `BF018`, `BF019`, `MAXARMY`) |
| 11 | `Zhufbar` | `binary\sound\special\` | 2 | 3 (`BF015`, `BF017`, `BF038`) |
| 12 | `Dragon` | `binary\sound\special\` | 1 | 2 (`BF014`, `MAXARMY`) |
| 13 | `PortCul` | `binary\sound\special\` | 1 | 2 (`BF037`, `MAXARMY`) |
| 14 | `MoleMach` | `binary\sound\special\` | 2 | 1 (`BF040`) |
| 15 | `Hiln` | `binary\sound\special\` | 1 | 1 (`BF001`) |
| 16 | `HelpUs` | `binary\sound\special\` | 1 | 2 (`BF010`, `BF011`) |
| 17 | `Peasant` | `binary\sound\special\` | 4 | 7 |

- Every campaign battle loads `buttonfx` + `Battle2`, plus at most two mission-specific packets.
- The race and weapon packets (`spells`, `missile`, `HumBtl`, `OrcBtl`, `DwrfBtl`, `Skaven`, `Monster`)
  appear only in test scripts or nowhere. **Hypothesis:** the game loads them itself, depending on the
  armies and spells present, and names in `.BTS` just force a load.
- `loadsfx` names are written with inconsistent case (`buttonfx`, `missile`); all 15 names resolve
  case-insensitively. No name without a packet.

### Odd files

- **`SPECIAL/Z.SFX`**: not in the table and not referenced. Structurally broken: the `SFID` chunk
  declares 23 bytes but the file ends after `Zhuf_Doors`, and the records contain stack garbage
  (`0x0064f5e8`…). The file has no slack. It is an interrupted save of an early `ZHUFBAR.SFX`
  (same samples, same first record). Ignore.
- **`SPECIAL/RETREAT.SFX`**: an **older editor version**. `unk00 = 0`, `unk28 = 100` instead of 911, only
  16 bytes of slack, and a non-empty `SMP ` chunk (28 B) with per-sample data:
  `u16 0x6c, u16 0xba, u16 0x40, u16 0xba, u32 15654 (= frame count of RETREAT1.WAV), u32 11025 (rate),
  u32 100 (volume), u32 64 (pan), u32 0`. The current reader finds `SMP ` but does not use its content,
  so the file still loads.

### WAV files

Script: `scripts/sfx_wavstats.py` (manual RIFF walk + cross-check with the `wave` module).

| Group | Files | Size | Total duration | Format |
|---|---|---|---|---|
| `FILE/BINARY/SOUND/**` | 96 | 1.6 MB | 148.9 s (2.5 min) | PCM mono 8-bit: 94 × 11025 Hz, 2 × 6000 Hz (`SPELLS/WINDMAG1/2`) |
| `REMOTE/BINARY/GLUE/SPEECH/` | 567 | 126.9 MB | 2877.6 s (48.0 min) | PCM mono: 564 × 22050 Hz 16-bit, 3 × 11025 Hz 8-bit (`B3`, `B4`, `B9`, 0.02–0.3 s) |

- All 663 files are valid: PCM, consistent `block_align`/`avg_bytes`, `data` inside the file, `data`
  size a multiple of the block size, and the `wave` module opens all of them with the same parameters.
- `fmt ` chunk is 16 B, or 18 B with `cbSize = 0` (43 SOUND files, 1 speech file).
- 47 SOUND and 4 speech files have a trailing `LIST/INFO` chunk: creation dates `1995-10-13`,
  `1995-11-08`, `1995-11-20`, software `Cool Edit v1.51`, `GoldWave v2.00`.
- **548 of 567 speech files have a wrong `RIFF` size field**: it holds the `data` size, not `file - 8`.
  It is harmless for readers that walk chunks. A strict parser must not trust the field.
- Speech file names: 501 × `B…`, 65 × `A…`, 1 × `FART.WAV`. `WHSHR.EXE` builds
  `binary\glue\speech\b%s.wav`. Mapping lines to scenes is ROADMAP 3.4, not covered here.

**WAV usage by the 17 packages** (`sfx_parse.py --check`):
- 92 of 96 SOUND WAVs are used by at least one effect; every sample in every packet is used by an effect.
- **Unused**: `RACE/B9578A.WAV` (0.76 s), `RACE/B9584.WAV` (2.26 s), `RACE/FART01.WAV` (0.20 s),
  `RACE/GRUNT07.WAV` (0.42 s).
- `RACE/B9596.WAV` and `SPECIAL/B9596.WAV` are byte-identical (`Hum_Die` and the peasant death cries).
- One WAV often serves several effects at different `pitch` values:
  - `Peasant`: `SFX_ManDie`/`SFX_WomanDie`/`SFX_BoyDie` = `B9596.WAV` at 11025/16029/19853 Hz.
  - `OrcBtl`: orc and goblin variants share samples (`Orc_Dies` 7567 Hz vs `Gob_Dies` 13100 Hz).
  - `buttonfx`: `SFX_Error` = `Beep01.wav` at 4312 Hz.
- Names of the effects in the table above:
  - `HumBtl`, `DwrfBtl`, `Skaven`: `Hum_Charge1`, `Hum_Rout1`, `Dwrf_Rally`, `Skav_Die`…
  - `Battle2`, `MISSILE`, `SPELLS`: `FightLoop1`, `SFX_Fire_Cannon`, `SFX_Cast_Fireball`…

  Full list: `python3 scripts/sfx_parse.py <WARFB>`.

### Listening catalogue: `RACE` and creature WAVs

The following identifications are from listening.  Text in **Notes** records uncertain transcription
or contextual observations; it is deliberately not normalized to an assumed in-game command.

| Filename | Contents | Notes |
|---|---|---|
| `B9501.WAV` | Fire! | |
| `B9504.WAV` | Rally | |
| `B9507.WAV` | Regoup | |
| `B9509.WAV` | Hold | |
| `B9512.WAV` | Charge | |
| `B9514.WAV` | I cannot | |
| `B9516.WAV` | To the death | |
| `B9518.WAV` | Attack | |
| `B9527.WAV` | Reload | |
| `B9529.WAV` | Retreat | |
| `B9530.WAV` | I sir | |
| `B9534.WAV` | Yes my lord | |
| `B9535.WAV` | Flee | |
| `B9537.WAV` | Destroy them | |
| `B9539.WAV` | All is lost | |
| `B9544.WAV` | Smash them | |
| `B9547.WAV` | Crush them | |
| `B9550.WAV` | No mercy | |
| `B9556.WAV` | Enemy sighted | |
| `B9559.WAV` | Mission compete | |
| `B9564.WAV` | Engage | |
| `B9567.WAV` | Totehoooo | |
| `B9570.WAV` | Run | |
| `B9572.WAV` | Die you will | |
| `B9578A.WAV` | Eeeehh | |
| `B9580.WAV` | Um blath | Possibly orc. |
| `B9582.WAV` | Die you be | |
| `B9583.WAV` | Blee | |
| `B9584.WAV` | Bleeee eeeh | |
| `B9592.WAV` | Uahhh | |
| `B9596.WAV` | Ooooh | Sounds like a wounded person. |
| `B9615.WAV` | Die die | |
| `BOAR02.WAV` | Boar sound | |
| `FART01.WAV` | Fart | |
| `FEAR01.WAV` | My men fear the best | |
| `GRUNT02.WAV` | Grunt | |
| `GRUNT07.WAV` | Grunt | |
| `GRUNT09.WAV` | Grunt | |
| `HORSE02.WAV` | Horse | When a cavalry unit dies. |
| `LAUGH08.WAV` | | |
| `LAUGH09.WAV` | | When an orc(?) starts chasing. |
| `LAUGH10.WAV` | | |
| `ROAR01.WAV` | | |
| `ROAR03.WAV` | | Beast dies. |
| `SQUEAL01.WAV` | | |
| `SQUIG02.WAV` | | |
| `WARGH1.WAV` | | |

## How it was verified

- **All 18 `.SFX` files** parsed by `sfx_parse.py --check`. 17 files have 0 problems. The only file with
  problems is `Z.SFX` (truncated, described above).
  - `RIFF` size = file size in 18/18.
  - Writer size formula (`84 + chunk data`) matches exactly in 16/18: all but `RETREAT` (older version)
    and `Z` (truncated).
  - Trailing bytes are all zero.
  - `SFX` size = 60 × `n_sfx`; the `NAME`/`SFID` string counts equal `n_samples`/`n_sfx`.
  - Every `sample` index is in range, and every list member is in `1..n_sfx` with a 0 separator.
  - The `LIST` chunk is consumed exactly: 56 B in `BATTLE2` = 13 + 1 u32, 12 B in `MISSILE` = 2 + 1.
  - 102/103 records of the listed packets match the writer constants (`unk00 = -1`, `unk28 = 911`,
    zeros); the exception is `RETREAT`.
- **Field meaning** was read from `ImportSFXpackage` (offsets of the values passed to the
  "plays sample … volume … pitch … pan … priority" printf, the flag tests next to `" LOOP"` etc., the
  list loop) and confirmed by `ExportSFXpackage`, which writes the same 15 × u32 layout, the flag
  remapping, `0x38F`, the `+1` of list entries, the `0` separator and the 20-byte slack.
- **Sanity of values**: `pitch` 11025 equals the rate of the WAVs. Effects that reuse one WAV differ
  exactly in `pitch`, with lower values for bigger creatures (orc vs goblin, man/woman/boy). The `LOOP`
  effects are long ambient sounds (fight loops, wind, fire, motor). The list contents are meaningful
  (archer shot + arrow; swords + silence).
- **Cross-reference**: all 15 distinct `loadsfx` names in the 54 `.BTS` files (via
  `whscript.load_battle`) resolve through the `GAMEF.DLL` table to an existing `.SFX`. All 103 samples
  resolve to an existing WAV in the packet directory.
- **Not verified by listening** in this session (no audio output available to the agent). Suggested
  check: play `Peasant` `SFX_BoyDie` resampled to 19853 Hz and `OrcBtl` `Gob_Dies`.

## Scripts

```
python3 scripts/sfx_parse.py ".../WARFB/FILE/BINARY/SOUND/BUTTONFX.SFX"     # one package
python3 scripts/sfx_parse.py ".../WARFB"                                     # all packages with WAV names
python3 scripts/sfx_parse.py ".../WARFB" --check --json extracted/sfx/sfx.json
python3 scripts/sfx_wavstats.py ".../WARFB" [--list] --json extracted/sfx/wavstats.json
```

- `sfx_parse.py`: `parse_sfx(bytes)` returns chunks, samples, effects (all 60 bytes as named fields,
  list members resolved to names) and a problem list. `packet_table(root)` reads the table from
  `GAMEF.DLL`. `analyse_install(root)` does the cross-reference: `loadsfx` usage, WAV users, unused
  and duplicate WAVs, stored directory vs packet directory. Paths are resolved case-insensitively,
  `UPDATE/BINARY` before `FILE/BINARY`; `UPDATE` has no sound files.
- `sfx_wavstats.py`: per-file RIFF/`fmt ` data, duration, `LIST` text and problems; summary per group.
- JSON output (game-derived data, not for distribution): `extracted/sfx/sfx.json`,
  `extracted/sfx/wavstats.json`.

## Open questions
> **Historical questions:** issue #40 is closed. These notes preserve the findings; the remaining unknowns are not standing research tasks. Reopen a focused issue only when a shipped feature or reproducible defect needs an answer.


- `param_a`/`param_b` (+36/+38): values `0x0a00/0x0a00` (most), `0/0`, `0xffff/0xffff`
  (`Mole_Crash`, `Zhuf_Inside`, both with priority 0), `0x07eb/0x07dc` (`SFX_Gallop2`),
  `0x04b7/0x04e6` (`SFX_Cast_Laugh`, which also has `pan = 127`). `SoundPlace` overwrites them from its
  arguments, and `MSFX_SetEnvelope`/`MSFX_SetEarPos` exist. Hypothesis: 3D position or distance/envelope
  parameters. Needs a closer look at `SoundPlace`/`SoundUpdate`.
- Exact effect of `priority` (channel stealing) and `INTERRUPTABLE`; what `3D` does with the
  listener position (`MSFX_SetEarPos`).
- How `pitch` is applied: presumably `IDirectSoundBuffer::SetFrequency(pitch)`; the `SetStat … pitch` string supports this.
- When `GAMEF.DLL` loads `Skaven`/`Monster`/race packets and which game events play which effect index
  (charge, rout, rally…). This needs disassembly of `GAMEF.DLL` (ROADMAP phase 4).
- Meaning of the first 8 bytes of the old `SMP ` record in `RETREAT.SFX` (`6c 00 ba 00 40 00 ba 00`).
- Whether the 4 unused WAVs are referenced from anywhere else (e.g. code or speech scripts);
  `strings` on the EXE/DLLs finds no WAV names except `speech\b%s.wav`.

## Proposed changes to ROADMAP.md

- "Effects and speech" row: status ⬜ → ✅ for `.SFX`/WAV formats. Replace the "SFX = own `RIFF MSFX`"
  description with: `MSNDDS.DLL` package: effects → external WAV, volume/pitch/pan/priority/flags/lists.
- 1.3: mark ✅. Weakened verification item: "sounds match names" is verified structurally (names, pitch
  variants, lists) but not by listening. Add a sub-item "listen to a few effects with the `pitch` applied".
- New item for phase 5 (engine): SFX playback = PCM + resampling to `pitch` + volume/pan
  + loop/list/random + priority channels; a 3D model needs `param_a/b` (open question above).
- New item for phase 4: which game events trigger which effect index (unit voices `Hum_*`, `Dwrf_*`…)
  and when race packets are loaded.
- Note for 3.4 (speech): 548/567 speech WAVs have a wrong RIFF size field, so use a chunk-walking reader.
