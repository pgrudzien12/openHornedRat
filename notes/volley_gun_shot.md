# Volley Gun: one shot order, three projectiles (GitHub #342)

Public implementation report. It resolves the 🟡 left in `machine_figure_animation.md` §2.2: what the shooting side does
with the two extra event posts of the Volley Gun's shoot program.

Companion reports, cited rather than repeated:

- `machine_figure_animation.md` §0.3 and §2.1–§2.2 (the shoot programs, the lock-out).
- `script_animation_sound.md` §0.3 (the unit's animation request: event code, divisor, countdown).
- `script_shooting.md` §1 (`FireAtTarget`), §1.3 and the war-machine walk-through.
- `ranged_combat_handoff.md` (projectile flight and impacts) and `game_rules.md` §8.3 (weapon table, misfire, scatter).

**Corrections made by this report:**

- `machine_figure_animation.md` §2.2: the 🟡 is resolved. **All three posts launch a projectile** (§1).
- `machine_figure_animation.md` §2.1 (and §2.2 by reference): the muzzle puff is placed 24 units ahead of the **unit's
  position** along the unit facing, not ahead of the machine figure (§4). Corrected there.

## 0. Shared state first

1. **The extra post is an ordinary fire event without a figure.** The Volley Gun's extra post sends the unit's
   **current animation-request event code** (34 for an ordinary shot, 35 for the 90 %-range fallback) to its own unit,
   with source "no figure" (−1). It does not look at or change the countdown or the divisor, and it needs no pending
   request. The program's third puff is the ordinary event step (countdown 1 → 0, event posted with the machine
   figure's index as source).
2. **Each event 34 is one `FireAtTarget`.** The library's event-34 handler (111) runs `FireAtTarget` for every event
   34 it receives, whatever its source (`script_shooting.md` §1). Each post is dispatched at the unit's next script
   step (pre-emptive dispatch). So a Volley Gun shot produces **three `FireAtTarget` launches**, one tick after each
   of the three puffs.
3. **`FireAtTarget` checks nothing about the shooter's state** (`script_shooting.md` §1.1: no range, arc, reload, line,
   visibility or target-state test). Every launch is a complete artillery launch of its own: reload re-stamp, misfire
   roll, scatter, projectile.
4. **Only the figure-referenced post gets the after-shot pause.** After `FireAtTarget`, handler 111 tests "event
   source is −1". The two extra posts skip the rest. For the third (machine-figure) post, an intact Artillery machine
   then does `SetWait 10; Wait; React 12; ReformToScriptRanks`, exactly as for a cannon.
5. **During the shot the request still names event 34.** The volley is ordered with countdown 1 (the war-machine
   `PlayLeaderAnimation 7 34`, `script_shooting.md`), and the countdown only reaches 0 at the third puff. So the
   ordering script's `IfAnimationDone 7` stays false until then and does not clear the request early. Both extra
   posts therefore carry 34 (or 35).

## 1. Q1 — what each post launches

| Post | Source | Launch start | Aim | Weapon values |
|---|---|---|---|---|
| 1st puff (extra) | none (−1) | the **unit position** (`script_shooting.md`: "a launch with no model starts at the unit centre") | the current target's centre **at launch time**, or the target point when aiming at a point (§1.1 of `script_shooting.md`), with **its own scatter** | the Volley Gun row (code 7) of `game_rules.md` §8.3: blast 24, wound die D4, flight 9 ticks, building S as S. **S 5 if the target is within 287 units at launch, else S 4**, decided per launch |
| 2nd puff (extra) | none (−1) | the unit position | same rule, re-read at its own launch tick | same, per launch |
| 3rd puff (event step) | the machine figure | unit position plus the machine figure's offset | same | same |

There is no per-shot change other than the S-by-distance rule, which is evaluated for each launch. Each launch is
credited to the Volley Gun unit (ordinary missile credit, `casualty_bookkeeping.md`).

