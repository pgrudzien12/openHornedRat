# Gap: mounted units (movement and the mount's extra attack)

**Symptom**: mounts aren't modelled in the engine at all — `whshr/combat.py`'s own module docstring
says so directly. A mounted regiment moves, charges, and fights exactly like an unmounted one: no
extra speed from the mount's Movement, no extra attack sequence for the mount in close combat.

## Known facts

Fully specified, no research task needed — `notes/game_rules.md`, "Mounts" (under close combat),
marked ✅.

- **A rider is mounted when its armour code has bit 3 set** (codes 8–13; `whshr.rules.armour_description`
  already recognises this range for display purposes, just not in the real-time engine).
- **Exactly five mount-record fields are ever read**: M, WS, S, A, and **charge strength**. BS, T, W, I,
  Ld are never touched by anything. Four mounts (`s_mount` 1–4):

  | `s_mount` | Name | Charge S | M | WS | BS | S | T | W | I | A | Ld |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | 1 | Warhorse | 5 | 7 | 3 | 0 | 3 | 3 | 1 | 3 | 1 | 5 |
  | 2 | War Boar | 6 | 6 | 4 | 0 | 3 | 4 | 1 | 3 | 1 | 3 |
  | 3 | Giant Wolf | 3 | 8 | 4 | 0 | 3 | 3 | 1 | 3 | 1 | 3 |
  | 4 | Cave Squig | 0 | 5 | 4 | 0 | 5 | 3 | 1 | 5 | 2 | 2 |

- **Movement is the mount's largest effect by far.** The speed stat (`s_rlmv`) is derived once at
  unit set-up using the **mount's M in place of the rider's** when mounted; the rider's own I is still
  used. Everything that scales off `s_rlmv` inherits this for free: per-tick speed in every movement
  state, charge reach (`12 × (s_rlmv + 1)`), turn/wheel rate, flight/pursuit speed, and each model's
  formation catch-up speed (epic #49). A Warhorse rider (M7 I3) gets `s_rlmv` 18 against 11 on foot
  (M4 I3) — about 64% more of everything above, and a 228-unit (9.5") charge reach instead of 144
  (6").
- **An extra attack sequence in close combat.** The mount attacks in its own right with its own A, WS
  and S, substituting its **charge strength** for S while the unit's charge counter is non-zero (not
  a flat "+1 S" like the rider's own charge bonus — the mount's S is *replaced* by its charge-strength
  stat). Because the rider and the mount each run an attack resolution, a mounted model also drains
  the charge counter faster than a foot model — already flagged as a deferred item in
  `notes/engine_gaps/charge_bonus.md`'s task #59, blocked on this gap.
- **No extra toughness, wounds or survivability.** A mounted model has a single wound counter and uses
  the **rider's** T and W; the mount cannot be wounded or killed separately, and is never removed while
  the rider lives. A mount is pure offence and pure speed.
- **Does not change**: the charge counter's *size* (`1.5 × frontage`, a formation property, unaffected
  by mounts), model spacing (12 world units for every class, cavalry included), the formation layout,
  or the automatic-contact-attack reach (12/18/24 world units) — that reach is selected from the
  unit's **class** alone (Cavalry/Monster get the wider values) and is read without reference to the
  mount record at all. Easy to get wrong by accident when wiring mounts in; worth an explicit
  regression check that it doesn't start reading the mount.

## Open questions

Tracked as [epic #61](https://github.com/pgrudzien12/openHornedRat/issues/61) (tasks #62-#64).

None — fully specified above.

## Implementation notes

Suggested breakdown (three GitHub tasks):

1. **Movement: mount's M substitutes for the rider's M.** Add a small verified constant table (the
   mount profile table above, matching `whshr.rules.EXPECTED_ARMOUR_SAVE`'s existing pattern — a
   lookup table of numbers, not "content") and read `s_mount`/`s_armr` at regiment construction
   (`whshr/engine.py: _decode_combat_profile`) to pick M' (mount's M when armour code ≥ 8, else the
   rider's own M) before calling `speed_per_tick(M', I)`. This alone fixes speed, charge reach,
   turn/wheel rate and model catch-up speed for mounted units for free, since they all already derive
   from the one stored `speed_per_tick`/`s_rlmv` value. Verify contact reach (class-only) and the
   charge counter's size (formation-only) stay unaffected as part of this task.
2. **Close combat: the mount's own extra attack resolution.** Once a model is known to be mounted
   (same armour-code test as task 1), `whshr/combat.py`'s strike resolution
   (`_strike_with_models`/`_roll_model_attacks`) must run a second attack resolution per fighting
   model using the mount's own A/WS/S — substituting the mount's **charge strength** for its S while
   `charge_counter` is non-zero (not the rider's own flat +1 S charge bonus) — against the same
   opponent, sharing the model's single wound counter (no extra T/W, mount never separately
   killed/wounded). This is also what unblocks `notes/engine_gaps/charge_bonus.md`'s task #59 (a
   mounted model draining the charge counter faster, since both attack resolutions decrement it).
3. **Verification**: tests confirming the worked Warhorse example (`s_rlmv` 18 vs. 11 on foot, charge
   reach 228 vs. 144), that a mounted model's wound count/survivability is unaffected, that contact
   reach and charge-counter size stay class-/formation-only (not mount-derived), and that the mount's
   attacks show up as a distinct resolution in combat logs/events (not folded into the rider's).
