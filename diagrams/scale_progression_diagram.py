"""
Scale and arpeggio progression strip renderer.

Renders a horizontal strip of scale-box or arpeggio-box diagrams — one panel
per chord degree in the progression, each showing the diatonic modal scale or
matching arpeggio to play over that chord.

Usage:
    from diagrams.scale_progression_diagram import (
        render_scale_progression_strip,
        render_arpeggio_progression_strip,
    )

    # items from data.progressions.get_progression_scales / get_progression_arpeggios
    img = render_scale_progression_strip(items, title="C Major | I–IV–V")
    img = render_arpeggio_progression_strip(items, title="C Major | I–IV–V")
"""

from PIL import Image, ImageDraw, ImageFont

import config
from data.scales import get_caged_positions
from data.arpeggios import get_arpeggio_positions
from diagrams.scale_diagram import render_scale_box


def _load_font(font_file, size):
    path = config.get_font_path(font_file)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            pass
    for fallback in ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(fallback, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _build_strip(
    items,
    title,
    panel_getter,          # callable(item) → (box_notes, start_fret, end_fret, panel_title)
    highlighted_idx=None,
    panel_w=380,
    panel_h=520,
    padding=24,
    title_height=80,
    label_height=56,
    bg_color=None,
):
    """
    Generic strip builder used by both scale and arpeggio progression renderers.

    panel_getter(item) must return (box_notes, start_fret, end_fret, panel_title).
    """
    n = len(items)
    if n == 0:
        return Image.new("RGBA", (800, 400), config.NAVY_DEEP + (255,))

    total_w = n * panel_w + (n + 1) * padding
    total_h = title_height + panel_h + label_height + padding

    if bg_color is not None:
        canvas = Image.new("RGBA", (total_w, total_h), bg_color + (255,))
    else:
        canvas = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(canvas)

    # ── Title bar ──────────────────────────────────────────
    font_title  = _load_font(config.FONT_DISPLAY,    int(title_height * 0.52))
    font_roman  = _load_font(config.FONT_BODY_BOLD,  int(label_height * 0.46))
    font_name   = _load_font(config.FONT_BODY,       int(label_height * 0.34))

    if title:
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tx = (total_w - (bbox[2] - bbox[0])) // 2
        ty = (title_height - (bbox[3] - bbox[1])) // 2
        draw.text((tx, ty), title, font=font_title, fill=config.GOLD)

    sep_y = title_height - 2
    draw.rectangle([padding, sep_y, total_w - padding, sep_y + 2], fill=config.GOLD)

    for i, item in enumerate(items):
        x = padding + i * (panel_w + padding)
        y = title_height

        # Highlighted glow (for video frames)
        if highlighted_idx == i:
            glow_margin = 10
            for shrink, alpha in [(0, 60), (3, 100), (6, 160)]:
                gr = [x - glow_margin + shrink, y - glow_margin + shrink,
                      x + panel_w + glow_margin - shrink,
                      y + panel_h + glow_margin - shrink]
                glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                ImageDraw.Draw(glow).rounded_rectangle(
                    gr, radius=18, fill=config.GOLD_BRIGHT + (alpha,)
                )
                canvas = Image.alpha_composite(canvas, glow)
                draw   = ImageDraw.Draw(canvas)

        # Render the scale/arpeggio box panel
        box_notes, start_fret, end_fret, panel_title = panel_getter(item)

        panel_img = render_scale_box(
            box_notes=box_notes,
            start_fret=start_fret,
            end_fret=end_fret,
            scale_name="",
            root_name="",
            bg_color=bg_color,
            width=panel_w,
            height=panel_h,
            show_watermark=False,
        )
        canvas.paste(panel_img, (x, y),
                     panel_img.split()[3] if panel_img.mode == "RGBA" else None)

        # ── Roman numeral + label below panel ─────────────
        label_y = y + panel_h + 6

        roman = item.get("roman", "")
        if roman:
            rb = draw.textbbox((0, 0), roman, font=font_roman)
            rx = x + panel_w // 2 - (rb[2] - rb[0]) // 2
            draw.text((rx, label_y), roman, font=font_roman, fill=config.GOLD + (255,))

        # Panel title (e.g. "C Ionian" or "C Major")
        nb = draw.textbbox((0, 0), panel_title, font=font_name)
        nx = x + panel_w // 2 - (nb[2] - nb[0]) // 2
        ny = label_y + (draw.textbbox((0, 0), roman, font=font_roman)[3] if roman else 0) + 3
        draw.text((nx, ny), panel_title, font=font_name,
                  fill=config.CREAM + (200,))

    return canvas


# ── Position selection helper ──────────────────────────────

def _pick_position(positions, position_num):
    """Return the box dict for position_num (1-based), clamping to available range."""
    if not positions:
        return None
    idx = max(0, min(position_num - 1, len(positions) - 1))
    return positions[idx]


# ── Public renderers ───────────────────────────────────────

def render_scale_progression_strip(
    items,
    title="",
    highlighted_idx=None,
    position_num=1,
    panel_w=380,
    panel_h=520,
    padding=24,
    title_height=80,
    label_height=56,
    bg_color=None,
):
    """
    Render a strip of scale-box diagrams — one per progression degree.

    items: from data.progressions.get_progression_scales()
    position_num: which CAGED box position to display (1-5)
    """
    def panel_getter(item):
        positions = get_caged_positions(item["chord_root"], item["scale_name"])
        pos = _pick_position(positions, position_num)
        if pos is None:
            return [], 0, 4, item["display_name"]
        return (
            pos["notes"],
            pos["start_fret"],
            pos["end_fret"],
            item["display_name"],
        )

    return _build_strip(
        items, title, panel_getter,
        highlighted_idx=highlighted_idx,
        panel_w=panel_w, panel_h=panel_h, padding=padding,
        title_height=title_height, label_height=label_height,
        bg_color=bg_color,
    )


def render_arpeggio_progression_strip(
    items,
    title="",
    highlighted_idx=None,
    position_num=1,
    panel_w=380,
    panel_h=520,
    padding=24,
    title_height=80,
    label_height=56,
    bg_color=None,
):
    """
    Render a strip of arpeggio-box diagrams — one per progression degree.

    items: from data.progressions.get_progression_arpeggios()
    position_num: which position box to display (1-N)
    """
    def panel_getter(item):
        positions = get_arpeggio_positions(item["chord_root"], item["arp_name"])
        pos = _pick_position(positions, position_num)
        if pos is None:
            return [], 0, 4, item["display_name"]
        return (
            pos["notes"],
            pos["start_fret"],
            pos["end_fret"],
            item["display_name"],
        )

    return _build_strip(
        items, title, panel_getter,
        highlighted_idx=highlighted_idx,
        panel_w=panel_w, panel_h=panel_h, padding=padding,
        title_height=title_height, label_height=label_height,
        bg_color=bg_color,
    )


def make_scale_progression_title(root_name, mode, prog_name, kind="Scale"):
    """Build a display title for the strip header."""
    return f"{root_name} {mode.capitalize()}  |  {prog_name}  |  {kind}"
