# Battle end and in-battle objective evaluation

Clean-room behavioural handoff for the implementer (GitHub #15, #164). It covers:
- when the original evaluates the mission objectives during a battle;
- what each letter counts;
- what happens once the battle is decided;
- how the player leaves the battle;
- which values end up in the `Result:` records.

Read it with `game_rules.md` "Missions and objectives" (letter table, flags), `debrief_evaluation.md` §2 (how the
debrief uses the records) and `threat_events_nodes.md` (live/removed units, node circles). This report is the
reference for the in-battle part. Where the older notes disagree, this one is right, and §11 lists the sentences it
corrected. Static research: the original was not run.

## 1. Short answer

- **No automatic end.** Meeting a battle-ending letter (flag `0x1`) **decides** the battle but does not stop it.
  - The game prints a battle message, plays a speech cue, and replaces the pause button with the **tent button**.
  - Everything keeps running: scripts, movement, melee, shooting, routs and player orders.
  - The battle ends only when the player **presses the tent**. Then the final pass runs, the result records are
    written and the battle window closes.
  - There is no timeout.
- **When objectives are checked.** On **segment-boundary ticks only** (every 19 ticks, the tick on which break tests
  and melee resolve). The check runs **at the start of that tick**, before any unit is updated.
- **Z is always active.** It is evaluated **first**, whatever the `.BTS` says. If Z and A become met in the same
  pass, **Z decides**.
- **A** is met when every enemy regiment counted at load is gone. A regiment is gone when it is:
  - removed (all models dead, fled off the table, or removed by a script);
  - or still on the field but **broken and unable to rally**.
- **F** counts only removed regiments. **Z** is A's rule for the player side.
- **The outcome cannot change after the decision.** Only J, K and X (flag `0x10`) are still evaluated per segment.
  The flag-`0x8` letters are evaluated once more when the player presses the tent.

## 2. Unit states used below

| state | meaning |
|---|---|
| **in battle** | on the battle roster. Includes hidden, not-yet-revealed, routing and departed (crossed the edge, not yet removed) regiments |
| **removed** | taken off the roster: all models dead, war machine destroyed, routed off the table (flight complete, `pursuit_map_edge.md`/`flight_solid_obstacles.md`), or `RemoveFromBattle`. A removed regiment keeps a record of how many of its models were still alive when it was removed (**escaped models**). Models killed in battle are not escaped |
| **counted** | the regiment was counted by an objective at battle load (§4). The state is permanent. It is **one shared state**: any letter's load-time count sets it, and every letter's "gone" test reads it |
| **cannot rally** | the regiment has `CantRally`, or its casualties (models lost since load) are at least **3 × its remaining models**. This is the same test that stops a rally attempt (`game_rules.md` "Rally") |
| **out of action** | in battle, **broken**, and **cannot rally** |
| **kept for return** | set by the script operand `SetUnitFlags2 0x1000` (escape scripts, e.g. BF004_3, BF004_4, BF005, BF006, BF020, and library 170 in the siege battles). A removed regiment in this state keeps its models and can be returned to the battle by the final pass of D, G or L |
| **decided** | battle-level state, set by the first battle-ending letter that becomes met. It is never cleared during the battle |

Sides are taken from the regiment's **current** side (`SetSide` changes it at once). The four side values are
player, allied/NPC (`0x40`), enemy (`0x80`) and building pseudo-units (`0x20`).

## 3. When and in what order

### 3.1 Battle load (mode 1)

1. The `.BTS` parser links the defined letters into an **evaluation list**.
   - **Z is always at the head of the list and is always defined.** A `Z` line in the `.BTS` is ignored, numbers
     included. Z's values are measured at load anyway.
   - The other letters, A–Y, follow **in the order they appear in the `.BTS`**. The list is not sorted.
2. After the battle file and the army are loaded, every letter in the list is initialised once, in list order. This
   is **before deployment**: the counts are taken at load and include hidden units and units placed later by
   scripts.
3. Regiments with no models at load are not counted by anyone. They are removed from the roster just after this
   step.

### 3.2 Battle ticks

- The **battle clock** is reset at load and advances only on running battle ticks. It does not advance during
  deployment or while paused.
- The first segment boundary is the **19th battle tick**, then every 19 ticks.
- A **turn** is 10 segments. Turn 1 starts at the 1st boundary, turn 2 at the 11th, and turn k at boundary
  `10(k−1)+1`, i.e. tick `19 × (10(k−1)+1)`.

On a **segment-boundary tick**, before any unit is updated, the game walks the evaluation list. A letter is
evaluated in mode 2 (the **segment check**) when all of these hold:
- it is not met yet;
- it has flag `0x2`;
- the battle is not decided, or the letter has flag `0x10`.

When the evaluator returns met:
- the letter becomes **met**, permanently;
- if the battle is not decided and the letter has flag `0x1`, the battle becomes **decided** (§6) and **the walk
  stops for this tick**;
- otherwise the walk continues with the next letter.

**Consequences:**
- What a check sees is the state at the end of the previous tick. A regiment removed on tick t counts at the first
  segment boundary after t, so detection can lag by up to 19 ticks.
- **Z is checked before everything else.** If Z and A (or F, N, H) are both satisfied at the same boundary, **Z
  decides**.
- A letter without flag `0x2` is never evaluated during the battle: B, C, D, E, G, I, L, M, O, P, Q, R, S, T, V, W,
  Y.

### 3.3 Leaving the battle (mode 3, the final pass)

The final pass runs only when the player presses the tent button (§7). Steps:
1. The battle stops: no more ticks, and the battle music stops.
2. Every letter in list order that is **not met** and has flag `0x8` is evaluated once in **mode 3**. If it returns
   met, it becomes met.
3. Per-unit end bookkeeping and the `debrief.dbf` file (`debrief_evaluation.md` §1). The mission results are one
   record per listed letter, in list order: met flag and its four values.
4. The battle window closes.

Letters that are already met, including the deciding letter, are not evaluated again.

## 4. The elimination letters A, F, N and Z

### 4.1 A: eliminate the enemy (flags `0x3`)

**At load:**
- Count the in-battle **enemy-side** regiments that have models. Each one becomes **counted**.
- `v1` := their total models, `v2` := their number.

**Segment check:** `remaining = v2`, then subtract:
- every counted enemy-side regiment that is in battle and **out of action**;
- every counted enemy-side regiment that is **removed**.

A is **met** when `remaining` reaches 0. At that point every regiment counted at load is either removed or out of
action. The "out of action" term is A's **adjustment for regiments still on the table**. A routing regiment that can
still rally is not gone until it leaves the table or is destroyed.

What counts as a remaining enemy:

| regiment | remains for A? |
|---|---|
| hidden, never placed or revealed (e.g. BF003's Wolfriders before tick 60) | **yes**: counted at load. A cannot be met until it is dealt with |
| routing on the table, can still rally | yes |
| routing on the table, `CantRally` or casualties ≥ 3 × remaining models | **no** (out of action) |
| departed (front past the edge) but not yet removed | same as routing on the table: gone only if it cannot rally, otherwise when removed |
| fled off the table (removed) | no |
| all models dead (removed) | no |
| removed by `RemoveFromBattle` (with or without "kept for return") | no |
| teleported by `TeleportToNode` but not removed | yes (teleport alone changes nothing) |
| counted enemy later switched to another side | **never gone**: the side test fails, so A can never be met. Not in shipped data (`SetSide` is only used on player and NPC units) |
| unit that becomes enemy mid-battle | ignored: not counted |
| Night Goblin fanatics spawned in battle | ignored: a spawned unit starts not counted. Killing or keeping the fanatics changes nothing for A |
| enemy with no models at load | ignored |

**Edge case:** with no enemy regiment at load, A is met at the first segment boundary.

### 4.2 F (flags `0x7`, BF009 only)

F is A without the adjustment: only **removed** counted enemy regiments count as gone. A broken enemy that cannot
rally still holds F open until it leaves the table or dies. `v1`/`v2` are measured like A's, but in F's own
record.

### 4.3 N: get past the Dragon (flags `0x3`, BF014 only)

N is **met** when both of these hold at the same segment boundary:
1. A's condition holds. N keeps the counts in **A's** record, not its own.
2. At least one **player-side** regiment in battle stands inside **node `a`**.

"Inside a node" is the same circle test as the node opcodes (`threat_events_nodes.md` Part C §2). Its rules:
- it uses the regiment's position, the front-rank reference point;
- the distance to the node centre must be **≤ the node radius** (Euclidean, inclusive);
- the node index is the **0-based position in the battle's node list**, like `MoveToNode` operands;
- hidden or broken regiments are **not** excluded.

BF014: `N,26,0`, so node index 26. N's own `v1` keeps the node index.

### 4.4 Z: stay alive (flags `0xF`, every battle)

**Ordinary battles** (no G defined):
- **At load:** count the in-battle **player-side** regiments with models; each becomes **counted**. `v1` := their
  models, `v2` := their number.
- **Segment check:** `remaining = v2`, then:
  1. Subtract every counted player-side regiment in battle that is **out of action**. If `remaining` is now 0, Z is
     met.
  2. Otherwise go through the removed regiments and subtract one for each regiment that is **either**:
     - counted **and** player-side,
     - **or** counted **and** in the **kept-for-return** state, **whatever its side**.

     Z is met when `remaining` reaches 0. When Z is met in this step, `v3` := `v2`.
- **Final pass** (Z not met):
  - Recount the player-side regiments in battle with models. That recount also marks them counted.
  - `v3` := `v2 −` that number, i.e. regiments lost, including regiments that changed side or were removed.
  - Z is never met by its own final pass. U and G can set it met (§5).
- If Z was met in step 1, `v3` stays 0.

**Answers for the player side:**
- Z counts **regiments**, not models; `v1` is information only.
- An allied regiment gained mid-battle is not counted and does not matter.
- A player regiment that switches to the allied side is **no longer** player-side. In an ordinary battle it is
  therefore never gone for Z, unless it is removed in the kept-for-return state. Shipped data does this only in the
  siege battles, which use the siege rule below.

**Quirk: escaping enemies count against the player.**
- The second alternative in step 2 counts kept-for-return regiments of **any** side.
- In **BF004_3** (all 8 enemy regiments run escape scripts) and **BF004_4** (7 enemy regiments run escape
  scripts), the enemies are counted by A. Each enemy regiment that escapes through its kept-for-return script
  lowers the number of player regiments that must fall before Z is met.
- Example: BF004_3 has 9 player regiments. If 3 enemy regiments get away, Z is met after 6 player regiments are
  removed or out of action.
- It is probably unintended. Reproduce it only if exact parity matters.

**Siege battles** (G defined: BF015, BF017):
- **At load:** count the player-side **and** allied-side regiments with models.
- **Segment check:** the same as above, with these differences:
  - out-of-action **player** regiments are subtracted, but out-of-action **allied** regiments are **added**
    (`remaining = v2 − player out of action + allied out of action`). This is how the original computes it. A
    broken allied regiment that cannot rally therefore delays Z until it is removed;
  - removed regiments count when they are counted and player-side or allied-side, or counted and kept for return.
- **When the count reaches 0**, the evaluator changes the **battle state**:
  - battle state 1 or 7 → it becomes 7;
  - battle state 4 → it becomes 5, the `Zhufbar` speech effect 0 plays, and **event 0x38** is broadcast to every
    unit (as in `script_behaviours.md` 19/20).

  In both cases Z returns met. In any other battle state Z returns not met and is tested again at later
  boundaries.
- Player regiments that got inside the walls (library 152 → 170: allied side, kept for return, removed) are
  therefore "gone" for Z. Z being met in a siege battle means "nobody is left outside", not a defeat: §6 plays the
  *complete* cue there. The campaign verdict comes from G at the final pass (`debrief_evaluation.md` §3.3).

## 5. The other letters (Result values `v1..v4`)

`v1`, `v2` are the `.BTS` numbers `a`, `b` unless a letter overwrites them. `v3` and `v4` start at 0. In the
"evaluated" column, **segment** means the segment check (flag `0x2`) and **end** means the final pass (flag
`0x8`).

| L | flags | evaluated | values and met rule |
|---|---|---|---|
| A, F, N, Z | — | segment | §4 |
| B | `0x28` | end | at load: `v2` := models of **race 6 (Peasant)** regiments in battle, any side; they become counted. At the end: `v4` := Peasant models still in battle **plus the escaped models of every removed Peasant regiment**; `v3` := `v4 × 100 / v2`, integer division. Met if `v3 ≥ a`. 🟡 With no Peasant models at load (`v2 = 0`) the original divides by zero: treat as not met. Custom end-of-list line (§8) |
| C | `0x28` | end | at load: `v2` := regiments on the **building side** (`0x20`) with models; they become counted. At the end: `v4` := the same count now; `v3` := `v4 × 100 / v2`. Met if `v3 ≥ a`. Custom line (§8) |
| D | `0x08` | end | at load: `v2` := **allied-side RollingStock** regiments (class 7, wagons) in battle with models. At the end, first every removed regiment that is kept for return and not player-side **returns to the battle** (so escaped wagons count as saved); then `v4` := the same count now; `v3` := `v2 − v4` (wagons lost). Met if `v3 ≤ a` |
| E | `0x08` | end | at load: `v2` := **the `.BTS` `b` plus** the enemy models of the regiments A would count (the `.BTS` number is not cleared first; BF025 `E,100,69` therefore needs 69 more kills than there are enemies, so it can never be met); they become counted. At the end: `v4` := for every removed, counted, enemy-side regiment, its casualties minus its escaped models (models **killed**; regiments still in battle contribute nothing); `v3` := `v4 × 100 / v2`. Met if `v3 ≥ a` |
| G | `0x08` | end | siege only, see `debrief_evaluation.md` §3.3 (at the end it may set **Z met**) |
| H | `0x07` | segment | met when the **battle state** (the value `SetBattleState`/`IfBattleState` use) is **7**. See §5.1 |
| I | `0x0C` | end | see `debrief_evaluation.md` §2.2. Never met. No effect on the battle end |
| J | `0x16` | segment, also after the decision | returns met only once the battle is **decided**: if the battle state is then below 2, it sets the state to 2, plays the `Zhufbar` speech effect 0 and is met. BF038 only |
| K, X | `0x16` | segment, also after the decision | **item pickup**, §5.2 |
| L | `0x0C` | end | at load: `v1` := enemy models (`v1` cleared first), `v2` := enemy regiments; they become counted. At the end: kept-for-return non-player removed regiments return to the battle (as for D); `v3` := enemy models in battle now; `v4` := enemy regiments in battle now. Never met |
| M | `0x0C` | end | never met |
| O | `0x08` | end | at load: find the in-battle regiment whose `whoami` equals `a`, comparing the **low byte only** (BF009 `O,666` matches `set:whoami=-102`). It must have a leader. At the end: met if that regiment's **leader model has been killed** (the same moment the game sends it event 0x17). A leader that fled off alive does not count. 🟡 If no such regiment exists, the original reads garbage: treat as not met |
| P | `0x28` | end | met at the end if a regiment with `whoami = a` is still **in battle** (not removed). Custom line (§8) |
| Q | `0x08` | end | at load and at the end: `v2` := the number of **tree pieces**, `v4` := how many are **standing**; `v3` := `v4 × 100 / v2`. Met if `v3 ≥ a`. Tree pieces are the `.BTS` `furniture:` entries of the pine types (`Pine`, `PineSml`, `PineLrg`, `TriPineSml`, `TriPineMed`, `TriPineLrg` and their `Nite…`/`Snw…` variants). 🟡 What knocks a tree down was not traced. BF024 only (`Q,60,0`) |
| R | `0x0C` | end | never met. Its `a` selects the custom lines of B, C, P (§8) |
| S, T | `0x08` | end | **always met** at the end |
| U | `0x0E` | segment + end | §5.3. Never met |
| V | `0x0C` | end | at load: `v2` := models of regiments of **race `a`** (any side); they become counted. At the end: `v4` := `v2 −` race-`a` models still in battle `−` escaped models of removed counted race-`a` regiments (= models killed). Always met. BF007 `V,5` = Skaven, BF008 `V,0` = Human |
| W | `0x0C` | end | at load: `v2` := **enemy-side** regiments of class `a` with models (`a = 32` = class 4 Artillery). At the end: `v4` := `v2 −` that count now (destroyed or gone). Always met |
| Y | `0x0C` | end | met if (siege battle) G is met, otherwise if Z is met. Read at its place in the list: Z is always earlier, so a Z set by U at the end counts only if U comes before Y |

### 5.1 The battle state and H

- The battle state belongs to the battle's **control piece**: a `.BTS` furniture piece of a gate/entrance type
  (`ZhufWallEnt`, `PortcullisEnt`, `MoleHole0`, `NiteUnderwayEnt`). Without one, the state reads 0 and setting it
  does nothing.
- Scripts set states 1, 2 and 5 (BF015, BF017, BF037, BF040). The piece's own animation advances it:
  - opening: 2 → 3 → 4 (open) at the end of its animation;
  - after 5 (shutting starts), the piece runs its closing animation and the state becomes **7**. 🟡 For one piece
    type 7 is set when the closing starts, for the other when it ends; which is the siege gate was not traced.
- The game also moves 4 → 5 when a qualifying regiment enters node 14 (`script_behaviours.md` 19/20), and the
  siege Z rule (§4.4) moves 1/7 → 7 and 4 → 5.
- **H** ("Silent Doors Shut", BF015/BF017) is met at the first segment boundary that sees state 7.

### 5.2 K and X: item pickup

**At load:**
- `v2` is the magic-item id. If it names a known item:
  - `v4` := its item-table index;
  - a **marker** is placed at node `a`'s position, and `v3` remembers it.
- Otherwise K/X can never be met.

**Segment check:** go through the player-side regiments in battle. The first one inside node `a` (the §4.3 circle)
that has a **free item slot** (5 slots) picks the item up:
- the marker is removed;
- `v3` := the picker's `whoami`;
- the item goes into the regiment's first free slot;
- the regiment shows `React 16` ("Found Magic Item!", `script_behaviours.md` §3.3);
- the letter is met.

A regiment with all slots full does not pick it up.

Because the flag is `0x16`, pickups keep working **after the decision**. The player can collect field items before
pressing the tent.

### 5.3 U: the impossible mission (BF012, BF018, BF019; `U,4,0`)

**Segment check:** at the first boundary of turn `a`, i.e. when the turn number equals `a`, at tick
`19 × (10(a−1)+1)`; for `a = 4` that is tick 589:
1. `a` increases by 1, so it fires again at the start of every later turn, and a counter `v3` increases.
2. The `v3`-th eligible player regiment in roster order shows `React 15` ("We must retreat!" with the `Retreat`
   speech). Eligible means:
   - in battle;
   - player-side;
   - without `CantBreak`;
   - not charging, broken or pursuing;
   - `whoami ≠ 2`.
3. The **tent button replaces the pause button**, as at a decision (§6).

U never returns met. At the **end**, U sets **Z met** (`debrief_evaluation.md` §3.3).

## 6. The decision

When the deciding letter is met:

1. The battle becomes **decided**.
2. **Message and speech.** Except in U battles, the battle message window prints **GMTXT 1005** ("Mission
   complete."). This happens for a loss too. Then a speech cue plays from the `HumBtl` packet:
   - effect **15 `Hum_Failed`** if **Z is met** and G is not defined;
   - otherwise effect **9 `Hum_Complete`**: a win by A, F, N or H, or a siege battle's Z.

   In **U battles**, no message is printed, and the speech plays only if Z is met (`Hum_Failed`).
3. **Buttons.** The start-battle and pause buttons are hidden, and the **tent button** is shown in their slot at
   (11, 118) (frames 50/51). Nothing is modal and the game is **not paused**. With the pause button gone it cannot
   be paused from the panel. 🟡 A keyboard pause was not checked.
4. The deciding letter is not otherwise reported. No caption is shown for it and no dialog opens.

**After the decision:**
- **The simulation continues unchanged.** All units on both sides keep running scripts, AI, movement, melee,
  shooting, routs and pursuits. Player orders work as before.
- **Evaluation.** At each segment boundary only the not-yet-met letters with flag `0x10` are evaluated: **J, K, X**.
  All other letters wait for the final pass.
- **The outcome is fixed.**
  - After an A win, Z is no longer tested per segment, and its final pass never returns met. In ordinary battles a
    later wipe-out therefore does not turn the win into a loss. Only U or G can set Z at the end (§5).
  - After a Z loss, A is not tested again and has no final pass. The battle stays lost.
- **Book button.** The book (record 12, frames 80/81 at (162, 242) in the minimap window) only repeats step 2:
  "Mission complete." and the speech, if it is not already playing. Exception: in U battles it shows the objective
  list (§8).

## 7. Leaving the battle

| control | available | effect |
|---|---|---|
| **tent** (panel record 4, ICONS frames 50/51, slot (11, 118)) | hidden until the battle is **decided**, or until U's first warning. During deployment the start button occupies the slot; during the battle, the pause button | ends the battle: final pass (§3.3), result records, battle window closes |
| **options** (wrench, record 5) → in-battle menu → quit | always | asks "quit the campaign?" (GMTXT 36070). On *yes* the battle window closes **without** a final pass or result records. 🟡 What the campaign does next was not traced |

- Before the decision there is no surrender and no withdraw-from-battle button. A battle whose ending letters can
  never be met can only be quit.
- **Every shipped campaign battle has a reachable ending letter**: Z always, and A, F or N (plus H in the siege
  battles).
- **No timeout.** No "all enemies gone and nothing left to pick up" rule either.
- **End values.**
  - The load-time values (`v1`, `v2`) are fixed at load.
  - Segment-letter values are as last computed.
  - Every end letter's values are computed **when the tent is pressed**, not at the decision.

## 8. The objective list (book button before the decision)

- Pressing the book while the battle is undecided prints **GMTXT 1004** ("Your mission objectives are…").
- Then, for every listed letter **without flag `0x4`**, in list order:
  - letters with flag `0x20` (B, C, P) print a **custom line** chosen by **R's `a`** (nothing if R is not defined or
    `a` selects nothing);
  - other letters print their caption, **GMTXT 33000 + (L − 'A')**.

With the shipped flags, captions are printed for A, D, E, G, N, O, Q, S and T. Z, F, H, K, X and the other silent
letters are never listed.

Custom lines:

| R's `a` | B line | C line | P line |
|---|---|---|---|
| 1, 2, 6 | 33026 (villagers) | 33030 (buildings) | — |
| 3 | 33027 (slaves) | — | — |
| 4 | 33028 (livestock) | — | — |
| 5 | 33029 (Dwarfs) | — | — |
| 7 | — | 33031 (tunnels) | — |
| 8 | — | — | 33032 (assist the Wizard) |
| 9 | — | — | 33033 (mole machine) |
| 10 | 33034 (prisoners) | — | — |

## 9. Shipped battles

Letters per campaign battle file, in `.BTS` order. Z is always first in the evaluation list whether or not it is
written.

| battles | ending letters | notes |
|---|---|---|
| BF001, BF003, BF004_1–5, BF005–BF008, BF010–BF012, BF016, BF018–BF042 | Z, A | BF012/BF018/BF019 also U (tent from turn 4) and K/X pickups; BF038 J |
| BF009 | Z, F | O (capture: leader killed) |
| BF014 | Z, N (node 26) | |
| BF015, BF017 | Z (siege rule), A, H | G, siege battle state |

- **Wiping out the player army** decides the battle as a loss, by Z, at the next segment boundary. This holds in
  every battle except BF015 and BF017. There the siege Z rule applies: the battle state changes, the *complete* cue
  plays, and G decides the campaign at the end.
- **Battles without Z:** none. The four `.BTS`-level "battles without Z" counted in the older notes do not exist at
  run time, because Z is always active.

## 10. Test vectors

The segment-boundary ticks are 19, 38, 57 and so on.

| before | tick | after |
|---|---|---|
| BF003 loaded; Wolfriders hidden; all other enemies removed by tick 40 | 57 | A not met (Wolfriders counted, still in battle) |
| same; Wolfriders removed at tick 300 | 304 | A met → decided. GMTXT 1005 and `Hum_Complete`; tent replaces pause; units keep moving |
| enemy regiment 4 of 12 models left, 8 casualties, routing, no `CantRally` (8 < 3×4) | boundary | not out of action → A not met |
| same, 3 models left, 9 casualties (9 ≥ 3×3) | boundary | out of action → counts as gone for A; **not** for F |
| enemy `CantRally` regiment broken at full strength, still on the table | boundary | gone for A |
| BF004_5 fanatics spawned and alive; every counted enemy removed | boundary | A met (fanatics not counted) |
| last counted enemy removed on tick 37; last player regiment removed on tick 37 | 38 | Z evaluated first → **Z decides**, loss: GMTXT 1005 and `Hum_Failed` |
| battle decided by A on tick 380; all player regiments die on tick 500 | 513 … | Z not evaluated; the battle stays won |
| decided by A; player regiment enters K's node, has a free item slot | next boundary | item picked up, React 16, K met |
| decided by A; player presses the tent | — | battle stops; final pass for unmet flag-`0x8` letters in list order; `debrief.dbf` written; window closes |
| BF004_3: 9 player regiments; 3 enemy escapers removed (kept for return); 6 player regiments removed | next boundary | Z met (6 + 3 = 9) → loss |
| BF014: A's condition true; a player regiment's front-rank point 30 units from node 26's centre, radius 32 | boundary | N met → decided (win) |
| same, distance 33 | boundary | N not met |
| BF012: turn 4 begins | 589 | `React 15` on the first eligible player regiment; tent shown; U not met |
| BF017: control piece reaches state 7 | next boundary | H met → decided, `Hum_Complete` (Z, checked first, is not met) |
| book pressed before the decision (BF003: Z, R 1, A, B, C, K) | — | GMTXT 1004, 33000 (A), 33026 (B), 33030 (C); nothing for Z, R, K |

## 11. Corrections to earlier notes

- `game_rules.md` "Missions and objectives" has been corrected for the following:
  - objectives are checked per segment boundary, not every tick;
  - Z always comes first;
  - there is no dialog or end stinger: it is a message, a speech cue and the tent button;
  - the final pass runs when the player leaves, not on "a less frequent poll";
  - Z is always active;
  - F is the removal-only rule;
  - U swaps the pause button for the tent and does not stop music;
  - R64 is resolved: codes 9 and 15 are the `HumBtl` speech effects `Hum_Complete` and `Hum_Failed`.
- `debrief_evaluation.md` §2.2 has been corrected as follows:
  - mode 3 is run when the player leaves;
  - F counts only removed regiments: routed-off regiments **do** count as gone, and broken ones on the table do
    not;
  - B counts race 6 (Peasant) models, not "class 6";
  - Z includes allied regiments only when **G** is defined. I affects only the debrief unit list.
