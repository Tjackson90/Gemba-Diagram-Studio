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


from diagrams.fonts import load_font as _load_font


def _build_strip(items,title,panel_getter,highlighted_idx=None,panel_w=380,panel_h=520,
    padding=24,title_height=80,label_height=56,bg_color=None):
    from diagrams.progression_diagram import compose_strip
    def render(item):
        notes,start,end,panel_title=panel_getter(item)
        return render_scale_box(notes,start,end,scale_name=panel_title,width=panel_w,height=panel_h,show_watermark=False)
    return compose_strip(items,title,render,panel_w,panel_h,padding,title_height,label_height,bg_color,highlighted_idx)


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


from services.documents import record_render
render_scale_progression_strip = record_render(render_scale_progression_strip)
render_arpeggio_progression_strip = record_render(render_arpeggio_progression_strip)
