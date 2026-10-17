---
name: Bug report
about: Report a problem with Open Horned Rat (launcher, campaign screens, battles, audio, packages)
title: "[Bug]: "
labels: bug
---

## What happened?

Describe the problem in a sentence or two.

## What did you expect?

What should have happened instead?

## How can we reproduce it?

List the steps, starting with how you started the game (launcher, desktop shortcut, or a command from a
source checkout). Mention the mission or battle if the problem happened in one.

1.
2.
3.

## Your setup

- Operating system and version:
- How you installed Open Horned Rat (Windows installer, .deb, .rpm, AppImage, macOS package, source checkout):
- Open Horned Rat version or package file name (for a source checkout, the commit and `python3 --version`):
- Original game edition (GOG v1.0, CD-ROM, Steam/SNEG, other):
- How you got the game files (installed normally, Wine/Proton, launcher's **Unpack...**, innoextract):
- GPU / graphics driver, if the problem is visual:

## Logs and evidence

Attach the logs from the session where it happened: the newest `battle-*.jsonl` for a battle problem, and
the `campaign-*.jsonl` from the same run. If GitHub refuses a `.jsonl` file, zip it first.

| How you run it | Logs folder |
|---|---|
| Windows package | `%APPDATA%\ohr\logs` |
| Linux package | `~/.local/share/ohr/logs` |
| macOS package | `~/Library/Application Support/ohr/logs` |
| Source checkout | `logs/` in the checkout |

For a crash, paste any error text a window or terminal showed. Screenshots or a short recording are welcome.

Please do **not** attach original game files or anything extracted from them.
