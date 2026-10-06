# Ranged combat engine choices

The behavioural source is `notes/ranged_combat_handoff.md`. The rules here are replaceable choices where that handoff leaves rendering or geometry open. They are not claims of original-game confirmation.

- Unit vertical extent is 24 battlefield units. An Archers-class code 17 Gyrocopter starts airborne at a base of 72 units; its state can be changed by the engine. A bomb falls from that height. Target aim uses the current unit centre at release.
- Flight uses the handoff's fixed tick counts and a symmetric triangular rise and fall. Collision checks sweep each tick's horizontal segment through unit and solid scenery circles, then compare height. Terrain uses four equally spaced samples per tick. Placed furniture without an object footprint gets a radius of 12 units, or 24 for names indicating a tower, house or wall. A solid object containing the shooter does not block its own launch.
- The first free slot in the 32-entry ordinary pool receives a missile. When full, the posted event is consumed. Innate fire and warpfire use a separate 64-entry pool. Their nine-tick visual flight is an engine choice.
- The installed `SCENERY.PBX` meshes render flight and impact: `ARROWS1` for bows, `ARROWS2` for Ctrl bow, `ARROWS3` for crossbows, `SPEAR1..4` for artillery variants, `FLAMES1` for bombs, and `EX1..8` for impacts. Velocity sets orientation; effect frames advance once per battle tick. Physics never reads the mesh selection. These assignments and frame schedules can be changed independently.
- Installed `MISSILE.SFX` cues play only when the battle requests that packet and a named cue and WAV are available. Launch and impact playback use the nearest name match. No substitute sound is generated.
- A Warpfire Thrower death emits its fifth puff at tick 8 and the blast at tick 9. This is the handoff's explicit timing choice.

Current limits: placed scenery has collision and targeting but no owning model or health in the parsed battle representation, so it intercepts missiles without taking wounds. Building-class regiments do use building strength and their first model. Flight visuals use the named installed meshes, but the exact weapon-to-mesh choice and pitch are provisional. The Gyrocopter's initial airborne state is inferred from its class and weapon code; no grounded transition is yet driven by mission data.
