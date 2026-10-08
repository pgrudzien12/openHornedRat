# The "Reload!" callout (GitHub #147)

Public behavioural handoff. It answers when a ranged unit's leader calls "Reload!", with what text, speech and
portrait, and how this relates to message 2003. Read with `script_behaviours.md` §3.3 (`React N` table and audience
rule), `react_portrait.md` (portrait pop-up), `script_shooting.md` §1 and §5 (reload test, volley scripts, events
33–35). Static research from the shipped scripts and data; the original was not run.

## 1. Short answers

- "Reload!" is **`React 12`**: text **GMTXT 34110**, speech **HumBtl (packet 5) effect 8**, audience marker **P**
  (never for enemy-army units). Only the Human, Elven and Dwarven rows have it; every other race row is empty for
  code 12, so those units say nothing. Portrait expression 2.
- It is spoken **only by artillery** (class Artillery), **after each shot**: the shot event handler waits 10 ticks,
  then calls `React 12`, then re-forms the crew. Archers and other shooters **never** say "Reload!"; their volley
  only has the `React 10` "FIRE!" shout at its start.
- It is a script reaction, not a separate game call. No engine code says it, and the reload state itself never
  triggers it. It is unrelated to message 2003 (§4).
- No throttle beyond "once per shot". The usual rules apply: one portrait pop-up at a time, and a speech cue is not
  restarted while the same cue plays.

## 2. Exactly when

The shot events 34 (fire at the target) and 35 (fire at 90 % range) are handled by library scripts 111 and 112,
reached through the shooters' event handlers 154 (artillery) and 156 (archers) (`script_shooting.md` §5):

```
111/112:  fire one projectile (FireAtTarget / FireAt90PercentRange)
          if the event came from a model (not a scripted ground-point shot)
             and the unit is class Artillery
             and its machine is not destroyed:
                 wait 10 ticks (the unit's main script is suspended)
                 React 12                     ← "Reload!"
                 re-form to the script ranks
```

So, for an artillery piece:
1. the volley script shouts `React 10` ("FIRE!", text 34108, HumBtl 3) and plays the leader's shoot animation;
2. the animation's fire step posts event 34; the projectile is launched;
3. **10 ticks later** comes "Reload!" (text, speech, portrait pop-up);
4. the crew re-form.

Not said:
- by **Archers** (or any non-Artillery shooter): the handler's class test fails;
- when the **machine is destroyed**;
- for a scripted bombardment shot whose event has no model source (mission `FireAtNode` steps fire through event 33 →
  volley → animation, and that animation's event 34 does come from a model, so those shots **do** get "Reload!");
- when the unit becomes ready again: there is no "reloaded" callout of any kind.

The same scripts run for player, allied and enemy artillery. The **P** marker then hides it for **enemy-army**
units, wherever they are. Player and allied units always show it, whether or not they are on screen or selected
(`react_portrait.md` §2).

## 3. Text, speech, portrait

| Race row | Text | Speech | Marker |
|---|---|---|---|
| Human (0), Elven (1), Dwarven (2) | GMTXT 34110 | packet 5 (`HumBtl`), effect 8 | P |
| Goblinoid, Orc, Skaven, Peasant, big | none → nothing at all | — | — |

When shown: the text goes to the battle message window. The speech plays non-positionally (not restarted if already
playing). The leader portrait pops up with **expression 2** for 25 ticks, unless a pop-up is already showing
(`react_portrait.md` §3). An artillery unit's leader is the machine's crew leader; its portrait is the unit's
`leaderportrait`.

## 4. Relation to message 2003 and the fire orders

Message **2003** ("still reloading", GMTXT 2003) is a different thing. It is printed by the readiness test when a
**ground-point fire order** (event 33, library 110) finds the unit not yet reloaded. It is a plain battle message:
no speech, no portrait. The same branch then calls **`React 14`** (34112 "cannot", HumBtl effect 5, marker P), which
does speak and pop the portrait. The other player fire orders are silent about reloading:

| Order | Not reloaded | Reloaded |
|---|---|---|
| fire at a **unit** (event 31 → 108) | `React 13` (34111, the order acknowledgement) at once, then wait silently until reloaded, then fire | `React 13`, fire |
| fire at a **building** (event 30 → 107) | `React 13`, wait silently, fire | `React 13`, fire |
| fire at **ground** (event 33 → 110) | **message 2003** + `React 14`; no shot; the order is dropped | volley (`React 10` "FIRE!") |
| search (fire on itself, event 32) | `React 13`, loop silently | `React 13`, fire at the nearest enemy |

Artillery also prints 2015 (machine destroyed) or 2016 (fewer than 2 models) from the same readiness test, whatever
the order (`script_shooting.md` §1).

## 5. Test vectors

| Before | Event | After |
|---|---|---|
| player Empire cannon (Human row), loaded, target in arc and range | volley | `React 10`: 34108 + HumBtl 3; shoot animation; event 34 → cannonball |
| same | 10 ticks after event 34 | `React 12`: 34110 + HumBtl 8, portrait pop-up (expression 2); crew re-form |
| player Dwarf cannon (Dwarven row) | shot | same: 34110 + HumBtl 8 |
| enemy Empire-race artillery (enemy army) | shot | no text, no speech, no portrait (P), on or off screen |
| enemy Goblin rock lobber | shot | nothing (no entry) |
| player crossbows (Archers) | volley | `React 10` only; no "Reload!" |
| player cannon whose machine was destroyed | (no shot possible) | ground-fire order: message 2015 + `React 14` |
| player cannon fired 5 ticks ago, still reloading | player fire at ground | message 2003, `React 14` (34112 + HumBtl 5, portrait), no shot |
| same | player fire at a unit | `React 13`, then waits, fires when reloaded, then "Reload!" 10 ticks after that shot |
| two player cannons fire on the same tick | 10 ticks later | both texts; one portrait pop-up (the first); the second speech skipped if the same cue is still playing |

## 6. Uncertainties

- 🟡 Whether further events are dispatched to the artillery unit during the 10-tick wait inside its handler
  (`script_shooting.md` §5 notes the same open point).
