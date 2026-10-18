# Artillery: what happens to the crew and its scripts when the machine is lost

Public implementation report (behaviour only), answering the implementer's playtest request (BF004_5, the player's
1st Mortar Crew: after a destroying misfire the crew routed, dragged the mortar along and printed `GMTXT 2015` every
tick). Marks: ✅ established, 🟡 inferred or not observed on screen.

Companions, cited and not repeated here:

- `game_rules.md` "Artillery misfire", "Death kinds"; `ranged_combat_handoff.md` §4 (anchor, firing eligibility);
- `panic_tests.md` §0 (the Leadership test, effective Ld), §1 (casualty test), §3 (event 0x0C and its handlers);
- `casualty_bookkeeping.md` (no kill credit for the misfire); `machine_figure_animation.md` (the wreck frame);
- `script_queries.md` B2/B3 (`SetClass`, `IfMachineDestroyed`); `script_shooting.md` (`ReadyToFire`, "manned");
- `unit_script_control.md` (event entry at the start of a tick, LIFO queue, nested handlers, `ConsumeEvent`,
  `Restart` empties the queue); `player_missile_orders.md` (the **keep-firing** state, script 100's idle loop);
- `battle_tick_order.md` §2.2 (script step before model update inside one unit's step).

**Corrections made in other reports** (also edited there):

- `game_rules.md` "Artillery misfire" and `ranged_combat_handoff.md` §4/§6 said a crew model is wounded on an
  **even** draw: it is wounded on an **odd** draw (`rand` odd). They also said a failed Leadership test after the
  explosion "routs" the crew. It only queues event 0x0C, which the artillery handlers ignore at that moment (§2), so
  in the shipped game **the explosion's own test never routs the crew**.

## 0. Shared state (read this first)

| State | Meaning | Changes |
|---|---|---|
| **machine figure** | the war machine is the unit's **leader model**, and it is the **first model of the roster** (the model list in formation order) from battle load until it leaves the roster | leaves the roster when its death sequence starts |
| **"machine destroyed"** (`IfMachineDestroyed`) | the leader model has taken wounds ≥ its W, or there is no leader | true from the lethal wound on |
| **"machine gone"** (`ReadyToFire`'s artillery test) | there is **no leader model any more**, i.e. the machine figure has **left the roster** | false during the collapse delay, true from the start of its death sequence |
| **class** | Artillery (32) until the "leader killed" event 0x17 is handled, then Infantry (8) (`script_queries.md` B2) | only by the 0x17 handler |
| **effective Ld** of the crew | `panic_tests.md` §0: the leader's Ld if it is not 0, otherwise the first model's Ld. **Every war machine in the shipped files has Ld 0**, and the machine is both the leader and the first model, so **every Leadership test of a crew fails while the machine is still in the roster** (its result is then ignored, §2). Once the machine has left, the first model is a crew model (Ld 7 for the Empire mortar crew) | — |
| **keep-firing** | `player_missile_orders.md`: set by fire loops 107/108/109, cleared only by halt-and-re-form | not touched by the machine's loss |

**Two rules decide everything below:**

1. While the crew is still of class Artillery, its handlers ignore event 0x0C (`panic_tests.md` §3). That covers
   library 154, which the player artillery handler 102 also calls.
2. Event 0x17 ("leader killed") is queued **when the machine figure leaves the roster**, right after that removal's
   own casualty test. Its handler makes the crew Infantry, and in the **player** handler 102 it also ends with
   `Restart`. `Restart` abandons the handler and the main script and **discards every event still queued** for the
   unit (`unit_script_control.md`).

## 1. Q1 — the destroying misfire, step by step ✅

Inside the fire event's handler (tick T, script step; library 111 → `FireAtTarget`), after the reload stamp
(`ranged_combat_handoff.md` §4):

1. D6 = 6, then D6 = 1 (two draws).
2. **The machine figure is killed first**: its wounds taken are set to its W. No killer is recorded, so nobody gets
   the kill. Death kind 2 (missile / slain outright). It stays in the roster for now.
3. The war-machine **anchor** state is cleared.
4. **One draw per roster model, in roster order, machine first**: an **odd** draw gives that model one more wound.
   The machine is included: its draw has no visible effect (it is already dead; it keeps death kind 2 and no
   killer). A crew model that reaches its W this way is killed with death kind 2 and no killer. A model that has
   more W left just takes the wound.
5. If **any** roster model is still below its W (the machine never is), **one** Leadership test at modifier 0: one
   draw. It **always fails** (§0, Ld 0) and queues **0x0C** to the unit. With no survivor there is no test and no
   draw.
6. `GMTXT 2018` ("…misfired and been destroyed").
7. No projectile. `FireAtTarget` counts this as success (`script_shooting.md` §1).

Draws in this order: `2 + size + (1 if a model survived)`, where `size` counts the machine. Example: a full mortar
crew (machine + 3) uses 2 + 4 + 1 = 7 draws.

After the step (same tick T, model update): the machine and every killed crew model start their 1-tick collapse
delay (kind 2). **At T + 1** (model update) their death sequences start, in roster order (machine first). Each
**leaves the roster**: strength drops and the formation re-forms. The machine shows its **wreck frame where it
stands, with its facing frozen**, and never moves again (`machine_figure_animation.md` rows 6 and 10). It is a free
figure now, **not part of the unit**, so a crew that later moves or flees leaves it behind.

**Each removal runs the ordinary casualty test** (`panic_tests.md` §1), the machine's included:

- the machine's removal tests **before** the leader is cleared, so a test that runs there uses Ld 0 and **always
  fails**. It runs only if the unit was **below full organisational strength** (a removal from exactly `orgsize`
  never tests). Mortar, cannon and similar crews have `orgsize` 4, so q = 1 and every later removal crosses a
  boundary;
- then the leader is cleared and **0x17 is queued** (after that test's 0x0C, so it lies **above** it in the LIFO
  queue);
- each crew removal after it tests with the crew's Ld (the first model is now a crew model). A failure queues 0x0C
  **above** the 0x17.

## 2. Q2 — does the crew rout? ✅

**The explosion's own Leadership test never routs anyone.** Its 0x0C is handled while the crew is still Artillery:

- in the player handler 102 (and every handler that loops `ConsumeEvent; LoopIfTrue`) it is handled **in the same
  tick T**: the handler's loop takes the newly queued event at once;
- in any case before T + 2, when 0x17 is handled.

So it reaches library 154's case 0x0C, which skips everything for class Artillery. **Flight is never started
directly by the misfire.** An engine that starts the flight itself diverges. Send 0x0C to the unit, as for a failed
panic test, and let the handler decide.

At **T + 2** (event entry, before any script word), the queue holds, newest first: crew-removal 0x0C(s) (if failed),
0x17, then the machine-removal 0x0C (only if the unit was below full strength):

| Handler | What happens |
|---|---|
| newest 0x0C (crew removals) | handled first, class still Artillery → **ignored** |
| 0x17, **player crew** (102) | anchor cleared, class Infantry, the event handler becomes the infantry handler 101, re-form (unless broken), **`Restart`**: the main script restarts at its restart point (script 100's idle loop) and **the rest of the queue is discarded**, including the machine-removal 0x0C → **no rout** |
| 0x17, **AI crew** (154) | anchor cleared, class Infantry, re-form (unless broken); **no restart**; the handler goes on |
| older 0x0C, AI crew | class is now Infantry → `RoutAllowed` → rout reaction (`React 4`) → flight script **157** (`FleeFromTarget`, else `FleeBackward`) |

Net result:

| Crew | Unit at full strength when the misfire happens | Unit below full strength |
|---|---|---|
| player (handler 102) | no rout | no rout |
| AI (handler 154) | no rout | **rout**: the machine-removal test always fails |

After the conversion the crew is an ordinary Infantry regiment with the infantry handler, so any **later** failed
test (a later casualty, a failed break test in melee, fear) routs it normally. 🟡 An AI unit whose mission handler
routes 0x17 elsewhere than 154 was not checked; the shipped library path is the one above.

## 3. Q3 — the 108 / 124 loop after the machine is gone ✅

`TestUnitFlags2 4` in 108 tests the **keep-firing** state (`player_missile_orders.md`), which the machine's loss
does not clear. What ends the loop for a player crew is the **`Restart` of the 0x17 handler at T + 2**. The original
**never prints 2015** in this sequence, for three reasons:

1. `ReadyToFire` tests the **reload first** (`script_shooting.md` §0, with the order confirmed here: held → not
   reloaded → artillery tests). The misfire's volley stamped the reload, so for at least the reload time (126–198
   ticks for a mortar crew) `ReadyToFire 0` returns false **silently** (operand 0: no 2003).
2. "Machine gone" is the **leader no longer existing**. That is false at T (the figure is only dying) and becomes true
   at T + 1's model update.
3. At T + 2 the 0x17 conversion runs at event entry, **before** any script word. The class is no longer Artillery, so
   the artillery test with its 2015/2016 messages no longer applies, and the player crew has left 108 anyway.

So between "machine gone" (model update of T + 1) and the next script step (T + 2), no `ReadyToFire` can run. 2015 is
printed only by an Artillery-class unit that has **no leader at all** while reloaded, for example a war machine
loaded without one. There is no message de-duplication anywhere: a unit that really stayed in that state would print
2015 on every pass.

**Engine consequence:** the ~4 400 messages come from three engine divergences. The machine figure must leave the
roster at T + 1, the 0x17 conversion must run (with `Restart` for player crews), and `ReadyToFire` must test the reload
before the machine.

## 4. Q4 — machine killed by melee or missiles, crew holding a fire order ✅

The same mechanism, without the explosion's draws and test:

| Phase | What happens |
|---|---|
| lethal wound (tick K) | machine "destroyed" (`IfMachineDestroyed` true) but still the leader and in the roster; the anchor stays until 0x17 is handled; **"manned" is still true**, so a reloaded crew may still pass `ReadyToFire` during the collapse delay 🟡 (not seen on screen) |
| collapse delay | 1 tick for missiles and shot (kind 2) and fire kinds; close combat: the staggered delay of `game_rules.md` "Death kinds" (18–72 ticks in melee) |
| removal (tick R) | wreck frame held in place; casualty test **only if the unit was below `orgsize`**, and then it **always fails** (Ld 0, §0); 0x17 queued above it |
| R + 1, event entry | 0x17 first: player → Infantry, handler 101, re-form unless broken, `Restart` (108 left, queue discarded, **no rout**); AI → Infantry, re-form, then the older 0x0C (if any) → rout via 157 |

The crew never prints 2015 here either (§3, reasons 2 and 3). A crew in close combat goes through the same handler.
Only its re-form is skipped while it is broken.

## 5. Test vectors ✅

Unit: Empire 1st Mortar Crew (`orgsize` 4: machine W3 Ld 0, first in the roster, + 3 crew W1 Ld 7), player-controlled,
in 108's loop with keep-firing set and a target, reload long (mortar I3). "r" = the shared random stream.

**V1 — full strength, misfire destroys the machine, one crew model killed.**

| Tick | Before | Action | After |
|---|---|---|---|
| T | fire event 34 queued (from the shoot pose); 4 models | handler 102 → 154 → 111 → `FireAtTarget`; r: 6, 1, machine draw (any), crew A odd, crew B even, crew C even, Ld draw (any) | machine wounds = 3, kind 2, no killer; anchor cleared; A killed (kind 2, no killer); Ld test fails → 0x0C; `GMTXT 2018`; no projectile |
| T | queue [0x0C] | 102 loop: `ConsumeEvent` (queue not empty) → `GetEvent` 0x0C → 154 case 0x0C | class Artillery → nothing; queue empty |
| T | 108 resumes | `GosubScript 124` → `ReadyToFire 0` | false (not reloaded), **no message**; keep-firing set → loop |
| T | model update | — | machine and A: dying, delay 1 |
| T + 1 | 108 | `ReadyToFire 0` | false, no message |
| T + 1 | model update | machine's death starts | off the roster, wreck frame held at its spot; 4 = `orgsize` → **no test**; leader cleared; 0x17 queued |
| T + 1 | model update | A's death starts | off the roster; 3 → 2 crosses q = 1: test at −1 with Ld 7 (one draw); say it fails → 0x0C queued above 0x17 |
| T + 2 | queue [0x0C, 0x17] (head first) | event entry | 0x0C: class Artillery → ignored. 0x17: Infantry, handler 101, re-form, `Restart` → script 100 idle loop. **No rout, no 2015**; 2 crew stand next to the wreck |

**V2 — same, but the crew had already lost a man (3 of 4), no crew killed by the explosion.**

| Tick | Before | Action | After |
|---|---|---|---|
| T | 3 models | misfire; r: 6, 1, machine draw, crew B even, crew C even, Ld draw | machine dead (kind 2); B, C unhurt; Ld test fails → 0x0C (ignored the same tick); `GMTXT 2018` |
| T + 1 | model update | machine's death starts | 3 → 2: test at −1 with **Ld 0** → **fails** (one draw) → 0x0C; then 0x17 above it |
| T + 2, player crew | queue [0x17, 0x0C] | event entry | 0x17 → Infantry, handler 101, re-form, `Restart` → **0x0C discarded, no rout** |
| T + 2, same unit under AI (154) | queue [0x17, 0x0C] | event entry | 0x17 → Infantry, re-form; 0x0C → `RoutAllowed` (not broken, no `CantBreak`) → `React 4` → script 157: **the two crew flee; the wreck stays** |

**V3 — no survivor.**

| Before | Action | After |
|---|---|---|
| machine + 1 crew W1 | misfire; r: 6, 1, machine draw, crew odd | both killed; **no Leadership test, no draw for it**; `GMTXT 2018`; T + 1 both leave the roster (machine first: 2 → 1, test, fails, 0x0C, then 0x17; crew: 1 → 0, test, then the unit is removed, `unit_removal_broadcast.md`); the queued events are discarded with the unit |

**V4 — `ReadyToFire 0` on an Artillery-class unit (operand 0).**

| Before | After |
|---|---|
| machine dead but still in the roster (collapse delay), 3 models, reloaded | **true** (manned: the leader still exists) |
| machine dead, reload not elapsed | false, **no message** (the reload is tested first) |
| machine off the roster, class still Artillery, reloaded (only possible before 0x17 is handled, i.e. not at a script step in shipped flows) | false, **2015** |
| machine present, 1 model left (the machine alone), reloaded | false, **2016** |
| after the 0x17 conversion (class Infantry), reloaded | true (no artillery tests; 🟡 what the converted crew's volley then does with no missile weapon was not researched; a player crew has left 108 by then) |

**V5 — misfire, second die 2–6** (for completeness): two draws, `GMTXT 2019`, no wound draws, no test, the machine
stays anchored and alive (unchanged from `ranged_combat_handoff.md`).

## 6. Open items

- 🟡 What an **AI** crew still inside a fire loop does after its conversion to Infantry, if it does not rout (§5 V4,
  last row).
- 🟡 Whether a crew can still launch during the machine's collapse delay (§4, first row). The rules allow it; it has
  not been seen on screen.
