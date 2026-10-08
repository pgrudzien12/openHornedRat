# The Rally order on a pursuing unit, and the pursuit-restraint test

Clean-room behavioural handoff, written to be implementable on its own. It specifies the player's **Rally** order
(order code 0x14) applied to a **pursuing** regiment, and the **pursuit-restraint test** that can end the pursuit.
Static research; the original was not run. Background, only where cited: `game_rules.md` "Pursuit", "Rally",
"The Leadership test", "Effective Leadership", "Player orders and the command panel"; `pursuit_map_edge.md` (the
rest of the pursuit update and what ends a pursuit); `reform_while_moving.md` §6 (the Re-group re-form).

## 1. Summary

- A pursuing regiment has a **rally-attempt state** (on/off) and a **scheduled segment** (a segment number 1–10).
- **Rally (0x14)** flips the rally-attempt state of a player regiment that is pursuing or broken. A second press
  switches it off again. There is no reply, no shout and no other effect.
- On every **segment boundary** the pursuer checks: is the segment number now equal to its scheduled segment,
  **and** is the rally-attempt state on? If both hold, the scheduled segment moves **3 segments on**, and the
  regiment rolls a **plain Leadership test**: no modifier, effective Leadership (leader's Ld, else the first model's
  Ld), uniform 2–12 roll. A regiment with `AlwaysPursue` skips the roll but is still rescheduled.
- **Pass** → the pursuit ends exactly as any other pursuit end: event 0x10 → "Re-group!" → stop pursuing,
  re-form in place, back to the regiment's script. **Fail** → nothing visible; the next roll comes 3 segments
  later while the state stays on.
- The first possible roll is **one full turn (10 segments) after the pursuit started**, and only if the state is on
  at that boundary.
- Not part of this test: casualties, nearby enemies, `CantRally`, fear, hatred, frenzy and the Independent toggle.
  AI regiments never get the state on, so they never test.

## 2. State

| State | Set | Cleared / changed |
|---|---|---|
| **pursuing** | pursuit start (`StartPursuit`) | pursuit end (Re-group: the `Rally` opcode of script 163), rout, removal |
| **rally-attempt** (on/off) | toggled by order 0x14; switched **on** automatically only when a player regiment with **Independent** set **routs** (not when it starts a pursuit) | switched **off** at pursuit start and at rout start (both reset the movement state), and by the `Rally` opcode (script 163) |
| **scheduled segment** (1–10) | set to the **current segment number** at pursuit start, and also at rout start (the same value is shared by the flight rally attempts, but each start overwrites it) | after each scheduled check that runs, `s := s − 3`, and if that is below 1, `s := s + 10` (i.e. 10 → 7 → 4 → 1 → 8 → 5 → 2 → 9 → 6 → 3 → 10 …) |

**Segment numbers.** A turn has 10 segments of 19 ticks each. The game numbers them **10, 9, 8 … 1**, counting down;
after segment 1 comes segment 10 of the next turn. A segment boundary is the tick on which the number changes
(the tick on which break tests and melee also resolve). "Equal to the scheduled segment" is tested against the
**new** number on that boundary tick. With numbers counting down, `s − 3` wrapped is exactly **3 segments later**.

Consequences:
- At pursuit start `s` = the current segment number, so the first boundary with that number again is **10
  boundaries (one turn) later**.
- If the rally-attempt state is **off** at the scheduled boundary, nothing happens and `s` is **not** advanced. The
  next chance is then a full turn later at the same number, not 3 segments later.
- Turning the state on between scheduled boundaries does not trigger a roll early. The roll waits for the next
  boundary whose number equals `s`, which may be 1 to 10 segments away.

## 3. The order (0x14 "Rally")

- **Who**: player regiments only (orders never apply to AI regiments). Any class. Accepted while the regiment is
  **pursuing or broken**. For any other regiment the order does nothing. The Rally button appears on the
  broken/pursuing command panel (`game_rules.md` "Battle HUD").
- **Effect**: rally-attempt := not rally-attempt. Nothing else changes: no shout or message (no `React`), no halt, no
  re-form, no restart of the script, and the scheduled segment is unchanged.
- **Repeat presses** toggle back and forth. An even number of presses between two scheduled boundaries leaves the
  state as it was.
- **Carry-over**: none. Pursuit start and rout start both reset the movement state, so a press made before a
  pursuit (or during a previous rout) does not carry into it. The order is checked every tick, whatever script the
  regiment is running.
- 🟡 Whether the HUD shows the on/off state (e.g. a pressed button) was not traced. The button art is the same open
  hand as Halt.

Other orders while pursuing (unchanged, `pursuit_map_edge.md` §5): Withdraw, Magic, Halt (shout only),
Independent and Fight harder pass the order gate; move/attack/turn/rank/charge/fire orders are ignored.

## 4. The restraint test

Performed on the scheduled boundary (§2) when the rally-attempt state is on:

1. Reschedule: `s := s − 3`, wrapping to 1–10.
2. If the regiment has **`AlwaysPursue`**: no roll; the pursuit continues. (No shipped battle uses `AlwaysPursue`.)
3. Otherwise roll `r` uniform in 2…12 and **pass if `r ≤ effective Ld`**, where effective Ld = the leader model's Ld
   if the regiment has a living leader with non-zero Ld, otherwise the Ld of its first model
   (`game_rules.md` "Effective Leadership").
   - **No modifier**: unlike the flight rally test there is no casualty modifier, no `casualties ≥ 3 × size`
     refusal, no `CantRally` refusal, and no "enemy within 160 units" condition.
   - "Fight harder" (+1 Ld for one segment) would apply if set, as in every Leadership test, but that order is
     only offered on melee panels, so it does not arise for a pursuer.
4. **Pass**: event 0x10 is sent to the regiment. **Fail**: nothing; the state stays on.

Pass probability: `(Ld − 1) / 11`, i.e. Ld 6 → 5/11 (45 %), Ld 7 → 6/11, Ld 8 → 7/11, Ld 9 → 8/11, Ld 10 → 9/11.

On the same boundary the rest of the pursuit update still runs (target check, re-aim, chase budget, edge probe;
`pursuit_map_edge.md` §2), and may itself send event 0x10. One stop is enough; a second event 0x10 changes nothing.

## 5. After a pass

Event 0x10 is handled at the start of the regiment's next update (before movement, so it takes no further pursuit
step):
1. `React 17`: the "Re-group!" bark (Dwarfs: "Rally!"), with its message and portrait as for any reaction
   (`script_behaviours.md` §3.3);
2. the re-form script 163: the `Rally` opcode ends pursuing (and charging/braced), **switches the rally-attempt
   state off**, halts the regiment, and re-forms it to its script rank count around its current position in the
   walk-back mode (`reform_while_moving.md` §6);
3. when the figures have settled: a final re-form to the script ranks, then the regiment's main script restarts.
   A player regiment then waits for orders.

Nothing returns the regiment to where the pursuit started. A fail has no bark, message or animation.

## 6. Test vectors

Regiment P: player cavalry, effective Ld 7, pursuing since the boundary into segment 6 (so `s` = 6), rally-attempt
off unless stated. "Boundary → n" = the boundary tick on which the segment number becomes n.

| Before | Action | After |
|---|---|---|
| P pursuing, rally-attempt off | player presses Rally | rally-attempt on; nothing else (no shout, `s` = 6) |
| P, rally-attempt on | player presses Rally again | rally-attempt off |
| P not pursuing and not broken | player presses Rally | no change |
| P, on, `s` 6, segment 9 | boundary → 8 | no roll (8 ≠ 6) |
| P, on, `s` 6 | boundary → 6 (one turn after the pursuit start) | `s` := 3; roll 2–12; roll 7 ≤ 7 → **pass**: event 0x10; next update "Re-group!", pursuit ends, re-form, rally-attempt off |
| same, roll 9 | boundary → 6 | `s` := 3; **fail**; still pursuing, state on |
| after that fail | boundary → 3 (3 segments later) | `s` := 10 (3 − 3 = 0 → +10); roll again |
| P, on, `s` 2 | boundary → 2 | `s` := 9 (2 − 3 = −1 → +10) |
| P, **off**, `s` 6 | boundary → 6 | nothing; `s` stays 6 (next chance: boundary → 6 a turn later) |
| P off, `s` 6; Rally pressed during segment 5 | boundaries → 4, 3, 2, 1, 10, 9, 8, 7 | no roll; first roll at boundary → 6 |
| P with `AlwaysPursue`, on, `s` 6 | boundary → 6 | `s` := 3; no roll; pursuit continues |
| P, 3 × casualties ≥ size, `CantRally` set, enemy 50 units away, on | boundary → `s` | roll as usual with no modifier (none of these matter here) |
| P, leader dead, first model Ld 6, on | boundary → `s` | pass on 2–6 only (5/11) |
| P Independent, pursuing, never pressed Rally | any boundary | never rolls (Independent does not switch the state on for a pursuit) |
| P Independent, broken (rout started while Independent) | — | rally-attempt on automatically at the rout (flight rally attempts, `game_rules.md` "Rally") |
| AI regiment pursuing | any | never rolls |
| P pursuing with rally-attempt on, then the pursuit ends for another reason (target gone, edge) | Re-group | rally-attempt off (the `Rally` opcode); a later pursuit starts with it off |

## 7. Corrections to earlier notes (applied)

- `game_rules.md` "Player orders" (Independent): Independent does **not** make a pursuing regiment test pursuit
  restraint. It switches the rally-attempt state on only when the regiment routs. Pursuit restraint is tested only
  after the Rally order.
- `pursuit_map_edge.md` §2 step 1 and §5: the same correction; the 🟡 there is resolved.

## 8. Uncertainties

- 🟡 HUD indication of the rally-attempt state (§3).
