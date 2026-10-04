"""
GembaGuitar Diagram Studio — Main GUI Application
"""

import json
import sys
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from PIL import Image, ImageDraw, ImageFont, ImageTk

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import customtkinter as ctk

import config
from data.chords import (
    CHORD_QUALITIES, CHORD_INTERVALS, get_voicings, get_chord_display_name,
    parse_chord_name,
)
from data.notes import ROOT_NAMES, SHARP_NAMES, note_name_to_semitone
from data.scales import (
    SCALE_NAMES, get_full_fretboard_scale, get_caged_positions,
    get_scale_display_name, get_scale_interval_labels,
    get_three_note_per_string_scale, get_three_nps_positions,
)
from data.arpeggios import (
    ARPEGGIO_NAMES, get_full_fretboard_arpeggio, get_arpeggio_positions,
    get_arpeggio_display_name, get_arpeggio_interval_labels,
)
from diagrams.chord_diagram import render_chord_diagram
from diagrams.scale_diagram import render_scale_full_fretboard, render_scale_box
from diagrams.export import export_diagram, batch_export
from diagrams.draw_utils import (
    apply_background_gradient, draw_fretboard_rect,
    draw_metallic_fret_h, draw_string_v,
    draw_inlay_dots_chord, draw_note_dot_3d,
    draw_string_circle, draw_decorative_border, draw_watermark_gold,
)
from diagrams.tab_diagram import render_chord_tab, render_scale_tab
from diagrams.video_export import (
    export_chord_video, export_scale_video, export_tab_video,
    export_progression_video, export_scale_arp_progression_video,
)
from audio.engine import (
    generate_chord_audio, generate_scale_audio, generate_progression_audio,
    play_audio, stop_audio, export_wav, export_mp3,
)
from data.progressions import (
    PROGRESSION_NAMES, MAJOR_PROGRESSIONS, MINOR_PROGRESSIONS,
    get_named_progression, get_progression_chords, parse_roman,
    get_progression_scales, get_progression_arpeggios,
)
from diagrams.progression_diagram import render_progression_strip, make_progression_title
from diagrams.scale_progression_diagram import (
    render_scale_progression_strip, render_arpeggio_progression_strip,
    make_scale_progression_title,
)
import data.custom_library as _custom_lib
from data.scales import SCALE_INTERVALS
from data.triads import (
    TRIAD_VOICING_NAMES, TRIAD_QUALITIES,
    get_diatonic_triads, get_diatonic_minor_triads,
    get_diatonic_harmonic_minor_triads, get_diatonic_melodic_minor_triads,
    get_triad_voicing,
)

# Combined progression list (major then minor) for the single Prog dropdown
ALL_PROG_NAMES = list(MAJOR_PROGRESSIONS.keys()) + list(MINOR_PROGRESSIONS.keys())


def _mode_for_prog(prog_name="", custom="", custom_mode="major"):
    """Auto-detect major/minor from progression name or custom roman string."""
    if custom:
        return custom_mode
    if prog_name in MAJOR_PROGRESSIONS:
        return "major"
    if prog_name in MINOR_PROGRESSIONS:
        return "minor"
    return "major"
from data.arpeggios import ARPEGGIO_INTERVALS

# ── Chord Identifier — module-level constants ──────────────────────
_CI_NOTES    = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
_CI_TUNING6  = [64, 59, 55, 50, 45, 40]   # strings 1-6 (high-e → low-E) MIDI
_CI_PATTERNS = [
    ("",        [0,4,7],    90), ("m",       [0,3,7],    90),
    ("dim",     [0,3,6],    88), ("aug",     [0,4,8],    88),
    ("sus2",    [0,2,7],    86), ("sus4",    [0,5,7],    86),
    ("5",       [0,7],      70), ("7",       [0,4,7,10], 95),
    ("maj7",    [0,4,7,11], 95), ("m7",      [0,3,7,10], 95),
    ("m(maj7)", [0,3,7,11], 93), ("m7b5",    [0,3,6,10], 93),
    ("dim7",    [0,3,6,9],  92), ("6",       [0,4,7,9],  92),
    ("m6",      [0,3,7,9],  92),
]
# Canvas layout constants (vertical mode)
_CI_PAD       = 18
_CI_LEFT_TEXT = 38
_CI_TOP_TEXT  = 70
_CI_GRID_W    = 210
_CI_GRID_H    = 248


from gui.workflows import WorkflowMixin
from gui.identifier import IdentifierMixin
from services.documents import CurrentDocument


