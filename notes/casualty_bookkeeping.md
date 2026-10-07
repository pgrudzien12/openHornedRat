# Casualties, kill credit, wounded and healing (battle → campaign)

Issue #123 (debrief → campaign hand-off). Status markers: ✅ established, 🟡 hypothesis, ⬜ unresolved.
Companion reports: `notes/campaign.md` (§1 experience and promotions, §3.3 summary of casualties, §4.5 roster table,
§4.8 `debrief.dbf`, §5 debrief flow), `notes/debrief_evaluation.md` (§3 campaign-over test, §4.3 text ops),
`notes/activity_results.md` §5, `notes/native-windows.md` §9.9–9.11 (debrief screen), `notes/game_rules.md` §7.2 (panic
on losses) and "Death kinds". This report is the authority for the counters below; the sentences it corrects in
those files are listed in §4.

## 1. Summary

- **Battle**: every model carries a *credited unit*. Close combat, contact attacks (pursuit) and fanatics set it on
  any wound; missiles, artillery, blasts and spells only on the lethal hit. When a model leaves its unit — killed **or
  removed alive** — the victim unit gets `s_calualties` +1 (and `s_routed` +1 if removed alive), and the credited
  unit, if any, gets `s_kills` +1 and `s_Exp` + the victim unit's `s_pntval`. No side check: friendly fire is credited.
- **Battle end**: no end-of-battle pass; units still on the field (routing or not) are "Surviving Units" with their
  live counters, units gone from the field are "Dead or Routed Units" with `s_size` 0.
- **Campaign**: before the screen the roster's `wounded_last` moves to `returning` and the new wounded
  (65 % of `s_calualties − s_routed`) are stored; at Done the army is merged, healed by `returning` (capped at
  `s_orgsize`) and regiments under 20 % are disbanded; `returning` is then cleared. Routed models rejoin in full.
  `Z` met loses this battle's wounded only.

## 2. Battle side: kill credit and counters

### 2.0 The model in one paragraph ✅

Every model carries a **credited unit** ("the unit that last wounded it", possibly none). It is empty when the model
is created and is set or cleared by the damage kinds of §2.1. Nothing is credited when a wound is dealt. Credit is
given **when the model is removed from its unit**, and removal is one of two kinds:

- **killed**: the model's death sequence starts (after the collapse delay of `game_rules.md` "Death kinds", 1 tick for
  missiles/fire/slain outright, up to 72 ticks for close combat). The panic check of §7.2 runs.
- **removed alive**: the model leaves the battle without dying (its unit leaves the map, is removed by a script, etc., §2.1).

On **every** removal, of either kind:

