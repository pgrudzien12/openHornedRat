"""Builds the launcher's PNG art (whshr/launcher/art/) from the project's own source illustrations.

The source images are AI-generated illustrations made for this project (not taken from the original
game); they are large, so only the derived, launcher-sized PNGs are committed. This tool needs Pillow
and NumPy, which the launcher itself does not: Tk loads the finished PNGs directly, and it cannot
scale images or key out backgrounds at runtime, so every size and state is prepared here.

Usage:
    python build_art.py SOURCE_DIR [OUT_DIR]

SOURCE_DIR holds portrait.png, top_bar.png, bottom_bar.png, scroll_up.png and scroll_down.png;
the decorations sit on a plain black background, which is keyed out to transparency.
"""

import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

BACKGROUND = (20, 15, 11)  # launcher window colour; keep in sync with gui.py's BACKGROUND
PORTRAIT_SIZE = (544, 680)
HEADER_WIDTH = 360
FOOTER_WIDTH = 280
ARROW_SIZE = 30
BUTTON_SIZES = {"wide": (300, 56), "small": (128, 40)}
# The rust panel's middle, as a fraction of a button's height (the spikes and cloth below it make the
# image taller than the plate); keep in sync with theme.py's BUTTON_TEXT_CENTRE.
PLATE_CENTRE = 0.37
PRESSED_BRIGHTNESS = 0.6
HOVER_BRIGHTNESS = 1.18


def key_black(image: Image.Image, threshold: int = 14, soft: int = 48) -> Image.Image:
    """Turns the black background (reachable from the border) transparent, with a soft edge."""
    rgb = np.asarray(image.convert("RGB")).astype(np.float32)
    level = rgb.max(axis=2)
    height, width = level.shape
    background = np.zeros((height, width), dtype=bool)
    pending: deque[tuple[int, int]] = deque()
    for x in range(width):
        pending.extend(((0, x), (height - 1, x)))
    for y in range(height):
        pending.extend(((y, 0), (y, width - 1)))
    while pending:
        y, x = pending.popleft()
        if background[y, x] or level[y, x] > threshold:
            continue
        background[y, x] = True
        if y > 0:
            pending.append((y - 1, x))
        if y < height - 1:
            pending.append((y + 1, x))
        if x > 0:
            pending.append((y, x - 1))
        if x < width - 1:
            pending.append((y, x + 1))
    # Pixels next to the background fade in with their brightness (they were blended with black).
    near = background.copy()
    for _ in range(3):
        grown = near.copy()
        grown[1:] |= near[:-1]
        grown[:-1] |= near[1:]
        grown[:, 1:] |= near[:, :-1]
        grown[:, :-1] |= near[:, 1:]
        near = grown
    alpha = np.ones((height, width), dtype=np.float32)
    edge = near & ~background
    alpha[edge] = np.clip(level[edge] / soft, 0.0, 1.0)
    alpha[background] = 0.0
    safe = np.maximum(alpha, 1e-3)[..., None]
    colour = np.where(edge[..., None], np.clip(rgb / safe, 0, 255), rgb)
    rgba = np.dstack([colour, alpha * 255]).astype(np.uint8)
    keyed = Image.fromarray(rgba, "RGBA")
    return keyed.crop(keyed.getbbox())


def brightness(image: Image.Image, factor: float) -> Image.Image:
    alpha = image.getchannel("A")
    out = ImageEnhance.Brightness(image.convert("RGB")).enhance(factor).convert("RGBA")
    out.putalpha(alpha)
    return out


def fit_width(image: Image.Image, width: int) -> Image.Image:
    return image.resize((width, round(image.height * width / image.width)), Image.Resampling.LANCZOS)


