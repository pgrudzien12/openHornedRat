# Open Horned Rat

**Open Horned Rat** is an open-source engine that runs *Warhammer: Shadow of the Horned Rat* (Mindscape, 1995) on modern systems, Linux included, without emulation and without the original program's crashes and sound problems.

**What it is not:** it is not a game, and it is not a standalone or replacement copy of one. It contains no original game content, and it does nothing without your own legally owned copy of the original, from which it reads every asset at runtime. It is also not the original executable, and it does not run that executable.

> **Early playtest build — source only.** It is useful for testing the opening campaign flow and some battles, and we especially need reports from people who can spend time with it. The first packaged playable release is targeted for **the end of October 2026**.

## Help us test

Campaign games take hours, so early feedback is incredibly valuable. Please try the build if you own the original game and tell us:

- whether it starts on your system and which version of the original game you used;
- where the campaign flow, controls, visuals, audio, or battle rules feel wrong;
- what happened immediately before a crash, freeze, or broken screen; and
- the battle log from `logs/` if one was created.

Once the repository is public, please [open an issue](../../issues) for a reproducible problem. Screenshots and short screen recordings are welcome, but do not upload or distribute original game assets. If you would like to help with code, research, documentation, or compatibility testing, start with an issue or Discussion so we can coordinate work.

## What you can play today

With your own copy of the game, a new campaign plays the prologue and intro, shows the main menu, and takes you through the campaign screens (the caravan, army records, troop selection, reinforcements, and mission selection) into a battle. In battle you deploy your regiments, then select them, move, charge, shoot, and finish with a victory or defeat result. This is a development prototype: the rules are simplified and a full campaign has not been played through to the end. The first battle is the most tested; expect rough edges in later ones.

| Area | Status | What to expect |
|---|---|---|
| Original game data | Works | Reads assets from your own installation; no game data is included here. |
| Opening and menu | Works | Prologue, intro movie, main menu, and mission briefings. |
| Campaign screens | In progress | Caravan, army records, troop selection, reinforcements, and mission select work; many screens and choices still need validation. |
| Saving and loading | In progress | Load/Save dialog and an automatic slot, written to the engine's own save directory (never your game installation). Saves are not compatible with the original game's, and may change between versions. |
| Battles | In progress | Deployment, movement, charges, ranged attacks, morale and routing, magic, and enemy AI. The first battle is the most tested; later ones are largely untested. |
| Battle rules and mission scripts | In progress | Rules follow the original's behaviour where it has been reverse-engineered, but some are still simplified, and mission scripting is not yet fully reproduced. |
| Complete campaign | Not verified | Nobody has yet played a full campaign start to finish. |
| Audio and presentation | In progress | Speech, effects, and cutscenes are used; expect gaps and rough edges. |
| Packaged downloads | Not available | Run from source for now. |

## Chat

Questions, playtest reports, or just want to talk about the game? Join us on [Discord](https://discord.gg/CPHBNFmwJ).

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

Or skip typing paths altogether with the standalone launcher, which finds the installation (or
lets you browse for it), remembers it, lists the available battles, and starts the engine for you:

```sh
python3 -m whshr.launcher
```

The launcher itself only needs the Python standard library (no `.venv` required to run it), but
still launches the engine through the `.venv` next to this checkout.

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

This repository contains no original game files and never will. *Warhammer* and *Shadow of the Horned Rat* are trademarks of their respective owners. Open Horned Rat is a non-commercial fan project and is not affiliated with Games Workshop, Mindscape, GOG, or SNEG. See [LEGAL.md](LEGAL.md) for details.

You can buy a compatible copy from [GOG.com](https://www.gog.com/en/game/warhammer_shadow_of_the_horned_rat). We have not yet verified the [Steam/SNEG re-release](https://store.steampowered.com/app/4280870/Warhammer_Shadow_of_the_Horned_Rat_Classic/).

## License

The Open Horned Rat source code is licensed under the GNU General Public License, version 3 or later (`GPL-3.0-or-later`), the same license family used by OpenXcom. See [LICENSE](LICENSE). This license applies to this project's code, not to the original game's assets or trademarks.

## Project details

The format coverage, behavioural specifications, and longer-term technical roadmap are kept for contributors in [ROADMAP.md](ROADMAP.md), [FORMATS.md](FORMATS.md), and [`notes/`](notes/). They are intentionally separate from these player instructions. Contributors should also read the [research and implementation boundary](docs/research-boundary.md): implementation uses public behavioural reports and must not use executable-analysis material.
