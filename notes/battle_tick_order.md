# Battle tick order: per-unit interleaving, unit order, what runs around the unit loop

Public behavioural handoff for issue #343, and the basis for restructuring an engine whose battle tick is
**phased**: all scripts, then all movement, then all collision passes. The original is **interleaved**: each unit
runs its complete step, from events to models, before the next unit starts. This report collects the tick order in
one place.

Already public; this report cites these and does not repeat them:

- `movement_formation.md` §1.2: the steps inside one unit's step.
- `spell_effects.md` §1.7: units, then missiles, then effects, then corpses.
- `game_rules.md`:
  - "Battle clock": 100 ms ticks, 19 ticks per segment, segments 10 → 1, pause.
  - "Close combat" and the break-test timing ("All break tests on a grid resolve before any unit strikes in that
    segment").
  - "Fight harder": cleared at the segment boundary after the unit's step.
  - objectives: evaluated on segment-boundary ticks, before units update.
- `terror_contact_charge.md` §8: the event-order consequence that prompted this report.

Marks: ✅ established, 🟡 inferred or not observed on screen.

## 1. One timer message (100 ms) ✅

In this order:

1. The **wind** and compass tape step (`battle_compass.md`).
2. The **camera** update: look-at, held buttons, shake (`camera_shake.md`, `battle_viewer.md`). Then the
   listener position for positional sound.
3. The **view rectangle** for the frame (`react_portrait.md` §"drawn"). It is computed here, **before** the
   simulation, from this tick's camera.
4. The **simulation step**. Nothing runs while the game is paused. Otherwise, by game mode:
   - **deployment**: §4;
   - **battle**: the battle tick, §2;
   - **deployment-flag layout**: a one-off step.
5. Compass heading and power-pool redraw, the portrait pop-up countdown (`react_portrait.md`), then the frame is
   painted.

## 2. The battle tick ✅

### 2.1 Before the unit loop: only on segment-boundary ticks

The segment clock advances first. On the tick where the segment changes (every 19th tick), before any unit runs:

1. For **every active unit**: clear the two one-segment states, then run the **break test** for each unit in melee
   (`game_rules.md`: it acts only in the grid's creation segment; a failure queues event 0x0C to the unit).
2. The **per-segment objective check** (`battle_end_objectives.md`; `game_rules.md` "Missions and objectives").

### 2.2 The unit loop

Units run **one after another in unit-table order** (§3). Each unit's step is complete before the next unit starts.

**Building pseudo-units** (`building_units.md`) run no script and no movement. They get only the collision pass
(when re-check is on) and the destruction check.

**Every other unit:**

1. Update counter +1. Recompute speed.
2. **Script step** (`unit_script_control.md` §1):
   - the periodic behaviour;
   - if events are queued, the event handler. It drains the queue in one pass, and a switch applied at
     `ReturnInterrupt` runs on at once (`terror_contact_charge.md` §8.1);
   - the wait countdown;
   - a pending player order (`player_missile_orders.md`);
   - the script itself, until it yields or waits.

   Shooting launches, casts, charge starts, `SendEvent…` and every other script effect happen here.
3. If the unit is still active (a script may have removed it): the **formation update**. This covers the re-form
   walk, the slot layout and, for a unit in melee, the grid pairing and gap closing (`grid_gap_closing.md`,
   `reform_while_moving.md`).
4. **Movement or close combat:**
   - **not in melee**: take the contact-latch snapshot, then run exactly one movement handler, chosen by priority:
     wait → flee (includes the rally attempt and the departure) → pursue (includes pursuit restraint) → move →
     charge → turn. With none of them, the unit is marked halted.
   - **in melee**: no movement. On a segment-boundary tick only, the unit's **melee round**, if its Initiative
     equals the segment number. A round may first show the "outnumbered/fear" reactions (`game_rules.md`
     "Close combat").
5. The **collision pass**, only if the unit's re-check state is on (`game_rules.md` "Routes, collisions";
   `fanatic_collisions.md`). This is where the contact fear test, push-apart, contact (0x0B) and contact attacks on
   fugitives happen.
6. If still active: the **models update**: animation, poses, death animations. A death removes the model, and a
   failed panic test queues 0x0C (`casualty_bookkeeping.md`, `game_rules.md` panic). The "drawn this frame" state
   is set against the rectangle from §1 step 3.
7. The unit's HUD or panel refresh. If the unit is the focused unit and has been removed, the camera re-focuses.
8. On a segment-boundary tick: the unit's **fight harder** state is cleared (after its step).

### 2.3 After the unit loop: every tick

1. **Ordinary missiles** (arrows, bolts, shot, artillery): every flying projectile advances and tests once.
2. **Active spell effects**: the dispel auras first, then each effect advances once (`spell_effects.md` §1.7).
3. **Corpses and battle birds** (`battle_birds.md`).
4. **Effect markers and particles**: deployment flags, building smoke, spell sprites (`building_ruins.md`,
   `deployment_flags.md`).
5. End-of-tick scene housekeeping.

There is **no** global close-combat, morale, rout or objective phase anywhere else in the tick. Each of these sits
inside a unit's step (§2.2) or in the segment pre-pass (§2.1).

| Concern | Where it runs |
|---|---|
| events and scripts, orders, shooting launch, spell launch, charge start | unit step 2 |
| re-form walk, grid pairing/gap closing | unit step 3 |
| movement, flight, rally attempt, departure off the field, pursuit, pursuit restraint | unit step 4 (not in melee) |
| melee round (strikes) | unit step 4 (in melee, segment tick, I = segment) |
| break test | segment pre-pass §2.1, all units, before any strike |
| contact, push-apart, contact fear, fugitive contact attacks | unit step 5 |
| model deaths, panic tests, death events | unit step 6 (and inside missile or effect hits for wounds; the removal itself happens through the victim's death animation, in its own step 6) |
| projectile flight and impact | after the loop §2.3 |
| spell effect updates | after the loop |
| objectives | segment pre-pass (plus the final pass when the battle ends) |
| wind | timer, before the battle tick |
| camera, view rectangle | timer, before the battle tick |

## 3. Unit order ✅ / 🟡

- **Load order**:
  1. the battle file's units in file order. Building pseudo-units are created while the scenery is read,
     **before** the `UNITS` section, and then come the `UNITS` entries (enemies, NPCs, anything else listed);
  2. **then** the player's army file, appended in its own order (the marching order, `builtin_widgets.md` §5).
  So player units normally run **after** the battle file's units.
- 🟡 In battles with objective G the merge rebuilds the table at start-up (`allied_npc_merge.md`); the resulting
  order was not traced.
- **Removed units keep their slot.** Dead, fled-off and script-removed units become inactive and are skipped, and
  their slot is never reused (they stay listed for the debrief and objectives). Hidden units are active and run
  normally: scripts, movement, collisions.
- **Spawned units** (`script_spawn_move.md` §2) take the first slot that was never used, which is **after every
  existing unit**; the table grows when full. The loop handles as many active units as were active when the tick
  began. A copy spawned during the tick is therefore normally **not** run until the next tick. 🟡 Exception: it
  runs in the same tick if a unit that had not yet been reached was removed during that tick. Corrects the 🟡 in
  `script_spawn_move.md` §2 ("may run its script in the same tick"): normally it does not.

## 4. Deployment mode ✅

See `deployment.md` for the player's side of deployment.

The same per-unit loop runs (placement handling, script, formation, movement, collision, models) for every active
unit. A unit that is still off the field is not moved. After the loop come the markers and the corpse ring. The
deployment tick has **no** segment pre-pass, no melee rounds, no missiles, no effect updates and no objective check.

## 5. What the interleaving changes (question 3) ✅

The table below lists, for a unit A earlier in the order than B, what each side sees in the same tick. A phased engine
gets each of these wrong in a specific direction.

| Interaction | Interleaved original | Phased engine (scripts → moves → collisions) |
|---|---|---|
| **Events A → B** sent in A's step (any step) | B handles them **this tick** (B runs later) | B handled them already this tick if sent in a later phase; otherwise next tick |
| **Events B → A** sent in B's step | A handles them **next tick** | same, but the order relative to A's own collision-pass events differs |
| **LIFO order in B's queue** | every sender's script-step events are older than its collision-pass events, and B drains between any two runs of a sender | events from several phases and several senders pile up between two drains: a sender's next script-step event can lie **above** its earlier contact event (`terror_contact_charge.md` §8.5) |
| **Positions** | B's script, movement and collision pass see A **after** A moved this tick; A saw B **before** B moved (B's position from the previous tick) | every script sees everyone's old positions; every collision sees everyone's new positions |
| **Contact pairs** | A's collision pass tests A's new footprint against B's old one. B's pass, later, tests both new footprints. Each pass runs only when its own re-check is on, and A's pass can arm B's re-check for B's pass **this tick** | all passes after all moves: symmetric, with re-check armed only for the next tick |
| **Fear and contact flight** | the unit that handles the fear 0x0D routs in its own script step, before its own movement and collision pass | it moves and collides unbroken for one phase |
| **Targets and queries** (distance, sight, nearest enemy, `TargetGone`, charge reach) | read the live state: units earlier in the order are already updated | read the start-of-tick state for everyone |
| **Removal in A's step** (death animation, flight off the field, script removal) | B sees A gone this tick; 0x16 or 0x0E arrives at B this tick | depends on the phase that removes |
| **Grid pairing / gap closing** | cells are claimed unit by unit, earlier units first (`grid_gap_closing.md`) | claimed in one phase; the conflict order differs |
| **Melee rounds at the same Initiative** | run unit by unit in table order, within the units' steps (after each one's script and formation) | one melee phase after all movement |
| **Missiles and spell effects** | after **all** units: they see every unit's final position this tick, and the events they cause (0x0C panic, 0x0D…) are handled by **every** unit next tick | same, if the projectile phase is last |

