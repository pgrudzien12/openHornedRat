"""Runtime compositing for the verified campaign speaker portraits."""

from .battlefield import read_sprite_sheet
from .script import resource_name

# Glue's resident portrait list, notes/glue_portraits.md §1.  Index 36 is
# BACKALL itself and is not a foreground speaker.
PORTRAIT_SPRITES = {
    0: "CER1", 1: "CARL", 2: "COMM", 3: "SKA4", 4: "SCRI", 5: "MER1", 6: "DWA1", 7: "DWA2",
    8: "DWA3", 9: "DWA4", 10: "GOTR", 11: "ELF1", 12: "BRIW", 13: "MER2", 14: "REIK", 15: "ORC2",
    16: "GOB1", 17: "BERN", 18: "CER2", 19: "BERI", 20: "HOLG", 21: "ENGR", 22: "AZGU", 23: "AMBE",
    24: "GINF", 25: "RAMO", 26: "CARO", 27: "ART1", 28: "CELE", 29: "HALB", 30: "KEEL", 31: "XBOW",
    32: "TREE", 33: "HAMM", 34: "IRON", 35: "KING",
}

# `[ANIM] index=-1` means "the player's current commander" (notes/glue_portraits.md §1.4).
SPEAKER_INDEX = -1
FALLBACK_POSITION = 4  # SCRI: no roster loaded, or the speaker's set is not in the resident list
VOID_LEADER_PORTRAIT = "VoidType"  # sprite-table entry 0: the regiment has no leader portrait


def first_leader_speaker(leader_portraits, portrait_sets):
    """The current speaker for a marching roster (§1.4 items 1-2).

    ``leader_portraits`` are the ``leaderportrait:`` names of the marching regiments in file
    order; the first one that is not the void entry wins. ``portrait_sets`` maps a lower-case
    sprite name to its portrait set name. Returns the upper-case set name (an unresolved name
    is returned as it is and later misses the resident list), or None without a leader.
    """
    for name in leader_portraits:
        token = resource_name(name)
        if token is None or token.casefold() == VOID_LEADER_PORTRAIT.casefold():
            continue
        return portrait_sets.get(token.casefold(), token).upper()
    return None


def speaker_position(speaker, available=None):
    """Resident-list position for ``index=-1`` (§1.4 items 3-4).

    A linear search of the list for the speaker's set; a miss (or no speaker) uses position 4.
    ``available(position)`` says whether that set's frames can be loaded; when they cannot the
    next available position is used (wrapping around; the start when none is available).
    """
    start = next((position for position, sprite in PORTRAIT_SPRITES.items()
                  if speaker is not None and sprite == str(speaker).upper()), FALLBACK_POSITION)
    if available is None:
        return start
    count = len(PORTRAIT_SPRITES)
    for step in range(count):
        position = (start + step) % count
        if available(position):
            return position
    return start


# Roster-book crop window: x, y origin of the 72x104 box cropped from a set's 120x152 frame 0,
# shared by the background (BACKALL frame 0) and the leader portrait so the face stays centred;
# notes/glue_portraits.md §1.3, notes/builtin_widgets.md §2.3. Keyed by set name (upper case).
LEADER_BOX_SIZE = (72, 104)
BACKGROUND_SET = "BACKALL"
NO_MATCH_CROP_WINDOW = (25, 5)  # background origin when the leader's portrait set has no entry below
CROP_WINDOWS = {
    "CER1": (0, 0), "CARL": (0, 0), "COMM": (26, 6), "SKA4": (0, 0), "SCRI": (0, 0),
    "MER1": (26, 5), "DWA1": (23, 12), "DWA2": (25, 17), "DWA3": (47, 5), "DWA4": (30, 21),
    "GOTR": (20, 6), "ELF1": (29, 5), "BRIW": (41, 16), "MER2": (16, 5), "REIK": (19, 4),
    "ORC2": (0, 0), "GOB1": (0, 0), "BERN": (23, 11), "CER2": (24, 3), "BERI": (0, 0),
    "HOLG": (26, 20), "ENGR": (24, 14), "AZGU": (24, 8), "AMBE": (23, 12), "GINF": (22, 9),
    "RAMO": (23, 7), "CARO": (23, 6), "ART1": (35, 16), "CELE": (24, 5), "HALB": (17, 8),
    "KEEL": (23, 9), "XBOW": (25, 9), "TREE": (21, 30), "HAMM": (31, 9), "IRON": (13, 18),
    "KING": (0, 0), BACKGROUND_SET: (0, 0),
}


def load_sprite_sheet(game, name):
    """Decode one installation-resident FOL/BOP sprite set."""
    return read_sprite_sheet(
        name,
        game.binary_file(f"{name}.FOL").read_bytes(),
        game.binary_file(f"{name}.BOP").read_bytes(),
        game.binary_file(f"{name}.PAL").read_bytes() if game.find("FILE", "BINARY", f"{name}.PAL") else b"",
    )


def compose_portrait(palette, background, foreground):
    """Composite one decoded foreground frame over one background frame."""
    if (background.width, background.height) != (foreground.width, foreground.height):
        raise ValueError("speaker portrait and background dimensions do not match")

    rgba = bytearray()
    for back, pixel in zip(background.pixels, foreground.pixels):
        rgba.extend((*palette[pixel or back], 255))
    return background.width, background.height, bytes(rgba)


