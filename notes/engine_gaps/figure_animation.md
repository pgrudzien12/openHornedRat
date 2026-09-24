# Gap: figure animation (per-model action state, timing, and desync)

**Symptom**: every model of a regiment shows the exact same frame at the exact same moment — the
engine computes one `(action, phase)` pair per **regiment** (`whshr/frontend/battle_view.py`, around
`WALK_ANIMATION_FPS`) and stamps it onto every model's position. A marching or fighting unit looks
like a rank of clones goose-stepping in lockstep, not a crowd of individuals.

## Known facts

Fully specified, no research task needed — `notes/game_rules.md`, "Figure animation: actions, timing,
and why the figures are never in step" (marked ✅). Not implemented anywhere: there is no per-model
animation state at all (`whshr.engine.ModelState` has no action/PC/loop fields), and `notes/
animations.md`'s own frame-timing row was `❌ needs the running game` until this research landed it.

**The model.** Every model runs its own animation program, one step per tick: sprite set, shading,
drawn facing, group base frame, **phase**, plus an **action id**, a **program counter**, and the same
per-model **stagger value** already used by movement/rout (epic #49's `ModelState.stagger`). Frame
selection is exactly `notes/animations.md`'s `frame = group_base + phase × 8 + direction` (standard
unit sets: 0=move, 32=dead, 40=attack, 72=stand, 104=shoot).

**Seven actions, meaning the same thing in every creature family**, each family carrying its own 8-slot
action table (slot 0 unused) — **37 families, 116 distinct scripts** in the data:

| action | meaning | standard infantry's script |
|---|---|---|
| 1 | stand still | stand group, phase 1 held forever |
| 2 | idle/mark time | stand group, 10-tick loop `0,0,0,1,1,2,2,2,3,3`, not randomised |
| 3 | walk | move group, 8-tick loop `0,0,1,1,2,2,3,3`, random entry 0…7 |
| 4 | fighting | attack group, 12-tick loop `0,0,1,2,3,3,1,1,3,0,2,2`, random entry 0…9 |
| 5 | weapon ready (in melee, unpaired) | attack group, phase 0 or 2 at random, held |
| 6 | dead | random facing, single corpse frame, held |
| 7 | shoot | shoot pose, random entry 0…3, 4 ticks, fire event, 2 more ticks, back to action 1 |

