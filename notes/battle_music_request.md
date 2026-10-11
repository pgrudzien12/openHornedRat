# Research request: battle music playback

BF010 was silent during the latest playtest. The user recalls battle music previously. Current BattleView has
no music start/stop lifecycle. Searches of tracked battle-view history found no prior MIDI playback hook;
this does not establish what the user heard. GlueView handles PlayMusic/StopMusic with pygame.mixer.music,
so a preceding campaign track carrying over is a possible explanation, not a confirmed finding.

Please pass this request to `$researcher` in a separate Codex conversation and return a public
`notes/battle_music_playback.md` report. Follow the clean-room report boundary; describe named states and
observable behavior, cite existing reports rather than re-derive facts, and mark uncertainties.

## Established public facts and engine state

- `notes/music.md` documents BATTLE.MID, installed MIDI loading, and campaign track selection, but does not
  establish battle track selection or start timing.
- `notes/battle_end_objectives.md` specifies music stopping in the battle-end sequence; objective U does not
  stop music.
- BattleScene/Battle expose deployment/battle phase, paused state, battle results and scene transitions.
  BattleView currently owns sound effects but no music lifecycle.
- GlueView owns a `music_name` and drains PlayMusic/StopMusic effects. Playback loads an installed MIDI,
  applies the shared music-volume setting, and loops. Native debrief and credits views start their own tunes.

## Questions

1. Which track plays? Is selection fixed or dependent on mission, army, first contact or current combat?
2. Does it start on scene entry, deployment, or the start-battle action? Does it replace prior campaign music?
3. Does it loop? Does pausing or returning from a menu suspend, resume or restart it?
4. When exactly does it stop for victory, defeat, retreat, objective U, exit and re-entry?
5. What happens with music disabled or a missing/unplayable track? What playback state must the scene retain?

## Requested test vectors

| Before | Action | After to establish |
|---|---|---|
| Campaign music playing | Enter BF010 deployment | Selected track and replacement timing |
| Silent deployment | Start battle | Track, loop and volume behavior |
| Battle music playing | First melee; later no melee | Track changes or continuity |
| Battle playing / paused | Pause / resume | Playback continuity |
| Battle playing | A / Z / U or retreat | Stop timing and exceptions |
| Battle / result scene | Exit and re-enter | Playback ownership and restart |
| Music disabled or track unavailable | Enter / start battle | Fallback behavior |
