# Music — `MUSIC/*.MID` + `SOUND/WARINTR3.SBK` (ROADMAP 1.2)

Black-box analysis (byte structure + strings, no disassembly). Game files are read from the
GOG installation; nothing from the game is in the repo (`extracted/music/` is git-ignored).

## Status

| Item | Status |
|---|---|
| `WARINTR3.SBK` structure | ✅ **SoundFont 1.0** (not SF2), fully parsed: 3 presets, 3 instruments, 6 samples |
| SBK sample rate / root key (fields SF1 does not store like SF2) | ✅ verified by pitch measurement (44100 Hz, gen 55 = root key in cents) |
| SF1 units of filter / modulation envelope / LFO generators | ❌ unknown (differ from SF2) |
| All 40 `.MID` files | ✅ parsed, 0 structural errors (SMF format 1, tempo, lengths, channels, programs) |
| Which presets come from the SBK and which from the AWE32 ROM | ✅ bank MSB 1 = SBK (every bank-1 program exists in the SBK); everything else = 1 MB GM ROM |
| GM vs FM variants (`XXXXXXFM.MID`) | ✅ naming rule verified on all files; selection by `MIDI.DLL` (strings) |
| Playback selection | ✅ | Tune names in glue scripts, window records, cutscene data and native screens are documented; the runtime plays glue `playmidi` plus native debrief and credits tunes. Window-record and cutscene music remain unwired. |
| Full audio render with original sound | ✅ all 21 GM tracks rendered with FluidSynth (FluidR3_GM + the converted SBK in bank 1) at one uniform gain, no clipped samples; the project owner listened to and confirmed both the SBK stems and the full renders |

## Summary (ready to paste into `FORMATS.md`)

- The music is **standard MIDI** (SMF format 1), 21 compositions in two arrangements each:
  a **GM** version for wavetable cards (`INTRO3.MID`) and an **FM** version for OPL cards
  (`INTRO3FM.MID`). `VICTORY` has no FM version; `LOOKING` and `LOOKIN2` share `LOOKINFM`.
- The only instrument bank shipped with the game, `SOUND/WARINTR3.SBK`, is a **SoundFont 1.0**
  user bank for the Sound Blaster AWE32 (EMU8000). It contains only **3 presets**
  (two choirs and a brass sound), not a GM set. `INFO irom = 1MGM` says the bank was made
  to sit on top of the AWE32's **1 MB General MIDI ROM**, which is where all other
  instruments come from (strings, timpani, harp, drums…). That ROM is not part of the game.
- MIDI files select the SBK presets with **bank select CC0 = 1** (the AWE32 user bank slot).
  All 25 other programs and all drum kits are selected with CC0 = 0, i.e. they come from the GM ROM.
- `WHSHR.EXE` loads the bank from `binary\sound\warintr3.sbk` (through `MSAWE.DLL` →
  `AWEMAN32.DLL` → `SBAWE32.DRV`, i.e. the real AWE32 driver). Under Wine there is no such
  driver, so the bank is never loaded. Music uses the Windows MIDI mapper (`midiOut*` in `MIDI.DLL`).

### `.SBK` — SoundFont 1.0

`RIFF sfbk` like SoundFont 2, but `ifil = 1.00` and some chunks differ:

| Chunk | SoundFont 2.01 | `WARINTR3.SBK` (SF 1.0) |
|---|---|---|
| `LIST sdta` | `smpl` only | **`snam`** (sample names, 20 B each) + `smpl` (16-bit PCM LE) |
| `phdr`, `pbag`, `pgen`, `inst`, `ibag`, `igen` | 38/4/4/22/4/4 B records | same sizes and meaning |
| `pmod`, `imod` | 10 B records | 6 B zero stub (no modulators) |
| `shdr` | 46 B (name, start, end, loop, **rate, root key, correction, link, type**) + terminal record | **16 B**: `start, end, loop_start, loop_end` (u32, in frames from `smpl` start), no terminal record |
| `inst` names | ASCII | garbage bytes (`00 ff ff …`) |
| generator 55 | reserved | **root key in cents** (`6000` = key 60, `7200` = key 72) |
| filter / mod env / LFO generators (5, 8, 10, 11, 21–30) | SF2 units | different units (e.g. brass `initialFilterFc = 0` would silence it in SF2) — unknown |

