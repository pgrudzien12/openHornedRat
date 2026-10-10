# Re-forming while the unit moves, orders during a re-form, and the post-pursuit "Re-group!"

Clean-room behavioural handoff for the implementer. It answers how a re-forming regiment's figures move while the
regiment itself moves, turns or receives orders, how long a re-form lasts, and what the "Re-group!" re-form after a
pursuit looks like. Static research; the original was not run. Read with:

- `game_rules.md` "Formations", "Models chase the unit, they are not carried by it", "Formation changes: how the
  figures re-sort themselves", "Turning, wheeling and reversing", "Figure animation", "Player orders and the command
  panel", "Pursuit";
- `movement_formation.md` Part A §1–§4 (move/turn/charge opcodes, the re-forming refusal of `MoveToTarget`) and
  Part B §1, §4, §9 (`ReformToScriptRanks`, `Rally`, the two re-form modes, event 0x34);
- `pursuit_map_edge.md` §4 (what ends a pursuit; event 0x10 → `React 17`, script 163).

Names used below: **re-forming** = the unit's figures are walking to newly assigned slots. It has two modes:
**shuffle mode** (the flat `s_rlmv / 8` mover, used by every ordinary re-form) and **walk-back mode** (the ordinary
rank-dependent catch-up walk, used only by the re-form that `Rally` starts; `movement_formation.md` Part B §0 calls it
"re-form by walking"). A script waiting with `WaitWhileUnitFlags 8` waits for either mode; `0x4008` names both.

## 1. Short answers

1. **While re-forming, the figures are carried by the unit.** Normally a unit's translation leaves every figure's
   world position unchanged and the figures catch up by walking (`game_rules.md` "Models chase the unit"). While the
   unit is re-forming — in **either** mode — that compensation is switched off: every figure moves rigidly with the
   unit, and the re-form mover only adds the figure's own step towards its slot, measured relative to the unit. So
   the re-form's duration does not depend on how fast or how far the unit travels. Your "add the anchor's
   translation first, then step" guess is **correct**.
   The 1-unit cap is **not** a general speed cap: it applies only inside the last 6 units of the approach (see §3).
   Capping every step at 1.0 is what makes your cavalry re-form crawl (s_rlmv 20 should shuffle at 2.5 units per
   tick).
