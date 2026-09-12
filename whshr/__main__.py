"""Unified command-line interface for the reverse-engineering tools."""

import argparse
import json
import sys
from pathlib import Path

from . import legacy
from . import audio, battle3d, campaign, pbx, si
from .paths import Installation


def _check(name, callback):
    try:
        result = callback()
    except Exception as error:  # A combined regression report must continue after one failed domain.
        print(f"ERROR {name}: {type(error).__name__}: {error}")
        return False
    if result is False:
        print(f"ERROR {name}: reported failures")
        return False
    print(f"OK    {name}")
    return True


def check(installation):
    """Run all established structural checks against an installation."""
    game = Installation(installation)
    checks = (
        ("scripts", lambda: legacy.module("whscript").check_dir(game.file_dir("SCRIPT"))),
        ("PBX/RNC", lambda: pbx.main(["--check", str(game.root)])),
        ("terrain", lambda: legacy.module("gd_render").check(game.file_dir())),
        ("sound effects", lambda: audio.sfx_main([str(game.root), "--check"])),
        ("WAV", lambda: audio.wavstats_main([str(game.root)])),
        ("fonts", lambda: legacy.module("fon_parse").check(game.binary_dirs())),
        ("cutscene containers", lambda: si.cmd_check(str(game.remote_dir("BINARY", "ANIM")))),
        ("cutscene side files", lambda: legacy.module("scene_dump").check_all(str(game.root))),
        ("MIDI", lambda: audio.midi_main(["--check", str(game.binary_dir("MUSIC"))])),
        ("SoundFont", lambda: audio.parse_sf2(
            game.binary_file("SOUND", "WARINTR3.SBK")
        )),
        ("campaign flow", lambda: bool(campaign.build_campaign_graph(str(game.root)))),
    )
    failed = sum(not _check(name, callback) for name, callback in checks)
    print(f"\n{len(checks) - failed}/{len(checks)} check groups passed")
    return failed == 0


def extract(installation, cache):
    """Run the established extractors into one cache directory."""
    game = Installation(installation)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)

    legacy.module("pe_extract").extract_all(str(game.root), str(cache / "pe_resources"))
    pbx.main([str(game.root), str(cache / "pbx")])
    si.cmd_extract(str(game.remote_dir("BINARY", "ANIM")), str(cache / "si"))
    legacy.module("anim_export").main([str(game.root), f"--out={cache / 'animations'}"])
    audio.sfx_main([str(game.root), "--json", str(cache / "sfx" / "sfx.json")])
    audio.extract_sfx_effects(str(game.root), str(cache / "sfx"))
    audio.extract_speech(str(game.root), str(cache / "speech"))

    camp_data = campaign.build_campaign_graph(str(game.root))
    camp_dir = cache / "campaign"
    camp_dir.mkdir(parents=True, exist_ok=True)
    with open(camp_dir / "campaign.json", "w", encoding="utf-8") as f:
        json.dump(camp_data, f, indent=2)
    with open(camp_dir / "campaign.dot", "w", encoding="utf-8") as f:
        f.write(campaign.export_graph_dot(camp_data))
    with open(camp_dir / "campaign.md", "w", encoding="utf-8") as f:
        f.write(campaign.export_campaign_markdown(camp_data))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="whshr",
        description="Tools for a locally installed copy of Warhammer: Shadow of the Horned Rat.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check_parser = commands.add_parser("check", help="run all structural regression checks")
    check_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    extract_parser = commands.add_parser("extract", help="extract decoded assets to a local cache")
    extract_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    extract_parser.add_argument("cache", type=Path, help="output directory; do not commit game assets")
    viewer_parser = commands.add_parser("viewer", help="render a static 3D battle scene to PNG")
    viewer_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    viewer_parser.add_argument("battle", help="BTS filename or path")
    viewer_parser.add_argument("output", type=Path, help="output PNG; do not commit game assets")
    viewer_parser.add_argument("--width", type=int, default=1280)
    viewer_parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args(argv)

    if args.command == "check":
        return 0 if check(args.installation) else 1
    if args.command == "viewer":
        result = battle3d.render(args.installation, args.battle, args.output, args.width, args.height)
        print(f"{result['output']}: {result['battle']}; scenery {result['scenery']} "
              f"({len(result['missing_scenery'])} unresolved), units {result['drawn_units']}/{result['units']}")
        if result["missing_scenery"]:
            print("Unresolved scenery: " + ", ".join(result["missing_scenery"]))
        return 0
    extract(args.installation, args.cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
