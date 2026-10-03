"""
Chord progression diagram renderer.

Draws a horizontal strip of chord diagrams for a progression,
with a shared title bar showing key + progression name.

Usage:
    from diagrams.progression_diagram import render_progression_strip

    img = render_progression_strip(
        chords=chord_dicts,   # from data.progressions.get_progression_chords()
        title="C Major  |  I – V – vi – IV",
        highlighted_idx=None,  # int index to glow (for video frames)
    )
"""

from PIL import Image, ImageDraw, ImageFont

import config
from data.notes import note_name_to_semitone
from diagrams.chord_diagram import render_chord_diagram


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


def render_progression_strip(
    chords,
    title="",
    highlighted_idx=None,
    chord_w=420,
    chord_h=560,
    padding=24,
    title_height=80,
    roman_height=52,
    bg_color=None,
    dot_label="note",
    show_barre=True,
    barre_style="rect",
    show_string_names=True,
    show_finger_numbers=True,
):
    """
    Render all chords side-by-side in a single image.

    Args:
        chords:         list of chord dicts from get_progression_chords()
        title:          top-of-image label, e.g. "C Major | I – V – vi – IV"
        highlighted_idx: index (0-based) of chord to highlight with a gold glow
        chord_w/h:      pixel dimensions of each individual chord sub-image
        padding:        horizontal gap between chords
        title_height:   pixels for the top title bar
        roman_height:   pixels for the Roman numeral labels below each chord
        bg_color:       (R,G,B) background, or None for transparent

    Returns:
        PIL.Image.Image (RGBA)
    """
    n = len(chords)
    if n == 0:
        return Image.new("RGBA", (800, 400), config.NAVY_DEEP + (255,))

    total_w = n * chord_w + (n + 1) * padding
    total_h = title_height + chord_h + roman_height + padding

    if bg_color is not None:
        canvas = Image.new("RGBA", (total_w, total_h), bg_color + (255,))
    else:
        canvas = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # ── Title bar ─────────────────────────────────────────
    font_title = _load_font(config.FONT_DISPLAY, int(title_height * 0.52))
    if title:
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tx = (total_w - (bbox[2] - bbox[0])) // 2
        ty = (title_height - (bbox[3] - bbox[1])) // 2
        draw.text((tx, ty), title, font=font_title, fill=config.GOLD)

    # Thin gold separator below title
    sep_y = title_height - 2
    draw.rectangle([padding, sep_y, total_w - padding, sep_y + 2], fill=config.GOLD)

    font_roman = _load_font(config.FONT_BODY_BOLD, int(roman_height * 0.48))
    font_name  = _load_font(config.FONT_BODY, int(roman_height * 0.36))

    for i, chord in enumerate(chords):
        x = padding + i * (chord_w + padding)
        y = title_height

        # Highlight glow for current chord
        is_highlighted = (highlighted_idx == i)
        if is_highlighted:
            glow_margin = 10
            glow_rect = [
                x - glow_margin, y - glow_margin,
                x + chord_w + glow_margin, y + chord_h + glow_margin,
            ]
            # Outer glow layers (soft gold)
            for shrink, alpha in [(0, 60), (3, 100), (6, 160)]:
                gr = [glow_rect[0] + shrink, glow_rect[1] + shrink,
                      glow_rect[2] - shrink, glow_rect[3] - shrink]
                glow_img = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                gd = ImageDraw.Draw(glow_img)
                gd.rounded_rectangle(gr, radius=18, fill=config.GOLD_BRIGHT + (alpha,))
                canvas = Image.alpha_composite(canvas, glow_img)
                draw = ImageDraw.Draw(canvas)

        # Render individual chord diagram
        root_semi = note_name_to_semitone(chord["chord_root"])
        chord_img = render_chord_diagram(
            frets=chord["frets"],
            fingers=chord.get("fingers"),
            chord_name=chord["display_name"],
            root_semitone=root_semi,
            bg_color=bg_color,
            width=chord_w,
            height=chord_h,
            show_watermark=False,
            dot_label=dot_label,
            show_muted_x=True,
            show_open_o=True,
            show_string_names=show_string_names,
            show_finger_numbers=show_finger_numbers,
            show_barre=show_barre,
            barre_style=barre_style,
        )
        canvas.paste(chord_img, (x, y), chord_img.split()[3] if chord_img.mode == "RGBA" else None)

        # ── Roman numeral + chord name below ──────────────
        label_y = y + chord_h + 6

        # Roman numeral (gold)
        roman = chord.get("roman", "")
        rb = draw.textbbox((0, 0), roman, font=font_roman)
        rx = x + (chord_w - (rb[2] - rb[0])) // 2
        draw.text((rx, label_y), roman, font=font_roman,
                  fill=config.GOLD_BRIGHT if is_highlighted else config.GOLD)

        # Chord name (cream, smaller)
        cname = chord.get("display_name", "")
        cb = draw.textbbox((0, 0), cname, font=font_name)
        cx = x + (chord_w - (cb[2] - cb[0])) // 2
        name_y = label_y + (rb[3] - rb[1]) + 2
        draw.text((cx, name_y), cname, font=font_name,
                  fill=config.CREAM)

    return canvas


def make_progression_title(root_name, mode, prog_name):
    """Build a display title string, e.g. 'A Minor  |  i – VI – III – VII'."""
    key_label = f"{root_name} {'Major' if mode == 'major' else 'Minor'}"
    return f"{key_label}  |  {prog_name}"
