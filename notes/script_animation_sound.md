# Unit-script animation requests, sound cues and casting-state queries

Public implementation report, batch 6 of the interpreter requests (GitHub #3). Behaviour only. Companion to
`unit_script_control.md` (condition word, LIFO event queue), `movement_formation.md` (per-tick order, the halted
signal), `target_queries.md` (`PendingInRange*`, casting arc), `threat_events_nodes.md` and `game_rules.md`. Script
listings come from `python3 -m whshr scripts <installation>`.

**Read in `game_rules.md` rather than re-deriving:**
- "Figure animation: actions, timing, and why the figures are never in step": the seven action ids (1 stand,
  2 idle, 3 walk, 4 fight, 5 weapon ready, 6 dead, 7 shoot/cast), random entry, "re-issuing the current action does
  nothing", one-shots that cannot be interrupted (the new action is queued), the shoot script, and the **volley
  countdown rule** (countdown = N, an event every time the new value is divisible by the modulus). This report
  only adds who sets the request and how scripts read it back.
- "Winds of magic and casting" (order 0x17 → event 0x2B, casting animation → event 0x2C → `CastPending`; busy wizard
  refuses with `GMTXT 2014`; Storm of Shemtek and Flying Bower keep the wizard busy) and "AI casting".
- `notes/sfx.md`, "Packet table": the sound packet slots (1 `buttonfx` … 17 `Peasant`) and effect indices.

Opcode lengths are from `whshr/behaviour.py` `LENGTHS`. Counts are uses across all mission DLLs (the shared library
100–170 counted once per DLL). Operands are decimal as `whshr scripts` prints them.

## 0. Shared state (read this first)

Every opcode in this batch reads or writes one of four pieces of state. Getting these right matters more than any
single opcode.

### 0.1 The unit's **action broadcast** (one tick long)

A unit holds one **requested action** (0 = none). During the unit's **model update**, which is the **last step of the
unit's own tick** (after the script, the formation update and the movement handler — `movement_formation.md` §1.2),
every model of the unit is visited in order:

1. if the model has its **own pending request** (§0.2), that is applied, and the broadcast is **ignored** for that
   model this tick;
2. otherwise, if the unit's requested action is non-zero, it is applied to the model;
3. after all models are visited the unit's requested action is **reset to 0**.

So the broadcast is a **one-tick pulse**, not a persistent override. What persists is the model's *current action*:
a model keeps playing the action it was given until something requests another one. "Applying" an action to a model
(the same rule for broadcast and own requests):

| model state | result |
|---|---|
| the model is **frozen** (e.g. a wizard channelling Storm of Shemtek) | request dropped |
| the model is already playing that action | nothing (no restart, no new random entry) |
| the model is in an **uninterruptible one-shot** (shoot/cast pose, death) | request **queued** as the model's own pending request; applied when the one-shot ends |
| otherwise | the model switches to the action at the start of its program (random entry rolled as in `game_rules.md`) |

The game itself writes the broadcast only **on state changes**, not every tick. Its main writers are:

- **halting / end of a wait / a move order to the unit's own spot** → the **rest action**, chosen in this order:
  charging (or another forced-run state 🟡) → 3 walk; a move, turn, flee or pursuit still active (and not in a
  timed wait) → 2 idle;
  the unit has a current target and is not an anchored war machine → 5 weapon ready; else → 1 stand;
- **starting a move or turn**, snapping a formation, a re-form → 2 idle (the models that actually walk then get 3
  through their own requests, §0.2);
- certain monster attacks run as effects (e.g. a dragon's fire breath) → 7 for the attacker's unit; the end of
  certain effects → 1.

Walking (3), fighting (4) and weapon-ready (5) are mostly **per-model** requests issued by the model movement and
close-combat pairing code (a model that walks to its slot or its opponent asks for 3, a paired model 4, an unpaired
model in melee 5, a model that arrives asks for the unit's rest action).

**Difference from the current engine:** the engine derives one action per model every tick from the regiment's
state. The original does not re-assert anything per tick; a request is made when something changes, and the last
request wins. A script request (`SetActionState`, `PlayUnitAnimation`) therefore **sticks** until the next state
change re-requests something else (the next halt, move start, pairing change, arrival …). If the engine keeps its
per-tick derivation, it must at least treat a script request as sticky until the next such change; otherwise
`SetActionState 4` in BF014 (models fighting in place while the unit stands) is undone on the next tick.

### 0.2 The model's **own pending request**

One action id per model (0 = none), consumed (cleared) at the model's next update, whether it is applied, dropped or
re-queued behind a one-shot. `PlayLeaderAnimation` writes it on the leader model only.

### 0.3 The unit's **animation request** (event code, divisor, countdown)

Three numbers per unit, all 0 when idle:

| field | meaning |
|---|---|
| **event code** | the event the models post to their own unit when their animation reaches its event step |
| **divisor** | post one event every *divisor*-th arrival |
| **countdown** | arrivals still expected; 0 = no request pending / request finished |

The **event step** inside an animation program (the shoot pose and the cast pose of every unit family have one; see
`game_rules.md` for its timing) does: if countdown > 0, countdown − 1; if the **new** countdown is divisible by the
divisor, post the event code to the unit. With countdown 0 the step does nothing (no event, no division). This is
exactly the volley rule of `game_rules.md`; `PlayLeaderAnimation` is the same rule with countdown 1 and divisor 1.

The request is cleared (all three to 0) by `ClearAnimationRequest` and by a successful `IfAnimationDone` (§2.4). It
is **not** cleared when the countdown reaches 0 by itself; the event code and divisor stay but are inert.

### 0.4 The unit's two **sound handles**

A **charge-sound handle** and a **loop-sound handle** (0 = none). They only matter for `MoveUnitSound`,
`StartUnitLoopSound` and `StopUnitLoopSound` (§4). No game rule reads them.

## 1. Summary table

| op | name | words | operands | condition written | blocks? | uses |
|---|---|---|---|---|---|---|
| 0x8D | `SetActionState` | 2 | action | no | no | 15 (mission only) |
| 0x8E | `PlayUnitAnimation` | 4 | action, event, divisor | no | no | 92 (library 115, 117; BF039) |
| 0x8F | `PlayLeaderAnimation` | 3 | action, event | no | no | 180 (library 115, 117, 132, 142) |
| 0x90 | `IfAnimationDone` | 2 | action | **yes** | no (scripts loop on it) | 212 |
| 0xE7 | `ClearAnimationRequest` | 1 | – | no | no | 128 |
| 0xA8 | `IfCastingAnimation` | 2 | message flag | **yes** | no | 241 |
| 0xA9 | `IfCasting` | 3 | re-enable flag, message flag | **yes** | no | 225 |
| 0x8A | `TurningToCastMessage` | 2 | flag | no | no | 45 (library 132) |
| 0xC0 | `PlaySoundAtUnit` | 3 | packet, effect | no | no | 8 |
| 0xC3 | `PlaySound` | 3 | packet, effect | no | no | 8 |
| 0xC4 | `StartUnitLoopSound` | 4 | packet, effect, fader | no | no | 1 (BF040) |
| 0xC5 | `StopUnitLoopSound` | 1 | – | no | no | 1 (BF040) |
| 0xC6 | `MoveUnitSound` | 2 | which handle | no | no | 91 |

None of these instructions yields: each completes immediately and the script continues in the same tick. "Condition
written: no" means the condition from the previous instruction survives (relevant for `If` right after them).

## 2. Animation opcodes

### 2.1 `SetActionState action` (0x8D, 2 words)

Sets the unit's action broadcast (§0.1) to `action`. Nothing else: no event, no countdown, no condition.

- Takes effect in this tick's model update (the script runs before it), unless the formation or movement step of the
  **same tick** writes the broadcast again (last write wins).
- Applies to every model without its own pending request this tick, subject to the frozen/one-shot rules.
- Does not stop or start movement; it is purely the figures' animation. A moving unit given `SetActionState 1`
  keeps moving with standing figures until its models next request walk.
- Shipped values: **1** (10 uses: BF005, BF015, BF017, BF020, BF026, BF029, BF030, BF031, BF040, BF042 — stand the
  figures still after a scripted halt or reveal) and **4** (5 uses, BF014 script 7 — figures fight in place).

### 2.2 `PlayUnitAnimation action event divisor` (0x8E, 4 words)

Sets the broadcast to `action` and the animation request (§0.3) to (event, divisor, **countdown = the unit's
current model count**). A previous request is overwritten without posting anything.

- Shipped: `7 34 4` and `7 35 4` (library 115/117: a volley — every 4th model posts event 34 or 35, which the
  shooting scripts turn into projectiles; `game_rules.md` volley rule) and `3 53 1` (BF039 scripts 7 and 9, the
  **Squig Hoppers** (correction: BF039's seven units are all Squig Hoppers, not fanatics; `script_spawn_move.md` §0):
  the squig hopper's walk program ends with an event step, so every hop posts event 53, which script 7
  catches to jump again).
- Divisor 0 is never shipped; treat it as invalid (the event step divides by it).
- Models that are frozen, dead before reaching the event step, or still finishing another one-shot when the request
  arrives may never reach the event step, so fewer than ⌈N / divisor⌉ events can be posted. Nothing waits for them;
  see `IfAnimationDone`.

### 2.3 `PlayLeaderAnimation action event` (0x8F, 3 words)

If the unit has a **leader model** (the champion/character model, or the machine of a war machine): set the
leader's own pending request (§0.2) to `action`, and the animation request to (event, divisor 1, countdown 1).
The other models are not touched.

If the unit has **no leader model**, nothing happens at all — **the previous animation request is left as it was**,
no event will ever be posted, and no condition is written.

Shipped: `7 34` / `7 35` (library 115/117: war machines and other non-Archers classes fire from the leader/machine
only) and `7 44` (library 132 and 142: the cast pose; its event step posts **event 44 (0x2C)**, which library 155
handles with `GosubScript 133` → `CastPending`, i.e. the spell launches at the event step, not at the end of the
pose).

### 2.4 `IfAnimationDone action` (0x90, 2 words)

Writes the condition. Exactly:

```
if countdown == 0:                      -> true   (no request, or every expected event step has been reached)
elif action == 0:                       -> false  (request kept)
elif any model of the unit is currently playing `action`:
                                        -> false  (request kept)
else:                                   -> clear event, divisor, countdown; true
```

- "Currently playing" is the model's **current** action, not a queued one. All models are scanned (leader
  included), whoever started the action. A model with action 7 still **queued** behind another one-shot does not
  count; if no model is in action 7 at that moment the request is cleared and its event will never be posted
  (🟡 edge case, rare in practice).
- The test is per unit, not per leader: after `PlayLeaderAnimation 7 44`, `IfAnimationDone 7` is true as soon as the
  leader's event step has run (countdown 1 → 0), even though the leader still has two ticks of pose left.
- With no request pending it is simply true, so a script can call it unconditionally.
- The "clear" branch is how a volley abandoned by dead or frozen models stops blocking: once no model is in the pose
  any more, the request is dropped and the shooting script moves on.
- Shipped operand: always **7**.

### 2.5 `ClearAnimationRequest` (0xE7, 1 word)

Sets event, divisor and countdown to 0. It does **not** change any model's action and does not touch the broadcast:
models already in the shoot or cast pose finish it, but their event step now posts nothing (no projectile, no cast).
Used at the start of the library shooting loops 113/114 (so a stale volley from an earlier order cannot fire) and by
38 mission uses in 20 DLLs.

### 2.6 Test vectors

N = models in the unit; "req" = (event, divisor, countdown); "bc" = action broadcast; L = leader model.

| before | instruction | after |
|---|---|---|
| bc 0, req (0,0,0), N = 10 | `PlayUnitAnimation 7 34 4` | bc 7, req (34,4,10); condition unchanged |
| req (34,4,10), models' event steps arrive one per tick | (model updates) | events posted at the 2nd, 6th and 10th arrival; req (34,4,0) |
| req (34,4,7): 3 models reached the step (countdown 10→9→8→7, one event at the 2nd arrival), the other 7 died before it; no model in action 7 | `IfAnimationDone 7` | req (0,0,0); cond true; 1 event in total instead of 3 |
| req (34,4,7), 2 models still in action 7 | `IfAnimationDone 7` | req unchanged; cond false |
| req (34,4,0), models still in action 7 (trailing pose ticks) | `IfAnimationDone 7` | req unchanged; cond **true** |
| req (0,0,0) | `IfAnimationDone 7` | cond true |
| req (34,4,3) | `IfAnimationDone 0` | cond false, req unchanged |
| unit with leader L, req (0,0,0) | `PlayLeaderAnimation 7 44` | L's own request 7; req (44,1,1); bc unchanged |
| L in action 7, req (44,1,1), L reaches its event step | (model update) | countdown 0, event 44 posted to the unit (0 is divisible by 1) |
| unit **without** a leader, req (34,4,6) | `PlayLeaderAnimation 7 44` | nothing changes: req (34,4,6) |
| req (34,4,6), 6 models in action 7 | `ClearAnimationRequest` | req (0,0,0); models keep the pose; their event steps post nothing |
| bc 0, model M walking (action 3), no own request | `SetActionState 1` | this tick's model update: M → action 1 (stand); bc reset to 0 |
| model M in the shoot pose (one-shot) | `SetActionState 1` | M's own request = 1, applied when the pose ends |
| model M already in action 4 | `SetActionState 4` | nothing for M (no restart, no new random entry) |
| script: `SetActionState 1`; same tick the move handler halts the unit | | the halt's rest action replaces the broadcast (last write wins) |

### 2.7 Worked example: the shooting loop (library 113 → 121 → 116 → 115)

```
script 113: ResetStack; SetUnitFlags2 4; React 13; ClearAnimationRequest
            PushPC; Yield; GosubScript 121; TestUnitFlags2 4; LoopIfTrue; ...
script 121: GosubScript 118; ReadyToFire 0
            If
              IfAnimationDone 7
              IfNot  PushPC; Yield; IfAnimationDone 7; LoopIfFalse  EndIf     # wait for the last volley
              FindTarget; InArcAndRange 0
              If GosubScript 116 (→ 115) ...
script 115: StampReload; ... React 10; IfClass 24
            If PlayUnitAnimation 7 34 4  Else PlayLeaderAnimation 7 34  EndIf
```

Tick by tick for a 10-model Archers unit (class 3, `IfClass 24` true), target in arc and range, reloaded:

1. Script 113 clears any stale request (req (0,0,0)). Next tick 121 runs: `IfAnimationDone 7` → true (countdown 0),
   so the wait is skipped; 116/115 stamp the reload and run `PlayUnitAnimation 7 34 4`: bc 7, req (34,4,10).
2. Same tick, model update: all ten models (none busy) switch to action 7 with their random skip; bc → 0.
3. Ticks 2–5 after the order: models reach the event step (each uniformly on tick 2…5, `game_rules.md`), the
   countdown runs 10 → 0, events 34 are posted on the 2nd, 6th and 10th arrivals → three projectiles.
4. Next pass of 121: if it comes while a model is still in action 7 and countdown > 0, `IfAnimationDone 7` is false
   and the script yields once per tick until either the countdown reaches 0 or no model is in the pose.
   `ReadyToFire` (reload) then gates the next volley.

The same loop for a war machine takes the `Else` branch: only the machine/leader model plays the pose, one event per
shot (req (34,1,1)).

## 3. Casting-state queries

The engine needs two named states per unit for these queries (and later for magic):

- **cast pose running**: some model of the unit is currently playing action 7. Note that action 7 is the shoot pose
  too: an Archers unit in mid-volley is "in the cast pose" for these tests.
- **spell pending**: the unit holds a spell chosen but not yet launched (set when the cast order / AI choice is taken,
  cleared by `CastPending` or `DropPendingSpell`).
- plus, from the spell engine, **channelling**: the unit is the caster of an active Storm of Shemtek or Flying Bower
  effect (`game_rules.md`: they keep the wizard busy until they end).

### 3.1 `IfCastingAnimation flag` (0xA8, 2 words)

Condition = **cast pose running OR channelling**. No class check (any unit). The spell-pending state is **not**
tested. If the result is true and `flag` ≠ 0, the battle message `GMTXT 2014` ("…is preparing to cast a spell", with
the unit's name) is shown. Shipped flag: always **0**.

Used by the AI wizard loops 135–140 (don't pick a new spell while busy) and in missions as "wait until not casting":
`PushPC; SetWait 5; Wait; IfCastingAnimation 0; LoopIfTrue` (`threat_events_nodes.md` B6).

### 3.2 `IfCasting reenable message` (0xA9, 3 words)

Condition = **is casting**, defined as:

```
false if the unit's class is not Wizard (class 5);
true if a model is in action 7, or a spell is pending, or the unit is channelling;
false otherwise.
```

So a non-Wizard caster (a leader with the casting weapon value, e.g. the Orc shaman on a Wyvern) is **never** "casting"
for this test 🟡 (consequence: such a unit is not protected by the busy checks of library 103/155).

When the result is true:
- `message` ≠ 0 → battle message `GMTXT 2014` (no unit name argument 🟡);
- `reenable` ≠ 0 → the **magic panel entry of the spell carried by the current event** is made available again,
  unless it is the same spell as the one already pending. This is the refusal path of a player cast order to a
  busy wizard; only the cosmetic "cast ordered" mark is cleared, button availability never depended on it
  (`notes/spell_lasting_effects.md` §8). 🟡 whether the power paid on the click is
  refunded is not settled here; nothing in this instruction changes the power pool.

When false: no side effect. Shipped operand pairs: **`0 0`** (176 uses; library 103 cases 3/4/6 and 155 case 10:
"ignore threats, new targets, being charged while casting") and **`1 1`** (44 uses; library 155 case 43 = event
0x2B, the cast order: busy → message + re-enable, else `TakeSpellEventTarget; GosubScript 132; Restart`).

### 3.3 `TurningToCastMessage flag` (0x8A, 2 words)

If `flag` = 0: show the battle message `GMTXT 2010` ("Turning Wizard to cast spell."). Otherwise nothing. **No game
state** changes and no condition is written. Used once per DLL, library 132 just before `GosubScript 141` (the turn
step). It is not filtered by side in the instruction itself 🟡 (whether AI wizards reach 132 is a question for the
magic batch).

### 3.4 Test vectors

| before | instruction | after |
|---|---|---|
| Wizard unit, no model in action 7, no spell pending, not channelling | `IfCasting 0 0` | cond false |
| Wizard, spell pending, models standing | `IfCasting 0 0` | cond **true** |
| Wizard, spell pending, models standing | `IfCastingAnimation 0` | cond **false** (pending is not tested) |
| Archers unit mid-volley (models in action 7) | `IfCastingAnimation 0` | cond **true** |
| Archers unit mid-volley | `IfCasting 0 0` | cond false (not class Wizard) |
| Wizard channelling Storm of Shemtek, models frozen | `IfCastingAnimation 0` / `IfCasting 0 0` | true / true |
| Wizard in cast pose; event 0x2B arrives carrying spell S ≠ pending | `IfCasting 1 1` | cond true; message 2014; S's panel entry re-enabled |
| as above but S = the pending spell | `IfCasting 1 1` | cond true; message 2014; panel unchanged |
| any unit | `TurningToCastMessage 0` | message 2010; condition unchanged |
| any unit | `TurningToCastMessage 1` | nothing |

### 3.5 Worked example: the player's cast order (library 155 → 132 → 141 → 142 → 133)

```
155 CaseEvent 43 (0x2B): IfCasting 1 1; IfNot  TakeSpellEventTarget; GosubScript 132; Restart  EndIf
132: TestUnitFlags2 8 (held) ...; PendingInRangeArc 1 → GosubScript 142
     else PendingInRange 0 → (in melee? DropPendingSpell : TurningToCastMessage 0; GosubScript 141;
                              PlayLeaderAnimation 7 44)
142: TestUnitFlags 512 (in melee) → ClearEvent; CastPending   else PlayLeaderAnimation 7 44
155 CaseEvent 44 (0x2C): SetCondFlags 4; GosubScript 133 → CastPending
```

The wizard's leader model plays the cast pose; its event step posts 0x2C; the event handler launches the pending
spell. From `PlayLeaderAnimation` until the pose ends, `IfCastingAnimation` and `IfCasting` are true; between the
order and the pose (while turning in 141), only `IfCasting` is (spell pending).

## 4. Sound opcodes (presentation only)

**No sound opcode changes game state**: no random numbers are drawn, no condition is written, no unit field other
than the two sound handles (§0.4) is touched, and nothing reads those handles except these opcodes and the game's own
sound stop calls. Recording each cue as a battle event and playing it in the frontend is a faithful implementation.

`packet` is the row of the sound packet table in `notes/sfx.md` (1 `buttonfx` … 17 `Peasant`); `effect` is the
**0-based** effect index inside that package (MoleMach has 2 effects and is played as 0 and 1; Dragon has 1 and is
played as 0). If the packet is not loaded in this battle (`loadsfx` in the `.BTS`), nothing plays.

| op | behaviour |
|---|---|
| `PlaySoundAtUnit packet effect` (0xC0) | positional: plays the effect at the unit's current position as an overlapping copy (several can sound at once). If the effect is a looping one it takes one of 31 sound slots, but the handle is not stored, so it can never be stopped or moved by script. Shipped: `6 5` (OrcBtl, BF004_5, BF015, BF034, BF038), `12 0` (Dragon, BF014). |
| `PlaySound packet effect` (0xC3) | non-positional; **not restarted if that effect is already playing**. Shipped: `11 0` (Zhufbar, BF015, BF017), `13 0` (PortCul, BF037), `14 1` (MoleMach, BF040). |
| `StartUnitLoopSound packet effect fader` (0xC4) | stops the unit's loop sound if any, then plays the effect at the unit's position (with `fader` ≠ 0 as a fading copy 🟡) and stores the handle as the unit's **loop-sound handle** (0 if the effect does not loop). Shipped once: `14 0 1` (BF040 mole machine). |
| `StopUnitLoopSound` (0xC5) | stops the sound in the loop-sound handle. The handle is not reset; stopping again is harmless. Shipped once (BF040). |
| `MoveUnitSound which` (0xC6) | moves the sound of the unit's handle — **0 = charge sound, 1 = loop sound** — to the unit's current position; nothing if that handle is empty. Positional sounds do not follow the unit by themselves, so scripts call this every tick of a loop. Shipped: `0` in library 106/160 (the charge loops), `1` once (BF040, the mole machine's engine noise). |

The **charge sound** is started by the game, not by a script: when a unit starts a charge, if it has no charge sound
running, a looping positional effect from packet 2 (`Battle2`) is started at the unit — effect **1** for Infantry and
Archers, for Cavalry **13** if the race is Human, Elven or Dwarven and **14** otherwise (Goblinoid, Orc, Skaven, …) — and stopped when the charge ends (halt,
contact, rout …). Other classes get none.

## 5. Corrections to `game_rules.md`

- "Unit behaviour scripts and events", event table row 0x35 and the sentence "event 0x35 is never handled by any
  script": **wrong**. Event 0x35 (53) is posted by the squig hoppers' walk animation through `PlayUnitAnimation 3 53 1`
  and handled by BF039 script 7 (`CaseEvent 53` → release/jump again). Both places now say so.

## 6. Open items 🟡

- Exact list of the "forced-run" states that make the rest action walk (charging is certain).
- Whether the power paid for a refused cast order is refunded (magic batch).
- `IfCasting`'s class test excludes non-Wizard casters; confirm in play with the Orc shaman on a Wyvern.
- (Settled in batch 9: the family with the walk-program event step is the Squig Hopper's.)
- `StartUnitLoopSound`'s third operand: fade behaviour of the copy.
