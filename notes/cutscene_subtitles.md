# Cutscene speech subtitles

Public implementation report: how the original shows the speech subtitles **inside** a cutscene film,
driven by the film's speech event tracks. Companion reports: `notes/cutscene_narration.md` (the caption
page before the film, the film rectangle, skipping and fades), `notes/si_omni.md` (event track format),
`notes/scene_scripts.md` (speech lines per film), `notes/fonts_glue.md` (font slot 4).

Status: ✅ unless marked 🟡. Tracker: issue #41.

## 1. Shared model

- Below the film there are **two subtitle blocks** (an upper and a lower one). Each block shows **one
  speech line at a time** and is a small two-line "teleprompter": text is typed into its **bottom line**
  and the block scrolls up when the text wraps.
- A speech track is assigned to a block **when its first record arrives**: the first free block, upper
  before lower. It keeps that block until its last record, which clears and frees it. A track that
  finds both blocks busy is ignored until one frees (never happens in the shipped films, §4).
- Everything happens **on event records** (one every 125 ms); nothing animates between records.

Speech track record fields (`notes/si_omni.md`): `(text_id, speaker, first_tick, current_tick,
last_tick[, extra])`. Only `current_tick` changes from record to record.

## 2. Where (640 × 480 front end)

With `L` = the line height of glue font slot 4 (`SUBTEXT`, 22 px; 🟡 assuming no external leading):

| Rectangle | x | y | width | height |
|---|---|---|---|---|
| Film | 0 | `F = (480 − (7·L + 272)) // 2` = **27** | 640 | 272 |
| Upper subtitle block | 0 | `F + 272 + L` = **321** | 640 | `2·L` = 44 |
| Lower subtitle block | 0 | upper `y + 3·L` = **387** | 640 | 44 |

So there is one empty line between the film and the upper block, and one empty line between the blocks.
For another window size, `x = (W − 640) // 2` and `F = (H − (7·L + 272)) // 2`; the rest is relative.

- **Lines:** two per block, at block `y` and block `y + L` (line spacing = `L`). **Left aligned**,
  text starting **4 px** from the block's left edge.
- **Wrap width:** a line may hold text whose width `w` satisfies `4 + w < 636` (strict), i.e. less than
  632 px. Word wrap at white space (§3.3).
- **Overflow: scroll, no pages, no clipping.** Text starts on the **bottom** line (the top line is
  empty). When a word does not fit, the bottom line moves up to the top line, the previous top line is
  dropped, and typing continues on the bottom line. Only the last two lines of a long speech are ever
  visible.

## 3. Look and timing

### 3.1 Look

- Font: glue font slot **4** (`SUBTEXT`), the same as the caption page.
- **Colour by speaker field:** 2 → **red (255, 0, 0)**, 3 → **green (0, 255, 0)**, 4 → **blue
  (0, 0, 255)**. The speaker field only selects the colour, not the block or position. (Other values
  would give 0 black, 1 white, 5 yellow, 6 magenta, 7 cyan; only 2–4 occur.)
- **Background:** each block is solid black; the glyphs are drawn with an opaque black cell. No
  shadow or outline.
- **Text shown as is**, including the `Speaker:` prefix (`Wizard: Prepare to die, sewer fiend!`).

### 3.2 Timing (typewriter driven by `current_tick`)

For a record with `current_tick = c`:

| Record | Effect |
|---|---|
| first record (`c = first_tick`) | take a free block, load the text, show the block (empty) |
| `first_tick ≤ c < last_tick` | visible characters = `trunc(len × (c − first_tick) / (last_tick − first_tick − 1))`; type the new characters since the previous record |
| `c = last_tick` (the last record) | clear the block to black, hide it, free it |

- `len` is the full text length (joined text for six-field tracks, §4).
- The text is complete when `c = last_tick − 1`. The data then repeats `c = last_tick − 1` for about 15
  more records, so a finished line stays **about 2 s** (16 records) before the clearing record. The hold
  is whatever the track contains, not a fixed delay (`A1` `1030` holds only 8 records).
- The reveal is linear in `current_tick`, not in record time or film frames. Truncation, not rounding.

### 3.3 Word wrap while typing

Before a character is typed, the block measures the current bottom line plus the **whole word** that
starts at this character (up to the next white space). If that would not fit (§2), the space before the
word becomes the line break and the word starts on a new bottom line (the block scrolls). So a word
never starts on one line and jumps to the next half-typed; it is placed on the line where it fits
before its first letter appears. A space typed at the end of a line does not by itself cause a wrap.

