"""
Tab diagram renderer — guitar tablature notation as branded PNG images.

Supports two modes:
  - Chord tab: single column showing all 6 strings with fret numbers
  - Scale/arpeggio tab: horizontal sequence of notes, one column per note
"""

from PIL import Image, ImageDraw, ImageFont
import config
from data.notes import STANDARD_TUNING_MIDI, STANDARD_TUNING_NAMES


# String names in standard tab order (high e at top)
TAB_STRING_NAMES = ["e", "B", "G", "D", "A", "E"]  # index 5→0 (high→low)


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


def _draw_watermark(draw, img, font_wm, width, height):
    """Draw the split Gemba/Guitar.com watermark."""
    part1, part2 = "Gemba", "Guitar.com"
    b1 = draw.textbbox((0, 0), part1, font=font_wm)
    b2 = draw.textbbox((0, 0), part2, font=font_wm)
    w1 = b1[2] - b1[0]
    w2 = b2[2] - b2[0]
    wm_h = max(b1[3] - b1[1], b2[3] - b2[1])
    wm_x = width - w1 - w2 - int(width * 0.02)
    wm_y = height - wm_h - int(height * 0.02)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.text((wm_x,      wm_y), part1, fill=config.GOLD    + (140,), font=font_wm)
    od.text((wm_x + w1, wm_y), part2, fill=config.WHITE   + (110,), font=font_wm)
    return Image.alpha_composite(img, overlay)


