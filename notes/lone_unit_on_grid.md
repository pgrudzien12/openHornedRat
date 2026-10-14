# When a unit's last enemy leaves its combat grid: event 0x19 vs 0x30 (GitHub #340)

Public implementation report. It settles which release a unit in melee gets when its last enemy leaves the battle
grid, for every way an enemy can leave. It also defines the "engaged enemy" used by the per-tick pairing.

Companion reports, cited rather than repeated:

- `game_rules.md` §5.7 ("Every caller" table, "Opcode 0x53 in full", "Event dispatch is pre-emptive").
- `terror_contact_charge.md` §0.5–§0.7 and §2 (the lone causer and 0x30).
- `movement_formation.md` §6 `LeaveSharedGrid` and "Left combat".
- `script_queries.md` §9 (`Query 22/23`), `script_behaviours.md` §2.9 (who engages whom), and
  `runaway_routers_broken.md` §1A (routing footprints) and §3 (`Rally`).
- `bf010_reserves_and_rout_reactions.md` (shooters send themselves 0x19).

**Corrections made by this report:**

- `movement_formation.md` §6 said the opponent left behind by `LeaveSharedGrid` "finds no enemy, leaves G and receives
  event 0x19". That is wrong when it is the only unit left: it gets **0x30**. Corrected there.
- The `game_rules.md` caller-table row for the per-tick pairing was right but incomplete. That 0x19 only happens while
  **another unit is still on the grid**, and it arrives with the unit's **target already cleared**. Clarified there.
- The `DropTarget` paragraph's "every non-broken unit that had a target then switches to 163" is true. The per-tick
  pairing's 0x19, however, is a case where the unit **has no target any more**. Noted there.

## 0. Shared state first

1. **One field: the engaged enemy is the current target.** The per-tick pairing uses the unit's script **current
   target** (the same field `DropTarget`, `EnemyRouted`, `TargetGone` and `AIQuery` case 5 read). There is no separate
   "engaged enemy". The per-model opponents (pairing) are a separate thing: they are used only by the "find another
   enemy" search (point 4).
2. **The per-tick pairing step looks at the number of units on the grid, not at sides.** For a unit in melee, every
   tick, in its formation step:
   - **no grid at all** → event **0x0C** to itself (only an engine bug can produce this state; see point 6);
   - **it is the only unit on its grid** → event **0x30** on every tick whose segment differs from the grid's creation
     segment, and nothing during the creation segment. Nothing else happens: no leaving, no target change, no
     pairing. It stays in melee and on the grid until a script handles the 0x30;
   - **two or more units on the grid (any side)** → ordinary pairing, which may end in **leave + 0x19** (point 3).

   So **"alone" means alone on the grid, whatever the side**. Two friendly units left on a grid after their enemy
   has gone are not alone, and neither gets 0x30 while both are on it.
3. **When the pairing step sends 0x19.** It only happens when two or more units are on the grid. The step depends on
   the unit's pairing mode (`game_rules.md` §5.7: owner or joiner pairing mode) and on its current target:

   | Pairing mode | Current target | What the step does |
   |---|---|---|
   | joiner | none, **or** a unit that is not on a grid | run the search (point 4). Found → current target := it. **None → current target := none, the unit leaves the grid, event 0x19** |
   | joiner | a unit on a grid | pair its models against that unit (ordinary pairing) |
   | owner | **none** | **nothing at all** (no pairing, no search, no event) |
   | owner | a unit that is not on a grid | same as joiner: search; none → target := none, leave, 0x19 |
   | owner | a unit on a grid | ordinary pairing, and the drop back to joiner mode when that unit has fewer than two thirds of this unit's models (`game_rules.md`) |

   Note the order. **The target is overwritten with the search result before 0x19 is queued**, so the unit receives
   0x19 with **no target**.
4. **The "another enemy" search** is the one of `game_rules.md` §5.7 ("no enemy remains"). It walks the unit's own
   models in model order and returns the unit of the first model's paired opponent that is not the departing unit,
   is on a grid, and is on the hostile, non-neutral side. It is not geometric.
5. **Script handlers run before the pairing step.** Event dispatch happens at the start of the unit's script step
   (`game_rules.md`, "Event dispatch is pre-emptive"), and the script step comes before the formation step within
   the unit's turn. If a script switch is made, the new script runs at once in the same step. So any event the
   departing enemy sent (0x0F rout, 0x16 removed) is **handled before this unit's next pairing step**. If the handler
   takes the unit off the grid, the pairing step does not run at all, because the unit is no longer in melee.
