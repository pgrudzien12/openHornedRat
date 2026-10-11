# Battle music lifecycle

Behavioural handoff for the silent BF010 report. This covers the original PC game's
battlefield music, including deployment, ordinary pause/resume and battle exit.
It does not require a mission-specific music field or a combat-triggered soundtrack.

## 1. Findings and existing references

**The battlefield plays `BATTLE`, starting during entry to deployment.** It repeats
until paused, disabled or stopped on leaving. Pressing **Start battle**, entering
melee, leaving melee, or deciding the battle does not select or restart a tune.

Established facts to retain:

- [music.md](music.md): installed GM/FM arrangements, MIDI duration, instrument banks
  and rendering limitations. `BATTLE.MID` and `BATTLEFM.MID` both last approximately
  219.4 seconds through their last MIDI event.
- [battle_end_objectives.md](battle_end_objectives.md), §§3.3, 5.3, 6–7: deciding a
  battle leaves the simulation running; pressing the tent actually finishes it.
  Objective U exposes the tent without stopping the music.
- [troop_selection.md](troop_selection.md), §1.3, and
  [debrief_evaluation.md](debrief_evaluation.md), §4.4: `TACTICAL` belongs to troop
  selection; `WIN`/`LOSE` belong to the relevant debrief screens. These are separate
  from music on the battlefield.

The lifecycle below is supported by the available original-game evidence, but no
new audible original-runtime session was captured for this report. Exact audible
loop gaps and output-device behaviour remain qualified in §7.

## 2. Track choice, entry and repetition

### Track choice

The battlefield chooses the composition `BATTLE` for all missions and army
compositions. The user's music mode selects its arrangement:

| Music mode | Battlefield asset |
|---|---|
| General MIDI | `BINARY/MUSIC/BATTLE.MID` |
| FM MIDI | `BINARY/MUSIC/BATTLEFM.MID` |
| Off | No audible battlefield music |

There is no switch to `COMBAT` on first melee, no race-dependent selection, and no
switch back when combat ceases. The existing `COMBAT` references in campaign ambush
scenes do not establish a battlefield combat trigger.

### Entry and replacement

Entering a newly loaded battle stops and releases any preceding tune. Once the
battlefield is being opened, `BATTLE` is prepared and playback starts if music is
enabled and the asset can be opened. This happens **before the player presses Start
battle**, so deployment itself has music. The loading interval may be silent;
there is no crossfade or instruction to preserve the campaign track underneath it.

This replacement is part of battle entry even when the campaign script did not
explicitly stop its previous tune. A direct battlefield launch also starts
`BATTLE`. Failure to open battle music leaves silence, not the preceding campaign
track.

### Repetition and volume

Playback repeats indefinitely, returning to the beginning after the tune ends.
It is independent of simulation ticks: deployment can last several complete
repetitions without starting the battle clock. Starting the battle does not reset
either the tune or its repetition schedule.

The original checks for tune completion at nominal 2.5-second intervals. Therefore
"loops" does **not** establish sample-continuous, gapless playback: after the last
event, the next restart waits for a completion check, plus any scheduling delay.
The 219.4-second file duration is not an exact wall-clock repeat period.

There is no battle-specific fade-in, combat-volume change, speech ducking, or
end-of-battle fade in this lifecycle. Successful tune initialization while music is
enabled restores the common music default; initialization while music is disabled
does not change output volume. The offline FluidSynth gain in `music.md` is a
rendering choice, not a battle-specific volume rule. Exact loudness equivalence
across MIDI devices and the engine's renderer is not established here.

## 3. Named states and transitions

Keep these independent concepts:

- **Battle phase:** deployment, running, decided-but-still-open, or left.
- **Ordinary battle pause:** active or inactive.
- **Music preference:** off, GM, or FM.
- **Tune availability:** loaded or unavailable.
- **Playback:** playing, suspended at a position, or stopped/released.

| Action | Music effect |
|---|---|
| Enter a new battlefield | Stop/release the prior tune; prepare `BATTLE`; start from its beginning when available and enabled |
| Start battle from deployment | Continue the existing playback position |
| First melee; later no melee | Continue unchanged |
| Ordinary Pause button | Silence music and preserve its position; no automatic loop restart while paused |
| Resume, with the same enabled music mode | Continue from the suspended position, rather than from the beginning |
| Resume with music preference off | Stay silent |
| Switch music off during playback | Suspend the tune; retain it for a later enable |
| Enable music again in the same arrangement | Resume the retained tune; if it has never played, begin it |
| Change between GM and FM | Replace the arrangement and begin the replacement from its start; do not transfer the old timestamp |
| Objective A/F/N/H decides victory, or Z decides loss | Continue `BATTLE`; no victory/defeat music replacement |
| Objective U gives its retreat warning and exposes the tent | Continue `BATTLE` |
| Regiment routs or retreats while the battlefield remains open | Continue `BATTLE` |
| Press the tent to leave | Stop music before final objective evaluation and result bookkeeping; release it when the battlefield closes |
| Quit/close the battlefield without the normal final pass | Release its music as part of battlefield teardown |
| Load/open the same battle again | Start a fresh `BATTLE` playback, with no retained position from the old battle |

