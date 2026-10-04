"""
Scale definitions — intervals, CAGED positions, and fretboard mapping.
"""

from data.notes import note_name_to_semitone, semitone_to_name, STANDARD_TUNING_MIDI

# ── Scale Intervals (semitones from root) ──────────────────
#
# Priority 1 — Core scales (must not be renamed; used by progressions.py and GUI)
# Priority 2 — Additional modal & jazz scales
# Priority 3 — Symmetric / exotic
#
SCALE_INTERVALS = {
    # ── Priority 1: Pentatonic & Core ──────────────────────
    "Pentatonic Minor":      [0, 3, 5, 7, 10],
    "Pentatonic Major":      [0, 2, 4, 7, 9],

    # ── Priority 1: Major modes (names locked by progressions.py) ───
    "Major":                 [0, 2, 4, 5, 7, 9, 11],   # Ionian
    "Dorian":                [0, 2, 3, 5, 7, 9, 10],
    "Phrygian":              [0, 1, 3, 5, 7, 8, 10],
    "Lydian":                [0, 2, 4, 6, 7, 9, 11],
    "Mixolydian":            [0, 2, 4, 5, 7, 9, 10],
    "Natural Minor":         [0, 2, 3, 5, 7, 8, 10],   # Aeolian
    "Locrian":               [0, 1, 3, 5, 6, 8, 10],

    # ── Priority 1: Blues (standard hexatonic) ──────────────
    "Blues":                 [0, 3, 5, 6, 7, 10],

    # ── Priority 2: Harmonic Minor family ───────────────────
    "Harmonic Minor":        [0, 2, 3, 5, 7, 8, 11],
    "Locrian #6":            [0, 1, 3, 5, 6, 9, 10],   # Harmonic minor mode 2
    "Ionian Augmented":      [0, 2, 4, 5, 8, 9, 11],   # Harmonic minor mode 3
    "Dorian #4":             [0, 2, 3, 6, 7, 9, 10],   # Harmonic minor mode 4
    "Phrygian Dominant":     [0, 1, 4, 5, 7, 8, 10],   # Harmonic minor mode 5
    "Lydian #2":             [0, 3, 4, 6, 7, 9, 11],   # Harmonic minor mode 6
    "Ultra Locrian":         [0, 1, 3, 4, 6, 8, 9],    # Harmonic minor mode 7

    # ── Priority 2: Melodic Minor family ────────────────────
    "Melodic Minor":         [0, 2, 3, 5, 7, 9, 11],
    "Dorian b2":             [0, 1, 3, 5, 7, 9, 10],   # Melodic minor mode 2
    "Lydian Augmented":      [0, 2, 4, 6, 8, 9, 11],   # Melodic minor mode 3
    "Lydian Dominant":       [0, 2, 4, 6, 7, 9, 10],   # Melodic minor mode 4
    "Mixolydian b6":         [0, 2, 4, 5, 7, 8, 10],   # Melodic minor mode 5
    "Locrian #2":            [0, 2, 3, 5, 6, 8, 10],   # Melodic minor mode 6
    "Altered":               [0, 1, 3, 4, 6, 8, 10],   # Melodic minor mode 7 (Super Locrian)

    # ── Priority 2: Blues modal variants ────────────────────
    "Blues Major":           [0, 2, 3, 4, 7, 9],       # Major blues hexatonic
    "Blues Dorian":          [0, 2, 5, 6, 7, 10],      # Dorian + b5 blue note
    "Blues Mixolydian":      [0, 2, 5, 7, 9, 10],      # Mixolydian blues hexatonic
    "Blues Phrygian":        [0, 3, 5, 7, 8, 10],      # Phrygian blues hexatonic

    # ── Priority 3: Symmetric / Exotic ──────────────────────
    "Whole Tone":            [0, 2, 4, 6, 8, 10],
    "Diminished (W-H)":      [0, 2, 3, 5, 6, 8, 9, 11],
    "Diminished (H-W)":      [0, 1, 3, 4, 6, 7, 9, 10],
}