Other families reuse these seven meanings with their own loop lengths/hold patterns (example: the
second most common family walks a flat 4-tick `0,1,2,3` loop, marks time on a lopsided 6-tick
`0,0,1,2,2,3`, and randomises even *stand still* between two phases). **One script word = one tick**
(same 100 ms battle tick as everything else): standard infantry walk a 0.8s cycle, fight a 1.2s cycle,
mark time on 1.0s. **Nothing scales with speed** — a charging unit's figures cover more ground per
tick (epic #49) but their legs still cycle at the fixed rate, and charging/marching/pursuing/fleeing
all share action 3 (no separate run animation).

**Five independent desync mechanisms** (rough order of visual weight):

1. **Random entry into the loop** on every action *change* — the dominant effect. Each model rolls
   independently, so a regiment that starts marching together immediately spreads across the whole
   walk cycle instead of goose-stepping. Appears 39 times across the 116 scripts.
2. **The offset persists until the action id actually changes** — re-issuing the same action is a
   no-op (no re-roll). A model mid one-shot animation queues the new action and applies it only once
   the one-shot finishes, desynchronising further.
3. **Uneven frame holds inside the loop** (e.g. infantry hold each walk phase 2 ticks, the fight loop
   visits phases out of order) — combined with random entry, two models on the same loop rarely look
   alike even at the same tick-offset.
4. **Per-model variant selection** from the fixed stagger value: one of three group variants
   (`stagger % 3`) in six scripts, one of two (`stagger` bit 1) in two more; the same value also picks
   one of three death cries.
5. **Staggered collapse on death.** A model whose wounds run out doesn't fall immediately: it keeps
   playing its current animation for `(stagger & 3 + 1) × 18` ticks (1.8–7.2s) — quartered outside
   melee (`(stagger >> 2) + 1`, 0.5–1.9s) — before switching to action 6, then gets a **random facing**
   (why corpses lie at all angles). A few special death kinds collapse in one tick or use a dedicated
   multi-phase death sprite set. A whole regiment destroyed outright falls together with zero delay.

**Drawn facing has its own slew**, separate from the model's body-position facing: turns at most
**22.5° (32/512 turn) per tick** toward a target that depends on the action — stand/weapon-ready/shoot
face the **unit's** facing, walking/fighting face the **model's own** heading (travel direction or
opponent). Dead/one-shot-locked models keep their facing frozen. **Exception: RollingStock (wagons)
snap instantly, no slew.**

**The shoot fire event is posted by the animation script**, not combat code — 4 ticks into the shoot
pose. Since shoot-pose entry is itself randomised 0…3, archers in one unit reach their fire event on
different ticks, which is what produces the documented "every 4th model posts the fire event" volley
rule (section 8.1) — an engine wiring the fire event through the animation state gets that rule mostly
for free; wiring it independently (as this engine currently does) risks a different, un-volleyed
cadence.

**Explicitly out of scope for a first pass** (listed so it isn't silently forgotten, not something to
implement blind): 59 further script operations exist beyond frame stepping — set/clear model flags,
branch on model/unit flags or death kind, mark/loop/repeat counters, yield without changing frame,
chain into another action/sprite set, play a sound or one of a random list, spawn blood decals,
randomise facing, toggle attached light/effect. An engine that only implements frame stepping "will
look wrong" per the source research, but these are a large, lower-priority tail — flagged, not
scoped into the tasks below.

## Open questions

Tracked as [epic #71](https://github.com/pgrudzien12/openHornedRat/issues/71) (tasks #72-#74).

None for the core mechanism — fully specified above. Per-family loop-table data (37 families, 116
scripts) needs decoding into a lookup table at implementation time, but that's data-extraction work
covered by the research already, not an open question.

## Implementation notes

State belongs in the engine (`whshr.engine`, stdlib-only), not the frontend
(`whshr/frontend/battle_view.py` currently computes one `(action, phase)` per regiment and should
instead just *read* each model's already-stepped state).

Suggested breakdown (three GitHub tasks):

1. **Per-model animation state + the seven-action stepper.** Add action id, program counter/loop
   position and a per-model random-entry-on-change mechanism to `ModelState` (reusing the existing
   `stagger` field), driven by a per-family loop-table data structure (group, loop sequence, hold
   pattern, random-entry range) covering at least the standard infantry family structurally so the
   other 36 are a data addition, not a redesign. Frame selection stays `group_base + phase*8 +
   direction` per `notes/animations.md`. Wire the frontend to read per-model state instead of
   `regiment.animation_seconds`.
2. **The remaining four desync mechanisms + drawn-facing slew.** Offset-persists-until-action-change
   and one-shot-blocks-interruption (mechanism 2), per-model variant selection from `stagger`
   (mechanism 4), staggered collapse-on-death timing with the in-melee/out-of-melee multiplier and
   random facing on death (mechanism 5), and the drawn-facing 22.5°/tick slew with its per-action
   target rule (wagons excepted — instant snap). Builds on task 1's per-model state.
3. **Shoot fire-event wiring + verification.** Move the archer fire event to be posted by the
   animation script at tick 4 of the shoot pose (task 1's per-model state) instead of directly from
   combat code, and confirm this reproduces the volley cadence in `notes/game_rules.md` section 8.1.
   Add tests/a visual check confirming a regiment that starts marching together visibly desynchronises
   across the walk cycle within one loop length, and that charging/marching/fleeing share one walk
   action (no separate run animation).
