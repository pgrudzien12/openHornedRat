"""Deterministic battle logging: JSON Lines recording, stdlib-only (no frontend import).

`notes/engine_architecture.md`, "Battle logs and replay" documents the format. In short: one JSON
object per line, each carrying `type` and `tick`. `BattleLogger` is created and driven by
`whshr.battle_scene.BattleScene`, so the exact same simulation calls (`Battle.tick`, `order_move`,
`order_attack`) that would run without a logger also produce the log -- recording and replay share one
code path by construction, they are never a second, parallel implementation of the rules.

Never crashes the battle: `BattleLogger(path=None)` is a no-op recorder, and any `OSError` opening or
writing the file (a missing/unwritable log directory, disk full, ...) disables it silently instead of
raising (docs/testing.md, "the log directory is not writable or disabled ... the battle still runs").
"""
import json
from datetime import datetime, timezone
from pathlib import Path

FORMAT_VERSION = 1


def default_log_path(log_dir, battle_asset_name, when=None):
    """`<log_dir>/battle-YYYYmmdd-HHMMSS-<battle_asset_name>.jsonl`."""
    when = when or datetime.now()
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in battle_asset_name.lower())
    return Path(log_dir) / f"battle-{when:%Y%m%d-%H%M%S}-{safe_name}.jsonl"


def regiment_header_rows(battle, sprite_bases):
    """One header row per regiment (notes/engine_architecture.md, "Battle logs and replay"): identity,
    resolved sprite mapping (to check a suspected wrong sprite mapping), formation and decoded combat
    profile/psychology -- everything needed to read the rest of the log without re-decoding the script."""
    rows = []
    for identifier in sorted(battle.regiments):
        regiment = battle.regiments[identifier]
        rows.append({
            "id": identifier, "name": regiment.name, "side": regiment.side.value,
            "sprite_resource": regiment.sprite,
            "sprite_base": sprite_bases.get((regiment.sprite or "").casefold()),
            "models": regiment.models, "ranks": regiment.ranks,
            "x": regiment.x, "y": regiment.y, "direction": regiment.direction,
            "profile": {
                "WS": regiment.ws, "BS": regiment.bs, "S": regiment.strength, "T": regiment.toughness,
                "W": regiment.wounds, "I": regiment.initiative, "A": regiment.attacks,
                "Ld": regiment.leadership, "armour": regiment.armour,
                "strength_bonus": regiment.strength_bonus, "missile_code": regiment.missile_code,
                "missile_range": regiment.missile_range,
            },
            "psychology": sorted(regiment.psychology),
        })
    return rows


class BattleLogger:
    """Appends JSON Lines records to `path`, flushing after every write so a crash or a closed window
    still leaves a usable log. Pass `path=None` for a disabled (no-op) recorder.

    `trace_scripts=True` additionally writes an `"opcode"` record for every bytecode instruction the
    interpreter (`whshr.interpreter.ScriptInterpreter`) dispatches -- off by default, since it is far
    higher volume than the rest of the log and only useful when actually debugging mission scripts
    (issue #3/#46). `whshr.battle_scene.BattleScene` turns it on via the `WHSHR_TRACE_SCRIPTS`
    environment variable.
    """

    def __init__(self, path=None, trace_scripts=False):
        self.path = Path(path) if path is not None else None
        self._file = None
        self.enabled = False
        self.trace_scripts = trace_scripts
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._file = open(self.path, "w", encoding="utf-8")
                self.enabled = True
            except OSError:
                self._file = None
                self.enabled = False

    def _write(self, record):
        if not self.enabled:
            return
        try:
            self._file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            self._file.write("\n")
            self._file.flush()
        except OSError:
            self.enabled = False
            self.close()

    def write_header(self, *, battle_asset, bts_path, seed, width, height, regiments):
        self._write({
            "type": "header", "tick": 0, "format_version": FORMAT_VERSION,
            "battle_asset": battle_asset, "bts_path": bts_path, "seed": seed,
            "width": width, "height": height,
            "started_at": datetime.now(timezone.utc).isoformat(),  # wall clock: never read by the simulation
            "regiments": regiments,
        })

    def write_order(self, tick, event):
        self._write({"type": "order", "tick": tick, "event": list(event)})

    def write_event(self, tick, battle_event):
        self._write(battle_event.as_record(tick))

    def write_opcode(self, tick, *, unit_id, script_id, pc, opcode, opcode_name, operand, outcome, state):
        """One dispatched bytecode instruction (only when `trace_scripts` is on).

        `outcome` is "ok", "unimplemented" (no handler -- PC advanced past it anyway) or "error" (the
        handler raised; PC also advanced past it, matching `ScriptInterpreter.run`'s recovery). `state`
        is a small snapshot of the fields opcodes actually change, taken *after* the instruction ran, so
        a trace read top-to-bottom shows exactly when e.g. `script_id`, `attack_target` or `cond_flags`
        changed -- this is what caught both the InitUnit and SetBehaviour regressions (issue #3/#46).
        """
        self._write({
            "type": "opcode", "tick": tick, "unit_id": unit_id, "script_id": script_id, "pc": pc,
            "opcode": opcode, "opcode_name": opcode_name, "operand": operand, "outcome": outcome,
            "state": state,
        })

    def write_snapshot(self, tick, battle):
        self._write({
            "type": "snapshot", "tick": tick, "result": battle.result,
            "side_counts": battle.side_counts(), "regiments": battle.snapshot(),
        })

    def write_result(self, tick, battle):
        self._write({"type": "result", "tick": tick, "result": battle.result,
                      "side_counts": battle.side_counts()})

    def write_end(self, tick, reason):
        self._write({"type": "end", "tick": tick, "reason": reason})
        self.close()

    def close(self):
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
        self.enabled = False