The pause/resume statements describe the ordinary battle control with otherwise
unchanged settings. They must not be generalized to every overlay that freezes
simulation. In particular, an options screen has its own audio preference changes;
exact combinations of options, focus loss and an already paused battle are not
fully specified here.

The post-battle campaign or debrief owns whatever plays next. Stopping the battle
tune does not itself choose `WIN`, `LOSE`, or restore a remembered campaign tune.

## 4. Disabled or missing music

Music-off is a valid silent state, independent of battlefield progression. It does
not defer a special music-start event until Start battle. Starting with music off
and later enabling it can play the prepared battle tune while still in deployment.

If the requested tune cannot be opened, the battle continues with no music. No
alternate composition, campaign-track continuation, or automatic opposite-arrangement
fallback is requested. Repeated battle ticks and Start battle do not retry loading
the missing tune. Re-entering a newly loaded battlefield performs a fresh load.

An engine audio backend being unavailable should likewise leave the battlefield
usable and silent. That is an implementation fallback recommendation; equivalent
behaviour for every original Windows MIDI device failure has not been verified.

## 5. Before/action/after vectors

Assume an available asset and enabled GM music unless a row says otherwise. These
are behavioural expectations for independently written tests, not runtime captures.

| Before | Action | After to establish |
|---|---|---|
| Campaign `SIGHTED` or `GENERIC` playing | Enter BF010 deployment | Prior tune released; `BATTLE` starts during battlefield entry |
| Silent direct launch | Enter BF010 deployment | `BATTLE` starts without a campaign music command |
| Deployment, `BATTLE` partway through | Press Start battle | Same tune and continuous position; no reload, volume change or restart |
| Deployment lasts longer than one tune | Wait without starting battle | `BATTLE` restarts after completion and continues repeating |
| Running battle, `BATTLE` playing | First melee begins; all melee later ends | Same tune and uninterrupted position throughout |
| Running, tune partway through | Pause; wait beyond the remaining tune duration | Silent, retained position, no loop advancement |
| Ordinary pause, music preference unchanged | Resume | Same tune resumes at its retained position |
| Running, music preference off | Pause and resume | Still silent |
| BF010 running | A or Z decides the outcome | `BATTLE` continues while the tent becomes available |
| U mission before its retreat warning | Warning exposes the tent | `BATTLE` continues; subsequent unit retreats do not replace it |
| Decided battle or U permits departure | Press tent | Music stops before final results; remains released after exit |
| Battle playing or suspended | Close it and reopen the same battle | Old playback released; enabled music starts afresh in new deployment |
| Music preference off | Enter deployment; press Start battle | Silent in both phases |
| Battle tune prepared while music off | Enable the same arrangement during deployment | Battle tune begins without Start battle |
| Battle tune playing in GM | Switch to FM, with both assets available | `BATTLEFM` begins from the start |
| Campaign music playing, required battle tune unavailable | Enter/start battle | Prior music stops; battle remains usable and silent; no substitute tune |
| One army/mission uses `BATTLE` | Enter a different mission with a different army | Same composition, subject only to music mode |

## 6. Changes to the implementer's model

The reported missing lifecycle in `BattleView` is sufficient to explain either
silence or a carried-over campaign track. The behavioural owner is the **active
battlefield's lifetime**, beginning in deployment, not the first running tick or
the first combat. `BattleScene` already exposes deployment/running phase, pause and
departure; its frontend can apply the resulting audio transitions to the shared
music player. This is an ownership recommendation, not a requirement to use a
particular class or representation.

Ensure one owner replaces the shared campaign playback when the battle opens and
releases battle playback when it closes. A visual refresh of the same battle is
not a new battle entry. A decided outcome or `can_leave` becoming true is also not
an exit. Playback position must survive ordinary pause/resume.

Corrections to public documentation:

- `music.md` formerly located `BATTLE` only as an unexplained asset reference;
  its battlefield/deployment role is now established.
- `FORMATS.md` formerly listed `battle` among unlocated tracks; that entry is
  corrected and this report linked.
- The existing statement that music stops when leaving the battle remains correct.
  It must not be read as stopping at the earlier win/loss decision.

## 7. Open items

- 🟡 No new audible original-runtime comparison: exact loop-gap length, instrument
  tails, and pause/resume behaviour at the precise end-of-tune boundary remain to
  be compared on a working MIDI device.
- 🟡 Exact combinations of options-screen preview/cancel, focus loss, and an
  already paused battlefield remain outside the ordinary pause/resume rule above.
- 🟡 Missing only one arrangement while changing modes, and recovery after an
  output-device failure, need runtime comparison. There is no established rule
  requiring a fallback track or automatic retry.
- 🟡 No device-independent numeric mixer gain is established by this report.

These do not block entry playback, continuous deployment-to-battle music,
ordinary pause/resume, or exit cleanup.
