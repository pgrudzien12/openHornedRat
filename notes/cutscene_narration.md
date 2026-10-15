# Cutscene narration caption pages

Public implementation report: what the original front end shows **before** a cutscene film (the black
"narration" page with white text), which `ANTXT` captions belong to which film, the page layout, and its
timing and input. Companion reports: `notes/si_omni.md` (the `.SI` film container and its event tracks),
`notes/scene_scripts.md` (scenes, speech and their place in the campaign), `notes/pe_resources.md`
(`ANTXT` numbering), `notes/fonts_glue.md` (glue font slots).

Status: ✅ unless marked 🟡.

## 1. When a caption page is shown

- **Only before a film, never between or after.** The page is put up when a film is opened, stays while
  the film loads, and is taken down right before the first film frame. Nothing in the shipped films
  brings a page back mid-film or after it ends (§2.3).
- **Every film-playing path gets it**: `playmovie`, `iftrueplaymovie`, `iffalseplaymovie` (the page
  belongs to the film that actually plays; a conditional that does not fire shows neither page nor film),
  the boot intro `A1`, and the defeat films `DEATH01`/`DEATH02`. The page is chosen from the **film name
  alone**, not from the glue script, so the same film shows the same page wherever it is played.
- `loadanimstringintocache` has nothing to do with the page; it prepares the speech subtitle lines
  shown *during* the film. The caption page reads its strings directly.
- A film with no caption entry (table below) plays immediately, with no page.

## 2. Which captions belong to which film

### 2.1 Rule

The film's number `M` is the decimal number right after the leading `A` of the file name (letters after
the number are ignored: `A12b` → 12, `A18B` → 18, `A16a` → 16). Names that do not start with `A` plus a
number (`DEATH01`, `DEATH02`) give number 0. The number selects a row in a fixed table of
*(first caption id, number of further ids)*; the page text is the strings
`first, first+1, …, first+extra` from `ANTXT`. One exception: a film numbered **16 whose name has `B`/`b`
right after the number** (`A16b`) uses `16600` with one further id instead of row 16.

### 2.2 Table (film number → caption ids)

| Film | Caption ids on the page | Notes |
|---|---|---|
| 0 (`DEATH01`, `DEATH02`) | — | no page |
| `A1` (boot intro) | 1100, 1101, 1102 | |
| `A2` | 2100 | |
| `A3` | 3100, 3101, 3102 | |
| `A4` | 4100 | |
| `A5` | 5100 | |
| `A6` | 6100 | |
| `A7` | 7100, 7101 | |
| `A8` | 8100, 8101, 8102 | |
| `A9` | — | no page |
| `A10` | 10100 | |
| `A11` | 11100 | |
| `A12` **and** `A12b` | 12100 | both endings share the page |
| `A13` | **13200** | not 13100 (see below) |
| `A14` | — | no page |
| `A15` | 15100 | |
| `A16a` | 16100 | |
| `A16b` | **16600, 16601** | the name exception of §2.1 |
| `A17` | 17100 | |
| `A18` **and** `A18B` | 18100, 18101 | both branches share the page |
| 19 | — | no such film |
| `A20` | **20100 only** | |
| 21 | 21100, 21101 | **no film `A21` exists, so these two captions are never shown** |
| `A22` | 22100, 22101 | |
| `A23` | 23100, 23101 | |
| `A24` | 24100 | |
| `A25` | 25100 | |
| `A26` | 26100 | |
| `A27` | 27100, 27101, 27102, 27103 | |

Higher numbers have no row (no such films).

### 2.3 The irregular ids explained

- **`12510`, `13100`, `16510`** are not captions: they are **speech subtitles** (they start with a
  speaker name and have recordings, `A12510.wav`, `A13100.wav`, `A16510.wav`). They are shown *inside*
  the film by its speech event tracks like any other `+10, +20…` line. The `+100` reading of
  `notes/pe_resources.md` does not apply to them; `13100` is simply the tenth speech line of `A13`.
- **`A13`'s caption is `13200`** ("Meanwhile in…").
- **`A20` shows only `20100`.** Its speech lines are numbered `21xxx` (`notes/scene_scripts.md`), and
  `21100–21101` sit in the row of the nonexistent film 21, so they never appear. Do not add them to
  `A20`'s page.
- **`A18`/`A18B` speech uses `19xxx`**, but the page comes from row 18 (`18100–18101`) for both.
- **`A27` is a real film**, not a text-only ending: `A27.SI` (with `.SM`/`.SN`/`.SR`) is in
  `REMOTE/BINARY/ANIM/`, like the other remote-only films. It has no speech; its four captions form its
  page, and the film follows.
- Film event tracks: every film has exactly one two-field event, `Fade (10, 10)` at 4 s (§4.3). No film
  carries an event that opens or closes a caption page, so in practice pages occur only before films.

## 3. Page layout

