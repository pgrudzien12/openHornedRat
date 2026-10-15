# Storm of Shemtek: the storm sprite at the wizard

Public behavioural report for the Storm of Shemtek's storm sprite
[#262](https://github.com/pgrudzien12/openHornedRat/issues/262), under
[epic #259](https://github.com/pgrudzien12/openHornedRat/issues/259).

Gameplay (2D6+1 bolts, target choice, bolt flight, the 7-tick flash between bolts, channelling, cancellation) is
specified in `spell_channelled_effects.md` §1; the bolts' beams and flashes are drawn as in `spell_visuals.md` §2.2.
This report adds only the **storm sprite**: its artwork, position, animation and removal, in the style of
`spell_attached_visuals.md` and `spell_madness_visuals.md`. T is the successful launch tick, including its effect
update. One battle tick is 0.1 seconds. Frame numbers are zero-based indexes in the installed `SPELLS` assets;
distances and heights are in battle units. E_k is the tick in which bolt k ends (stopped, below ground or terminal
impact) and E_last the end tick of the last bolt, as in `spell_channelled_effects.md` §1.3.

## 1. Result

| Spell | Artwork | Placement | Timing |
|---|---|---|---|
| Storm of Shemtek (code 3) | SPELLS **391–400**: 391–394 a crackling ball that grows; 395–398 the full crackling storm; 399–400 the storm breaking up into loose sparks | **One** sprite per Storm, on the ground at the caster's **first figure** (first roster entry) **as it stood at the launch**; it does **not** follow | 391–394 once (wind-up, T…T+3); then **395–398 looping without a break** from T+4 through every bolt and every flash; 399–400 once after the last flash (E_last+7, E_last+8); gone at E_last+9 when the effect ends |

- **Nondirectional.** The same frame from every camera angle; no facing.
- **No per-bolt animation.** Releasing a bolt neither restarts nor changes the sprite: the 395–398 loop runs on
  through bolt launches, flights, impacts and flashes.
- No random start phase, no jitter, no fade.

### 1.1 Anchor and palette

| Frames | Dimensions | Anchor X/Y | Added bank | Effective colour map |
|---|---|---|---|---|
| 391–400 | 32 × 32 | 16, 32 (bottom centre) | 16 | 21 |

Anchor rule and colour-map decoding as in `spell_attached_visuals.md` §2.2: the frame's own map nibble (5) plus the
bank (16). A decoder that already resolves the full map number must not add the bank again. The first frame (391)
and the bank (16) are the game's first-frame and bank values for code 3; frames 395 and 399 are that first frame
+ 4 and + 8.

## 2. Placement

- At the launch the sprite is put at the **ground point of the caster's first figure** (the first entry of the
  caster's roster, the same figure the bolts start from, `spell_channelled_effects.md` §1.3). Its height is the
  **terrain height under that point** (+0); with the bottom-centre anchor the storm stands on the ground.
- The point is **fixed for the whole Storm**. Later stages keep it. The sprite does not follow the wizard if he
  moves, turns, is pushed, routs or loses the figure it was placed at. The bolts, however, always leave from the
  **current** first figure (§1.3 there), so a moved wizard fires from a point away from his storm sprite.
- One sprite per Storm, not per figure.

## 3. Animation and stages

One frame per tick, drawn before it advances (the shared sprite-animation model of `spell_attached_visuals.md`). Isolated
Storm (the normal case, see §6 for the exception):

| Tick | Frame | Gameplay at the same update (`spell_channelled_effects.md` §1.3) |
|---|---|---|
| T (launch) | 391 | value rolled, no bolt yet |
| T+1 | 392 | |
| T+2 | 393 | |
| T+3 | 394 | |
| T+4 | **395** | wind-up over: bolt 1 launched (W = 4); the loop starts at once, no blank tick |
| T+4+j, up to E_last+6 | `395 + (j mod 4)` | bolt flights, impacts, flashes, later bolt launches — none of them affects the frame |
| E_last+7 | **399** | the last flash has ended; the closing animation starts (replaces the loop frame in this update) |
| E_last+8 | **400** | |
| E_last+9 | **none** | the effect ends (end step: caster unfrozen, stand request, channelling over); sprite removed before drawing |

So the isolated Storm's wind-up is **4 ticks** and its closing animation **2 ticks**: the effect ends in tick
**E_last + 9**, the "🟡 E_last + 9" alternative of `spell_channelled_effects.md` §1.3.

## 4. Removal

Every end removes the sprite **in that same update**, with no fade or tail (no 399–400 except at the normal end):

| End | Sprite |
|---|---|
| normal end (after the last bolt's flash) | 399 at E_last+7, 400 at E_last+8, removed at E_last+9 |
| dispelled (dispel position = the aim point) | removed at once, whatever stage (also during the wind-up: then no bolt at all) |
| Ctrl+click cancel by the caster | removed at once |
| Wizard-class caster removed from the battle | removed at once |
| the Storm's recorded target unit removed (§1.5 there) | removed at once, with the whole Storm |
| caster in close combat, broken, fleeing or routing | **not** an end: the sprite keeps looping at its fixed point; the Storm goes on as in §1.4–1.5 there |
| caster loses figures (but not the unit) | not an end; the sprite stays where it was put |
| failed cast | no sprite |
| a second Storm by the same or another wizard | see §6 (overlap) |

## 5. Frames 391–400 — all used; 399–400 are the Storm's closing

Frames 391–400 are the Storm's own sprite: 391–394 the wind-up, 395–398 the loop, **399–400 the closing
animation** after the last bolt. Nothing else selects them. The next art, 401–432, is the developer (Shift)
variant of the Lightning bolt (`spell_visuals.md` §3), and 433–439 the Lightning-family flash.

## 6. 🟡 Overlapping spell effects — original-game comparison still needed

The sequence above is not universal in the original. Call a running spell effect *leading* if, at the moment it was
cast, no leading effect was running (so the first effect cast on an otherwise quiet battlefield is leading; one
cast while it still runs is not; once the leading effect ends, the next cast is leading again).

- A Storm that is **not leading** shows **no storm sprite at all**. Its wind-up is skipped (bolt 1 leaves in tick T,
  W = 0) and its closing lasts one tick (the effect ends at **E_last + 8**). Its bolts, beams and flashes are normal.
  This is the "W = 0, 1-tick close" behaviour reported in `spell_channelled_effects.md` §1.3.
- A non-leading Storm cast while the **leading effect is itself a Storm** disturbs that Storm's sprite: the leading
  Storm's sprite jumps to the new caster's first figure and plays 391–394 there once, then disappears; it shows again
  (399–400, at that new point) only for the leading Storm's own closing, or for the closing of the non-leading Storm
  if it ends first while the leading one still runs. While the leading Storm is still in its wind-up, the new 391–394
  also restarts that wind-up (its bolt 1 is delayed accordingly).
- A non-leading Storm cast while the leading effect is any other spell changes nothing visible.

None of these cases has been observed in a running original-game scene. **Engine baseline: every Storm behaves as the
isolated Storm of §3** (own sprite at its own caster, W = 4, 2-tick close). Do not reproduce the overlap artefacts as
the normal spell animation; keep them, if at all, behind an explicit compatibility option.

## 7. Test vectors

Common: isolated Storm (no other spell effect running); caster W's first figure F at (100, 200), terrain height 12
there; aim and bolt geometry as in `spell_channelled_effects.md` §1.6 (every bolt N = 21, terminal impact 20 ticks
after its launch). Expected state after the tick's effect update, before rendering.

| Before | Action | After |
|---|---|---|
| — | Storm succeeds at T, value 2 (3 bolts) | One sprite, frame 391, at (100, 200), height 12 (bottom-centre anchor) |
| frame 391 at T | updates T+1, T+2, T+3 | 392, 393, 394; no bolt yet |
| frame 394 at T+3 | update T+4 | bolt 1 launched; sprite frame **395**, same point |
| loop running | updates T+5 … T+8 | 396, 397, 398, 395 |
| bolt 1 ends at T+24, flash T+25…T+30 | update T+31 (bolt 2 launched) | sprite frame `395 + (27 mod 4)` = 398: no restart at the release |
| W walks to (160, 200) during T+40 | update T+41 | sprite still at (100, 200), height 12; bolt 3 (launched T+58) leaves from (160, 200) |
| bolt 3 ends at E_last = T+78; last flash T+79…T+84 | update T+84 | loop frame `395 + (80 mod 4)` = 395 |
| — | update T+85 | **399** |
| — | update T+86 | **400** |
| — | update T+87 | no sprite; effect over, W unfrozen and standing |
| wind-up showing 392 at T+1 | dispel before the T+2 update | no sprite from T+2; no bolt is ever launched |
| loop showing 397 during bolt 2's flight | Ctrl+click cancel | sprite, bolt, beam segments gone in that update; no 399–400 |
| bolt 1 destroys the recorded target, unit removed at T+29 | update T+29 | Storm cancelled: sprite removed, no closing |
| W charged into melee at T+50 | updates T+50 … | sprite loops on at (100, 200) |
| a Fireball (another wizard) still running when W casts the Storm | Storm cast (🟡 §6) | original: no storm sprite, bolt 1 at T, end at E_last+8; engine baseline: as the isolated rows above |

## 8. Differences from the current public text and engine model

Public text (`spell_visuals.md` §2.3, summary-table row, §3 notes):

- "plays 395–398 **as each bolt is released**" → wrong: 395–398 **loop continuously** from the end of the wind-up
  (T+4) to the end of the last flash; bolt releases do not restart or trigger it.
- "391–394 once when the spell starts" → confirmed (T…T+3), and bolt 1 leaves on the tick the loop starts (T+4).
- Frames **399–400** were unaccounted for → they are the closing animation (E_last+7, E_last+8).
- "at the wizard's leader figure" → at the caster's **first figure** (first roster entry), **fixed at its launch
  position**; it does not follow the wizard.
- Colour bank +16 confirmed; effective map 21; anchor 16, 32 (bottom centre); height = ground.
- `spell_channelled_effects.md` §1.3: the wind-up W = 4 and the effect end E_last + 9 are the isolated-cast
  behaviour; W = 0 / end E_last + 8 is the non-leading overlap case of §6. The engine suggestion there (W = 4,
  **1**-tick close) should become W = 4 and a **2**-tick close, so the 399–400 closing is shown.

Current engine (`whshr/frontend/spell_visuals.py`, `STORM_FORMING = (391, 4)`, `STORM_RELEASE = (395, 4)`, provisional):

| | Engine now | After this report |
|---|---|---|
| wind-up | 391–394 once at the Storm's first effect tick | same (T…T+3) |
| between the wind-up and the first release | nothing, if the wind-up ends before bolt 1 leaves | the loop starts at T+4, the tick bolt 1 leaves |
| per bolt | one 395–398 run started when each bolt leaves, then nothing | no per-bolt run |
| between bolts (flight and flash) | nothing after the 4-tick run | 395–398 looping without a break |
| end | nothing | 399, 400, then removal at the effect end (E_last+9) |
| position | the caster's **current** first figure at each run's start | the first figure's ground point **at the launch**, fixed for the whole Storm |
| height | 0 above ground (same) | ground (+0) |
| a new run while one is playing | replaces it | not applicable (one continuous sprite) |
| cancellation / dispel / caster or target removed | an already started run plays to its end | removed in that update |
| overlapping Storms | each has its own runs | baseline: each its own sprite (original artefacts §6 not reproduced) |

## 🟡 Open items

- No original-game screen capture was made. A comparison should confirm the sprite's apparent size and position
  at the wizard, the continuous 395–398 loop through bolts and flashes, and the 399–400 closing.
- The overlap behaviour of §6 (no sprite, W = 0, 1-tick close; disturbed sprite of an earlier Storm) is derived
  without a running-scene check; reproduce it with two wizards casting Storms (and a Storm cast while another spell
  runs) before deciding whether any compatibility option is wanted.
