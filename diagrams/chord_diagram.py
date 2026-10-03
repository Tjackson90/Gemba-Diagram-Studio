"""
Chord diagram renderer — draws vertical chord box diagrams with Pillow.
Premium visual design: gradient background, wood-grain fretboard, metallic frets,
varied-thickness strings, 3-D note dots, decorative border, gold watermark.
"""

from PIL import Image, ImageDraw, ImageFont
import config
from data.notes import fret_to_note_name, STANDARD_TUNING_MIDI
from diagrams.draw_utils import (
    apply_background_gradient,
    draw_fretboard_rect,
    draw_metallic_fret_h,
    draw_string_v,
    draw_inlay_dots_chord,
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


def render_chord_diagram(
    frets,
    fingers=None,
    chord_name="",
    root_semitone=None,
    bg_color=None,
    width=600,
    height=800,
    show_watermark=True,
    dot_label="note",
    show_muted_x=True,
    show_open_o=True,
    show_string_names=True,
    show_finger_numbers=True,
    show_barre=True,
    barre_style="rect",
    highlighted_strings=None,
):
    """
    Render a chord diagram as a Pillow Image.

    Args:
        frets: list of 6 ints [-1=muted, 0=open, 1+=fret]
        fingers: list of 6 ints [0=unused, 1-4=finger] or None
        chord_name: display name (e.g., "Am7")
        root_semitone: semitone value of root (0-11) for root highlighting
        bg_color: tuple (R,G,B) or None for transparent
        width: image width in pixels
        height: image height in pixels
        show_watermark: include GembaGuitar.com watermark
        dot_label: "note", "finger", or "none"
        show_muted_x: draw X above muted strings
        show_open_o: draw O above open strings
        show_string_names: draw string name circles below the grid
        show_finger_numbers: draw finger numbers below string names
        show_barre: detect and draw barre bars
        barre_style: "rect" for filled rectangle bar, "arch" for curved arc above dots
        highlighted_strings: set of string indices to draw a bright halo around

    Returns:
        PIL.Image.Image (RGBA)
    """
    if fingers is None:
        fingers = [0] * 6
    if highlighted_strings is None:
        highlighted_strings = set()

    has_bg = bg_color is not None
    num_strings = 6
    num_frets = 5

    # ── Base image ─────────────────────────────────────────
    if has_bg:
        img = Image.new("RGBA", (width, height), bg_color + (255,))
        img = apply_background_gradient(img)
    else:
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    draw = ImageDraw.Draw(img)

    # ── Layout ─────────────────────────────────────────────
    margin_top    = int(height * 0.18)
    margin_bottom = int(height * 0.16)   # slightly more room for circles + fingers
    margin_left   = int(width  * 0.18)
    margin_right  = int(width  * 0.12)

    grid_x = margin_left
    grid_y = margin_top
    grid_w = width  - margin_left - margin_right
    grid_h = height - margin_top  - margin_bottom

    string_spacing = grid_w / (num_strings - 1)
    fret_spacing   = grid_h / num_frets

    # ── Fonts ──────────────────────────────────────────────
    title_size    = int(height * 0.08)
    label_size    = int(height * 0.038)
    dot_text_size = int(height * 0.032)
    finger_size   = int(height * 0.028)
    fret_num_size = int(height * 0.032)
    wm_size       = max(int(height * 0.040), 14)

    font_title  = _load_font(config.FONT_DISPLAY,   title_size)
    font_label  = _load_font(config.FONT_BODY_BOLD,  label_size)
    font_dot    = _load_font(config.FONT_BODY_BOLD,  dot_text_size)
    font_finger = _load_font(config.FONT_BODY,       finger_size)
    font_fret   = _load_font(config.FONT_BODY,       fret_num_size)
    font_wm     = _load_font(config.FONT_BODY,       max(wm_size, 10))

    # ── Fret range ─────────────────────────────────────────
    played_frets = [f for f in frets if f > 0]
    if played_frets:
        min_fret = min(played_frets)
        max_fret = max(played_frets)
    else:
        min_fret = max_fret = 0

    if max_fret <= 5:
        start_fret = 1
        show_nut   = True
    else:
        start_fret = min_fret
        show_nut   = False

    # ── Wood-grain fretboard rect (when bg present) ────────
    if has_bg:
        pad = int(width * 0.02)
        img = draw_fretboard_rect(
            img,
            grid_x - pad,
            grid_y - int(height * 0.01),
            grid_w + pad * 2,
            grid_h + int(height * 0.02),
        )
        draw = ImageDraw.Draw(img)   # refresh draw after composite

    # ── Inlay dots on fretboard ────────────────────────────
    draw_inlay_dots_chord(
        draw, grid_x, grid_y, grid_w, fret_spacing, start_fret, num_frets
    )

    # ── Nut / fret number ──────────────────────────────────
    if show_nut:
        nut_y = grid_y
        draw_metallic_fret_h(draw, grid_x - 4, grid_x + grid_w + 4, nut_y, is_nut=True)
    elif start_fret > 1:
        fret_label = str(start_fret)
        bbox = draw.textbbox((0, 0), fret_label, font=font_fret)
        fh = bbox[3] - bbox[1]
        fw = bbox[2] - bbox[0]
        fx = grid_x - int(width * 0.08) - fw
        fy = grid_y + fret_spacing / 2 - fh / 2
        draw.text((fx, fy), fret_label, fill=config.COLOR_LABEL + (255,), font=font_fret)

    # ── Fret wire lines ─────────────────────────────────────
    for i in range(num_frets + 1):
        y = grid_y + i * fret_spacing
        draw_metallic_fret_h(draw, grid_x, grid_x + grid_w, y)

    # ── Strings ─────────────────────────────────────────────
    for i in range(num_strings):
        x = grid_x + i * string_spacing
        draw_string_v(draw, x, grid_y, grid_y + grid_h, i)

    # ── O/X markers above nut ──────────────────────────────
    marker_y = grid_y - int(height * 0.05)
    lw = max(int(width * 0.003), 1)
    for i in range(num_strings):
        x = grid_x + i * string_spacing
        f = frets[i]
        if f == -1 and show_muted_x:
            sz = int(height * 0.018)
            draw.line([(x - sz, marker_y - sz), (x + sz, marker_y + sz)],
                      fill=config.COLOR_MUTED + (255,), width=max(lw, 2))
            draw.line([(x - sz, marker_y + sz), (x + sz, marker_y - sz)],
                      fill=config.COLOR_MUTED + (255,), width=max(lw, 2))
        elif f == 0 and show_open_o:
            sz = int(height * 0.016)
            is_highlighted = i in highlighted_strings
            draw.ellipse(
                [x - sz, marker_y - sz, x + sz, marker_y + sz],
                fill=config.GOLD_BRIGHT + (220,) if is_highlighted else None,
                outline=config.GOLD_BRIGHT + (255,) if is_highlighted else config.COLOR_OPEN + (255,),
                width=max(lw, 2),
            )

    # ── Chord name title ───────────────────────────────────
    if chord_name:
        bbox = draw.textbbox((0, 0), chord_name, font=font_title)
        tw = bbox[2] - bbox[0]
        title_x = grid_x + grid_w / 2 - tw / 2
        title_y = int(height * 0.02)
        draw.text(
            (title_x, title_y),
            chord_name,
            fill=config.COLOR_LABEL + (255,),
            font=font_title,
        )

    # ── Detect barre groups ────────────────────────────────
    from collections import defaultdict
    barre_strings = set()
    barre_groups  = []

    if show_barre and fingers:
        _groups = defaultdict(list)
        for i in range(num_strings):
            f_i, fg_i = frets[i], fingers[i]
            if f_i > 0 and fg_i > 0:
                _groups[(f_i, fg_i)].append(i)
        for (f_b, fg_b), slist in _groups.items():
            if len(slist) >= 2:
                slist = sorted(slist)
                barre_strings.update(slist)
                barre_groups.append((f_b, fg_b, slist))

    prefer_flat = root_semitone in {1, 3, 6, 8, 10} if root_semitone else False
    dot_radius  = int(min(string_spacing, fret_spacing) * config.CHORD_LAYOUT["dot_radius_ratio"])

    # ── Barre bars — drawn directly on img (no layer = no bleed) ──
    for (f_b, fg_b, slist) in barre_groups:
        fret_in_box = f_b - start_fret
        y       = int(grid_y + (fret_in_box + 0.5) * fret_spacing)
        x_left  = int(grid_x + slist[0]  * string_spacing)
        x_right = int(grid_x + slist[-1] * string_spacing)
        # Cap overhang so bar stays within the fretboard grid
        bar_overhang = max(1, dot_radius // 3)

        if barre_style == "arch":
            # Draw a gentle arch that sits clearly above the dots.
            # The arch endpoints align with the top edges of the outer dots
            # and the peak rises arch_rise pixels above that.
            arch_rise = max(int(dot_radius * 1.2), 6)
            line_w    = max(3, dot_radius // 3)
            # Bounding box: endpoints are at the mid-height of the bbox,
            # so top = dot_top - arch_rise, bottom = dot_top + arch_rise
            dot_top   = y - dot_radius
            draw.arc(
                [x_left, dot_top - arch_rise, x_right, dot_top + arch_rise],
                start=180, end=0,
                fill=config.WHITE + (255,),
                width=line_w,
            )
        else:
            # Solid white barre rectangle with tightened overhang
            draw.rectangle(
                [x_left - bar_overhang, y - dot_radius,
                 x_right + bar_overhang, y + dot_radius],
                fill=config.WHITE + (255,),
            )

        # Per-dot halos first (so dots render on top of them)
        hi_sxs = [int(grid_x + si * string_spacing)
                  for si in slist if si in highlighted_strings]
        if hi_sxs:
            hr = dot_radius + max(int(dot_radius * 0.4), 4)
            halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
            h_draw = ImageDraw.Draw(halo)
            for sx in hi_sxs:
                h_draw.ellipse(
                    [sx - hr, y - hr, sx + hr, y + hr],
                    fill=config.GOLD_BRIGHT + (160,),
                )
            img = Image.alpha_composite(img, halo)
            draw = ImageDraw.Draw(img)

        # One filled dot circle per string in the barre (drawn after halo)
        for si in slist:
            sx = int(grid_x + si * string_spacing)
            midi_val = STANDARD_TUNING_MIDI[si] + f_b
            semi = midi_val % 12
            is_root = (root_semitone is not None and semi == root_semitone)
            fill_color = config.COLOR_DOT_ROOT if is_root else config.COLOR_DOT_FILL
            text_color = config.COLOR_DOT_TEXT_ROOT if is_root else config.COLOR_DOT_TEXT

            draw.ellipse(
                [sx - dot_radius, y - dot_radius,
                 sx + dot_radius, y + dot_radius],
                fill=fill_color + (255,),
            )

            if dot_label == "note":
                lbl = fret_to_note_name(si, f_b, prefer_flat=prefer_flat)
            elif dot_label == "finger":
                lbl = str(fg_b)
            else:
                lbl = ""

            if lbl:
                bbox = draw.textbbox((0, 0), lbl, font=font_dot)
                nw = bbox[2] - bbox[0]
                nh = bbox[3] - bbox[1]
                draw.text(
                    (sx - nw / 2, y - nh / 2 - 1),
                    lbl, fill=text_color + (255,), font=font_dot,
                )

    # ── Shadow / dot layers for individual 3-D dots ───────
    shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dot_layer    = Image.new("RGBA", img.size, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    d_draw = ImageDraw.Draw(dot_layer)

    # ── Individual note dots ───────────────────────────────
    for i in range(num_strings):
        f = frets[i]
        if f <= 0 or i in barre_strings:
            continue

        x = grid_x + i * string_spacing
        fret_in_box = f - start_fret
        y = grid_y + (fret_in_box + 0.5) * fret_spacing

        midi     = STANDARD_TUNING_MIDI[i] + f
        semi     = midi % 12
        is_root  = (root_semitone is not None and semi == root_semitone)

        # Highlight halo (animated playback)
        if i in highlighted_strings:
            hr = dot_radius + max(int(dot_radius * 0.4), 4)
            d_draw.ellipse(
                [x - hr, y - hr, x + hr, y + hr],
                fill=config.GOLD_BRIGHT + (160,),
            )

        if dot_label == "note":
            label = fret_to_note_name(i, f, prefer_flat=prefer_flat)
        elif dot_label == "finger":
            fg = fingers[i] if fingers else 0
            label = str(fg) if fg > 0 else ""
        else:
            label = ""

        draw_note_dot_3d(s_draw, d_draw, x, y, dot_radius, is_root, label, font_dot)

    # Composite shadow then dots
    img = Image.alpha_composite(img, shadow_layer)
    img = Image.alpha_composite(img, dot_layer)
    draw = ImageDraw.Draw(img)

    # ── String name circles / labels below ─────────────────
    string_names  = config.CHORD_LAYOUT["string_names"]
    circle_radius = max(int(height * 0.030), 11)
    circle_y      = grid_y + grid_h + int(height * 0.030)

    if show_string_names:
        circle_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(circle_layer)
        for i, name in enumerate(string_names):
            if frets[i] == -1:
                continue
            x = grid_x + i * string_spacing
            draw_string_circle(c_draw, x, circle_y, circle_radius, name, font_label)
        img = Image.alpha_composite(img, circle_layer)
        draw = ImageDraw.Draw(img)

    # ── Finger numbers ─────────────────────────────────────
    if show_finger_numbers and any(f > 0 for f in fingers):
        row_offset = circle_radius * 2 + int(height * 0.010) if show_string_names else 0
        finger_y   = circle_y + row_offset
        for i in range(num_strings):
            if frets[i] == -1:
                continue
            fg = fingers[i]
            if fg > 0 and frets[i] > 0:
                fg_str = str(fg)
                bbox = draw.textbbox((0, 0), fg_str, font=font_finger)
                fw = bbox[2] - bbox[0]
                x  = grid_x + i * string_spacing
                draw.text(
                    (x - fw / 2, finger_y),
                    fg_str,
                    fill=config.COLOR_FINGER_NUM + (255,),
                    font=font_finger,
                )

    # ── Decorative border + watermark (only when bg present) ─
    if has_bg:
        img  = draw_decorative_border(img)
        draw = ImageDraw.Draw(img)

    if show_watermark:
        # Centered watermark below the string-name circles (or grid bottom if hidden)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        part1, part2 = "Gemba", "Guitar.com"
        b1 = od.textbbox((0, 0), part1, font=font_wm)
        b2 = od.textbbox((0, 0), part2, font=font_wm)
        w1   = b1[2] - b1[0]
        w2   = b2[2] - b2[0]
        wm_h = max(b1[3] - b1[1], b2[3] - b2[1])
        total_w = w1 + w2
        # Place below string circles (or grid bottom when hidden)
        circles_bottom = circle_y + circle_radius if show_string_names else grid_y + grid_h
        wm_y = circles_bottom + int(height * 0.018)
        # Clamp so it doesn't spill past the image edge
        wm_y = min(wm_y, height - wm_h - int(height * 0.010))
        wm_x = (width - total_w) // 2
        od.text((wm_x,      wm_y), part1, fill=config.GOLD  + (200,), font=font_wm)
        od.text((wm_x + w1, wm_y), part2, fill=config.CREAM + (160,), font=font_wm)
        img = Image.alpha_composite(img, overlay)

    return img