SCALE_NAMES = list(SCALE_INTERVALS.keys())

# Merge any user-saved custom scales into the live dicts at import time
try:
    from data.custom_library import load_into_scale_dicts as _load_custom
    _load_custom(SCALE_INTERVALS, SCALE_NAMES)
except (ValueError, OSError) as exc:
    import warnings
    warnings.warn(f"Custom library was not loaded: {exc}", RuntimeWarning)


def get_scale_notes_set(root_semitone, scale_name):
    """Get the set of semitones (0-11) in a scale."""
    intervals = SCALE_INTERVALS.get(scale_name)
    if intervals is None:
        return set()
    return {(root_semitone + i) % 12 for i in intervals}


def get_full_fretboard_scale(root_name, scale_name, num_frets=15):
    """
    Get all scale notes on the full fretboard.

    Returns list of dicts:
        {string, fret, semitone, note_name, is_root}
    """
    if "/" in root_name:
        root_name = root_name.split("/")[0]
    root_semi = note_name_to_semitone(root_name)
    scale_notes = get_scale_notes_set(root_semi, scale_name)

    if not scale_notes:
        return []

    result = []
    for string_idx in range(6):
        open_midi = get_tuning()[string_idx]
        for fret in range(num_frets + 1):
            midi = open_midi + fret
            semi = midi % 12
            if semi in scale_notes:
                prefer_flat = root_semi in {1, 3, 6, 8, 10}
                from data.notes import FLAT_NAMES, SHARP_NAMES
                name = FLAT_NAMES[semi] if prefer_flat else SHARP_NAMES[semi]
                result.append({
                    "string": string_idx,
                    "fret": fret,
                    "semitone": semi,
                    "note_name": name,
                    "is_root": (semi == root_semi),
                })
    labels = dict(zip(SCALE_INTERVALS[scale_name], get_scale_tone_names(root_name, scale_name)))
    for note in result:
        note["note_name"] = labels[(note["semitone"] - root_semi) % 12]
    return result


def get_caged_positions(root_name, scale_name, num_frets=15):
    """Five pentatonic patterns, or exploratory fret windows for other scales.

    The historic function name remains for callers. Non-pentatonic windows
    describe available tones rather than promising a standard CAGED fingering.
    """
    from data.instrument import settings
    from data.positions import pentatonic_positions, fret_windows
    if scale_name in ('Pentatonic Minor', 'Pentatonic Major') and settings()['tuning'] == 'Standard':
        return pentatonic_positions(root_name, scale_name, get_full_fretboard_scale)
    return fret_windows(root_name, scale_name, get_full_fretboard_scale)


