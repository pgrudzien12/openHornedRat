# Close-combat grid: closing gaps after casualties, who may strike whom, and deaths during a charge

Clean-room behavioural handoff for the implementer. It extends `game_rules.md` "Battle grid procedure
(implementation specification)" and "Engagement: battle grid and pairing" (§5.7). Read those first; this report
does not repeat seeding, the 17 × 17 frame, the joiner's two/four candidate cells or the leave conditions. Static
research; the original was not run.

## 0. Model states used below

The rules below depend on the *state* a model is in, not on distances. An engine needs these states per model
(its own representation):

| State | Meaning |
|---|---|
| **placed** | holds a grid cell (the cell stays reserved for it until it dies or is moved) |
| **paired** | has an opponent model (and that model's unit) |
| **at rest** | its walk to its cell has finished; an at-rest model in a melee unit is **not stepped and not re-tested** |
| **fighting** (in hand-to-hand) | it reached its cell **while paired**: only fighting models strike |
| **reserve** | walking to (or waiting in) a cell next to a comrade, not paired; ignored by the pairing searches |
| **pausing** | timed pause (charge start stagger, rout turn): ignored by the joiner search |
| **dying** | wounds ≥ W, death delay running |

**Arrival is an event, not a distance test.** A model becomes fighting at the moment the walk mover finds it
within 3 units of its cell (`ARRIVAL_DISTANCE`) — and the mover only looks at models that are **not at rest**.
A model that is already at rest when it gets an opponent does **not** become fighting by standing in its cell;
something must wake it (take it out of at rest) first. This one rule answers most of question 2 (§3).

## 1. Short answers

1. **Gaps close by re-placement, every tick.**
   (a) Owner: each unpaired, placed, non-reserve model first looks for an enemy model at Manhattan distance 1 that
   is **at rest**. If none, it moves to a free cell beside the **nearest fighting-or-paired, at-rest comrade** (§2.2).
   All such models move in the same tick, with no cap. The closest (model, comrade) pairs are served first.
   (b) Joiner: a model whose opponent died (or that never found one) is **re-collected by the joiner search**
   (up to `frontage` models per tick, model-list order). Its current cell is offered back to it, so it keeps its
   cell if that cell is still adjacent to the nearest enemy model. Otherwise it moves (§2.1).
   (c) Rear-rank models step forward through **reserve release**: whenever one of a unit's own models is removed,
   all of that unit's reserves are released on the next tick and searched again. There is no "step into the dead
   comrade's cell" rule; the freed cell is simply available to the searches.
   (d) No: a melee never ends because nobody is adjacent. Leaving is only by the state conditions of §5.7. The
   searches above keep refilling contact, so the stall you describe (row 7 empty for 700 ticks) does not persist
   in the original.
2. **Yes, a fighting model strikes its opponent wherever that opponent is.** There is no arrival or distance check
   on the victim, a hit counts, and a killed figure dies **where it stands**. But in the original a defender
   almost never gets an un-arrived opponent, because a model that is **back-paired while at rest does not start
   fighting until its new opponent arrives** (§3). Your engine's "arrived = within 3 units of the cell" makes
   every defender in its cell fight at once; that is the bug behind symptom B.
3. **Pairing is not forced symmetric.** When A takes B, B takes A **only if B has no opponent**. Up to 4 attackers
   can share one victim (one per orthogonal cell). The victim fights only its own opponent. Every extra attacker
   gets +1 WS (`game_rules.md` §5.2, "ganging up"). A striking model **grabs** a victim that has no opponent (§4).
4. **No.** A charging unit that is not broken has no figures killed by contact before engagement. Contact attacks
   only hit a **broken (routing)** unit: a charger or pursuer that touches it, or **any** enemy unit whose
   footprint a broken unit runs into. Behaviour 14 (`ThreatInReach`, peasants and sheep only) is the one exception,
   with the hits landing on the script's own unit (`script_behaviours.md` §1). So before contact only shooting,
   magic and fanatics can kill a charger's figures. Deaths "before the charge ends" are either close-combat
   deaths of figures already paired on the grid (the charge state ends at engagement, before the figures have
   walked in), or an engine bug.

## 2. Gap closing in detail

### 2.1 Joining unit (every tick, `game_rules.md` step 3, refined)

1. **Collect** up to `frontage` own models in model-list order that are **not paired, not reserve, not pausing,
   not a war machine** — whether or not they already hold a cell. Models whose opponent died, models that never
   found a cell, and reserves that have arrived all qualify.
2. **Candidates**: every (collected model, enemy model) pair, where the enemy model is a placed model of the unit's
   **current opponent unit** (not of other units on the grid). Pairs are sorted by straight-line distance,
   ascending, over the whole batch.
3. Walk the sorted pairs. For a model not yet placed this tick, try the cells orthogonally next to that enemy model.
   There are 2 candidates while the model is farther than 18 units, 4 at ≤ 18, in the attack-side order below.
   Cells outside 0..16 are skipped. **A model that already holds a cell has that cell counted as free during its
   own search**, so it may keep it.
4. On success the model is placed and paired with that enemy model. The enemy model is paired back only if it has
   no opponent. If the cell changed, the model gets a new walk target, is woken and walks. If the cell is
   unchanged, its target and its at-rest state are left as they were (🟡 §6).
5. Models still unplaced become **reserves**: each takes a free cell beside the nearest placed own model that is
   paired or reserve (a reserve comrade counts as 96 units farther). Same candidate order. They walk there
   unpaired and are collected again after arriving.

Candidate order (cells relative to the enemy model; "side" is fixed at engagement from the attack direction):

| attack side | 1st | 2nd | 3rd | 4th |
|---|---|---|---|---|
| A | row + 1 | col − 1 | col + 1 | row − 1 |
| B | row − 1 | col − 1 | col + 1 | row + 1 |
| C | col + 1 | row + 1 | row − 1 | col − 1 |
| D | col − 1 | row + 1 | row − 1 | col + 1 |

The first cell faces the attacker's side, the next two are the flanks and the last is the far side, as
`game_rules.md` already states. The grid owner itself uses side A when it switches to the joining procedure.

### 2.2 Grid owner (every tick, step 5, refined)

For each own model that is placed, not paired and not reserve, in model-list order:

1. **Adjacent enemy**: the first model of the **current opponent unit**, in that unit's model-list order, that is
   placed and **at rest** at Manhattan distance 1. Pair with it, wake this model (it re-arrives in its cell and
   starts fighting next movement step) and pair the enemy back if it has no opponent. **A walking enemy model is
   not taken**, so the owner never initiates against an enemy that has not arrived.
2. **Otherwise move beside a comrade.** Every own model that is **paired, placed and at rest** is a candidate
   comrade. All (unpaired model, comrade) pairs of this tick are sorted by distance and served nearest-first.
   Each model moves at most once per tick, no cap. For a pair, up to three cells next to the comrade are tried,
   **the comrade's neighbour cells on the model's side first**:

   | model relative to the comrade | cells tried (relative to the comrade) |
   |---|---|
   | behind it, same column or to its lower-column side | row + 1 (between them), col + 1, col − 1 |
   | behind it, to its higher-column side | col + 1, row + 1 |
   | in front of it, same column or lower-column side | col − 1, row − 1 |
   | in front of it, higher-column side | col + 1, row − 1 |
   | same row, higher-column side | col + 1, row + 1, row − 1 |
   | same row, lower-column side | 🟡 **none** in the original. The code tests the wrong axis, so this case gets no candidate. An engine should offer col − 1, row − 1, row + 1 |

   ("behind" = higher row number; rows grow from the owner's front rank backwards.)
   - If a candidate is the model's **own** cell, it stays where it is and becomes a **reserve**, standing ready.
   - If a candidate is free, the model releases its old cell, takes the new one, becomes a **reserve** walking to
     it, and **copies the comrade's opponent as its intended opponent** (not paired yet).
   - When it arrives, its reserve state clears and it is searched again (step 1) on a later tick.
3. When the owner has more than 1.5× the enemy's model count it switches to the joining procedure of §2.1 for
   the rest of the fight. BF003: 20 goblins vs 12 cavalry, `20 × 2 > 12 × 3`, so **the goblins switch at once**
   and both sides use §2.1.

### 2.3 Reserve release (both sides)

When a unit loses a model (the figure is removed at the end of its death delay), the unit is marked "lost a model
this tick". On its next pairing pass **every reserve of that unit stops being a reserve** and is searched again by
§2.1 or §2.2. That is how models waiting beside or behind fighting comrades move up when a comrade falls. Nothing
else releases a reserve that is standing still.

### 2.4 When a model's opponent dies

(`game_rules.md` "When a model's own opponent dies".) If the dead model's opponent was **this** model, this
model is demoted: it is no longer paired or fighting and is **woken**, but keeps its cell. It re-arrives at once,
unpaired and at rest, and is then picked up by §2.1/§2.2. A ganging attacker, whose victim was fighting someone
else, is unpaired at its next strike attempt instead ("weapon ready"). That attacker **stays at rest**, which
matters for §6.

## 3. Who may strike whom (question 2)

- A model strikes in the melee round if it is **alive and fighting** (paired and arrived). The victim is its
  opponent model, **whatever the victim's own state**: walking, reserve, at rest, far away. A hit wounds, and
  a killed victim dies at its current figure position. There is no "too far" rule.
- When does a model become fighting? Only by an arrival (§0), i.e. when it is woken and the mover finds it within
  3 units of its cell. Waking happens when:
  - **its own placement moves it** (new cell): it walks there, arrives, fights;
  - **owner adjacency pairing** (§2.2 step 1): woken, arrives next step;
  - **its opponent arrives** and names it: the arriving model wakes its opponent if that opponent has none, or
    already names the arriving model but is not yet fighting. Higher `s_pntval` and war-machine steals are as
    in `game_rules.md` "Retargeting";
  - **it is grabbed**: an enemy strikes it while it has no opponent (§4);
  - **its opponent died** (demotion wakes it, §2.4).
- **Back-pairing does not wake.** When a joiner model is placed next to a defender who is at rest in its cell, the
  defender is paired back but stays at rest. It **starts fighting only when the joiner model arrives** and wakes
  it. So the normal sequence is: the joiner walks in, arrives, fights; the defender is woken the same moment and
  fights back from its next movement step. A walking joiner is not struck by its defender.
- The narrow exception: a defender whose own opponent has just died is awake for the one tick it needs to
  re-arrive. If in that tick a far joiner model is placed next to it and back-paired, it arrives paired and can
  strike that joiner while it is still walking. This is rare and short-lived.

**Fix for symptom B**: keep "at rest" as a real state. Test arrival only for awake models. Do not make a
back-paired at-rest model fight; wake it when its opponent arrives.

## 4. Pairing symmetry (question 3)

| Event | A (acting model) | B (the other model) |
|---|---|---|
| joiner placement A → beside B | paired with B; walks if its cell changed | paired with A **only if B has no opponent**; **not woken** |
| owner adjacency A ↔ B (B at rest) | paired with B, woken | paired with A only if B has no opponent; not woken |
| A arrives (paired with B) | fighting; faces B | if B has no opponent, or B names A but is not fighting yet → B paired with A and woken. If B fights someone else → B is stolen only if A's unit has a higher `s_pntval` than B's current attacker's unit, or B's current opponent is a war machine |
| A strikes B, B has no opponent | — | B **grabbed**: paired with A, woken, no longer reserve |
| A strikes B, B fights C | A gets +1 WS | unchanged |

B never loses an existing opponent through the first two rows. One victim can have up to 4 attackers (its 4
orthogonal cells). Each attacker strikes it in its own round, and the victim strikes back only at its own
opponent.

## 5. Deaths before contact (question 4)

Contact attacks (`game_rules.md` §7.7, reach 12 / 18 cavalry / 24 monsters, once per segment per attacking unit)
fire only in these situations:

| Situation | Attacking unit | Victim unit |
|---|---|---|
| a charging or pursuing unit's footprint touches a **routing** unit | the charger/pursuer | the routing unit |
| a **broken** unit's footprint, while it moves, touches any enemy unit | that enemy unit (it need not be charging) | the broken unit |
| behaviour 14 `ThreatInReach` (peasants, sheep; `script_behaviours.md` §1) | every charging or pursuing unit within range, any side | the script's own unit |

A charging, unbroken unit is never the victim, so its figures die only to shooting, magic and fanatics before
engagement. At engagement its charge state ends at once (`game_rules.md` "Why the charger disperses"), so "dying
while still running in" means figures that are already paired on the grid. With the §3 rule, these can only be
hit by defenders whose own opponent has arrived, i.e. by defenders that are already fighting someone. Check that your
defenders are not fighting walking chargers.

## 6. Uncertainties and original quirks

- 🟡 **Re-placed into the same cell while at rest.** A ganging attacker unpaired by its victim's death (§2.4) is at
  rest and unpaired. The joiner search re-collects it. If its best candidate is its own cell, it is paired again
  **without being woken**, so it holds an opponent but never fights, and it is no longer collected (it is paired).
  It recovers only if its new opponent arrives or strikes it. This looks like an original defect that can leave
  single models idle. An engine should wake a model whenever it receives a new opponent while at rest, and treat
  that as recommended, not as compatibility.
- 🟡 The "same row, lower-column side" owner case of §2.2 gets no candidate in the original (wrong-axis test). An
  engine should use the symmetric rule.
- 🟡 Reserve-in-place (§2.2: the model's own cell is a candidate) leaves an at-rest reserve that only reserve
  release (§2.3) frees. Harmless in practice, because a fight produces casualties every round.
- 🟡 Unit processing order within a tick decides the narrow window of §3 (a defender striking a walking joiner). It
  was not traced.

## 7. Differences from the current engine

| Engine now | Original |
|---|---|
| "arrived" = within 3 units of the cell, any time | arrival is an event for **awake** models only; at-rest models are not re-tested |
| a back-paired defender fights at once | stays at rest; woken when its opponent arrives |
| owner: no "move beside comrade" | §2.2 step 2, every tick, nearest pairs first, then reserve until arrival |
| joiner never re-places a model with a cell | every unpaired, non-reserve, non-pausing model is re-collected (≤ frontage per tick); its own cell counts as free in its search |
| no reserve release | a unit's reserves are released on the tick after it loses a model |
| owner pairs with any adjacent enemy | only with an **at-rest** adjacent model of its current opponent unit |
| (unknown) owner ratio switch | 20 vs 12 → the owner switches to joining at once (> 1.5×) |

## 8. Test vectors

Grid coordinates (row, col); owner = goblins (G), joiner = cavalry (C). Rows grow backwards from the goblins' front.

| Before | Action | After |
|---|---|---|
| G1 at (8,8) at rest, unpaired; C1 placed at (7,8), walking (24 units out) | pairing tick | C1 paired with G1; G1 paired with C1 but **at rest, not fighting** |
| same, C1 reaches < 3 units of its cell | movement step | C1 fighting, faces G1; G1 woken (paired with C1) |
| same, next tick | movement step | G1 re-arrives in its cell: fighting |
| G1 fighting C1; C2 at (8,7) arrives, paired with G1 | arrival | C2 fighting; G1 stays with C1 (C2's unit `s_pntval` not higher); C2 strikes G1 with +1 WS |
| C1 dies; G1's opponent was C1 | removal | G1 woken, unpaired, keeps (8,8); cavalry marked "lost a model" |
| next tick | cavalry pairing | every cavalry reserve released; up to 4 (frontage) unpaired cavalry collected; nearest pairs placed beside G models |
| C3 at rest at (6,8) unpaired, enemies in row 8 only, (7,8) free | joiner pass | C3 placed at (7,8) (≤ 18 units → 4 candidates), paired with G1 if G1 is the nearest, walks one cell |
| owner model G5 at (9,8) unpaired, G1 at (8,8) paired and at rest, (9,8) is G5's cell | owner pass, no adjacent enemy | candidates for "behind G1": (9,8) = own cell → G5 stays, becomes a reserve |
| owner model G6 at (10,9) unpaired, G1 at (8,8) paired and at rest | owner pass | G6 is behind, higher-column side: tries (8,9) then (9,8); takes the first free one as a reserve walking there |
| C4 fighting G2; G2 dies while fighting C5 (C4 was a ganging attacker) | C4's next strike | C4 unpaired, "weapon ready", **still at rest** |
| C4 then re-collected, best candidate = its own cell next to G7 (G7 unpaired) | joiner pass | C4 paired with G7, G7 paired with C4, **neither woken → neither fights** (🟡 §6; recommended engine: wake C4) |
| charging cavalry, not broken, crossing peasants' area | any tick before contact | no contact attacks on the cavalry; the peasants (behaviour 14) take hits from the cavalry if it is charging and within range |
| broken goblins run into the cavalry's footprint | collision pass | cavalry makes contact attacks on the goblins (once per segment), whether or not it is charging |