| counter | change |
|---|---|
| victim unit `s_size` | −1 |
| victim unit `s_calualties` | +1 |
| victim unit `s_routed` | +1 **only** if removed alive |
| victim unit current worth (the AI's threat-vs-worth value) | − victim `s_pntval` |
| credited unit (if any) `s_kills` | +1 |
| credited unit (if any) `s_Exp` | + victim unit's `s_pntval` |

Credit therefore does **not** depend on the removal kind: a model removed alive still credits the unit that last
wounded it, if any (in practice only multi-wound models can carry such a stale credit, §2.1).

### 2.1 Which damage credits whom (A1) ✅

Short answer: whoever caused the damage is credited, with two different "write" rules:
**any-wound** kinds overwrite the credit whenever they cause at least one wound; **lethal-only** kinds overwrite it
only when, after the hit, the model's wounds are at or above its W (the hit killed it, or it was already dying).
There is no side test anywhere: friendly fire and allied NPCs are credited like anyone else.

| Removal / damage kind | Credited unit | Write rule | Victim `s_calualties` | Victim `s_routed` | Notes |
|---|---|---|---|---|---|
| Close combat blow (attacks of a model on its opponent) | the attacking unit | any wound | +1 at removal | — | targets of class Infantry, Cavalry, Archers, Artillery, Wizard, Monster |
| Close combat against RollingStock (wagons) or Furniture (buildings) | **none** | — (credit untouched) | +1 | — | damage goes to the first model of the target; it never sets the credit |
| Strike back (a monster hitting the model that attacked it) | the struck-back unit (the defender) | any wound | +1 | — | `game_rules.md` "Only monsters strike back" |
| Contact attacks (`game_rules.md` §7.7: chargers/pursuers touching broken units, Query 14 "ThreatInReach", collision contact) | the moving unit making the contact attacks | any wound | +1 | — | **this is how pursuit kills are credited**: the pursuer gets them. Friendly units can be hit (script_behaviours code 14) |
| Missile weapons (bows, crossbows, handguns) | the shooting unit | lethal-only | +1 | — | the projectile carries its shooter to impact |
| Artillery and other area shots (cannon ball and bounce, stone thrower/mortar blast, Hellblaster, Gyrocopter bomb, ...) | the firing unit | lethal-only | +1 | — | only the firer's own unit is excluded from the blast; other friendly units in the area are hit **and credited to the firer** |
| Spell damage, direct and area (fireball family, magical impacts) | the casting unit | lethal-only | +1 | — | effect owner = caster |
| Conflagration of Doom finale, Da Krunch (slain outright) | the casting unit | set on every slain model | +1 | — | **no exclusion at all**: the caster's own unit can be slain and credited to itself |
| Sapphire Arch: a unit kept away too long is killed | **none** | cleared | +1 | — | |
| Animation-driven impacts (e.g. the Giant's blast) | the unit whose model plays the animation | lethal-only | +1 | — | 🟡 list of animations using this impact not enumerated |
| Fanatic hitting models (Infantry/Cavalry/Archers/Wizard/Monster, artillery crew and machine, rolling stock, Special) | the fanatic unit | any wound | +1 | — | |
| Fanatic's own death after hitting artillery/rolling stock/building/Special | **none** | cleared | +1 (fanatic unit) | — | |
| Contact attacks on a fanatic by a unit moving through it | that unit | any wound | +1 (fanatic) | — | the player can earn kills on fanatics |
| Own artillery misfire (explosion) | **none** | cleared on the machine and on every crew model it kills | +1 per model | — | a crew model wounded but not killed keeps any older credit |
| Unit flees off the map (rout, scripted flee) | the model's existing credit, if any | — | +1 per model | **+1 per model** | event 0x0E then removal of all remaining models |
| Script removal of a unit (opcode 0x8C `RemoveFromBattle`) | existing credit, if any | — | +1 per model | +1 per model | if the unit was marked "kept for return" (siege), its `s_size`, `s_calualties`, `s_routed` are restored afterwards (§2.4) |
| Script kill of all models (opcode 0x8B `KillAllModels`) | existing credit, if any | — | +1 per model (killed) | — | 🟡 models die through their death sequence; credit is whatever they carried |
| Fanatic entering a terrain area that removes it | existing credit | — | +1 | +1 | |
| Building destroyed | existing credit of the building's first piece | — | +1 per piece | single-piece building types: +1 (removed alive); multi-piece types: — (killed) | building pseudo-units have `s_pntval` 0: the credited unit gains **+1 `s_kills`, +0 `s_Exp`** |
| Drowning / terrain damage to ordinary units | — | — | — | — | no such removal exists |

When is the credit cleared/reset? Only by misfire, fanatic self-death and the Sapphire Arch expiry (all set it to
"none"). Otherwise it is overwritten by the next qualifying hit and survives non-qualifying ones:

- a model wounded in close combat by X, then hit non-lethally by a missile from Y: credit stays X;
- the same model then hit lethally by Y's missile: credit becomes Y (Y gets the kill);
- a model already at/over its W but not yet removed (inside the collapse delay) can still be re-credited by a
  later lethal-only or any-wound hit; the unit that hit it last before removal gets the kill 🟡 (whether close-combat
  partners keep striking a dying model during the delay is not confirmed; blasts and missiles certainly can pick it).

Stale credit on removal alive: yes. A model removed alive (its unit runs off the map, script removal, fanatic
terrain) credits its stored unit. With W = 1 models this cannot happen (any credit-setting wound kills them), so
in practice it concerns monsters, war machines, characters/leaders and other multi-wound models.

### 2.2 Which `s_pntval` (A2) ✅

- The **victim unit's troop-profile `s_pntval` at the moment of removal** (an unsigned byte, so it includes campaign
  promotions: +7 each, `campaign.md` §1.3). It is a per-unit value: the leader model, a champion, the war machine
  model of an artillery unit and every crew model all give the same value. The leader's own profile value is never
  used.
- **No multiplier** of any kind (characters, monsters, wizards, artillery crew, buildings).
- A building pseudo-unit's `s_pntval` is 0 (§2.1, last rows).
- `s_Exp` is a 16-bit signed field written as a decimal; 🟡 overflow above 32767 not tested (unreachable in practice).

### 2.3 Allied NPC units and sides (A3) ✅

- No side test exists at credit time. Allied NPC units (side "ally") credit their own `s_kills`/`s_Exp` for kills they
  make; kills **of** allied NPCs are credited to whoever caused them (enemy, or player/ally through blasts,
  Conflagration, contact attacks); a unit under Madness credits its kills to itself whatever side it hits.
- Side matters only at writing time (§2.5): enemy units are never written, so their credit is lost; NPC units are
  written only when NPC merging is enabled (objective `G` or `I` defined) and `whoami < 50`.
- When NPC merging copies an army regiment into an NPC at battle start, it copies `s_Exp` (not `s_kills`,
  `s_calualties`, `s_routed`), so the NPC's experience continues from its career value.

### 2.4 `s_calualties`, `s_routed`, battle start and end (A4) ✅

- `s_calualties` = **every** model removed from the unit this battle (killed + removed alive).
- `s_routed` = models removed **alive** (fled off the map, script removal, fanatic terrain, single-piece building).
- `s_size` = models still in the unit (models in their collapse delay still count; see "Battle end" below).
- **Battle start:** the four counters are read from the unit text (`set:s_calualties=… s_routed=… s_kills=… s_Exp=…`)
  exactly as given; nothing resets them when `MARCH.MRC` is loaded. In the campaign they arrive as 0/0/0 and the career
  `s_Exp` because the debrief step zeroes the first three before writing the army (§3.3 P5 and §3.5).
- **Battle end (tent button):** the final objective pass, then `debrief.dbf` is written. There is **no** end-of-battle
  pass over remaining models: units still on the field — routing, rallied or steady — are written under
  **Surviving Units** with their live `s_size` and counters unchanged; units removed during the battle (all models
  dead or fled, or removed by script) are written under **Dead or Routed Units** with `s_size` 0 (except
  "kept for return" units, below). Models whose death sequence has not started yet when the tent is pressed are
  still in `s_size` and not counted anywhere.
- Siege battles (objective `G`) 🟡: its final step removes every player/allied unit still on the field that is not
  marked as having got in, zeroing its `s_calualties` and `s_routed` ("killed"), and brings units removed while
  marked "kept for return" back to the surviving set; the exact mark and the campaign consequence need an in-game
  check. Objective `I` / NPC merge clean-ups remove units with their size set to 0 first, so they change no counter,
  and take them off the dead/routed list (they are not written).

Before/after (player unit, `s_orgsize` 20, start 20/0/0):

| Case | Section in `debrief.dbf` | `s_size` | `s_calualties` | `s_routed` | → campaign (§3, default option) |
|---|---|---|---|---|---|
| loses 5 in melee, routs off the map with 15 | Dead or Routed | 0 | 20 | 15 | lost 5 → 3 wounded, 2 dead; `s_size` 0 + 15 = 15 |
| loses 5, still routing on the field at the end | Surviving | 15 | 5 | 0 | lost 5 → 3 wounded, 2 dead; `s_size` 15 |
| loses 5, routs, rallies, ends on the field | Surviving | 15 | 5 | 0 | same as above |
| loses 5, never routs | Surviving | 15 | 5 | 0 | same as above |
| all 20 killed | Dead or Routed | 0 | 20 | 0 | lost 20 → 13 wounded, 7 dead |

The engine model described by the implementer (`routed = all models if fled else 0, casualties = dead + routed`,
size = models alive on the field) matches these rows. Differences from the original: kill credit is missing, models removed alive can credit a unit, models still in
their collapse delay at the end are neither casualties nor credits, and the list section depends on removal, not on routing.

### 2.5 The `debrief.dbf` unit writer ✅

Per unit (both sections): unit name, `whoami`, `hired`, banner/graphics lines, item and spell lines, the stat
fields `s_side`…`s_rnks` (13–16, so `s_orgsize` unchanged and the live `s_size`), 21–29 (M…Ld), 30–35, 36–39, then
`set:` lines `s_calualties`, `s_routed`, `s_kills`, `s_Exp` with the raw battle values, psychology, the leader block
when the unit has one, and the battle `dir`/`x`/`y`.

- Surviving Units: every unit still in the battle that is a player unit, or an allied NPC with `whoami < 50` when
  objective `G` or `I` is defined.
- Dead or Routed Units: the same filter over the removed-unit list. For such an NPC **only `s_calualties` is set to 0**;
  `s_routed`, `s_kills`, `s_Exp` are written unchanged.
- Units with `whoami ≥ 50` (story NPCs), enemy units, buildings and other pseudo-units are never written.

### 2.6 Test vectors

| Before | Event | After |
|---|---|---|
| victim unit V (`s_pntval` 15, W 1) 10 models 0/0/0; X `s_kills` 3, `s_Exp` 40 | X's model wounds one V model in close combat; collapse delay ends | V `s_size` 9, `s_calualties` 1, `s_routed` 0; X 4 / 55 |
| same | X wounds it, battle ends (tent) before the collapse delay ends | V `s_size` 10, 0/0; X 3 / 40 |
| Troll T (`s_pntval` 50, W 3); X 3/40, archers Y 0/0 | X deals 2 wounds in melee; Y's arrow deals the 3rd | T `s_calualties` 1; **Y** 1/50, X 3/40 |
| T (W 3); Y 0/0 | Y's arrow deals 1 wound (non-lethal); T routs off the map | T `s_calualties` 1, `s_routed` 1; nobody credited |
| T (W 3); X 3/40 | X deals 1 wound in melee; T routs off the map | T `s_calualties` 1, `s_routed` 1; **X 4/90** (stale credit) |
| enemy unit E (15 models, `s_pntval` 12) routing; pursuer P 0/0 | P's contact attacks wound 2 models; E then leaves the map with 13 | E `s_calualties` 15, `s_routed` 13; P 2/24 |
| player cannon C 0/0 | cannon ball kills 3 enemy (`s_pntval` 9) and 1 model of friendly unit F (`s_pntval` 10) | C 4 / 37; F `s_calualties` 1 |
| player cannon, 3 crew | misfire explosion kills machine and 1 crew | cannon `s_calualties` 2, nobody credited |
| wizard unit W 0/0 (own unit 1 model, `s_pntval` 40) | its Da Krunch/Conflagration covers its own unit and 5 enemy models (`s_pntval` 6) | W 6 / 70 (credits itself) and W `s_calualties` 1 |
| fanatic unit N 0/0; player unit P (`s_pntval` 8) | N wounds 3 P models, then hits artillery and dies | N 3/24; N's own removal credits nobody |
| player cannon C 2/20; building (single piece) | C's shot is lethal on the building | building removed alive; C 3/20 |
| player unit P 20 models, objective `G` battle, P outside at the end 🟡 | final pass | P in Dead or Routed, `s_size` 0, `s_calualties` 0, `s_routed` 0 |

## 3. Campaign side: one state machine for casualties, wounded, healing and disbanding ✅

### 3.1 State

Per regiment, in the unit text of each file (`debrief.dbf`, `PLAY.MRC`, `ARMY.MRC`, `MARCH.MRC`):
`s_size` (models present), `s_orgsize`, `s_calualties`, `s_routed`, `s_kills`, `s_Exp`. Per `whoami`, in the roster
(`notes/campaign.md` §4.5): `wounded_last` (`+0x2C`, wounded of the most recent battle the regiment fought), `returning`
(`+0x30`, wounded that rejoin at the current debrief's Done), `exp_at_start` (`+0x1C`), `keep` (`+0x00`), `artillery`
(`+0x0C`). Option `dead` (developer command line only): the share of lost models that die; **default: 65 % of lost models
are wounded, 35 % die** (`dead:N` makes the wounded share `100 − N`, N clamped to 0–100).

Derived values (used everywhere below):

```
lost      = s_calualties − s_routed
wounded   = lost × 65 // 100            (integer division; default option)
dead      = lost − wounded
present   = s_size + s_routed           (strength for prices, disbanding and "destroyed")
destroyed = present == 0, or (artillery and present < 2)
```

### 3.2 Which debriefs run it

Only the **post-battle** debriefs (modes 2 and 6: `playgame…` / `encounterplaygame…`) run the bookkeeping. Glue
`debrief:` / `debriefwithsummary:` (modes 4 and 7) only pay; they touch no wounded, healing, merge or disbanding. With the
developer option `nobattle` the pre-screen part is skipped entirely.

### 3.3 Before the screen (right after the battle, modes 2 and 6), in this order

| # | Step | Effect |
|---|---|---|
| P1 | Campaign-over test | `notes/debrief_evaluation.md` §3.1, with the precise "commander dead" test of §3.6 below. If the campaign is over: death movie, title screen, **nothing else** in this table or at Done runs. If the commander regiment is dead but `Z` is not met: its `s_routed += 1`, `debrief.dbf` rewritten. |
| P2 | Shift | For **every** roster entry (all 38 regiments, marching or not): `returning := wounded_last` (overwrite, not add), `wounded_last := 0`. |
| P3 | New wounded | For every unit in `debrief.dbf` (surviving and dead/routed lists, allied NPCs included): `wounded_last[whoami] := wounded` of that unit. |
| P4 | Model back | For every unit in `debrief.dbf`: **whoami 2** (commander's regiment): if `destroyed` and `wounded > 0` → `s_routed += 1` and `wounded_last −= 1`. **Any other** regiment with `keep`: if `present + wounded == 0` → `s_routed += 1` (no wounded counter changes). `debrief.dbf` rewritten. |
| P5 | Merge into `PLAY.MRC` | For every debrief unit whose `whoami` is in `PLAY.MRC` (all 38 always are): copy the troop and leader profiles (including `s_size`, `s_orgsize`), `s_calualties`, `s_routed`, `s_kills`, `s_Exp`, the spell list and the item list. Then for **every** unit of `PLAY.MRC`: `s_size += s_routed`, `s_calualties = s_routed = s_kills = 0` (`s_Exp` is kept). File written. |
| P6 | `Z` | If objective `Z` is present and met: `wounded_last := 0` for every roster entry. `returning` is **not** touched. |

### 3.4 On the screen

- The troop page (P3) reads `debrief.dbf` as left by P4: kills = `s_kills`, dead/wounded from the formulas above,
  experience = `s_Exp − exp_at_start` (**before** doubling; the doubled value is never shown).
- Text op `0x1C` (only in the success list of `setdebrief:33`, `bf021`) runs when the mission-text page is drawn:
  for every roster entry `returning += wounded_last`, `wounded_last := 0`. Drawing the page again changes nothing.
  It never runs when the screen is skipped (no list → no page).

### 3.5 Done (modes 2 and 6), in this order

| # | Step | Effect |
|---|---|---|
| D1 | Payment | mode 2 only (`notes/debrief_evaluation.md` §6) |
| D2 | Armour rewards | on `debrief.dbf` (`notes/campaign.md` §1.4) |
| D3 | Experience | per debrief unit: doubling, promotions (`notes/campaign.md` §1.2–1.3), then `exp_at_start[whoami] := s_Exp` (the doubled value); `debrief.dbf` written |
| D4 | Merge into `ARMY.MRC` | as P5's copy, for debrief units whose `whoami` is in the army (no `s_routed` return here) |
| D5 | Heal and disband `ARMY.MRC` | for **every** army regiment (marching or not), in file order: **heal** — if `s_size + returning > s_orgsize` then `s_size := s_orgsize`, `s_calualties := 0`, `s_routed := 0` (the excess returning wounded and any pending routed models are lost); else `s_size += returning`. Then **disband** if `present < max(1, s_orgsize × 20 // 100)` and `whoami ≠ 2` and not `keep`: the regiment is removed from the file. File written. |
| D6 | mode 6 only | `ARMY.MRC`: `s_size += s_routed`, counters `s_calualties`, `s_routed`, `s_kills` := 0, written. Then the same D4 merge, D5 heal/disband (same `returning` values) and routed return/counter reset on `MARCH.MRC`. |
| D7 | Clear | `returning := 0` for every roster entry; then the glue script continues. |

In **mode 2** `ARMY.MRC` keeps `s_routed`/`s_calualties`/`s_kills` from the battle after Done; the routed models rejoin
`s_size` (and the counters reset) when troop selection is confirmed (`ARMY.MRC` and `PLAY.MRC`), which also rewrites
`MARCH.MRC` from the selection. Until then `present` (prices, "destroyed", the reinforcement limit) includes them.
The reinforcement window allows at most `s_orgsize − (s_size + s_routed + wounded)` new models, with `wounded`
computed from the army file's counters — i.e. it reserves room for the wounded of the last battle only while those
counters still exist (between Done and troop selection).

### 3.6 The commander-dead test, precisely

The commander regiment (whoami 2) is "dead" when it is in `debrief.dbf` and `s_size + s_routed + wounded == 0`, with
`wounded = lost × 65 // 100` of **this** battle (the roster counters are not used). With the default option a lost
regiment of 2 or more models always has `wounded ≥ 1`, so the regiment counts as dead only if it lost **at most one**
model and none are left or routed — in practice only when it entered the battle with a single model. Otherwise P4 gives
it one wounded model back when it was wiped out.

| Cavalry in `debrief.dbf` | wounded | dead? | P1 | P4 |
|---|---|---|---|---|
| s_size 0, s_calualties 12, s_routed 0 | 7 | no | campaign continues (G/Y test only) | `s_routed` 0→1, `wounded_last` 7→6 |
| s_size 0, s_calualties 1, s_routed 0 | 0 | yes | Z met → game over (`death01`); else `s_routed` 0→1 | not destroyed any more → nothing |
| s_size 0, s_calualties 5, s_routed 5 | 0 | no (routed 5) | — | not destroyed → nothing |

### 3.7 Worked examples (mode 2, one regiment, `s_orgsize` 20, not `keep`)

Battle 1: enters with 20, 10 killed and 4 routed off the map. Battle 2: enters with 10, loses nothing.

| Moment | s_size | s_routed | s_calualties | wounded_last | returning | note |
|---|---|---|---|---|---|---|
| debrief 1 written | 6 | 4 | 14 | 0 | 0 | lost 10 → wounded 6, dead 4 |
| P2 shift | 6 | 4 | 14 | 0 | 0 | |
| P3 | 6 | 4 | 14 | **6** | 0 | |
| P5 `PLAY.MRC` | 10 | 0 | 0 | 6 | 0 | PLAY only |
| D5 `ARMY.MRC` | 6 | 4 | 14 | 6 | 0 | heal adds 0; present 10 ≥ 4 → kept |
| D7 | 6 | 4 | 14 | 6 | 0 | |
| troop selection confirmed | 10 | 0 | 0 | 6 | 0 | routed rejoin |
| debrief 2 written | 10 | 0 | 0 | 6 | 0 | |
| P2 shift | 10 | 0 | 0 | 0 | **6** | |
| P3 | 10 | 0 | 0 | 0 | 6 | no new wounded |
| D5 heal | **16** | 0 | 0 | 0 | 6 | 10 + 6 ≤ 20 |
| D7 | 16 | 0 | 0 | 0 | 0 | 4 dead for good |

Variants (start from "debrief 2 written" unless stated):

| Case | Before | Result |
|---|---|---|
| Cap: reinforced to 18 after troop selection (the window then no longer reserves room), battle 2 no losses | s_size 18, returning 6 at D5 | 18 + 6 > 20 → s_size 20; 4 returning wounded are lost |
| `Z` met in battle 2, which lost 6 models (→ wounded 3) | P3 sets wounded_last 3; returning 6 | P6 clears wounded_last (3 lost for good); D5 still heals the 6 from battle 1 |
| `Z` met in battle 1 | wounded_last 6 after P3 | P6 → 0: all 10 lost models are gone; returning unaffected |
| Op `0x1C` (bf021 success) in battle 1 | after P3: wounded_last 6, returning 0 | page drawn → returning 6, wounded_last 0; D5 heals at once: s_size 6 + 6 = 12, routed 4 rejoin later → 16 |
| Not marching in battle 2 but in the army | wounded_last 6 from battle 1 | P2 shifts it to returning; D5 heals the army copy to 16 although it did not fight |
| Wiped out, not `keep`: s_size 0, s_routed 0, lost 20 | wounded 13 | P3 wounded_last 13; D5 present 0 < 4 → disbanded; the 13 never return (unless a script brings the regiment back and it is in the army at the next debrief) |
| Wiped out, `keep` | wounded 13 | not disbanded; stays with 0 models ("destroyed", cannot be selected); next debrief heals 13 |
| `keep`, s_size 0, s_routed 0, lost 1 | wounded 0 | P4: s_routed 1 → one model back |
| Disband boundary, s_orgsize 20 | present 3 / 4 | 3 < 4 disbanded / 4 kept |
| Disband boundary, s_orgsize 4 | present 0 | 4 × 20 // 100 = 0 → limit 1 → disbanded; present 1 kept |

### 3.8 Answers to B1–B6 in short

- **B1** One state machine: P1–P6 before the screen, op `0x1C` on the text page, D1–D7 at Done. "Healed at Done" (D5 adds
  `returning`) and "committed by op 0x1C" (moves this battle's `wounded_last` into `returning` early) are both true; D7
  then clears `returning`.
- **B2** §3.7.
- **B3** Yes: P2 shifts every roster entry and D5 heals and disband-tests every army regiment, marching or not. Modes 4/7
  do none of it.
- **B4** A disbanded regiment is dropped from `ARMY.MRC` (mode 6: also `MARCH.MRC`). Its `PLAY.MRC` record keeps the P5
  state (so a later `unitjoinmission`/`addunit` brings it back with that strength, experience and kit); its roster entry
  keeps `wounded_last` and `exp_at_start`; `returning` is cleared by D7 like everyone's. The roster's "in army" flag is
  only recomputed when troop selection is confirmed or a game is loaded 🟡 (a `testforunitinarmy` right after the
  debrief still sees it). A `keep` regiment at 0 models keeps its wounded and heals at the next debrief.
- **B5** Yes, through the files: an allied NPC with `whoami < 50` is written to `debrief.dbf` like a player unit, so P3
  records its wounded, P5 copies its result into `PLAY.MRC`, and D4–D5 merge and heal it in `ARMY.MRC` if that regiment
  is in the army. (Which NPC units are written and with which counters: §2.)
- **B6** The troop page shows `s_Exp − exp_at_start` read before D3, i.e. **without** the ×2. `s_kills` is reset to 0
  whenever routed models are returned (P5 for `PLAY.MRC`, troop selection / mode-6 Done for the army and march files),
  so the next battle starts from 0; `s_Exp` is never reset and accumulates.

### 3.9 Quirks an engine should reproduce or consciously drop

- `PLAY.MRC` is merged **before** Done, so it holds the un-doubled experience, no promotions and no armour reward of
  that battle; a regiment that leaves (`unitleavemission`) and later rejoins from `PLAY.MRC` comes back without them,
  and its next "experience gained" (`s_Exp − exp_at_start`) can be negative.
- The troop page's wounded column for the commander's regiment is recomputed from the file after P4's `s_routed + 1`
  (`(lost − 1) × 65 // 100`), which can differ from the roster's `wounded_last − 1`.

## 4. Corrections made to other notes

- `notes/game_rules.md` field table rows 40–42 (`s_calualties`, `s_routed`, `s_kills`) and §7.2 "Removal without
  death … adds to `s_routed` instead": removal alive adds to **both** `s_calualties` and `s_routed`; `s_kills` counts
  models removed while the unit held their credit, any side, removed alive included.
- `notes/campaign.md` §1.1: credit is paid on removal (killed or alive) to the unit holding the model's credit (§2.1),
  not simply "when a model dies".
- `notes/campaign.md` §3.3 items 3, 6 and 7: `Z` clears only this battle's wounded (`wounded_last`), not `returning`;
  the heal cap also clears `s_routed`; the commander-dead test uses this battle's computed wounded (§3.6).
- `notes/campaign.md` §4.8: for dead/routed NPCs only `s_calualties` is reset.
- `notes/campaign.md` §5 step 6: in mode 6 `MARCH.MRC` is merged, healed and disband-tested on its own (§3.5 D6), not
  "rewritten from the army".
- `notes/debrief_evaluation.md` §3.1 (commander dead) and §3.2 (`Z` clears the *new* wounded, not the returning ones).
- `FORMATS.md` token 34 `s_pntval`: ✅.

## 5. Open items

- 🟡 Whether close-combat partners keep striking a model during its collapse delay (affects who gets the credit when
  two units fight the same dying model).
- 🟡 Which animations carry the animation-driven impact (Giant's blast confirmed in `game_rules.md`; others?).
- 🟡 Objective `G` final step: the "got in" mark and whether regiments left outside really return with 0 models
  (needs an in-game check of BF015/BF017).
- 🟡 Opcode 0x8B `KillAllModels`: confirm the models then die through their ordinary death sequence (killed path).
- ⬜ No `debrief.dbf`/save after a completed Done exists locally; §3 rests on the code paths and arithmetic
  (`notes/campaign.md` §8).
- In-game confirmation suggested: one monster wounded in melee that then routs off the map should give the melee unit
  a kill in the debrief troop book.
