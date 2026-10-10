"""Simple reproducible BF001 pilot using the public battle-auto JSON Lines protocol.

The pilot orders each available player regiment toward its nearest visible enemy
every 20 ticks. It is a testing aid, not an attempt to model human tactics.
Game-derived captures and logs must stay in ignored local directories.
"""

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

from whshr.launcher.config import load_config


def nearest_enemy(unit: dict, enemies: list[tuple[str, dict]]) -> str | None:
    available = [(name, enemy) for name, enemy in enemies
                 if enemy["models"] > 0 and not enemy["fled"] and not enemy["hidden"]]
    return min(available, key=lambda pair: math.hypot(unit["x"] - pair[1]["x"],
                                                       unit["y"] - pair[1]["y"]))[0] if available else None


def play(installation: str, battle: str, ticks: int, output: Path, seed: int) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen([sys.executable, "-m", "whshr", "battle-auto", installation,
                                "--battle", battle, "--seed", str(seed), "--battle-log", str(output)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def command(payload: dict) -> dict:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(f"battle-auto exited with code {process.poll()}")
        response = json.loads(line)
        if not response["ok"]:
            raise RuntimeError(response["error"])
        return response

    try:
        state = command({"op": "state"})["state"]
        print("roster:", state["player_army"], flush=True)
        players = [(name, unit) for name, unit in state["regiments"].items() if unit["side"] == "player"]
        if players:
            average_x = sum(unit["x"] for _, unit in players) / len(players)
            average_y = sum(unit["y"] for _, unit in players) / len(players)
            command({"op": "target", "point": [average_x, average_y]})
        command({"op": "capture", "path": str(output / "tick-0000.png")})
        command({"op": "order", "event": ["start_battle"]})
        while state["tick"] < ticks and state["result"] is None:
            regiments = state["regiments"]
            enemies = [(name, unit) for name, unit in regiments.items() if unit["side"] == "enemy"]
            for name, unit in regiments.items():
                if unit["side"] != "player" or unit["models"] <= 0 or unit["routing"] or unit["fled"]:
                    continue
                target = nearest_enemy(unit, enemies)
                if target is not None:
                    command({"op": "order", "event": ["select", name]})
                    command({"op": "order", "event": ["attack", target]})
            remaining = ticks - state["tick"]
            state = command({"op": "step", "ticks": min(20, remaining)})["state"]
            if state["tick"] % 100 == 0 or state["result"] is not None:
                present = [unit for unit in state["regiments"].values()
                           if unit["side"] == "player" and unit["models"] > 0 and not unit["fled"]]
                if present and state["result"] is None:
                    command({"op": "target", "point": [sum(unit["x"] for unit in present) / len(present),
                                                       sum(unit["y"] for unit in present) / len(present)]})
                command({"op": "capture", "path": str(output / f"tick-{state['tick']:04d}.png")})
                print(f"tick {state['tick']}: {state['result'] or state['phase']}", flush=True)
        (output / "final-state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return state
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.wait(timeout=30)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installation", nargs="?", default=load_config().installation_path,
                        help="WARFB path (defaults to launcher config)")
    parser.add_argument("--battle", default="BF001")
    parser.add_argument("--ticks", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1995)
    parser.add_argument("--output", type=Path, default=Path("samples") / "auto-play")
    args = parser.parse_args()
    if not args.installation:
        parser.error("WARFB path required; pass it or configure the launcher")
    if args.ticks < 0:
        parser.error("--ticks must not be negative")
    state = play(args.installation, args.battle, args.ticks, args.output, args.seed)
    print(f"final: tick {state['tick']}, {state['result'] or state['phase']}")


if __name__ == "__main__":
    main()