## 4. Overlap and joining

- **Two tracks at once: they stack, not replace.** The new track takes the other block. In the shipped
  films overlaps happen when the next line starts during the previous one's 2-s hold (or, in `A1`
  `1020/1030`, while it is still typing). **At most two tracks are ever active at once**, so no line
  waits or is dropped.
- The block a line uses depends only on which block is free at its first record. Typical pattern: a
  line with no overlap uses the **upper** block; when lines overlap they alternate between upper and
  lower (`A1`: 1010 upper, 1020 upper, 1030 lower, 1040 upper, 1050 lower).
- **Six-field tracks** (`A13` 13030, `A14` 14010): the text is the strings `id … id + extra`
  concatenated with no separator (the first ends with a space), in **one block**, typed as one text with
  one `len`. Only one colour (the track's speaker) is used.

## 5. Skip, fade and film end

- **Skip with the fade marker set** (after 4 s, `notes/cutscene_narration.md` §4.3): both blocks are
  cleared to black **at once**, before the picture/sound fade starts.
- **Skip before the marker** or any stop: both blocks are hidden immediately and all blocks freed.
- **`AnimDone` fade and skip fade do not dim the subtitles**: the picture fade darkens only the film's
  own colours and leaves the reserved system colours alone, which is where the pure red/green/blue/black
  of the subtitles live. A subtitle still on screen when the film fades (e.g. the end of `A13` 13100)
  stays at full brightness until its clearing record or the film stop.
- Text-only tracks without a recording (`A9` 9010, `DEATH01` 30000, `DEATH02` 31000/31010) are shown
  exactly the same way.

## 6. Test vectors

`A1`, track `E1010` (`1010`, speaker 2, first 230, last 251, text length 36, denominator 20):

| Before | Record (time, `current_tick`) | Visible result |
|---|---|---|
| both blocks free | 28.625 s, 230 | upper block shown, empty (black) |
| upper, 0 chars | 28.750 s, 231 | red `W` (trunc(36·1/20) = 1) on the upper block's bottom line, x = 4 |
| | 30.000 s, 241 | red `Wizard: Prepare to ` (trunc(36·11/20) = trunc(19.8) = 19 chars, ending with the space) |
| | 31.125 s, 250 | full `Wizard: Prepare to die, sewer fiend!` (one line) |
| full text | 31.250 – 33.000 s, 250 (×15) | unchanged |
| full text | 33.125 s, 251 | upper block cleared and hidden, free |

`A1` overlap, tracks `1020` (speaker 3) and `1030` (speaker 4):

| Before | Record | Visible result |
|---|---|---|
| both free | 38.125 s, `1020` c = 306 | upper block taken (green, empty) |
| upper typing `1020` | 39.250 s, `1030` c = 315 | lower block taken (blue, empty); `1020` keeps typing in the upper block |
| both active | 42.000 s, `1020` c = 322 | upper block cleared; `1030` continues in the lower block |
| upper free, lower busy | 46.375 s, `1030` c = 365 | lower block cleared; both free |
| both free | 46.750 s, `1040` c = 375 | `1040` takes the **upper** block |

`A13`, six-field track `13030` (extra 1, speaker 2, first 125, last 467; text = `13030` (457 chars) +
`13031` (112 chars) = 569, denominator 341):

| Before | Record | Visible result |
|---|---|---|
| `13010` cleared at 9.625 s (upper free), `13020` active in the lower block until 16.625 s | 15.625 s, c = 125 | 13030 takes the **upper** block (red, empty) |
| | c = 200 | 125 characters typed (trunc(569·75/341) = 125); only the last two wrapped lines are visible, newest on the bottom line |
| | c = 466 (58.250 s) | all 569 characters typed; the last two lines show the end of `13031` |
| | c = 467 (60.250 s) | block cleared and freed |

Wrap: with 632 px usable and a 12-px average glyph (`SUBTEXT`), a line holds roughly 50 characters, so
`13030 + 13031` scrolls through about 11 lines.

## 7. Open items

- 🟡 `L` = 22 assumes the font reports no external leading (line height = cell height 22 px). If the
  engine's SUBTEXT line height differs, use it for both the film placement and the blocks.