class DiagramStudioApp(WorkflowMixin, IdentifierMixin, ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("GembaGuitar Diagram Studio")
        self.geometry("1280x900")
        self.minsize(960, 680)

        # Apply brand theming
        try:
            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
        except Exception:
            pass

        self.configure(bg=config.HEX_NAVY_DEEP)

        self._init_workflows()
        self.document = CurrentDocument()

        # Current state
        self._current_image = None
        self._current_audio = None
        self._current_name = ""
        self._current_frets = None
        self._current_fingers = None
        self._current_root_semitone = None
        self._current_scale_notes = None
        self._current_is_arpeggio = False   # True when _current_scale_notes is arpeggio data
        self._current_progression = None   # list of chord dicts
        self._current_prog_title = ""
        self._current_scale_prog_items = None   # list of scale-prog dicts
        self._current_arp_prog_items   = None   # list of arp-prog dicts

        # Batch export queue — list of snapshot dicts
        self._batch_queue = []

        # Chord Lookup state
        self._cl_root = "A"
        self._cl_qual = "Major"
        self._cl_photo_refs: list = []
        self._cl_key_btns: dict = {}
        self._cl_qual_btns: dict = {}

        # Chord Identifier state
        self._ci_fingers: list = []
        self._ci_open_muted: list = ["O"] * 6
        self._ci_strings: int = 6
        self._ci_frets_visible: int = 5
        self._ci_start_fret: int = 1
        self._ci_orientation: str = "v"

        # History & Favorites
        self._history = []           # list of snapshot dicts (newest first)
        self._MAX_HISTORY = 12
        self._favorites_file = config.DATA_DIR / "favorites.json"
        self._favorites = self._load_favorites()

        self._build_ui()

        # ── Keyboard shortcuts ─────────────────────────────
        self.bind_all("<Control-s>", lambda e: self._save_png_as())
        self.bind_all("<Control-S>", lambda e: self._save_png_as())
        # Space plays audio (only when focus is NOT in an entry widget)
        self.bind_all("<space>", self._on_space)
        self._start_workflows()

    def _build_ui(self):
        """Build the main UI layout."""
        # ── Header ─────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=config.HEX_NAVY_MID, height=70)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        # Left: title + subtitle
        hdr_left = ctk.CTkFrame(header, fg_color="transparent")
        hdr_left.pack(side="left", padx=20, fill="y")
        _display_font = ("Bebas Neue", 32) if os.path.exists(
            str(config.FONT_DIR / config.FONT_DISPLAY)
        ) else ("Arial", 26, "bold")
        ctk.CTkLabel(
            hdr_left, text="GembaGuitar Diagram Studio",
            font=_display_font, text_color=config.HEX_GOLD,
        ).pack(anchor="w", pady=(12, 0))
        ctk.CTkLabel(
            hdr_left, text="Professional Guitar Diagram & Audio Studio",
            font=("Arial", 10), text_color="#6a8ab8",
        ).pack(anchor="w")

        # Right: branding
        ctk.CTkLabel(
            header, text="GembaGuitar.com",
            font=("Arial", 11), text_color="#3a5a8f",
        ).pack(side="right", padx=20)

        # Gold accent line below header
        ctk.CTkFrame(self, fg_color=config.HEX_GOLD, height=2).pack(fill="x")

        # ── Main content: sidebar + preview ────────────────
        content = ctk.CTkFrame(self, fg_color=config.HEX_NAVY_DEEP, corner_radius=0)
        content.pack(fill="both", expand=True)

        # Sidebar (left) — scrollable
        self.sidebar = ctk.CTkScrollableFrame(
            content, width=315, fg_color=config.HEX_NAVY_DEEP, corner_radius=0,
            scrollbar_button_color=config.HEX_NAVY_LIGHT,
            scrollbar_button_hover_color=config.HEX_GOLD,
        )
        self.sidebar.pack(side="left", fill="y", padx=0, pady=0)

        # Thin vertical separator
        ctk.CTkFrame(content, width=1, fg_color=config.HEX_NAVY_LIGHT, corner_radius=0).pack(
            side="left", fill="y"
        )

        # Preview (right)
        self.preview_frame = ctk.CTkFrame(content, fg_color=config.HEX_NAVY_DEEP, corner_radius=0)
        self.preview_frame.pack(side="right", fill="both", expand=True)

        self.preview_label = ctk.CTkLabel(
            self.preview_frame, text="Select a chord or scale to preview",
            text_color="#3a5a8f", font=("Arial", 15),
        )
        self.preview_label.pack(expand=True)

        # Chord Lookup panel (hidden until ChordLookup mode is selected)
        self._build_chord_lookup_panel()

        # Chord Identifier panel (hidden until ChordID mode is selected)
        self._build_chord_identifier_panel()

        # ── Build sidebar controls ─────────────────────────
        self._build_sidebar()

        # ── Bottom bar (export controls) ───────────────────
        self._build_export_bar()

    def _build_sidebar(self):
        """Build sidebar with mode tabs and controls."""

        # ── Helper: styled section card ────────────────────
        def _card(parent, title=None, pady_bottom=6):
            outer = ctk.CTkFrame(parent, fg_color=config.HEX_NAVY_MID, corner_radius=8)
            outer.pack(fill="x", padx=8, pady=(0, pady_bottom))
            if title:
                ctk.CTkLabel(
                    outer, text=title, font=("Arial", 9, "bold"),
                    text_color=config.HEX_GOLD,
                ).pack(anchor="w", padx=10, pady=(7, 4))
            return outer

        # ── Helper: inline label + widget row ──────────────
        def _lrow(parent, label, lw=80):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", padx=8, pady=(0, 4))
            r.columnconfigure(0, minsize=lw)
            r.columnconfigure(1, weight=1)
            ctk.CTkLabel(
                r, text=label, text_color=config.HEX_CREAM,
                font=("Arial", 11), anchor="w", width=lw,
            ).grid(row=0, column=0, sticky="w")
            return r

        # ── Helper: styled option menu ──────────────────────
        _menu_kw = dict(
            fg_color=config.HEX_NAVY_DEEP, button_color=config.HEX_NAVY_LIGHT,
            button_hover_color=config.HEX_GOLD, dropdown_fg_color=config.HEX_NAVY_MID,
        )

        # ── Spacer ─────────────────────────────────────────
        ctk.CTkFrame(self.sidebar, height=8, fg_color="transparent").pack()

        # ── Mode selector card ─────────────────────────────
        mode_card = _card(self.sidebar)
        ctk.CTkLabel(
            mode_card, text="MODE", font=("Arial", 9, "bold"),
            text_color=config.HEX_GOLD,
        ).pack(anchor="w", padx=10, pady=(7, 4))

        self.mode_var = ctk.StringVar(value="Chord")

        # Row 1: Chord | Scale | Arpeggio
        mode_row1 = ctk.CTkFrame(mode_card, fg_color="transparent")
        mode_row1.pack(padx=8, pady=(0, 3), fill="x")
        mode_row1.columnconfigure(0, weight=1)
        mode_row1.columnconfigure(1, weight=1)
        mode_row1.columnconfigure(2, weight=1)

        self._mode_btn_chord = ctk.CTkButton(
            mode_row1, text="Chord", height=32, font=("Arial", 11),
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._set_mode("Chord"),
        )
        self._mode_btn_chord.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self._mode_btn_scale = ctk.CTkButton(
            mode_row1, text="Scale", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._set_mode("Scale"),
        )
        self._mode_btn_scale.grid(row=0, column=1, sticky="ew", padx=(0, 2))

        self._mode_btn_arp = ctk.CTkButton(
            mode_row1, text="Arpeggio", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._set_mode("Arpeggio"),
        )
        self._mode_btn_arp.grid(row=0, column=2, sticky="ew")

        # Row 2: Chord Prog | Scale Prog | Arp Prog
        mode_row2 = ctk.CTkFrame(mode_card, fg_color="transparent")
        mode_row2.pack(padx=8, pady=(0, 8), fill="x")
        mode_row2.columnconfigure(0, weight=1)
        mode_row2.columnconfigure(1, weight=1)
        mode_row2.columnconfigure(2, weight=1)

        self._mode_btn_prog = ctk.CTkButton(
            mode_row2, text="Chd Prog", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._set_mode("Progression"),
        )
        self._mode_btn_prog.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self._mode_btn_scale_prog = ctk.CTkButton(
            mode_row2, text="Scl Prog", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._set_mode("ScaleProg"),
        )
        self._mode_btn_scale_prog.grid(row=0, column=1, sticky="ew", padx=(0, 2))

        self._mode_btn_arp_prog = ctk.CTkButton(
            mode_row2, text="Arp Prog", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._set_mode("ArpProg"),
        )
        self._mode_btn_arp_prog.grid(row=0, column=2, sticky="ew")

        # Row 3: Chord Lookup | Chord ID | Custom Library
        mode_row3 = ctk.CTkFrame(mode_card, fg_color="transparent")
        mode_row3.pack(padx=8, pady=(0, 8), fill="x")
        mode_row3.columnconfigure(0, weight=1)
        mode_row3.columnconfigure(1, weight=1)
        mode_row3.columnconfigure(2, weight=1)

        self._mode_btn_lookup = ctk.CTkButton(
            mode_row3, text="Chord Lookup", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._set_mode("ChordLookup"),
        )
        self._mode_btn_lookup.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self._mode_btn_chord_id = ctk.CTkButton(
            mode_row3, text="Chord ID", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._set_mode("ChordID"),
        )
        self._mode_btn_chord_id.grid(row=0, column=1, sticky="ew", padx=(0, 2))

        self._mode_btn_custom = ctk.CTkButton(
            mode_row3, text="Custom", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._set_mode("Custom"),
        )
        self._mode_btn_custom.grid(row=0, column=2, sticky="ew")

        # Row 4: Triads
        mode_row4 = ctk.CTkFrame(mode_card, fg_color="transparent")
        mode_row4.pack(padx=8, pady=(0, 8), fill="x")
        mode_row4.columnconfigure(0, weight=1)

        self._mode_btn_triads = ctk.CTkButton(
            mode_row4, text="Triads", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._set_mode("Triads"),
        )
        self._mode_btn_triads.grid(row=0, column=0, sticky="ew")

        # ── Custom Library frame ───────────────────────────
        self.custom_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self._build_custom_panel(self.custom_frame)

        # ── Chord controls frame ───────────────────────────
        self.chord_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")

        # Quick Input card
        qi_card = _card(self.chord_frame, "QUICK INPUT")
        self.chord_input = ctk.CTkEntry(
            qi_card, placeholder_text="e.g. Am7, F#dim, Cmaj7",
            height=33, fg_color=config.HEX_NAVY_DEEP,
            text_color=config.HEX_CREAM, border_color=config.HEX_NAVY_LIGHT,
        )
        self.chord_input.pack(padx=8, fill="x", pady=(0, 4))
        self.chord_input.bind("<Return>", lambda e: self._quick_chord())
        ctk.CTkButton(
            qi_card, text="Generate", height=32,
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=self._quick_chord,
        ).pack(padx=8, fill="x", pady=(0, 8))

        # Select card
        sel_card = _card(self.chord_frame, "OR SELECT")
        self.root_var = ctk.StringVar(value="A")
        r = _lrow(sel_card, "Root:")
        ctk.CTkOptionMenu(r, variable=self.root_var, values=ROOT_NAMES,
                          **_menu_kw, command=lambda _: self._schedule_preview("Chord"),
                          ).grid(row=0, column=1, sticky="ew")

        self.quality_var = ctk.StringVar(value="Minor")
        r = _lrow(sel_card, "Quality:")
        ctk.CTkOptionMenu(r, variable=self.quality_var, values=CHORD_QUALITIES,
                          **_menu_kw, command=lambda _: self._schedule_preview("Chord"),
                          ).grid(row=0, column=1, sticky="ew")

        self.voicing_var = ctk.StringVar(value="1")
        r = _lrow(sel_card, "Voicing:")
        self.voicing_menu = ctk.CTkOptionMenu(r, variable=self.voicing_var, values=["1"],
                                              **_menu_kw, command=lambda _: self._schedule_preview("Chord"))
        self.voicing_menu.grid(row=0, column=1, sticky="ew")
        ctk.CTkFrame(sel_card, height=4, fg_color="transparent").pack()

        # Diagram options card
        diag_card = _card(self.chord_frame, "DIAGRAM OPTIONS")
        self.dot_label_var = ctk.StringVar(value="finger")
        r = _lrow(diag_card, "Dot label:")
        ctk.CTkOptionMenu(r, variable=self.dot_label_var, values=["note", "finger", "none"],
                          **_menu_kw, command=lambda _: self._schedule_preview("Chord"),
                          ).grid(row=0, column=1, sticky="ew")

        def _make_checkbox(parent, text, var):
            try:
                return ctk.CTkCheckBox(
                    parent, text=text, variable=var,
                    text_color=config.HEX_CREAM, font=("Arial", 11),
                    fg_color=config.HEX_GOLD, hover_color=config.HEX_GOLD_BRIGHT,
                    checkmark_color=config.HEX_NAVY_DEEP,
                    command=lambda: self._schedule_preview("Chord"),
                )
            except Exception:
                return None

        self.show_muted_x_var = ctk.BooleanVar(value=True)
        cb = _make_checkbox(diag_card, "Show X on muted strings", self.show_muted_x_var)
        if cb: cb.pack(padx=10, anchor="w", pady=1)

        self.show_open_o_var = ctk.BooleanVar(value=True)
        cb = _make_checkbox(diag_card, "Show O on open strings", self.show_open_o_var)
        if cb: cb.pack(padx=10, anchor="w", pady=1)

        self.show_string_names_var = ctk.BooleanVar(value=True)
        cb = _make_checkbox(diag_card, "Show string names (E A D G B e)", self.show_string_names_var)
        if cb: cb.pack(padx=10, anchor="w", pady=1)

        self.show_finger_numbers_var = ctk.BooleanVar(value=False)
        cb = _make_checkbox(diag_card, "Show finger numbers below", self.show_finger_numbers_var)
        if cb: cb.pack(padx=10, anchor="w", pady=1)

        self.show_barre_var = ctk.BooleanVar(value=True)
        cb = _make_checkbox(diag_card, "Show barre bar (same finger + fret)", self.show_barre_var)
        if cb: cb.pack(padx=10, anchor="w", pady=(1, 2))

        self.barre_style_var = ctk.StringVar(value="Arch")
        try:
            ctk.CTkSegmentedButton(
                diag_card, values=["Rectangle", "Arch"],
                variable=self.barre_style_var,
                fg_color=config.HEX_NAVY_DEEP, selected_color=config.HEX_GOLD,
                selected_hover_color=config.HEX_GOLD_BRIGHT,
                unselected_color=config.HEX_NAVY_LIGHT,
                text_color=config.HEX_CREAM,
                command=lambda _: self._schedule_preview("Chord"),
            ).pack(padx=10, fill="x", pady=(2, 8))
        except Exception:
            pass

        self.chord_frame.pack(fill="x")

        # ── Scale controls frame (hidden initially) ────────
        self.scale_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")

        scale_card = _card(self.scale_frame, "SCALE")
        self.scale_root_var = ctk.StringVar(value="A")
        r = _lrow(scale_card, "Root:")
        ctk.CTkOptionMenu(r, variable=self.scale_root_var, values=ROOT_NAMES,
                          **_menu_kw, command=lambda _: self._schedule_preview("Scale"),
                          ).grid(row=0, column=1, sticky="ew")

        self.scale_type_var = ctk.StringVar(value="Pentatonic Minor")
        r = _lrow(scale_card, "Scale:")
        self._scale_type_menu = ctk.CTkOptionMenu(
            r, variable=self.scale_type_var, values=SCALE_NAMES,
            **_menu_kw, command=lambda _: self._schedule_preview("Scale"),
        )
        self._scale_type_menu.grid(row=0, column=1, sticky="ew")

        self.scale_view_var = ctk.StringVar(value="Full Fretboard")
        r = _lrow(scale_card, "View:")
        ctk.CTkOptionMenu(
            r, variable=self.scale_view_var,
            values=["Full Fretboard",
                    "Position 1", "Position 2", "Position 3", "Position 4", "Position 5"],
            **_menu_kw, command=lambda _: self._schedule_preview("Scale"),
        ).grid(row=0, column=1, sticky="ew")

        self.invert_var = ctk.BooleanVar(value=True)
        try:
            ctk.CTkCheckBox(
                scale_card, text="Invert fretboard (low E at top)",
                variable=self.invert_var,
                text_color=config.HEX_CREAM, font=("Arial", 11),
                fg_color=config.HEX_GOLD, hover_color=config.HEX_GOLD_BRIGHT,
                checkmark_color=config.HEX_NAVY_DEEP,
                command=lambda: self._schedule_preview("Scale"),
            ).pack(padx=10, anchor="w", pady=(4, 8))
        except Exception:
            pass

        # ── Arpeggio controls frame (hidden initially) ─────
        self.arp_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")

        arp_card = _card(self.arp_frame, "ARPEGGIO")
        self.arp_root_var = ctk.StringVar(value="A")
        r = _lrow(arp_card, "Root:")
        ctk.CTkOptionMenu(r, variable=self.arp_root_var, values=ROOT_NAMES,
                          **_menu_kw, command=lambda _: self._schedule_preview("Arpeggio"),
                          ).grid(row=0, column=1, sticky="ew")

        self.arp_type_var = ctk.StringVar(value="Minor")
        r = _lrow(arp_card, "Type:")
        self._arp_type_menu = ctk.CTkOptionMenu(
            r, variable=self.arp_type_var, values=ARPEGGIO_NAMES,
            **_menu_kw, command=lambda _: self._schedule_preview("Arpeggio"),
        )
        self._arp_type_menu.grid(row=0, column=1, sticky="ew")

        self.arp_view_var = ctk.StringVar(value="Full Fretboard")
        r = _lrow(arp_card, "View:")
        ctk.CTkOptionMenu(
            r, variable=self.arp_view_var,
            values=["Full Fretboard", "Position 1", "Position 2", "Position 3", "Position 4"],
            **_menu_kw, command=lambda _: self._schedule_preview("Arpeggio"),
        ).grid(row=0, column=1, sticky="ew")
        ctk.CTkFrame(arp_card, height=8, fg_color="transparent").pack()

        # ── Progression controls frame (hidden initially) ──
        self.prog_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")

        prog_card = _card(self.prog_frame, "CHORD PROGRESSION")
        self.prog_root_var = ctk.StringVar(value="C")
        r = _lrow(prog_card, "Key Root:")
        ctk.CTkOptionMenu(r, variable=self.prog_root_var, values=ROOT_NAMES,
                          **_menu_kw, command=lambda _: self._schedule_preview("Progression"),
                          ).grid(row=0, column=1, sticky="ew")

        self.prog_quality_var = ctk.StringVar(value="Auto")
        r = _lrow(prog_card, "Quality:")
        ctk.CTkOptionMenu(
            r, variable=self.prog_quality_var,
            values=["Auto", "Major", "Minor", "Maj7", "Min7", "7",
                    "Dim", "Dim7", "Aug", "Sus2", "Sus4", "Add9", "Min7b5"],
            **_menu_kw, command=lambda _: self._schedule_preview("Progression"),
        ).grid(row=0, column=1, sticky="ew")

        self.prog_key_mode_var = ctk.StringVar(value='major')
        r = _lrow(prog_card, 'Custom key:')
        ctk.CTkOptionMenu(r, variable=self.prog_key_mode_var, values=['major','minor'],
                         **_menu_kw, command=lambda _: self._schedule_preview("Progression")).grid(row=0,column=1,sticky='ew')
        self.prog_name_var = ctk.StringVar(value=ALL_PROG_NAMES[0])
        r = _lrow(prog_card, "Prog:")
        self.prog_name_menu = ctk.CTkOptionMenu(
            r, variable=self.prog_name_var, values=ALL_PROG_NAMES,
            **_menu_kw, command=lambda _: self._schedule_preview("Progression"),
        )
        self.prog_name_menu.grid(row=0, column=1, sticky="ew")

        ctk.CTkLabel(prog_card, text="Custom (e.g. I-IV-V):",
                     text_color=config.HEX_CREAM, font=("Arial", 10)).pack(padx=10, anchor="w", pady=(4, 0))
        self.prog_custom_var = ctk.StringVar(value="")
        prog_entry = ctk.CTkEntry(
            prog_card, textvariable=self.prog_custom_var,
            placeholder_text="e.g. I-V-vi-IV",
            height=32, fg_color=config.HEX_NAVY_DEEP,
            text_color=config.HEX_CREAM, border_color=config.HEX_NAVY_LIGHT,
        )
        prog_entry.pack(padx=8, fill="x", pady=(0, 4))
        prog_entry.bind("<Return>", lambda e: self._update_progression())
        ctk.CTkButton(
            prog_card, text="Generate", height=32,
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._schedule_preview("Progression"),
        ).pack(padx=8, fill="x", pady=(0, 8))

        # Diagram options card
        diag2_card = _card(self.prog_frame, "DIAGRAM OPTIONS")
        self.prog_dot_label_var = ctk.StringVar(value="note")
        r = _lrow(diag2_card, "Dot label:")
        ctk.CTkOptionMenu(r, variable=self.prog_dot_label_var, values=["note", "finger", "none"],
                          **_menu_kw, command=lambda _: self._schedule_preview("Progression"),
                          ).grid(row=0, column=1, sticky="ew")

        def _prog_checkbox(parent, text, var):
            try:
                return ctk.CTkCheckBox(
                    parent, text=text, variable=var,
                    text_color=config.HEX_CREAM, font=("Arial", 11),
                    fg_color=config.HEX_GOLD, hover_color=config.HEX_GOLD_BRIGHT,
                    checkmark_color=config.HEX_NAVY_DEEP,
                    command=lambda: self._schedule_preview("Progression"),
                )
            except Exception:
                return None

        self.prog_show_barre_var = ctk.BooleanVar(value=True)
        cb = _prog_checkbox(diag2_card, "Show barre bar", self.prog_show_barre_var)
        if cb: cb.pack(padx=10, anchor="w", pady=(1, 2))

        self.prog_barre_style_var = ctk.StringVar(value="Rectangle")
        try:
            ctk.CTkSegmentedButton(
                diag2_card, values=["Rectangle", "Arch"],
                variable=self.prog_barre_style_var,
                fg_color=config.HEX_NAVY_DEEP, selected_color=config.HEX_GOLD,
                selected_hover_color=config.HEX_GOLD_BRIGHT,
                unselected_color=config.HEX_NAVY_LIGHT,
                text_color=config.HEX_CREAM,
                command=lambda _: self._schedule_preview("Progression"),
            ).pack(padx=10, fill="x", pady=(2, 4))
        except Exception:
            pass

        self.prog_show_string_names_var = ctk.BooleanVar(value=True)
        cb = _prog_checkbox(diag2_card, "Show string names", self.prog_show_string_names_var)
        if cb: cb.pack(padx=10, anchor="w", pady=1)

        self.prog_show_finger_numbers_var = ctk.BooleanVar(value=True)
        cb = _prog_checkbox(diag2_card, "Show finger numbers", self.prog_show_finger_numbers_var)
        if cb: cb.pack(padx=10, anchor="w", pady=(1, 8))

        # Playback card
        pb_card = _card(self.prog_frame, "PLAYBACK")
        ctk.CTkLabel(pb_card, text="Chord Duration (s):",
                     text_color=config.HEX_CREAM, font=("Arial", 11)).pack(padx=10, anchor="w")
        self.prog_duration_var = ctk.DoubleVar(value=2.0)
        ctk.CTkSlider(
            pb_card, variable=self.prog_duration_var,
            from_=0.5, to=4.0, number_of_steps=14,
            button_color=config.HEX_GOLD,
            button_hover_color=config.HEX_GOLD_BRIGHT,
            progress_color=config.HEX_GOLD,
        ).pack(padx=10, fill="x", pady=(0, 6))

        ctk.CTkLabel(pb_card, text="Playback Direction:",
                     text_color=config.HEX_GOLD, font=("Arial", 10, "bold"),
        ).pack(padx=10, anchor="w", pady=(4, 0))
        self._prog_dir_frame = ctk.CTkFrame(pb_card, fg_color="transparent")
        self._prog_dir_frame.pack(padx=10, fill="x", pady=(0, 8))
        self._prog_dir_vars = []

        # ── Scale Progression panel ────────────────────────
        self.scale_prog_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self._build_scale_arp_prog_panel(
            self.scale_prog_frame, "scale_prog",
            "Scale Progression",
            lambda _: self._update_scale_prog(),
        )

        # ── Arpeggio Progression panel ─────────────────────
        self.arp_prog_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self._build_scale_arp_prog_panel(
            self.arp_prog_frame, "arp_prog",
            "Arpeggio Progression",
            lambda _: self._update_arp_prog(),
        )

        # ── Triads panel ───────────────────────────────────
        self.triads_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self._build_triads_panel()

        # ── Chord Lookup sidebar (minimal — content lives in preview area) ──
        self.chord_lookup_sidebar_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        _card_cl = _card(self.chord_lookup_sidebar_frame)
        ctk.CTkLabel(
            _card_cl, text="CHORD LOOKUP",
            font=("Arial", 9, "bold"), text_color=config.HEX_GOLD,
        ).pack(anchor="w", padx=10, pady=(7, 2))
        ctk.CTkLabel(
            _card_cl,
            text="Browse all 12 keys with\nmultiple voicings per chord.",
            font=("Arial", 10), text_color=config.HEX_CREAM,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        # ── Chord Identifier sidebar ────────────────────────
        self.ci_sidebar_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        _card_ci = _card(self.ci_sidebar_frame, "CHORD IDENTIFIER")
        ctk.CTkLabel(
            _card_ci,
            text="Click the fretboard to place\nfingers and identify chords.",
            font=("Arial", 10), text_color=config.HEX_CREAM, justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 4))

        # Structure sub-card
        struct_ci = _card(self.ci_sidebar_frame, "STRUCTURE")

        r = _lrow(struct_ci, "Title:")
        self._ci_title_var = ctk.StringVar(value="")
        _ci_title_entry = ctk.CTkEntry(
            r, textvariable=self._ci_title_var, height=28,
            fg_color=config.HEX_NAVY_DEEP, text_color=config.HEX_CREAM,
            border_color=config.HEX_NAVY_LIGHT,
        )
        _ci_title_entry.grid(row=0, column=1, sticky="ew")
        self._ci_title_var.trace_add("write", lambda *_: self._ci_render())

        nums_row = ctk.CTkFrame(struct_ci, fg_color="transparent")
        nums_row.pack(fill="x", padx=8, pady=(0, 4))
        for c in range(3): nums_row.columnconfigure(c, weight=1)

        ctk.CTkLabel(nums_row, text="Start\nfret", font=("Arial", 9),
                     text_color=config.HEX_CREAM).grid(row=0, column=0)
        ctk.CTkLabel(nums_row, text="Frets", font=("Arial", 9),
                     text_color=config.HEX_CREAM).grid(row=0, column=1)
        ctk.CTkLabel(nums_row, text="Strings", font=("Arial", 9),
                     text_color=config.HEX_CREAM).grid(row=0, column=2)

        self._ci_start_fret_var = ctk.StringVar(value="1")
        self._ci_frets_var      = ctk.StringVar(value="5")
        self._ci_strings_var    = ctk.StringVar(value="6")

        for col, var in enumerate([self._ci_start_fret_var, self._ci_frets_var, self._ci_strings_var]):
            e = ctk.CTkEntry(nums_row, textvariable=var, width=48, height=28,
                             fg_color=config.HEX_NAVY_DEEP, text_color=config.HEX_CREAM,
                             border_color=config.HEX_NAVY_LIGHT)
            e.grid(row=1, column=col, padx=2, pady=(2, 0))
            var.trace_add("write", lambda *_: self._ci_update_from_vars())

        def _ci_cb(parent, text, var, cmd):
            try:
                return ctk.CTkCheckBox(
                    parent, text=text, variable=var,
                    text_color=config.HEX_CREAM, font=("Arial", 11),
                    fg_color=config.HEX_GOLD, hover_color=config.HEX_GOLD_BRIGHT,
                    checkmark_color=config.HEX_NAVY_DEEP, command=cmd,
                )
            except Exception:
                return None

        self._ci_hide_pos_var     = ctk.BooleanVar(value=False)
        self._ci_show_markers_var = ctk.BooleanVar(value=True)
        self._ci_show_names_var   = ctk.BooleanVar(value=True)

        for text, var in [
            ("Hide position label",    self._ci_hide_pos_var),
            ("Show fret markers",      self._ci_show_markers_var),
            ("Show string names",      self._ci_show_names_var),
        ]:
            cb = _ci_cb(struct_ci, text, var, self._ci_render)
            if cb: cb.pack(padx=10, anchor="w", pady=1)
        ctk.CTkFrame(struct_ci, height=6, fg_color="transparent").pack()

        # Action buttons
        act_ci = _card(self.ci_sidebar_frame)
        act_row = ctk.CTkFrame(act_ci, fg_color="transparent")
        act_row.pack(padx=8, pady=8, fill="x")
        act_row.columnconfigure(0, weight=1)
        act_row.columnconfigure(1, weight=1)

        ctk.CTkButton(
            act_row, text="Clear", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, command=self._ci_clear,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        ctk.CTkButton(
            act_row, text="Reset", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, command=self._ci_reset,
        ).grid(row=0, column=1, sticky="ew")

        # Export sub-card
        exp_ci = _card(self.ci_sidebar_frame, "EXPORT")

        _ci_menu_kw = dict(
            fg_color=config.HEX_NAVY_DEEP, button_color=config.HEX_NAVY_LIGHT,
            button_hover_color=config.HEX_GOLD, dropdown_fg_color=config.HEX_NAVY_MID,
            text_color=config.HEX_CREAM, dropdown_text_color=config.HEX_CREAM,
        )

        res_row = ctk.CTkFrame(exp_ci, fg_color="transparent")
        res_row.pack(padx=8, fill="x", pady=(0, 4))
        ctk.CTkLabel(res_row, text="Res:", text_color=config.HEX_CREAM,
                     font=("Arial", 11)).pack(side="left", padx=(0, 4))
        self._ci_res_var = ctk.StringVar(value="1080p")
        ctk.CTkOptionMenu(
            res_row, variable=self._ci_res_var,
            values=list(config.RESOLUTIONS.keys()), height=28,
            **_ci_menu_kw,
        ).pack(side="left", fill="x", expand=True)

        bg_row = ctk.CTkFrame(exp_ci, fg_color="transparent")
        bg_row.pack(padx=8, fill="x", pady=(0, 6))
        ctk.CTkLabel(bg_row, text="BG:", text_color=config.HEX_CREAM,
                     font=("Arial", 11)).pack(side="left", padx=(0, 4))
        self._ci_bg_var = ctk.StringVar(value="transparent")
        ctk.CTkOptionMenu(
            bg_row, variable=self._ci_bg_var, values=["transparent", "navy"],
            height=28, **_ci_menu_kw,
        ).pack(side="left", fill="x", expand=True)

        btn_row = ctk.CTkFrame(exp_ci, fg_color="transparent")
        btn_row.pack(padx=8, fill="x", pady=(0, 8))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        ctk.CTkButton(
            btn_row, text="Save PNG…", height=32, font=("Arial", 11, "bold"),
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=self._ci_save_png_as,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            btn_row, text="All Sizes", height=32, font=("Arial", 11),
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD,
            command=self._ci_export_all,
        ).grid(row=0, column=1, sticky="ew")

        # ── Audio controls card (shared) ───────────────────
        audio_card = _card(self.sidebar, "AUDIO")
        self.tone_var = ctk.StringVar(value="Nylon")
        r = _lrow(audio_card, "Tone:")
        ctk.CTkOptionMenu(r, variable=self.tone_var,
                          values=["Acoustic", "Nylon", "Harp",
                                  "Clean", "Electric", "Jazz",
                                  "Piano", "E. Piano", "Organ",
                                  "Bell", "Pad"],
                          **_menu_kw).grid(row=0, column=1, sticky="ew")

        self.tempo_var = ctk.StringVar(value="100")
        r = _lrow(audio_card, "Tempo:")
        ctk.CTkOptionMenu(r, variable=self.tempo_var,
                          values=["60", "80", "100", "120", "140", "160"],
                          **_menu_kw).grid(row=0, column=1, sticky="ew")

        self.play_style_var = ctk.StringVar(value="Arpeggiate + Strum")
        r = _lrow(audio_card, "Style:")
        ctk.CTkOptionMenu(r, variable=self.play_style_var,
                          values=["Strum Down", "Strum Up", "Arpeggiate", "Arpeggiate + Strum"],
                          **_menu_kw).grid(row=0, column=1, sticky="ew")
        self.strum_var = self.play_style_var  # compatibility shim

        ctk.CTkLabel(audio_card, text="Volume:", text_color=config.HEX_CREAM,
                     font=("Arial", 11)).pack(padx=10, anchor="w", pady=(4, 0))
        self.volume_var = ctk.DoubleVar(value=0.8)
        ctk.CTkSlider(
            audio_card, variable=self.volume_var,
            from_=0.1, to=1.0, number_of_steps=18,
            button_color=config.HEX_GOLD,
            button_hover_color=config.HEX_GOLD_BRIGHT,
            progress_color=config.HEX_GOLD,
        ).pack(padx=10, fill="x", pady=(0, 8))

        # Play / Stop
        pb_row = ctk.CTkFrame(audio_card, fg_color="transparent")
        pb_row.pack(padx=8, fill="x", pady=(0, 4))
        pb_row.columnconfigure(0, weight=1)
        pb_row.columnconfigure(1, weight=1)
        self.play_btn = ctk.CTkButton(
            pb_row, text="▶  Play", height=34,
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT, font=("Arial", 12, "bold"),
            command=self._play_audio,
        )
        self.play_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(
            pb_row, text="■  Stop", height=34,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color="#8b2222", font=("Arial", 12),
            command=self._stop_audio,
        ).grid(row=0, column=1, sticky="ew")

        # Export audio
        ea_row = ctk.CTkFrame(audio_card, fg_color="transparent")
        ea_row.pack(padx=8, fill="x", pady=(0, 8))
        ea_row.columnconfigure(0, weight=1)
        ea_row.columnconfigure(1, weight=1)
        ctk.CTkButton(
            ea_row, text="Export WAV", height=30,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, font=("Arial", 11),
            command=lambda: self._export_audio("wav"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(
            ea_row, text="Export MP3", height=30,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, font=("Arial", 11),
            command=lambda: self._export_audio("mp3"),
        ).grid(row=0, column=1, sticky="ew")

        # ── Tone shaping card ───────────────────────────────
        tone_card = _card(self.sidebar, "TONE SHAPING")

        self.tone_attack_var     = ctk.DoubleVar(value=0.3)
        self.tone_decay_var      = ctk.DoubleVar(value=0.5)
        self.tone_brightness_var = ctk.DoubleVar(value=0.5)
        self.tone_warmth_var     = ctk.DoubleVar(value=0.3)
        self.tone_harmonics_var  = ctk.DoubleVar(value=0.5)
        self.tone_body_var       = ctk.DoubleVar(value=0.5)
        self.tone_reverb_var     = ctk.DoubleVar(value=0.4)

        def _tone_slider(label, var):
            hdr = ctk.CTkFrame(tone_card, fg_color="transparent")
            hdr.pack(fill="x", padx=10, pady=(4, 0))
            ctk.CTkLabel(hdr, text=label, text_color=config.HEX_CREAM,
                         font=("Arial", 11)).pack(side="left")
            val_lbl = ctk.CTkLabel(hdr, text=f"{var.get():.2f}",
                                   text_color=config.HEX_GOLD,
                                   font=("Arial", 11), width=36)
            val_lbl.pack(side="right")

            def _on_change(v, lbl=val_lbl):
                lbl.configure(text=f"{float(v):.2f}")
                self._apply_tone_settings()

            ctk.CTkSlider(
                tone_card, variable=var,
                from_=0.0, to=1.0, number_of_steps=20,
                button_color=config.HEX_GOLD,
                button_hover_color=config.HEX_GOLD_BRIGHT,
                progress_color=config.HEX_GOLD,
                command=_on_change,
            ).pack(padx=10, fill="x", pady=(0, 2))

        _tone_slider("Attack",     self.tone_attack_var)
        _tone_slider("Decay",      self.tone_decay_var)
        _tone_slider("Brightness", self.tone_brightness_var)
        _tone_slider("Warmth",     self.tone_warmth_var)
        _tone_slider("Harmonics",  self.tone_harmonics_var)
        _tone_slider("Body",       self.tone_body_var)
        _tone_slider("Reverb",     self.tone_reverb_var)

        def _reset_tone():
            self.tone_attack_var.set(0.3)
            self.tone_decay_var.set(0.5)
            self.tone_brightness_var.set(0.5)
            self.tone_warmth_var.set(0.3)
            self.tone_harmonics_var.set(0.5)
            self.tone_body_var.set(0.5)
            self.tone_reverb_var.set(0.4)
            self._apply_tone_settings()

        ctk.CTkButton(
            tone_card, text="Reset to Defaults", height=28,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, font=("Arial", 11),
            command=_reset_tone,
        ).pack(padx=10, fill="x", pady=(6, 2))
        ctk.CTkFrame(tone_card, height=4, fg_color="transparent").pack()

        # ── Library card (Favorites + Recent) ──────────────
        lib_card = _card(self.sidebar, pady_bottom=10)

        # Favorites section
        fav_hdr = ctk.CTkFrame(lib_card, fg_color="transparent")
        fav_hdr.pack(fill="x", padx=10, pady=(7, 2))
        ctk.CTkLabel(fav_hdr, text="FAVORITES", font=("Arial", 9, "bold"),
                     text_color=config.HEX_GOLD).pack(side="left")
        ctk.CTkButton(
            fav_hdr, text="★ Save", width=65, height=22,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, font=("Arial", 10),
            command=self._add_favorite,
        ).pack(side="right")
        self._fav_list_frame = ctk.CTkFrame(lib_card, fg_color="transparent")
        self._fav_list_frame.pack(fill="x", padx=8, pady=(0, 4))
        self._refresh_favorites_panel()

        # Divider
        ctk.CTkFrame(lib_card, height=1, fg_color=config.HEX_NAVY_LIGHT).pack(
            fill="x", padx=10, pady=(2, 4)
        )

        # Recent section
        ctk.CTkLabel(lib_card, text="RECENT", font=("Arial", 9, "bold"),
                     text_color=config.HEX_GOLD).pack(anchor="w", padx=10, pady=(0, 2))
        self._history_list_frame = ctk.CTkFrame(lib_card, fg_color="transparent")
        self._history_list_frame.pack(fill="x", padx=8, pady=(0, 8))
        self._refresh_history_panel()

    def _build_export_bar(self):
        """Build the bottom export panel."""
        # Gold top border
        ctk.CTkFrame(self, fg_color=config.HEX_NAVY_LIGHT, height=1).pack(fill="x", side="bottom")

        bar = ctk.CTkFrame(self, fg_color=config.HEX_NAVY_MID, height=140)
        bar.pack(fill="x", padx=0, pady=0, side="bottom")
        bar.pack_propagate(False)

        _menu_kw = dict(
            fg_color=config.HEX_NAVY_DEEP, button_color=config.HEX_NAVY_LIGHT,
            button_hover_color=config.HEX_GOLD, dropdown_fg_color=config.HEX_NAVY_MID,
        )

        # ── Top row: label + status ─────────────────────────
        top_row = ctk.CTkFrame(bar, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(8, 2))

        ctk.CTkLabel(
            top_row, text="EXPORT",
            font=("Arial", 10, "bold"), text_color=config.HEX_GOLD,
        ).pack(side="left")

        self.status_label = ctk.CTkLabel(
            top_row, text="", text_color=config.HEX_CREAM, font=("Arial", 11),
        )
        self.status_label.pack(side="left", padx=(14, 0))

        self._progress_bar = ctk.CTkProgressBar(
            top_row, width=160, height=12,
            progress_color=config.HEX_GOLD,
            fg_color=config.HEX_NAVY_LIGHT,
        )
        # Not packed yet — shown only during long operations

        # ── Controls row ────────────────────────────────────
        ctrl_row = ctk.CTkFrame(bar, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=16, pady=(2, 8))

        # Resolution
        ctk.CTkLabel(ctrl_row, text="Res:", text_color=config.HEX_CREAM,
                     font=("Arial", 11)).pack(side="left", padx=(0, 3))
        self.res_var = ctk.StringVar(value="1080p")
        ctk.CTkOptionMenu(
            ctrl_row, variable=self.res_var,
            values=list(config.RESOLUTIONS.keys()), width=88, height=30,
            **_menu_kw,
        ).pack(side="left", padx=(0, 10))

        # Background
        ctk.CTkLabel(ctrl_row, text="BG:", text_color=config.HEX_CREAM,
                     font=("Arial", 11)).pack(side="left", padx=(0, 3))
        self.bg_var = ctk.StringVar(value="transparent")
        ctk.CTkOptionMenu(
            ctrl_row, variable=self.bg_var, values=["transparent", "navy"],
            width=100, height=30, **_menu_kw,
        ).pack(side="left", padx=(0, 10))

        # Custom size
        ctk.CTkLabel(ctrl_row, text="W×H:", text_color=config.HEX_CREAM,
                     font=("Arial", 11)).pack(side="left", padx=(0, 3))
        self.custom_w_var = ctk.StringVar(value="")
        ctk.CTkEntry(ctrl_row, textvariable=self.custom_w_var, width=54, height=30,
                     placeholder_text="w", fg_color=config.HEX_NAVY_DEEP,
                     text_color=config.HEX_CREAM, border_color=config.HEX_NAVY_LIGHT,
                     ).pack(side="left", padx=(0, 2))
        ctk.CTkLabel(ctrl_row, text="×", text_color="#6a8ab8",
                     font=("Arial", 11)).pack(side="left", padx=(0, 2))
        self.custom_h_var = ctk.StringVar(value="")
        ctk.CTkEntry(ctrl_row, textvariable=self.custom_h_var, width=54, height=30,
                     placeholder_text="h", fg_color=config.HEX_NAVY_DEEP,
                     text_color=config.HEX_CREAM, border_color=config.HEX_NAVY_LIGHT,
                     ).pack(side="left", padx=(0, 14))

        # Divider
        ctk.CTkFrame(ctrl_row, width=1, height=28, fg_color=config.HEX_NAVY_LIGHT
                     ).pack(side="left", padx=(0, 14))

        # Save PNG As
        ctk.CTkButton(
            ctrl_row, text="Save PNG…", width=100, height=32,
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT, font=("Arial", 11, "bold"),
            command=self._save_png_as,
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            ctrl_row, text="All Sizes", width=80, height=32,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, font=("Arial", 11),
            command=self._export_all,
        ).pack(side="left", padx=(0, 14))

        # Divider
        ctk.CTkFrame(ctrl_row, width=1, height=28, fg_color=config.HEX_NAVY_LIGHT
                     ).pack(side="left", padx=(0, 14))

        ctk.CTkButton(
            ctrl_row, text="Preview Tab", width=95, height=32,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, font=("Arial", 11),
            command=self._preview_tab,
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            ctrl_row, text="Save Tab…", width=90, height=32,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, font=("Arial", 11),
            command=self._save_tab_as,
        ).pack(side="left", padx=(0, 14))

        # Divider
        ctk.CTkFrame(ctrl_row, width=1, height=28, fg_color=config.HEX_NAVY_LIGHT
                     ).pack(side="left", padx=(0, 14))

        ctrl_row = ctk.CTkFrame(bar, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkButton(
            ctrl_row, text="Save Video…", width=100, height=32,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, font=("Arial", 11),
            command=self._save_video_as,
        ).pack(side="left", padx=(0, 5))

        # Video format toggles (9:16 portrait and with-tab combined frame)
        self.video_portrait_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            ctrl_row, text="9:16", variable=self.video_portrait_var,
            width=55, height=28, checkbox_width=16, checkbox_height=16,
            font=("Arial", 11),
            text_color=config.HEX_CREAM, fg_color=config.HEX_GOLD,
            hover_color=config.HEX_GOLD,
        ).pack(side="left", padx=(2, 4))

        self.video_with_tab_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            ctrl_row, text="+ Tab", variable=self.video_with_tab_var,
            width=65, height=28, checkbox_width=16, checkbox_height=16,
            font=("Arial", 11),
            text_color=config.HEX_CREAM, fg_color=config.HEX_GOLD,
            hover_color=config.HEX_GOLD,
        ).pack(side="left", padx=(0, 5))

        # Divider before batch controls
        ctk.CTkFrame(ctrl_row, width=1, height=28, fg_color=config.HEX_NAVY_LIGHT
                     ).pack(side="left", padx=(4, 8))

        ctk.CTkButton(
            ctrl_row, text="+ Queue", width=80, height=32,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, font=("Arial", 11),
            command=self._add_to_batch_queue,
        ).pack(side="left", padx=(0, 4))

        self._batch_export_btn = ctk.CTkButton(
            ctrl_row, text="Export Queue (0)", width=130, height=32,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color=config.HEX_GOLD, font=("Arial", 11),
            command=self._export_batch_queue,
        )
        self._batch_export_btn.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            ctrl_row, text="Clear", width=55, height=32,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color="#8B0000", font=("Arial", 11),
            command=self._clear_batch_queue,
        ).pack(side="left", padx=(0, 5))

    # ── Mode Switching ─────────────────────────────────────

    def _set_mode(self, mode):
        self.mode_var.set(mode)
        self.document = CurrentDocument()
        self._current_image = None

        # Update mode button highlight colours
        for btn, name in (
            (self._mode_btn_chord,      "Chord"),
            (self._mode_btn_scale,      "Scale"),
            (self._mode_btn_arp,        "Arpeggio"),
            (self._mode_btn_prog,       "Progression"),
            (self._mode_btn_scale_prog, "ScaleProg"),
            (self._mode_btn_arp_prog,   "ArpProg"),
            (self._mode_btn_lookup,     "ChordLookup"),
            (self._mode_btn_chord_id,   "ChordID"),
            (self._mode_btn_custom,     "Custom"),
            (self._mode_btn_triads,     "Triads"),
        ):
            if name == mode:
                btn.configure(fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP)
            else:
                btn.configure(fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM)

        self.chord_frame.pack_forget()
        self.scale_frame.pack_forget()
        self.arp_frame.pack_forget()
        self.prog_frame.pack_forget()
        self.scale_prog_frame.pack_forget()
        self.arp_prog_frame.pack_forget()
        self.chord_lookup_sidebar_frame.pack_forget()
        self.ci_sidebar_frame.pack_forget()
        self.custom_frame.pack_forget()
        self.triads_frame.pack_forget()

        # Show/hide specialty panels vs normal preview label
        if mode == "ChordLookup":
            self.preview_label.pack_forget()
            self.ci_panel.pack_forget()
            self.chord_lookup_panel.pack(fill="both", expand=True)
        elif mode == "ChordID":
            self.preview_label.pack_forget()
            self.chord_lookup_panel.pack_forget()
            self.ci_panel.pack(fill="both", expand=True)
        else:
            self.chord_lookup_panel.pack_forget()
            self.ci_panel.pack_forget()
            self.preview_label.pack(expand=True)

        if mode == "Chord":
            self.chord_frame.pack(fill="x")
            self._update_chord()
        elif mode == "Scale":
            self.scale_frame.pack(fill="x")
            self._update_scale()
        elif mode == "Arpeggio":
            self.arp_frame.pack(fill="x")
            self._update_arpeggio()
        elif mode == "Progression":
            self.prog_frame.pack(fill="x")
            self._update_progression()
        elif mode == "ScaleProg":
            self.scale_prog_frame.pack(fill="x")
            self._update_scale_prog()
        elif mode == "ChordLookup":
            self.chord_lookup_sidebar_frame.pack(fill="x")
            self._cl_refresh_all()
        elif mode == "ChordID":
            self.ci_sidebar_frame.pack(fill="x")
            self._ci_render()
        elif mode == "Custom":
            self.custom_frame.pack(fill="x")
            self._refresh_custom_lists()
        elif mode == "Triads":
            self.triads_frame.pack(fill="x")
            self._update_triads()
        else:  # ArpProg
            self.arp_prog_frame.pack(fill="x")
            self._update_arp_prog()

    # ── Chord Generation ───────────────────────────────────

    def _quick_chord(self):
        """Handle quick chord input (e.g., 'Am7')."""
        text = self.chord_input.get().strip()
        if not text:
            return

        root, quality = parse_chord_name(text)
        if root is None:
            self._set_status(f"Could not parse '{text}' — try e.g. Am7, F#dim")
            return

        # Update dropdowns
        # Find matching root in ROOT_NAMES
        for rn in ROOT_NAMES:
            if rn == root or rn.startswith(root + "/") or rn.endswith("/" + root):
                self.root_var.set(rn)
                break
        self.quality_var.set(quality)
        self._update_chord()

    def _custom_size(self, default_w, default_h):
        return default_w, default_h


    def _update_chord(self):
        """Regenerate chord diagram from current selections."""
        try:
            self._update_chord_inner()
        except Exception as e:
            self._set_status(f"Error generating chord: {e}")

    def _update_chord_inner(self):
        self.document = CurrentDocument()
        self._current_image = None
        """Internal chord update logic."""
        root = self.root_var.get()
        quality = self.quality_var.get()

        # Get root name (first part of enharmonic)
        root_name = root.split("/")[0] if "/" in root else root

        voicings = get_voicings(root_name, quality)
        if not voicings:
            self._set_status(f"No voicings found for {root_name} {quality}")
            return

        # Update voicing dropdown
        voicing_labels = [f"{i+1}: {v['label']}" for i, v in enumerate(voicings)]
        self.voicing_menu.configure(values=voicing_labels)
        current = self.voicing_var.get()
        try:
            current_idx = int(current[0])
        except (ValueError, IndexError):
            current_idx = 0
        if current_idx < 1 or current_idx > len(voicings):
            self.voicing_var.set(voicing_labels[0])

        # Get selected voicing index
        try:
            idx = int(self.voicing_var.get()[0]) - 1
        except (ValueError, IndexError):
            idx = 0
        idx = max(0, min(idx, len(voicings) - 1))

        v = voicings[idx]
        chord_name = get_chord_display_name(root_name, quality)
        root_semi = note_name_to_semitone(root_name)

        # Store state for audio/export
        self._current_frets = v["frets"]
        self._current_fingers = v.get("fingers")
        self._current_root_semitone = root_semi
        self._current_name = chord_name
        self._current_scale_notes = None
        self._current_is_arpeggio = False
        self._current_progression = None

        # Render diagram
        w, h = self._custom_size(600, 800)
        img = render_chord_diagram(
            frets=v["frets"],
            fingers=v.get("fingers"),
            chord_name=chord_name,
            root_semitone=root_semi,
            bg_color=None,
            width=w,
            height=h,
            dot_label=getattr(self, "dot_label_var", None) and self.dot_label_var.get() or "note",
            show_muted_x=getattr(self, "show_muted_x_var", None) is None or self.show_muted_x_var.get(),
            show_open_o=getattr(self, "show_open_o_var", None) is None or self.show_open_o_var.get(),
            show_string_names=getattr(self, "show_string_names_var", None) is None or self.show_string_names_var.get(),
            show_finger_numbers=getattr(self, "show_finger_numbers_var", None) is None or self.show_finger_numbers_var.get(),
            show_barre=getattr(self, "show_barre_var", None) is None or self.show_barre_var.get(),
            barre_style="arch" if getattr(self, "barre_style_var", None) and self.barre_style_var.get() == "Arch" else "rect",
        )

        self._current_image = img
        self._show_preview(img)
        self._set_status(f"{chord_name} — {v['label']}")
        self._record_history(self._snapshot())

    # ── Scale Generation ───────────────────────────────────

    def _update_scale(self):
        """Regenerate scale diagram from current selections."""
        try:
            self._update_scale_inner()
        except Exception as e:
            self._set_status(f"Error generating scale: {e}")

    def _update_scale_inner(self):
        self.document = CurrentDocument()
        self._current_image = None
        self._current_is_arpeggio = False
        root = self.scale_root_var.get()
        root_name = root.split("/")[0] if "/" in root else root
        scale_name = self.scale_type_var.get()
        view = self.scale_view_var.get()
        root_semi = note_name_to_semitone(root_name)

        display_name = get_scale_display_name(root_name, scale_name)
        self._current_name = display_name.replace(" ", "_")

        if view == "Full Fretboard":
            notes = get_full_fretboard_scale(root_name, scale_name, num_frets=15)
            self._current_scale_notes = notes
            self._current_frets = None

            invert = getattr(self, "invert_var", None)
            fw, fh = self._custom_size(1600, 500)
            img = render_scale_full_fretboard(
                scale_notes=notes,
                scale_name=scale_name,
                root_name=root_name,
                bg_color=None,
                width=fw,
                height=fh,
                invert=invert.get() if invert else False,
            )
        elif view.startswith("3NPS"):
            pos_num = int(view.split()[-1])
            notes = get_three_note_per_string_scale(root_name, scale_name, position=pos_num)
            if not notes:
                self._set_status(f"3NPS position {pos_num} not available for this scale")
                return

            all_frets = [n["fret"] for n in notes]
            start_fret = max(1, min(all_frets))
            end_fret = max(all_frets)

            self._current_scale_notes = notes
            self._current_frets = None

            bw, bh = self._custom_size(600, 800)
            img = render_scale_box(
                box_notes=notes,
                start_fret=start_fret,
                end_fret=end_fret,
                scale_name=f"{scale_name} (3NPS)",
                root_name=root_name,
                position_num=pos_num,
                bg_color=None,
                width=bw,
                height=bh,
            )
        else:
            # Positional box (CAGED)
            pos_num = int(view.split()[-1])
            positions = get_caged_positions(root_name, scale_name)
            if pos_num > len(positions):
                self._set_status(f"Position {pos_num} not available")
                return

            pos = positions[pos_num - 1]
            self._current_scale_notes = pos["notes"]
            self._current_frets = None

            bw, bh = self._custom_size(600, 800)
            img = render_scale_box(
                box_notes=pos["notes"],
                start_fret=pos["start_fret"],
                end_fret=pos["end_fret"],
                scale_name=scale_name,
                root_name=root_name,
                position_num=pos_num,
                bg_color=None,
                width=bw,
                height=bh,
            )

        interval_labels = get_scale_interval_labels(scale_name)
        intervals_str = "  |  " + "  ".join(interval_labels) if interval_labels else ""
        self._current_image = img
        self._show_preview(img)
        self._set_status(display_name + (f" — {view}" if view != "Full Fretboard" else " — Full Fretboard") + intervals_str)
        self._record_history(self._snapshot())

    # ── Progression Generation ─────────────────────────────

    def _on_prog_mode_change(self):
        """Kept for snapshot compatibility; mode is now auto-detected."""
        self._update_progression()

    # ── Scale/Arpeggio Progression Panel Builder ───────────

    def _build_scale_arp_prog_panel(self, frame, prefix, title_text, on_change):
        """
        Build the sidebar panel shared by Scale Prog and Arp Prog modes.
        prefix: "scale_prog" or "arp_prog" — used to name the CTk vars.
        """
        _menu_kw = dict(
            fg_color=config.HEX_NAVY_DEEP, button_color=config.HEX_NAVY_LIGHT,
            button_hover_color=config.HEX_GOLD, dropdown_fg_color=config.HEX_NAVY_MID,
        )

        def _card(title=None):
            outer = ctk.CTkFrame(frame, fg_color=config.HEX_NAVY_MID, corner_radius=8)
            outer.pack(fill="x", padx=8, pady=(0, 6))
            if title:
                ctk.CTkLabel(outer, text=title, font=("Arial", 9, "bold"),
                             text_color=config.HEX_GOLD).pack(anchor="w", padx=10, pady=(7, 4))
            return outer

        def _lrow(parent, label, lw=80):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", padx=8, pady=(0, 4))
            r.columnconfigure(0, minsize=lw)
            r.columnconfigure(1, weight=1)
            ctk.CTkLabel(r, text=label, text_color=config.HEX_CREAM,
                         font=("Arial", 11), anchor="w", width=lw).grid(row=0, column=0, sticky="w")
            return r

        main_card = _card(title_text.upper())

        root_var = ctk.StringVar(value="C")
        setattr(self, f"_{prefix}_root_var", root_var)
        r = _lrow(main_card, "Key Root:")
        ctk.CTkOptionMenu(r, variable=root_var, values=ROOT_NAMES,
                          **_menu_kw, command=on_change).grid(row=0, column=1, sticky="ew")

        mode_var = ctk.StringVar(value='major')
        setattr(self, f'_{prefix}_key_mode_var', mode_var)
        r = _lrow(main_card, 'Custom key:')
        ctk.CTkOptionMenu(r, variable=mode_var, values=['major','minor'],
                         **_menu_kw, command=on_change).grid(row=0,column=1,sticky='ew')
        name_var = ctk.StringVar(value=ALL_PROG_NAMES[0])
        setattr(self, f"_{prefix}_name_var", name_var)
        r = _lrow(main_card, "Prog:")
        name_menu = ctk.CTkOptionMenu(r, variable=name_var, values=ALL_PROG_NAMES,
                                      **_menu_kw, command=on_change)
        name_menu.grid(row=0, column=1, sticky="ew")
        setattr(self, f"_{prefix}_name_menu", name_menu)

        if prefix == "arp_prog":
            arp_type_var = ctk.StringVar(value="Auto")
            setattr(self, "_arp_prog_type_var", arp_type_var)
            r = _lrow(main_card, "Arp Type:")
            _arp_prog_type_menu = ctk.CTkOptionMenu(
                r, variable=arp_type_var,
                values=["Auto"] + ARPEGGIO_NAMES,
                **_menu_kw, command=on_change,
            )
            _arp_prog_type_menu.grid(row=0, column=1, sticky="ew")
            self._arp_prog_type_menu_widget = _arp_prog_type_menu

        ctk.CTkLabel(main_card, text="Custom (e.g. I-IV-V):",
                     text_color=config.HEX_CREAM, font=("Arial", 10)).pack(padx=10, anchor="w", pady=(4, 0))
        custom_var = ctk.StringVar(value="")
        setattr(self, f"_{prefix}_custom_var", custom_var)
        entry = ctk.CTkEntry(
            main_card, textvariable=custom_var,
            placeholder_text="e.g. I-V-vi-IV",
            height=32, fg_color=config.HEX_NAVY_DEEP,
            text_color=config.HEX_CREAM, border_color=config.HEX_NAVY_LIGHT,
        )
        entry.pack(padx=8, fill="x", pady=(0, 4))
        entry.bind("<Return>", on_change)
        ctk.CTkButton(
            main_card, text="Generate", height=32,
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: on_change(None),
        ).pack(padx=8, fill="x", pady=(0, 8))

        # Settings card
        settings_card = _card("SETTINGS")
        pos_var = ctk.StringVar(value="1")
        setattr(self, f"_{prefix}_pos_var", pos_var)
        r = _lrow(settings_card, "Neck Pos:")
        ctk.CTkOptionMenu(r, variable=pos_var, values=["1", "2", "3", "4", "5"],
                          **_menu_kw, command=on_change).grid(row=0, column=1, sticky="ew")

        ctk.CTkFrame(settings_card, height=4, fg_color="transparent").pack()

        # Playback direction card
        dir_card = _card("PLAYBACK DIRECTION")
        ctk.CTkLabel(dir_card, text="(generated per degree)",
                     text_color="#6a8ab8", font=("Arial", 9)).pack(padx=10, anchor="w", pady=(0, 2))
        dir_frame = ctk.CTkFrame(dir_card, fg_color="transparent")
        dir_frame.pack(padx=8, fill="x", pady=(0, 8))
        setattr(self, f"_{prefix}_dir_frame", dir_frame)
        setattr(self, f"_{prefix}_dir_vars", [])

    # ── Custom Library Panel ────────────────────────────────

    def _build_custom_panel(self, frame):
        """Build the Custom Library sidebar panel."""
        _menu_kw = dict(
            fg_color=config.HEX_NAVY_DEEP, button_color=config.HEX_NAVY_LIGHT,
            button_hover_color=config.HEX_GOLD, dropdown_fg_color=config.HEX_NAVY_MID,
        )

        def _card(title=None):
            outer = ctk.CTkFrame(frame, fg_color=config.HEX_NAVY_MID, corner_radius=8)
            outer.pack(fill="x", padx=8, pady=(0, 6))
            if title:
                ctk.CTkLabel(outer, text=title, font=("Arial", 9, "bold"),
                             text_color=config.HEX_GOLD).pack(anchor="w", padx=10, pady=(7, 4))
            return outer

        # ── ADD CUSTOM SCALE ──────────────────────────────
        scale_card = _card("ADD CUSTOM SCALE")

        ctk.CTkLabel(scale_card, text="Name:", text_color=config.HEX_CREAM,
                     font=("Arial", 11), anchor="w").pack(padx=10, anchor="w")
        self._custom_scale_name_var = ctk.StringVar()
        ctk.CTkEntry(
            scale_card, textvariable=self._custom_scale_name_var,
            placeholder_text="e.g. My Blues Scale",
            height=30, fg_color=config.HEX_NAVY_DEEP,
            text_color=config.HEX_CREAM, border_color=config.HEX_NAVY_LIGHT,
        ).pack(padx=8, fill="x", pady=(0, 4))

        ctk.CTkLabel(scale_card, text="Intervals (0-11, comma-separated):",
                     text_color=config.HEX_CREAM, font=("Arial", 11), anchor="w").pack(padx=10, anchor="w")
        self._custom_scale_intervals_var = ctk.StringVar()
        ctk.CTkEntry(
            scale_card, textvariable=self._custom_scale_intervals_var,
            placeholder_text="e.g. 0,2,4,5,7,9,11",
            height=30, fg_color=config.HEX_NAVY_DEEP,
            text_color=config.HEX_CREAM, border_color=config.HEX_NAVY_LIGHT,
        ).pack(padx=8, fill="x", pady=(0, 4))

        ctk.CTkButton(
            scale_card, text="+ Save Custom Scale", height=30,
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=self._add_custom_scale,
        ).pack(padx=8, fill="x", pady=(0, 8))

        # ── SAVED CUSTOM SCALES LIST ──────────────────────
        self._custom_scales_list_card = _card("SAVED CUSTOM SCALES")
        self._custom_scales_list_frame = ctk.CTkFrame(
            self._custom_scales_list_card, fg_color="transparent"
        )
        self._custom_scales_list_frame.pack(fill="x", padx=8, pady=(0, 8))

        # ── ADD CUSTOM ARPEGGIO ───────────────────────────
        arp_card = _card("ADD CUSTOM ARPEGGIO")

        ctk.CTkLabel(arp_card, text="Name:", text_color=config.HEX_CREAM,
                     font=("Arial", 11), anchor="w").pack(padx=10, anchor="w")
        self._custom_arp_name_var = ctk.StringVar()
        ctk.CTkEntry(
            arp_card, textvariable=self._custom_arp_name_var,
            placeholder_text="e.g. My Arp",
            height=30, fg_color=config.HEX_NAVY_DEEP,
            text_color=config.HEX_CREAM, border_color=config.HEX_NAVY_LIGHT,
        ).pack(padx=8, fill="x", pady=(0, 4))

        ctk.CTkLabel(arp_card, text="Intervals (0-11, comma-separated):",
                     text_color=config.HEX_CREAM, font=("Arial", 11), anchor="w").pack(padx=10, anchor="w")
        self._custom_arp_intervals_var = ctk.StringVar()
        ctk.CTkEntry(
            arp_card, textvariable=self._custom_arp_intervals_var,
            placeholder_text="e.g. 0,4,7,11",
            height=30, fg_color=config.HEX_NAVY_DEEP,
            text_color=config.HEX_CREAM, border_color=config.HEX_NAVY_LIGHT,
        ).pack(padx=8, fill="x", pady=(0, 4))

        ctk.CTkButton(
            arp_card, text="+ Save Custom Arpeggio", height=30,
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=self._add_custom_arpeggio,
        ).pack(padx=8, fill="x", pady=(0, 8))

        # ── SAVED CUSTOM ARPEGGIOS LIST ───────────────────
        self._custom_arps_list_card = _card("SAVED CUSTOM ARPEGGIOS")
        self._custom_arps_list_frame = ctk.CTkFrame(
            self._custom_arps_list_card, fg_color="transparent"
        )
        self._custom_arps_list_frame.pack(fill="x", padx=8, pady=(0, 8))

    def _refresh_custom_lists(self):
        """Rebuild the saved-items lists in the Custom Library panel."""
        # Scales list
        for w in self._custom_scales_list_frame.winfo_children():
            w.destroy()
        saved_scales = _custom_lib.list_custom_scales()
        if saved_scales:
            for name in saved_scales:
                row = ctk.CTkFrame(self._custom_scales_list_frame, fg_color="transparent")
                row.pack(fill="x", pady=(0, 3))
                row.columnconfigure(0, weight=1)
                ctk.CTkLabel(
                    row, text=f"★ {name}", text_color=config.HEX_CREAM,
                    font=("Arial", 11), anchor="w",
                ).grid(row=0, column=0, sticky="w")
                ctk.CTkButton(
                    row, text="✕", width=28, height=24,
                    fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
                    hover_color="#8b2020",
                    command=lambda n=name: self._delete_custom_scale(n),
                ).grid(row=0, column=1, sticky="e")
        else:
            ctk.CTkLabel(
                self._custom_scales_list_frame, text="No custom scales saved.",
                text_color="#6a8ab8", font=("Arial", 10),
            ).pack(anchor="w")

        # Arpeggios list
        for w in self._custom_arps_list_frame.winfo_children():
            w.destroy()
        saved_arps = _custom_lib.list_custom_arpeggios()
        if saved_arps:
            for name in saved_arps:
                row = ctk.CTkFrame(self._custom_arps_list_frame, fg_color="transparent")
                row.pack(fill="x", pady=(0, 3))
                row.columnconfigure(0, weight=1)
                ctk.CTkLabel(
                    row, text=f"★ {name}", text_color=config.HEX_CREAM,
                    font=("Arial", 11), anchor="w",
                ).grid(row=0, column=0, sticky="w")
                ctk.CTkButton(
                    row, text="✕", width=28, height=24,
                    fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
                    hover_color="#8b2020",
                    command=lambda n=name: self._delete_custom_arpeggio(n),
                ).grid(row=0, column=1, sticky="e")
        else:
            ctk.CTkLabel(
                self._custom_arps_list_frame, text="No custom arpeggios saved.",
                text_color="#6a8ab8", font=("Arial", 10),
            ).pack(anchor="w")

    def _add_custom_scale(self):
        name = self._custom_scale_name_var.get().strip()
        raw  = self._custom_scale_intervals_var.get().strip()
        try:
            intervals = _custom_lib.parse_interval_string(raw)
            _custom_lib.add_custom_scale(name, intervals, SCALE_INTERVALS, SCALE_NAMES)
        except ValueError as e:
            self._set_status(f"Custom scale error: {e}")
            return
        self._custom_scale_name_var.set("")
        self._custom_scale_intervals_var.set("")
        self._scale_type_menu.configure(values=list(SCALE_NAMES))
        self._refresh_custom_lists()
        self._set_status(f"Custom scale '★ {name}' saved — available in the Scale section.")

    def _delete_custom_scale(self, display_name: str):
        _custom_lib.delete_custom_scale(display_name, SCALE_INTERVALS, SCALE_NAMES)
        self._scale_type_menu.configure(values=list(SCALE_NAMES))
        # If the deleted scale was selected, reset to default
        if self.scale_type_var.get() == _custom_lib.CUSTOM_PREFIX + display_name:
            self.scale_type_var.set("Pentatonic Minor")
        self._refresh_custom_lists()
        self._set_status(f"Custom scale '{display_name}' deleted.")

    def _add_custom_arpeggio(self):
        name = self._custom_arp_name_var.get().strip()
        raw  = self._custom_arp_intervals_var.get().strip()
        try:
            intervals = _custom_lib.parse_interval_string(raw)
            _custom_lib.add_custom_arpeggio(name, intervals, ARPEGGIO_INTERVALS, ARPEGGIO_NAMES)
        except ValueError as e:
            self._set_status(f"Custom arpeggio error: {e}")
            return
        self._custom_arp_name_var.set("")
        self._custom_arp_intervals_var.set("")
        self._arp_type_menu.configure(values=list(ARPEGGIO_NAMES))
        # Also refresh the arp prog type dropdown if it exists
        arp_prog_type_menu = getattr(self, "_arp_prog_type_menu_widget", None)
        if arp_prog_type_menu:
            arp_prog_type_menu.configure(values=["Auto"] + list(ARPEGGIO_NAMES))
        self._refresh_custom_lists()
        self._set_status(f"Custom arpeggio '★ {name}' saved — available in the Arpeggio section.")

    def _delete_custom_arpeggio(self, display_name: str):
        _custom_lib.delete_custom_arpeggio(display_name, ARPEGGIO_INTERVALS, ARPEGGIO_NAMES)
        self._arp_type_menu.configure(values=list(ARPEGGIO_NAMES))
        arp_prog_type_menu = getattr(self, "_arp_prog_type_menu_widget", None)
        if arp_prog_type_menu:
            arp_prog_type_menu.configure(values=["Auto"] + list(ARPEGGIO_NAMES))
        if self.arp_type_var.get() == _custom_lib.CUSTOM_PREFIX + display_name:
            self.arp_type_var.set("Minor")
        self._refresh_custom_lists()
        self._set_status(f"Custom arpeggio '{display_name}' deleted.")

    # ── Scale Progression Generation ───────────────────────

    def _update_scale_prog(self):
        try:
            self._update_scale_prog_inner()
        except Exception as e:
            self._set_status(f"Error generating scale progression: {e}")

    def _update_scale_prog_inner(self):
        self.document = CurrentDocument()
        self._current_image = None
        root    = getattr(self, "_scale_prog_root_var").get().split("/")[0]
        custom  = getattr(self, "_scale_prog_custom_var").get().strip()
        mode    = _mode_for_prog(getattr(self, "_scale_prog_name_var").get(), custom, self._scale_prog_key_mode_var.get())
        pos_num = int(getattr(self, "_scale_prog_pos_var").get())

        if custom:
            degrees = parse_roman(custom, mode)
            if degrees is None:
                self._set_status(f"Could not parse '{custom}' — use e.g. I-V-vi-IV")
                return
            prog_name = custom.upper()
        else:
            prog_name = getattr(self, "_scale_prog_name_var").get()
            progs = MAJOR_PROGRESSIONS if mode == "major" else MINOR_PROGRESSIONS
            degrees = progs[prog_name]

        items = get_progression_scales(root, mode, degrees)
        title = make_scale_progression_title(root, mode, prog_name, kind="Scales")
        img   = render_scale_progression_strip(items, title=title, position_num=pos_num)

        self._rebuild_direction_controls(
            "scale_prog",
            [f"{it['roman']}  {it['display_name']}" for it in items],
            ["Asc", "Desc", "Asc + Desc"],
            "Asc",
        )

        self._current_image              = img
        self._current_frets              = None
        self._current_scale_notes        = None
        self._current_is_arpeggio        = False
        self._current_progression        = None
        self._current_scale_prog_items   = items
        self._current_arp_prog_items     = None
        self._current_prog_title         = title
        self._current_name = f"{root}_{mode}_{prog_name.replace(' ', '_')}_scales"

        self._show_preview(img)
        self._set_status(f"{title}  |  " + "  ·  ".join(it["display_name"] for it in items))
        self._record_history(self._snapshot())

    # ── Arpeggio Progression Generation ────────────────────

    def _update_arp_prog(self):
        try:
            self._update_arp_prog_inner()
        except Exception as e:
            self._set_status(f"Error generating arpeggio progression: {e}")

    def _update_arp_prog_inner(self):
        self.document = CurrentDocument()
        self._current_image = None
        root    = getattr(self, "_arp_prog_root_var").get().split("/")[0]
        custom  = getattr(self, "_arp_prog_custom_var").get().strip()
        mode    = _mode_for_prog(getattr(self, "_arp_prog_name_var").get(), custom, self._arp_prog_key_mode_var.get())
        pos_num = int(getattr(self, "_arp_prog_pos_var").get())

        if custom:
            degrees = parse_roman(custom, mode)
            if degrees is None:
                self._set_status(f"Could not parse '{custom}' — use e.g. I-V-vi-IV")
                return
            prog_name = custom.upper()
        else:
            prog_name = getattr(self, "_arp_prog_name_var").get()
            progs = MAJOR_PROGRESSIONS if mode == "major" else MINOR_PROGRESSIONS
            degrees = progs[prog_name]

        items = get_progression_arpeggios(root, mode, degrees)

        # Apply arp type override if not "Auto"
        arp_type_var = getattr(self, "_arp_prog_type_var", None)
        selected_type = arp_type_var.get() if arp_type_var else "Auto"
        if selected_type != "Auto":
            for item in items:
                item["arp_name"] = selected_type
                item["display_name"] = f"{item['chord_root']} {selected_type}"

        title = make_scale_progression_title(root, mode, prog_name, kind="Arpeggios")
        img   = render_arpeggio_progression_strip(items, title=title, position_num=pos_num)

        self._rebuild_direction_controls(
            "arp_prog",
            [f"{it['roman']}  {it['display_name']}" for it in items],
            ["Asc", "Desc", "Asc + Desc"],
            "Asc",
        )

        self._current_image              = img
        self._current_frets              = None
        self._current_scale_notes        = None
        self._current_is_arpeggio        = True
        self._current_progression        = None
        self._current_scale_prog_items   = None
        self._current_arp_prog_items     = items
        self._current_prog_title         = title
        self._current_name = f"{root}_{mode}_{prog_name.replace(' ', '_')}_arpeggios"

        self._show_preview(img)
        self._set_status(f"{title}  |  " + "  ·  ".join(it["display_name"] for it in items))
        self._record_history(self._snapshot())

    def _update_progression(self):
        try:
            self._update_progression_inner()
        except Exception as e:
            self._set_status(f"Error generating progression: {e}")

    def _update_progression_inner(self):
        self.document = CurrentDocument()
        self._current_image = None
        root = self.prog_root_var.get().split("/")[0]
        custom = self.prog_custom_var.get().strip()
        prog_name_peek = self.prog_name_var.get()
        mode = _mode_for_prog(prog_name_peek, custom, self.prog_key_mode_var.get())

        if custom:
            degrees = parse_roman(custom, mode)
            if degrees is None:
                self._set_status(f"Could not parse '{custom}' — use e.g. I-V-vi-IV")
                return
            chords = get_progression_chords(root, mode, degrees)
            prog_name = custom.upper()
        else:
            prog_name = self.prog_name_var.get()
            degrees, chords = get_named_progression(root, mode, prog_name)

        # Apply chord quality override if not "Auto"
        quality_override = getattr(self, "prog_quality_var", None)
        if quality_override:
            sel_quality = quality_override.get()
            if sel_quality != "Auto":
                from data.chords import get_voicings, get_chord_display_name
                for ch in chords:
                    voicings = get_voicings(ch["chord_root"], sel_quality)
                    if voicings:
                        v = voicings[0]
                        ch["quality"] = sel_quality
                        ch["display_name"] = get_chord_display_name(ch["chord_root"], sel_quality)
                        ch["frets"] = v["frets"]
                        ch["fingers"] = v.get("fingers")

        title = make_progression_title(root, mode, prog_name)
        img = render_progression_strip(
            chords,
            title=title,
            dot_label=self.prog_dot_label_var.get(),
            show_barre=self.prog_show_barre_var.get(),
            barre_style="arch" if getattr(self, "prog_barre_style_var", None) and self.prog_barre_style_var.get() == "Arch" else "rect",
            show_string_names=self.prog_show_string_names_var.get(),
            show_finger_numbers=self.prog_show_finger_numbers_var.get(),
        )

        self._rebuild_direction_controls(
            "prog",
            [f"{c['roman']}  {c['display_name']}" for c in chords],
            ["Down", "Up"],
            "Down",
        )

        self._current_image = img
        self._current_frets = None
        self._current_scale_notes = None
        self._current_is_arpeggio = False
        self._current_progression = chords
        self._current_prog_title = title
        self._current_name = f"{root}_{mode}_{prog_name.replace(' ', '_')}"

        self._show_preview(img)
        chord_names = " — ".join(c["display_name"] for c in chords)
        self._set_status(f"{title}  |  {chord_names}")
        self._record_history(self._snapshot())

    # ── Triads Generation ──────────────────────────────────

    def _on_triads_scale_change(self):
        """Show/hide the quality row depending on whether Custom mode is selected."""
        if self.triads_scale_var.get() == "Custom":
            self._triads_quality_row.pack(
                fill="x", padx=8, pady=(0, 4),
                before=self._triads_voicing_row,
            )
        else:
            self._triads_quality_row.pack_forget()
        self._update_triads()

    def _update_triads(self):
        try:
            self._update_triads_inner()
        except Exception as e:
            self._set_status(f"Error generating triads: {e}")

    def _update_triads_inner(self):
        self.document = CurrentDocument()
        self._current_image = None
        key     = self.triads_key_var.get().split("/")[0]
        voicing = self.triads_voicing_var.get()
        scale   = getattr(self, "triads_scale_var", None)
        scale   = scale.get() if scale else "Major"

        from data.triads import TRIAD_TEMPLATES
        string_label = TRIAD_TEMPLATES[voicing]["string_label"]

        if scale == "Custom":
            quality = self.triads_quality_var.get()
            chord   = get_triad_voicing(key, quality, voicing)
            chords  = [{
                "chord_root":   key,
                "quality":      quality,
                "frets":        chord["frets"],
                "fingers":      chord["fingers"],
                "display_name": chord["display_name"],
                "roman":        quality,
            }]
            title = f"{chord['display_name']}  |  {voicing} ({string_label})"
        else:
            _scale_funcs = {
                "Major":          (get_diatonic_triads,               "Major"),
                "Natural Minor":  (get_diatonic_minor_triads,         "Natural Minor"),
                "Harmonic Minor": (get_diatonic_harmonic_minor_triads, "Harmonic Minor"),
                "Melodic Minor":  (get_diatonic_melodic_minor_triads,  "Melodic Minor"),
            }
            func, scale_label = _scale_funcs.get(scale, (get_diatonic_triads, "Major"))
            chords = func(key, voicing)
            title  = f"{key} {scale_label}  |  Triads — {voicing} ({string_label})"

        img = render_progression_strip(
            chords,
            title=title,
            dot_label=self.triads_dot_label_var.get(),
            show_barre=self.triads_show_barre_var.get(),
            barre_style="arch" if getattr(self, "triads_barre_style_var", None) and self.triads_barre_style_var.get() == "Arch" else "rect",
            show_string_names=self.triads_show_string_names_var.get(),
            show_finger_numbers=True,
        )

        self._current_image = img
        self._current_frets = None
        self._current_scale_notes = None
        self._current_is_arpeggio = False
        self._current_progression = chords
        self._current_prog_title = title
        self._current_name = title.replace("  |  ", "_").replace(" ", "_").replace("/", "-")

        self._show_preview(img)
        chord_names = "  ".join(
            f"{c.get('roman', '')} {c['display_name']}".strip() for c in chords
        )
        self._set_status(f"{title}  |  {chord_names}")

    # ── Arpeggio Generation ────────────────────────────────

    def _update_arpeggio(self):
        """Regenerate arpeggio diagram from current selections."""
        try:
            self._update_arpeggio_inner()
        except Exception as e:
            self._set_status(f"Error generating arpeggio: {e}")

    def _update_arpeggio_inner(self):
        self.document = CurrentDocument()
        self._current_image = None
        self._current_is_arpeggio = True
        root = self.arp_root_var.get()
        root_name = root.split("/")[0] if "/" in root else root
        arp_name = self.arp_type_var.get()
        view = self.arp_view_var.get()

        display_name = get_arpeggio_display_name(root_name, arp_name)
        self._current_name = display_name.replace(" ", "_")

        if view == "Full Fretboard":
            notes = get_full_fretboard_arpeggio(root_name, arp_name, num_frets=15)
            self._current_scale_notes = notes
            self._current_frets = None

            invert = getattr(self, "invert_var", None)
            fw, fh = self._custom_size(1600, 500)
            img = render_scale_full_fretboard(
                scale_notes=notes,
                scale_name=f"{arp_name} Arpeggio",
                root_name=root_name,
                bg_color=None,
                width=fw,
                height=fh,
                invert=invert.get() if invert else False,
            )
        else:
            pos_num = int(view.split()[-1])
            positions = get_arpeggio_positions(root_name, arp_name)
            if pos_num > len(positions):
                self._set_status(f"Position {pos_num} not available for this arpeggio")
                return

            pos = positions[pos_num - 1]
            self._current_scale_notes = pos["notes"]
            self._current_frets = None

            bw, bh = self._custom_size(600, 800)
            img = render_scale_box(
                box_notes=pos["notes"],
                start_fret=pos["start_fret"],
                end_fret=pos["end_fret"],
                scale_name=f"{arp_name} Arpeggio",
                root_name=root_name,
                position_num=pos_num,
                bg_color=None,
                width=bw,
                height=bh,
            )

        interval_labels = get_arpeggio_interval_labels(arp_name)
        intervals_str = "  |  " + "  ".join(interval_labels) if interval_labels else ""
        self._current_image = img
        self._show_preview(img)
        self._set_status(display_name + f" — {view}" + intervals_str)
        self._record_history(self._snapshot())

    # ── Preview ────────────────────────────────────────────

    def _show_preview(self, img):
        """Display a PIL image in the preview panel."""
        self._preview_source = img
        # Fit to preview area
        pw = self.preview_frame.winfo_width()
        ph = self.preview_frame.winfo_height()
        if pw < 10 or ph < 10:
            pw, ph = 700, 600

        scale = min(pw / img.width, ph / img.height, 1.0) * self._preview_zoom
        display_w = max(int(img.width * scale), 1)
        display_h = max(int(img.height * scale), 1)

        display_img = img.resize((display_w, display_h), Image.Resampling.LANCZOS)
        photo = ctk.CTkImage(light_image=display_img, dark_image=display_img, size=(display_w, display_h))

        self.preview_label.configure(image=photo, text="")
        self.preview_label.image = photo  # Keep reference

    # ── Chord Lookup ───────────────────────────────────────

    _CL_KEYS = [
        {"root": "A",  "display": "A",  "flat": None},
        {"root": "A#", "display": "A#", "flat": "Bb"},
        {"root": "B",  "display": "B",  "flat": None},
        {"root": "C",  "display": "C",  "flat": None},
        {"root": "C#", "display": "C#", "flat": "Db"},
        {"root": "D",  "display": "D",  "flat": None},
        {"root": "D#", "display": "D#", "flat": "Eb"},
        {"root": "E",  "display": "E",  "flat": None},
        {"root": "F",  "display": "F",  "flat": None},
        {"root": "F#", "display": "F#", "flat": "Gb"},
        {"root": "G",  "display": "G",  "flat": None},
        {"root": "G#", "display": "G#", "flat": "Ab"},
    ]

    _CL_QUALITIES = [
        {"qual": "Major",   "label": "Major"},
        {"qual": "Minor",   "label": "Minor"},
        {"qual": "7",       "label": "7th"},
        {"qual": "Maj7",    "label": "Major 7"},
        {"qual": "Min7",    "label": "Minor 7"},
        {"qual": "Sus2",    "label": "Sus 2"},
        {"qual": "Sus4",    "label": "Sus 4"},
        {"qual": "Dim",     "label": "Dim"},
        {"qual": "Aug",     "label": "Aug"},
        {"qual": "Add9",    "label": "Add 9"},
        {"qual": "Power",   "label": "Power 5"},
        {"qual": "9",       "label": "9th"},
        {"qual": "Maj9",    "label": "Major 9"},
        {"qual": "Min9",    "label": "Minor 9"},
        {"qual": "Dim7",    "label": "Dim 7"},
        {"qual": "Min7b5",  "label": "m7b5"},
    ]

    _CL_QUAL_LABELS = {
        "Major":   "Major",          "Minor":   "Minor",
        "7":       "Dominant 7th",   "Maj7":    "Major 7th",
        "Min7":    "Minor 7th",      "Sus2":    "Suspended 2nd",
        "Sus4":    "Suspended 4th",  "Dim":     "Diminished",
        "Aug":     "Augmented",      "Add9":    "Add 9",
        "Power":   "Power Chord",    "9":       "9th",
        "Maj9":    "Major 9th",      "Min9":    "Minor 9th",
        "Dim7":    "Diminished 7th", "Min7b5":  "Minor 7b5",
    }

    def _build_triads_panel(self):
        """Build the Triads sidebar panel (diatonic triad voicings)."""
        frame = self.triads_frame

        _menu_kw = dict(
            fg_color=config.HEX_NAVY_DEEP, button_color=config.HEX_NAVY_LIGHT,
            button_hover_color=config.HEX_GOLD, dropdown_fg_color=config.HEX_NAVY_MID,
        )

        def _card(title=None):
            outer = ctk.CTkFrame(frame, fg_color=config.HEX_NAVY_MID, corner_radius=8)
            outer.pack(fill="x", padx=8, pady=(0, 6))
            if title:
                ctk.CTkLabel(outer, text=title, font=("Arial", 9, "bold"),
                             text_color=config.HEX_GOLD).pack(anchor="w", padx=10, pady=(7, 4))
            return outer

        def _lrow(parent, label, lw=80):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", padx=8, pady=(0, 4))
            r.columnconfigure(0, minsize=lw)
            r.columnconfigure(1, weight=1)
            ctk.CTkLabel(r, text=label, text_color=config.HEX_CREAM,
                         font=("Arial", 11), anchor="w", width=lw).grid(row=0, column=0, sticky="w")
            return r

        main_card = _card("TRIADS")

        # Key root
        self.triads_key_var = ctk.StringVar(value="C")
        r = _lrow(main_card, "Key:")
        ctk.CTkOptionMenu(
            r, variable=self.triads_key_var, values=ROOT_NAMES,
            **_menu_kw, command=lambda _: self._schedule_preview("Triads"),
        ).grid(row=0, column=1, sticky="ew")

        # Scale type / mode
        _scale_options = [
            "Major", "Natural Minor", "Harmonic Minor", "Melodic Minor", "Custom",
        ]
        self.triads_scale_var = ctk.StringVar(value="Major")
        r = _lrow(main_card, "Scale:")
        ctk.CTkOptionMenu(
            r, variable=self.triads_scale_var, values=_scale_options,
            **_menu_kw, command=lambda _: self._on_triads_scale_change(),
        ).grid(row=0, column=1, sticky="ew")

        # Voicing type (saved as instance var so quality row can be inserted before it)
        self.triads_voicing_var = ctk.StringVar(value=TRIAD_VOICING_NAMES[0])
        self._triads_voicing_row = _lrow(main_card, "Voicing:")
        ctk.CTkOptionMenu(
            self._triads_voicing_row, variable=self.triads_voicing_var,
            values=TRIAD_VOICING_NAMES,
            **_menu_kw, command=lambda _: self._schedule_preview("Triads"),
        ).grid(row=0, column=1, sticky="ew")

        # Custom quality row (shown only when Scale = "Custom")
        # Created after voicing row so we can reference it with pack(before=...)
        self.triads_quality_var = ctk.StringVar(value="Aug")
        self._triads_quality_row = _lrow(main_card, "Quality:")
        ctk.CTkOptionMenu(
            self._triads_quality_row, variable=self.triads_quality_var,
            values=TRIAD_QUALITIES,
            **_menu_kw, command=lambda _: self._schedule_preview("Triads"),
        ).grid(row=0, column=1, sticky="ew")
        self._triads_quality_row.pack_forget()   # hidden by default

        ctk.CTkButton(
            main_card, text="Generate", height=32,
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=lambda: self._schedule_preview("Triads"),
        ).pack(padx=8, fill="x", pady=(0, 8))

        # Display settings card
        disp_card = _card("DISPLAY")

        self.triads_dot_label_var = ctk.StringVar(value="note")
        r = _lrow(disp_card, "Dot label:")
        ctk.CTkOptionMenu(
            r, variable=self.triads_dot_label_var, values=["note", "finger", "none"],
            **_menu_kw, command=lambda _: self._schedule_preview("Triads"),
        ).grid(row=0, column=1, sticky="ew")

        self.triads_show_barre_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            disp_card, text="Show barre indicator",
            variable=self.triads_show_barre_var,
            font=("Arial", 10), text_color=config.HEX_CREAM,
            checkbox_width=16, checkbox_height=16,
            command=lambda: self._schedule_preview("Triads"),
        ).pack(anchor="w", padx=10, pady=(2, 2))

        self.triads_barre_style_var = ctk.StringVar(value="Rectangle")
        try:
            ctk.CTkSegmentedButton(
                disp_card, values=["Rectangle", "Arch"],
                variable=self.triads_barre_style_var,
                fg_color=config.HEX_NAVY_DEEP, selected_color=config.HEX_GOLD,
                selected_hover_color=config.HEX_GOLD_BRIGHT,
                unselected_color=config.HEX_NAVY_LIGHT,
                text_color=config.HEX_CREAM,
                command=lambda _: self._schedule_preview("Triads"),
            ).pack(padx=10, fill="x", pady=(2, 4))
        except Exception:
            pass

        self.triads_show_string_names_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            disp_card, text="Show string names",
            variable=self.triads_show_string_names_var,
            font=("Arial", 10), text_color=config.HEX_CREAM,
            checkbox_width=16, checkbox_height=16,
            command=lambda: self._schedule_preview("Triads"),
        ).pack(anchor="w", padx=10, pady=(2, 6))

    def _build_chord_lookup_panel(self):
        """Build the scrollable chord lookup panel inside preview_frame (hidden initially)."""
        self.chord_lookup_panel = ctk.CTkScrollableFrame(
            self.preview_frame,
            fg_color=config.HEX_NAVY_DEEP, corner_radius=0,
            scrollbar_button_color=config.HEX_NAVY_LIGHT,
            scrollbar_button_hover_color=config.HEX_GOLD,
        )
        # Don't pack yet — _set_mode controls visibility

        inner = self.chord_lookup_panel

        # ── Key selector ──────────────────────────────────
        key_sec = ctk.CTkFrame(inner, fg_color="transparent")
        key_sec.pack(fill="x", padx=20, pady=(18, 0))
        ctk.CTkLabel(
            key_sec, text="KEY", font=("Arial", 9, "bold"), text_color="#8fa3bf",
        ).pack(anchor="w", pady=(0, 6))

        keys_row = ctk.CTkFrame(key_sec, fg_color="transparent")
        keys_row.pack(fill="x")

        for k in self._CL_KEYS:
            btn_frame = self._cl_make_key_btn(keys_row, k)
            btn_frame.pack(side="left", padx=(0, 5), pady=(0, 2))
            self._cl_key_btns[k["root"]] = btn_frame

        # ── Quality selector ──────────────────────────────
        qual_sec = ctk.CTkFrame(inner, fg_color="transparent")
        qual_sec.pack(fill="x", padx=20, pady=(14, 0))
        ctk.CTkLabel(
            qual_sec, text="TYPE", font=("Arial", 9, "bold"), text_color="#8fa3bf",
        ).pack(anchor="w", pady=(0, 6))

        qual_grid = ctk.CTkFrame(qual_sec, fg_color="transparent")
        qual_grid.pack(fill="x")
        _cols = 8
        for col in range(_cols):
            qual_grid.columnconfigure(col, weight=0)

        for i, q in enumerate(self._CL_QUALITIES):
            btn = ctk.CTkButton(
                qual_grid, text=q["label"],
                font=("Arial", 11), height=32,
                fg_color=config.HEX_NAVY_MID, text_color="#8fa3bf",
                border_color="#1e3d6e", border_width=1,
                hover_color="#1a3050", corner_radius=16,
                command=lambda qual=q["qual"]: self._cl_set_qual(qual),
            )
            btn.grid(row=i // _cols, column=i % _cols, padx=(0, 6), pady=(0, 6), sticky="ew")
            self._cl_qual_btns[q["qual"]] = btn

        # ── Chord info banner ─────────────────────────────
        banner = ctk.CTkFrame(
            inner, fg_color="#0f2344",
            border_color=config.HEX_GOLD, border_width=1,
            corner_radius=12,
        )
        banner.pack(fill="x", padx=20, pady=(16, 0))

        banner_inner = ctk.CTkFrame(banner, fg_color="transparent")
        banner_inner.pack(fill="x", padx=24, pady=16)

        name_col = ctk.CTkFrame(banner_inner, fg_color="transparent")
        name_col.pack(side="left")

        _bebas = ("Bebas Neue", 36) if os.path.exists(str(config.FONT_DIR / config.FONT_DISPLAY)) else ("Arial", 26, "bold")
        _bebas_sm = ("Bebas Neue", 22) if os.path.exists(str(config.FONT_DIR / config.FONT_DISPLAY)) else ("Arial", 16, "bold")

        self._cl_banner_root = ctk.CTkLabel(
            name_col, text="", font=_bebas, text_color=config.HEX_CREAM,
        )
        self._cl_banner_root.pack(anchor="w")

        self._cl_banner_qual = ctk.CTkLabel(
            name_col, text="", font=_bebas_sm, text_color=config.HEX_GOLD,
        )
        self._cl_banner_qual.pack(anchor="w")

        self._cl_banner_tones = ctk.CTkFrame(banner_inner, fg_color="transparent")
        self._cl_banner_tones.pack(side="left", padx=(28, 0), fill="y")

        # ── Voicing cards area ─────────────────────────────
        cards_outer = ctk.CTkFrame(inner, fg_color="transparent")
        cards_outer.pack(fill="x", padx=20, pady=(20, 24))

        ctk.CTkLabel(
            cards_outer, text="VOICINGS",
            font=("Arial", 9, "bold"), text_color="#8fa3bf",
        ).pack(anchor="w", pady=(0, 10))

        self._cl_cards_grid = ctk.CTkFrame(cards_outer, fg_color="transparent")
        self._cl_cards_grid.pack(fill="x")

        for col in range(3):
            self._cl_cards_grid.columnconfigure(col, weight=1, uniform="clcard")

    def _cl_make_key_btn(self, parent, key_info: dict):
        """Create a clickable key button frame with stacked note labels."""
        root = key_info["root"]
        is_acc = key_info["flat"] is not None
        frame = ctk.CTkFrame(
            parent,
            fg_color=config.HEX_NAVY_DEEP if is_acc else config.HEX_NAVY_MID,
            border_color="#1e3d6e", border_width=1,
            corner_radius=8, width=64, height=52 if is_acc else 48,
        )
        frame.pack_propagate(False)

        main_lbl = ctk.CTkLabel(
            frame, text=key_info["display"],
            font=("Arial", 16, "bold"), text_color=config.HEX_CREAM,
        )
        main_lbl.pack(pady=(6 if is_acc else 10, 0))

        flat_lbl = None
        if is_acc:
            flat_lbl = ctk.CTkLabel(
                frame, text=key_info["flat"],
                font=("Arial", 9), text_color=config.HEX_GOLD,
            )
            flat_lbl.pack()

        clickables = [frame, main_lbl] + ([flat_lbl] if flat_lbl else [])
        for w in clickables:
            w.bind("<Button-1>", lambda e, r=root: self._cl_set_root(r))
            w.bind("<Enter>",    lambda e, r=root: self._cl_key_hover(r, True))
            w.bind("<Leave>",    lambda e, r=root: self._cl_key_hover(r, False))

        return frame

    def _cl_set_root(self, root: str):
        self._cl_root = root
        self._cl_refresh_all()

    def _cl_set_qual(self, qual: str):
        self._cl_qual = qual
        self._cl_refresh_all()

    def _cl_key_hover(self, root: str, entering: bool):
        if root == self._cl_root:
            return
        frame = self._cl_key_btns.get(root)
        if not frame:
            return
        if entering:
            frame.configure(fg_color="#1a3050", border_color=config.HEX_GOLD)
        else:
            self._cl_apply_key_style(root)

    def _cl_apply_key_style(self, root: str):
        frame = self._cl_key_btns.get(root)
        if not frame:
            return
        k = next((k for k in self._CL_KEYS if k["root"] == root), None)
        if not k:
            return
        selected = (self._cl_root == root)
        is_acc = k["flat"] is not None
        if selected:
            frame.configure(fg_color=config.HEX_GOLD, border_color=config.HEX_GOLD)
            for child in frame.winfo_children():
                child.configure(text_color=config.HEX_NAVY_DEEP)
        else:
            frame.configure(
                fg_color=config.HEX_NAVY_DEEP if is_acc else config.HEX_NAVY_MID,
                border_color="#1e3d6e",
            )
            for child in frame.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    child.configure(
                        text_color=config.HEX_CREAM if child.cget("text") == k["display"] else config.HEX_GOLD
                    )

    def _cl_apply_qual_style(self, qual: str):
        btn = self._cl_qual_btns.get(qual)
        if not btn:
            return
        if self._cl_qual == qual:
            btn.configure(fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP, border_color=config.HEX_GOLD)
        else:
            btn.configure(fg_color=config.HEX_NAVY_MID, text_color="#8fa3bf", border_color="#1e3d6e")

    def _cl_refresh_all(self):
        for k in self._CL_KEYS:
            self._cl_apply_key_style(k["root"])
        for q in self._CL_QUALITIES:
            self._cl_apply_qual_style(q["qual"])
        self._cl_refresh_banner()
        self._cl_refresh_cards()

    def _cl_refresh_banner(self):
        k = next((k for k in self._CL_KEYS if k["root"] == self._cl_root), None)
        root_display = f"{k['display']} / {k['flat']}" if (k and k["flat"]) else self._cl_root
        self._cl_banner_root.configure(text=root_display)
        self._cl_banner_qual.configure(text=self._CL_QUAL_LABELS.get(self._cl_qual, self._cl_qual))

        for w in self._cl_banner_tones.winfo_children():
            w.destroy()

        root_idx = SHARP_NAMES.index(self._cl_root) if self._cl_root in SHARP_NAMES else 0
        intervals = CHORD_INTERVALS.get(self._cl_qual, [0])
        tones = [SHARP_NAMES[(root_idx + iv) % 12] for iv in intervals]

        for tone in tones:
            wrap = ctk.CTkFrame(self._cl_banner_tones, fg_color="#1a2e4a", corner_radius=6)
            wrap.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                wrap, text=tone, font=("Arial", 13, "bold"),
                text_color=config.HEX_GOLD_BRIGHT, fg_color="transparent",
            ).pack(padx=10, pady=4)

    def _cl_refresh_cards(self):
        for w in self._cl_cards_grid.winfo_children():
            w.destroy()
        self._cl_photo_refs.clear()

        chord_name = get_chord_display_name(self._cl_root, self._cl_qual)
        root_semi = note_name_to_semitone(self._cl_root)
        voicings = get_voicings(self._cl_root, self._cl_qual)

        if not voicings:
            ctk.CTkLabel(
                self._cl_cards_grid,
                text="No voicings available for this chord.",
                text_color="#8fa3bf", font=("Arial", 13),
            ).grid(row=0, column=0, columnspan=3, pady=48)
            return

        for idx, voicing in enumerate(voicings):
            card = self._cl_build_card(voicing, chord_name, root_semi)
            card.grid(
                row=0, column=idx,
                padx=(0, 16) if idx < len(voicings) - 1 else 0,
                sticky="n",
            )

    def _cl_build_card(self, voicing: dict, chord_name: str, root_semi: int):
        card = ctk.CTkFrame(
            self._cl_cards_grid,
            fg_color=config.HEX_NAVY_MID,
            border_color=config.HEX_GOLD, border_width=1,
            corner_radius=12,
        )

        ctk.CTkLabel(
            card, text=voicing["label"].upper(),
            font=("Arial", 9, "bold"), text_color=config.HEX_GOLD,
        ).pack(pady=(12, 6), padx=16)

        pil_img = render_chord_diagram(
            frets=voicing["frets"],
            fingers=voicing.get("fingers"),
            chord_name=chord_name,
            root_semitone=root_semi,
            bg_color=None,
            width=220, height=290,
            show_watermark=False,
        )

        # Composite transparent diagram onto white for display
        bg = Image.new("RGBA", pil_img.size, (255, 255, 255, 255))
        bg.paste(pil_img, mask=pil_img.split()[3])
        photo = ImageTk.PhotoImage(bg.convert("RGB"))
        self._cl_photo_refs.append(photo)

        img_container = ctk.CTkFrame(card, fg_color="#ffffff", corner_radius=8)
        img_container.pack(padx=14, pady=(0, 10))
        import tkinter as tk
        tk.Label(
            img_container, image=photo, bd=0, highlightthickness=0, bg="#ffffff",
        ).pack(padx=6, pady=6)

        ctk.CTkButton(
            card, text="Save PNG",
            font=("Arial", 11), height=30,
            fg_color="transparent", text_color="#8fa3bf",
            border_color="#1e3d6e", border_width=1,
            hover_color=config.HEX_GOLD, corner_radius=6,
            command=lambda v=voicing, cn=chord_name, rs=root_semi: self._cl_save_voicing(v, cn, rs),
        ).pack(padx=14, pady=(0, 14), fill="x")

        return card

    def _cl_save_voicing(self, voicing: dict, chord_name: str, root_semi: int):
        from tkinter import filedialog
        slug = (
            voicing["label"]
            .replace(" ", "-").replace("·", "").replace("(", "").replace(")", "")
            .lower().strip("-")
        )
        out_dir = config.OUTPUT_DIR / "chords"
        out_dir.mkdir(parents=True, exist_ok=True)

        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")],
            initialfile=f"{chord_name}-{slug}.png",
            initialdir=str(out_dir),
            title="Save Chord Diagram",
        )
        if not path:
            return

        img = render_chord_diagram(
            frets=voicing["frets"],
            fingers=voicing.get("fingers"),
            chord_name=chord_name,
            root_semitone=root_semi,
            bg_color=config.NAVY_DEEP,
            width=600, height=800,
            show_watermark=True,
        )
        flat = Image.new("RGB", img.size, config.NAVY_DEEP)
        flat.paste(img, mask=img.split()[3])
        flat.save(path, "PNG")
        self._set_status(f"Saved: {path}")

    # ── Audio ──────────────────────────────────────────────

    def _bpm_to_note_ms(self):
        """Convert current BPM selection to note duration in ms (one note per beat)."""
        try:
            bpm = int(self.tempo_var.get())
        except (ValueError, AttributeError):
            bpm = 100
        return 60000 / max(20, min(400, bpm))  # one note per beat

    def _rebuild_direction_controls(self, prefix, labels, options, default):
        """
        Clear and repopulate the per-item direction controls for a progression panel.

        prefix:  "prog", "scale_prog", or "arp_prog"
        labels:  list of short strings to identify each item (e.g. "I  Cmaj7")
        options: allowed direction strings (e.g. ["Asc", "Desc", "Asc + Desc"])
        default: initial value for each new dropdown
        """
        dir_frame = getattr(self, f"_{prefix}_dir_frame", None)
        if dir_frame is None:
            return

        for w in dir_frame.winfo_children():
            w.destroy()

        new_vars = []
        for label in labels:
            row = ctk.CTkFrame(dir_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row, text=label[:16], width=86, anchor="w",
                text_color=config.HEX_CREAM, font=("Arial", 10),
            ).pack(side="left")
            var = ctk.StringVar(value=default)
            ctk.CTkOptionMenu(
                row, variable=var, values=options,
                width=110, height=24,
                fg_color=config.HEX_NAVY_DEEP,
                button_color=config.HEX_NAVY_LIGHT,
                button_hover_color=config.HEX_GOLD,
                dropdown_fg_color=config.HEX_NAVY_MID,
            ).pack(side="left", padx=(4, 0))
            new_vars.append(var)

        setattr(self, f"_{prefix}_dir_vars", new_vars)

    def _parse_play_style(self):
        """Return (play_style, strum_direction) from the play style dropdown."""
        raw = getattr(self, "play_style_var", None)
        val = raw.get() if raw else "Strum Down"
        if val == "Strum Up":
            return "strum", "up"
        elif val == "Arpeggiate":
            return "arpeggio", "down"
        elif val == "Arpeggiate + Strum":
            return "arpeggio_strum", "down"
        else:  # "Strum Down" or legacy "down"/"up"
            direction = "up" if val == "up" else "down"
            return "strum", direction


    def _apply_tone_settings(self):
        """Push GUI slider values into the audio engine's TONE_SETTINGS dict."""
        import audio.engine as _eng
        _eng.TONE_SETTINGS["attack"]     = self.tone_attack_var.get()
        _eng.TONE_SETTINGS["decay"]      = self.tone_decay_var.get()
        _eng.TONE_SETTINGS["brightness"] = self.tone_brightness_var.get()
        _eng.TONE_SETTINGS["warmth"]     = self.tone_warmth_var.get()
        _eng.TONE_SETTINGS["harmonics"]  = self.tone_harmonics_var.get()
        _eng.TONE_SETTINGS["body"]       = self.tone_body_var.get()
        _eng.TONE_SETTINGS["reverb"]     = self.tone_reverb_var.get()




    # ── Image Export ───────────────────────────────────────



    # ── Tab Export ─────────────────────────────────────────




    # ── Video Export ────────────────────────────────────────

    def _video_display_kwargs(self):
        """Return current display setting values for video export (all modes)."""
        mode = self.mode_var.get() if hasattr(self, "mode_var") else "Chord"

        # Pick the right barre/display vars depending on active mode
        if mode in ("Progression",):
            dot_label   = self.prog_dot_label_var.get()   if hasattr(self, "prog_dot_label_var")   else "note"
            show_barre  = self.prog_show_barre_var.get()  if hasattr(self, "prog_show_barre_var")  else True
            barre_style = ("arch" if hasattr(self, "prog_barre_style_var")
                           and self.prog_barre_style_var.get() == "Arch" else "rect")
            show_str    = self.prog_show_string_names_var.get()  if hasattr(self, "prog_show_string_names_var")  else True
            show_fng    = self.prog_show_finger_numbers_var.get() if hasattr(self, "prog_show_finger_numbers_var") else True
        elif mode in ("Triads",):
            dot_label   = self.triads_dot_label_var.get()  if hasattr(self, "triads_dot_label_var")  else "note"
            show_barre  = self.triads_show_barre_var.get() if hasattr(self, "triads_show_barre_var") else True
            barre_style = ("arch" if hasattr(self, "triads_barre_style_var")
                           and self.triads_barre_style_var.get() == "Arch" else "rect")
            show_str    = self.triads_show_string_names_var.get() if hasattr(self, "triads_show_string_names_var") else True
            show_fng    = True
        else:  # Chord and everything else
            dot_label   = self.dot_label_var.get()   if hasattr(self, "dot_label_var")   else "note"
            show_barre  = self.show_barre_var.get()  if hasattr(self, "show_barre_var")  else True
            barre_style = ("arch" if hasattr(self, "barre_style_var")
                           and self.barre_style_var.get() == "Arch" else "rect")
            show_str    = self.show_string_names_var.get()  if hasattr(self, "show_string_names_var")  else True
            show_fng    = self.show_finger_numbers_var.get() if hasattr(self, "show_finger_numbers_var") else True

        return dict(
            dot_label=dot_label,
            show_barre=show_barre,
            barre_style=barre_style,
            show_string_names=show_str,
            show_finger_numbers=show_fng,
        )

    def _snapshot_current_state(self):
        """
        Capture all UI state needed to export the current diagram as a video.
        Returns a dict, or None if there is nothing to export.
        """
        if (not self._current_frets and not self._current_scale_notes
                and not self._current_progression
                and self._current_scale_prog_items is None
                and self._current_arp_prog_items is None):
            return None

        snap = dict(
            name=self._current_name or "video",
            tone=self.tone_var.get(),
            note_ms=self._bpm_to_note_ms(),
            disp=self._video_display_kwargs(),
            portrait=self.video_portrait_var.get() if hasattr(self, "video_portrait_var") else False,
            with_tab=self.video_with_tab_var.get() if hasattr(self, "video_with_tab_var") else False,
            # mode-specific state
            frets=list(self._current_frets) if self._current_frets else None,
            fingers=list(getattr(self, "_current_fingers", None) or []) or None,
            root_semitone=getattr(self, "_current_root_semitone", None),
            scale_notes=list(self._current_scale_notes) if self._current_scale_notes else None,
            is_arpeggio=self._current_is_arpeggio,
            progression=list(self._current_progression) if self._current_progression else None,
            prog_title=self._current_prog_title,
            scale_prog_items=list(self._current_scale_prog_items) if self._current_scale_prog_items else None,
            arp_prog_items=list(self._current_arp_prog_items) if self._current_arp_prog_items else None,
            # play settings
            play_style_raw=self._parse_play_style(),
            show_muted_x=self.show_muted_x_var.get() if hasattr(self, "show_muted_x_var") else True,
            show_open_o=self.show_open_o_var.get() if hasattr(self, "show_open_o_var") else True,
            invert=self.invert_var.get() if hasattr(self, "invert_var") else False,
            prog_duration=getattr(self, "prog_duration_var", None) and self.prog_duration_var.get() or 2.0,
            prog_strum_dirs=[v.get() for v in getattr(self, "_prog_dir_vars", [])],
            scale_prog_pos=int(self._scale_prog_pos_var.get()) if hasattr(self, "_scale_prog_pos_var") else 1,
            scale_prog_duration=int(self._scale_prog_duration_var.get() * 1000) if hasattr(self, "_scale_prog_duration_var") else 2000,
            scale_prog_dirs=[v.get() for v in getattr(self, "_scale_prog_dir_vars", [])],
            arp_prog_pos=int(self._arp_prog_pos_var.get()) if hasattr(self, "_arp_prog_pos_var") else 1,
            arp_prog_duration=int(self._arp_prog_duration_var.get() * 1000) if hasattr(self, "_arp_prog_duration_var") else 2000,
            arp_prog_dirs=[v.get() for v in getattr(self, "_arp_prog_dir_vars", [])],
        )
        import copy
        snap['render_spec'] = copy.deepcopy(self._current_image.info.get('render_spec')) if self._current_image else None
        snap['instrument'] = self._instrument_settings()
        snap['volume'] = self.volume_var.get() if hasattr(self, 'volume_var') else .8
        snap['tone_settings'] = {key: getattr(self, 'tone_'+key+'_var').get()
                                 for key in ('attack','decay','brightness','warmth','harmonics','body','reverb')}
        return snap






    # ── Keyboard helpers ────────────────────────────────────

    def _on_space(self, event):
        """Play audio on Space, unless focus is in a text entry."""
        widget = self.focus_get()
        if widget and widget.winfo_class() in ("Entry", "CTkEntry"):
            return  # let the entry handle it
        self._play_audio()

    # ── Progress bar helpers ─────────────────────────────────

    def _show_progress(self, indeterminate=True):
        """Show the progress bar in the export bar header."""
        self._progress_bar.pack(side="right", padx=(0, 8))
        if indeterminate:
            self._progress_bar.configure(mode="indeterminate")
            self._progress_bar.start()
        else:
            self._progress_bar.configure(mode="determinate")
            self._progress_bar.set(0)

    def _hide_progress(self):
        """Hide and stop the progress bar."""
        try:
            self._progress_bar.stop()
        except Exception:
            pass
        self._progress_bar.pack_forget()

    # ── History ─────────────────────────────────────────────


    def _refresh_history_panel(self):
        """Rebuild the recent-history list widgets."""
        for w in self._history_list_frame.winfo_children():
            w.destroy()

        if not self._history:
            ctk.CTkLabel(self._history_list_frame, text="(none yet)",
                         text_color=config.HEX_CREAM, font=("Arial", 11)).pack(anchor="w")
            return

        for snap in self._history:
            row = ctk.CTkFrame(self._history_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            label = snap.get("label", "—")
            ctk.CTkButton(
                row, text=label, anchor="w", height=26,
                fg_color="transparent", text_color=config.HEX_CREAM,
                hover_color=config.HEX_NAVY_LIGHT, font=("Arial", 11),
                command=lambda s=snap: self._restore_snapshot(s),
            ).pack(fill="x")


    def _restore_legacy_snapshot(self, snap: dict):
        """Restore UI state from a history/favorite snapshot."""
        mode = snap.get("mode", "Chord")
        self._set_mode(mode)
        if mode == "Chord":
            self.root_var.set(snap.get("root", "A"))
            self.quality_var.set(snap.get("quality", "Minor"))
            self._update_chord()
            voicing = snap.get("voicing")
            if voicing:
                self.voicing_var.set(voicing)
                self._update_chord()
        elif mode == "Scale":
            self.scale_root_var.set(snap.get("root", "A"))
            self.scale_type_var.set(snap.get("scale", "Pentatonic Minor"))
            self.scale_view_var.set(snap.get("view", "Full Fretboard"))
            self._update_scale()
        elif mode == "Arpeggio":
            self.arp_root_var.set(snap.get("root", "A"))
            self.arp_type_var.set(snap.get("arp_type", "Minor"))
            self.arp_view_var.set(snap.get("view", "Full Fretboard"))
            self._update_arpeggio()
        else:
            self.prog_root_var.set(snap.get("root", "C"))
            saved_name = snap.get("prog_name", ALL_PROG_NAMES[0])
            if saved_name not in ALL_PROG_NAMES:
                saved_name = ALL_PROG_NAMES[0]
            self.prog_name_var.set(saved_name)
            self.prog_custom_var.set(snap.get("prog_custom", ""))
            self._update_progression()

    # ══════════════════════════════════════════════════════════
    #  CHORD IDENTIFIER
    # ══════════════════════════════════════════════════════════


    # ── Chord detection ───────────────────────────────────────




    # ── Premium PIL rendering ─────────────────────────────────



    # ── Click handling ────────────────────────────────────────




    # ── Control callbacks ─────────────────────────────────────





    # ── PNG export ────────────────────────────────────────────

    # ── Audio ─────────────────────────────────────────────────




    # ── PNG Export ────────────────────────────────────────────





    # ── Favorites ────────────────────────────────────────────



    def _add_favorite(self):
        if not self._current_name:
            self._set_status("Nothing to save — generate a diagram first")
            return
        snap = self._snapshot()
        # Don't duplicate
        for fav in self._favorites:
            if fav == snap:
                self._set_status(f"Already in favorites: {snap['label']}")
                return
        self._favorites.insert(0, snap)
        self._save_favorites()
        self._refresh_favorites_panel()
        self._set_status(f"Saved to favorites: {snap['label']}")

    def _remove_favorite(self, snap: dict):
        self._favorites = [f for f in self._favorites
                           if f != snap]
        self._save_favorites()
        self._refresh_favorites_panel()

    def _refresh_favorites_panel(self):
        """Rebuild the favorites list widgets."""
        for w in self._fav_list_frame.winfo_children():
            w.destroy()

        if not self._favorites:
            ctk.CTkLabel(self._fav_list_frame, text="(none saved)",
                         text_color=config.HEX_CREAM, font=("Arial", 11)).pack(anchor="w")
            return

        for fav in self._favorites:
            row = ctk.CTkFrame(self._fav_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkButton(
                row, text=fav.get("label", "—"), anchor="w", height=26,
                fg_color="transparent", text_color=config.HEX_GOLD,
                hover_color=config.HEX_NAVY_LIGHT, font=("Arial", 11),
                command=lambda f=fav: self._restore_snapshot(f),
            ).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(
                row, text="✕", width=26, height=26,
                fg_color="transparent", text_color=config.HEX_CREAM,
                hover_color="#8b2222", font=("Arial", 10),
                command=lambda f=fav: self._remove_favorite(f),
            ).pack(side="right")

    # ── Status ─────────────────────────────────────────────



def _document_property(name):
    return property(lambda self: getattr(self.document, name),
                    lambda self, value: setattr(self.document, name, value))

for _field in CurrentDocument.__dataclass_fields__:
    setattr(DiagramStudioApp, '_current_'+_field, _document_property(_field))


def run():
    """Launch the GUI application."""
    app = DiagramStudioApp()
    app.mainloop()


if __name__ == "__main__":
    run()