def render_chord_tab(
    frets,
    chord_name="",
    bg_color=None,
    width=500,
    height=420,
    show_watermark=True,
    highlighted_strings=None,
):
    """
    Render a chord as guitar tab notation (6 string lines, one note column).

    Args:
        frets: list of 6 ints [-1=muted, 0=open, 1+=fret]
        chord_name: display name for title
        bg_color: (R,G,B) or None for transparent
        width, height: image dimensions
        show_watermark: include GembaGuitar.com watermark
        highlighted_strings: set of string indices to highlight (for animation)

    Returns:
        PIL.Image.Image (RGBA)
    """
    if highlighted_strings is None:
        highlighted_strings = set()

    if bg_color:
        img = Image.new("RGBA", (width, height), bg_color + (255,))
    else:
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Layout ─────────────────────────────────────────────
    margin_top = int(height * 0.20)
    margin_bottom = int(height * 0.12)
    margin_left = int(width * 0.12)
    margin_right = int(width * 0.12)

    grid_x = margin_left
    grid_y = margin_top
    grid_w = width - margin_left - margin_right
    grid_h = height - margin_top - margin_bottom

    string_spacing = grid_h / 5  # 6 strings, 5 gaps
    col_x = grid_x + grid_w * 0.5  # Single note column centered

    # ── Fonts ──────────────────────────────────────────────
    title_size = int(height * 0.09)
    label_size = int(height * 0.055)
    note_size = int(height * 0.055)
    wm_size = max(int(width * config.WATERMARK_FONT_SIZE_RATIO), 10)

    font_title = _load_font(config.FONT_DISPLAY, title_size)
    font_label = _load_font(config.FONT_BODY, label_size)
    font_note = _load_font(config.FONT_BODY_BOLD, note_size)
    font_wm = _load_font(config.FONT_BODY, wm_size)

    # ── Title ──────────────────────────────────────────────
    if chord_name:
        bbox = draw.textbbox((0, 0), chord_name, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(
            (width / 2 - tw / 2, int(height * 0.02)),
            chord_name,
            fill=config.COLOR_LABEL + (255,),
            font=font_title,
        )

    # ── String lines ───────────────────────────────────────
    line_width = max(int(height * 0.004), 1)
    # Strings drawn top=high e (string 5) to bottom=low E (string 0)
    string_row = {5: 0, 4: 1, 3: 2, 2: 3, 1: 4, 0: 5}  # string_idx -> row

    for row in range(6):
        y = grid_y + row * string_spacing
        draw.line(
            [(grid_x, y), (grid_x + grid_w, y)],
            fill=config.COLOR_STRING + (200,),
            width=max(line_width + (row // 2), 1),
        )

    # ── Bar lines on left and right ────────────────────────
    bar_width = max(int(width * 0.004), 2)
    draw.line([(grid_x, grid_y), (grid_x, grid_y + grid_h)],
              fill=config.COLOR_NUT + (255,), width=bar_width * 2)
    draw.line([(grid_x + grid_w, grid_y), (grid_x + grid_w, grid_y + grid_h)],
              fill=config.COLOR_FRET_WIRE + (150,), width=bar_width)

    # ── String name labels on left ──────────────────────────
    for si, row in string_row.items():
        y = grid_y + row * string_spacing
        name = TAB_STRING_NAMES[5 - si]  # high e first
        bbox = draw.textbbox((0, 0), name, font=font_label)
        nw = bbox[2] - bbox[0]
        nh = bbox[3] - bbox[1]
        draw.text(
            (grid_x - nw - int(width * 0.03), y - nh / 2),
            name,
            fill=config.COLOR_LABEL + (200,),
            font=font_label,
        )

    # ── Fret numbers at each string position ───────────────
    pad_x = int(note_size * 0.4)
    for si in range(6):
        row = string_row[si]
        y = grid_y + row * string_spacing
        f = frets[si]

        if f == -1:
            label = "x"
            color = config.COLOR_MUTED + (255,)
        else:
            label = str(f)
            is_highlighted = si in highlighted_strings
            color = config.GOLD_BRIGHT + (255,) if is_highlighted else config.CREAM + (255,)

        bbox = draw.textbbox((0, 0), label, font=font_note)
        nw = bbox[2] - bbox[0]
        nh = bbox[3] - bbox[1]

        # White background box to break the string line
        box_pad = int(note_size * 0.2)
        draw.rectangle(
            [col_x - nw / 2 - box_pad, y - nh / 2 - box_pad,
             col_x + nw / 2 + box_pad, y + nh / 2 + box_pad],
            fill=bg_color if bg_color else config.NAVY_DEEP,
        )
        draw.text(
            (col_x - nw / 2, y - nh / 2),
            label,
            fill=color,
            font=font_note,
        )

    # ── Watermark ──────────────────────────────────────────
    if show_watermark:
        img = _draw_watermark(draw, img, font_wm, width, height)

    return img


def render_scale_tab(
    notes_data,
    title="",
    bg_color=None,
    width=1600,
    height=420,
    show_watermark=True,
    ascending=True,
    descending=False,
    root_to_root=True,
    highlighted_idx=None,
    stop_at_high_e_root=False,
):
    """
    Render a scale or arpeggio as guitar tab notation (horizontal note sequence).

    Args:
        notes_data: list of dicts {string, fret, is_root, note_name, ...}
        title: display title (e.g., "A Pentatonic Minor")
        bg_color: (R,G,B) or None for transparent
        width, height: image dimensions
        show_watermark: include GembaGuitar.com watermark
        ascending: include ascending run
        descending: include descending run
        root_to_root: start and end on lowest root note
        highlighted_idx: index into the note sequence to highlight (for animation)

    Returns:
        PIL.Image.Image (RGBA)
    """
    if bg_color:
        img = Image.new("RGBA", (width, height), bg_color + (255,))
    else:
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Build note sequence (same logic as audio engine) ───
    all_midi = sorted(set(
        STANDARD_TUNING_MIDI[n["string"]] + n["fret"]
        for n in notes_data
    ))

    # Build a lookup: midi value -> (string, fret, is_root)
    # Prefer lower string index (thicker string) for same MIDI pitch
    midi_to_note = {}
    for n in sorted(notes_data, key=lambda x: x["string"]):
        m = STANDARD_TUNING_MIDI[n["string"]] + n["fret"]
        midi_to_note[m] = n

    if root_to_root and notes_data:
        root_midi_values = sorted(set(
            STANDARD_TUNING_MIDI[n["string"]] + n["fret"]
            for n in notes_data if n.get("is_root", False)
        ))
        start_midi = root_midi_values[0] if root_midi_values else all_midi[0]
        end_midi   = root_midi_values[-1] if root_midi_values else all_midi[-1]

        if stop_at_high_e_root:
            HIGH_E = 5
            high_e_root_midis = sorted(
                STANDARD_TUNING_MIDI[n["string"]] + n["fret"]
                for n in notes_data
                if n.get("is_root", False) and n["string"] == HIGH_E
            )
            if high_e_root_midis:
                end_midi = high_e_root_midis[0]

        asc_notes = [m for m in all_midi if start_midi <= m <= end_midi]
        if not asc_notes:
            asc_notes = all_midi
    else:
        start_midi = all_midi[0] if all_midi else 0
        asc_notes = all_midi

    sequence_midi = []
    if ascending:
        sequence_midi.extend(asc_notes)
    if descending:
        desc = list(reversed(asc_notes[:-1] if ascending else asc_notes))
        sequence_midi.extend(desc)
        if root_to_root and sequence_midi and sequence_midi[-1] != start_midi:
            sequence_midi.append(start_midi)

    if not sequence_midi:
        return img

    # ── Layout ─────────────────────────────────────────────
    margin_top = int(height * 0.22)
    margin_bottom = int(height * 0.12)
    margin_left = int(width * 0.06)
    margin_right = int(width * 0.03)

    grid_x = margin_left
    grid_y = margin_top
    grid_w = width - margin_left - margin_right
    grid_h = height - margin_top - margin_bottom

    string_spacing = grid_h / 5
    n_cols = len(sequence_midi)
    col_spacing = grid_w / max(n_cols, 1)

    # ── Fonts ──────────────────────────────────────────────
    title_size = int(height * 0.10)
    label_size = int(height * 0.058)
    note_size = max(int(min(col_spacing * 0.5, string_spacing * 0.5)), 8)
    wm_size = max(int(width * config.WATERMARK_FONT_SIZE_RATIO), 10)

    font_title = _load_font(config.FONT_DISPLAY, title_size)
    font_label = _load_font(config.FONT_BODY, label_size)
    font_note = _load_font(config.FONT_BODY_BOLD, note_size)
    font_wm = _load_font(config.FONT_BODY, wm_size)

    # ── Title ──────────────────────────────────────────────
    if title:
        bbox = draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(
            (width / 2 - tw / 2, int(height * 0.02)),
            title,
            fill=config.COLOR_LABEL + (255,),
            font=font_title,
        )

    # ── String lines (high e at top) ───────────────────────
    string_row = {5: 0, 4: 1, 3: 2, 2: 3, 1: 4, 0: 5}
    line_width = max(int(height * 0.004), 1)

    for si, row in string_row.items():
        y = grid_y + row * string_spacing
        draw.line(
            [(grid_x, y), (grid_x + grid_w, y)],
            fill=config.COLOR_STRING + (200,),
            width=max(line_width + (row // 2), 1),
        )

    # ── Bar lines ──────────────────────────────────────────
    bar_width = max(int(width * 0.002), 2)
    draw.line([(grid_x, grid_y), (grid_x, grid_y + grid_h)],
              fill=config.COLOR_NUT + (255,), width=bar_width * 2)
    draw.line([(grid_x + grid_w, grid_y), (grid_x + grid_w, grid_y + grid_h)],
              fill=config.COLOR_FRET_WIRE + (150,), width=bar_width)

    # ── String name labels on left ──────────────────────────
    for si, row in string_row.items():
        y = grid_y + row * string_spacing
        name = TAB_STRING_NAMES[5 - si]
        bbox = draw.textbbox((0, 0), name, font=font_label)
        nw = bbox[2] - bbox[0]
        nh = bbox[3] - bbox[1]
        draw.text(
            (grid_x - nw - int(width * 0.01), y - nh / 2),
            name,
            fill=config.COLOR_LABEL + (200,),
            font=font_label,
        )

    # ── Draw fret numbers for each note in sequence ────────
    bg_fill = bg_color if bg_color else config.NAVY_DEEP
    for col_idx, midi in enumerate(sequence_midi):
        note = midi_to_note.get(midi)
        if note is None:
            continue

        si = note["string"]
        fret = note["fret"]
        is_root = note.get("is_root", False)
        row = string_row[si]

        col_center_x = grid_x + (col_idx + 0.5) * col_spacing
        y = grid_y + row * string_spacing

        is_highlighted = (col_idx == highlighted_idx)
        if is_highlighted:
            color = config.GOLD_BRIGHT + (255,)
        elif is_root:
            color = config.GOLD + (255,)
        else:
            color = config.CREAM + (255,)

        label = str(fret)
        bbox = draw.textbbox((0, 0), label, font=font_note)
        nw = bbox[2] - bbox[0]
        nh = bbox[3] - bbox[1]

        # Clear the string line behind the number
        box_pad = max(int(note_size * 0.15), 2)
        draw.rectangle(
            [col_center_x - nw / 2 - box_pad, y - nh / 2 - box_pad,
             col_center_x + nw / 2 + box_pad, y + nh / 2 + box_pad],
            fill=bg_fill,
        )

        # Highlight background for current note
        if is_highlighted:
            draw.rectangle(
                [col_center_x - nw / 2 - box_pad * 2, y - nh / 2 - box_pad * 2,
                 col_center_x + nw / 2 + box_pad * 2, y + nh / 2 + box_pad * 2],
                fill=config.NAVY_LIGHT,
            )

        draw.text(
            (col_center_x - nw / 2, y - nh / 2),
            label,
            fill=color,
            font=font_note,
        )

    # ── Watermark ──────────────────────────────────────────
    if show_watermark:
        img = _draw_watermark(draw, img, font_wm, width, height)

    return img