- **One page with all captions joined**, not one page per id. The strings are concatenated **with no
  separator**; the caption strings already end with a space where a sentence continues ("…Border
  Princes, " + "unnoticed by…"), so plain concatenation reads correctly. Do not insert spaces or line
  breaks.
- **Background:** solid black over the whole front-end window (the page covers the full client area,
  hiding the screen underneath). No bitmap, no palette effect.
- **Text:** white `(255, 255, 255)`, drawn transparently on the black, glue font slot **4**
  (`GLUE/SUBTEXT.FON`, `notes/fonts_glue.md`).
- **Box:** a 125-pixel margin on every side. For a `W × H` window the text box is `x ∈ [125, W − 125]`;
  on the 640 × 480 front end that is a **390-pixel wrap width** starting at x = 125.
- **Wrapping:** word wrap at white space to the box width; leading white space of the text is skipped;
  explicit line breaks in a string (none in the shipped captions) start a new line; an `ESC` character
  ends the text.
- **Alignment:** every line is **centred horizontally** in the box; the whole block is **centred
  vertically** between y = 125 and y = H − 125: `top = 125 + ((H − 250) − block_height) // 2`, where
  `block_height` is the wrapped line count × the font's line height (top of first line to bottom of last).
  Example: on 640 × 480, a block of height `h` starts at `125 + (230 − h) // 2`.
- 🟡 Whether a block taller than the box is clipped: no shipped caption page comes close (the longest,
  `A27`, is four sentences), so this never matters in practice.

## 4. Timing and input

### 4.1 Caption page

- The page appears when the film is opened. It stays up until **9.9 seconds after it appeared**, or until
  the player **presses the left mouse button with the cursor over the film area** (§4.2), or **presses
  Enter**, whichever comes first. The time spent loading the film counts toward the 9.9 s, so the page
  is visible for 9.9 s in total, not 9.9 s after loading. If loading alone took 9.9 s or longer, the film
  starts as soon as it is ready.
- The check is on the button/key **being down**, not on release, so pressing ends the page at once.
- **A click ends only the page**; the film then starts and plays normally (the press went to the page,
  so the film never sees it). 🟡 Enter: the key press may additionally reach the film once it starts and
  end the film early (§4.2). Recommended engine behaviour: let the input that dismisses the page be
  consumed by it, so neither the click nor Enter skips the film.
- With swapped mouse buttons (the Windows "left-handed" setting) the primary button is used.
- **No fade** on the page: it appears and disappears at once (black page → first film frame).

### 4.2 The film after the page

For completeness (these are the film's own rules, already partly in `notes/si_omni.md`):

- The film plays in a **640 × 272** area centred horizontally; vertically the film plus seven text lines
  of the subtitle font are centred together, `y = (H − (7 × line_height + 272)) // 2`; the two speech
  subtitle lines sit below the film. The "film area" of §4.1 is this rectangle.
- **Skipping the film:** Enter, or a left click (press **and** release) on the film area, ends it.
- **Natural end:** when the film's final event track (`AnimDone`) has counted down to 0 the film is
  finished and the game continues.
- Moving the mouse while the film runs postpones that automatic end (the waiting time after the stream
  ends restarts); with the delay of 0 used by every film this has no visible effect.

### 4.3 Film fades (not the page)

- `AnimDone` (one field, 98, 96 … 0 every 125 ms): each record sets the film's sound and music volume to
  the value (as a percentage) and darkens the film picture one step, so the picture and audio fade out
  together over the last 6.25 s.
- `Fade (10, 10)` at 4 s marks the film as "fade when stopped": if the player skips it after that point,
  the speech subtitles are cleared and the picture and sound fade out quickly (ten short steps) instead
  of cutting. Skipping in the first 4 s cuts immediately. Every shipped film has this event.
- The darkening touches only the film's own colours, not the first and last ten palette entries
  (the system colours).

### 4.4 Speech subtitle joining (related)

A speech event track with **six** fields (`A13030`, `A14010`) shows its line followed by the next id(s)
joined into one subtitle: the last field is the number of further ids (`1`, so `13030 + 13031`,
`14010 + 14011`). Five-field tracks show one id.

## 5. Test vectors

| Before | Event | Visible result |
|---|---|---|
| Boot sequence reaches the intro | film `A1` opened | black screen, white centred SUBTEXT text = `ANTXT 1100 + 1101 + 1102` joined, word-wrapped to 390 px, block centred vertically between y 125 and 355 |
| `A1` page up for 3.0 s | left mouse pressed over the film area | page disappears at once; `A1` starts from frame 0 and plays to the end |
| `A1` page up, no input | 9.9 s pass since the page appeared | page disappears; film starts |
| `A1` page up, film took 10.5 s to load | loading finishes | page disappears immediately, film starts (no further wait) |
| `BPMISSION15B` glue, objective test true | `iftrueplaymovie:A12b` | page = `ANTXT 12100` (same as `A12`); then `A12b` plays with speech subtitle `12510` |
| `EN4_SUBSCRIPT0` | `playmovie:A16b` | page = `16600 + 16601` (not `16100`); film `A16b` with speech `16510` |
| `SZMISSION5` | `playmovie:A16a` | page = `16100` |
| `SZMISSION2` | `playmovie:A13` | page = `13200`; `13100` appears later as a speech subtitle |
| `GMMISSION3`, test false | `iffalseplaymovie:A18B` | page = `18100 + 18101` (same as `A18`) |
| `LMISSION3` | `playmovie:A20` | page = `20100` only; `21100/21101` never shown |
| `LASTMISSION`, ending 2000 + `Z` | `iftrueplaymovie:A27` | page = `27100 + 27101 + 27102 + 27103`, then film `A27` |
| `REMISSION6` | `playmovie:A9` | no page; film starts at once |
| Player killed / fled | `DEATH01` / `DEATH02` | no page; film starts at once |
| `A27` playing, 2 s in | Enter | film cut immediately (before the 4 s fade marker) |
| `A27` playing, 10 s in | Enter | subtitles cleared, picture and sound fade quickly, then the game continues |

## 6. Open items

- 🟡 Whether the Enter press that dismisses a page also ends the film (input queue timing in the
  original). Recommended: no.
- 🟡 Text taller than the box (never happens with shipped data).
