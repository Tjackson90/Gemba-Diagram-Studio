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

try:
    import customtkinter as ctk
except ImportError:
    print("customtkinter not found. Install with: pip install customtkinter")
    print("Falling back to basic tkinter...")
    import tkinter as ctk
    ctk.CTk = ctk.Tk
    ctk.CTkFrame = ctk.Frame
    ctk.CTkLabel = ctk.Label
    ctk.CTkButton = ctk.Button
    ctk.CTkOptionMenu = ctk.OptionMenu
    ctk.CTkEntry = ctk.Entry
    ctk.CTkTabview = None
    ctk.set_appearance_mode = lambda x: None
    ctk.set_default_color_theme = lambda x: None

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


def _mode_for_prog(prog_name="", custom=""):
    """Auto-detect major/minor from progression name or custom roman string."""
    if custom:
        first = custom.strip().replace(",", "-").split("-")[0].strip()
        return "minor" if first and first[0].islower() else "major"
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


class DiagramStudioApp(ctk.CTk):
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
        self._favorites_file = config.OUTPUT_DIR / "favorites.json"
        self._favorites = self._load_favorites()

        self._build_ui()

        # ── Keyboard shortcuts ─────────────────────────────
        self.bind_all("<Control-s>", lambda e: self._save_png_as())
        self.bind_all("<Control-S>", lambda e: self._save_png_as())
        # Space plays audio (only when focus is NOT in an entry widget)
        self.bind_all("<space>", self._on_space)

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
                          **_menu_kw, command=lambda _: self._update_chord(),
                          ).grid(row=0, column=1, sticky="ew")

        self.quality_var = ctk.StringVar(value="Minor")
        r = _lrow(sel_card, "Quality:")
        ctk.CTkOptionMenu(r, variable=self.quality_var, values=CHORD_QUALITIES,
                          **_menu_kw, command=lambda _: self._update_chord(),
                          ).grid(row=0, column=1, sticky="ew")

        self.voicing_var = ctk.StringVar(value="1")
        r = _lrow(sel_card, "Voicing:")
        self.voicing_menu = ctk.CTkOptionMenu(r, variable=self.voicing_var, values=["1"],
                                              **_menu_kw, command=lambda _: self._update_chord())
        self.voicing_menu.grid(row=0, column=1, sticky="ew")
        ctk.CTkFrame(sel_card, height=4, fg_color="transparent").pack()

        # Diagram options card
        diag_card = _card(self.chord_frame, "DIAGRAM OPTIONS")
        self.dot_label_var = ctk.StringVar(value="finger")
        r = _lrow(diag_card, "Dot label:")
        ctk.CTkOptionMenu(r, variable=self.dot_label_var, values=["note", "finger", "none"],
                          **_menu_kw, command=lambda _: self._update_chord(),
                          ).grid(row=0, column=1, sticky="ew")

        def _make_checkbox(parent, text, var):
            try:
                return ctk.CTkCheckBox(
                    parent, text=text, variable=var,
                    text_color=config.HEX_CREAM, font=("Arial", 11),
                    fg_color=config.HEX_GOLD, hover_color=config.HEX_GOLD_BRIGHT,
                    checkmark_color=config.HEX_NAVY_DEEP,
                    command=self._update_chord,
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
                command=lambda _: self._update_chord(),
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
                          **_menu_kw, command=lambda _: self._update_scale(),
                          ).grid(row=0, column=1, sticky="ew")

        self.scale_type_var = ctk.StringVar(value="Pentatonic Minor")
        r = _lrow(scale_card, "Scale:")
        self._scale_type_menu = ctk.CTkOptionMenu(
            r, variable=self.scale_type_var, values=SCALE_NAMES,
            **_menu_kw, command=lambda _: self._update_scale(),
        )
        self._scale_type_menu.grid(row=0, column=1, sticky="ew")

        self.scale_view_var = ctk.StringVar(value="Full Fretboard")
        r = _lrow(scale_card, "View:")
        ctk.CTkOptionMenu(
            r, variable=self.scale_view_var,
            values=["Full Fretboard",
                    "Position 1", "Position 2", "Position 3", "Position 4", "Position 5"],
            **_menu_kw, command=lambda _: self._update_scale(),
        ).grid(row=0, column=1, sticky="ew")

        self.invert_var = ctk.BooleanVar(value=True)
        try:
            ctk.CTkCheckBox(
                scale_card, text="Invert fretboard (low E at top)",
                variable=self.invert_var,
                text_color=config.HEX_CREAM, font=("Arial", 11),
                fg_color=config.HEX_GOLD, hover_color=config.HEX_GOLD_BRIGHT,
                checkmark_color=config.HEX_NAVY_DEEP,
                command=self._update_scale,
            ).pack(padx=10, anchor="w", pady=(4, 8))
        except Exception:
            pass

        # ── Arpeggio controls frame (hidden initially) ─────
        self.arp_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")

        arp_card = _card(self.arp_frame, "ARPEGGIO")
        self.arp_root_var = ctk.StringVar(value="A")
        r = _lrow(arp_card, "Root:")
        ctk.CTkOptionMenu(r, variable=self.arp_root_var, values=ROOT_NAMES,
                          **_menu_kw, command=lambda _: self._update_arpeggio(),
                          ).grid(row=0, column=1, sticky="ew")

        self.arp_type_var = ctk.StringVar(value="Minor")
        r = _lrow(arp_card, "Type:")
        self._arp_type_menu = ctk.CTkOptionMenu(
            r, variable=self.arp_type_var, values=ARPEGGIO_NAMES,
            **_menu_kw, command=lambda _: self._update_arpeggio(),
        )
        self._arp_type_menu.grid(row=0, column=1, sticky="ew")

        self.arp_view_var = ctk.StringVar(value="Full Fretboard")
        r = _lrow(arp_card, "View:")
        ctk.CTkOptionMenu(
            r, variable=self.arp_view_var,
            values=["Full Fretboard", "Position 1", "Position 2", "Position 3", "Position 4"],
            **_menu_kw, command=lambda _: self._update_arpeggio(),
        ).grid(row=0, column=1, sticky="ew")
        ctk.CTkFrame(arp_card, height=8, fg_color="transparent").pack()

        # ── Progression controls frame (hidden initially) ──
        self.prog_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")

        prog_card = _card(self.prog_frame, "CHORD PROGRESSION")
        self.prog_root_var = ctk.StringVar(value="C")
        r = _lrow(prog_card, "Key Root:")
        ctk.CTkOptionMenu(r, variable=self.prog_root_var, values=ROOT_NAMES,
                          **_menu_kw, command=lambda _: self._update_progression(),
                          ).grid(row=0, column=1, sticky="ew")

        self.prog_quality_var = ctk.StringVar(value="Auto")
        r = _lrow(prog_card, "Quality:")
        ctk.CTkOptionMenu(
            r, variable=self.prog_quality_var,
            values=["Auto", "Major", "Minor", "Maj7", "Dom7", "Min7", "7",
                    "Dim", "Dim7", "Aug", "Sus2", "Sus4", "Add9", "Min7b5"],
            **_menu_kw, command=lambda _: self._update_progression(),
        ).grid(row=0, column=1, sticky="ew")

        self.prog_name_var = ctk.StringVar(value=ALL_PROG_NAMES[0])
        r = _lrow(prog_card, "Prog:")
        self.prog_name_menu = ctk.CTkOptionMenu(
            r, variable=self.prog_name_var, values=ALL_PROG_NAMES,
            **_menu_kw, command=lambda _: self._update_progression(),
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
            command=self._update_progression,
        ).pack(padx=8, fill="x", pady=(0, 8))

        # Diagram options card
        diag2_card = _card(self.prog_frame, "DIAGRAM OPTIONS")
        self.prog_dot_label_var = ctk.StringVar(value="note")
        r = _lrow(diag2_card, "Dot label:")
        ctk.CTkOptionMenu(r, variable=self.prog_dot_label_var, values=["note", "finger", "none"],
                          **_menu_kw, command=lambda _: self._update_progression(),
                          ).grid(row=0, column=1, sticky="ew")

        def _prog_checkbox(parent, text, var):
            try:
                return ctk.CTkCheckBox(
                    parent, text=text, variable=var,
                    text_color=config.HEX_CREAM, font=("Arial", 11),
                    fg_color=config.HEX_GOLD, hover_color=config.HEX_GOLD_BRIGHT,
                    checkmark_color=config.HEX_NAVY_DEEP,
                    command=self._update_progression,
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
                command=lambda _: self._update_progression(),
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

        bar = ctk.CTkFrame(self, fg_color=config.HEX_NAVY_MID, height=95)
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
        """Return (width, height) from custom fields if filled, else defaults."""
        try:
            w = int(self.custom_w_var.get())
            h = int(self.custom_h_var.get())
            if w > 0 and h > 0:
                return w, h
        except (ValueError, AttributeError):
            pass
        return default_w, default_h

    def _update_chord(self):
        """Regenerate chord diagram from current selections."""
        try:
            self._update_chord_inner()
        except Exception as e:
            self._set_status(f"Error generating chord: {e}")

    def _update_chord_inner(self):
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
        root    = getattr(self, "_scale_prog_root_var").get().split("/")[0]
        custom  = getattr(self, "_scale_prog_custom_var").get().strip()
        mode    = _mode_for_prog(getattr(self, "_scale_prog_name_var").get(), custom)
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
        root    = getattr(self, "_arp_prog_root_var").get().split("/")[0]
        custom  = getattr(self, "_arp_prog_custom_var").get().strip()
        mode    = _mode_for_prog(getattr(self, "_arp_prog_name_var").get(), custom)
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
        root = self.prog_root_var.get().split("/")[0]
        custom = self.prog_custom_var.get().strip()
        prog_name_peek = self.prog_name_var.get()
        mode = _mode_for_prog(prog_name_peek, custom)

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
        # Fit to preview area
        pw = self.preview_frame.winfo_width() or 700
        ph = self.preview_frame.winfo_height() or 600

        scale = min(pw / img.width, ph / img.height, 1.0)
        display_w = max(int(img.width * scale), 100)
        display_h = max(int(img.height * scale), 100)

        display_img = img.resize((display_w, display_h), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(display_img)

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
            **_menu_kw, command=lambda _: self._update_triads(),
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
            **_menu_kw, command=lambda _: self._update_triads(),
        ).grid(row=0, column=1, sticky="ew")

        # Custom quality row (shown only when Scale = "Custom")
        # Created after voicing row so we can reference it with pack(before=...)
        self.triads_quality_var = ctk.StringVar(value="Aug")
        self._triads_quality_row = _lrow(main_card, "Quality:")
        ctk.CTkOptionMenu(
            self._triads_quality_row, variable=self.triads_quality_var,
            values=TRIAD_QUALITIES,
            **_menu_kw, command=lambda _: self._update_triads(),
        ).grid(row=0, column=1, sticky="ew")
        self._triads_quality_row.pack_forget()   # hidden by default

        ctk.CTkButton(
            main_card, text="Generate", height=32,
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT,
            command=self._update_triads,
        ).pack(padx=8, fill="x", pady=(0, 8))

        # Display settings card
        disp_card = _card("DISPLAY")

        self.triads_dot_label_var = ctk.StringVar(value="note")
        r = _lrow(disp_card, "Dot label:")
        ctk.CTkOptionMenu(
            r, variable=self.triads_dot_label_var, values=["note", "finger", "none"],
            **_menu_kw, command=lambda _: self._update_triads(),
        ).grid(row=0, column=1, sticky="ew")

        self.triads_show_barre_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            disp_card, text="Show barre indicator",
            variable=self.triads_show_barre_var,
            font=("Arial", 10), text_color=config.HEX_CREAM,
            checkbox_width=16, checkbox_height=16,
            command=self._update_triads,
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
                command=lambda _: self._update_triads(),
            ).pack(padx=10, fill="x", pady=(2, 4))
        except Exception:
            pass

        self.triads_show_string_names_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            disp_card, text="Show string names",
            variable=self.triads_show_string_names_var,
            font=("Arial", 10), text_color=config.HEX_CREAM,
            checkbox_width=16, checkbox_height=16,
            command=self._update_triads,
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
        """Convert current BPM selection to note duration in ms (eighth notes)."""
        try:
            bpm = int(self.tempo_var.get())
        except (ValueError, AttributeError):
            bpm = 100
        return int(60000 / bpm)  # eighth notes at given BPM

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

    def _build_audio(self, tone):
        """Generate audio for whatever is currently displayed."""
        if self._current_frets:
            play_style, strum_dir = self._parse_play_style()
            return generate_chord_audio(
                self._current_frets,
                tone=tone,
                play_style=play_style,
                strum_direction=strum_dir,
            )
        elif self._current_progression:
            dur = getattr(self, "prog_duration_var", None)
            chord_dur = dur.get() if dur else 2.0
            play_style, default_dir = self._parse_play_style()
            dir_vars = getattr(self, "_prog_dir_vars", [])
            strum_dirs = [
                "up" if (dir_vars[i].get() == "Up") else "down"
                for i in range(len(self._current_progression))
                if i < len(dir_vars)
            ]
            # Pad with default if fewer vars than chords
            while len(strum_dirs) < len(self._current_progression):
                strum_dirs.append(default_dir)
            play_styles = [play_style] * len(self._current_progression)
            return generate_progression_audio(
                self._current_progression,
                tone=tone,
                chord_duration_s=chord_dur,
                strum_directions=strum_dirs,
                play_styles=play_styles,
            )
        elif self._current_scale_prog_items is not None:
            import numpy as np
            from data.scales import get_full_fretboard_scale
            note_ms = self._bpm_to_note_ms()
            dir_vars = getattr(self, "_scale_prog_dir_vars", [])
            segments = []
            for idx, item in enumerate(self._current_scale_prog_items):
                d = dir_vars[idx].get() if idx < len(dir_vars) else "Asc"
                asc  = d in ("Asc", "Asc + Desc")
                desc = d in ("Desc", "Asc + Desc")
                notes = get_full_fretboard_scale(item["chord_root"], item["scale_name"])
                seg = generate_scale_audio(
                    notes, tone=tone, note_duration_ms=note_ms,
                    ascending=asc, descending=desc, root_to_root=True,
                )
                segments.append(seg)
            if not segments:
                return None
            return np.concatenate(segments)
        elif self._current_arp_prog_items is not None:
            import numpy as np
            from data.arpeggios import get_full_fretboard_arpeggio
            note_ms = self._bpm_to_note_ms()
            dir_vars = getattr(self, "_arp_prog_dir_vars", [])
            segments = []
            for idx, item in enumerate(self._current_arp_prog_items):
                d = dir_vars[idx].get() if idx < len(dir_vars) else "Asc"
                asc  = d in ("Asc", "Asc + Desc")
                desc = d in ("Desc", "Asc + Desc")
                notes = get_full_fretboard_arpeggio(item["chord_root"], item["arp_name"])
                seg = generate_scale_audio(
                    notes, tone=tone, note_duration_ms=note_ms,
                    ascending=asc, descending=desc, root_to_root=True,
                    stop_at_high_e_root=True,
                )
                segments.append(seg)
            if not segments:
                return None
            return np.concatenate(segments)
        elif self._current_scale_notes:
            return generate_scale_audio(
                self._current_scale_notes,
                tone=tone,
                note_duration_ms=self._bpm_to_note_ms(),
                ascending=True,
                descending=True,
                root_to_root=True,
                stop_at_high_e_root=self._current_is_arpeggio,
            )
        return None

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

    def _play_audio(self):
        """Play audio for current chord or scale."""
        tone = self.tone_var.get()
        volume = getattr(self, "volume_var", None)
        vol = volume.get() if volume else 0.8

        def _play():
            self._set_status("Playing...")
            self.after(0, lambda: self._show_progress(indeterminate=True))
            try:
                audio = self._build_audio(tone)
                if audio is None:
                    self._set_status("Nothing to play — select a chord or scale first")
                    return
                self._current_audio = audio
                play_audio(audio, volume=vol)
            except Exception as e:
                self._set_status(f"Playback error: {e}")
            finally:
                self.after(0, self._hide_progress)
                if self.status_label.cget("text") == "Playing...":
                    self.after(0, lambda: self._set_status(""))

        threading.Thread(target=_play, daemon=True).start()

    def _stop_audio(self):
        """Stop currently playing audio."""
        stop_audio()
        self._set_status("Stopped")

    def _export_audio(self, fmt):
        """Export current audio to file."""
        import numpy as np
        tone = self.tone_var.get()
        name = self._current_name or "untitled"

        audio = self._build_audio(tone)
        if audio is None:
            self._set_status("Nothing to export — select a chord or scale first")
            return

        # Apply volume slider to export (same as playback)
        volume = getattr(self, "volume_var", None)
        vol = volume.get() if volume else 0.8
        audio = np.clip(audio * vol, -1.0, 1.0)

        output_dir = config.OUTPUT_DIR / "audio"
        if fmt == "wav":
            path = export_wav(audio, output_dir / f"{name}.wav")
        else:
            path = export_mp3(audio, output_dir / f"{name}.mp3")

        if path:
            self._set_status(f"Saved: {path}")
        else:
            self._set_status("Export failed — check dependencies")

    # ── Image Export ───────────────────────────────────────

    def _save_png_as(self):
        """Open Save As dialog then export current diagram as PNG."""
        if self._current_image is None:
            self._set_status("Nothing to export — generate a diagram first")
            return

        name = self._current_name or "diagram"
        res = self.res_var.get()
        bg = self.bg_var.get()
        default_name = f"{name}_{res}_{bg}.png"

        path = filedialog.asksaveasfilename(
            title="Save PNG As",
            initialdir=str(config.OUTPUT_DIR),
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not path:
            return

        saved = export_diagram(self._current_image, path, res, bg)
        self._set_status(f"Saved: {saved}")

    def _export_all(self):
        """Export current diagram in all resolutions and backgrounds."""
        if self._current_image is None:
            self._set_status("Nothing to export — generate a diagram first")
            return

        name = self._current_name or "diagram"
        sub = "chords" if self._current_frets else "scales"
        output_dir = config.OUTPUT_DIR / sub

        paths = batch_export(self._current_image, name, output_dir)
        self._set_status(f"Exported {len(paths)} files to {output_dir}")

    # ── Tab Export ─────────────────────────────────────────

    def _render_tab_image(self):
        """Render the current state as a tab PIL image and return it (or None)."""
        bg_raw = getattr(self, "bg_var", None)
        bg_name = bg_raw.get() if bg_raw else "transparent"
        bg = config.NAVY_DEEP if bg_name == "navy" else None

        if self._current_frets:
            from diagrams.tab_diagram import render_chord_tab
            return render_chord_tab(
                frets=self._current_frets,
                chord_name=self._current_name.replace("_", " "),
                bg_color=bg,
            )
        elif self._current_progression:
            from diagrams.tab_diagram import render_chord_tab
            tab_w, tab_h, gap = 500, 420, 10
            tabs = [render_chord_tab(frets=c["frets"], chord_name=c["display_name"],
                                     bg_color=bg, width=tab_w, height=tab_h)
                    for c in self._current_progression]
            total_w = tab_w * len(tabs) + gap * (len(tabs) - 1)
            img = Image.new("RGBA", (total_w, tab_h), (bg or config.NAVY_DEEP) + (255,))
            for idx, t in enumerate(tabs):
                img.paste(t, (idx * (tab_w + gap), 0))
            return img
        elif self._current_scale_prog_items is not None:
            tab_w, tab_h, gap = 900, 280, 12
            dir_vars = getattr(self, "_scale_prog_dir_vars", [])
            pos_num_var = getattr(self, "_scale_prog_pos_var", None)
            pos_num = int(pos_num_var.get()) if pos_num_var else 1
            tabs = []
            for idx, item in enumerate(self._current_scale_prog_items):
                d = dir_vars[idx].get() if idx < len(dir_vars) else "Asc"
                asc  = d in ("Asc", "Asc + Desc")
                desc = d in ("Desc", "Asc + Desc")
                positions = get_caged_positions(item["chord_root"], item["scale_name"])
                if pos_num <= len(positions):
                    notes = positions[pos_num - 1]["notes"]
                else:
                    notes = get_full_fretboard_scale(item["chord_root"], item["scale_name"])
                tabs.append(render_scale_tab(
                    notes_data=notes, title=item["display_name"],
                    bg_color=bg, width=tab_w, height=tab_h,
                    ascending=asc, descending=desc, root_to_root=True,
                ))
            total_w = tab_w * len(tabs) + gap * (len(tabs) - 1)
            img = Image.new("RGBA", (total_w, tab_h), (bg or config.NAVY_DEEP) + (255,))
            for idx, t in enumerate(tabs):
                img.paste(t, (idx * (tab_w + gap), 0))
            return img
        elif self._current_arp_prog_items is not None:
            tab_w, tab_h, gap = 600, 280, 12
            dir_vars = getattr(self, "_arp_prog_dir_vars", [])
            pos_num_var = getattr(self, "_arp_prog_pos_var", None)
            pos_num = int(pos_num_var.get()) if pos_num_var else 1
            tabs = []
            for idx, item in enumerate(self._current_arp_prog_items):
                d = dir_vars[idx].get() if idx < len(dir_vars) else "Asc"
                asc  = d in ("Asc", "Asc + Desc")
                desc = d in ("Desc", "Asc + Desc")
                positions = get_arpeggio_positions(item["chord_root"], item["arp_name"])
                if pos_num <= len(positions):
                    notes = positions[pos_num - 1]["notes"]
                else:
                    notes = get_full_fretboard_arpeggio(item["chord_root"], item["arp_name"])
                tabs.append(render_scale_tab(
                    notes_data=notes, title=item["display_name"],
                    bg_color=bg, width=tab_w, height=tab_h,
                    ascending=asc, descending=desc, root_to_root=True,
                    stop_at_high_e_root=True,
                ))
            total_w = tab_w * len(tabs) + gap * (len(tabs) - 1)
            img = Image.new("RGBA", (total_w, tab_h), (bg or config.NAVY_DEEP) + (255,))
            for idx, t in enumerate(tabs):
                img.paste(t, (idx * (tab_w + gap), 0))
            return img
        elif self._current_scale_notes:
            return render_scale_tab(
                notes_data=self._current_scale_notes,
                title=self._current_name.replace("_", " "),
                bg_color=bg,
                width=1600,
                height=420,
                ascending=True,
                descending=True,
                root_to_root=True,
                stop_at_high_e_root=self._current_is_arpeggio,
            )
        return None

    def _preview_tab(self):
        """Render the tab and display it in the main preview area."""
        has_content = (
            self._current_frets or self._current_scale_notes
            or self._current_progression
            or self._current_scale_prog_items is not None
            or self._current_arp_prog_items is not None
        )
        if not has_content:
            self._set_status("Nothing to preview — generate a diagram first")
            return

        def _run():
            self.after(0, lambda: self._show_progress(indeterminate=True))
            try:
                img = self._render_tab_image()
                if img:
                    self.after(0, lambda: self._show_preview(img))
                    self.after(0, lambda: self._set_status(
                        "Tab preview — click any Generate button to return to diagram"))
            except Exception as e:
                self.after(0, lambda: self._set_status(f"Tab preview error: {e}"))
            finally:
                self.after(0, self._hide_progress)

        threading.Thread(target=_run, daemon=True).start()

    def _save_tab_as(self):
        """Open Save As dialog then export current diagram as a guitar tab PNG."""
        has_content = (
            self._current_frets or self._current_scale_notes
            or self._current_progression
            or self._current_scale_prog_items is not None
            or self._current_arp_prog_items is not None
        )
        if not has_content:
            self._set_status("Nothing to export — generate a diagram first")
            return

        name = self._current_name or "tab"
        default_name = f"{name}_tab.png"
        path = filedialog.asksaveasfilename(
            title="Save Tab As",
            initialdir=str(config.OUTPUT_DIR),
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not path:
            return

        img = self._render_tab_image()
        if img is None:
            self._set_status("Nothing to export — generate a diagram first")
            return
        img.save(str(path))
        self._set_status(f"Tab saved: {path}")

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
        # Render tab image on UI thread now (PIL object; not JSON-serialisable but fine in-memory)
        snap["tab_img"] = self._render_tab_image() if snap["with_tab"] else None
        return snap

    def _add_to_batch_queue(self):
        """Snapshot current state and add it to the batch export queue."""
        snap = self._snapshot_current_state()
        if snap is None:
            self._set_status("Nothing to queue — generate a diagram first")
            return
        self._batch_queue.append(snap)
        n = len(self._batch_queue)
        self._batch_export_btn.configure(text=f"Export Queue ({n})")
        self._set_status(f"Added to queue: {snap['name']} ({n} item{'s' if n != 1 else ''} total)")

    def _clear_batch_queue(self):
        """Clear all items from the batch export queue."""
        self._batch_queue.clear()
        self._batch_export_btn.configure(text="Export Queue (0)")
        self._set_status("Batch queue cleared")

    def _export_batch_queue(self):
        """Pick an output folder and export all queued items as MP4s."""
        if not self._batch_queue:
            self._set_status("Batch queue is empty — use '+ Queue' to add items")
            return

        out_dir = filedialog.askdirectory(
            title="Select folder for batch video export",
            initialdir=str(config.OUTPUT_DIR),
        )
        if not out_dir:
            return

        import os
        queue = list(self._batch_queue)   # snapshot so UI changes don't interfere
        self._batch_queue.clear()
        self._batch_export_btn.configure(text="Export Queue (0)")

        def _run():
            total = len(queue)
            for idx, snap in enumerate(queue):
                self._set_status(f"Batch export {idx + 1}/{total}: {snap['name']}…")
                self.after(0, self._show_progress)
                try:
                    # Build a unique output path (avoid collisions)
                    base = snap["name"].replace(" ", "_").replace("/", "-")
                    out_path = os.path.join(out_dir, f"{base}.mp4")
                    counter = 2
                    while os.path.exists(out_path):
                        out_path = os.path.join(out_dir, f"{base}_{counter}.mp4")
                        counter += 1

                    self._export_snapshot(snap, out_path)
                except Exception as e:
                    self._set_status(f"Error exporting {snap['name']}: {e}")
            self.after(0, self._hide_progress)
            self._set_status(f"Batch export complete — {total} video{'s' if total != 1 else ''} saved to {out_dir}")

        threading.Thread(target=_run, daemon=True).start()

    def _export_snapshot(self, snap, out_path):
        """Export a single batch-queue snapshot dict to *out_path* (called from worker thread)."""
        import numpy as _np

        tone     = snap["tone"]
        note_ms  = snap["note_ms"]
        disp     = snap["disp"]
        portrait = snap["portrait"]
        tab_img  = snap["tab_img"]
        bg       = config.NAVY_DEEP
        _ps, _sd = snap["play_style_raw"]

        if snap["frets"]:
            audio = generate_chord_audio(
                snap["frets"], tone=tone,
                play_style=_ps, strum_direction=_sd,
                strum_delay_ms=20, arpeggio_delay_ms=note_ms,
            )
            render_kwargs = dict(
                frets=snap["frets"],
                fingers=snap["fingers"],
                chord_name=snap["name"],
                root_semitone=snap["root_semitone"],
                bg_color=bg, width=600, height=800,
                show_watermark=True,
                show_muted_x=snap["show_muted_x"],
                show_open_o=snap["show_open_o"],
                dot_label=disp["dot_label"],
                show_string_names=disp["show_string_names"],
                show_finger_numbers=disp["show_finger_numbers"],
                show_barre=disp["show_barre"],
                barre_style=disp["barre_style"],
                strum_direction=_sd,
            )
            export_chord_video(
                frets=snap["frets"], render_fn=render_chord_diagram,
                render_kwargs=render_kwargs, audio_data=audio,
                output_path=out_path, play_style=_ps,
                strum_delay_ms=20, arpeggio_delay_ms=note_ms,
                portrait=portrait, tab_img=tab_img,
            )

        elif snap["scale_notes"]:
            audio = generate_scale_audio(
                snap["scale_notes"], tone=tone, note_duration_ms=note_ms,
                ascending=True, descending=True, root_to_root=True,
                stop_at_high_e_root=snap["is_arpeggio"],
            )
            render_kwargs = dict(
                scale_notes=snap["scale_notes"], scale_name="", root_name="",
                bg_color=bg, width=1600, height=500,
                invert=snap["invert"],
                ascending=True, descending=True, root_to_root=True,
            )
            export_scale_video(
                notes_data=snap["scale_notes"], render_fn=render_scale_full_fretboard,
                render_kwargs=render_kwargs, audio_data=audio,
                output_path=out_path, note_duration_ms=note_ms,
                portrait=portrait, tab_img=tab_img,
            )

        elif snap["progression"]:
            chord_dur = snap["prog_duration"]
            dir_vars  = snap["prog_strum_dirs"]
            strum_dirs = ["up" if d == "Up" else "down" for d in dir_vars]
            while len(strum_dirs) < len(snap["progression"]):
                strum_dirs.append(_sd)
            audio = generate_progression_audio(
                snap["progression"], tone=tone,
                chord_duration_s=chord_dur, strum_directions=strum_dirs,
            )
            export_progression_video(
                chords=snap["progression"], title=snap["prog_title"],
                audio_data=audio, output_path=out_path,
                chord_duration_ms=int(chord_dur * 1000),
                dot_label=disp["dot_label"], show_barre=disp["show_barre"],
                barre_style=disp["barre_style"],
                show_string_names=disp["show_string_names"],
                show_finger_numbers=disp["show_finger_numbers"],
                portrait=portrait, tab_img=tab_img,
            )

        elif snap["scale_prog_items"]:
            from data.scales import get_full_fretboard_scale
            segs = []
            dirs = snap["scale_prog_dirs"]
            for idx, item in enumerate(snap["scale_prog_items"]):
                d = dirs[idx] if idx < len(dirs) else "Asc"
                asc  = d in ("Asc", "Asc + Desc")
                desc = d in ("Desc", "Asc + Desc")
                notes = get_full_fretboard_scale(item["chord_root"], item["scale_name"])
                segs.append(generate_scale_audio(notes, tone=tone, note_duration_ms=note_ms,
                                                 ascending=asc, descending=desc, root_to_root=True))
            audio = _np.concatenate(segs)
            export_scale_arp_progression_video(
                items=snap["scale_prog_items"], title=snap["prog_title"],
                audio_data=audio, output_path=out_path,
                strip_render_fn=render_scale_progression_strip,
                position_num=snap["scale_prog_pos"],
                item_duration_ms=snap["scale_prog_duration"],
                portrait=portrait, tab_img=tab_img,
            )

        elif snap["arp_prog_items"]:
            from data.arpeggios import get_full_fretboard_arpeggio
            segs = []
            dirs = snap["arp_prog_dirs"]
            for idx, item in enumerate(snap["arp_prog_items"]):
                d = dirs[idx] if idx < len(dirs) else "Asc"
                asc  = d in ("Asc", "Asc + Desc")
                desc = d in ("Desc", "Asc + Desc")
                notes = get_full_fretboard_arpeggio(item["chord_root"], item["arp_name"])
                segs.append(generate_scale_audio(notes, tone=tone, note_duration_ms=note_ms,
                                                 ascending=asc, descending=desc, root_to_root=True,
                                                 stop_at_high_e_root=True))
            audio = _np.concatenate(segs)
            export_scale_arp_progression_video(
                items=snap["arp_prog_items"], title=snap["prog_title"],
                audio_data=audio, output_path=out_path,
                strip_render_fn=render_arpeggio_progression_strip,
                position_num=snap["arp_prog_pos"],
                item_duration_ms=snap["arp_prog_duration"],
                portrait=portrait, tab_img=tab_img,
            )

    def _save_video_as(self):
        """Open Save As dialog then export the current diagram + audio as an MP4 video."""
        if (not self._current_frets and not self._current_scale_notes
                and not self._current_progression
                and self._current_scale_prog_items is None
                and self._current_arp_prog_items is None):
            self._set_status("Nothing to export — generate a diagram first")
            return

        name = self._current_name or "video"
        out_path = filedialog.asksaveasfilename(
            title="Save Video As",
            initialdir=str(config.OUTPUT_DIR),
            initialfile=f"{name}.mp4",
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
        )
        if not out_path:
            return

        tone = self.tone_var.get()
        note_ms = self._bpm_to_note_ms()
        bg = config.NAVY_DEEP

        # Snapshot display settings on the UI thread before handing off
        disp = self._video_display_kwargs()
        portrait = self.video_portrait_var.get() if hasattr(self, "video_portrait_var") else False
        with_tab  = self.video_with_tab_var.get()  if hasattr(self, "video_with_tab_var")  else False
        tab_img   = self._render_tab_image() if with_tab else None

        def _run():
            self._set_status("Rendering video…")
            self.after(0, self._show_progress)

            try:
                if self._current_frets:
                    _ps, _sd = self._parse_play_style()
                    _strum_delay_ms = 20
                    _arp_delay_ms   = note_ms   # BPM-driven arpeggio timing
                    audio = generate_chord_audio(
                        self._current_frets,
                        tone=tone,
                        play_style=_ps,
                        strum_direction=_sd,
                        strum_delay_ms=_strum_delay_ms,
                        arpeggio_delay_ms=_arp_delay_ms,
                    )
                    render_kwargs = dict(
                        frets=self._current_frets,
                        fingers=getattr(self, "_current_fingers", None),
                        chord_name=self._current_name or "",
                        root_semitone=getattr(self, "_current_root_semitone", None),
                        bg_color=bg,
                        width=600,
                        height=800,
                        show_watermark=True,
                        show_muted_x=self.show_muted_x_var.get() if hasattr(self, "show_muted_x_var") else True,
                        show_open_o=self.show_open_o_var.get()   if hasattr(self, "show_open_o_var")   else True,
                        dot_label=disp["dot_label"],
                        show_string_names=disp["show_string_names"],
                        show_finger_numbers=disp["show_finger_numbers"],
                        show_barre=disp["show_barre"],
                        barre_style=disp["barre_style"],
                        strum_direction=_sd,
                    )
                    path = export_chord_video(
                        frets=self._current_frets,
                        render_fn=render_chord_diagram,
                        render_kwargs=render_kwargs,
                        audio_data=audio,
                        output_path=out_path,
                        play_style=_ps,
                        strum_delay_ms=_strum_delay_ms,
                        arpeggio_delay_ms=_arp_delay_ms,
                        portrait=portrait,
                        tab_img=tab_img,
                    )

                elif self._current_scale_notes:
                    audio = generate_scale_audio(
                        self._current_scale_notes,
                        tone=tone,
                        note_duration_ms=note_ms,
                        ascending=True,
                        descending=True,
                        root_to_root=True,
                        stop_at_high_e_root=self._current_is_arpeggio,
                    )
                    invert = self.invert_var.get() if hasattr(self, "invert_var") else False
                    render_kwargs = dict(
                        scale_notes=self._current_scale_notes,
                        scale_name="",
                        root_name="",
                        bg_color=bg,
                        width=1600,
                        height=500,
                        invert=invert,
                        ascending=True,
                        descending=True,
                        root_to_root=True,
                    )
                    path = export_scale_video(
                        notes_data=self._current_scale_notes,
                        render_fn=render_scale_full_fretboard,
                        render_kwargs=render_kwargs,
                        audio_data=audio,
                        output_path=out_path,
                        note_duration_ms=note_ms,
                        portrait=portrait,
                        tab_img=tab_img,
                    )

                elif self._current_progression:
                    dur = getattr(self, "prog_duration_var", None)
                    chord_dur = dur.get() if dur else 2.0
                    dir_vars = getattr(self, "_prog_dir_vars", [])
                    strum_dirs = [
                        "up" if (dir_vars[i].get() == "Up") else "down"
                        for i in range(len(self._current_progression))
                        if i < len(dir_vars)
                    ]
                    while len(strum_dirs) < len(self._current_progression):
                        strum_dirs.append(self._parse_play_style()[1])
                    audio = generate_progression_audio(
                        self._current_progression,
                        tone=tone,
                        chord_duration_s=chord_dur,
                        strum_directions=strum_dirs,
                    )
                    path = export_progression_video(
                        chords=self._current_progression,
                        title=self._current_prog_title,
                        audio_data=audio,
                        output_path=out_path,
                        chord_duration_ms=int(chord_dur * 1000),
                        dot_label=disp["dot_label"],
                        show_barre=disp["show_barre"],
                        barre_style=disp["barre_style"],
                        show_string_names=disp["show_string_names"],
                        show_finger_numbers=disp["show_finger_numbers"],
                        portrait=portrait,
                        tab_img=tab_img,
                    )

                elif self._current_scale_prog_items is not None:
                    from data.scales import get_full_fretboard_scale
                    dur = getattr(self, "_scale_prog_duration_var", None)
                    item_dur_ms = int(dur.get() * 1000) if dur else 2000
                    segments = []
                    scale_dir_vars = getattr(self, "_scale_prog_dir_vars", [])
                    for idx, item in enumerate(self._current_scale_prog_items):
                        d = scale_dir_vars[idx].get() if idx < len(scale_dir_vars) else "Asc"
                        asc  = d in ("Asc", "Asc + Desc")
                        desc = d in ("Desc", "Asc + Desc")
                        notes = get_full_fretboard_scale(item["chord_root"], item["scale_name"])
                        seg = generate_scale_audio(notes, tone=tone, note_duration_ms=note_ms,
                                                   ascending=asc, descending=desc, root_to_root=True)
                        segments.append(seg)
                    import numpy as np
                    audio = np.concatenate(segments)
                    pos_num = getattr(self, "_scale_prog_pos_var", None)
                    position_num = int(pos_num.get()) if pos_num else 1
                    title = getattr(self, "_current_prog_title", "")
                    path = export_scale_arp_progression_video(
                        items=self._current_scale_prog_items,
                        title=title,
                        audio_data=audio,
                        output_path=out_path,
                        strip_render_fn=render_scale_progression_strip,
                        position_num=position_num,
                        item_duration_ms=item_dur_ms,
                        portrait=portrait,
                        tab_img=tab_img,
                    )

                elif self._current_arp_prog_items is not None:
                    from data.arpeggios import get_full_fretboard_arpeggio
                    dur = getattr(self, "_arp_prog_duration_var", None)
                    item_dur_ms = int(dur.get() * 1000) if dur else 2000
                    segments = []
                    arp_dir_vars = getattr(self, "_arp_prog_dir_vars", [])
                    for idx, item in enumerate(self._current_arp_prog_items):
                        d = arp_dir_vars[idx].get() if idx < len(arp_dir_vars) else "Asc"
                        asc  = d in ("Asc", "Asc + Desc")
                        desc = d in ("Desc", "Asc + Desc")
                        notes = get_full_fretboard_arpeggio(item["chord_root"], item["arp_name"])
                        seg = generate_scale_audio(notes, tone=tone, note_duration_ms=note_ms,
                                                   ascending=asc, descending=desc, root_to_root=True,
                                                   stop_at_high_e_root=True)
                        segments.append(seg)
                    import numpy as np
                    audio = np.concatenate(segments)
                    pos_num = getattr(self, "_arp_prog_pos_var", None)
                    position_num = int(pos_num.get()) if pos_num else 1
                    title = getattr(self, "_current_prog_title", "")
                    path = export_scale_arp_progression_video(
                        items=self._current_arp_prog_items,
                        title=title,
                        audio_data=audio,
                        output_path=out_path,
                        strip_render_fn=render_arpeggio_progression_strip,
                        position_num=position_num,
                        item_duration_ms=item_dur_ms,
                        portrait=portrait,
                        tab_img=tab_img,
                    )

                else:
                    self._set_status("Nothing to export — generate a diagram first")
                    return

                if path:
                    self._set_status(f"Video saved: {path}")
                else:
                    self._set_status("Video export failed — is ffmpeg installed?")

            except Exception as e:
                self._set_status(f"Video export error: {e}")
            finally:
                self.after(0, self._hide_progress)

        threading.Thread(target=_run, daemon=True).start()

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

    def _record_history(self, snapshot: dict):
        """Push a snapshot onto the history stack and refresh the panel."""
        # Avoid duplicate consecutive entries
        if self._history and self._history[0].get("label") == snapshot.get("label"):
            return
        self._history.insert(0, snapshot)
        self._history = self._history[:self._MAX_HISTORY]
        self._refresh_history_panel()

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

    def _snapshot(self):
        """Capture current diagram state as a restorable dict."""
        mode = self.mode_var.get()
        if mode == "Chord":
            return {
                "label": self._current_name or "Chord",
                "mode": "Chord",
                "root": self.root_var.get(),
                "quality": self.quality_var.get(),
                "voicing": self.voicing_var.get(),
            }
        elif mode == "Scale":
            return {
                "label": self._current_name.replace("_", " ") or "Scale",
                "mode": "Scale",
                "root": self.scale_root_var.get(),
                "scale": self.scale_type_var.get(),
                "view": self.scale_view_var.get(),
            }
        elif mode == "Arpeggio":
            return {
                "label": self._current_name.replace("_", " ") or "Arpeggio",
                "mode": "Arpeggio",
                "root": self.arp_root_var.get(),
                "arp_type": self.arp_type_var.get(),
                "view": self.arp_view_var.get(),
            }
        else:
            return {
                "label": self._current_prog_title or "Progression",
                "mode": "Progression",
                "root": self.prog_root_var.get(),
                "prog_name": self.prog_name_var.get(),
                "prog_custom": self.prog_custom_var.get(),
            }

    def _restore_snapshot(self, snap: dict):
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

    def _build_chord_identifier_panel(self):
        """Build the interactive chord identifier panel (lives in preview_frame)."""
        self.ci_panel = ctk.CTkFrame(
            self.preview_frame, fg_color=config.HEX_NAVY_DEEP, corner_radius=0,
        )
        # Not packed yet — _set_mode controls visibility

        # ── Chord name display ────────────────────────────
        name_frame = ctk.CTkFrame(self.ci_panel, fg_color="transparent")
        name_frame.pack(pady=(18, 6))

        ctk.CTkLabel(
            name_frame, text="DETECTED CHORD",
            font=("Arial", 9, "bold"), text_color="#8fa3bf",
        ).pack()

        _bebas = (
            ("Bebas Neue", 52) if os.path.exists(str(config.FONT_DIR / config.FONT_DISPLAY))
            else ("Arial", 38, "bold")
        )
        self._ci_chord_name_label = ctk.CTkLabel(
            name_frame, text="—", font=_bebas, text_color=config.HEX_GOLD,
        )
        self._ci_chord_name_label.pack()

        # ── Diagram image label (interactive fretboard) ───
        img_outer = ctk.CTkFrame(
            self.ci_panel,
            fg_color=config.HEX_NAVY_MID,
            corner_radius=16,
            border_color=config.HEX_GOLD,
            border_width=1,
        )
        img_outer.pack(padx=24, pady=8)

        self._ci_img_label = tk.Label(
            img_outer,
            bg=config.HEX_NAVY_MID,
            cursor="crosshair",
            bd=0,
            relief="flat",
        )
        self._ci_img_label.pack(padx=14, pady=14)
        self._ci_img_label.bind("<ButtonPress-1>", self._ci_on_click)
        self._ci_layout: dict = {}   # populated on each render

        # ── Audio buttons ─────────────────────────────────
        audio_row = ctk.CTkFrame(self.ci_panel, fg_color="transparent")
        audio_row.pack(pady=(4, 4))

        ctk.CTkButton(
            audio_row, text="▶  Play", width=110, height=34,
            fg_color=config.HEX_GOLD, text_color=config.HEX_NAVY_DEEP,
            hover_color=config.HEX_GOLD_BRIGHT, font=("Arial", 12, "bold"),
            command=self._ci_play_audio,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            audio_row, text="■  Stop", width=90, height=34,
            fg_color=config.HEX_NAVY_LIGHT, text_color=config.HEX_CREAM,
            hover_color="#8b2222", font=("Arial", 12),
            command=self._ci_stop_audio,
        ).pack(side="left")

        # ── Instructions ──────────────────────────────────
        ctk.CTkLabel(
            self.ci_panel,
            text="Click frets to place/remove fingers  •  Click above nut to toggle O / X",
            font=("Arial", 10), text_color="#6a8ab8",
        ).pack(pady=(4, 10))

    # ── Chord detection ───────────────────────────────────────

    def _ci_sounding_notes(self):
        """Return list of {string, midi, pc} for non-muted strings."""
        tuning = list(_CI_TUNING6)
        while len(tuning) < self._ci_strings:
            tuning.append(40)
        out = []
        for s in range(1, self._ci_strings + 1):
            f = next((f for f in self._ci_fingers if f["string"] == s), None)
            om = self._ci_open_muted[s - 1] if s - 1 < len(self._ci_open_muted) else "O"
            if f:
                midi = tuning[s - 1] + f["fret"]
                out.append({"string": s, "midi": midi, "pc": midi % 12})
            elif om == "X":
                continue
            else:
                midi = tuning[s - 1]
                out.append({"string": s, "midi": midi, "pc": midi % 12})
        return out

    def _ci_detect_chord(self):
        """Detect chord name from current finger placements."""
        snd = self._ci_sounding_notes()
        if not snd:
            return "—"
        pcs  = list(dict.fromkeys(n["pc"] for n in snd))
        bass = min(snd, key=lambda n: n["midi"])
        best = None

        for root_pc in pcs:
            iset = set((pc - root_pc) % 12 for pc in pcs)
            for p_name, p_ints, p_score in _CI_PATTERNS:
                pat = set(p_ints)
                if not pat.issubset(iset):
                    continue
                s     = 100 - (len(iset) - len(pat)) * 6
                boost = 6 if bass["pc"] == root_pc else 0
                ext   = ""
                if "7" not in p_name:
                    if 2 in iset:
                        ext = "add9"
                    elif 9 in iset and p_name not in ("6", "m6"):
                        ext = "6"
                    elif 11 in iset and p_name != "maj7":
                        ext = "maj7"
                    elif 10 in iset and p_name != "7":
                        ext = "7"
                chord_name = _CI_NOTES[root_pc] + p_name + ext
                score = p_score + s + boost
                if best is None or score > best[0]:
                    best = (score, root_pc, chord_name)

        if best is None:
            return "-".join(_CI_NOTES[pc] for pc in pcs)
        _, root_pc, chord_name = best
        if _CI_NOTES[bass["pc"]] != _CI_NOTES[root_pc]:
            return f"{chord_name}/{_CI_NOTES[bass['pc']]}"
        return chord_name

    def _ci_get_root_pc(self, snd):
        """Return the root pitch class for the current sounding notes (for dot highlighting)."""
        pcs  = list(dict.fromkeys(n["pc"] for n in snd))
        bass = min(snd, key=lambda n: n["midi"])
        best = None
        for root_pc in pcs:
            iset = set((pc - root_pc) % 12 for pc in pcs)
            for p_name, p_ints, p_score in _CI_PATTERNS:
                pat = set(p_ints)
                if not pat.issubset(iset):
                    continue
                score = p_score + 100 - (len(iset) - len(pat)) * 6 + (6 if bass["pc"] == root_pc else 0)
                if best is None or score > best[0]:
                    best = (score, root_pc)
        return best[1] if best else None

    # ── Premium PIL rendering ─────────────────────────────────

    def _ci_render(self):
        """Re-render the diagram image and update display + chord name label."""
        if not hasattr(self, "_ci_img_label") or self._ci_img_label is None:
            return

        img      = self._ci_render_premium_pil()
        max_w    = 460
        max_h    = 660
        scale    = min(max_w / img.width, max_h / img.height, 1.0)
        dw       = max(int(img.width  * scale), 80)
        dh       = max(int(img.height * scale), 80)
        display  = img.resize((dw, dh), Image.Resampling.LANCZOS)
        photo    = ImageTk.PhotoImage(display)

        self._ci_img_label.configure(image=photo)
        self._ci_img_label.image = photo   # keep reference

        # Store display scale so click handler can map back to PIL coords
        if self._ci_layout:
            self._ci_layout["display_w"] = dw
            self._ci_layout["display_h"] = dh

        detected = self._ci_detect_chord()
        self._ci_chord_name_label.configure(text=detected)

    def _ci_render_premium_pil(self, transparent=False):
        """Render the CI fretboard as a premium RGBA/RGB PIL Image matching the app style."""
        ns = self._ci_strings
        nf = self._ci_frets_visible
        sf = self._ci_start_fret
        show_names = self._ci_show_names_var.get() if hasattr(self, "_ci_show_names_var") else True
        hide_pos   = self._ci_hide_pos_var.get()   if hasattr(self, "_ci_hide_pos_var")   else False
        show_marks = self._ci_show_markers_var.get() if hasattr(self, "_ci_show_markers_var") else True

        W, H = 420, 600

        # ── Base image with gradient background ─────────
        if transparent:
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        else:
            img  = Image.new("RGBA", (W, H), config.NAVY_MID + (255,))
            img  = apply_background_gradient(img)
        draw = ImageDraw.Draw(img)

        # ── Layout ─────────────────────────────────────
        margin_top    = int(H * 0.17)
        margin_bottom = int(H * 0.16)
        margin_left   = int(W * 0.18)
        margin_right  = int(W * 0.12)

        grid_x = margin_left
        grid_y = margin_top
        grid_w = W - margin_left - margin_right
        grid_h = H - margin_top  - margin_bottom

        string_spacing = grid_w / max(ns - 1, 1)
        fret_spacing   = grid_h / nf
        marker_y       = grid_y - int(H * 0.05)   # O/X symbols Y centre

        # ── Fonts ──────────────────────────────────────
        from PIL import ImageFont as _IFont
        def _lf(fname, size):
            p = config.get_font_path(fname)
            if p:
                try:
                    return _IFont.truetype(p, size)
                except Exception:
                    pass
            return _IFont.load_default()

        font_title  = _lf(config.FONT_DISPLAY,  int(H * 0.086))
        font_label  = _lf(config.FONT_BODY,      int(H * 0.030))
        font_dot    = _lf(config.FONT_BODY_BOLD, int(H * 0.032))
        font_wm     = _lf(config.FONT_BODY,      max(int(W * 0.025), 10))

        # ── Detected chord name at top ──────────────────
        detected = self._ci_detect_chord()
        display_name = detected if detected != "—" else "—"
        bbox = draw.textbbox((0, 0), display_name, font=font_title)
        tw   = bbox[2] - bbox[0]
        draw.text((W / 2 - tw / 2, int(H * 0.025)), display_name,
                  fill=config.COLOR_LABEL + (255,), font=font_title)

        # ── Wood-grain fretboard rect (only when not transparent) ──
        pad_fb = int(W * 0.02)
        if not transparent:
            img = draw_fretboard_rect(
                img,
                grid_x - pad_fb, grid_y - int(H * 0.01),
                grid_w + pad_fb * 2, grid_h + int(H * 0.02),
            )
        draw = ImageDraw.Draw(img)

        # ── Fret inlay dots ────────────────────────────
        if show_marks:
            draw_inlay_dots_chord(draw, grid_x, grid_y, grid_w, fret_spacing, sf, nf)

        # ── Nut / position label ───────────────────────
        if sf == 1:
            draw_metallic_fret_h(draw, grid_x - 4, grid_x + grid_w + 4, grid_y, is_nut=True)
        elif not hide_pos:
            draw.text((grid_x - int(W * 0.09), grid_y + fret_spacing * 0.5),
                      f"{sf}fr", fill=config.COLOR_LABEL + (255,), font=font_label)

        # ── Remaining fret wires ───────────────────────
        for i in range(nf + 1):
            draw_metallic_fret_h(draw, grid_x, grid_x + grid_w, grid_y + i * fret_spacing)

        # ── Strings ────────────────────────────────────
        # PIL index 0 = low-E (left), ns-1 = high-e (right)
        # CI string 6 → PIL idx 0 (low-E), CI string 1 → PIL idx ns-1 (high-e)
        for i in range(ns):
            draw_string_v(draw, int(grid_x + i * string_spacing),
                          grid_y, grid_y + grid_h, i)

        # ── O / X markers above nut ────────────────────
        lw   = max(int(W * 0.004), 1)
        fmap = {f["string"]: f for f in self._ci_fingers}
        for s in range(1, ns + 1):
            if s in fmap:
                continue
            pil_idx = ns - s   # CI s=1→pil ns-1 (right), CI s=6→pil 0 (left)
            x       = int(grid_x + pil_idx * string_spacing)
            om      = self._ci_open_muted[s - 1] if s - 1 < len(self._ci_open_muted) else "O"
            if om == "X":
                sz = int(H * 0.020)
                draw.line([(x - sz, marker_y - sz), (x + sz, marker_y + sz)],
                          fill=config.COLOR_MUTED + (255,), width=lw + 2)
                draw.line([(x - sz, marker_y + sz), (x + sz, marker_y - sz)],
                          fill=config.COLOR_MUTED + (255,), width=lw + 2)
            else:
                sz = int(H * 0.018)
                draw.ellipse([x - sz, marker_y - sz, x + sz, marker_y + sz],
                             outline=config.COLOR_OPEN + (255,), width=lw + 2)

        # ── Finger dots (3-D with shadow) ──────────────
        dot_r        = int(min(string_spacing, fret_spacing) * 0.34)
        shadow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dot_layer    = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        s_draw       = ImageDraw.Draw(shadow_layer)
        d_draw       = ImageDraw.Draw(dot_layer)

        snd            = self._ci_sounding_notes()
        detected_root  = self._ci_get_root_pc(snd) if snd else None

        for f in self._ci_fingers:
            fi = f["fret"] - sf + 1
            if fi < 1 or fi > nf:
                continue
            pil_idx = ns - f["string"]
            cx = int(grid_x + pil_idx * string_spacing)
            cy = int(grid_y + (fi - 0.5) * fret_spacing)
            midi     = _CI_TUNING6[f["string"] - 1] + f["fret"]
            is_root  = (detected_root is not None and midi % 12 == detected_root)
            draw_note_dot_3d(s_draw, d_draw, cx, cy, dot_r, is_root, "", None)

        img  = Image.alpha_composite(img, shadow_layer)
        img  = Image.alpha_composite(img, dot_layer)
        draw = ImageDraw.Draw(img)

        # ── String name circles ────────────────────────
        if show_names:
            name_labels = ["E", "A", "D", "G", "B", "e"]
            circle_y    = int(grid_y + grid_h + int(H * 0.042))
            r_circle    = int(H * 0.026)
            for i in range(ns):
                lbl = name_labels[i] if i < len(name_labels) else str(i + 1)
                draw_string_circle(draw, int(grid_x + i * string_spacing),
                                   circle_y, r_circle, lbl, font_label)

        # ── Decorative border + watermark (only when not transparent) ──
        if not transparent:
            img = draw_decorative_border(img)
        img = draw_watermark_gold(img, font_wm)

        # ── Store layout metrics for click mapping ──────
        self._ci_layout = {
            "W": W, "H": H,
            "grid_x": grid_x, "grid_y": grid_y,
            "grid_w": grid_w, "grid_h": grid_h,
            "string_spacing": string_spacing,
            "fret_spacing":   fret_spacing,
            "marker_y":       marker_y,
            "marker_half":    int(H * 0.028),
            "ns": ns, "nf": nf, "sf": sf,
        }

        return img if transparent else img.convert("RGB")

    # ── Click handling ────────────────────────────────────────

    def _ci_on_click(self, event):
        """Handle click on the diagram image label — map pixels to CI state."""
        L = self._ci_layout
        if not L:
            return

        # Map display-pixel coords → PIL-image coords
        W, H   = L["W"], L["H"]
        lw     = self._ci_img_label.winfo_width()
        lh     = self._ci_img_label.winfo_height()
        scale_x = lw / W if lw > 0 else 1.0
        scale_y = lh / H if lh > 0 else 1.0

        px = event.x / scale_x
        py = event.y / scale_y

        grid_x  = L["grid_x"];  grid_y  = L["grid_y"]
        grid_w  = L["grid_w"];  grid_h  = L["grid_h"]
        ss      = L["string_spacing"]
        fs      = L["fret_spacing"]
        ns      = L["ns"];  nf = L["nf"];  sf = L["sf"]
        marker_y     = L["marker_y"]
        marker_half  = L["marker_half"]

        # Must be within horizontal string range
        if px < grid_x - ss * 0.45 or px > grid_x + grid_w + ss * 0.45:
            return

        pil_idx = round((px - grid_x) / ss)
        pil_idx = max(0, min(ns - 1, pil_idx))
        ci_s    = ns - pil_idx   # PIL 0=low-E → CI 6, PIL ns-1=high-e → CI 1

        # O/X zone: above the nut area
        if marker_y - marker_half <= py <= grid_y + 2:
            self._ci_toggle_ox(ci_s)
            return

        # Grid zone: within fret cells
        if grid_y <= py <= grid_y + grid_h:
            fret_rel = int((py - grid_y) / fs)
            fret_rel = max(0, min(nf - 1, fret_rel))
            self._ci_toggle_finger(ci_s, sf + fret_rel)
            return

    def _ci_toggle_ox(self, string):
        """Cycle O → X → O for a string (and remove any finger on it)."""
        idx = string - 1
        if idx < 0 or idx >= len(self._ci_open_muted):
            return
        # Remove finger if present
        self._ci_fingers = [f for f in self._ci_fingers if f["string"] != string]
        self._ci_open_muted[idx] = "X" if self._ci_open_muted[idx] == "O" else "O"
        self._ci_render()

    def _ci_toggle_finger(self, string, fret):
        """Place finger at (string, fret) or remove if already there."""
        existing = next((f for f in self._ci_fingers
                         if f["string"] == string and f["fret"] == fret), None)
        if existing:
            self._ci_fingers.remove(existing)
        else:
            # Remove any other finger on same string first
            self._ci_fingers = [f for f in self._ci_fingers if f["string"] != string]
            # Reset that string to Open when a finger is placed
            if string - 1 < len(self._ci_open_muted):
                self._ci_open_muted[string - 1] = "O"
            self._ci_fingers.append({"string": string, "fret": fret})
        self._ci_render()

    # ── Control callbacks ─────────────────────────────────────

    def _ci_update_from_vars(self):
        """Sync CI state from UI vars and re-render."""
        try:
            sf = int(self._ci_start_fret_var.get())
            if 1 <= sf <= 20:
                self._ci_start_fret = sf
        except (ValueError, AttributeError):
            pass
        try:
            nf = int(self._ci_frets_var.get())
            if 3 <= nf <= 12:
                self._ci_frets_visible = nf
        except (ValueError, AttributeError):
            pass
        try:
            ns = int(self._ci_strings_var.get())
            if 4 <= ns <= 8:
                if ns != self._ci_strings:
                    self._ci_strings = ns
                    old = self._ci_open_muted[:]
                    self._ci_open_muted = ["O"] * ns
                    for i in range(min(len(old), ns)):
                        self._ci_open_muted[i] = old[i]
                    self._ci_fingers = [f for f in self._ci_fingers
                                        if 1 <= f["string"] <= ns]
        except (ValueError, AttributeError):
            pass
        self._ci_render()

    def _ci_set_orientation(self, mode):
        self._ci_orientation = mode
        self._ci_render()

    def _ci_clear(self):
        """Clear all fingers; reset all strings to Open."""
        self._ci_fingers    = []
        self._ci_open_muted = ["O"] * self._ci_strings
        self._ci_render()

    def _ci_reset(self):
        """Reset everything to default state."""
        self._ci_fingers       = []
        self._ci_strings       = 6
        self._ci_frets_visible = 5
        self._ci_start_fret    = 1
        self._ci_open_muted    = ["O"] * 6
        if hasattr(self, "_ci_title_var"):    self._ci_title_var.set("")
        if hasattr(self, "_ci_start_fret_var"): self._ci_start_fret_var.set("1")
        if hasattr(self, "_ci_frets_var"):    self._ci_frets_var.set("5")
        if hasattr(self, "_ci_strings_var"):  self._ci_strings_var.set("6")
        if hasattr(self, "_ci_hide_pos_var"):     self._ci_hide_pos_var.set(False)
        if hasattr(self, "_ci_show_markers_var"): self._ci_show_markers_var.set(True)
        if hasattr(self, "_ci_show_names_var"):   self._ci_show_names_var.set(True)
        self._ci_render()

    # ── PNG export ────────────────────────────────────────────

    # ── Audio ─────────────────────────────────────────────────

    def _ci_to_audio_frets(self):
        """Convert CI state to the 6-element [low-E…high-e] frets list for generate_chord_audio."""
        audio_frets = [-1] * 6   # default: all muted
        for s in range(1, min(self._ci_strings + 1, 7)):
            audio_idx = 6 - s    # CI s=6(low-E) → audio 0, CI s=1(high-e) → audio 5
            f  = next((ff for ff in self._ci_fingers if ff["string"] == s), None)
            om = self._ci_open_muted[s - 1] if s - 1 < len(self._ci_open_muted) else "O"
            if f:
                audio_frets[audio_idx] = f["fret"]
            elif om == "O":
                audio_frets[audio_idx] = 0
        return audio_frets

    def _ci_play_audio(self):
        """Play audio for the current chord identifier state."""
        tone   = self.tone_var.get() if hasattr(self, "tone_var") else "acoustic"
        vol    = self.volume_var.get() if hasattr(self, "volume_var") else 0.8
        raw    = self.play_style_var.get().lower() if hasattr(self, "play_style_var") else "strum down"
        style_map = {
            "strum down": ("strum", "down"),
            "strum up":   ("strum", "up"),
            "arpeggiate": ("arpeggio", "down"),
            "arpeggiate + strum": ("arpeggio_strum", "down"),
        }
        play_style, strum_dir = style_map.get(raw, ("strum", "down"))
        frets = self._ci_to_audio_frets()

        def _play():
            self._set_status("Playing...")
            self.after(0, lambda: self._show_progress(indeterminate=True))
            try:
                audio = generate_chord_audio(
                    frets, tone=tone, duration=2.0,
                    play_style=play_style, strum_direction=strum_dir,
                )
                play_audio(audio, volume=vol)
            except Exception as e:
                self._set_status(f"Playback error: {e}")
            finally:
                self.after(0, self._hide_progress)
                if self.status_label.cget("text") == "Playing...":
                    self.after(0, lambda: self._set_status(""))

        threading.Thread(target=_play, daemon=True).start()

    def _ci_stop_audio(self):
        """Stop any playing audio."""
        stop_audio()
        self._set_status("Stopped")

    # ── PNG Export ────────────────────────────────────────────

    def _ci_get_export_image(self):
        """Return RGBA PIL image for CI export (transparent when BG = transparent)."""
        bg = getattr(self, "_ci_bg_var", None)
        use_transparent = (bg is None or bg.get() == "transparent")
        return self._ci_render_premium_pil(transparent=use_transparent)

    def _ci_save_png_as(self):
        """Open Save As dialog then export the chord identifier diagram."""
        res = getattr(self, "_ci_res_var", None)
        bg  = getattr(self, "_ci_bg_var",  None)
        res_val = res.get() if res else "1080p"
        bg_val  = bg.get()  if bg  else "transparent"

        detected = self._ci_detect_chord()
        name = detected if detected not in ("—", "-") else "chord-identifier"
        default_name = f"{name}_{res_val}_{bg_val}.png"

        path = filedialog.asksaveasfilename(
            title="Save Chord Diagram As",
            initialdir=str(config.OUTPUT_DIR),
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            img = self._ci_get_export_image()
            saved = export_diagram(img, path, res_val, bg_val)
            self._set_status(f"Saved: {Path(saved).name}")
        except Exception as e:
            self._set_status(f"Export failed: {e}")

    def _ci_export_all(self):
        """Export the chord identifier diagram in all resolutions and backgrounds."""
        try:
            img = self._ci_render_premium_pil(transparent=True)
            detected = self._ci_detect_chord()
            name = detected if detected not in ("—", "-") else "chord-identifier"
            output_dir = config.OUTPUT_DIR / "chords"
            paths = batch_export(img, name, output_dir)
            self._set_status(f"Exported {len(paths)} files to {output_dir}")
        except Exception as e:
            self._set_status(f"Export failed: {e}")

    def _ci_export_png(self):
        """Legacy entry point — delegate to Save As dialog."""
        self._ci_save_png_as()

    # ── Favorites ────────────────────────────────────────────

    def _load_favorites(self) -> list:
        try:
            if self._favorites_file.exists():
                return json.loads(self._favorites_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def _save_favorites(self):
        try:
            self._favorites_file.parent.mkdir(parents=True, exist_ok=True)
            self._favorites_file.write_text(
                json.dumps(self._favorites, indent=2), encoding="utf-8"
            )
        except Exception as e:
            self._set_status(f"Could not save favorites: {e}")

    def _add_favorite(self):
        if not self._current_name:
            self._set_status("Nothing to save — generate a diagram first")
            return
        snap = self._snapshot()
        # Don't duplicate
        for fav in self._favorites:
            if fav.get("label") == snap.get("label") and fav.get("mode") == snap.get("mode"):
                self._set_status(f"Already in favorites: {snap['label']}")
                return
        self._favorites.insert(0, snap)
        self._save_favorites()
        self._refresh_favorites_panel()
        self._set_status(f"Saved to favorites: {snap['label']}")

    def _remove_favorite(self, snap: dict):
        self._favorites = [f for f in self._favorites
                           if not (f.get("label") == snap.get("label") and f.get("mode") == snap.get("mode"))]
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

    def _set_status(self, text):
        """Update the status bar text."""
        self.status_label.configure(text=text)


def run():
    """Launch the GUI application."""
    app = DiagramStudioApp()
    app.mainloop()


if __name__ == "__main__":
    run()
