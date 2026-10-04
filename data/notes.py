"""
Music theory helpers — notes, intervals, frequencies, fretboard mapping.
"""

# ── Note Names ─────────────────────────────────────────────
SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES  = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# Display-friendly names with enharmonic labels
DISPLAY_NAMES = [
    "C", "C#/Db", "D", "D#/Eb", "E", "F",
    "F#/Gb", "G", "G#/Ab", "A", "A#/Bb", "B"
]

# For short labels (prefer sharps by default)
SHORT_NAMES = SHARP_NAMES

# ── Standard Tuning (low to high: E2 A2 D3 G3 B3 E4) ─────
# MIDI note numbers for standard tuning
STANDARD_TUNING_MIDI = [40, 45, 50, 55, 59, 64]  # E2, A2, D3, G3, B3, E4
STANDARD_TUNING_NAMES = ["E", "A", "D", "G", "B", "E"]

# ── Frequency Calculation ──────────────────────────────────
A4_FREQ = 440.0
A4_MIDI = 69

def midi_to_freq(midi_note):
    """Convert MIDI note number to frequency in Hz."""
    return A4_FREQ * (2 ** ((midi_note - A4_MIDI) / 12))

def note_name_to_semitone(name):
    """Convert note name (e.g., 'C', 'F#', 'Bb') to semitone index 0-11."""
    name = name.strip().replace('♯', '#').replace('♭', 'b')
    if name and name[0].upper() in 'ABCDEFG' and all(c in '#b' for c in name[1:]):
        natural = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
        return (natural[name[0].upper()] + name[1:].count('#') - name[1:].count('b')) % 12
    # Try sharp names first
    if name in SHARP_NAMES:
        return SHARP_NAMES.index(name)
    if name in FLAT_NAMES:
        return FLAT_NAMES.index(name)
    # Handle enharmonic input like "C#/Db"
    if "/" in name:
        return note_name_to_semitone(name.split("/")[0])
    raise ValueError(f"Unknown note: {name}")

def semitone_to_name(semitone, prefer_flat=False):
    """Convert semitone index (0-11) to note name."""
    idx = semitone % 12
    return FLAT_NAMES[idx] if prefer_flat else SHARP_NAMES[idx]

# ── Fretboard Helpers ──────────────────────────────────────
def fret_to_midi(string_idx, fret):
    """Get MIDI note number for a string index (0=low E) and fret."""
    return get_tuning()[string_idx] + fret

def fret_to_note_name(string_idx, fret, prefer_flat=False):
    """Get note name for a string index and fret."""
    midi = fret_to_midi(string_idx, fret)
    return semitone_to_name(midi, prefer_flat)

def fret_to_semitone(string_idx, fret):
    """Get semitone class (0-11) for a string index and fret."""
    return fret_to_midi(string_idx, fret) % 12

def get_fretboard_notes(num_frets=15):
    """
    Build a full map of the fretboard.
    Returns: dict[string_idx][fret] = (midi, semitone, note_name)
    """
    fb = {}
    for s in range(6):
        fb[s] = {}
        for f in range(num_frets + 1):
            midi = fret_to_midi(s, f)
            semi = midi % 12
            name = semitone_to_name(semi)
            fb[s][f] = (midi, semi, name)
    return fb

# ── Interval / Chord Helpers ──────────────────────────────
def get_chord_notes(root_semitone, intervals):
    """
    Given a root semitone (0-11) and list of intervals,
    return list of semitone values for the chord.
    """
    return [(root_semitone + i) % 12 for i in intervals]

def get_scale_notes(root_semitone, intervals):
    """
    Given a root semitone (0-11) and list of scale intervals,
    return list of semitone values in the scale.
    """
    return [(root_semitone + i) % 12 for i in intervals]

# ── Note Names for Specific Roots ─────────────────────────
# Some roots prefer flats in their scale/chord spelling
FLAT_ROOTS = {1, 3, 5, 6, 8, 10}  # Db, Eb, F, Gb, Ab, Bb

def note_display_name(semitone, root_semitone=0):
    """
    Get display name for a note, using flats if the root prefers flats.
    """
    prefer_flat = root_semitone in FLAT_ROOTS
    return semitone_to_name(semitone, prefer_flat)

# ── All 12 Root Names (for UI dropdowns) ──────────────────
ROOT_NAMES = [
    "C", "C#/Db", "D", "D#/Eb", "E", "F",
    "F#/Gb", "G", "G#/Ab", "A", "A#/Bb", "B"
]


def spell_intervals(root, intervals, degrees=None):
    """Preserve diatonic letter names independently of sounding pitch classes."""
    root = root.split('/')[0].replace('♯', '#').replace('♭', 'b')
    semi = note_name_to_semitone(root)
    letters = 'CDEFGAB'
    natural = [0, 2, 4, 5, 7, 9, 11]
    if degrees is None and len(intervals) == 7:
        degrees = range(7)
    if degrees is None:
        return [semitone_to_name(semi+iv, 'b' in root or semi in FLAT_ROOTS) for iv in intervals]
    start = letters.index(root[0].upper())
    result = []
    for iv, degree in zip(intervals, degrees):
        index = (start + degree) % 7
        accidental = (semi + iv - natural[index] + 6) % 12 - 6
        result.append(letters[index] + ('#' * accidental if accidental >= 0 else 'b' * -accidental))
    return result

from data.instrument import get_tuning, string_names, string_column
