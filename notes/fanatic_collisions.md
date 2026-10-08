# Fanatic footprints in the collision pass, the re-check throttle, wagon event 0x27 and per-unit order (GitHub #195)

Public behavioural handoff for #195 (follow-up of #170). Static research; the original was not run. It refines
`script_behaviours.md` §2.1–2.2 (shared state and the collision pass) and corrects two of its statements (§6). Fanatic
damage itself (`FanaticUpdate`) stays as in `game_rules.md` "Night Goblin Fanatics".

## 1. Summary

- A fanatic's footprint is a **fanatic footprint**. While the fanatic is hidden it is **inactive** and nothing sees
  it. Once released it takes part in other units' collision passes only through the special branch below. The
  fanatic **never runs a collision pass of its own**.
- A regiment overlapping a released fanatic gets **no push, no contact event (0x0B), no contact latch, no re-check**
  on either unit. The only thing that can happen is a **contact attack**:
  - by a **charging or pursuing** regiment **on the fanatic**, but only if the fanatic lacks `CantMelee`. Every
    shipped fanatic has `CantMelee` (`CantBreak|HateDwarfs|PsyImmune|CantMelee`), so **with shipped data this never
    happens**;
  - by **the fanatic on a broken (routing) regiment** that runs into it: once per segment, whatever the fanatic is
    doing.
- All the fanatic's real damage comes from its own update (`Query 18`, every 5 ticks, by distance), not from
  contact. Being touched never interrupts its wander loop.
- The re-check state from a unit's **own position step** is throttled: it is switched on only on **every 4th
  update** of that unit. Gradual turns and every formation re-layout also switch it on (correcting §2.1).
- Wagon event 0x27 needs the **wagon's own collision pass**, i.e. its own re-check state. It comes from the broad
  (circle) test only.

## 2. The fanatic branch of the collision pass

Order of tests when unit A's pass meets another footprint X owned by U (`script_behaviours.md` §2.2). Only the rows
that differ for fanatics are shown.

| A (pass-taker) | X | Result |
|---|---|---|
| a fanatic (released or hidden) | anything | **no pass at all**: no push, no edge correction from the pass, no contact, no 0x27 |
| any | hidden fanatic | X is ignored (inactive footprint) |
| wagon | released fanatic | 0x27 if X lies within ±45° of the wagon's facing (§4), then as below |
| regiment, same army as the fanatic | released fanatic | **no push** (the same-army push-apart excludes fanatics); nothing else |
| regiment, other army, **not broken** | released fanatic | (a) fear-on-contact check as for any regiment (fanatics cause no fear, so it passes); (b) **no touch test**: if U lacks `CantMelee`, A makes contact attacks on U (only if A is charging or pursuing, once per segment, `game_rules.md` §7.7). With `CantMelee` (all shipped fanatics), nothing |
| regiment, other army **or U is A's target**, **broken** | released fanatic | **U (the fanatic) makes contact attacks on A**: forced (the fanatic need not be charging), once per segment, reach 12 (the fanatic is infantry), automatic hits on models not in the turning state |
| building (when its pass runs) | released fanatic | 🟡 if the fanatic footprint counts as a troops footprint, a contact record and 0x0B go to the fanatic. Its handler ignores everything except 0x34, so this has no effect |

Consequences:
- A fanatic is never pushed and never pushes. It never holds the contact latch and never gets 0x0B from regiments.
  Regiments and fanatics overlap freely.
- A regiment's latch is unaffected by overlapping a fanatic. The latched-move undo test, and `CheckCollisions`
  (library 166), count a fanatic overlap only through contact attacks that wounded something: never on a
  `CantMelee` fanatic, but yes when a fanatic hits a broken regiment. `CheckCollisions` then returns true, and the
  wounds stand even in probe mode.
- Kill credit: contact attacks credit the attacker (`casualty_bookkeeping.md`). The row "contact attacks on a
  fanatic by a unit moving through it" there applies only to a fanatic without `CantMelee`, which shipped data never
  has. In practice, kills on fanatics come from missiles, magic, terrain and the fanatic's own death after hitting
  machines or buildings.

## 3. Fanatic wander and touches

The wander loop (`script_queries.md` §10: event 0x34 → `Query 17` → walk → re-form → 0x34 …) is driven only by the
fanatic's own movement and re-form. Overlaps with regiments raise no event for the fanatic, so touches neither
interrupt nor restart the loop. The fanatic's damage is applied by its own update every 5 ticks, to units by
distance (`game_rules.md` "Night Goblin Fanatics"), whether or not their footprints overlap. Hitting artillery,
rolling stock or buildings kills it there. Leaving through the battle edge removes it. Entering other `0xB0` areas
kills it.

## 4. Wagon event 0x27

