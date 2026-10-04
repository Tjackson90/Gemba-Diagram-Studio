"""
Premium drawing utilities shared by chord_diagram.py and scale_diagram.py.

Provides:
  - Radial gradient background + noise texture
  - Dark wood-grain fretboard rectangle
  - Metallic bevel fret wires (horizontal and vertical)
  - String thickness + shadow (horizontal and vertical)
  - Fret inlay position marker dots
  - Note dot 3-D shadow + sphere highlight
  - String name cap circles
  - Gold double-line decorative border
  - Gold-style watermark
"""

from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw
import config


# ── Background ─────────────────────────────────────────────────────────────

def apply_background_gradient(img):
    return _background_gradient(img.size).copy()


@lru_cache(maxsize=4)
def _background_gradient(size):
    """
    Replace image pixels with a radial gradient (center → edge) plus subtle noise.
    Returns a new RGBA Image.
    """
    w, h = size
    cx, cy = w / 2, h / 2

    ys = np.arange(h, dtype=np.float32)[:, None]
    xs = np.arange(w, dtype=np.float32)[None, :]
    dist = np.sqrt(((xs - cx) / cx) ** 2 + ((ys - cy) / cy) ** 2)
    dist = np.clip(dist, 0.0, 1.0)

    c_c = np.array(config.BG_GRADIENT_CENTER, dtype=np.float32)
    c_e = np.array(config.BG_GRADIENT_EDGE,   dtype=np.float32)

    t = dist[:, :, np.newaxis]               # shape (h, w, 1)
    rgb = (c_c * (1.0 - t) + c_e * t)       # shape (h, w, 3)

    # Subtle film-grain noise  ±5 per channel
    rng = np.random.default_rng(seed=42)
    noise = rng.integers(-5, 6, size=(h, w, 3), dtype=np.int16)
    rgb = np.clip(rgb.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    alpha = np.full((h, w, 1), 255, dtype=np.uint8)
    arr = np.concatenate([rgb, alpha], axis=2)
    return Image.fromarray(arr, "RGBA")


# ── Fretboard rectangle ────────────────────────────────────────────────────

def draw_fretboard_rect(img, x, y, w, h):
    """
    Composite a dark wood-grain fretboard rectangle onto *img*.
    Returns a new RGBA Image.
    """
    fb = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(fb)

    # Solid base
    draw.rectangle([x, y, x + w, y + h], fill=config.FRETBOARD_FILL + (255,))

    # Procedural grain — vertical streaks with deterministic seed
    rng = np.random.default_rng(seed=7)
    num_grains = max(int(w / 3), 8)
    for _ in range(num_grains):
        gx = int(x + rng.integers(0, w + 1))
        color = config.FRETBOARD_GRAIN_LO if rng.random() > 0.5 else config.FRETBOARD_GRAIN_HI
        alpha = int(rng.integers(35, 90))
        draw.line([(gx, y), (gx, y + h)], fill=color + (alpha,), width=1)

    return Image.alpha_composite(img, fb)


# ── Fret wires ─────────────────────────────────────────────────────────────

def draw_metallic_fret_h(draw, x1, x2, y, is_nut=False):
    """
    Draw one horizontal fret wire with a 3-tone bevel (highlight / main / shadow).
    For chord-box / scale-box diagrams where frets are horizontal.
    """
    x1, x2, y = int(x1), int(x2), int(y)
    if is_nut:
        draw.line([(x1, y - 3), (x2, y - 3)], fill=config.FRET_WIRE_HIGHLIGHT + (200,), width=2)
        draw.line([(x1, y),     (x2, y)],     fill=config.COLOR_NUT           + (255,), width=6)
        draw.line([(x1, y + 3), (x2, y + 3)], fill=config.FRET_WIRE_SHADOW   + (160,), width=2)
    else:
        draw.line([(x1, y - 1), (x2, y - 1)], fill=config.FRET_WIRE_HIGHLIGHT + (160,), width=1)
        draw.line([(x1, y),     (x2, y)],     fill=config.FRET_WIRE_MAIN      + (190,), width=2)
        draw.line([(x1, y + 1), (x2, y + 1)], fill=config.FRET_WIRE_SHADOW   + (120,), width=1)


def draw_metallic_fret_v(draw, x, y1, y2, is_nut=False):
    """
    Draw one vertical fret line with a 3-tone bevel.
    For full-fretboard diagrams where frets are vertical.
    """
    x, y1, y2 = int(x), int(y1), int(y2)
    if is_nut:
        draw.line([(x - 3, y1), (x - 3, y2)], fill=config.FRET_WIRE_HIGHLIGHT + (200,), width=2)
        draw.line([(x,     y1), (x,     y2)], fill=config.COLOR_NUT           + (255,), width=6)
        draw.line([(x + 3, y1), (x + 3, y2)], fill=config.FRET_WIRE_SHADOW   + (160,), width=2)
    else:
        draw.line([(x - 1, y1), (x - 1, y2)], fill=config.FRET_WIRE_HIGHLIGHT + (160,), width=1)
        draw.line([(x,     y1), (x,     y2)], fill=config.FRET_WIRE_MAIN      + (190,), width=2)
        draw.line([(x + 1, y1), (x + 1, y2)], fill=config.FRET_WIRE_SHADOW   + (120,), width=1)


# ── Strings ────────────────────────────────────────────────────────────────

def draw_string_v(draw, x, y1, y2, string_idx):
    """
    Draw a vertical guitar string (chord / scale-box layout).
    string_idx 0 = low E (thickest), 5 = high e (thinnest).
    """
    x, y1, y2 = int(x), int(y1), int(y2)
    sw = config.STRING_WIDTHS[string_idx]
    color = config.STRING_BASS if string_idx < 3 else config.STRING_TREBLE

    # Drop shadow
    if sw >= 2:
        draw.line([(x + 1, y1 + 1), (x + 1, y2 + 1)], fill=(0, 0, 0, 70), width=sw)

    # Main string
    draw.line([(x, y1), (x, y2)], fill=color + (220,), width=sw)

    # Surface highlight on thicker strings
    if sw >= 3:
        draw.line([(x - 1, y1), (x - 1, y2)], fill=(255, 255, 255, 35), width=1)


def draw_string_h(draw, x1, x2, y, string_idx):
    """
    Draw a horizontal guitar string (full-fretboard layout).
    string_idx 0 = low E (thickest), 5 = high e (thinnest).
    """
    x1, x2, y = int(x1), int(x2), int(y)
    sw = config.STRING_WIDTHS[string_idx]
    color = config.STRING_BASS if string_idx < 3 else config.STRING_TREBLE

    if sw >= 2:
        draw.line([(x1 + 1, y + 1), (x2 + 1, y + 1)], fill=(0, 0, 0, 70), width=sw)

    draw.line([(x1, y), (x2, y)], fill=color + (220,), width=sw)

    if sw >= 3:
        draw.line([(x1, y - 1), (x2, y - 1)], fill=(255, 255, 255, 35), width=1)


# ── Fret inlay dots ────────────────────────────────────────────────────────

_INLAY_FRETS  = {3, 5, 7, 9, 12, 15, 17, 19, 21}
_DOUBLE_FRETS = {12}


def draw_inlay_dots_chord(draw, grid_x, grid_y, grid_w, fret_spacing, start_fret, num_frets):
    """
    Draw fret position-marker inlay dots for chord-box / scale-box (vertical) layout.
    Dots are centred horizontally in each fret cell.
    """
    radius = max(int(grid_w * 0.04), 4)

    for fret_offset in range(num_frets):
        abs_fret = start_fret + fret_offset
        if abs_fret not in _INLAY_FRETS:
            continue
        cy = int(grid_y + (fret_offset + 0.5) * fret_spacing)
        cx = int(grid_x + grid_w / 2)

        if abs_fret in _DOUBLE_FRETS:
            off = int(grid_w * 0.22)
            draw.ellipse([cx - off - radius, cy - radius, cx - off + radius, cy + radius],
                         fill=config.INLAY_COLOR + (100,))
            draw.ellipse([cx + off - radius, cy - radius, cx + off + radius, cy + radius],
                         fill=config.INLAY_COLOR + (100,))
        else:
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                         fill=config.INLAY_COLOR + (100,))


