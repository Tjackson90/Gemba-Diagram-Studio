"""
Chord progression data — diatonic degree mappings + named progressions.

Progression format:
    A list of 0-based scale-degree indices (0 = I/i, 1 = II/ii, …, 6 = VII/vii).

Roman-numeral names use standard convention:
    Major keys: I ii iii IV V vi vii°
    Minor keys: i ii° III iv v VI VII
"""

from data.notes import note_name_to_semitone, FLAT_NAMES, SHARP_NAMES

# ── Scale intervals ────────────────────────────────────────
MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]   # natural minor

# Diatonic chord quality for each degree (major key)
MAJOR_DEGREE_QUALITIES = [
    "Major",      # I
    "Minor",      # ii
    "Minor",      # iii
    "Major",      # IV
    "Major",      # V   (dominant — optionally "7" but Major for simplicity)
    "Minor",      # vi
    "Dim",        # vii°
]

# Diatonic chord quality for each degree (natural minor key)
MINOR_DEGREE_QUALITIES = [
    "Minor",      # i
    "Dim",        # ii°
    "Major",      # III
    "Minor",      # iv
    "Minor",      # v
    "Major",      # VI
    "Major",      # VII
]

# Roman numeral labels for display
MAJOR_DEGREE_LABELS = ["I", "ii", "iii", "IV", "V", "vi", "vii°"]
MINOR_DEGREE_LABELS = ["i", "ii°", "III", "iv", "v", "VI", "VII"]

# ── Named progressions ────────────────────────────────────
# Format: {prog_name: degree_list}  (0-based indices)

MAJOR_PROGRESSIONS = {
    "I – IV – V":           [0, 3, 4],
    "I – IV – V – I":       [0, 3, 4, 0],
    "I – V – vi – IV":      [0, 4, 5, 3],
    "I – vi – IV – V":      [0, 5, 3, 4],
    "I – vi – ii – V":      [0, 5, 1, 4],
    "ii – V – I":           [1, 4, 0],
    "I – IV – vi – V":      [0, 3, 5, 4],
    "I – ii – IV – V":      [0, 1, 3, 4],
    "vi – IV – I – V":      [5, 3, 0, 4],
    "I – V – IV – V":       [0, 4, 3, 4],
    "I – IV – I – V":       [0, 3, 0, 4],
    "I – IV – ii – V":      [0, 3, 1, 4],
    "I – iii – IV – V":     [0, 2, 3, 4],
    "I – IV – V – vi":      [0, 3, 4, 5],
}

MINOR_PROGRESSIONS = {
    "i – iv – v":            [0, 3, 4],
    "i – iv – v – i":        [0, 3, 4, 0],
    "i – VI – III – VII":    [0, 5, 2, 6],
    "i – VII – VI – VII":    [0, 6, 5, 6],
    "i – iv – VII – III":    [0, 3, 6, 2],
    "i – VI – VII – i":      [0, 5, 6, 0],
    "i – III – VII – VI":    [0, 2, 6, 5],
    "i – v – VI – VII":      [0, 4, 5, 6],
    "i – iv – i – v":        [0, 3, 0, 4],
    "i – ii° – v – i":       [0, 1, 4, 0],
}

PROGRESSION_NAMES = {
    "major": list(MAJOR_PROGRESSIONS.keys()),
    "minor": list(MINOR_PROGRESSIONS.keys()),
}


# ── Core lookup helpers ───────────────────────────────────

def get_degree_chord(root_name, mode, degree_idx):
    """
    Return (chord_root_name, quality) for one scale degree.

    Args:
        root_name:  e.g. "C", "F#", "Bb"
        mode:       "major" or "minor"
        degree_idx: 0-based (0 = I/i)
    """
    if mode == "major":
        scale = MAJOR_SCALE
        qualities = MAJOR_DEGREE_QUALITIES
    else:
        scale = MINOR_SCALE
        qualities = MINOR_DEGREE_QUALITIES

    root_semi = note_name_to_semitone(root_name)
    degree_semi = (root_semi + scale[degree_idx]) % 12
    quality = qualities[degree_idx]

    prefer_flat = root_semi in {1, 3, 6, 8, 10}
    chord_root = FLAT_NAMES[degree_semi] if prefer_flat else SHARP_NAMES[degree_semi]
    return chord_root, quality


def get_progression_chords(root_name, mode, degree_indices):
    """
    Return full chord data for each degree in the progression.

    Returns list of dicts:
        {degree_idx, chord_root, quality, display_name, frets, fingers, label, roman}
    """
    from data.chords import get_voicings, get_chord_display_name

    labels = MAJOR_DEGREE_LABELS if mode == "major" else MINOR_DEGREE_LABELS
    result = []

    for deg in degree_indices:
        chord_root, quality = get_degree_chord(root_name, mode, deg)
        voicings = get_voicings(chord_root, quality)
        if not voicings:
            # Fallback — all muted
            voicings = [{"frets": [-1, -1, -1, -1, -1, -1], "label": "?", "fingers": None}]
        v = voicings[0]
        result.append({
            "degree_idx": deg,
            "roman": labels[deg],
            "chord_root": chord_root,
            "quality": quality,
            "display_name": get_chord_display_name(chord_root, quality),
            "frets": v["frets"],
            "fingers": v.get("fingers"),
            "voicing_label": v["label"],
        })

    return result