6. **Leaving a grid always ends melee.** Every way out of a grid clears in-melee, has-a-grid and the owner pairing
   mode together. An engine must never leave a unit in melee without a grid (that would produce 0x0C every tick).
7. **What the library does with the two releases** (library 152; the player, AI, shooter and mission handlers all
   pass both events through to it unchanged):
   - **0x30**: `LeaveSharedGrid` (true while still on a grid), then **switch to 163** (halt, re-form, `Restart`)
     **unless broken or pursuing**.
   - **0x19**: `DropTarget`. **Only if it had a target** (and is not broken): the "Re-group!" bark if pursuing, then
     **switch to 163**. With no target, `DropTarget` is false and **nothing happens**. The unit returns to the
     interrupted script, which for a unit that was in melee is **165, the endless idle loop**.

   Put together: a unit that receives the **per-tick pairing's** 0x19 ends up off the grid, not in melee, with no
   target, **not re-formed** (its figures walk back to their old slots under the catch-up walk), and idling in 165
   until some later event (contact, enemy spotted, a message, an order) moves it on. 🟡 This is the original's
   behaviour as read from the rules; it has not been observed on screen. It looks like an oversight in the original
   rather than a design choice. An engine may decide to send such a unit to 163, but it should treat that as a
   deliberate deviation.

## 1. Q1 — the engaged enemy (= current target): who sets it, who clears it

| Event | Effect on the current target |
|---|---|
| ordinary (non-charging) engagement on contact | **both** units: each one's target := the other; 0x1A goes to the engager's previous target if that differs (`script_behaviours.md` §2.9) |
| engagement as charger | **charger only**: target := defender (0x1A to its previous target if different). The **defender's target is unchanged** (`terror_contact_charge.md` §0.7), so it may be none or an unrelated unit |
| fear refusal at contact | mover's target := the feared unit (`terror_contact_charge.md` §0.1) |
| `EnemyRouted` (0x53) in melee, another enemy found | target := that enemy (`game_rules.md`) |
| `TargetGone` (0x56), `Query 22/23` in melee, another enemy found | target := that enemy |
| per-tick pairing, target not on a grid | target := search result, **possibly none** (§0.3) |
| `DropTarget`, the three flee opcodes | cleared |
| script/order targeting (`Attack`, `Charge`, `SetTarget…` ops) | set as documented for each opcode |