`INFO`: `isng=EMU8000`, `irom=1MGM`, `iver=2.08`, `INAM="Warhammer Intro"`, `IPRD=SBAWE32`,
`IENG=Skimpy`, `ISFT="SFSTORE.DLL v1.0"`, `ICRD="10  3 95"`,
`ICMT="This bank contains two choir sounds for the Warhammer Intro tune."`,
`ICOP="Copyright © Mindscape Int."`. `smpl` = 449 726 B = 224 863 frames (5.1 s at 44.1 kHz), all samples in RAM (no ROM references).

| Bank in file | Bank in game | Program | GM name of that slot | Preset | Zones: key range → sample (recorded pitch as MIDI key) |
|---|---|---|---|---|---|
| 0 | 1 | 52 | Choir Aahs | `HAL5TSL.WAV` | 0–127 → `HAL5TSL.WAV` (72.87) |
| 0 | 1 | 54 | Synth Voice | `HALOOH22.WAV` | 0–127 → `HALOOH22.WAV` (58.4) |
| 0 | 1 | 57 | Trombone | `WarBrass` | 0–63 → `TRUMPC4` (60); 64–81 → `TRUMPC5` (72); 82–108 → `TRUMPC6` (84); 12–107 → `TRUMPC5` (71.82, −8 dB layer) |

Samples: `HALOOH22.WAV` 76 028 frames, `HAL5TSL.WAV` 59 901, `TRUMPC3` 31 626 (**not used by any zone**),
`TRUMPC4` 25 260, `TRUMPC5` 15 320, `TRUMPC6` 16 512. All loop (`sampleModes = 1`). The choirs
loop over their second half, the trumpet samples use loop offsets from the zones.

### `.MID` — tracks

All 40 files: SMF **format 1**, 4–29 tracks, PPQN 384 (`IMPERIAL`, `SKAVEN` 480; `LOSEFM`,
`TACTICFM` 120), one tempo (except `INTRO3` with 4 and `SCRIBE` with 2), 4/4. Controllers
used: 0, 1, 7, 10, 32, 91, 93 (+112, 119 in two files). No SysEx, no NRPN (so no AWE32-specific
effect programming), no text/marker events. Track names are only the composer's
labels (`Strings`, `Timpani`, `OrchDrums`, …).

