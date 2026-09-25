# Legal notes

Open Horned Rat is a non-commercial fan project. This page explains what it is, what it contains, and what it does
not. It is not legal advice.

## No affiliation

This project is not affiliated with, endorsed by, or sponsored by Games Workshop, Mindscape or its successors, the
current rights holders of the original game, GOG, or SNEG. All product names are used only to identify the game the
software is compatible with.

*Warhammer*, *Warhammer Fantasy Battle*, *Shadow of the Horned Rat* and related names, marks and lore are the
property of their respective owners. This project does not use them as its own branding and does not reproduce the
setting's lore or text.

## No original content

This repository contains **no original game files or content**: no executables or libraries, sprites, textures, meshes,
maps, fonts, music, sound effects, speech, video, script or dialogue text. It never will.

Open Horned Rat is a program that reads the game data from **your own legally obtained copy** of the game, at run
time, from a directory you point it at. Without that copy it cannot show the game's content. It is not a means of
obtaining, copying or redistributing the original game.

Do not add original game content to this repository, to issues, to pull requests or to discussions. Bug reports may
include logs, error messages and short screenshots or recordings, but not extracted game files.

## What this repository does contain

- **Source code** written for this project, licensed under the GNU General Public License, version 3 or later
  (see [LICENSE](LICENSE)). The licence covers this project's code only, not the original game's content or
  trademarks.
- **Documentation** of the original game's file formats and of its observable behaviour: layouts, formulas, small data
  tables and worked examples ([FORMATS.md](FORMATS.md), [`notes/`](notes/)). Its purpose is interoperability with a
  legally owned copy of the game. It does not reproduce the game's code, art, audio, lore or dialogue text.
- **Tests** and tooling for verifying the above against an installation supplied by the user.

## How the project is developed

Open Horned Rat is an independent reimplementation of the game's behaviour. It is not a port, translation or
modification of the original program's code. It never executes the original program's code; it only reads the data
files (including data stored in the game's libraries) from your installation.

Development follows a documented boundary between research and implementation
([`docs/research-boundary.md`](docs/research-boundary.md)): implementation work is done from public behavioural
descriptions and documented file formats, and contributions must not include original code, disassembly, analysis-tool
output, memory addresses or internal names from the original program.

## Saves and user data

The engine never writes into your game installation. Its own saves and logs go to a separate directory of its own
(see [README.md](README.md)) and are not compatible with the original game's save files.

## Rights holders

If you are a rights holder and believe something in this repository should not be here, please open an issue or
contact the maintainer through the repository profile. The material in question will be reviewed and, where
appropriate, removed promptly.
