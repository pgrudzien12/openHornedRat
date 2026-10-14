# Spell sounds: which effect plays when, where, and when it stops

Public implementation report (research hand-off). Companion reports: `notes/sfx.md` (the `.SFX` packages, the
packet table, the effect records and the `LOOP` flag), `notes/spell_effects.md` §1.4 (how an effect ends or is
cancelled), `notes/spell_channelled_effects.md` §4 (Curse of Anraheir rules),
`notes/spell_attached_visuals.md` (Curse spirits), `notes/spell_area_effects.md`,
`notes/spell_obstacle_visuals.md`, `notes/spell_transport_visuals.md` and `notes/spell_area_particle_visuals.md`
(the phase timings that sounds below are tied to), `notes/battle_music.md` (pause and audio settings).

Not checked by listening to the original at runtime. Effect indexes are 0-based rows of the `spells` package
(packet slot 3, `notes/sfx.md` "Packet table"). Names are the effect names stored in `SPELLS.SFX`.

## 0. Shared rules

- **Every spell sound belongs to one active spell effect** (`spell_effects.md` §1). An effect can own several
  sounds at once. **When the effect ends or is cancelled, all of its sounds stop at once, in the same effect step**:
  natural end, Ctrl+click cancel, recast cancel, dispel, removal of a Wizard-class caster, removal of the target
  unit (the full list is `spell_effects.md` §1.4). No spell sound fades out or plays a tail after its effect is gone.
- **Sounds start only at the moment the game code says** (launch, or a named phase change below). Nothing
  restarts them later. In particular, **if sound effects are switched off when a sound would start, that sound is
  skipped for good**: switching effects on again later does not start the Curse loop of a curse that is already
  running.
- **Positional.** Every spell sound is placed at a battlefield point (x, y in battle coordinates). The listener is
  the battle camera: every frame the game passes the camera position and its view heading to the sound library.
  Volume and stereo position therefore depend on the distance and bearing from the camera. 🟡 The attenuation and
  pan law live inside the Mindscape sound library and were not investigated (the record fields `param_a/param_b`,
  2560 for most spell effects, are its likely inputs, `sfx.md`). 🟡 Which camera point is used (the eye or the
  look-at point) is not settled. The game asks for one of two placement modes per sound. Spell sounds marked
  "fading" below use the same mode as the charge sounds; the others use the plain mode. 🟡 What distinguishes the
  two modes is inside the library and not known.
- **Following.** Some sounds are moved every effect step to a moving point (a target unit's centre, a projectile's
  current position). The others stay where they started.
- **Pause** mutes all sound effects without stopping them; resuming (with effects enabled) unmutes them. A running
  loop therefore continues after a pause (`battle_music.md` describes the same pause control for music).
