# openHornedRat

An open, fan-made engine for **Warhammer: Shadow of the Horned Rat** (Mindscape, 1995),
the first real-time strategy game set in the Warhammer Fantasy world.

We follow in the footsteps of projects such as [OpenMW](https://openmw.org) (Morrowind) and
[OpenRA](https://www.openra.net) (Command & Conquer). The goal is to make the original game
comfortably playable on modern systems, including Linux, without emulation, without Wine
and without the old engine's bugs, such as missing sound or random crashes.

## Project status

The project is at an early stage. For now we are **reverse-engineering the game's file
formats** rather than writing the engine itself. The scripts in `scripts/` can already read
almost all of the game's data: palettes, backgrounds and animated unit sprites, battle and
army scripts, UI bitmaps and texts, fonts, music and sound effects, the 3D battle terrain,
textures and scenery meshes, and the cutscene videos. What is still missing is the game logic
(mission scripts, combat rules, save games). Details:

- [`FORMATS.md`](FORMATS.md): description of the reverse-engineered and still unknown file formats;
- [`ROADMAP.md`](ROADMAP.md): plan of further work and milestones.

## Original game required

**This repository does not contain any files from the game and never will.**
The graphics, sound, maps and mission scripts are the property of their owners (Games Workshop
and others). Like OpenMW or OpenRA, the engine will load assets from **your own legally
purchased copy of the game**.

You can buy the game, for example, here:

- **GOG.com**: [Warhammer: Shadow of the Horned Rat](https://www.gog.com/en/game/warhammer_shadow_of_the_horned_rat),
  a DRM-free version. All work so far is based on this version (GOG v1.0).
- **Steam**: [Warhammer: Shadow of the Horned Rat (Classic)](https://store.steampowered.com/app/4280870/Warhammer_Shadow_of_the_Horned_Rat_Classic/),
  a 2026 re-release. We have not yet checked whether its files are identical to the GOG version.

The original 1995 CD-ROM release should also work, but it has not been tested.

## Using the tools

The individual scripts in `scripts/` remain available while they are migrated into the `whshr`
package. The package provides the common entry points:

```sh
python3 -m whshr check /path/to/WARFB
python3 -m whshr extract /path/to/WARFB extracted
python3 -m whshr viewer /path/to/WARFB BF001.BTS battle.png
python3 -m whshr viewer /path/to/WARFB BF001.BTS battle-debug.png --diagnostic
python3 -m whshr viewer /path/to/WARFB BF001.BTS camera.png --projection perspective --yaw 225 --pitch 32 --distance 160 --fov 50
python3 -m whshr viewer /path/to/WARFB BF001.BTS topdown.png --projection orthographic --yaw 180 --pitch 85
python3 -m whshr viewer-web /path/to/WARFB BF001.BTS
python3 -m whshr viewer-2d /path/to/WARFB BF001.BTS game-view.png --target-x 1100 --target-y 600
python3 -m whshr terrain-check /path/to/WARFB
```

Both commands take the `WARFB/` directory of the GOG installation. Extraction output, such as
sprites, maps, and the battle atlas, must remain local. The directories holding such output
(`samples/`, `battles/`, `extracted/`) are in
`.gitignore`. They contain data extracted from the game, so they must not be committed or
distributed. `viewer` writes a static, textured PNG from a battle's terrain, scenery, and initial
units; its output must also remain local. `--diagnostic` adds scenery-pivot and unit origin markers
and writes a JSON sidecar. `terrain-check` verifies that each `GRND.PBX` vertex height agrees with
`GRND.GD`. `--projection perspective` matches the game's camera model: a look-at eye positioned
from the selected ground target by yaw, pitch, and `--distance` (mesh units), framed by vertical
`--fov`. `--projection orthographic` is a diagnostic view, e.g. top-down (`--yaw 180 --pitch 85`,
north up) for comparison with plan maps. Both modes accept
`--yaw`, `--pitch`, `--target-x`, and `--target-y`; `--zoom` applies only to orthographic mode.
`--ambient` and `--light X Y Z` control lighting.
`--scenery-scale` is a temporary multiplier for calibrating scenery meshes independently.
`viewer-web` opens local projection, look-at camera, and lighting controls at
`http://127.0.0.1:8765/`; its field mini-map can set the ground target by clicking. It only
serves the local browser and renders from the local game installation.

`viewer-2d` is a separate top-down game-view pipeline: it samples the battle's `loadplanmap`
(`MAP*.FOL/.BOP`) in a 544×386 viewport by default, then composites directional unit sprites in
their `.BTS`/`.MRC` formations. Use `--target-x`, `--target-y`, and `--zoom` to select a view;
`--spacing` and `--direction-offset` support visual calibration. It does not use PBX terrain or
scenery and does not alter the independent `viewer`/`viewer-web` 3D asset viewer.

## License and rights

This is a hobby, non-commercial project, not affiliated with Games Workshop, Mindscape, GOG
or SNEG. Warhammer and Shadow of the Horned Rat are trademarks of their respective owners.
