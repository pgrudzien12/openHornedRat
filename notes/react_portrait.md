# Battle reactions: the leader-portrait pop-up, expressions, and the "on screen" rule (GitHub #174)

Public behavioural handoff. It extends `script_behaviours.md` §3.3 (`React N`: per-race text, speech, audience
markers and the per-code expression table) and corrects the "Selected-unit readout" paragraph of `game_rules.md`
"Battle HUD layout". Static research; the original was not run. Data facts (frame counts, sequences) were read from
the installed game.

## 1. Short answers

- **The portrait panel is a pop-up, not a selected-unit readout.** The 128×177 rectangle at (72, 0) of the command
  panel normally shows the **compass**. When a reaction is shown, it switches to the **reacting unit's** leader
  portrait for **25 ticks (2.5 s)**, then returns to the compass. Selecting a regiment does not show its portrait.
- **The expression is not a frame.** Expression `e` (0–4) selects a **talking animation**: a mouth sequence played
  once over the face, while the eyes blink on a loop. The base face is always frame 0 of the sheet.
- **One portrait at a time.** While a portrait is showing (the 25 ticks), later reactions still print their text and
  play their speech, but **do not** change or restart the portrait.
- **On screen** = the unit's position (front-rank centre) lies inside a map-aligned rectangle around what the camera
  sees, plus a margin. It is refreshed every tick and read once, at the moment the reaction runs. Hidden enemy
  units never count as on screen. An enemy reaction that fails the test is dropped (not deferred), and so are its
  text, speech and portrait together.
- The expression table `0 2 0 1 4 2 2 1 2 2 0 2 2 2 2 3 2 1 3 1 2` (codes 0–20) is **confirmed**.

## 2. Who shows a reaction (unchanged, restated)

For a reaction code `c` of a unit `U` (race row from `s_race`):

1. No text for (race, c) → nothing at all.
2. `U` belongs to the **enemy army** and the entry is marked **P** ("not for enemy units") → nothing.
3. `U` belongs to the enemy army, the entry is not marked **E** ("also off screen"), and `U` is **not on screen**
   (§5) → nothing.
4. Otherwise, all three together:
   - the text goes to the battle message window;
   - the portrait pop-up is offered (§3) with expression `table[c]`;
   - the speech cue plays, if the entry has one (non-positional; not restarted if it is already playing).

Player-army and allied units skip steps 2–3, so their reactions show whether or not they are on screen or
selected. Text and speech are never split. The portrait can be skipped on its own (§3).

## 3. The portrait pop-up

**State**: the panel shows either the **compass** (default) or the **portrait of one unit**. A **pop-up timer** is
idle, or counts the ticks left.

When a reaction is shown (step 4 above) with expression `e`:
1. If the pop-up timer is **running** (a portrait is already up), the portrait part is skipped. Text and speech
   still happen.
2. Otherwise the timer starts at **25 ticks**, and the panel switches to the reacting unit `U`:
   - if `U` has a **living leader model** and a leader portrait, draw that portrait. Its layers start the expression
     `e` sequences (§4);
   - if not (no leader, or the leader is dead), the panel still switches to `U`, but no face is drawn: background,
     ornament frame and a stand-in picture (🟡 which picture was not identified).
3. Each tick while the portrait is up, its animation layers advance one step.
4. When the timer runs out, the panel returns to the compass, and the timer becomes idle, so the next reaction can
   show a portrait.

The pop-up timer counts in the same per-tick loop as the battle. 🟡 Whether it also counts while the game is paused
was not traced.

Expression numbers ≥ 5 are ignored (no portrait change). The shipped table only uses 0–4, so this never happens
with shipped data.

The ornament frame around the portrait is chosen by the unit's look, as `game_rules.md` describes (default /
enemy / wizard-or-monster ICONS frames 181–188 / 189–196 / 197–204). Enemy units get their own portraits too, when
their reaction passes §2.

The game's **`ShowMessage`** opcode (0xC1, no shipped uses) does the same with expression 0 and no audience filter,
if the unit has a leader.

No other portrait changes exist in battle: nothing for wounds, rout, death or hiding beyond the "no living leader"
case above.

## 4. Portrait sheets and the expression sequences

A leader portrait sheet (`leaderportrait` → `.FOL/.BOP`, `sprite_names.md`) has **6, 7 or 8 frames**:

| Frames | Shipped sheets |
|---|---|
| 8 | all except those below (34 sheets: `CER1`, `CER2`, `ART1`, `BRIW`, `CARL`, `COMM`, `DWA2`–`DWA4`, `ELF1`, `GOB1`, `GOTR`, `MER1`, `MER2`, `ORC2`, `REIK`, `SCRI`, `BERN`, `BERI`, `HOLG`, `ENGR`, `AZGU`, `CELE`, `CARO`, `KEEL`, `HALB`, `UGLE`, `RAMO`, `GINF`, `AMBE`, `XBOW`, `KING`, `HAMM`, `IRON`) |
| 7 | `DWA1`, `ORC1`, `ORC3`, `SHA1` |
| 6 | `SKA1`, `SKA2`, `SKA3`, `SKA4`, `THAN`, `TREE` |

Frame 0 is the whole face, drawn first. Frame roles below are inferred from how the sequences use them: Frame 2 is the **eyes open** overlay, and the last frame is **eyes closed**.
The remaining frames (1, 3, 4, …) are **mouth** overlays, and frame 1 is the mouth at rest. The animation set depends
only on the frame count, so an engine can pick it from the sheet.

Each portrait has two animated overlay layers drawn over frame 0: the **eyes** layer and the **mouth** layer.
Notation: `f×n` = show frame `f` for `n` ticks; *loop* = restart the sequence; *hold* = keep the last frame.