def portrait(source: Image.Image) -> Image.Image:
    """Scales the portrait and fades its right and bottom edges into the window background."""
    image = source.convert("RGB").resize(PORTRAIT_SIZE, Image.Resampling.LANCZOS)
    pixels = np.asarray(image).astype(np.float32)
    width, height = PORTRAIT_SIZE
    fade_x = np.clip((width - 1 - np.arange(width)) / 110.0, 0.0, 1.0) ** 1.6
    fade_y = np.clip((height - 1 - np.arange(height)) / 60.0, 0.0, 1.0)
    weight = (fade_y[:, None] * fade_x[None, :])[..., None]
    blended = pixels * weight + np.array(BACKGROUND, dtype=np.float32) * (1.0 - weight)
    return Image.fromarray(blended.astype(np.uint8), "RGB")


def plate_button(top_bar: Image.Image, size: tuple[int, int]) -> Image.Image:
    """A blank riveted plate made from the top bar's end cap and rust panel (no emblem)."""
    # Coordinates are in the keyed, cropped 1234-wide top bar: cap with rivets, then plain rust panel.
    piece_top, piece_bottom = 100, 470
    cap = top_bar.crop((0, piece_top, 300, piece_bottom))
    panel = top_bar.crop((300, piece_top, 420, piece_bottom))
    scale = size[1] / cap.height
    cap = cap.resize((max(1, round(cap.width * scale)), size[1]), Image.Resampling.LANCZOS)
    panel = panel.resize((max(1, round(panel.width * scale)), size[1]), Image.Resampling.LANCZOS)
    button = Image.new("RGBA", size, (0, 0, 0, 0))
    mirrored_panel = panel.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    x, flip = cap.width, False
    while x < size[0] - cap.width:
        button.paste(mirrored_panel if flip else panel, (x, 0))
        x += panel.width
        flip = not flip
    button.paste(cap, (0, 0))
    right_cap = cap.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    button.paste(right_cap, (size[0] - cap.width, 0))
    # Darken the middle so bone-coloured text reads over the rust.
    xs = np.arange(size[0], dtype=np.float32)
    ys = np.arange(size[1], dtype=np.float32)
    ramp = cap.width * 0.6
    across = np.clip(np.minimum(xs - cap.width * 0.5, size[0] - cap.width * 0.5 - xs) / ramp, 0.0, 1.0)
    down = np.clip(1.0 - np.abs(ys - size[1] * PLATE_CENTRE) / (size[1] * 0.24), 0.0, 1.0) ** 0.7
    darkness = 125.0 * down[:, None] * across[None, :]
    shade = Image.new("RGBA", size, (0, 0, 0, 0))
    shade.putalpha(Image.fromarray(darkness.astype(np.uint8)))
    return Image.alpha_composite(button, shade)


def main(argv: list[str]) -> int:
    source = Path(argv[1])
    out = Path(argv[2]) if len(argv) > 2 else Path(__file__).resolve().parents[2] / "whshr" / "launcher" / "art"
    out.mkdir(parents=True, exist_ok=True)

    portrait(Image.open(source / "portrait.png")).save(out / "portrait.png", optimize=True)
    top_bar = key_black(Image.open(source / "top_bar.png"))
    fit_width(top_bar, HEADER_WIDTH).save(out / "header.png", optimize=True)
    fit_width(key_black(Image.open(source / "bottom_bar.png")), FOOTER_WIDTH).save(out / "footer.png", optimize=True)

    for name in ("scroll_up", "scroll_down"):
        arrow = key_black(Image.open(source / f"{name}.png"))
        arrow.thumbnail((ARROW_SIZE, ARROW_SIZE), Image.Resampling.LANCZOS)
        arrow.save(out / f"{name}.png", optimize=True)
        brightness(arrow, HOVER_BRIGHTNESS).save(out / f"{name}_hover.png", optimize=True)
        brightness(arrow, PRESSED_BRIGHTNESS).save(out / f"{name}_pressed.png", optimize=True)

    for kind, size in BUTTON_SIZES.items():
        button = plate_button(top_bar, size)
        button.save(out / f"button_{kind}.png", optimize=True)
        brightness(button, HOVER_BRIGHTNESS).save(out / f"button_{kind}_hover.png", optimize=True)
        brightness(button, PRESSED_BRIGHTNESS).save(out / f"button_{kind}_pressed.png", optimize=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