def draw_inlay_dots_fretboard(draw, grid_x, grid_y, fret_spacing, string_spacing, num_frets):
    """
    Draw fret position-marker inlay dots for the horizontal full-fretboard layout.
    Dots sit mid-height of the fretboard.
    """
    radius = max(int(string_spacing * 0.14), 4)
    mid_y   = grid_y + string_spacing * 2.5  # midpoint of 5 gaps

    for f in range(1, num_frets + 1):
        if f not in _INLAY_FRETS:
            continue
        cx = int(grid_x + (f - 0.5) * fret_spacing)

        if f in _DOUBLE_FRETS:
            off = int(string_spacing * 0.65)
            draw.ellipse([cx - radius, mid_y - off - radius, cx + radius, mid_y - off + radius],
                         fill=config.INLAY_COLOR + (100,))
            draw.ellipse([cx - radius, mid_y + off - radius, cx + radius, mid_y + off + radius],
                         fill=config.INLAY_COLOR + (100,))
        else:
            draw.ellipse([cx - radius, mid_y - radius, cx + radius, mid_y + radius],
                         fill=config.INLAY_COLOR + (100,))


# ── Note dots ──────────────────────────────────────────────────────────────

def draw_note_dot_3d(shadow_draw, dot_draw, cx, cy, radius, is_root,
                     label="", font=None):
    """
    Draw a note dot onto *shadow_draw* (shadow pass) and *dot_draw* (dot + highlight pass).

    Typical usage — create two RGBA layers, draw all dots, then composite both once:

        shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        dot_layer    = Image.new("RGBA", img.size, (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow_layer)
        d_draw = ImageDraw.Draw(dot_layer)
        for note in notes:
            draw_note_dot_3d(s_draw, d_draw, cx, cy, r, is_root, label, font)
        img = Image.alpha_composite(img, shadow_layer)
        img = Image.alpha_composite(img, dot_layer)
    """
    cx, cy = int(cx), int(cy)

    # Drop shadow (shifted down-right)
    sd = max(int(radius * 0.28), 2)
    shadow_draw.ellipse(
        [cx - radius + sd, cy - radius + sd,
         cx + radius + sd, cy + radius + sd],
        fill=(0, 0, 0, config.DOT_SHADOW_ALPHA),
    )

    # Main dot fill
    fill = config.COLOR_DOT_ROOT if is_root else config.COLOR_DOT_FILL
    dot_draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=fill + (255,),
    )

    # Label text centred inside dot
    if label and font:
        text_color = config.COLOR_DOT_TEXT_ROOT if is_root else config.COLOR_DOT_TEXT
        bbox = dot_draw.textbbox((0, 0), label, font=font)
        nw = bbox[2] - bbox[0]
        nh = bbox[3] - bbox[1]
        dot_draw.text(
            (cx - nw / 2, cy - nh / 2 - 1),
            label,
            fill=text_color + (255,),
            font=font,
        )


