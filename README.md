# Open Horned Rat

**Open Horned Rat** is an open-source engine that runs *Warhammer: Shadow of the Horned Rat* (Mindscape, 1995) on modern systems, Linux included, without emulation and without the original program's crashes and sound problems.


**What it is not:** it is not a game, and it is not a standalone or replacement copy of one. It contains no original game content, and it does nothing without your own legally owned copy of the original, from which it reads every asset at runtime. It is also not the original executable, and it does not run that executable.

> **Early playtest builds are available, but there is no stable release yet.** The installers have passed automated builds but have not been tested on players' machines. The first stable packaged release is targeted for **the end of October 2026**.

## Join the discussion

Questions, playtest reports, or just want to talk about the game? Join the community in [GitHub Discussions](https://github.com/pgrudzien12/openHornedRat/discussions).

Please [open an issue](https://github.com/pgrudzien12/openHornedRat/issues) for a reproducible problem. Screenshots and short screen recordings are welcome, but do not upload or distribute original game assets. If you would like to help with code, research, documentation, or compatibility testing, start with an issue or a [Discussion](https://github.com/pgrudzien12/openHornedRat/discussions) so we can coordinate work.

## Help us test

Campaign games take hours, so early feedback is incredibly valuable. Please try the build if you own the original game and tell us:

- whether it starts on your system and which version of the original game you used;
- where the campaign flow, controls, visuals, audio, or battle rules feel wrong;
- what happened immediately before a crash, freeze, or broken screen; and
- the battle log from `logs/` if one was created.

Please [open an issue](https://github.com/pgrudzien12/openHornedRat/issues) for a problem you found, we apprechiate it!

## What you can play today

With your own copy of the game, you can watch or skip the opening movies, start a campaign, use the caravan and mission screens, and enter battles. You can deploy regiments and give movement, attack, and firing orders. Battles produce results and return to the campaign flow. A campaign can currently reach Nuln, about halfway through the game. This is still a development prototype: expect some rough edges in battles and later campaign missions, and a full campaign has not been played through to the end.

| Area | What to expect |
|---|---|
| ✅ Original game data | Reads assets from your own installation; no game data is included here. |
| ✅ Opening and menu | Prologue, intro movie, main menu, and mission briefings. |
| ✅ Campaign screens | Caravan, army records, troop selection, reinforcements, and mission selection are in place; minor bugs may remain. |
| ✅ Saving and loading | Manual save slots and a loadable automatic slot work during a playthrough. Saves use the engine's own directory (never your game installation), are incompatible with the original game's saves, and may not work across engine versions. |
| 🟡 Battles | Deployment, movement, charges, ranged attacks, morale and routing, magic, enemy AI, and victory or defeat results are in place. Most battle rules have been recreated with substantial effort to match the original experience; mission scripts also drive battles, though rough edges remain. |
| 🟡 Campaign progress | You can reach Nuln, about halfway through the campaign; the remainder has not been verified. |
| ✅ Audio and presentation | Opening movies, speech, music, and effects are mostly done. The Options screen saves separate volume levels for music, dialogue, and effects; minor gaps may remain. |
| 🟡 Packaged downloads | Windows, Debian, RPM, AppImage, and Apple Silicon macOS installers are built and available as prereleases. Installation and play have not yet been tested on players' machines; there is no stable release. |

## Install a playtest package

Download the most recent package for your system from [GitHub Releases](https://github.com/pgrudzien12/openHornedRat/releases). Windows, Debian, RPM, and AppImage packages appear in **daily** prereleases; the Apple Silicon macOS package appears in **weekly** prereleases. A prerelease contains the formats rebuilt that day, so you may need to look at an earlier one for your system. These packages are unsigned and have not yet had a full installation and play test. You also need your own legally owned game files. When the launcher first opens, select the original game's `WARFB` directory if it is not found automatically.

### Windows (64-bit)

Download `ohr-engine-setup-*.exe` and run it. Follow the installer prompts; it installs for your user account. Later, open **Open Horned Rat** from the Start menu, or use the desktop shortcut if you selected that option during installation.

### Debian or Ubuntu (64-bit)

Download the `ohr-engine_*_amd64.deb` file. From the directory containing the download, run:

```sh
sudo apt install ./ohr-engine_*_amd64.deb
```

Later, open **Open Horned Rat** from the application menu or run `ohr-engine` in a terminal.

### RPM-based Linux (64-bit)

Download the `ohr-engine-*.x86_64.rpm` file. From the directory containing the download, run:

```sh
sudo dnf install ./ohr-engine-*.x86_64.rpm
```

Later, open **Open Horned Rat** from the application menu or run `ohr-engine` in a terminal. The RPM is built on Rocky Linux 9 and targets compatible systems.

### AppImage (64-bit Linux)

Download the `ohr-engine-*-x86_64.AppImage` file. It needs no installation. Make it executable and run it from the directory containing the download:

```sh
chmod +x ./ohr-engine-*-x86_64.AppImage
./ohr-engine-*-x86_64.AppImage
```

Later, run the same AppImage file again. If your system cannot run AppImages through FUSE, use `APPIMAGE_EXTRACT_AND_RUN=1 ./ohr-engine-*-x86_64.AppImage`.

### macOS (Apple Silicon)

Download `ohr-engine-*-macos-arm64.pkg` from the weekly prerelease and open it with Installer. After installation, open **Open Horned Rat** from Applications. The package is unsigned and not notarized, so macOS may ask you to approve it before installation. An Intel Mac package is not available yet.

The launcher starts the bundled engine when you select **Start game**. On Windows and Linux, you can also run the engine directly from a terminal with `ohr-engine --engine /path/to/WARFB`; on macOS, `/usr/local/bin/ohr-engine /path/to/WARFB` is the engine command. Original game files, launcher settings, and saves are outside the package; uninstalling does not remove them.

## Run it from source

### You need

- Python 3 and a system capable of creating an OpenGL 3.3 window.
- A legal local copy of *Warhammer: Shadow of the Horned Rat*. The GOG v1.0 release is the version we actively test. The 1995 CD edition may work; the Steam/SNEG re-release has not yet been verified.
- A checkout of this repository.

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

The **Options** button opens audio levels for Music, Dialogue, and Sound Effects. Each cycles through Off, 25%,
50%, 75%, and 100%; OK saves the levels in the engine's save directory, and Cancel discards the edits.

### Battle controls

| Action | Control |
|---|---|
| Select a regiment | Left-click it |
| Move, attack, or fire | Select a player regiment, click the matching command button, then click a destination or target |
| Direct move or attack | With a player regiment selected, right-click the ground or an enemy regiment |
| Deselect | Escape |
| Pan camera | Arrow keys, WASD, or right-drag |
| Rotate camera | Q/E or middle-drag |
| Tilt camera | Page Up / Page Down |
| Zoom | Mouse wheel |
| Reset camera | Home |

Battle sessions create a JSON Lines log in `logs/` by default. Attach the relevant log to a bug report when possible; it helps us reproduce deterministic battle behaviour. You can begin directly in the first battle for a quick test with `--battle BF001`.

### Automated battle captures

`battle-auto` keeps one hidden battle open and accepts one JSON command per line on stdin. It returns
one JSON response per command on stdout. It uses the same battle scene and GPU view as the normal
engine and advances one 100 ms simulation update per requested tick. For example:

```sh
.venv/bin/python -m whshr battle-auto /path/to/WARFB --battle BF001
{"op":"state"}
{"op":"capture","path":"samples/bf001-start.png"}
{"op":"order","event":["start_battle"]}
{"op":"order","event":["select","Grudgebringer<Infantry"]}
{"op":"order","event":["attack","Clanrat_Warriors"]}
{"op":"step","ticks":20}
{"op":"capture","path":"samples/bf001-20.png"}
```

The `state` response lists each regiment's side, position, figures, ranks, and orders. `camera`
accepts `{"op":"camera","values":[225,45,120]}` (yaw, pitch, distance); `target` accepts
`{"op":"target","point":[500,500]}` in battlefield coordinates. Closing stdin ends the session.
Captures and battle logs contain derived game data and belong in ignored local directories.

For a repeatable example pilot, run `.venv/bin/python -m scripts.auto_play_battle --ticks 200`. It reads
the launcher-configured installation, orders active player regiments toward their nearest visible enemy,
and writes frames, a battle log, and final state under ignored `samples/auto-play/`.

Direct `--battle` entry reads the battle's own `loadmerc` `.MRC` file. It supplies the player
units in file order and their initial figures and ranks. A battle reached through a running campaign
instead receives the selected campaign marching army, preserving its current roster and marching order.
The `state.player_army` field identifies which source the automated session used.

## Original game required

This repository contains no original game files and never will. *Warhammer* and *Shadow of the Horned Rat* are trademarks of their respective owners. Open Horned Rat is a non-commercial fan project and is not affiliated with Games Workshop, Mindscape, GOG, or SNEG. See [LEGAL.md](LEGAL.md) for details.

You can buy a compatible copy from [GOG.com](https://www.gog.com/en/game/warhammer_shadow_of_the_horned_rat). We have not yet verified the [Steam/SNEG re-release](https://store.steampowered.com/app/4280870/Warhammer_Shadow_of_the_Horned_Rat_Classic/).

## License

The Open Horned Rat source code is licensed under the GNU General Public License, version 3 or later (`GPL-3.0-or-later`), the same license family used by OpenXcom. See [LICENSE](LICENSE). This license applies to this project's code, not to the original game's assets or trademarks.

## Project details

The format coverage, behavioural specifications, and longer-term technical roadmap are kept for contributors in [ROADMAP.md](ROADMAP.md), [FORMATS.md](FORMATS.md), and [`notes/`](notes/). They are intentionally separate from these player instructions. Contributors should also read the [research and implementation boundary](docs/research-boundary.md): implementation uses public behavioural reports and must not use executable-analysis material.