Engine advice:

- Reproduce the per-unit loop: for each active unit in table order, run the whole unit step (§2.2 steps 1–8).
  Then run missiles, then effects, then corpses and markers.
- Run the segment pre-pass before the loop.
- Keep the unit-table order of §3. Do not re-sort the table by side or by any other key.
- A phased engine cannot reproduce the event-order rules of `terror_contact_charge.md` §8.5 in general.

## 6. Test vectors

| Before | Action | After |
|---|---|---|
| A (table index 3) moves 20 units east this tick; B (index 7) tests the distance to A in its script | tick | B sees A's **new** position |
| same, B index 1 | tick | B sees A's **old** position |
| A sends 0x0A to B in A's script step; B is later in the order | tick t | B handles 0x0A in tick t |
| same, B earlier in the order | tick t | B handles it in tick t+1 |
| W (earlier) collision pass at t gives C (later) a reciprocal 0x0B | tick t | C handles that 0x0B in tick t. W's 0x07 from handling its own 0x0B arrives in tick t+1, before C's step, above W's new 0x0B of t+1 |
| segment-boundary tick, units X (I 4) and Y (I 4) in melee on one grid, the grid's creation segment = 4 | tick | segment pre-pass: both break tests; loop: X's step with its round, then Y's step with its round (table order); missiles after |
| unit S spawns copy K during its script; no unit is removed this tick | tick t | K exists, with its slot after every existing unit; K's script first runs in tick t+1 |
| a hidden reserve | every tick | runs its script and movement normally |
| a unit fled off the field at t | t+1 onwards | slot skipped, never reused |
| deployment mode | tick | per-unit loop only; no break tests, no missiles, no objectives |

## 🟡 Open

- The table order after a G merge's rebuild.
- The spawned unit's same-tick run in the "earlier removal" case.
- No screen observation of any ordering effect.