`TargetGone` and `Query 22` (and the shooters' self-sent 0x19 path) **keep the target** when they find no other enemy.
Their 0x19 or "true" therefore does lead to 163. Only the per-tick pairing clears it first.

## 2. Q2 — each way the last enemy can leave

Setup: my unit A is in melee on grid G with enemy E. "Alone" means A is the only unit left on G after E leaves.
`seg` is the current segment and `s0` is G's creation segment. "0x30 path" means: 0x30 on A's formation step on every
tick with `seg ≠ s0`. It is dispatched at A's next script step, where `LeaveSharedGrid` and the switch to 163 happen
(unless A is broken or pursuing), so A is off G one tick after the 0x30.

| How E leaves | E is A's target? | A alone? | What A gets |
|---|---|---|---|
| **E routs** (and a withdraw against a living enemy, which *is* a rout, `game_rules.md` order 0x13) | yes | either | **0x0F → `EnemyRouted`** at A's next script step, before any pairing. In melee: another enemy found → switch to it, stay in melee. None → pursue (164, whose first instruction `LeaveSharedGrid` takes A off G in the same step). Shooters: self-sent 0x19 with target kept → 163 (`bf010_…` report). **No 0x30, no pairing 0x19** |
| E routs | no | yes | 0x0F ignored (not its target) → **0x30 path → 163** |
| E routs | no | no | 0x0F ignored → per-tick pairing (§0.3): A's target is none or not on a grid → search → none → **leave + 0x19, target none → idle in 165**. A target that is still on a grid → A keeps pairing towards it (🟡 a grid other than G) |
| **E destroyed** (last model removed; the removal is broadcast as 0x16) | yes | either | **0x16 → `Query 22`** first: in melee, no other enemy → **leaves G, 0x19 with target kept → 163**. Another enemy found → switch, stay |
| E destroyed | no | yes | `Query 22` does nothing for A (only clears a threat slot or parent naming E) → **0x30 path → 163** |
| E destroyed | no | no | → per-tick pairing as in row 3 (**leave + 0x19, target none → idle**) unless A's target is on a grid |
| **E removed alive by a script** (quiet removal: **no** 0x16 broadcast) | either | yes | **0x30 path → 163** |
| E removed alive by a script | yes / no | no | target E is no longer on a grid → search → none → **leave + 0x19, target none → idle** |
| **E fled off the table** | n/a | n/a | it already left G when it routed (row 1–3). The later 0x0E runs `Query 23`; for a unit not in melee whose target is E this means 0x19 with target kept → 163 |
| **E leaves by `LeaveSharedGrid`** (pursuit 164, its own 0x30 or `TargetGone` handler, …) | either | yes | no event reaches A → **0x30 path → 163** |
| E leaves by `LeaveSharedGrid` | either | no | per-tick pairing → **leave + 0x19, target none → idle** (or keep pairing towards a target that is on a grid) |

Priority, in short: **(1)** a script handler for an event that E sent and that names A's target (0x0F, 0x16) always
acts first. **(2)** Otherwise, if A is alone, it gets 0x30 (from the first tick of the next segment if G is still in
its creation segment). **(3)** Otherwise it gets the pairing step's 0x19 (target cleared). **(4)** 0x0C never happens
in a correct engine.

Two more details:

- When A is a **placed building or furniture** pseudo-unit (side code 0x20) and is the one left, it leaves the grid
  as part of the departing unit's leave (`movement_formation.md` §6) and gets no event.
- The 0x30 is re-sent **every tick** until handled. It is handled at the very next script step, so in practice it
  comes once. If A's interrupt handling is held (for example a high-priority script that ignores 0x30), A keeps
  receiving it.

## 3. Q3 — same-tick ordering with 0x0F → `EnemyRouted`

- Yes. When the router is A's current target, the 0x0F is handled at A's **next script step**, and that always
  comes before A's next pairing step (§0.5). This holds whether A comes before or after the router in the unit
  order: if A comes earlier, the next tick; if later, the same tick. Pursuit (164) runs `LeaveSharedGrid` in that
  same script step, so A is no longer in melee when its formation step comes, and neither 0x30 nor the pairing 0x19
  can follow.
- If `EnemyRouted` **switches** A to another enemy (found by the search), A stays in melee. Its pairing step then
  runs normally against the new target: no 0x19, and no 0x30 because the new enemy is on the grid.
- So A cannot get both the 0x0F handling and a pairing 0x19 for the same rout. The only overlap possible is when
  A's handler is held so that the 0x0F is not dispatched (🟡, not seen in shipped handlers). In that case a lone A
  gets 0x30. Its handler is harmless for a pursuer (`LeaveSharedGrid`, then no 163 while pursuing).

## 4. Q4 — friends left on the grid, no enemy (two of mine, A and B, vs router R)

- After R leaves, G holds A and B (count 2). **Neither is alone**, so neither gets 0x30 yet.
- If R was a unit's target, that unit handles 0x0F first (§3): it pursues or switches. A pursuer leaves G at once.
- For a unit whose target was not R, the pairing step runs. A unit in **joiner** mode with no target (or a target
  not on a grid) runs the search → none → **leaves G, 0x19 with no target → idle in 165**. A unit in **owner** mode
  with **no target** does **nothing** and stays in melee on G.
- As soon as one of them has left, the other is **alone**: **0x30 path → 163**, and the grid is freed when it
  leaves (or ownership passes on, as in `movement_formation.md` §6).
- Units are processed in the fixed unit order, so it is always the unit whose pairing step runs first that takes
  the 0x19, and the other gets the 0x30.
- The grid stays as long as at least one unit is on it.

## 5. Q5 — routing footprints in collision passes

Confirmed, as in `runaway_routers_broken.md` §1A. Every **other** unit's collision pass skips a routing footprint
completely: no push, no fear test, no contact record, no contact attack. The router's own pass still runs. Against
an overlapping non-routing enemy it only triggers that enemy's forced contact attacks on it. Friends never push it.
Solid scenery pushes it. **A building pushes it unless the mover is charging or in melee**, and a router is neither,
so buildings **do** push routers. Removing the engine's exemption is correct. Edge correction does not apply to a
routing unit.

## 6. Test vectors

Notation: G has creation segment `s0`. A is in melee on G. "t" is the tick on which E leaves (during E's turn), and A's
turn comes after E's in the unit order unless stated. `→163` means A's script switches to the halt / re-form / `Restart`
script.

| # | Before | Event | A's next ticks | A in melee after? |
|---|---|---|---|---|
| 1 | A, E on G; A.target = E; seg ≠ s0 | E routs (t) | t: 0x0F dispatched → `EnemyRouted`: no other enemy → 164, `LeaveSharedGrid` (G freed) → pursuing | no (from t) |
| 2 | A, E on G; A.target = none (E charged A); seg ≠ s0 | E routs (t) | t: 0x0F ignored; formation step: alone → 0x30. t+1: 152 case 48 → leaves G (freed) → 163 | until t+1 |
| 3 | as 2, but seg = s0 and 7 ticks of s0 remain | E routs (t) | t … t+6: alone, **no event**, stays in melee. t+7 (first tick of the next segment): 0x30. t+8: leaves → 163 | until t+8 |
| 4 | A, E on G; A.target = E | E's last model removed (t) | t: 0x16 → `Query 22`: no other enemy → leaves G, 0x19 (target E kept). t+1: `DropTarget` true → 163 | no (from t) |
| 5 | A, E on G; A.target = T (another enemy on another grid… or none) | E's last model removed (t) | `Query 22`: nothing (E ≠ target). Formation step: alone → 0x30 (seg ≠ s0). t+1 → 163 | until t+1 |
| 6 | A, E on G; any target | E removed by script, quietly (t) | no event; alone → 0x30 → t+1 → 163 | until t+1 |
| 7 | A, B (mine), R on G; A, B targets none; A joiner, B owner; A before B | R routs (t) | t: A: 0x0F ignored; pairing: target none → search none → **A leaves G, 0x19 (target none)**. B: now alone → 0x30 (seg ≠ s0). t+1: A: `DropTarget` false → **A idles in 165, off G, not re-formed**. B: 0x30 → leaves G (freed) → 163 | A: until t; B: until t+1 |
| 8 | as 7 but A owner, B joiner, A before B | R routs (t) | t: A (owner, no target): **nothing**. B: pairing: target none → leaves G, 0x19 (none). t+1: A: alone → 0x30; B: idles in 165. t+2: A → 163 | A: until t+2; B: until t |
| 9 | as 7 but A.target = B.target = R | R routs (t) | t: each handles 0x0F → no other enemy → 164 → `LeaveSharedGrid`; both pursue | no (from t) |
| 10 | A, B (mine), E on G; A.target = E, B.target = E | E's last model removed (t) | t: each `Query 22` → no other enemy → leaves G, 0x19 (target E kept). t+1: each → 163 | no (from t) |
| 11 | A shooter (handler 156), A.target = E, in melee | E routs (t) | t: 0x0F → condition true → self 0x19 (target kept) → `DropTarget` true → 163 | (`bf010_…` report) |
| 12 | A broken (routing) and alone on G | — | cannot occur: a rout leaves the grid | — |

**Invariants an engine can assert**

- The pairing step never sends 0x19 to a unit that is alone on its grid. A lone unit's only release from the pairing
  step is 0x30.
- 0x30 never comes during the grid's creation segment.
- After the per-tick pairing's 0x19, the unit has no target and no grid and is not in melee.
- No unit is ever left in melee with no grid.

## 7. Differences from the implementer's current model

| Engine case | Original |
|---|---|
| (a) only a "charger's partner routed before the grid existed" fight is marked alone and gets 0x30 | **every** unit that is the only unit on its grid gets 0x30 (outside the creation segment), whatever the reason |
| (b) all touched units inactive → leave at once + 0x19 | if A's target was the destroyed unit and it was broadcast (0x16): `Query 22` makes A leave + 0x19 **with the target kept** → 163. A quiet script removal, or a destroyed unit that was not A's target: **0x30** if A is alone, otherwise the pairing step's leave + 0x19 **with the target cleared** (→ idle) |
| (c) opponent routed and left → leave at once, no event | the target case: 0x0F → `EnemyRouted` (unchanged). Not the target: **stay in melee and get 0x30** (alone), or the pairing step's leave + 0x19 (not alone). **Never a silent leave**, and this is the fix for the stuck unit |
| geometry ("no longer touches any enemy footprint") decides | **nothing geometric** (`game_rules.md`: "There is no geometric disengagement"). Grid membership, the unit count and the target decide |
| no engaged enemy separate from the current target | ✅ correct: they are the same field |
| routers exempt from building pushes | ✗ buildings push routers (§5) |

## 🟡 Open items

- §0.7: a unit idling in 165 after the pairing step's target-less 0x19 has not been confirmed on screen. Whether an
  engine copies this is a design decision for the project.
- A current target that is on a *different* grid from the unit's own (§2 rows 3 and 6): the pairing step pairs
  towards it. How the cells behave in that case was not traced, and it should be rare.
- When the owner pairing mode is entered was not re-traced here. The table in §0.3 only needs the mode as it stands.