| Track | FM file | Tracks | PPQN | BPM | Length s (GM / FM) | Channels (GM) | SBK presets (bank 1) | Where used (strings, see below) |
|---|---|---|---|---|---|---|---|---|
| `BATTLE` | `BATTLEFM` | 14 | 384 | 140 | 219.4 / 219.4 | 1,2,4,6,7,9,10,12,14,16 | – | only a bare `battle.mid` string in `GAMEF.DLL` |
| `COMBAT` | `COMBATFM` | 14 | 384 | 140 | 216.0 / 216.0 | 1,2,4–7,9,10,12–14,16 | – | glue: ambush encounters (`playmidi:combat` ×5) |
| `DEAD` | `DEADFM` | 4 | 384 | 80 | 24.0 / 24.0 | 6,7,10 | – | death cutscenes `DEATH01`, `DEATH02` (GM and FM files are byte-identical) |
| `DWARF` | `DWARFFM` | 8 | 384 | 100 | 153.6 / 153.6 | 2,3,4,7,10,12,14 | 57 | cutscenes A6, A12, A12B, A18, A18B |
| `FOREST` | `FORESTFM` | 11 | 384 | 100 | 122.2 / 122.2 | 2–4,6–8,10–12,14 | 57 | not found |
| `GENERIC` | `GENERIFM` | 7 | 384 | 110 | 78.5 / 78.5 | 2,3,7,12,16 | 57 | glue: campaign map / travel / encounters (`playmidi:generic` ×55) |
| `IMPERIAL` | `IMPERIFM` | 10 | 480 | 95 | 141.5 / 141.5 | 2–4,6,7,9,12,14 | – | cutscenes A9, A13, A14, A15, A16A, A16B |
| `INTRO3` | `INTRO3FM` | 21 | 384 | 102.8 | 86.2 / 86.2 | 1–10 | 52, 54, 57 | intro cutscene A1; `[MIDI] name:intro3` on `MoreOptionScreen`; `WHSHR.EXE` credits (`CreditBook`, `CreditWindow`) |
| `LOOKIN2` | `LOOKINFM` | 14 | 384 | 100 | 182.4 / 182.4 | 1–8,10,11,15,16 | – | not found (near-copy of `LOOKING`, +16 notes) |
| `LOOKING` | `LOOKINFM` | 13 | 384 | 100 | 182.4 / 182.4 | 1–8,10,11,15,16 | – | glue: `addmidiobject:looking` on map windows (×4) |
| `LOSE` | `LOSEFM` | 9 | 384 | 80 | 144.0 / 144.0 | 3,4,6,7,10,12,14,16 | – | `WHSHR.EXE` next to `[OpenTroopSelection] … Debriefing`; cutscenes A5, A10, A27 |
| `ORC` | `ORCFM` | 9 | 384 | 120 | 132.5 / 132.5 | 2,4,7,10,12,13,16 | – | cutscenes A4, A8, A17 |
| `SCRIBE` | `SCRIBEFM` | 16 | 384 | 250→100 | 164.2 / 182.4 | 1–8,10–12,14–16 | 52, 54 | glue: caravan screens with Dietrich the scribe (`[MIDI] name:scribe` ×23) |
| `SIGHTED` | `SIGHTEFM` | 17 | 384 | 100 | 242.4 / 242.4 | 1–10,12–15 | – | glue: `[START]` of every campaign mission script (`playmidi:sighted` ×46) |
| `SKAVEN` | `SKAVENFM` | 9 | 480 | 80 | 143.6 / 143.6 | 1,2,7–11,14 | – | cutscenes A2, A3, A7, A20, A22, A24 |
| `TACTICAL` | `TACTICFM` | 11 | 384 | 100 | 134.4 / 122.4 | 2–4,6–8,10–12,14 | 57 | `WHSHR.EXE` next to `TroopWindow` (troop selection / deployment?) |
| `TENSE` | `TENSEFM` | 21 | 384 | 100 | 134.4 / 134.4 | 1–3,6,7,10,12,14,16 | 54, 57 | not found |
| `TITLE` | `TITLEFM` | 29 | 384 | 104 | 279.2 / 272.3 | 1–8,10 | 52, 57 | glue: `[MIDI] name:title` on `OptionScreen` (main menu) |
| `VICTORY` | **none** | 11 | 384 | 140 | 72.0 / – | 2,4,6,7,9–12,14,15 | – | not found |
| `WIN` | `WINFM` | 9 | 384 | 140 | 143.4 / 105.4 | 2,4,7,10–12,14,15 | 57 | `WHSHR.EXE` next to `[OpenTroopSelection] … Debriefing`; cutscenes A25, A26 |
| `WINTIT` | `WINTITFM` | 14 | 384 | 104 | 90.0 / 90.0 | 1,2,5,8,10 | – | cutscene A23 (final victory) |

Notes on the table:
- The length is up to the last MIDI event (usually the end-of-track marker), taken over the tempo map.
- GM and FM arrangements are the same composition: same tempo, mostly the same length.
  FM versions use only channels 1–10 (drums on 10) and fewer notes (e.g. `TITLE` 8662 vs 5287).
  GM versions spread parts over channels 1–16. Differences: `SCRIBE` starts with 4 bars at 250 BPM
  (then 100) while `SCRIBEFM` stays at 100 BPM; `TITLE`, `WIN` and `TACTICAL` have shorter
  FM endings.
- The FM files also contain the CC0 = 1 bank selects. They were just ignored on OPL cards.

