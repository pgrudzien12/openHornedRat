# Gap: formation changes (rank changes and re-forms) — how the figures re-sort themselves

**Symptom**: a rank change or any other queued re-form isn't modelled as its own process at all —
there's no re-slotting search, no dedicated flat-speed re-form mover, and no place-swap rule. Nothing
in the engine distinguishes "re-forming" from ordinary movement.

## Known facts

Fully specified, no research task needed — `notes/game_rules.md`, "Formation changes: how the figures
re-sort themselves" (marked ✅). Not implemented anywhere: `whshr/formation.py`/`engine.py` have no
re-form flag, no alternate mover, and no model re-slotting search.

**Three things distinguish re-forming from ordinary movement:**

1. **Models are re-assigned to slots by nearest-match, not kept in their old ones.** Re-forming
   recomputes the shape (`frontage = ceil(models/ranks)`, leftovers into the front ranks), then fills
   slots one at a time, front rank first, centre outward: for each slot, scan every not-yet-placed
   model and take the nearest by **octagonal distance** (`larger + smaller/2` of the axis deltas),
   stopping early on an exact match. A soldier does not keep "his" place — he takes whichever slot in
   the new shape is closest to where he already stands, and the whole unit re-sorts for shortest total
   walking. The front-rank centre slot is handed directly to the **leader model** (no search) if not
   already placed.
2. **A separate mover takes over while re-forming.** A flag means "models are off their slots"; while
   set, the unit uses a flat mover instead of the ordinary rank-dependent catch-up walk (epic #49):
   - flat **`s_rlmv / 8`** world units/tick, no rank factor, **no ramp-up** — full speed on the first
     tick, held.
   - decelerates in the last 6 world units: step divided by `7 − distance`, so it slows to a half,
     third, quarter... and settles smoothly (a separate 1-world-unit step cap only bites the fastest
     units).
   - **arrival snaps the model's heading** to the unit's facing.
   - **the unit's own translation speed is halved** for the whole re-form.
   - clearing the flag (last model settled) raises a "re-form complete" event.
3. **Models trade places rather than walk through each other.** Each tick, before stepping, a moving
   model checks its projected next position against every comrade already **at rest**. If it's about
   to step onto one roughly half a spacing away, the two **exchange their entire slot assignment**
   (target position, slot index, rank, column) and re-aim: the walker inherits the settled one's place
   and stops, the settled one wakes and walks off to where the walker was headed. Purely local, no
   global planning — this is what produces the shuffling, place-swapping look.

**Formation differences**: **blocks and monsters** use the flat re-form mover above. **War machines
and wagons do the opposite** — their layouts explicitly *clear* the re-forming flag, so their models
stay on the ordinary rank-dependent catch-up walk (epic #49/#50) instead, ramping up and moving at
rank-dependent speeds; a war machine's crew re-settles around the machine at varied rates rather than
in a uniform shuffle. **The war-machine layout inverts the slot search**: the machine model goes
straight to the front-rank-centre slot, and every crew slot takes the **farthest** unplaced model (not the
nearest) whenever the battle is not in its deployment phase — which is always, for an engine with no
deployment phase. Wagons, monsters and blocks never invert. Full rule and the phase's life cycle in
`notes/game_rules.md`, "Formation changes".

**Cost and gating**: a formation change costs no time of its own (only the walking); rank counts clamp
to `[min, models/min]` with `min = max(1, trunc(0.75 × √models))`; a re-form is refused while fleeing,
held, or charging.

## Open questions

Tracked as [epic #67](https://github.com/pgrudzien12/openHornedRat/issues/67) (tasks #68-#70).

None — fully specified above.

## Implementation notes

Suggested breakdown (three GitHub tasks):

1. **Re-slotting search + the flat re-form mover.** On a rank-count change or any other queued
   re-form, recompute the shape and re-assign every model to a slot by nearest octagonal distance
   (leader gets the front-rank centre directly), then drive affected models with the flat
   `s_rlmv/8`-no-ramp mover (last-6-unit deceleration, heading-snap on arrival, halved unit
   translation speed for the duration) instead of epic #49/#50's rank-dependent catch-up walk, via a
   per-unit "off their slots" flag. This is the coherent core of the mechanic — keep it one task.
2. **Place-swap/exchange rule.** Per-tick, before a moving model steps, check its projected next
   position against at-rest comrades roughly half a spacing away; on a hit, exchange the two models'
   full slot assignment (position, index, rank, column) instead of one walking through the other.
   Builds on task 1's re-form state.
3. **Formation-type differences + verification.** War machines and wagons must clear the re-forming
   flag so their models stay on the ordinary catch-up walk instead of the flat mover; the war-machine
   layout places the machine directly at the front-rank centre and fills every crew slot with the
   **farthest** unplaced model (always, absent a deployment phase). Add tests confirming: a
   re-form costs no extra time beyond walking, is refused while fleeing/held/charging, and a
   war-machine/wagon re-form visibly differs from a block/monster one (rank-dependent speeds, not the
   uniform flat shuffle).
