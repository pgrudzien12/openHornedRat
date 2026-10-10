# What `CheckCollisions` answers (wagons and regiments), and why convoys do not deadlock

Public implementation report (behaviour only), answering the implementer's BF006 convoy question. It refines
`movement_formation.md` §3.10, `script_grid_events.md` §4 and `convoy_jam_and_melee_obstacles.md` §A, whose
"true if anything was pushed or touched" and "the probe queues another 0x27 and returns true" are corrected here
(and in those files). Companions: `script_behaviours.md` §2.2 (the collision pass, "Push apart, exactly"),
`fanatic_collisions.md` §4–5.

## 0. Shared state (read this first)

- `CheckCollisions` runs the unit's ordinary collision pass at once, in **probe mode**. Probe mode changes only the
  enemy **contact**: it is tested but not recorded (no contact handler, no 0x0B, no engagement). Everything else
  really happens: friendly and scenery pushes move the unit, boundary correction moves it, re-check states are
  switched on, 0x27 and the contact-fear 0x0D are queued.
- **The answer is not "anything happened".** For each overlapping footprint the pass produces a per-footprint answer,
  and the instruction's condition is the answer of the **last footprint that produced one** (footprints are examined
  in a fixed order: the battle's footprint list, scenery objects and buildings before regiments as created at load 🟡).
  Answers do not add up: a later "no" overwrites an earlier "yes".
- **A wagon (rolling-stock unit) is never moved by a push**, so every "push the wagon" answer is **no**.

## 1. Per-footprint answers (overlapping footprint X, in this order within one footprint)

| step | applies when | answer |
|---|---|---|
| 1. wagon look-ahead | the **mover is a wagon** and X lies within ±45° of the wagon's facing | 0x27 queued to the mover; answer **yes** (provisional: step 2 for the same X usually overwrites it) |
| 2a. solid scenery | X is solid scenery | push the mover: **yes** for a regiment (it moves), **no** for a wagon |
| 2b. building | mover not charging and not in melee | push the mover: yes / **no** for a wagon |
| 2b'. building | mover charging or in melee | contact test: yes if a corner of the mover's box is inside the building |
| 2c. war machine or wagon X, **same army** | neither unit in melee, broken or pursuing, and no friendly push yet in this pass | push the mover: yes for a regiment, **no** for a wagon; both re-check states on |
| 2c'. same, but one of them in melee, broken or pursuing, or a friendly push already happened | – | **no answer** (the previous answer stands) |
| 2d. war machine or wagon X, other army | mover not broken and not in a catch-up re-form | contact test: yes / no |
| 2d'. same | mover broken or in a catch-up re-form | push the mover: yes / no (wagon) |
| 2e. regiment X whose unit is marked | – | no answer |
| 2f. regiment X, **same army** and not the mover's current target | X is not a fanatic and neither unit is in melee, broken or pursuing, and no friendly push yet in this pass | push the mover: yes / **no** for a wagon; both re-check states on |
| 2f'. same, otherwise | – | no answer |
| 2g. regiment X, other army or the mover's current target | mover broken | X's contact attacks on the mover; no answer |
| 2h. same | mover not broken | (fear-on-contact may queue 0x0D) then contact test: yes if a corner of the mover's box is inside X, else **no** |

"Pushed" therefore means "the mover itself was moved by a push", and **a regiment push always answers yes**, even if
its shift truncates to 0 on both axes. "Touched" means **only** an other-army footprint (or the mover's own target)
with a corner of the mover's box inside it; a friendly overlap never "touches". **Boundary correction never gives
an answer** (it runs first and is ignored by the result; wagons are corrected like regiments). The "one friendly push
per pass" rule only ever triggers for regiment movers, because a wagon's push never succeeds.

## 2. Answers to the questions

1. **A wagon overlapping a same-army wagon, regiment or war machine answers no**, because the push moves nothing. This
   overwrites the yes of its own 0x27 for the same footprint. A regiment's push answers yes even when it moves 0.
2. A friendly overlap behind the wagon raises no 0x27 and answers no. "Touched" is only an other-army box corner.
3. Scenery and building pushes answer no for a wagon (it is not moved). Boundary correction never counts, for anyone.
4. **No deadlock in the original.** In 166 a wagon's probe answers no as soon as nothing but friends overlaps it, so
   it `Restart`s and drives on. The wagon that still has a friend within ±45° ahead also re-queued 0x27 during the
   probe. That 0x27 sends it back into 166 on the next tick, now as a real switch (166 starts again from `Yield`), so a
   following wagon **creeps**: it drives about 2–3 ticks, halts, waits 20 ticks, probes, and so on. The lead wagon
   has no friend ahead once the infantry has been pushed aside (§3 (c)), so it leaves for good. An engine whose probe
   answers "any overlap" keeps all three wagons in 166 forever: that is the BF006 deadlock.

## 3. Test vectors (all units of the same army unless stated; overlaps are circle overlaps)

| case | before | `CheckCollisions` | after |
|---|---|---|---|
| (a) | lead wagon L in 166, friendly wagon F overlapping **behind** (180°), nothing else | runs | no 0x27; same-army wagon → L not moved → **false**; contact latch cleared; F's re-check on → `Restart`: L resumes its main script and drives on |
| (b) | following wagon F in 166, friendly wagon L overlapping **ahead** (20° off F's facing) | runs | 0x27 queued; same-army wagon → F not moved → **false** (overwrites) → `Restart` → main script moves F this tick; next tick 0x27 → handler → switch to 166 (a different script now) → `Yield`, then `HaltAndReform`: F creeps 2–3 ticks per ~22 |
| (c) | wagon W in 166, friendly infantry I overlapping ahead, I not in melee | runs | 0x27 queued; same-army regiment → W not moved → **false**; I's re-check on → I's own pass moves I away by half the overlap + 1. W `Restart`s; it creeps until I is clear |
| (c') | same, but I is **in melee** | runs | 0x27 queued; same-army row skipped (no answer) → **true** (from 0x27) → W waits another 20 ticks while I fights in front of it |
| (d) | wagon W, nothing overlapping | runs | **false**, latch cleared → `Restart` |
| (e) | regiment R overlapping friendly regiment Q, neither in melee, broken or pursuing | runs | R moved away from Q by half the overlap + 1 → **true**; both re-check states on; a second friendly overlap in the same pass: no push, no answer → still true |
| (e') | R overlaps friendly Q, and later in the list an enemy E whose circle overlaps but no corner of R's box is inside E | runs | push → yes, then E's contact test → **false** (the last answer wins) |
| (f) | wagon W, enemy E ahead, a corner of W's box inside E | runs | 0x27 queued; contact test → **true** (no engagement in probe mode) |
| (g) | wagon W overlapping solid scenery | runs | not moved → **false** |

## 4. Corrections to public notes (made in the same commit)

- `movement_formation.md` §3.10: "Condition = true if anything was pushed or touched" → the last per-footprint answer;
  wagon pushes answer no.
- `script_grid_events.md` §4: "true if anything was pushed, touched … or 0x27 raised" → as above; 0x27 does not keep
  the condition true when the same footprint then answers no.
- `convoy_jam_and_melee_obstacles.md` A.2 / A.3: the probe of a cart with a friendly cart ahead **returns false**, so
  the cart restarts and creeps rather than standing; "never drives through W1" is replaced by the creep behaviour.

## 🟡 Open

- The exact order of footprints when several overlap at once (it decides cases like (e')).
- Whether a creeping follower can, over many cycles, drive into a lead cart that stays halted for a long time.