2. **Figure heading** = the bearing of the figure's own step vector, which is computed from the figure's
   position **relative to its slot** (no unit-velocity term). It is set instantly at each re-aim. A figure whose slot
   is behind it therefore faces backwards, even while it is carried forward. Shuffle-mode arrival snaps the heading
   to the unit's facing; walk-back arrival leaves the last heading. The drawn direction then slews ≤ 22.5° per tick
   towards the heading or the unit facing, depending on the animation (`game_rules.md` "Drawn facing is its own
   slew"). In the original this backwards walk rarely shows, because a re-forming unit seldom translates (point 3).
3. **Move orders do not start while re-forming.** A player **Move**, **Face point** or **Charge** order is kept as
   the unit's pending order and retried every tick until the re-form ends, then carried out. A player **Attack**
   order is accepted at once, but the approach script it starts (158) first **waits until the re-form is over**,
   then moves. A script's `MoveToTarget` is refused while re-forming, and the charge-reach test is false while
   re-forming. The re-form is **never cancelled** by an order. Your "attack runs alongside the re-form at half speed"
   is **wrong** for this case: the unit stands until its figures have settled.
4. **Pursuit:** the anchor cannot outrun its figures by much. With the public walk rule, the steady lag behind a
   pursuing anchor is about `10 × s_rlmv / F` units: about 6–17 units for cavalry, not 40–130 (🟡 computed, not
   observed). **Re-group** halts the unit and lays the new block out **around the anchor, at its current position
   and facing**. The anchor does not move to the figures. The figures walk back in **walk-back mode** (fast,
   rank-dependent, no halving), not the flat shuffle.
5. **Ranks at Re-group** = the unit's script rank count `s_rnks` (clamped), set by `Rally`. The BF003 player cavalry
   has `s_rnks` 3, so 3 is right. The **2** you saw before comes from **`ReformBlock`** (opcode 0x45), which every
   attack approach runs right after `MoveToTarget`: `ranks = trunc(N / (1.15 × √N))`, i.e. 2 for 10 models (§7).
6. **Turning while re-forming:** an ordinary move's wheel and halted turn, a charge's turn and a turn order are all
   **suspended** while re-forming (the unit keeps translating along its current facing). A pursuit keeps turning,
   but the formation is not rotated with it until the re-form is over. Outside a re-form, every gradual-turn tick
   rotates the whole set of slots with the facing (§5).
7. **No time or distance limit.** A re-form ends when every figure has settled. The other ways it ends are
   engagement in close combat and the script opcode `SnapModelsToFormation`. Any new layout (halt, rank change,
   instant turn, `ReformBlock`, `Rally`) restarts it with new slots. Orders never cancel it (§8).

## 2. Shared state: two re-form modes, carried figures

| | not re-forming | re-forming, shuffle mode | re-forming, walk-back mode (`Rally` only) |
|---|---|---|---|
| figure mover | catch-up walk (`game_rules.md`, rank factor `F`, ramp-up) | flat `s_rlmv / 8` step, deceleration, place swaps | catch-up walk |
| unit translation moves the figures? | **no** (world positions unchanged) | **yes** (carried) | **yes** (carried) |
| unit speed this tick | normal | **halved** | normal |
| arrival heading | unchanged | **snapped to the unit's facing** | unchanged |
| figures that arrive | keep walking while the unit moves | at rest until re-aimed | at rest (stop being stepped) |
| ends | — | first tick on which no figure stepped and none is pausing → event 0x34 | first tick on which every figure is at rest → both re-form states clear, event 0x34 |

Three further exceptions keep the figures carried whatever the state: **artillery**, **rolling stock** and
**building** units, and any unit while it holds the one-tick **contact latch** (touching an enemy, engagement
pending; `game_rules.md` "What triggers engagement").

**Order within a tick** (`movement_formation.md` §1.2): speed → script → formation update (the re-form layout, the
figure movers, and the halving of the speed when in shuffle mode) → the movement handler (translation, carrying the
figures if re-forming) → figure animation. The figure step and the carry are therefore both applied in the same tick
and simply add up.

## 3. The shuffle-mode mover in detail (corrects the 1-unit cap)

Per figure, per tick, positions relative to the unit:

1. A figure in its timed pause (`ResetModelAnimations`, charge start stagger) counts down and does not step. It still
   counts as "not settled". The countdown runs for **every** figure, also one at rest or in a melee unit, before
   step 2 (`bf003_playtest_fireball_grid_pursuit.md` §4).
2. A figure that is at rest is skipped.
3. **Re-aim** happens on the figure's first step and whenever a countdown runs out. The countdown is set to
   `trunc(d) div 2` at each re-aim and decreased by `s_rlmv` every tick. At a re-aim, the integer offset to the slot
   is computed (the figure's position is rounded, a fraction of exactly one half rounding down). If it is zero, the
   figure **arrives**: it stops, its heading is set to the unit's facing, and it is at rest. Otherwise:
   - heading := bearing to the slot;
   - step := `s_rlmv / 8` world units along that heading (per axis: sin/cos of the heading × `s_rlmv / 8`);
   - **if `d < 6`** (d = truncated distance to the slot): step := step / `(7 − d)`, and then each axis component is
     capped at **+1 world unit**. 🟡 The original caps only components that point in the positive axis direction.
     An engine may cap both signs; the difference shows only for `s_rlmv > 16` inside the last 6 units.
4. Before stepping, the place-swap test against settled comrades (`game_rules.md` "Formation changes" §3).
5. Position += step.

There is **no cap outside the last 6 units**. The step is the same for every rank.

Computed settle times (from the rules above, one figure on a straight line; ±1 tick):

| `s_rlmv` | distance to slot | ticks to settle |
|---|---|---|
| 8 | 12 / 30 / 100 | 27 / 45 / 115 |
| 11 | 12 / 30 / 100 | 20 / 33 / 84 |
| 20 | 12 / 30 / 100 | 11 / 19 / 47 |

With your global 1.0 cap, an `s_rlmv` 20 figure needs about 100+ ticks for 100 units. That matches the ~130-tick
re-form you observed.

## 4. Orders and script moves during a re-form

**Player orders.** The order gate of `game_rules.md` "Player orders" comes first: while charging, in melee, broken,
pursuing or braced, move/attack/turn/rank/charge/fire orders are dropped. After it, a re-form (either mode) changes
only these orders:

| Order | Not re-forming | Re-forming |
|---|---|---|
| Move (1) | the move starts | **held as the pending order**, retried every tick; first time only: order reply `React 13`. Applied once the re-form ends; the script is then restarted as for any applied order |
| Face point (0x0B) | the turn starts | held and retried the same way (`React 13` once) |
| Charge (0x15) | event 0x06 → charge script 106 | held and retried the same way (`React 13` once) |
| Attack (3) | event 0x04 → approach script 158 | **accepted at once**, plus `React 13`. Script 158 starts with `WaitWhileUnitFlags 0x4008`, so the unit does not move until the re-form is over |
| Ranks up/down (0x0F/0x10) | re-form | accepted: a new layout, so the re-form restarts with the new shape |
| Halt (0x19) | halt and re-form | accepted: a new layout around the current position |

A held order is replaced by any later order. Player orders are checked at the start of every tick, whatever script
the unit is running, so an order given during script 163 (the Re-group script) is not lost.

**Script moves.** `MoveToTarget`, `CircleAroundTarget` and the move order's goto are refused while re-forming
(`movement_formation.md` §3.1, §3.8). `IfTargetInChargeReach` is false while re-forming. Every library approach
(105, 158, 159) waits with `WaitWhileUnitFlags 0x4008` before `MoveToTarget`. `ChargeTarget` and `StartPursuit`
themselves do not test re-forming. The library reaches them only after a reach test, or (pursuit) right after
`ReformToScriptRanks`.

**When a re-forming unit does translate** in the original:
- **every attack approach**: `MoveToTarget` (which may also snap 90°/180°, queueing a re-form) followed at once by
  `ReformBlock` (§7). The unit sets off at half speed while its figures shuffle into the new block, carried along;
- **pursuit start** (script 164): `ReformToScriptRanks`, then `StartPursuit`. The pursuit runs at half speed until
  the figures have settled;
- a scripted re-form (`ReformToScriptRanks`, `SetRanks`, a rank order) while a move is under way, and the re-form a
  halted turn or instant turn queues during a move.

In each case the figures are carried, so the re-form ends after the times of §3, wherever the unit has got to.

## 5. Turning while re-forming

| Movement | Turning while re-forming |
|---|---|
| ordinary move, wheel (turn 7.7°–45°) | **suspended**: the unit keeps translating (at half speed) along its current facing; the wheel resumes after the re-form |
| ordinary move, halted turn (> 45° owed) | **suspended, and the unit does not move at all** that tick (no translation) |
| turn order (`TurnToFaceTarget`, face point) | suspended: the tick is skipped (`movement_formation.md` §3.3) |
| charge | turning suspended; the charge keeps translating along its current facing; its distance budget runs as usual |
| pursuit | **keeps turning** (re-aim once per segment, `pursuit_map_edge.md`), but without the pivot shift and without rotating the slots |

**Outside a re-form**, each tick of a gradual turn re-derives every figure's slot from its rank and file at the new
facing, shifts the anchor about the inner front corner and compensates the figures' positions for that shift.
The slots therefore sweep with the facing, and the figures follow with the catch-up walk. Your engine's
"re-aim each update sweeps the outer slots sideways" is the original's behaviour **outside** a re-form. **During** a
re-form the facing is frozen for everything except a pursuit. In a pursuit the slots stay where the layout put them
(relative to the unit, in world axes) until the re-form is over.

## 6. Pursuit lag and the Re-group re-form

**Lag.** A pursuer that is not re-forming moves its anchor at the pursuit step (`game_rules.md` R39: at most
`1.5 × s_rlmv / 16` units per tick). Its figures use the catch-up walk with no broken-unit exemption: speed counter
`≤ min(distance, s_rlmv)`, step per counter unit `F × 2.4 / 256`. The figures keep up when
`min(d, s_rlmv) × F × 2.4 / 256 = 1.5 × s_rlmv / 16`, i.e. at a steady lag of

```
d ≈ 10 × s_rlmv / F      (F = rank factor of "Models chase the unit"; front rank 3-rank block F 28–34, rear F 12–18)
```

For BF003 cavalry (`s_rlmv` 20, 3 ranks): about 6–7 units for the front rank and 11–17 for the rear. 🟡 Steady
state, computed from the public rules (re-aim granularity adds a little). The original has no speed cap or wait tied
to figure lag. It needs none, because the rear rank's top speed (`0.1125 × s_rlmv`) exceeds the pursuit step
(`0.094 × s_rlmv`). A lag of 40–130 units points at the engine's catch-up walk or pursuit speed, not at a missing
rule.

**Re-group** (event 0x10 → `React 17` → script 163, `pursuit_map_edge.md` §4):

| Tick | What happens |
|---|---|
| T | event 0x10 handled: "Re-group!", switch to 163 |
| T+1 | `Rally`: pursuing/charging/braced states cleared, **halted** (destination cleared), timed pauses cancelled, ranks := clamp(`s_rnks`), block laid out **around the anchor at its current position and facing**, nearest-slot assignment (leader to the front-rank centre); **walk-back mode** |
| T+2… | figures walk to their slots with the catch-up walk (rank-dependent, ramp-up); the halted unit does not move; the unit's speed is not halved |
| T+k | last figure at rest → re-form over, event 0x34 |
| T+k+1 | 163: `ReformToScriptRanks` re-lays the same block (figures already on their slots); in shuffle mode each figure's first re-aim finds a zero offset → its heading snaps to the unit facing. Then `Restart`: a player unit returns to its main script and waits for orders |

Because walk-back arrival does not snap the heading, the final `ReformToScriptRanks` is what turns the figures to face
front. If an Attack order arrives during T+1…T+k, script 158 replaces 163 and waits for the re-form to finish. The
figures then keep their last walking headings until the approach's own `ReformBlock` re-form snaps them.

## 7. `ReformBlock` (0x45, 1 word; library 105, 158, 159; 13 mission uses)

With `N` = current model count (nothing happens when `N = 0`):

```
requested ranks = trunc(N / (1.15 × √N))
```

It then goes through the same check and clamp as a rank order: refused while fleeing, held or charging; clamped to
`[min, N div min]`, `min = max(1, trunc(0.75 × √N))`. The rank count is stored and a re-form is **queued**, i.e. laid
out at this tick's formation update (no layout while the unit has a grid, `movement_formation.md` Part B §1). The
selected-unit panel is refreshed. The condition is untouched. It does not stop a move.

| N | 1 | 4 | 6 | 8 | 10 | 12 | 16 | 18 | 20 | 24 | 25 | 28 | 32 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ranks | 1 | 1 | 2 | 2 | **2** | 3 | 3 | 3 | 3 | 4 | 4 | 4 | 4 |

A block slightly wider than deep. So a 10-model unit attacks in 2 ranks and returns to its script ranks
(`ReformToScriptRanks`/`Rally`) after the fight. BF003's player cavalry (`s_side` …,12,12,3 in its army file:
`s_rnks` 3) goes 2 → 3 at Re-group, as you saw.

## 8. What ends or restarts a re-form

- **Settling** (§2 table): the only normal end. No time limit, no distance limit, no snapping.
- **Engagement**: when the unit engages in close combat, re-forming ends (with the charging state), and the
  figures go into the close-combat placement.
- **`SnapModelsToFormation`** (0x67, missions only): figures placed on their slots, facing the unit's facing,
  re-forming and any queued re-form cleared.
- **Restart with new slots**: any new layout — halt-and-re-form (including the Halt order and arrival at the end of
  a move), rank orders, `ReformToScriptRanks`, `ReformBlock`, `SetRanks`, instant turns, `Rally`. The halt also
  cancels timed pauses.
- **Not** ended by: player orders (held, §4), the unit moving, the unit's target moving, or a charge starting.

## 9. Differences from the current engine

| Engine now | Original |
|---|---|
| shuffle step `min(s_rlmv/8, 1.0, d)` | `s_rlmv / 8` with no cap; only inside `d < 6`: divide by `7 − d`, then cap each axis component at 1 |
| anchor translation added to figures while re-forming | same (carried) — also in walk-back mode, and always for artillery, rolling stock and buildings |
| attack/charge/move order accepted during a re-form, anchor at half speed | Move/Face/Charge held until the re-form ends; Attack accepted but the approach waits (`WaitWhileUnitFlags 0x4008`) |
| Re-group re-forms with the flat shuffle | `Rally` uses walk-back mode (catch-up walk, no halving), then a final `ReformToScriptRanks` |
| re-aim / turn every update while re-forming | wheel, halted turn, charge turn and turn order suspended while re-forming; pursuit turns but slots are not rotated |
| pursuit lag 40–130 units | steady lag ≈ `10 × s_rlmv / F` (≤ ~17 units for cavalry) |
| sprite slews 32/512 per tick towards the step direction | same slew (public), towards the heading = bearing to the slot relative to the unit; shuffle arrival snaps the heading to the unit facing |

## 10. Test vectors

| Before | Action | After |
|---|---|---|
| block re-forming (shuffle mode), anchor moving +X at 1.0/tick (already halved), figure at unit-relative (0, −30), slot (0, 0), `s_rlmv` 20 | 1 tick | figure world position += (1.0, 0) (carried) + (0, +2.5) (shuffle step); heading = 0 (+Y, towards the slot) |
| same, not re-forming (catch-up walk) | 1 tick | figure world position changes only by its own walk step; unit-relative position −= (1.0, 0) |
| figure 5 units from its slot (`d` = 5), `s_rlmv` 20, slot in +Y | re-aim | step = 2.5 / 2 = 1.25 → capped to 1.0 |
| figure 5 units from its slot in −Y, `s_rlmv` 20 | re-aim | step −1.25 (🟡 not capped in the original; an engine may cap to −1.0) |
| figure 10 units from its slot, `s_rlmv` 20 | re-aim | step 2.5 (no cap, no deceleration) |
| figure 3 units from its slot, `s_rlmv` 8 | re-aim | step 1.0 / 4 = 0.25 |
| figure exactly on its slot (rounded offset 0) | re-aim | arrives: at rest, heading := unit facing |
| player unit in Re-group walk-back re-form | player Move to P | `React 13`; order held; unit stays halted; on the first tick after the re-form ends the move to P starts, script restarted |
| same | player Attack on unit U | `React 13`; event 0x04; next tick script 158 starts and waits; after the re-form: `React 1`, `MoveToTarget` U, `ReformBlock` |
| same | player Charge | `React 13`; held; after the re-form: event 0x06, charge straight ahead (script 106) |
| same | player Ranks up | accepted: new layout with ranks + 1; the re-form restarts with the new slots, still in walk-back mode (🟡 §12) |
| unit moving (ordinary move), re-forming, needs a 30° wheel | movement tick | no turn; translates at half speed along its current facing |
| unit moving, re-forming, owes a 60° turn (halted turn) | movement tick | no turn, no translation |
| pursuer re-forming after 164 | segment tick, target 40° off | turns (pursuit rate); slots not rotated; anchor not pivot-shifted; pursuit step halved |
| 10-model unit | `ReformBlock` | ranks 2 (frontage 5); re-form queued |
| 10-model unit, `s_rnks` 3 | `Rally` | ranks 3 (frontage 4: rows 4, 3, 3), block around the anchor |
| 12-model unit | `ReformBlock` | 12 / (1.15 × 3.464) = 3.01 → 3 |
| unit re-forming, enemy contact engages it | engagement | re-forming ends; figures placed for close combat |

## 11. Corrections to `game_rules.md` (applied)

- "Formation changes" §2: the one-unit cap applies only inside the last 6 units, after the deceleration divide. It is
  not a general cap.
- "Models chase the unit": while re-forming (either mode), for artillery, rolling stock and buildings, and during the
  contact latch, the figures **are** carried by the unit's translation.

## 12. Uncertainties

- 🟡 The positive-only per-axis cap (§3) is the original's literal behaviour; it looks unintended.
- 🟡 Whether a rank order or `Halt` given during walk-back mode keeps walk-back mode: the new layout itself clears it
  only for war machines/wagons. A halt does not touch it, and a rank order does not either. So the walk-back mode
  probably persists until the re-form ends. Treat it as persisting.
- 🟡 Drawn direction for the "mark time" animation (action 2), which shuffling figures play: the public slew rule
  names stand/ready/shoot (unit facing) and walk/fight (own heading). Mark time was not classified.
- 🟡 The pursuit lag of §6 is a steady-state calculation, not a trace.