# ── String name circles ────────────────────────────────────────────────────

def draw_string_circle(draw, cx, cy, radius, label, font):
    """
    Draw a small labelled circle cap at a string end (string name indicator).
    """
    cx, cy = int(cx), int(cy)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=config.NAVY_DEEP + (210,),
        outline=config.GOLD + (200,),
        width=2,
    )
    if label and font:
        bbox = draw.textbbox((0, 0), label, font=font)
        # Correctly center using all four bbox coords (handles font descenders)
        nw = bbox[2] - bbox[0]
        nh = bbox[3] - bbox[1]
        draw.text(
            (cx - bbox[0] - nw / 2, cy - bbox[1] - nh / 2),
            label,
            fill=config.CREAM + (240,),
            font=font,
        )


# ── Decorative border ──────────────────────────────────────────────────────

def draw_decorative_border(img):
    """
    Composite a gold double-line border frame onto *img*.
    Returns a new RGBA Image.
    """
    w, h = img.size
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    p = config.FRAME_PADDING
    g = config.FRAME_GAP

    d.rectangle([p,         p,         w - p,         h - p],         outline=config.GOLD + (155,), width=2)
    d.rectangle([p + g,     p + g,     w - p - g,     h - p - g],     outline=config.GOLD + (100,), width=1)

    return Image.alpha_composite(img, layer)


# ── Watermark ──────────────────────────────────────────────────────────────

def draw_watermark_gold(img, font_wm):
    """
    Composite a gold "GembaGuitar.com" watermark, positioned inside the frame.
    Returns a new RGBA Image.
    """
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    part1, part2 = "Gemba", "Guitar.com"
    b1 = od.textbbox((0, 0), part1, font=font_wm)
    b2 = od.textbbox((0, 0), part2, font=font_wm)
    w1 = b1[2] - b1[0]
    w2 = b2[2] - b2[0]
    wm_h = max(b1[3] - b1[1], b2[3] - b2[1])

    pad = config.FRAME_PADDING + config.FRAME_GAP + 4
    wm_x = w - w1 - w2 - int(w * 0.02) - pad
    wm_y = h - wm_h - pad

    od.text((wm_x,      wm_y), part1, fill=config.GOLD  + (160,), font=font_wm)
    od.text((wm_x + w1, wm_y), part2, fill=config.CREAM + (120,), font=font_wm)

    return Image.alpha_composite(img, overlay)