**GM ROM programs used (bank MSB ≠ 1)**, number of files out of 40: String Ensemble 1 (48) 36,
Timpani (47) 34, Orchestral Harp (46) 26, Tubular Bells (14) 25, Oboe (68) 23, String Ensemble 2 (49) 18,
Bright Acoustic Piano (1) 13, Bassoon (70) 13, Glockenspiel (9) 11, Clarinet (71) 9, Reverse Cymbal (119) 9,
French Horn (60) 8, Pizzicato Strings (45) 6, Taiko Drum (116) 6, Trombone (57) 5, Pad 2 (89) 4,
Orchestra Hit (55) 3, Tuba (58) 3, Pad 1 (88) 3, and 2 files each: Trumpet (56), Pan Flute (75),
Shakuhachi (77), Lead 8 (87), Piano (0, channels without a program change); Synth Voice (54) 1.
Drum channel: program 48 (GS "Orchestra" kit) in 29 files, 0 in 4, 58 in 4 (`INTRO3`, `TITLE`), 27 in 2 (`INTRO3`).
`LOSE`, `VICTORY` and `WINTITFM` use **GM** Trombone (bank 0) and not `WarBrass`. `ORC` uses
CC0 = 0 / CC32 = 1 with program 57, and `TITLE`/`WINTIT` use the same with 60. So the ROM
instrument answered there, which fits the AWE32 selecting banks by CC0 only.

### How the game picks music (strings only)

- **Engine**: `binary\music\%s.mid` in `WHSHR.EXE`/`GAMEF.DLL`. `MIDI.DLL` exports
  `MIDI_InitTune/PlayTune/StopTune/FadeAndDiscard/SetRepeats/SetVolume/UseFM` and logs
  `"MIDI_InitTune: Called with arg "%s". Using %s version."` with the strings `GM`/`FM`, plus
  `"MIDI_UseFM: The MIDI system will use %s music files."`. On disk the FM file name is
  **the first 6 characters of the name + `FM`** (`SIGHTED` → `SIGHTEFM`, `GENERIC` → `GENERIFM`).
  The rule holds for all 19 FM files. **Hypothesis:** `MIDI.DLL` builds that name when FM mode is on.
- **Bank**: `binary\sound\warintr3.sbk` in `WHSHR.EXE` (among `[WinMain]` strings). `MSAWE.DLL`:
  `AWE_Open`, `AWE_LoadBank` ("Failed to load user bank %s"), `AWE_ClearBank`. This is a *user* bank, hence bank number 1.
- **Campaign "glue" scripts** are embedded as resources in `FILE/DLL/WND.DLL`
  (same INI-like syntax as `.BTS`). Music commands (command list also in `GAMEF.DLL`:
  `playmidi`, `stopmidi`, `setmidivolume`, `addmidiobject`, section `[MIDI]`):
  - `[WINDOW] … [MIDI] name:<track> [END]`: background music of a window
    (`title` on `OptionScreen`, `intro3` on `MoreOptionScreen`, `scribe` on caravan screens);
  - `playmidi:sighted` at `[START]` of mission scripts (comments such as
    `;--Border Princes : Mission 01 : Protect Schnappleburg--`), `playmidi:generic` on the map
    and in encounters, `playmidi:combat` in ambush windows, `stopmidi:` before battles/cutscenes;
  - `addmidiobject:looking` when a map window opens.
- **Cutscenes** (`REMOTE/BINARY/ANIM/*.SR`, Mindscape Omni) reference two paths each:
  `music\<name>fm.mid` and `musicawe\<name>.mid` (objects `Music_A1_FM_MID`, `Music_A1_GM_MID`
  in `.SI`). The `.SI` files contain no embedded `MThd`, and there is no `MUSICAWE` directory,
  so the Omni player presumably maps these paths onto `BINARY/MUSIC` (hypothesis). `DEATH01/02`
  only have `musicawe\dead.mid`. `A11` has no music.
- Track names never appear in `.BTS`/`.MRC`, `SCRIPT/*.DLL` or the save games.

## How it was verified

1. **SBK parser** (`music_sf2.py`) on the only SBK. The RIFF size matches the file, all chunks
   are consumed, all zone/bag/generator indices resolve, and all samples lie inside `smpl`.