## 2. Q2 — bookkeeping and gating per launch

| Item | Effect of each of the three launches |
|---|---|
| ammunition | none exists (`ranged_combat_handoff.md`) |
| reload stamp | **re-stamped at every launch**, including one that misfires. The reload interval therefore effectively starts at the **third** launch |
| volley countdown / divisor | untouched by the extra posts. The third post's event step takes it from 1 to 0 |
| kill credit | the unit, per projectile |
| needs a free projectile record | yes, each launch. With none free the launch silently fails |
| target gone (no current target, no target point) | that launch launches **nothing** (no misfire roll, no stamp) |
| target moved, out of range or arc | still launched at the target's centre at launch time, with the larger scatter of the larger distance |
| machine destroyed, crew below 2, unit in melee, broken or held | **not tested**. A post that is dispatched still launches. 🟡 Whether a machine destroyed by the first shot's misfire still finishes its shoot program (and so still posts the second and third events) depends on the death request being locked out during the shot (`machine_figure_animation.md` §0.3). By that rule it does, so up to two more balls can come from a gun that has just blown up. Not observed on screen |

## 3. Q3, Q4 — timing, random draws, scatter and misfire

Ticks are counted from the tick on which the machine figure enters the shoot action (tick 1 = its first shoot tick).
`r0`, `r1`, `r2` are each `rand() mod 4` from the battle's shared random stream (MSVC `rand`, `game_rules.md` §4).

| Tick | Machine figure | Shooting side |
|---|---|---|
| 1 | draw `r0` | |
| 1 … 6−r0 | intact frames | |
| P1 = 7−r0 | **puff 1**, extra post (event 34, no figure), then draw `r1` | |
| P1+1 | | dispatch → `FireAtTarget` **launch 1** from the unit position |
| P1+1 … P1+4−r1 | intact frames | |
| P2 = P1+5−r1 | **puff 2**, extra post, then draw `r2` | |
| P2+1 | | **launch 2** from the unit position |
| P3 = P2+5−r2 | **puff 3** + event step (countdown 1 → 0, event 34, source = machine figure) | |
| P3+1 | | **launch 3** from the machine figure; then (intact Artillery) `SetWait 10; Wait; React 12; ReformToScriptRanks` |
| P3+1 … P3+4 | intact frames | |
| P3+5 | back to stand | |

So the extra launches happen **on the tick after each puff**, like the ordinary one. They are not batched at the fire
step. The three shots are 5–8 ticks apart (`5 − r`).

**Random-stream order.** `r0` is drawn when the shoot action starts. Each `r1`/`r2` is drawn on its puff tick (during
the model update, after the post). Each launch's draws happen at the next tick's script step: the misfire D6 (and a
second D6 on a 6) first, then the scatter draws of the launch (`game_rules.md` §8.3). So per shot the stream order is
`r0` … `r1` … [launch 1: misfire, scatter] … `r2` … [launch 2: misfire, scatter] … [launch 3: misfire, scatter], with
other units' draws interleaved by unit order.

**Scatter.** Each launch rolls its own scatter. The first misfire D6 (when it is 1–5) is also the shot's scatter die
`d`, so the spread is `8d`, plus 8 when the aim line is obstructed (`game_rules.md` §8.3, `ranged_combat_handoff.md`).
Three shots at the same target therefore land at three independent points.

**Misfire.** **Every launch** rolls its own misfire: on a 6, a second D6 gives 1 = the machine is destroyed, anything
else = the shot is lost. Both mean no projectile (`game_rules.md`). A lost shot still re-stamps the reload. A misfire on
an extra launch is not followed by the after-shot pause, because the source is "none".

## 4. Q5 — the muzzle puff (also the cannon's)

Each puff is spawned by the animation itself, before and independent of the launch:

- **Position**: the unit's position plus **24 units straight ahead along the unit facing** (the offset is turned by
  the facing with the usual ×256 direction values, truncated toward zero). It is **not** offset from the machine
  figure. This rule is shared with the cannon and Great Cannon (`machine_figure_animation.md` §2.1, corrected).
- **Height**: 12 above the ground. 🟡 The effect keeps only its own point, so the ground is taken at the **puff
  point** (not at the machine). That is the general effect-drawing convention; it was not separately traced.
- **Look**: the battle-effects one-shot, 4 ticks, 4 frames (`machine_figure_animation.md` §2.1).
- **Always drawn**, for all three puffs: also when that launch then misfires, finds no target, or there is no free
  projectile record. The only exception is when no effect record is free.

## 5. Test vectors

Volley Gun unit V at (1000, 1000), facing 0 (+y), intact, crew 3, target regiment E centre at (1000, 1240)
(distance 240 < 287 → S 5). The shot is ordered at tick 0 (war-machine volley: event 34, divisor 1, countdown 1).

| Before | Action | After |
|---|---|---|
| V idle, request (34, 1, 1) | machine enters the shoot action on tick 1, `r0` = 2 | puff 1 on tick 5 at (1000, 1024), height 12; event 34 (no figure) posted; `r1` drawn |
| event 34 (no figure) pending | tick 6 dispatch → 111 | `FireAtTarget`: reload stamp := 6; misfire D6 = 3 (no misfire; scatter `d` = 3, spread 24); **ball 1** from (1000, 1000), S 5, aimed at E's centre at tick 6; source −1 → no wait, no re-form |
| `r1` = 0 | tick 5 + 5 − 0 = 10 | puff 2; event 34 (no figure) posted; `r2` drawn |
| E has moved to (1000, 1300) (distance 300) | tick 11 dispatch | **ball 2** from (1000, 1000), **S 4** (300 > 287), aimed at (1000, 1300), its own scatter; reload stamp := 11 |
| `r2` = 3 | tick 10 + 5 − 3 = 12 | puff 3 + event step: countdown 1 → 0, event 34 (source = machine figure) |
| — | tick 13 dispatch | **ball 3** from the machine figure; reload stamp := 13; source ≠ −1, Artillery, intact → `SetWait 10; Wait`, then `React 12`, `ReformToScriptRanks` |
| launch 2's misfire D6 = 6, second D6 = 4 | tick 11 | shot **lost**: no ball 2; reload stamp := 11; message as for any lost shot; launch 3 still happens on tick 13 |
| launch 1's misfire D6 = 6, second D6 = 1 | tick 6 | machine **destroyed**: no ball 1. 🟡 Its shoot program still runs, so the puffs and posts on ticks 10 and 12 follow, and balls 2 and 3 are launched |
| V's target cleared (target gone) before tick 11, no target point | tick 11 dispatch | launch 2: **nothing**, no stamp; puff 2 was still drawn on tick 10 |
| `r0 = r1 = r2 = 0` | — | puffs on ticks 7, 12, 17; launches on 8, 13, 18 (the slowest shot) |
| `r0 = r1 = r2 = 3` | — | puffs on ticks 4, 6, 8; launches on 5, 7, 9 (the fastest shot) |

The last two rows were computed from §3: P1 = 7 − r0, P2 = P1 + 5 − r1, P3 = P2 + 5 − r2, each launch one tick after
its puff.

**Invariants an engine can assert**

- One ordered Volley Gun shot gives exactly three launches (fewer only through misfires, a missing target or no free
  projectile record), each on the tick after a puff.
- Launches 1 and 2 start at the unit position, and launch 3 at the machine figure.
- The reload stamp after a shot equals the tick of the last launch attempt that found a target and a free projectile
  record (a misfire still counts).
- The after-shot pause runs once per shot (after launch 3), never after launches 1–2.

## 🟡 Open items

- A machine destroyed by an early misfire still completing its program (§2, §5): follows from the lock-out rule, but
  not observed on screen.
- The puff's ground sample point (§4).
