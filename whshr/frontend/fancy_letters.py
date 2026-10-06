"""Source rectangles for the installed FancyLetters book drop-cap sheet."""

# notes/native-windows.md §5.7: stored dimensions gain two pixels when drawn.
_ROWS = (
    (("A", 0, 60, 72), ("B", 64, 66, 72), ("C", 136, 51, 72), ("D", 192, 52, 72),
     ("E", 248, 61, 72), ("F", 312, 56, 85), ("G", 376, 56, 72), ("H", 440, 54, 82),
     ("I", 496, 50, 72), ("J", 552, 67, 83)),
    (("K", 0, 62, 73), ("L", 64, 59, 72), ("M", 128, 93, 71), ("N", 224, 56, 76),
     ("O", 288, 46, 72), ("P", 336, 58, 85), ("Q", 400, 62, 82), ("R", 464, 54, 72),
     ("S", 520, 45, 72), ("T", 568, 52, 72)),
    (("U", 0, 51, 72), ("V", 56, 58, 72), ("W", 120, 61, 72), ("X", 184, 45, 78),
     ("Y", 232, 48, 85), ("Z", 288, 52, 72)),
)
CAPS = {letter: (x, row * 88, width + 2, height + 2)
        for row, entries in enumerate(_ROWS)
        for letter, x, width, height in entries}