2. **Sample rate and root key**. Autocorrelation pitch of each sample: `TRUMPC3/4/5/6` measure
   129.7 / 260.9 / 518.8 / 1050 Hz, which are C3/C4/C5/C6 **only at 44100 Hz** (at 22050 Hz they would
   be an octave lower than their names). Then `music_render.py selftest` plays keys 60 and 72
   on every preset with gen 55 as the root key plus coarse/fine tune. Result: 261.7/523.6,
   262.8/521.5 and 261.7/523.0 Hz against 261.6/523.3 Hz expected, so errors are +1…+8 cents.
   Gen 55 is consistent in all 6 zones (e.g. choir `HAL5TSL` is recorded at ~C♯5, and
   `coarseTune=-1, fineTune=+13` with root 72 brings it to C5).
3. **MIDI parser** (`music_midi.py --check`) on all 40 files. Each track's parsed length equals
   its declared `MTrk` length, every track ends with End-of-Track, and the track count matches the header.
4. **Bank mapping** (`music_report.py`) across all 40 files. Every program change made with
   CC0 = 1 (52, 54, 57, in 17 files) exists in the SBK. No bank-1 program is missing, and no
   SBK preset goes unused.
5. **SBK → SF2 conversion** (`music_sbk2sf2.py`) re-read with our own parser: SF2 2.01,
   3 presets in bank 1, 6 samples at 44100 Hz, no warnings.
6. **Audio (pure Python, since no external tools are available)**:
   - the 6 samples as WAV: all non-silent (peak −0.01…−6.2 dBFS, RMS −11…−20 dBFS);
   - "SBK stems", i.e. only the notes that play on the game's bank, at 22 050 Hz mono, normalised:

     | Stem | SBK notes | Peak / RMS dBFS | WAV length | MIDI length | Audible until |
     |---|---|---|---|---|---|
     | `INTRO3_sbk_stem.wav` | 596 (= all notes of channels with CC0 = 1) | −1.0 / −22.3 | 89.2 s | 86.2 s (+3 s release tail) | 87.2 s |
     | `TITLE_sbk_stem.wav` | 642 | −1.0 / −22.9 | 282.2 s | 279.2 s | 192.4 s (SBK parts end there) |
     | `SCRIBE_sbk_stem.wav` | 120 | −1.0 / −24.5 | 167.2 s | 164.2 s | 60.5 s (quiet: raw peak 0.03) |

   **Listened to and confirmed by the project owner (2026-09-12).** The full renders of all
   21 tracks followed (next section).

## Scripts

```
python3 scripts/music_sf2.py  .../FILE/BINARY/SOUND/WARINTR3.SBK                  # INFO, presets, zones, samples
python3 scripts/music_sf2.py  .../WARINTR3.SBK --extract-samples extracted/music/sbk_samples --rate 44100
python3 scripts/music_midi.py --check .../FILE/BINARY/MUSIC                        # table of all 40 files
python3 scripts/music_midi.py .../FILE/BINARY/MUSIC/INTRO3.MID [--json]            # channels, programs, texts
python3 scripts/music_report.py .../WARFB                                          # Markdown tables used above
python3 scripts/music_sbk2sf2.py .../WARINTR3.SBK extracted/music/WARINTR3_bank1.sf2   # SF1 -> SF2, presets in bank 1
python3 scripts/music_render.py selftest .../WARFB                                 # pitch test of the SBK presets
python3 scripts/music_render.py stem .../WARFB INTRO3 extracted/music/INTRO3_sbk_stem.wav
python3 scripts/music_render.py verify extracted/music/X.wav .../MUSIC/X.MID       # RMS/peak/length vs MIDI
python3 scripts/music_render.py commands .../WARFB extracted/music [--run]         # full-render commands
```

`music_sbk2sf2.py` keeps the structure, tuning, loops, attenuation, chorus/reverb sends and the
volume envelope (SF2 timecents, **hypothesis**). It **drops** the filter, modulation-envelope and
LFO generators, whose SF1 units are unknown. The timbre is therefore approximate: no filter sweep
on `WarBrass`.

### Full render