0x27 is raised **inside the wagon's own collision pass**. For every other active footprint whose **circle** overlaps
the wagon's circle (broad test only; no corner test), the bearing from the wagon to that footprint's centre is
compared with the wagon's facing. If the difference is **strictly under 64/512 (45°)**, the wagon gets 0x27,
once per such footprint. This applies to any kind: regiment, fanatic, building, scenery, machine.

So it needs the wagon's **re-check state exactly**: another unit's pass touching the wagon does not raise it, and
the wagon's movement raises it only on the updates where its re-check state is on (§5). A wagon standing still in
contact raises it only when something else switches its re-check state on (a push, a turn).

## 5. The re-check state (corrects "except in one special movement sub-state")

Each unit has an **update counter** that goes up by one every update. Its starting value is the unit's slot
number, so units are staggered. A unit's own **position step** (ordinary move, charge, pursuit, flight) switches
the re-check state on **only on updates where the counter is a multiple of 4**. So a moving unit runs its own
collision pass about every 4th update, at a phase that differs between units. There is no "special movement
sub-state": this throttle is what that sentence referred to.

Other sources switch it on every time:
- **each gradual turn step** (wheel, halted turn, charge or pursuit re-aim, turn order);
- **every formation re-layout** (re-form, rank change, the re-form after an instant turn or halt);
- the battle-edge repel, being touched or pushed in another unit's pass, the contact handler's latch-off branches, and
  `Rally` (as already listed).

The pass clears it at its start.

Test vectors:

| Before | Update | After |
|---|---|---|
| unit moving, counter 7 | counter → 8, position step | re-check on; pass runs this update |
| same | counter → 9, 10, 11 | no re-check from moving; pass does not run (unless something else set it) |
| unit wheeling, counter 9 | turn step | re-check on (turn) |
| unit standing, re-forms to new ranks | layout | re-check on once |

## 6. Per-unit order (question 1)

The original processes units **one at a time** in slot order. For each unit: update counter +1, speed, script,
formation update, then movement (or, in melee, its close-combat round at a segment boundary), then its collision
pass if the re-check state is on, then its figure update. Only then does the next unit start.

Observable differences against "all scripts, then all moves, then one pass":
- **Contact timing**: a unit later in the order sees earlier units' moves in the same update, so contact, 0x0B and
  engagement can come one update earlier, as in the §2.8 example.
- **Who engages whom when both close in the same update**: the first unit whose pass detects the overlap runs the
  handshake. That decides the joiner and owner, who gets the charge counter, and the flank/rear event
  (`game_rules.md` "Two units both charging"). This changes combat results, not just timing.
- **Joiner cell claims** on a shared grid follow the same order (`game_rules.md` "Cell ownership is per side").
- With the throttle of §5, *which* updates a moving unit runs its pass on depends on its slot. A per-update pass for
  everyone changes when contacts are detected by up to 3 updates.

Mission scripts poll flags and events each update and are insensitive to one-update shifts. Engagement order and
the joiner/owner choice are the visible effects. **Recommendation**: run the unit loop per unit (script →
movement/melee → own pass → figures) if exact combat parity matters. It is a structural change but a simple one.
Otherwise keep the batch order and accept occasional differences in who charges whom. The throttle of §5 should be
reproduced in either case.

## 7. Corrections to `script_behaviours.md` §2.1 (applied)

- "Set by: the unit's own position step … (except in one special movement sub-state)" → set by the own position step
  only on every 4th update of the unit (§5).
- "Not set by turning in place, by re-forming" → gradual turn steps and formation re-layouts **do** set it; standing
  still and instant turns by themselves do not (an instant turn sets it through the re-form it queues).

## 8. Test vectors (fanatic)

| Before | Action | After |
|---|---|---|
| fanatic hidden inside its parent; enemy regiment overlaps it | enemy pass | nothing (inactive footprint) |
| released fanatic F (`CantMelee`) overlaps an advancing enemy regiment R (not charging) | R's pass | no push, no 0x0B, no latch; R keeps moving; F unaffected |
| same, R charging | R's pass | no contact attacks (`CantMelee`); R's charge continues |
| F without `CantMelee` (not in shipped data), R charging | R's pass | R makes contact attacks on F once this segment; credit to R |
| broken enemy regiment B flees through released F | B's pass | F makes contact attacks on B (forced, once per segment): automatic hits on B's models within reach that are not turning |
| friendly regiment of F's army overlaps F | its pass | no push (fanatic exempt); nothing |
| F walks over a regiment | F's update | no pass for F; damage only through `FanaticUpdate` (every 5 ticks, by distance) |
| latched regiment L overlapping only F tries to move | probe pass | nothing counts as overlap, so the step stands and the latch goes off |
| wagon W moving, F 30° off its facing, circles overlap | W's pass (re-check on) | 0x27 to W |
| same, W's re-check off this update | — | no 0x27 |
