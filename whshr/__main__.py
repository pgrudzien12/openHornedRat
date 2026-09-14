"""Unified command-line interface for the reverse-engineering tools."""

import argparse
import json
import sys
from pathlib import Path

from . import legacy
from . import audio, battle2d, battle3d, behaviour, campaign, catalog, game, pbx, rules, si, viewer_web
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
        ("3D viewer orientation", battle3d.check_orientation),
        ("game rules tables and unit stats", lambda: rules.check(game.root)),
        ("behaviour scripts", lambda: behaviour.check(game.root)),
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
    catalog_parser = commands.add_parser("catalog", help="index lazy-loadable assets without extracting them")
    catalog_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    catalog_parser.add_argument("output", type=Path, help="metadata JSON output, normally under a user cache")
    game_parser = commands.add_parser("game", help="run the current campaign scene flow")
    game_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    game_parser.add_argument("--player", default="ffplay", help="Smacker player executable (default: ffplay)")
    game_parser.add_argument("--skip-intro", action="store_true", help="enter the main menu without playing A1.SI")
    engine_parser = commands.add_parser(
        "engine", help="run the real-time engine (needs the packages in requirements-engine.txt)"
    )
    engine_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    engine_parser.add_argument("--width", type=int, default=1280, help="window width (default: 1280)")
    engine_parser.add_argument("--height", type=int, default=800, help="window height (default: 800)")
    engine_parser.add_argument("--skip-intro", action="store_true", help="start in the main menu")
    engine_parser.add_argument("--battle", help="start directly in a battle, e.g. BF001 (development shortcut)")
    engine_parser.add_argument("--camera", type=float, nargs=3, metavar=("YAW", "PITCH", "DISTANCE"),
                               help="initial battle camera: degrees, degrees, mesh units")
    engine_parser.add_argument("--hidden", action="store_true", help="do not show the window (captures)")
    engine_parser.add_argument("--frames", type=int, help="quit after this many frames")
    engine_parser.add_argument("--screenshot", type=Path,
                               help="with --frames: save the last frame as PNG; do not commit game assets")
    engine_parser.add_argument("--frame-time", type=float,
                               help="fixed seconds per frame instead of wall-clock time (reproducible captures)")
    viewer_parser = commands.add_parser("viewer", help="render a static 3D battle scene to PNG")
    viewer_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    viewer_parser.add_argument("battle", help="BTS filename or path")
    viewer_parser.add_argument("output", type=Path, help="output PNG; do not commit game assets")
    viewer_parser.add_argument("--width", type=int, default=1280)
    viewer_parser.add_argument("--height", type=int, default=900)
    viewer_parser.add_argument("--diagnostic", action="store_true",
                               help="mark scenery pivots and unit origins; write a JSON sidecar")
    viewer_parser.add_argument("--yaw", type=float, default=battle3d.DEFAULT_YAW,
                               help="camera clockwise rotation in degrees (default: 45)")
    viewer_parser.add_argument("--pitch", type=float, default=battle3d.DEFAULT_PITCH,
                               help="camera elevation in degrees (default: 26.565)")
    viewer_parser.add_argument("--projection", choices=battle3d.PROJECTIONS, default="orthographic",
                               help="camera projection (default: orthographic)")
    viewer_parser.add_argument("--zoom", type=float, default=1.0,
                               help="orthographic zoom multiplier")
    viewer_parser.add_argument("--distance", type=float, default=battle3d.DEFAULT_DISTANCE,
                               help="eye-to-ground-target distance in mesh units (perspective only)")
    viewer_parser.add_argument("--fov", type=float, default=battle3d.DEFAULT_FOV,
                               help="vertical field of view in degrees (perspective only)")
    viewer_parser.add_argument("--scenery-scale", type=float, default=1.0,
                               help="temporary multiplier for scenery mesh dimensions")
    viewer_parser.add_argument("--target-x", type=float, help="camera target X in BTS world units")
    viewer_parser.add_argument("--target-y", type=float, help="camera target Y in BTS world units")
    viewer_parser.add_argument("--ambient", type=float, default=0.45, help="ambient light, from 0 to 1")
    viewer_parser.add_argument("--light", type=float, nargs=3, metavar=("X", "Y", "Z"),
                               default=battle3d.DEFAULT_LIGHT, help="directional light vector")
    viewer_2d_parser = commands.add_parser(
        "viewer-2d", help="render a static top-down 2D game-view battle viewport to PNG"
    )
    viewer_2d_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    viewer_2d_parser.add_argument("battle", help="BTS filename or path")
    viewer_2d_parser.add_argument("output", type=Path, help="output PNG; do not commit game assets")
    viewer_2d_parser.add_argument("--width", type=int, default=battle2d.DEFAULT_WIDTH,
                                  help="viewport width in pixels (default: 544)")
    viewer_2d_parser.add_argument("--height", type=int, default=battle2d.DEFAULT_HEIGHT,
                                  help="viewport height in pixels (default: 386)")
    viewer_2d_parser.add_argument("--target-x", type=float, help="viewport centre X in BTS world units")
    viewer_2d_parser.add_argument("--target-y", type=float, help="viewport centre Y in BTS world units")
    viewer_2d_parser.add_argument("--zoom", type=float, default=battle2d.DEFAULT_ZOOM,
                                  help="pixels per BTS world unit (default: 1)")
    viewer_2d_parser.add_argument("--spacing", type=float, default=battle2d.DEFAULT_SPACING,
                                  help="formation soldier spacing in BTS world units (default: 12, traced in GAMEF.DLL)")
    viewer_2d_parser.add_argument("--direction-offset", type=int, default=0,
                                  help="add a directional sprite-frame offset, in eighth-turns")
    terrain_parser = commands.add_parser("terrain-check", help="compare GRND.PBX mesh heights with GRND.GD")
    terrain_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    terrain_parser.add_argument("battle", nargs="?", help="optional MESH directory, e.g. BF001")
    rules_parser = commands.add_parser("rules", help="print GAMEF.DLL combat tables or decoded unit stats")
    rules_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    rules_parser.add_argument("script", nargs="?", help="optional BTS/MRC filename or path: decode its units")
    scripts_parser = commands.add_parser("scripts", help="summarise or disassemble SCRIPT/BFxxx.DLL behaviour scripts")
    scripts_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    scripts_parser.add_argument("dll", nargs="?", help="optional mission DLL filename or path, e.g. BF001.DLL")
    scripts_parser.add_argument("ids", nargs="*", help="optional script ids to disassemble (default: all)")
    scripts_parser.add_argument("--names", action="append", type=Path,
                                help="JSON opcode catalogue {\"<op>\": {\"name\": ...}}; may be repeated")
    web_parser = commands.add_parser("viewer-web", help="open local browser controls for the battle viewer")
    web_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    web_parser.add_argument("battle", help="BTS filename or path")
    web_parser.add_argument("--port", type=int, default=8765, help="localhost port (default: 8765)")
    web_2d_parser = commands.add_parser("viewer-2d-web", help="open local browser controls for the 2D game view")
    web_2d_parser.add_argument("installation", type=Path, help="WARFB installation directory")
    web_2d_parser.add_argument("battle", help="BTS filename or path")
    web_2d_parser.add_argument("--port", type=int, default=8765, help="localhost port (default: 8765)")
    args = parser.parse_args(argv)

    if args.command == "check":
        return 0 if check(args.installation) else 1
    if args.command == "catalog":
        result = catalog.write(args.installation, args.output)
        print(f"{args.output}: {len(result.records)} metadata records")
        return 0
    if args.command == "game":
        game.start(args.installation, args.player, args.skip_intro)
        return 0
    if args.command == "engine":
        if args.width <= 0 or args.height <= 0:
            parser.error("--width and --height must be greater than zero")
        if args.frames is not None and args.frames <= 0:
            parser.error("--frames must be greater than zero")
        if args.screenshot is not None and args.frames is None:
            parser.error("--screenshot needs --frames")
        if args.frame_time is not None and args.frame_time < 0:
            parser.error("--frame-time must not be negative")
        try:
            from .frontend import app
        except ModuleNotFoundError as error:
            if error.name not in ("pygame", "zengl"):
                raise
            print(f"The engine needs {error.name}. Install the frontend packages into a local virtual "
                  "environment and run the engine with it:\n"
                  "  python3 -m venv .venv && .venv/bin/pip install --only-binary=:all: -r requirements-engine.txt\n"
                  "  .venv/bin/python -m whshr engine <WARFB>", file=sys.stderr)
            return 2
        result = app.run(args.installation, (args.width, args.height), args.skip_intro, args.hidden,
                         args.frames, args.screenshot, args.frame_time, args.battle, args.camera)
        print(f"{result['frames']} frames, {result['ticks']} ticks, final scene {result['scene']}")
        return 0
    if args.command == "viewer":
        try:
            battle3d.validate_options(args.width, args.height, args.yaw, args.pitch, args.zoom, args.target_x,
                                      args.target_y, args.ambient, tuple(args.light), args.scenery_scale,
                                      args.projection, args.distance, args.fov)
        except ValueError as error:
            parser.error(str(error))
        result = battle3d.render(args.installation, args.battle, args.output, args.width, args.height,
                                 args.diagnostic, args.yaw, args.pitch, args.zoom, args.target_x, args.target_y,
                                 args.ambient, tuple(args.light), args.scenery_scale, args.projection,
                                 args.distance, args.fov)
        print(f"{result['output']}: {result['battle']}; scenery {result['scenery']} "
              f"({len(result['missing_scenery'])} unresolved), units {result['drawn_units']}/{result['units']}")
        if result["missing_scenery"]:
            print("Unresolved scenery: " + ", ".join(result["missing_scenery"]))
        return 0
    if args.command == "viewer-2d":
        if args.width <= 0 or args.height <= 0:
            parser.error("--width and --height must be greater than zero")
        if args.zoom <= 0:
            parser.error("--zoom must be greater than zero")
        if args.spacing <= 0:
            parser.error("--spacing must be greater than zero")
        result = battle2d.render(
            args.installation, args.battle, args.output, args.width, args.height,
            args.target_x, args.target_y, args.zoom, args.spacing, args.direction_offset,
        )
        print(f"{result['output']}: {result['battle']}; map {result['planmap']}, "
              f"units {result['drawn_units']}/{result['units']}, soldiers {result['soldiers']}")
        if result["missing_units"]:
            print("Unresolved units: " + ", ".join(result["missing_units"]))
        return 0
    if args.command == "terrain-check":
        results = battle3d.check_terrain(args.installation, args.battle)
        for result in results:
            print("{mesh}: {compared}/{vertices} vertices, RMSE {rmse:.6f}, max {max_error:.6f}, "
                  "outside GD {outside_gd}".format(**result))
        return 0 if results and all(result["max_error"] < 0.025 for result in results) else 1
    if args.command == "rules":
        return rules.main(args.installation, args.script)
    if args.command == "scripts":
        return behaviour.main(args.installation, args.dll, args.ids, args.names)
    if args.command == "viewer-web":
        viewer_web.serve(args.installation, args.battle, args.port)
        return 0
    if args.command == "viewer-2d-web":
        viewer_web.serve_2d(args.installation, args.battle, args.port)
        return 0
    extract(args.installation, args.cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