The original sound is AWE32 = 1 MB GM ROM + this bank. No free copy of the ROM exists, so use a GM
soundfont as a stand-in and load the converted bank **after** it, so it takes priority for bank 1:

```sh
sudo apt install fluidsynth fluid-soundfont-gm ffmpeg
W=".../GOG Games/Warhammer - Shadow of the Horned Rat/WARFB"
python3 scripts/music_sbk2sf2.py "$W/FILE/BINARY/SOUND/WARINTR3.SBK" extracted/music/WARINTR3_bank1.sf2 --bank 1
mkdir -p extracted/music/full
for S in BATTLE COMBAT DEAD DWARF FOREST GENERIC IMPERIAL INTRO3 LOOKIN2 LOOKING LOSE ORC SCRIBE \
         SIGHTED SKAVEN TACTICAL TENSE TITLE VICTORY WIN WINTIT; do
  fluidsynth -ni -q -g 0.26 -r 44100 -o synth.midi-bank-select=gs -F extracted/music/full/$S.wav \
    /usr/share/sounds/sf2/FluidR3_GM.sf2 extracted/music/WARINTR3_bank1.sf2 "$W/FILE/BINARY/MUSIC/$S.MID"
  python3 scripts/music_render.py verify extracted/music/full/$S.wav "$W/FILE/BINARY/MUSIC/$S.MID"
  ffmpeg -y -loglevel error -i extracted/music/full/$S.wav -c:a libvorbis -q:a 6 extracted/music/full/$S.ogg
done
```

`python3 scripts/music_render.py commands <WARFB> extracted/music/full --run` runs the same steps.

**Gain.** The first renders used `-g 0.8`, which clipped 10 of the 21 tracks (up to 0.4 % of the
samples in `COMBAT`). A float render (`-O float`) at 0.8 gave the true peaks: `INTRO3` 2.65
(+8.5 dBFS), `BATTLE`/`TITLE` 2.14, `COMBAT` 2.10 … `DEAD` 0.16. To keep the relative loudness of
the tracks (the game played them at one volume), all tracks use **one gain, 0.26**, which puts the
loudest track at −1.3 dBFS. Result (FluidSynth 2.4.8, FluidR3_GM, 44.1 kHz stereo, 0 clipped samples
in all 21 files): peaks from −1.3 dBFS (`INTRO3`) to −25.5 dBFS (`DEAD`); `SKAVEN`, `SCRIBE` and
`LOOKING` are quiet compositions (RMS below −38 dBFS). Lengths match the MIDI files plus the release
tail. 64 MB of OGG in `extracted/music/full/`.

`synth.midi-bank-select=gs` (FluidSynth's default) uses only CC0 for the bank number, which
matches the AWE32 behaviour inferred above. FluidSynth does not read SoundFont 1 files, hence
the conversion. To compare, render without `WARINTR3_bank1.sf2`: bank-1 notes then fall back to
GM Choir Aahs / Synth Voice / Trombone. `music_render.py commands … --run` runs exactly these
steps once the tools exist.

## Research boundary

Issue #39 is closed. Glue scripts, window records and cutscene data supply tune names for
data-driven playback; `win`, `lose` and `tactical` are documented in `notes/native-windows.md` §9.
The current frontend plays glue `playmidi` effects; it does not yet use window-record music or
schedule cutscene MIDI.
The locations of unreferenced tracks and the original AWE32's exact filter, envelope and drum-kit
choices are not prerequisites for playback. Investigate a music discrepancy when a shipped scene
actually plays the wrong tune or sounds wrong with the supported renderer.

## Current ROADMAP status

Item 1.2 is ✅: the MIDI and SBK formats, bank mapping, FluidSynth renders of all 21 GM tracks,
and listening review are complete. Cutscene music references and glue music commands are documented
above and in their respective topic notes. Offline FluidSynth verification used a GM soundfont
with the converted SBK in bank 1. That combination is the intended runtime design; currently the
frontend passes installed `.MID` files to `pygame.mixer.music` without configuring those banks.
Unresolved SF1 filter and envelope units are outside the current playback scope.
