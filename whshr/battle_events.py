"""Structured battle event records shared by `whshr.engine`, `whshr.combat`, `whshr.ai` and
`whshr.battle_log`.

`whshr.engine.Battle.events` has always been "a list the view can still print" (docs/testing.md,
existing BDD scenarios in `tests/test_combat.py` compare it against plain strings). `BattleEvent` is a
`str` subclass so every existing use keeps working unchanged (`==`, `in`, `str.format`, printing) while
also carrying a machine-readable `kind` and a `data` mapping of structured fields, which
`whshr.battle_log.BattleLogger` uses to write a diagnosable JSON Lines record instead of re-parsing text.
"""


class BattleEvent(str):
    """A human-readable event string plus a `kind` and structured `data` for logging."""

    def __new__(cls, text, kind, **data):
        self = super().__new__(cls, text)
        self.kind = kind
        self.data = data
        return self

    def as_record(self, tick):
        """This event as a JSON-serializable `battle_log` record."""
        record = {"type": "event", "tick": tick, "kind": self.kind, "text": str(self)}
        record.update(self.data)
        return record
