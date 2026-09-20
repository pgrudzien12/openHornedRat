"""Decodes the glue-interpreter part of a savegame.N (SHDR depths + STAX chunk); see notes/save_resume.md.

Usage: save_stax.py <savegame.N> [--check]
--check exits non-zero if the STAX size does not equal the size implied by the SHDR depths.
"""
import struct
import sys

WINDOW_STATE = 0x218A0   # snapshot of the 8 window slots (8 * 0x4314)
SLOT = 0x4314
CALLER = 0x80
FRAME = 0xA0


def chunks(data):
    pos, found = 12, {}
    while pos < len(data):
        tag, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        found[tag] = data[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)
    return found


def decode(data):
    parts = chunks(data)
    header, stax = parts[b"SHDR"], parts[b"STAX"]
    states, contexts, callers, frames = struct.unpack_from("<4I", header, 0xCC)
    expected = states * (WINDOW_STATE + 8) + contexts * 4 + callers * (CALLER + 4) + frames * FRAME
    pos = states * WINDOW_STATE
    snapshots = [stax[i * WINDOW_STATE:(i + 1) * WINDOW_STATE] for i in range(states)]
    counts = struct.unpack_from(f"<{states}I", stax, pos)
    pos += 4 * states
    palettes = struct.unpack_from(f"<{states}i", stax, pos)
    pos += 4 * states
    kinds = struct.unpack_from(f"<{contexts}I", stax, pos)
    pos += 4 * contexts
    names = [stax[pos + i * CALLER:pos + (i + 1) * CALLER].split(b"\0")[0].decode("latin1") for i in range(callers)]
    pos += callers * CALLER
    caller_kinds = struct.unpack_from(f"<{callers}I", stax, pos)
    pos += 4 * callers
    script_frames = []
    for i in range(frames):
        frame = stax[pos + i * FRAME:pos + (i + 1) * FRAME]
        words = struct.unpack("<40I", frame)
        script_frames.append({"name": frame[4:0x84].split(b"\0")[0].decode("latin1"), "module": words[0x21],
                              "position": words[0x26], "parked": words[0x27]})
    slots = [[s[k * SLOT:k * SLOT + 40].split(b"\0")[0].decode("latin1") for k in range(8)] for s in snapshots]
    return {"size_ok": len(stax) == expected, "window_counts": counts, "palette_ids": palettes,
            "context_kinds": kinds, "callers": names, "caller_kinds": caller_kinds,
            "frames": script_frames, "snapshot_slots": slots}


def main(argv):
    result = decode(open(argv[1], "rb").read())
    for key, value in result.items():
        print(key, value)
    return 0 if result["size_ok"] or "--check" not in argv else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
