"""Glue speech recordings: ``B<id>.WAV`` for a text line (notes/briefing_dialogue.md §3.2)."""

import io
import struct
import wave
from pathlib import Path

from .paths import Installation

SPEECH_DIRECTORY = ("BINARY", "GLUE", "SPEECH")  # under REMOTE, looked up case-insensitively


def speech_path(installation: Installation, string_id: int) -> Path | None:
    """The recording of text line ``string_id``, or ``None`` when the installation has none."""
    try:
        directory = installation.remote_dir(*SPEECH_DIRECTORY)
    except FileNotFoundError:
        return None
    wanted = f"b{int(string_id)}.wav"
    return next((path for path in directory.iterdir() if path.name.casefold() == wanted), None)


def canonical_wav(data: bytes) -> bytes | None:
    """The clip as a well-formed WAV file: most originals carry a wrong RIFF size, so the ``fmt `` and ``data``
    chunks are read directly and the PCM is rewritten with correct headers. ``None`` for anything else than PCM."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    position, fmt, pcm = 12, None, None
    while position + 8 <= len(data):
        name, size = data[position:position + 4], struct.unpack_from("<I", data, position + 4)[0]
        body = position + 8
        if name == b"fmt ":
            fmt = struct.unpack_from("<HHIIHH", data, body)
        elif name == b"data":
            pcm = data[body:body + size]  # a size beyond the file just takes what is there
            break
        position = body + size + (size & 1)
    if fmt is None or pcm is None or fmt[0] != 1:
        return None
    _, channels, rate, _, _, bits = fmt
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(bits // 8)
        writer.setframerate(rate)
        writer.writeframes(pcm[:len(pcm) - len(pcm) % (channels * (bits // 8))])
    return out.getvalue()


def load_speech(installation: Installation, string_id: int) -> bytes | None:
    """A playable WAV for ``string_id`` (see :func:`canonical_wav`), or ``None`` when missing or unreadable."""
    path = speech_path(installation, string_id)
    if path is None:
        return None
    try:
        return canonical_wav(path.read_bytes())
    except OSError:
        return None


def clip_milliseconds(installation: Installation | None, string_id: int) -> float:
    """How long the recording of ``string_id`` plays, or 0 when there is none (or no installation)."""
    if installation is None:
        return 0.0
    data = load_speech(installation, string_id)
    if data is None:
        return 0.0
    with wave.open(io.BytesIO(data)) as reader:
        return 1000.0 * reader.getnframes() / max(1, reader.getframerate())