# Mouth/eye overlay rectangles verified for the two portraits used by every shipped briefing
# (notes/glue_portraits.md §3.1); other sprite sets' overlay geometry is not yet reverse-engineered
# (§6 open question), so they fall back to the static frame-0 portrait with no talk/blink overlay.
OVERLAY_POSITIONS = {
    "SCRI": {frame: (40, 84, 44, 26) for frame in (1, 3, 4, 5, 6)} | {frame: (47, 69, 32, 5) for frame in (2, 7)},
    "COMM": {frame: (43, 64, 36, 27) for frame in (1, 3, 4, 5, 6)} | {frame: (45, 52, 28, 4) for frame in (2, 7)},
}

# Kind-5 sequence tables, notes/glue_portraits.md §3.3. The eye loop's tick counts are given in
# full and reproduced exactly. The mouth "talking" pattern is documented only as a partial,
# non-generated prefix ("looks pseudo-random but is a fixed sequence... then loops"); this repeats
# that documented prefix rather than inventing the undocumented remainder of the real 36-step table.
_EYE_OPEN_TICKS = (49, 36, 40, 46, 22, 44)
EYE_SEQUENCE = tuple(step for open_ticks in _EYE_OPEN_TICKS for step in ((2, open_ticks + 1), (7, 2)))
MOUTH_TALK_FRAMES = (1, 4, 6, 5, 3, 4, 1, 4, 3, 4, 1, 4, 6, 4, 1, 3, 5, 3)


def _mouth_step_ticks(frame):
    return 2 if frame == 6 else 3


class PortraitAnimator:
    """Advance one [ANIM] block's mouth and eye overlay slots (notes/glue_portraits.md §3.2-3.4).

    ``sequence`` 1 = talking (mouth cycles ``MOUTH_TALK_FRAMES``, eyes blink); 2 = stopped (mouth
    held closed at frame 1, eyes still blink - the same loop as sequence 1).

    The tick length is an open question (§6): the timer's *designed* rate is 25 ms, but the note
    itself flags that real Windows 9x hardware only delivered it about every 55 ms, and that this
    was never actually timed against the running original. Using the 55 ms Windows 9x figure here
    rather than the 25 ms design rate; a real capture would settle this properly.
    """
    TICK_MILLISECONDS = 55

    def __init__(self, sequence=1):
        self.sequence = 1
        self._mouth_index = 0
        self._mouth_remaining = 0
        self._eye_index = 0
        self._eye_remaining = 0
        self._elapsed_ms = 0
        self.apply(sequence)

    def apply(self, sequence):
        self.sequence = 2 if int(sequence) == 2 else 1
        self._mouth_index = 0
        self._mouth_remaining = _mouth_step_ticks(MOUTH_TALK_FRAMES[0])
        self._eye_index = 0
        self._eye_remaining = EYE_SEQUENCE[0][1]
        self._elapsed_ms = 0

    @property
    def mouth_frame(self):
        return MOUTH_TALK_FRAMES[self._mouth_index] if self.sequence == 1 else 1

    @property
    def eye_frame(self):
        return EYE_SEQUENCE[self._eye_index][0]

    def advance(self, milliseconds):
        """One step per glue timer message (§3.2), see TICK_MILLISECONDS."""
        self._elapsed_ms += milliseconds
        while self._elapsed_ms >= self.TICK_MILLISECONDS:
            self._elapsed_ms -= self.TICK_MILLISECONDS
            self._step()

    def _step(self):
        if self.sequence == 1:
            self._mouth_remaining -= 1
            if self._mouth_remaining <= 0:
                self._mouth_index = (self._mouth_index + 1) % len(MOUTH_TALK_FRAMES)
                self._mouth_remaining = _mouth_step_ticks(MOUTH_TALK_FRAMES[self._mouth_index])
        self._eye_remaining -= 1
        if self._eye_remaining <= 0:
            self._eye_index = (self._eye_index + 1) % len(EYE_SEQUENCE)
            self._eye_remaining = EYE_SEQUENCE[self._eye_index][1]


def compose_talking_portrait(palette, background, base, sprite_sheet, mouth_frame, eye_frame):
    """Composite the base portrait, then stamp the current mouth and eye overlay frames onto it."""
    width, height, rgba = compose_portrait(palette, background, base)
    positions = OVERLAY_POSITIONS.get(sprite_sheet.name)
    if positions is None:
        return width, height, rgba
    canvas = bytearray(rgba)
    for frame_index in (mouth_frame, eye_frame):
        position = positions.get(frame_index)
        if position is None or frame_index >= len(sprite_sheet.frames):
            continue
        ox, oy, overlay_width, overlay_height = position
        overlay = sprite_sheet.frames[frame_index]
        for row in range(overlay_height):
            for col in range(overlay_width):
                pixel = overlay.pixels[row * overlay_width + col]
                if not pixel:
                    continue
                px, py = ox + col, oy + row
                if 0 <= px < width and 0 <= py < height:
                    offset = (py * width + px) * 4
                    canvas[offset:offset + 3] = bytes(palette[pixel])
                    canvas[offset + 3] = 255
    return width, height, bytes(canvas)


def speaker_portrait(installation, index, bkindex):
    """Compatibility wrapper around the shared content repository."""
    from .glue_content import GlueContent
    content = installation if isinstance(installation, GlueContent) else GlueContent(installation)
    return content.portrait_data(index, bkindex)


def dietrich_portrait(installation, bkindex=15):
    """Compatibility wrapper for callers that explicitly need index 4 / SCRI."""
    return speaker_portrait(installation, 4, bkindex)