**Eyes** (every expression; `X` = the eyes-closed frame, i.e. 7, 6 or 5):
- expressions 0 and 4: `2×2, X×2, 2×5, X×2, 2×11`, loop;
- expressions 1, 2, 3: `2×2, X×2, 2×6, X×2, 2×2, X×2, 2×9, X×2, 2×11`, loop.

**Mouth**:

| e | 8-frame sheets | 7-frame sheets | 6-frame sheets |
|---|---|---|---|
| 0 | `3×1, 5×3, 1×1`, hold | `3×1, 4×4, 1×1`, hold | `1×1, 3×4, 1×1`, hold |
| 1 | `5, 3, 6, 4, 1` (1 tick each), hold | `5×1, 3×1, 1×1, 4×4, 1×1`, hold | `4×1, 1×1, 3×4, 4×1, 1×1`, hold |
| 2 | `1, 4, 3, 6, 5, 3, 1` (1 tick each), hold | `3×1, 4×4, 5×1, 3×1, 1×1, 5×1, 1×1`, hold | `3×1, 1×1, 3×4, 1×1, 4×1, 3×4, 1×1`, hold |
| 3 | `1, 3, 5, 4, 6, 4, 5, 6, 3, 1, 5, 3, 1` (1 tick each), hold | `1, 3, 5, 4, 3, 4, 1, 5, 3, 5, 4, 3, 1` (1 tick each), hold | `1, 4, 1, 3, 4, 3, 1, 4, 3, 1, 4, 3, 1, 4, 3, 1` (1 tick each), hold |
| 4 | `3×1, 4×5, 1×1`, hold | `3×1, 4×5, 1×1`, hold | `1×1, 3×5, 1×1`, hold |

So 0 is a short word, 1–2 a phrase, 3 a long phrase and 4 a held shout. None is "neutral": the neutral face is the
mouth layer resting on frame 1 after its sequence ends (every sequence ends on 1). All sequences finish well inside
the 25-tick pop-up. The eyes keep blinking until the pop-up closes.

## 5. "On screen"

Each tick the game computes a **view rectangle** on the map, aligned with the map axes. It is the smallest box
holding the camera's ground position and the ground points under the top (far) corners of the 3D view, enlarged on
every side by a fixed margin (10 units of the 3D scene; 🟡 conversion to world units not checked; roughly 80 world
units if the scene uses the terrain's 1/8 scale). It uses the current camera, so rotation, tilt and zoom all
matter, but it is a coarse box, not a frustum test. It therefore also counts as on screen some ground just
outside the visible trapezoid.

At the end of each unit's tick the unit is marked **drawn** when:
- its position (the front-rank centre) is inside the view rectangle, **and**
- it is not hidden (`hidden:`) while in the enemy army (hidden friendly units still count),
- and it has not left the battle.

Otherwise it is marked **not drawn**. A reaction tests "drawn **and** not hidden" once, when it runs. Scripts run
early in the unit's tick, so the test sees the mark from the previous tick. A failing enemy reaction is dropped:
no text, no speech, no portrait, and no retry.

## 6. Test vectors

`T` = the 25-tick pop-up timer. "Panel" = what the portrait rectangle shows.

| Selected | Reacting unit | Code | View / timer before | Panel after | Text / speech |
|---|---|---|---|---|---|
| player Human regiment A (8-frame sheet) | A | 4 ("Retreat!") | T idle | A's portrait, mouth `3×1, 4×5, 1×1`, eyes blinking; T = 25 | 34103 + HumBtl 1 |
| player regiment B | player Human regiment A | 2 | T idle | **A's** portrait (not B's), expression 0 | 34102 + HumBtl 0 |
| nothing | player regiment A | 3 | T idle | A's portrait, expression 1 | shown |
| any | enemy Orc regiment E, on screen | 2 | T idle | E's portrait (`ORC1`/`ORC3` 7-frame or `ORC2` 8-frame), expression 0, enemy ornament | 34002 + OrcBtl 2 |
| any | enemy Orc E, off screen | 2 (no marker) | — | unchanged | nothing |
| any | enemy Human E, on or off screen | 1 (P) | — | unchanged | nothing |
| any | enemy Skaven E, off screen | 18 (E) | T idle | E's portrait (6-frame), expression 3 | 34303 + Hiln 0 |
| any | enemy Skaven E, on screen but hidden | 2 | — | unchanged | nothing |
| any | player regiment A, then player regiment C 5 ticks later | 4, then 17 | T idle | A's portrait for 25 ticks; C's reaction gives **no** portrait | both texts; both speeches (unless the first cue is still playing and is the same cue) |
| any | C again at tick 26 | 17 | T idle again (A's pop-up closed at tick 25 → compass) | C's portrait, expression 1 | shown |
| any | player regiment whose leader is dead | 4 | T idle | panel switches to that unit, no face (🟡 stand-in), T = 25 | shown |
| any | any unit, expression 5 or more (not in shipped data) | — | T idle | unchanged | text/speech per §2 |
| — | — | — | pop-up up, T reaches 0 | compass | — |

## 7. Corrections to earlier notes (applied)

- `game_rules.md` "Battle HUD layout", "Selected-unit readout": the rectangle is the compass by default and shows a
  **reacting** unit's portrait for 25 ticks. It is not tied to the selection.
- `script_behaviours.md` §3.3: "the unit's leader portrait takes the code's expression" now points here (pop-up,
  talking animation, one at a time).

## 8. Uncertainties

- 🟡 The stand-in picture for a unit without a living leader.
- 🟡 Whether the pop-up timer runs while the game is paused.
- 🟡 Margin of the view rectangle in world units (§5).
- 🟡 Clicking the portrait pop-up appears to act on the shown unit (select it / centre the camera); not traced in
  detail.
