"""
Scale diagram renderer — full fretboard (horizontal) and positional box (vertical).
Premium visual design: gradient background, wood-grain fretboard, metallic frets,
varied-thickness strings, fret inlay dots, 3-D note dots, decorative border, gold watermark.
"""

from PIL import Image, ImageDraw, ImageFont
import config
from data.notes import STANDARD_TUNING_MIDI, STANDARD_TUNING_NAMES
from diagrams.draw_utils import (
    apply_background_gradient,
    draw_fretboard_rect,
    draw_metallic_fret_h,
    draw_metallic_fret_v,
    draw_string_v,
    draw_string_h,
    draw_inlay_dots_chord,
    draw_inlay_dots_fretboard,
    draw_note_dot_3d,
    draw_string_circle,
    draw_decorative_border,
    draw_watermark_gold,
)


def _load_font(font_file, size):
    """Load a TTF font with fallback to default."""
    path = config.get_font_path(font_file)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            pass
    for fallback in ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(fallback, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# ── Full fretboard (horizontal) ────────────────────────────────────────────

def render_scale_full_fretboard(
    scale_notes,
    scale_name="",
    root_name="",
    bg_color=None,
    width=1600,
    height=500,
    num_frets=15,
    show_watermark=True,
    invert=False,
    highlighted_notes=None,
):
    """
    Render a full fretboard scale diagram (horizontal orientation).

    Args:
        scale_notes: list of dicts {string, fret, semitone, note_name, is_root}
        scale_name: e.g., "Pentatonic Minor"
        root_name: e.g., "A"
        bg_color: (R,G,B) tuple or None for transparent
        width, height: image dimensions
        num_frets: frets to show (0 to num_frets)
        show_watermark: include GembaGuitar.com watermark
        invert: if True, high e string is at top
        highlighted_notes: set of (string, fret) tuples for bright halo

    Returns:
        PIL.Image.Image (RGBA)
    """
    if highlighted_notes is None:
        highlighted_notes = set()

    has_bg = bg_color is not None

    if has_bg:
        img = Image.new("RGBA", (width, height), bg_color + (255,))
        img = apply_background_gradient(img)
    else:
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    draw = ImageDraw.Draw(img)

    # ── Layout ─────────────────────────────────────────────
    margin_top    = int(height * 0.22)
    margin_bottom = int(height * 0.20)
    margin_left   = int(width  * 0.07)
    margin_right  = int(width  * 0.03)

    grid_x = margin_left
    grid_y = margin_top
    grid_w = width  - margin_left - margin_right
    grid_h = height - margin_top  - margin_bottom

    fret_spacing   = grid_w / num_frets
    string_spacing = grid_h / 5          # 6 strings → 5 gaps

    # ── Fonts ──────────────────────────────────────────────
    title_size    = int(height * 0.09)
    label_size    = int(height * 0.050)
    dot_text_size = max(int(min(fret_spacing, string_spacing) * 0.35), 8)
    fret_num_size = int(height * 0.04)
    wm_size       = max(int(width * config.WATERMARK_FONT_SIZE_RATIO), 10)

    font_title = _load_font(config.FONT_DISPLAY,  title_size)
    font_label = _load_font(config.FONT_BODY_BOLD, label_size)
    font_dot   = _load_font(config.FONT_BODY_BOLD, dot_text_size)
    font_fret  = _load_font(config.FONT_BODY_BOLD, fret_num_size)
    font_wm    = _load_font(config.FONT_BODY,      wm_size)

    # ── Wood-grain fretboard rect ──────────────────────────
    if has_bg:
        pad_v = int(height * 0.01)
        img = draw_fretboard_rect(
            img, grid_x, grid_y - pad_v, grid_w, grid_h + pad_v * 2
        )
        draw = ImageDraw.Draw(img)

    # ── Title ──────────────────────────────────────────────
    title = f"{root_name} {scale_name}" if root_name else scale_name
    if title:
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(
            (width / 2 - tw / 2, int(height * 0.02)),
            title,
            fill=config.COLOR_LABEL + (255,),
            font=font_title,
        )

    # ── Inlay dots ─────────────────────────────────────────
    draw_inlay_dots_fretboard(
        draw, grid_x, grid_y, fret_spacing, string_spacing, num_frets
    )

    # ── Nut ────────────────────────────────────────────────
    draw_metallic_fret_v(draw, grid_x, grid_y - 2, grid_y + grid_h + 2, is_nut=True)

    # ── Fret lines (vertical) ──────────────────────────────
    for i in range(1, num_frets + 1):
        x = grid_x + i * fret_spacing
        draw_metallic_fret_v(draw, x, grid_y, grid_y + grid_h)

    # ── Strings (horizontal) ───────────────────────────────
    string_row_order = list(range(5, -1, -1)) if invert else list(range(6))
    for row, s_idx in enumerate(string_row_order):
        y = grid_y + row * string_spacing
        draw_string_h(draw, grid_x, grid_x + grid_w, y, s_idx)

    # ── String name circles on the left ───────────────────
    circle_radius = max(int(string_spacing * 0.38), 10)
    circle_layer  = Image.new("RGBA", img.size, (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(circle_layer)
    for row, s_idx in enumerate(string_row_order):
        y    = grid_y + row * string_spacing
        cx   = grid_x - int(width * 0.025) - circle_radius
        name = STANDARD_TUNING_NAMES[s_idx]
        draw_string_circle(c_draw, cx, y, circle_radius, name, font_label)
    img = Image.alpha_composite(img, circle_layer)
    draw = ImageDraw.Draw(img)

    # ── Fret numbers below ─────────────────────────────────
    dot_radius  = int(min(fret_spacing, string_spacing) * 0.30)
    fret_markers = {3, 5, 7, 9, 12, 15}
    for f in range(1, num_frets + 1):
        if f in fret_markers:
            x     = grid_x + (f - 0.5) * fret_spacing
            y_num = grid_y + grid_h + dot_radius + int(height * 0.03)
            label = str(f)
            bbox  = draw.textbbox((0, 0), label, font=font_fret)
            fw    = bbox[2] - bbox[0]
            draw.text(
                (x - fw / 2, y_num),
                label,
                fill=config.GOLD + (220,),
                font=font_fret,
            )

    # ── Scale dots (3-D) ───────────────────────────────────
    string_to_y = {
        s_idx: grid_y + row * string_spacing
        for row, s_idx in enumerate(string_row_order)
    }

    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dot_layer    = Image.new("RGBA", img.size, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    d_draw = ImageDraw.Draw(dot_layer)

    for note in scale_notes:
        s = note["string"]
        f = note["fret"]
        if f > num_frets:
            continue

        y = string_to_y[s]
        x = grid_x - dot_radius - 8 if f == 0 else grid_x + (f - 0.5) * fret_spacing

        is_root = note.get("is_root", False)

        if (s, f) in highlighted_notes:
            hr = dot_radius + max(int(dot_radius * 0.4), 4)
            d_draw.ellipse([x - hr, y - hr, x + hr, y + hr],
                           fill=config.GOLD_BRIGHT + (200,))

        draw_note_dot_3d(s_draw, d_draw, x, y, dot_radius, is_root,
                         note["note_name"], font_dot)

    img = Image.alpha_composite(img, shadow_layer)
    img = Image.alpha_composite(img, dot_layer)
    draw = ImageDraw.Draw(img)

    # ── Decorative border + watermark ──────────────────────
    if has_bg:
        img  = draw_decorative_border(img)
        draw = ImageDraw.Draw(img)

    if show_watermark:
        if has_bg:
            img = draw_watermark_gold(img, font_wm)
        else:
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            part1, part2 = "Gemba", "Guitar.com"
            b1 = od.textbbox((0, 0), part1, font=font_wm)
            b2 = od.textbbox((0, 0), part2, font=font_wm)
            w1 = b1[2] - b1[0]
            wm_h = max(b1[3] - b1[1], b2[3] - b2[1])
            wm_x = width - w1 - (b2[2] - b2[0]) - int(width * 0.02)
            wm_y = height - wm_h - int(height * 0.02)
            od.text((wm_x,      wm_y), part1, fill=config.GOLD  + (140,), font=font_wm)
            od.text((wm_x + w1, wm_y), part2, fill=config.WHITE + (110,), font=font_wm)
            img = Image.alpha_composite(img, overlay)

    return img


# ── Positional scale box (vertical) ───────────────────────────────────────

def render_scale_box(
    box_notes,
    start_fret,
    end_fret,
    scale_name="",
    root_name="",
    position_num=None,
    bg_color=None,
    width=600,
    height=800,
    show_watermark=True,
    highlighted_notes=None,
):
    """
    Render a positional box scale diagram (vertical, like a chord diagram).

    Args:
        box_notes: list of dicts {string, fret, semitone, note_name, is_root}
        start_fret: lowest fret in the box
        end_fret:   highest fret in the box
        scale_name, root_name: for title
        position_num: CAGED position number (1-5) for subtitle
        bg_color: (R,G,B) or None for transparent
        width, height: image dimensions
        show_watermark: include watermark
        highlighted_notes: set of (string, fret) tuples for bright halo

    Returns:
        PIL.Image.Image (RGBA)
    """
    if highlighted_notes is None:
        highlighted_notes = set()

    has_bg = bg_color is not None

    if has_bg:
        img = Image.new("RGBA", (width, height), bg_color + (255,))
        img = apply_background_gradient(img)
    else:
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    draw = ImageDraw.Draw(img)

    num_strings      = 6
    num_frets_shown  = end_fret - start_fret + 1
    if num_frets_shown < 4:
        num_frets_shown = 4
        end_fret = start_fret + num_frets_shown - 1

    # ── Layout ─────────────────────────────────────────────
    margin_top    = int(height * 0.20)
    margin_bottom = int(height * 0.14)
    margin_left   = int(width  * 0.18)
    margin_right  = int(width  * 0.12)

    grid_x = margin_left
    grid_y = margin_top
    grid_w = width  - margin_left - margin_right
    grid_h = height - margin_top  - margin_bottom

    string_spacing = grid_w / (num_strings - 1)
    fret_spacing   = grid_h / num_frets_shown

    # ── Fonts ──────────────────────────────────────────────
    title_size    = int(height * 0.06)
    subtitle_size = int(height * 0.035)
    label_size    = int(height * 0.036)
    dot_text_size = int(height * 0.028)
    fret_num_size = int(height * 0.030)
    wm_size       = max(int(width * config.WATERMARK_FONT_SIZE_RATIO), 10)

    font_title = _load_font(config.FONT_DISPLAY,  title_size)
    font_sub   = _load_font(config.FONT_BODY,      subtitle_size)
    font_label = _load_font(config.FONT_BODY_BOLD, label_size)
    font_dot   = _load_font(config.FONT_BODY_BOLD, dot_text_size)
    font_fret  = _load_font(config.FONT_BODY,      fret_num_size)
    font_wm    = _load_font(config.FONT_BODY,      wm_size)

    # ── Wood-grain fretboard rect ──────────────────────────
    if has_bg:
        pad = int(width * 0.02)
        img = draw_fretboard_rect(
            img,
            grid_x - pad,
            grid_y - int(height * 0.01),
            grid_w + pad * 2,
            grid_h + int(height * 0.02),
        )
        draw = ImageDraw.Draw(img)

    # ── Title ──────────────────────────────────────────────
    title = f"{root_name} {scale_name}" if root_name else scale_name
    if title:
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(
            (width / 2 - tw / 2, int(height * 0.02)),
            title,
            fill=config.COLOR_LABEL + (255,),
            font=font_title,
        )

    if position_num is not None:
        sub  = f"Position {position_num}"
        bbox = draw.textbbox((0, 0), sub, font=font_sub)
        sw   = bbox[2] - bbox[0]
        draw.text(
            (width / 2 - sw / 2, int(height * 0.09)),
            sub,
            fill=config.GOLD_BRIGHT + (255,),
            font=font_sub,
        )

    # ── Fret number indicator ──────────────────────────────
    if start_fret > 0:
        fret_label = str(start_fret)
        bbox = draw.textbbox((0, 0), fret_label, font=font_fret)
        fh   = bbox[3] - bbox[1]
        draw.text(
            (grid_x - int(width * 0.08), grid_y + fret_spacing * 0.5 - fh / 2),
            fret_label,
            fill=config.COLOR_LABEL + (255,),
            font=font_fret,
        )

    # ── Inlay dots ─────────────────────────────────────────
    draw_inlay_dots_chord(
        draw, grid_x, grid_y, grid_w, fret_spacing, start_fret, num_frets_shown
    )

    # ── Nut ────────────────────────────────────────────────
    if start_fret <= 1:
        draw_metallic_fret_h(draw, grid_x - 4, grid_x + grid_w + 4, grid_y, is_nut=True)

    # ── Fret wire lines ─────────────────────────────────────
    for i in range(num_frets_shown + 1):
        y = grid_y + i * fret_spacing
        draw_metallic_fret_h(draw, grid_x, grid_x + grid_w, y)

    # ── Strings ─────────────────────────────────────────────
    for i in range(num_strings):
        x = grid_x + i * string_spacing
        draw_string_v(draw, x, grid_y, grid_y + grid_h, i)

    # ── String name circles below ──────────────────────────
    string_names  = config.CHORD_LAYOUT["string_names"]
    circle_radius = max(int(height * 0.028), 10)
    circle_y      = grid_y + grid_h + int(height * 0.028)

    circle_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(circle_layer)
    for i, name in enumerate(string_names):
        x = grid_x + i * string_spacing
        draw_string_circle(c_draw, x, circle_y, circle_radius, name, font_label)
    img = Image.alpha_composite(img, circle_layer)
    draw = ImageDraw.Draw(img)

    # ── Scale dots (3-D) ───────────────────────────────────
    dot_radius = int(min(string_spacing, fret_spacing) * config.SCALE_BOX_LAYOUT["dot_radius_ratio"])

    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dot_layer    = Image.new("RGBA", img.size, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    d_draw = ImageDraw.Draw(dot_layer)

    for note in box_notes:
        s = note["string"]
        f = note["fret"]
        x = grid_x + s * string_spacing

        if f < start_fret:
            y = grid_y - int(height * 0.04)   # open string above nut
        else:
            fret_in_box = f - start_fret
            y = grid_y + (fret_in_box + 0.5) * fret_spacing

        is_root = note.get("is_root", False)

        if (s, f) in highlighted_notes:
            hr = dot_radius + max(int(dot_radius * 0.4), 4)
            d_draw.ellipse([x - hr, y - hr, x + hr, y + hr],
                           fill=config.GOLD_BRIGHT + (200,))

        draw_note_dot_3d(s_draw, d_draw, x, y, dot_radius, is_root,
                         note["note_name"], font_dot)

    img = Image.alpha_composite(img, shadow_layer)
    img = Image.alpha_composite(img, dot_layer)
    draw = ImageDraw.Draw(img)

    # ── Decorative border + watermark ──────────────────────
    if has_bg:
        img  = draw_decorative_border(img)
        draw = ImageDraw.Draw(img)

    if show_watermark:
        if has_bg:
            img = draw_watermark_gold(img, font_wm)
        else:
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            part1, part2 = "Gemba", "Guitar.com"
            b1 = od.textbbox((0, 0), part1, font=font_wm)
            b2 = od.textbbox((0, 0), part2, font=font_wm)
            w1 = b1[2] - b1[0]
            wm_h = max(b1[3] - b1[1], b2[3] - b2[1])
            wm_x = width - w1 - (b2[2] - b2[0]) - int(width * 0.03)
            wm_y = height - wm_h - int(height * 0.02)
            od.text((wm_x,      wm_y), part1, fill=config.GOLD  + (140,), font=font_wm)
            od.text((wm_x + w1, wm_y), part2, fill=config.WHITE + (110,), font=font_wm)
            img = Image.alpha_composite(img, overlay)

    return img
