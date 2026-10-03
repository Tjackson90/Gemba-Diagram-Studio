"""
GembaGuitar Diagram Studio — Brand & Layout Configuration
"""

import os
from pathlib import Path

# ── Project Paths ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
FONT_DIR = PROJECT_ROOT / "fonts"
OUTPUT_DIR = PROJECT_ROOT / "output"

# ── Brand Colors (RGB tuples) ──────────────────────────────
NAVY_DEEP = (11, 30, 61)        # #0b1e3d
NAVY_MID = (18, 42, 82)         # #122a52
NAVY_LIGHT = (26, 58, 110)      # #1a3a6e
GOLD = (201, 168, 76)           # #c9a84c
GOLD_BRIGHT = (232, 201, 106)   # #e8c96a
CREAM = (245, 240, 232)         # #f5f0e8
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
TRANSPARENT = (0, 0, 0, 0)

# Hex versions for display / GUI
HEX_NAVY_DEEP = "#0b1e3d"
HEX_NAVY_MID = "#122a52"
HEX_NAVY_LIGHT = "#1a3a6e"
HEX_GOLD = "#c9a84c"
HEX_GOLD_BRIGHT = "#e8c96a"
HEX_CREAM = "#f5f0e8"

# ── Diagram Colors ─────────────────────────────────────────
COLOR_FRETBOARD_BG = NAVY_MID
COLOR_FRET_WIRE = CREAM
COLOR_STRING = CREAM
COLOR_DOT_FILL = CREAM               # Regular scale/chord tones
COLOR_DOT_ROOT = GOLD                 # Root notes
COLOR_DOT_TEXT = NAVY_DEEP            # Note name text inside dots
COLOR_DOT_TEXT_ROOT = NAVY_DEEP       # Note name text inside root dots
COLOR_LABEL = CREAM                   # Chord/scale name, fret numbers
COLOR_MUTED = (180, 170, 155)         # Muted string X
COLOR_OPEN = CREAM                    # Open string O
COLOR_NUT = GOLD                      # Nut (fret 0 bar)
COLOR_FINGER_NUM = GOLD_BRIGHT        # Finger number text
COLOR_WATERMARK = (245, 240, 232, 80) # Semi-transparent cream

# ── Fonts ──────────────────────────────────────────────────
FONT_DISPLAY = "BebasNeue-Regular.ttf"
FONT_BODY = "DMSans-Regular.ttf"
FONT_BODY_BOLD = "DMSans-Bold.ttf"

def get_font_path(font_file):
    """Get full path to a font file, with fallback info."""
    path = FONT_DIR / font_file
    if path.exists():
        return str(path)
    return None

# ── Export Resolutions ─────────────────────────────────────
RESOLUTIONS = {
    "1080p": (1920, 1080),
    "4K": (3840, 2160),
    "Square": (1080, 1080),
    "Square 4K": (2160, 2160),
}

# ── Chord Diagram Layout ──────────────────────────────────
CHORD_LAYOUT = {
    "num_frets": 5,           # Frets shown in a chord box
    "num_strings": 6,
    "dot_radius_ratio": 0.35, # Dot radius as ratio of cell size
    "nut_thickness": 8,       # Pixels for the nut bar
    "string_names": ["E", "A", "D", "G", "B", "e"],
}

# ── Scale Diagram Layout ──────────────────────────────────
SCALE_BOX_LAYOUT = {
    "num_frets": 5,           # Frets shown in positional box
    "num_strings": 6,
    "dot_radius_ratio": 0.35,
}

SCALE_FULL_LAYOUT = {
    "num_frets": 15,          # Full fretboard (0–14)
    "num_strings": 6,
    "dot_radius_ratio": 0.30,
}

# ── Audio ──────────────────────────────────────────────────
AUDIO_SAMPLE_RATE = 44100
AUDIO_STRUM_DELAY_MS = 20     # Delay between strings in strum
AUDIO_NOTE_DURATION_S = 1.5   # Single note sustain
AUDIO_SCALE_NOTE_MS = 300     # Time per note in scale playback

# ── Watermark ──────────────────────────────────────────────
WATERMARK_TEXT = "GembaGuitar.com"
WATERMARK_FONT_SIZE_RATIO = 0.025  # Relative to image width

# ── Premium Visual Design Colors ───────────────────────────
# Fretboard (rosewood-feel dark wood)
FRETBOARD_FILL      = (20, 16, 42)       # dark navy-brown
FRETBOARD_GRAIN_LO  = (12, 9, 25)        # dark grain line
FRETBOARD_GRAIN_HI  = (38, 28, 58)       # light grain line

# Fret wires (metallic bevel)
FRET_WIRE_MAIN      = (200, 200, 210)    # silver
FRET_WIRE_HIGHLIGHT = (230, 230, 240)    # bright edge
FRET_WIRE_SHADOW    = (120, 120, 130)    # dark edge

# Strings (steel gauge coloring)
STRING_BASS         = (180, 170, 155)    # wound strings E, A, D
STRING_TREBLE       = (210, 205, 195)    # plain strings G, B, e
STRING_WIDTHS       = [4, 3, 3, 2, 2, 1] # px per string (index 0=low E)

# Fret inlay dots
INLAY_COLOR         = (60, 55, 80)       # muted navy-gray

# Background gradient
BG_GRADIENT_CENTER  = (18, 42, 82)       # navy mid
BG_GRADIENT_EDGE    = (8, 20, 45)        # navy dark

# Decorative frame
FRAME_PADDING       = 18                 # px from image edge
FRAME_GAP           = 8                  # gap between outer and inner frame line

# Note dot shadow
DOT_SHADOW_ALPHA    = 80                 # 0-255
