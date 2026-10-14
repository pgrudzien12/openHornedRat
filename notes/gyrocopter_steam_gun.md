# Gyrocopter: steam gun, bomb, command panel and orders

Public implementation report on the Gyrocopter's weapons: which file variant has which, the buttons it shows, what
plain Fire and Ctrl+Fire do, whether any script fires them, and the steam-gun shot itself (flight, hits, look, sound).

Companion reports, cited rather than repeated:

- `game_rules.md` "Player orders and the command panel", "Who shoots, orders and volleys", "Reload time",
  "Artillery misfire", "Special weapons"; `FORMATS.md` (`s_race`, `s_side`, `S_BalWeap`).
- `player_missile_orders.md` §0 (the order gate, which selected units take an order).
- `script_shooting.md` §1.2 (what `Launch`/`FireAtTarget` does per class), §5.1.
- `spell_effects.md` §1 (active effects, innate launches), §2 (start/aim heights, scatter, flight, terminal impact,
  §2.5 pass-through), §3.7 (Pestilent Breath), §4 (one magical hit).
- `spell_visuals.md` §2.6 (Pestilent Breath's look, which the steam gun copies), `spell_sounds.md`.
- `airborne_units.md` §A2 (flying state, elevation), §A3.2 (Gyrocopter rest actions), §A8 (bolts vs fliers).
- `ranged_combat_handoff.md` (the bomb's flight and blast), `casualty_bookkeeping.md`, `panic_tests.md`.

Conventions as in `spell_effects.md`: world units (24 = 1"), angles in 1/512 turn (0 = +y, clockwise), one tick = one
battle update.

**Corrections made by this report** (each also fixed in place):

- `game_rules.md` "Special weapons": the steam gun is **not** limited to Infantry-class files. **Every** code-17 unit
  fires it on a plain Fire order, Archers class included; the bomb is the Ctrl variant of the Archers/Artillery-class
  unit (§3, §4). "Range 144" is a **scatter scale**, not a range: the steam gun has no range limit (§5). "One model of
  each unit it crosses" is one model **per tick** spent inside each unit, plus the terminal impact (§5.2).
- `game_rules.md` order 0x16: Ctrl is read when the Fire **button** is released, for the focused unit only (§2).
- `script_shooting.md` §5.1 item 1: the 🟡 is settled in its favour (§3).
- `airborne_units.md` §A1 table: the campaign Gyrocopter is the Archers-class variant and has both weapons; the
  Infantry-class variant exists only in `BF033.MRC` (§0). §A8.1 rule 4 and §B2.7: the steam gun also launches from
  the shooter's elevation, and its aim height is fixed (§5.1).
- `spell_sounds.md` steam row: the 🟡 stop condition is settled (§6.2).

## 0. The two variants, and where the class comes from ✅

**Shared state first.** The class that decides the command panel, the shooting rules and the interrupt script is
the **class part of `s_race`** (`class × 8 + race`, `FORMATS.md` token 33; `game_rules.md` setstats table). It is not
the type code in `s_side`. Both Gyrocopter variants have `s_side` type 4, so a class taken from `s_side` puts both in
Infantry, which is wrong for the campaign one. 🟡 The same mapping may misclassify other units too. Check it against
`s_race` for the whole roster.

| file | regiments (whoami) | `s_race` | class | used when |
|---|---|---|---|---|
| `FILE/SCRIPT/MAXARMY.MRC`, copied to `SAVE/PLAY.MRC` (the campaign roster) | `3rd_Gyrocopters<No.1` (13), `<No.2` (36), `<No.3` (37) | **26** | **Archers** | the **campaign**: every Gyrocopter the player can have there comes from this roster |
| `FILE/SCRIPT/BF033.MRC` (the `loadmerc:` army of `BF033.BTS` and `BF021.BTS`) | the same three | **10** | **Infantry** | only when one of those battles is loaded outside the campaign |

- All of them have `S_BalWeap = 17` (No.1 also on its leader). The missile code is read as in `game_rules.md` "Who
  shoots", so every Gyrocopter record has code 17, with or without a leader.
- Only No.1 has a leader block. No.2 and No.3 are leaderless single figures.
- All use `PLAYER_SCRIPT`. No shipped `.BTS`/`.MRC` puts a Gyrocopter on the enemy, allied or neutral side.
- Nothing in the campaign rules changes `s_race`.

Summary: **an Archers-class Gyrocopter has both weapons** (plain Fire = steam gun, Ctrl+Fire = bomb). **An
Infantry-class one has only the steam gun**, and only through a multi-selection (§3).

## 1. Command panel ✅

The panel comes from the class of the **focused** unit and the panel state (`game_rules.md` "Player orders and the
command panel"):

| state | Archers-class Gyrocopter (campaign) | Infantry-class Gyrocopter (`BF033.MRC`) |
|---|---|---|
| idle | Move, Attack, Independent | Move, Attack, Independent |
| attack sub-panel, no items | Charge, **Fire**, Halt, Back | Charge, Back (**no Fire**) |
| attack sub-panel, with items | Charge, **Fire**, Items, Halt, Back | Charge, Items, Back |
| melee, broken, charging, deployment | as every Archers unit (no Fire) | as every Infantry unit |

- **Only the class** decides whether Fire is shown. The missile code and the special-shooter test are not looked at.
- Fire has no keyboard shortcut. It starts only from the panel button.
- While the player picks a point, the *fire* cursor is shown. The click, or a cancel, restores the previous cursor.

## 2. The Fire button and Ctrl ✅

When the Fire button is **released**:

1. If the panel is already waiting for a Fire click, nothing happens (no toggle, no bomb).
2. Otherwise, if **Ctrl is held at that moment**, the game tries the **bomb** for the **focused unit only** (§4). The
   attempt is final whenever the focused unit may bomb at all (Archers or Artillery class, code 17, and the
   original's projectile capacity not full). It either drops the bomb or is refused with a message, and no pick mode
   starts. For any other unit, Ctrl is ignored and step 3 follows.
3. The fire cursor appears. The next map or minimap click issues the **Fire order** (§3) to the selected units.

Ctrl is **not** read at the map click: holding or releasing it while clicking changes nothing. Ordinary bows read
Ctrl when the projectile launches (`ranged_combat_handoff.md`); the steam gun and the bomb do not. Every shot needs a
new Fire press and click.

## 3. Plain Fire on a Gyrocopter fires the steam gun at once ✅

The Fire order reaches each **selected** player unit at the start of its tick, like every order
(`player_missile_orders.md` §0). A selected unit takes it if it is the focused unit **or** has a missile code (unit
or leader). The **order gate** comes first: a unit that is **charging, in melee, broken, pursuing or braced** drops
the order silently.

A unit whose missile code is a special shooter (14 breath, 15 warpfire, **17**) handles the order itself, **for
every class**:

| aspect | behaviour |
|---|---|
| what is fired | **one steam-gun shot** (§5) aimed at the **clicked ground point** |
| clicked on an enemy, a friend, itself, a building or open ground | no difference: the aim is the clicked point, never "the unit under the cursor". No target is stored, no event is queued, no targeting text (none of 2007/2008/2009/2017) |
| minimap click | the point snaps to the centre of the unit the minimap pick finds (any side), as for Magic (`player_magic_panel.md`) |
| range | **none**. A click 1000 units away still fires (§5.1: 144 only scales the scatter) |
| arc, turning | no arc test, no turn to face. The shot still starts 24 units ahead along the craft's facing (§5.1), so a shot behind the craft flies back over it |
| reload | **none**: no reload test and no reload stamp. The player can fire as fast as Fire + click can be repeated. The bomb's reload (§4) is neither tested nor used up |
| a moving Gyrocopter | **not halted**: it keeps flying its route |
| airborne / grounded | both fire. Only the launch height differs (§5.1) |
| held (Tangling Thorn), hold fire | **not tested**: the shot is fired |
| hidden | the shot reveals the Gyrocopter |
| scripts | **bypassed**: no event 30–37, no fire loop, no restart. The script position and the current target are unchanged |
| animation | **none**: no shoot action. The rest action does not change, so a hovering Gyrocopter keeps hovering and a grounded one stays grounded (`airborne_units.md` §A3.2) |
| refusal | only when the original's active-effect capacity is full: a player unit then gets `GMTXT 2021` (the "attempted … but failed" text with the effect's name). No other refusal, no success text |

Consequences:

- **Archers-class (campaign) Gyrocopter**: plain Fire fires the steam gun.
- **Infantry-class Gyrocopter**: its own panel has no Fire. It still fires the steam gun when it is **selected
  together with** a focused Archers or Artillery unit and the player gives Fire + click.
- Several selected Gyrocopters each fire one shot at the same point.

## 4. Ctrl+Fire: the bomb ✅

Only the **focused** unit, and only an Archers- or Artillery-class unit with missile code 17. In practice that is the
campaign Gyrocopter; the Infantry-class file never bombs. Checks in this order:

| step | check | on failure |
|---|---|---|
| 1 | class Archers/Artillery and the original's projectile capacity not full | falls back to the ordinary pick mode (§2 step 3), so the next click fires the **steam gun** |
| 2 | missile code 17 | ordinary pick mode |
| 3 | ready to fire: not held, and the reload has elapsed (`game_rules.md` "Reload time": I2 and no bow reduction give **144 ticks**; ready when `now − last ≥ 144`) | `GMTXT 2003` (also shown when held); nothing else happens |
| 4 | **the reload is stamped now** | — |
| 5 | the craft is **in the flying state** (elevation > 0, `airborne_units.md` §A2) | `GMTXT 2020`; the reload stamped in step 4 **is used up** |
| 6 | the artillery misfire roll (`game_rules.md` "Artillery misfire") | `GMTXT 2018` (destroyed) or `2019` (shot lost); no bomb; the reload is used up |
| 7 | launch: one bomb at the craft's **own current position**, falling from its **current elevation** (any of 4…32, e.g. 16 during take-off) to the ground in 9 ticks. The first misfire D6 (1–5) is the scatter die, with no distance scaling. Blast values in `game_rules.md` §8.3 and `ranged_combat_handoff.md` | — |
| 8 | the drop reveals a hidden craft | — |

- The bomb is not an order, so the order gate does not apply: the button acts at once. The Fire button exists only in
  the attack sub-panel, which is reached from the idle state. 🟡 Whether that sub-panel can still be on screen after
  the unit has entered melee or broken (which would allow a bomb then) was not checked.
- The bomb does not halt, turn, retarget or animate the craft. A moving craft drops it where it is and flies on.
- No success text.
- The reload is the **same** one the scripted volley stamps (§7), so a threat-reaction "volley" delays the next bomb.
- **Destroyed misfire** (6 then 1): what gets destroyed is the unit's **leader figure** (the machine). whoami 13 has
  one; whoami 36 and 37 have none. 🟡 For them the original's result is undefined, probably a crash. Recommended
  engine choice: treat it as a lost shot (`GMTXT 2019`), tagged as a deviation.

## 5. The steam-gun shot ✅

Every steam-gun shot is **one innate launch of spell effect 27** by the Gyrocopter's unit. It is a full active effect
(`spell_effects.md` §1): it counts towards the original's effect capacity (full → `GMTXT 2021` for a player-army
shooter), never touches a spell list, is never dispelled or cancelled, and **reveals a hidden shooter**
(`spell_effects.md` §1.6). Nothing else in the shipped game launches effect 27. The many `SetBehaviour n 27` lines in
mission scripts are behaviour 27, Pestilent Breath, which is unrelated.

It belongs to the same family as Pestilent Breath (`spell_effects.md` §3.7): the same 18-tick pass-through cloud and
the same look. The differences are S4 instead of S3, the start 24 units ahead, the launch height that follows the
elevation, and the fixed aim height.

### 5.1 Launch parameters

| item | steam gun (27, innate) |
|---|---|
| launching model | none: the **unit** is the origin |
| start (x, y) | the unit position **plus 24 units ahead along the unit's current facing** (the unit's, not a figure's). Each axis is rounded down after scaling, as for the Dragon breath (`bf014_dragon_rendering.md` §3.2): `dx = floor(24 × trunc(256·sin(2πf/512)) / 256)`, `dy = floor(24 × trunc(256·cos(2πf/512)) / 256)`. The ground under the start and the scatter distance are taken at the **unit position**, before this shift. The destination is not shifted |
| launch height L | **8** for a grounded unit. For a unit in the **flying state** (elevation E > 0, take-off and landing included): **E**, read once at launch |
| aim height A | **always 8**. The "flying unit under the aim point" pick of `spell_effects.md` §2.1 (`airborne_units.md` §A8.1 rule 1) is **not** used: aiming at an airborne flier still gives 8 |
| height above ground in flight | the `spell_effects.md` §2.1 rule: the line runs from `ground(unit position) + L` to `ground(destination) + 8`, no arc. On flat ground: grounded shooter **16 all the way**; flying shooter `E + 8 + trunc((E − 8) × r / 18)` (2E at the start, E + 8 at the end) |
| flight | **fixed 18 ticks**, straight: r = 18 … 0, i.e. **19 tested positions**, the first at the start, the last at the destination (`spell_effects.md` §2.3). Speed is `distance / 18` per tick, whatever the distance (≈ 6.7 per tick for a 6" shot) |
| range | **no clamp and no refusal**: the shot flies to its (scattered) aim point however far it is. 144 is only the scatter divisor |
| scatter | yes, `spell_effects.md` §2.2 with the **unit's BS** and divisor **144**: `step = trunc(8 × d(unit position, aim) / 144)`; four random draws (x size, x sign, y size, y sign). Step 8 at 6", 32 at 24" |
| stops on hit | **no** (pass-through, `spell_effects.md` §2.5) |
| in-flight test | `spell_effects.md` §4 at the current point and height: radius 0, **own unit excluded**, silent. Every other unit (any side, friends included) whose footprint contains the point **strictly** (`d < footprint radius`) and passes the height test (ground unit: `h ≤ 16`; flier at elevation E': `E' ≤ h ≤ E' + 16`) takes **one hit per tick**, so a unit is hit once for **every tick** the cloud spends inside it. Buildings in reach are damaged (S4 against a building). Solid scenery and spell area objects are passed through without effect |
| per hit | one random model (leader and champion included), **S4, 1 wound, no armour save** (regenerators are wounded normally), magical (`MagicResistent` ignores it on an even draw), **ordinary death**, kill credited to the Gyrocopter's unit (`casualty_bookkeeping.md`) |
| morale | each death runs the ordinary casualty panic (`game_rules.md` §7.2). **No** impact panic, **no** forced rout, no event or message to the victim |
| terminal impact | at r = 0, after that tick's in-flight test: one impact at the **scattered destination**, **height 0**, nothing excluded (the Gyrocopter's own unit can be hit), messages on (`GMTXT 2004` for each unit struck), the same S4 / 1 wound / no save. It never strikes a unit that is airborne at that tick (`airborne_units.md` §A8.1 rule 3) |
| below ground | if the cloud's height above the ground under it is negative after a tick's test, the cloud is removed with **no** terminal impact. A ridge between shooter and aim stops it |
| random draws | at launch: the four scatter draws only. Per struck unit per test, in map-object order: the model pick, the D6 to wound, then (only if wounded and the unit is `MagicResistent`) the even draw, then the wound draw (a draw of `rand mod 1`, still taken) |

🟡 Whether **hidden** units are struck is not settled: no hidden test was found in the impact.

### 5.2 Consequences

- **Grounded Gyrocopter:** a flat cloud at 16 above the ground, exactly the (inclusive) ground-unit height limit, so it
  hits ground units on flat ground. On uneven ground the cloud follows the straight line between its end heights:
  over a hollow it can pass **above** ground units (height > 16), and a rise of more than 16 above the line removes it.
- **Airborne Gyrocopter at 32:** the cloud runs from 64 down to 40 above the ground. **It never hits ground units in
  flight.** Its only hit on ground units is the terminal impact at the destination: one hit per unit there, with the
  message.
- **During take-off or landing:** E = 4 and 8 still hit ground units in flight (heights 8–12 and 16). E ≥ 12 does not
  (heights ≥ 20).
- **Several hits per unit:** a 6" shot through the centre of a unit with footprint radius 40 hits it **12 times**
  (V1). This is where most of the steam gun's damage comes from.
- **A shot aimed behind the craft** starts 24 ahead and flies back over the craft, which is excluded in flight. The
  terminal impact can still hit it if the destination lies inside its own footprint.

## 6. Look and sound ✅

### 6.1 Look

The steam gun is drawn like Pestilent Breath (`spell_visuals.md` §2.6), with its own frames:

| part | steam gun |
|---|---|
| head | `SPELLS` frame **591 + s**, colour bank **+32**. Frames 591–594 are 32 × 32 puffs growing from small to large; with bank +32 they are grey steam. `s` is the flight stage, with the same thresholds as Pestilent Breath (0 while `4(N − r) ≤ N`, then 1, 2, 3; N = 18). Drawn at the cloud's position and height each flight tick. Not directional, no per-tick cycle |
| trail | one **static** puff left at the cloud's previous position (at its height there) on every tick the cloud has moved: one at the start on the launch tick, none on the next tick (the head has not moved yet), then one per tick, and the last one at the destination on the tick after the terminal impact. That is about **19 puffs**. Each keeps the stage frame it was left with, so the path is lined with puffs that grow from the Gyrocopter towards the aim. They never animate |
| end | the head disappears on the tick after the cloud finishes. The trail is then removed **one puff per tick, oldest (shooter end) first**. The effect ends when the last puff has gone, about 19 ticks later. 🟡 The stage may lag one tick behind the table, as noted for Pestilent Breath |
| shoot pose | **none**. Neither the shot nor the scripts that would order it request an animation. The Gyrocopter keeps whatever rotor program it is running (its action 7 has no fire step anyway, `airborne_units.md` §A3.2). No muzzle smoke, flash or explosion |

### 6.2 Sound (settles the 🟡 of `spell_sounds.md`)

- `SFX_Cast_Steam` (index 14 of the spells sound package, looping), plain mode. It starts at launch, placed once at
  the **Gyrocopter's unit position** at that moment (not at the start point 24 ahead), and is **never moved**.
- **Stop:** on the **same tick the cloud finishes**, i.e. the tick of its terminal impact or the tick it is removed
  below ground, after that tick's flight step. It does not wait for the trail to clear. So the hiss lasts the 19 flight
  ticks (≈ 1.9 s).
- If effect sounds are switched off at launch, the shot stays silent for its whole life (no late start).

## 7. Scripts and AI ✅

**No script and no AI ever launches a Gyrocopter weapon in the shipped game.**

- No mission script uses `IsSpecialShooter`, `FireAtTarget` or a behaviour that fires code 17, and no mission puts a
  Gyrocopter on a scripted side. The library uses `IsSpecialShooter` only in the two volley scripts 115 and 117
  (counted in one mission DLL; the library repeats in all). The periodic behaviours 11/12 fire only for code 13
  (Doomwheel).
- `PLAYER_SCRIPT` (script 100) installs the interrupt script by class: 104 for Archers, 101 for Infantry.
  - **Infantry-class Gyrocopter** (101 → 153 → 152): no fire handling at all. Its threat reaction (independent only)
    is the infantry one (script 159: approach and charge).
  - **Archers-class Gyrocopter** (104 → 156): the Archers threat reaction runs (`script_shooting.md`, 126 → loop 124;
    independent: 122). It uses the code-17 **scripted missile range 384** (16", strict `<`), ready-to-fire (reload
    144), the arc test and the target test, then volley script 115. That script **stamps the reload**, takes the
    special-shooter branch and runs `FireAtTarget`, with no animation and no `React 10`. `FireAtTarget` on an
    Archers-class unit with code 17 **launches nothing** (`script_shooting.md` §1.2 branch 4: it stamps the reload
    and fails, because code 17 has no ordinary missile). Only with the projectile capacity full would it take the
    special branch and fire the steam gun, which is practically unreachable.
  - Visible result for an Archers-class Gyrocopter under a threat reaction: it quarter-turns to the threat and gets a
    current target. The target changes its rest action, so it **lands** (`airborne_units.md` §A3.2). It turns to face
    the target and runs silent "volleys" every 144 ticks that fire nothing but keep restarting the bomb reload. An
    independent one also moves towards targets beyond 384 (scripts 119/120).
- Fire events 30–37 never reach a Gyrocopter: the Fire order of §3 handles special shooters before any event is made.

## 8. Test vectors

Notation: G = Gyrocopter (Archers class unless stated), focused and selected, elevation E; G' = Infantry-class
Gyrocopter; T = enemy; "now − last" = ticks since G's reload stamp. Flat ground at height 0 unless stated.

### 8.1 Panel and button

| before | action | after |
|---|---|---|
| G (campaign, `s_race` 26) idle | Attack | panel: Charge, Fire, Halt, Back |
| G' (`BF033.MRC`, `s_race` 10) idle | Attack | panel: Charge, Back (no Fire) |
| G, attack sub-panel, Ctrl up | release Fire | fire cursor, waiting for a click |
| G, already waiting for a Fire click | Ctrl + Fire again | nothing |
| G, Ctrl held, E = 32, now − last = 144 | release Fire | bomb dropped at once; no fire cursor |
| crossbow unit X focused, Ctrl held | release Fire | ordinary fire cursor (Ctrl ignored) |

### 8.2 Plain Fire (steam gun order)

| before | action | after |
|---|---|---|
| G hovering at E = 32, T at 100 | Fire + click on T | one steam-gun shot this tick at the clicked point; no text; G still hovering; no reload stamp |
| G, T at 144 / 145 / 1000 | Fire + click on T | shot fired in every case (no range test); scatter step 8 / 8 / 55 |
| G, point behind G | Fire + click | shot fired; G does not turn |
| G fired 1 tick ago | Fire + click | second shot fired (no reload) |
| G moving on a route | Fire + click | shot fired; G keeps moving |
| G grounded | Fire + click | shot fired from launch height 8 |
| G held by Tangling Thorn | Fire + click | shot fired |
| G in melee, broken, charging or pursuing | Fire order arrives | dropped silently, no shot |
| G hidden | Fire + click | shot fired; G no longer hidden |
| G' and crossbow unit X (focused) both selected | Fire + click on T | X: event 31 and its fire loop as usual; G': a steam-gun shot at the clicked point |
| G and a second Gyrocopter H selected | Fire + minimap click where T is picked | both fire one shot at T's centre |
| active-effect capacity full | Fire + click | `GMTXT 2021`; no shot |

### 8.3 Ctrl+Fire (bomb)

| before | action | after |
|---|---|---|
| G at E = 32, now − last = 144 | Ctrl + Fire | bomb from height 32 at G's position; reload stamped; the first D6 (1–5) is the scatter die |
| G at E = 32, now − last = 143 | Ctrl + Fire | `GMTXT 2003`; stamp unchanged |
| G at E = 4 / E = 16 (taking off), reloaded | Ctrl + Fire | bomb from height 4 / 16 |
| G at E = 0, reloaded | Ctrl + Fire | `GMTXT 2020`; **reload stamped** |
| same, 10 ticks later, now airborne | Ctrl + Fire | `GMTXT 2003` (134 ticks still to wait) |
| G at E = 32, reloaded; D6 = 6, then 3 | Ctrl + Fire | `GMTXT 2019`; no bomb; reload used up; a hidden G stays hidden |
| G, projectile capacity full | Ctrl + Fire | ordinary fire cursor; the next click fires the steam gun |
| G under a threat reaction, silent volley 50 ticks ago | Ctrl + Fire | `GMTXT 2003` |

### 8.4 The shot: geometry and hits (grounded G, scatter draws 0)

| before | action | after |
|---|---|---|
| G at (1000, 1000), facing 0; aim (1000, 1144) | shot | start (1000, 1024), destination (1000, 1144). y at r = 18 … 0: 1024, 1031, 1038, 1044, 1051, 1058, 1064, 1071, 1078, 1084, 1091, 1098, 1104, 1111, 1118, 1124, 1131, 1138, 1144 (`1144 + trunc(−120 r / 18)`); height 16 at every position |
| unit U centred (1000, 1100), footprint radius 40 | same shot | U inside (d < 40) at r = 12 … 1 (d = 36, 29, 22, 16, 9, 2, 4, 11, 18, 24, 31, 38): **12 hits**, silent. r = 13 (d 42) and r = 0 (d 44) miss; the terminal impact at (1000, 1144) misses U (d 44) |
| same, U radius 38 | same shot | at r = 1, d = 38 is not < 38: **11 hits** (r = 12 … 2) |
| a friendly unit in U's place | same shot | the same 12 hits (no side test) |
| G at (1000, 1000), aim (1000, 1004) inside G's own footprint | shot | start (1000, 1024); the cloud flies **back** 20 units; in-flight tests skip G; the terminal impact at (1000, 1004) **hits G** (`GMTXT 2004` on the player side) |
| G airborne (E = 32), enemy ground unit at the destination | shot | no in-flight hits on it; **1** terminal hit, with message |

### 8.5 Start offset (24 ahead)

| facing | 0 | 64 | 128 | 192 | 256 | 320 | 384 | 448 |
|---|---|---|---|---|---|---|---|---|
| (dx, dy) | (0, +24) | (+16, +16) | (+24, 0) | (+16, −17) | (0, −24) | (−17, −17) | (−24, 0) | (−17, +16) |

### 8.6 Heights against targets (height above flat ground at r = 18 / 9 / 6 / 0)

| E at launch | heights | ground unit hit in flight? | flier at E' = 32 (band 32–48) | flier at E' = 4 (band 4–20) |
|---|---|---|---|---|
| 0 (grounded) | 16 / 16 / 16 / 16 | yes | never | yes |
| 4 | 8 / 10 / 11 / 12 | yes | never | yes |
| 8 | 16 / 16 / 16 / 16 | yes | never | yes |
| 12 | 24 / 22 / 21 / 20 | **no** | never | only where h ≤ 20: r ≤ 4 |
| 16 | 32 / 28 / 26 / 24 | no | only at r = 18 (h = 32) | never |
| 32 | 64 / 52 / 48 / 40 | no | where h ≤ 48: r ≤ 6 | never |

In every row the terminal impact is at height 0: it hits ground units (and fliers at elevation 0) at the
destination, never airborne ones.

### 8.7 Terrain

| before | action | after |
|---|---|---|
| grounded G; ground 10 at G and at the destination, a hollow at 0 halfway | shot | over the hollow the cloud is 26 above the ground: ground units there are **not** hit |
| grounded G; ground 0 at both ends, a ridge at 20 between | shot | over the ridge the height is −4: that tick's test runs, then the cloud is removed; no terminal impact; the sound stops that tick; the trail clears as usual |

### 8.8 Look and sound timeline (launch on tick T, uninterrupted)

| tick | event |
|---|---|
| T | effect created; `SFX_Cast_Steam` starts at G's position; the start position is tested; head frame 591; trail puff 1 at the start |
| T+1 | position r = 17; no new puff |
| T+2 … T+18 | one puff per tick at the previous position; stage 0 → 3; on T+18 (r = 0): in-flight test, terminal impact, **sound stopped** |
| T+19 | head gone; the last puff is left at the destination; trail removal starts (oldest first, one per tick) |
| ≈ T+38 | last puff removed; effect ends |

### 8.9 Scripts

| before | event | after |
|---|---|---|
| Archers G (`PLAYER_SCRIPT`), enemy T attacking it at 200 | threat reaction | quarter-turn, target T, loop 124; in arc, < 384 and reloaded → reload stamped, **nothing fired**; G lands (rest action with a target) |
| same, T at exactly 384 | loop 124 | out of range (strict `<`): no "volley"; at 383 and in arc: a silent volley when reloaded |
| G' (Infantry, `PLAYER_SCRIPT`), not independent, enemy attacking | threat reaction | ignored (the infantry handler needs the independent state) |

## 9. Where the original differs from the current engine model

1. **Class**: from `s_race`, not `s_side`. The campaign Gyrocopter is **Archers** class and has a Fire button.
2. **Plain Fire** on any code-17 unit fires the steam gun at once: at the clicked point, with no range, arc or reload
   test, no halt, no turn, no animation, no events. Infantry-class ones fire it through a multi-selection.
3. **Ctrl+Fire**: Ctrl is read when the button is released, for the focused unit. Check order: reload (2003) → stamp →
   airborne (2020) → misfire (2018/2019). A refusal after the stamp still uses up the 144-tick reload. If the
   projectile capacity is full, the button falls back to the pick mode.
4. **Scripts never fire it**: an Archers-class Gyrocopter's threat reaction only stamps the reload and makes it land.
5. **The shot**: start 24 ahead along the unit facing; **18 ticks** (19 positions), not 9; launch height 8, or E when
   flying; aim height 8; scatter with BS and divisor 144; **one hit per tick inside** each unit (friends included,
   own unit spared); **terminal impact always** at height 0 (own unit included, with message), not only when nothing
   was struck; ordinary deaths; casualty panic only.
6. **Look and sound**: `SPELLS` 591–594 at bank +32 as head and trail puffs; `SFX_Cast_Steam` from launch until the
   cloud finishes.

## 🟡 Open items

- Whether hidden units are struck by the cloud (§5.1).
- Whether the attack sub-panel can stay visible after the unit enters melee or breaks, allowing a bomb (§4).
- The destroyed misfire of a leaderless Gyrocopter (whoami 36/37) (§4).
- A possible one-tick lag of the head's stage frame (§6.1).
- None of this has been observed on screen. Check it in Wine with a campaign army that has the Gyrocopter.
