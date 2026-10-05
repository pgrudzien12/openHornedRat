"""Shared helpers for interpreter tests that run real script words through ScriptInterpreter.run."""

from whshr import behaviour


def word(name: str) -> int:
    """The instruction word of a named opcode."""
    opcode = next(o for o in range(len(behaviour.LENGTHS)) if behaviour.opcode_name(o) == name)
    return behaviour.OPCODE_FLAG | opcode


class FakeDll:
    """A script DLL stand-in: every requested script id returns the same words."""

    def __init__(self, words):
        self._words = words

    def scripts(self, ids):
        return {i: list(self._words) for i in ids}