- **Many at once.** Each effect owns its own copies, so two effects of the same spell play two copies (two
  wizards' Curses = two independent loops). The original sets no per-spell limit. 🟡 The sound library has its own
  voice limit and priorities (`priority` 10 for every spell effect), not investigated.
- **The `spells` package is loaded** whenever any unit in the battle lists a spell or a magic item, or carries one of
  the special weapons that launch spell effects (Dragon breath, warpfire, steam gun and some others). This answers
  the load hypothesis in `sfx.md` for this package.
- **No other source.** Behaviour scripts and the animation programs (including the wizards' cast poses) play no
  sound from the `spells` package. A cast therefore has **no separate "casting" sound** before the launch; the
  first spell sound is the one started at the launch (the event step of the cast pose, `script_animation_sound.md`).

## 1. Curse of Anraheir (code 14) ✅

| Item | Value |
|---|---|
| Effect | index **15**, `SFX_Cast_Curse`: **LOOP**, volume 75, pitch 11025; sample 1.82 s, 8-bit mono 11025 Hz |
| Mode | fading |
| Start | at the **launch**, in the same step that halves the target's values and creates the spirits (appearance frames start at the same tick T, `spell_attached_visuals.md` §3). Only after a target was found: a failed Curse launch (no unit under the point) plays nothing |
| Place | the **target unit's centre** at the launch, then **moved to the target unit's current centre every effect step** (it follows the cursed regiment) |
| One-shot before it | none |
| Stops | whenever the Curse effect ends (§0): failed mounted panic test (same step as the failure), dispel, Ctrl+click on the spell, a new successful Curse by the same caster, removal of the target, removal of a Wizard-class caster |

Order inside a new Curse by the same caster: the target lookup comes first; if it succeeds, the old Curse is
cancelled (its loop stops) and then the new loop starts on the new target, **in the same tick**. If the new
cast fails for lack of a unit under the point, the old Curse and its loop continue.

The user's impression "it plays until the next curse is cast" is right for **unmounted** targets: their Curse has no
timer and no natural end (`spell_channelled_effects.md` §4.3), so the loop runs until the same wizard successfully
curses again (or one of the other ends above). Two **different** wizards' Curses coexist, with two loops.

### 1.1 Test vectors

`W`, `W2` = Wizard-class casters; `A`, `B` = units; T = launch tick of the first Curse. "Loop(A)" = a Curse loop
placed at `A`'s centre.

| Before | Action | After |
|---|---|---|
| no Curse; effects on | `W` curses `A` (target found) at T | Loop(A) starts at T; it is at A's centre |
| no Curse | `W` casts the Curse at an empty point | launch fails; no sound |
| Loop(A) running | `A` moves 40 units in a tick | the loop is at A's new centre in the same effect step |
| Loop(A); `A` mounted | segment 10 tick, `A` fails the panic test | the Curse ends; Loop(A) stops in that same step |
| Loop(A); `A` mounted | segment 10 tick, `A` passes | Loop(A) continues |
| Loop(A); `A` unmounted | any number of turns pass | Loop(A) continues (no timer) |
| Loop(A) from `W` | `W` curses `B` successfully at T2 | at T2: Loop(A) stops, Loop(B) starts |
| Loop(A) from `W` | `W` curses `A` again at T2 | at T2: old loop stops, a new Loop(A) starts from the start of the sample |
| Loop(A) from `W` | `W` casts the Curse at an empty point | cast fails; Loop(A) continues |
| Loop(A) from `W` | `W2` curses `B` | Loop(A) and Loop(B) both play |
| Loop(A) from `W` | `W2` curses `A` | two loops at A's centre, both play |
| Loop(A) | `A` is removed (destroyed, fled off the field, removed by a script) | Loop(A) stops |
| Loop(A) from Wizard-class `W` | `W` is removed | Loop(A) stops |
| Loop(A) from `W` | `W` routs, is broken or fights in melee | Loop(A) continues |
| Loop(A) | the Curse is dispelled | Loop(A) stops |
| Loop(A) from `W` | Ctrl+click on the Curse button for `W` | Loop(A) stops |
| Loop(A) | Pause / resume | muted during the pause; continues after resume |
| effects switched off | `W` curses `A`; effects switched on later | Curse runs silent to its end (no loop is started late) |

🟡 Not traced: whether the loop keeps sounding between the battle being decided and the player leaving the field.
On exit the game discards the battle's sound packages, which silences everything.

## 2. Other spells

"Caster" = the caster unit's centre at the launch; "aim point" = the clicked point at the launch; "target" = the
unit under the point. Sounds not marked LOOP are one-shot. All stop with their effect (§0).

| Spell (code) | Effect index, name | LOOP | Mode | Starts | Place |
|---|---|---|---|---|---|
| Wind Blast (1) | 3 `SFX_Cast_Wind1` | yes | fading | launch | caster, fixed |
| | 4 `SFX_Cast_Wind2` | yes | fading | **every trail deposit** (the trail begins at T+5; see below) | the gust head's point at that deposit, fixed |
| Azure Blades (2) | 13 `SFX_Cast_Spell` | yes | plain | launch | target, follows it every step |
| Storm of Shemtek (3) | — | | | silent | |
| Sapphire Arch (4) | 13 `SFX_Cast_Spell` | yes | plain | launch | aim point, fixed |
| Lightning (5) | 2 `SFX_Cast_Thunder` | no | plain | launch | caster |
| Piercing Bolts of Burning (6) | 0 `SFX_Cast_Fireball` | no | plain | launch | caster |
| The Burning Head (7) | 0 `SFX_Cast_Fireball` | no | plain | launch | caster |
| | 1 `SFX_Cast_Laugh` | no | plain | first flight step | the head, moved with it every flight step (only in the normal, non-Shift variant) |
| Conflagration of Doom (8) | 10 `SFX_Cast_Doom` | no | plain | when the fire reaches the ground (flash 108 and the camera shake, `spell_area_particle_visuals.md`) | the fire's point (the aim point) |
| Flamestorm (9) | 7 `SFX_Cast_Flamestorm` | yes | fading | launch | aim point, fixed |
| Fireball (10) | 0 `SFX_Cast_Fireball` | no | plain | launch | caster |
| Flying Bower (11) | 3 `SFX_Cast_Wind1` | yes | plain | launch (take-off) | caster's take-off point, fixed |
| | 4 `SFX_Cast_Wind2` | yes | fading | start of the flight leg | the flying projectile, moved with it every step |
| | | | | both stop at the landing (the caster is placed at the destination) | |
| Tangling Thorn (12) | — | | | silent | |
| Hunting Spear (13) | — | | | silent | |
| **Curse of Anraheir (14)** | 15 `SFX_Cast_Curse` | yes | fading | launch | target, follows it (§1) |
| Flock of Doom (15) | 6 `SFX_Cast_Flock` | yes | fading | launch | aim point, fixed |
| Dispel Magic (16) | — | | | silent | |
| Gaze of Mork (17) | 11 `SFX_Cast_GazeOfMork` | no | plain | launch | caster |
| Ere We Go (18) | 13 `SFX_Cast_Spell` | yes | plain | launch | target, follows it |
| Da Krunch (19) | 8 `SFX_Cast_DaKrunch` | no | plain | the foot stands (T+10, with the camera shake, `spell_area_effects.md`) | the foot's point |
| Fists of Gork (20) | — | | | silent | |
| Mork Save Uz (21) | 13 `SFX_Cast_Spell` | yes | plain | launch | target, follows it |
| Warp Lightning (22), also each Doomwheel bolt | 2 `SFX_Cast_Thunder` | no | plain | launch | caster |
| Skitterleap (23) | 9 `SFX_Cast_Skitterleap` | no | plain | launch | caster's departure point |
| Pestilent Breath (24), spell and behaviour breath | — | | | silent | |
| Madness (25) | 12 `SFX_Cast_Madness` | no | plain | launch | aim point |
| warpfire flame (26, innate) | 0 `SFX_Cast_Fireball` | no | plain | each flame's launch | the shooter |
| steam-gun shot (27, innate) | 14 `SFX_Cast_Steam` | yes | plain | launch | the shooter, fixed; stopped on the tick the cloud finishes (terminal impact or removal below ground), not at the end of the trail (`gyrocopter_steam_gun.md` §6.2) |

Items use their spell's row (Banner of Wrath = Lightning, Grudgebringer = Fireball). Dragon breath flames are
Fireball launches, so each flame plays `SFX_Cast_Fireball` at the shooter.

Notes:

- **Wind Blast trail loops.** Once the trail begins (T+5), each time the gust drops a trail sprite
  (`spell_obstacle_visuals.md` §2.2, up to 30), the game starts **another** `SFX_Cast_Wind2` loop at the gust
  head's point. All of them (plus the `Wind1` loop at the caster) run until the Wind Blast ends, which has no natural
  end (recast, Ctrl+click or dispel). 🟡 How many of them the library actually mixes depends on its voice limit.
- **Long one-shots outlive short flights.** A one-shot is not cut when its own phase ends, only when the whole effect
  ends; e.g. `SFX_Cast_Thunder` (5.26 s) is cut when the Lightning effect ends (after its flash tail).
  🟡 Whether the library cuts a playing one-shot on stop was not checked in the library itself; the game does ask
  for a stop at the effect's end.
- 🟡 **Burning Head laugh**: the game re-places the laugh at the head on every flight step. Whether a repeated
  placement of a finished one-shot restarts it is library behaviour, not checked.
- Effect 5 `SFX_FanFare` is not used by any spell.

## 3. For the engine

- Treat each sound as owned by its effect, with a list of handles per effect; stop them all in the effect's end
  routine, whatever caused the end.
- Start a sound only at its trigger; do not "resume" a missed start later.
- For the Curse: on launch emit `loop_start` (slot 3, effect 15, at the target's centre), on every effect step
  `loop_move` to the target's centre, and `loop_stop` in the Curse's end step (all six end causes).
- Keep the cancel-then-start order of a same-caster recast within one tick.

## 4. Open items 🟡

- Distance attenuation and pan law; meaning of the two placement modes and of `param_a/param_b` (library internals).
- Which camera point is the listener.
- The library's voice limit (matters for many Wind Blast trail loops).
- Battle decided → exit: whether loops keep sounding until the battlefield closes.
- Runtime listening comparison with the original.
