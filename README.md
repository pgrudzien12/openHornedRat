# Open Horned Rat

**Open Horned Rat** is an early, reimplementation of *Warhammer: Shadow of the Horned Rat* (Mindscape, 1995). Our aim is to make the original campaign playable on modern systems—Linux included—without emulation or the original engine's crashes and sound problems.

> **Early playtest build — source only.** This is not yet a replacement for the original game. It is useful for testing the opening campaign flow and the first battle, and we especially need reports from people who can spend time with it. The first packaged playable release is targeted for **the end of October 2026**.

## Help us test

Campaign games take hours, so early feedback is incredibly valuable. Please try the build if you own the original game and tell us:

- whether it starts on your system and which version of the original game you used;
- where the campaign flow, controls, visuals, audio, or battle rules feel wrong;
- what happened immediately before a crash, freeze, or broken screen; and
- the battle log from `logs/` if one was created.

Once the repository is public, please [open an issue](../../issues) for a reproducible problem. Screenshots and short screen recordings are welcome, but do not upload or distribute original game assets. If you would like to help with code, research, documentation, or compatibility testing, start with an issue or Discussion so we can coordinate work.

## What you can play today

Start a new campaign and the build plays the opening prologue and intro, shows the main menu, and takes you through the early campaign screens into the first battle (`BF001`). In battle you can select regiments, move, charge, shoot, and finish with a victory or defeat result. It is a development prototype: saves, a complete campaign, faithful rules, and broad platform testing are still in progress.

| Area | Status | What to expect |
|---|---|---|
| Original game data | Works | Reads assets from your own installation; no game data is included here. |
| Opening and menu | Works | Prologue, intro movie, main menu, and first mission briefing are playable. |
| Campaign screens | In progress | The early campaign flow is implemented; many screens and choices still need validation. |
| First battle (`BF001`) | Playable | Movement, selection, charges, ranged attacks, basic morale/routing, enemy AI, and a result screen. |
| Battle rules and missions | In progress | Rules and AI are simplified; original mission behaviour is not yet fully reproduced. |
| Full campaign and saves | Not ready | Do not expect to complete or save a campaign yet. |
| Audio and presentation | In progress | Some original presentation is used; expect gaps and rough edges. |
| Packaged downloads | Not available | Run from source for now. |

## Run it from source

### You need

- Python 3 and a system capable of creating an OpenGL 3.3 window.
- A legal local copy of *Warhammer: Shadow of the Horned Rat*. The GOG v1.0 release is the version we actively test. The 1995 CD edition may work; the Steam/SNEG re-release has not yet been verified.
- A checkout of this repository. There is no release binary yet.

The project never ships original game files. Point the engine at the `WARFB` directory in your own installation.

### Install and start

From the repository root, create an isolated Python environment and install the small frontend dependency set:

```sh
python3 -m venv .venv
.venv/bin/pip install --only-binary=:all: -r requirements-engine.txt
```

Then run the engine, replacing `/path/to/WARFB` with your game's `WARFB` directory:

```sh
.venv/bin/python -m whshr engine /path/to/WARFB
```

Or use the convenience script after completing the install step:

```sh
./scripts/run_engine.sh /path/to/WARFB
```

If the game files are elsewhere, you can set `WARFB` instead:

```sh
export WARFB=/path/to/WARFB
.venv/bin/python -m whshr engine
```

The window opens with the prologue and intro. Any key or click skips the intro; choose **New Campaign** with `N` or Enter. Use Ctrl+Q or close the window to quit.

### Battle controls

| Action | Control |
|---|---|
| Select a regiment | Left-click it |
| Move selected regiment / charge an enemy | Left-click the ground / an enemy regiment |
| Move without a selection | Right-click the ground |
| Deselect | Escape |
| Pan camera | Arrow keys, WASD, or right-drag |
| Rotate camera | Q/E or middle-drag |
| Tilt camera | Page Up / Page Down |
| Zoom | Mouse wheel |
| Reset camera | Home |

Battle sessions create a JSON Lines log in `logs/` by default. Attach the relevant log to a bug report when possible; it helps us reproduce deterministic battle behaviour. You can begin directly in the first battle for a quick test with `--battle BF001`.

## Original game required

This repository contains no original game files and never will. *Warhammer* and *Shadow of the Horned Rat* are trademarks of their respective owners. Open Horned Rat is a non-commercial fan project and is not affiliated with Games Workshop, Mindscape, GOG, or SNEG.

You can buy a compatible copy from [GOG.com](https://www.gog.com/en/game/warhammer_shadow_of_the_horned_rat). We have not yet verified the [Steam/SNEG re-release](https://store.steampowered.com/app/4280870/Warhammer_Shadow_of_the_Horned_Rat_Classic/).

## License

The Open Horned Rat source code is licensed under the GNU General Public License, version 3 or later (`GPL-3.0-or-later`), the same license family used by OpenXcom. See [LICENSE](LICENSE). This license applies to this project's code, not to the original game's assets or trademarks.

## Project details

The format coverage, behavioural specifications, and longer-term technical roadmap are kept for contributors in [ROADMAP.md](ROADMAP.md), [FORMATS.md](FORMATS.md), and [`notes/`](notes/). They are intentionally separate from these player instructions. Contributors should also read the [research and implementation boundary](docs/research-boundary.md): implementation uses public behavioural reports and must not use executable-analysis material.
