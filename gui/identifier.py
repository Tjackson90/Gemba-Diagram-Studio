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




class IdentifierMixin:
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


    def _ci_sounding_notes(self):
        """Return list of {string, midi, pc} for non-muted strings."""
        tuning = list(reversed(get_tuning()))
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
        if hasattr(self, "mode_var") and self.mode_var.get() == "ChordID":
            self._record_history(self._snapshot())


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
            midi     = list(reversed(get_tuning()))[min(f["string"] - 1, 5)] + f["fret"]
            is_root  = (detected_root is not None and midi % 12 == detected_root)
            draw_note_dot_3d(s_draw, d_draw, cx, cy, dot_r, is_root, "", None)

        img  = Image.alpha_composite(img, shadow_layer)
        img  = Image.alpha_composite(img, dot_layer)
        draw = ImageDraw.Draw(img)

        # ── String name circles ────────────────────────
        if show_names:
            from data.instrument import string_names
            name_labels = string_names()
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
        frets = list(self._ci_to_audio_frets())
        tone, volume = self.tone_var.get(), self.volume_var.get()
        style, direction = self._parse_play_style()
        note_ms = self._bpm_to_note_ms()
        settings = {key: getattr(self, 'tone_'+key+'_var').get()
                    for key in ('attack','decay','brightness','warmth','harmonics','body','reverb')}
        instrument_value = self._instrument_settings()
        def work():
            from data.instrument import instrument
            from audio.engine import tone_settings
            from services.jobs import check_cancelled
            with tone_settings(settings), instrument(instrument_value):
                audio = generate_chord_audio(frets, tone=tone, play_style=style,
                                             strum_direction=direction, arpeggio_delay_ms=note_ms)
            check_cancelled()
            play_audio(audio, volume=volume)
        self._run_job('Playing...', work, lambda _: self._set_status('Playback complete'))


    def _ci_stop_audio(self):
        """Stop any playing audio."""
        self._cancel_job()


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


from data.instrument import get_tuning