def get_three_note_per_string_scale(root_name, scale_name, position=1):
    """
    Generate a 3-notes-per-string (3NPS) scale pattern across all 6 strings.

    Each string receives exactly 3 consecutive scale tones in ascending pitch
    order, producing the classic shred/lead guitar fingering pattern.

    Args:
        root_name: e.g., "A", "C#", "Bb"
        scale_name: must be in SCALE_INTERVALS
        position: 1 = start from root on low E string;
                  2-7 = start from subsequent scale degrees on low E
                  (wraps at octave, giving 7 positions for 7-note scales,
                   5 positions for pentatonic, etc.)

    Returns:
        list of dicts {string, fret, semitone, note_name, is_root}
        ordered string 0→5 (low E → high e), left to right per string
    """
    if "/" in root_name:
        root_name = root_name.split("/")[0]

    root_semi = note_name_to_semitone(root_name)
    intervals = SCALE_INTERVALS.get(scale_name)
    if not intervals:
        return []

    from data.notes import FLAT_NAMES, SHARP_NAMES
    prefer_flat = root_semi in {1, 3, 6, 8, 10}

    # Low E open MIDI = 40
    low_e_open = get_tuning()[0]  # 40

    # Find the first occurrence of the root on the low E string (fret 0–11)
    root_fret_base = (root_semi - low_e_open % 12) % 12
    if root_fret_base == 0 and (low_e_open % 12) != root_semi:
        root_fret_base = 12  # prefer 12th fret over open if root isn't E

    # Starting MIDI pitch for this root occurrence on low E
    root_midi = low_e_open + root_fret_base

    # Shift starting degree by (position - 1) scale steps for different positions
    pos_idx = (position - 1) % len(intervals)
    # Starting MIDI = root_midi + intervals[pos_idx]
    # But we want to stay on or after root_midi for position>1
    start_midi = root_midi + intervals[pos_idx]

    # Build a long ascending sequence of scale MIDI values from start_midi
    # covering enough range for all 6 strings (roughly 3 octaves)
    all_scale_midi = []
    for octave_offset in range(-1, 5):
        for iv in intervals:
            m = root_midi + octave_offset * 12 + iv
            all_scale_midi.append(m)
    all_scale_midi = sorted(set(m for m in all_scale_midi if m >= start_midi))

    result = []
    midi_seq_idx = 0

    for string_idx in range(6):
        open_midi = get_tuning()[string_idx]
        notes_placed = 0

        while notes_placed < 3 and midi_seq_idx < len(all_scale_midi):
            midi = all_scale_midi[midi_seq_idx]
            fret = midi - open_midi

            if fret < 0:
                # This pitch is below the open string — advance to the next pitch
                midi_seq_idx += 1
                continue

            semi = midi % 12
            name = FLAT_NAMES[semi] if prefer_flat else SHARP_NAMES[semi]
            result.append({
                "string": string_idx,
                "fret": fret,
                "semitone": semi,
                "note_name": name,
                "is_root": (semi == root_semi),
            })
            notes_placed += 1
            midi_seq_idx += 1

    from data.instrument import settings
    limit = 24-settings()['capo']
    if result and max(n['fret'] for n in result)>limit:
        if min(n['fret'] for n in result)>=12:
            for note in result:
                note['fret'] -= 12
        if max(n['fret'] for n in result)>limit:
            return []
    labels = dict(zip(intervals, get_scale_tone_names(root_name, scale_name)))
    for note in result:
        note["note_name"] = labels[(note["semitone"]-root_semi)%12]
    return result


def get_three_nps_positions(root_name, scale_name):
    """
    Return all 3NPS positions for a scale (one per scale degree).

    Returns list of dicts, each matching the format of get_caged_positions():
        {position_num, start_fret, end_fret, notes}
    """
    intervals = SCALE_INTERVALS.get(scale_name, [])
    n_positions = len(intervals)
    positions = []
    for pos in range(1, n_positions + 1):
        notes = get_three_note_per_string_scale(root_name, scale_name, position=pos)
        if not notes:
            continue
        frets = [n["fret"] for n in notes]
        positions.append({
            "position_num": pos,
            "start_fret": min(frets),
            "end_fret": max(frets),
            "notes": notes,
        })
    return positions


# ── Interval label names ──────────────────────────────────────────────
_INTERVAL_LABELS = {
    0: "R", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4",
    6: "b5", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7",
}


def get_scale_interval_labels(scale_name):
    """
    Return the interval labels for a scale, e.g.:
        "Pentatonic Minor" -> ["R", "b3", "4", "5", "b7"]
    """
    intervals = SCALE_INTERVALS.get(scale_name, [])
    return [_INTERVAL_LABELS[i] for i in intervals]


def get_scale_display_name(root_name, scale_name):
    """Get display name like 'A Minor Pentatonic' or 'C Major'."""
    return f"{root_name} {scale_name}"


def get_scale_tone_names(root_name, scale_name):
    """Get the note names of all tones in the scale."""
    from data.notes import spell_intervals
    intervals = SCALE_INTERVALS.get(scale_name, [])
    degrees = {'Pentatonic Minor': [0,2,3,4,6], 'Pentatonic Major': [0,1,2,4,5]}.get(scale_name)
    return spell_intervals(root_name, intervals, degrees)

from data.instrument import get_tuning, string_names, string_column