def get_named_progression(root_name, mode, prog_name):
    """
    Look up a named progression and return chord data.

    Returns (degree_indices, chord_dicts).
    """
    progs = MAJOR_PROGRESSIONS if mode == "major" else MINOR_PROGRESSIONS
    if prog_name not in progs:
        raise ValueError(f"Unknown progression '{prog_name}' for {mode} key")
    degrees = progs[prog_name]
    return degrees, get_progression_chords(root_name, mode, degrees)


# ── Modal scale name for each diatonic degree ─────────────
# Maps to keys in data/scales.SCALE_INTERVALS
MAJOR_DEGREE_MODES = [
    "Major",         # I   — Ionian
    "Dorian",        # ii
    "Phrygian",      # iii
    "Lydian",        # IV
    "Mixolydian",    # V
    "Natural Minor", # vi  — Aeolian
    "Locrian",       # vii°
]

MINOR_DEGREE_MODES = [
    "Natural Minor", # i   — Aeolian
    "Locrian",       # ii°
    "Major",         # III — Ionian
    "Dorian",        # iv
    "Phrygian",      # v
    "Lydian",        # VI
    "Mixolydian",    # VII
]

# Display names for the modes (what shows on the diagram title)
MAJOR_DEGREE_MODE_LABELS = [
    "Ionian", "Dorian", "Phrygian", "Lydian",
    "Mixolydian", "Aeolian", "Locrian",
]
MINOR_DEGREE_MODE_LABELS = [
    "Aeolian", "Locrian", "Ionian", "Dorian",
    "Phrygian", "Lydian", "Mixolydian",
]

# Chord quality → arpeggio type (must match data/arpeggios.ARPEGGIO_INTERVALS keys)
QUALITY_TO_ARPEGGIO = {
    "Major": "Major",
    "Minor": "Minor",
    "Dim":   "Dim",
    "Dom7":  "Dom7",
    "Maj7":  "Maj7",
    "Min7":  "Min7",
}


def get_progression_scales(root_name, mode, degree_indices):
    """
    For each degree in a progression, return the diatonic modal scale to play.

    Returns list of dicts:
        {degree_idx, roman, chord_root, chord_display, scale_name, mode_label, display_name}
    """
    if mode == "major":
        scale_map   = MAJOR_DEGREE_MODES
        mode_labels = MAJOR_DEGREE_MODE_LABELS
        labels      = MAJOR_DEGREE_LABELS
        scale_def   = MAJOR_SCALE
    else:
        scale_map   = MINOR_DEGREE_MODES
        mode_labels = MINOR_DEGREE_MODE_LABELS
        labels      = MINOR_DEGREE_LABELS
        scale_def   = MINOR_SCALE

    root_semi   = note_name_to_semitone(root_name)
    prefer_flat = root_semi in {1, 3, 6, 8, 10}
    result = []

    for deg in degree_indices:
        degree_semi = (root_semi + scale_def[deg]) % 12
        chord_root  = FLAT_NAMES[degree_semi] if prefer_flat else SHARP_NAMES[degree_semi]
        scale_name  = scale_map[deg]
        mode_label  = mode_labels[deg]
        result.append({
            "degree_idx":   deg,
            "roman":        labels[deg],
            "chord_root":   chord_root,
            "chord_display": chord_root,
            "scale_name":   scale_name,
            "mode_label":   mode_label,
            "display_name": f"{chord_root} {mode_label}",
        })
    return result


def get_progression_arpeggios(root_name, mode, degree_indices):
    """
    For each degree in a progression, return the matching arpeggio to play.

    Returns list of dicts:
        {degree_idx, roman, chord_root, chord_display, arp_name, display_name}
    """
    if mode == "major":
        qualities = MAJOR_DEGREE_QUALITIES
        labels    = MAJOR_DEGREE_LABELS
        scale_def = MAJOR_SCALE
    else:
        qualities = MINOR_DEGREE_QUALITIES
        labels    = MINOR_DEGREE_LABELS
        scale_def = MINOR_SCALE

    root_semi   = note_name_to_semitone(root_name)
    prefer_flat = root_semi in {1, 3, 6, 8, 10}
    result = []

    for deg in degree_indices:
        degree_semi = (root_semi + scale_def[deg]) % 12
        chord_root  = FLAT_NAMES[degree_semi] if prefer_flat else SHARP_NAMES[degree_semi]
        quality     = qualities[deg]
        arp_name    = QUALITY_TO_ARPEGGIO.get(quality, "Major")
        result.append({
            "degree_idx":   deg,
            "roman":        labels[deg],
            "chord_root":   chord_root,
            "chord_display": chord_root,
            "quality":      quality,
            "arp_name":     arp_name,
            "display_name": f"{chord_root} {arp_name}",
        })
    return result


def parse_roman(roman_str, mode):
    """
    Parse a user-typed Roman numeral string like 'I-IV-V' into degree indices.

    Returns list of 0-based degree indices, or None on parse failure.
    """
    labels = MAJOR_DEGREE_LABELS if mode == "major" else MINOR_DEGREE_LABELS
    labels_lower = [l.lower() for l in labels]

    parts = roman_str.replace(",", "-").replace(" ", "-").split("-")
    parts = [p.strip() for p in parts if p.strip()]

    indices = []
    for p in parts:
        pl = p.lower().rstrip("°").rstrip("o")
        matched = False
        for i, lbl in enumerate(labels_lower):
            if lbl.rstrip("°").rstrip("o") == pl:
                indices.append(i)
                matched = True
                break
        if not matched:
            return None   # unrecognised token

    return indices if indices else None
