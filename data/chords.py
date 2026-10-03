"""
Chord voicing database.

Uses barre shape templates (E-shape, A-shape) that transpose to all 12 keys,
plus hand-coded open voicing overrides for common chords.

frets format: [E, A, D, G, B, e]  (low to high)
  -1 = muted (X)
   0 = open (O)
   1+ = fret number

fingers format: [E, A, D, G, B, e]
   0 = not played / open
   1-4 = finger number (index through pinky)
"""

from data.notes import note_name_to_semitone, SHARP_NAMES

# ── Chord Quality Intervals ───────────────────────────────
CHORD_INTERVALS = {
    "Major":   [0, 4, 7],
    "Minor":   [0, 3, 7],
    "7":       [0, 4, 7, 10],
    "Maj7":    [0, 4, 7, 11],
    "Min7":    [0, 3, 7, 10],
    "Sus2":    [0, 2, 7],
    "Sus4":    [0, 5, 7],
    "Dim":     [0, 3, 6],
    "Aug":     [0, 4, 8],
    "Add9":    [0, 2, 4, 7],
    "Power":   [0, 7],
    "9":       [0, 4, 7, 10, 14],
    "Maj9":    [0, 4, 7, 11, 14],
    "Min9":    [0, 3, 7, 10, 14],
    "Dim7":    [0, 3, 6, 9],
    "Min7b5":  [0, 3, 6, 10],
}

CHORD_QUALITIES = list(CHORD_INTERVALS.keys())

# ── Barre Shape Templates ─────────────────────────────────
# Each template defines the fret offsets relative to the barre position.
# "barre_pos" means: frets values are offsets added to the barre fret.
# "root_string" is which string (0-5) carries the root note.
# The barre fret for a given root is calculated from the root string.
#
# E-shape: root on string 0 (low E). Open E = fret 0.
# A-shape: root on string 1 (A). Open A = fret 0.

# fmt: off
BARRE_TEMPLATES = {
    "Major": {
        "E": {"frets": [0, 2, 2, 1, 0, 0], "fingers": [1, 3, 4, 2, 1, 1], "root_string": 0},
        "A": {"frets": [-1, 0, 2, 2, 2, 0], "fingers": [0, 1, 2, 3, 4, 1], "root_string": 1},
        "D": {"frets": [-1, -1, 0, 2, 3, 2], "fingers": [0, 0, 1, 3, 4, 2], "root_string": 2},
    },
    "Minor": {
        "E": {"frets": [0, 2, 2, 0, 0, 0], "fingers": [1, 3, 4, 1, 1, 1], "root_string": 0},
        "A": {"frets": [-1, 0, 2, 2, 1, 0], "fingers": [0, 1, 3, 4, 2, 1], "root_string": 1},
        "D": {"frets": [-1, -1, 0, 2, 3, 1], "fingers": [0, 0, 1, 3, 4, 2], "root_string": 2},
    },
    "7": {
        "E": {"frets": [0, 2, 0, 1, 0, 0], "fingers": [1, 3, 1, 2, 1, 1], "root_string": 0},
        "A": {"frets": [-1, 0, 2, 0, 2, 0], "fingers": [0, 1, 2, 1, 3, 1], "root_string": 1},
        "D": {"frets": [-1, -1, 0, 2, 1, 2], "fingers": [0, 0, 1, 3, 2, 4], "root_string": 2},
    },
    "Maj7": {
        "E": {"frets": [0, 2, 1, 1, 0, 0], "fingers": [1, 3, 2, 2, 1, 1], "root_string": 0},
        "A": {"frets": [-1, 0, 2, 1, 2, 0], "fingers": [0, 1, 3, 2, 4, 1], "root_string": 1},
        "D": {"frets": [-1, -1, 0, 2, 2, 2], "fingers": [0, 0, 1, 2, 2, 2], "root_string": 2},
    },
    "Min7": {
        "E": {"frets": [0, 2, 0, 0, 0, 0], "fingers": [1, 3, 1, 1, 1, 1], "root_string": 0},
        "A": {"frets": [-1, 0, 2, 0, 1, 0], "fingers": [0, 1, 3, 1, 2, 1], "root_string": 1},
        "D": {"frets": [-1, -1, 0, 2, 1, 1], "fingers": [0, 0, 1, 3, 2, 2], "root_string": 2},
    },
    "Sus2": {
        "E": {"frets": [0, 2, 2, -1, 0, 0], "fingers": [1, 3, 4, 0, 1, 1], "root_string": 0},
        "A": {"frets": [-1, 0, 2, 2, 0, 0], "fingers": [0, 1, 3, 4, 1, 1], "root_string": 1},
        "D": {"frets": [-1, -1, 0, 2, 3, 0], "fingers": [0, 0, 1, 3, 4, 1], "root_string": 2},
    },
    "Sus4": {
        "E": {"frets": [0, 2, 2, 2, 0, 0], "fingers": [1, 2, 3, 4, 1, 1], "root_string": 0},
        "A": {"frets": [-1, 0, 2, 2, 3, 0], "fingers": [0, 1, 2, 3, 4, 1], "root_string": 1},
        "D": {"frets": [-1, -1, 0, 2, 3, 3], "fingers": [0, 0, 1, 3, 4, 4], "root_string": 2},
    },
    "Dim": {
        "A": {"frets": [-1, 0, 1, 2, 1, -1], "fingers": [0, 1, 2, 4, 3, 0], "root_string": 1},
    },
    "Aug": {
        "E": {"frets": [0, 3, 2, 1, 0, -1], "fingers": [1, 4, 3, 2, 1, 0], "root_string": 0},
    },
    "Add9": {
        "A": {"frets": [-1, 0, 2, 2, 2, 2], "fingers": [0, 1, 2, 3, 3, 3], "root_string": 1},
    },
    "Power": {
        "E": {"frets": [0, 2, 2, -1, -1, -1], "fingers": [1, 3, 4, 0, 0, 0], "root_string": 0},
        "A": {"frets": [-1, 0, 2, 2, -1, -1], "fingers": [0, 1, 3, 4, 0, 0], "root_string": 1},
    },
    "9": {
        "E": {"frets": [0, 2, 0, 1, 0, 2], "fingers": [1, 3, 1, 2, 1, 4], "root_string": 0},
        "A": {"frets": [-1, 0, 2, 0, 2, 2], "fingers": [0, 1, 3, 1, 4, 2], "root_string": 1},
    },
    "Maj9": {
        "A": {"frets": [-1, 0, 2, 1, 2, 2], "fingers": [0, 1, 3, 2, 4, 4], "root_string": 1},
    },
    "Min9": {
        "A": {"frets": [-1, 0, 2, 0, 1, 2], "fingers": [0, 1, 3, 1, 2, 4], "root_string": 1},
    },
    "Dim7": {
        "A": {"frets": [-1, 0, 1, 2, 1, 2], "fingers": [0, 1, 2, 4, 3, 4], "root_string": 1},
    },
    "Min7b5": {
        "A": {"frets": [-1, 0, 1, 2, 1, 0], "fingers": [0, 1, 2, 4, 3, 1], "root_string": 1},
    },
}
# fmt: on

# ── Open Chord Overrides ──────────────────────────────────
# Hand-coded open voicings that sound better than barre shapes at low positions.
# Keys are (root_name, quality) tuples.

# fmt: off
OPEN_OVERRIDES = {
    # ── Major ──
    ("C", "Major"):  [{"frets": [-1, 3, 2, 0, 1, 0], "fingers": [0, 3, 2, 0, 1, 0], "label": "Open C"},
                      {"frets": [3, 3, 2, 0, 1, 0],  "fingers": [3, 4, 2, 0, 1, 0], "label": "Open C/G"}],
    ("D", "Major"):  [{"frets": [-1, -1, 0, 2, 3, 2], "fingers": [0, 0, 0, 1, 3, 2], "label": "Open D"}],
    ("E", "Major"):  [{"frets": [0, 2, 2, 1, 0, 0],  "fingers": [0, 2, 3, 1, 0, 0], "label": "Open E"}],
    ("F", "Major"):  [{"frets": [1, 3, 3, 2, 1, 1],  "fingers": [1, 3, 4, 2, 1, 1], "label": "F Barre"}],
    ("G", "Major"):  [{"frets": [3, 2, 0, 0, 0, 3],  "fingers": [2, 1, 0, 0, 0, 3], "label": "Open G"},
                      {"frets": [3, 2, 0, 0, 3, 3],  "fingers": [2, 1, 0, 0, 3, 4], "label": "Open G (4-finger)"}],
    ("A", "Major"):  [{"frets": [-1, 0, 2, 2, 2, 0], "fingers": [0, 0, 1, 2, 3, 0], "label": "Open A"}],
    ("B", "Major"):  [{"frets": [-1, 2, 4, 4, 4, 2], "fingers": [0, 1, 2, 3, 4, 1], "label": "B Barre"}],

    # ── Minor ──
    ("C", "Minor"):  [{"frets": [-1, 3, 5, 5, 4, 3], "fingers": [0, 1, 3, 4, 2, 1], "label": "Cm Barre"}],
    ("D", "Minor"):  [{"frets": [-1, -1, 0, 2, 3, 1], "fingers": [0, 0, 0, 2, 3, 1], "label": "Open Dm"}],
    ("E", "Minor"):  [{"frets": [0, 2, 2, 0, 0, 0],  "fingers": [0, 2, 3, 0, 0, 0], "label": "Open Em"}],
    ("F", "Minor"):  [{"frets": [1, 3, 3, 1, 1, 1],  "fingers": [1, 3, 4, 1, 1, 1], "label": "Fm Barre"}],
    ("G", "Minor"):  [{"frets": [3, 5, 5, 3, 3, 3],  "fingers": [1, 3, 4, 1, 1, 1], "label": "Gm Barre"}],
    ("A", "Minor"):  [{"frets": [-1, 0, 2, 2, 1, 0], "fingers": [0, 0, 2, 3, 1, 0], "label": "Open Am"}],
    ("B", "Minor"):  [{"frets": [-1, 2, 4, 4, 3, 2], "fingers": [0, 1, 3, 4, 2, 1], "label": "Bm Barre"},
                      {"frets": [7, 9, 9, 7, 7, 7],  "fingers": [1, 3, 4, 1, 1, 1], "label": "Bm (E-shape, 7th fret)"}],
    ("F#", "Minor"): [{"frets": [2, 4, 4, 2, 2, 2],  "fingers": [1, 3, 4, 1, 1, 1], "label": "F#m Barre (E-shape, 2nd fret)"},
                      {"frets": [-1, 9, 11, 11, 10, 9], "fingers": [0, 1, 3, 4, 2, 1], "label": "F#m (A-shape, 9th fret)"}],
    ("Bb", "Major"): [{"frets": [-1, 1, 3, 3, 3, 1],  "fingers": [0, 1, 3, 3, 3, 1], "label": "Bb Barre (A-shape, 1st fret)"},
                      {"frets": [6, 8, 8, 7, 6, 6],   "fingers": [1, 3, 4, 2, 1, 1], "label": "Bb Barre (E-shape, 6th fret)"}],
    ("Eb", "Major"): [{"frets": [-1, 6, 8, 8, 8, 6],  "fingers": [0, 1, 3, 3, 3, 1], "label": "Eb Barre (A-shape, 6th fret)"},
                      {"frets": [-1, -1, 5, 3, 4, 3],  "fingers": [0, 0, 4, 1, 2, 1], "label": "Eb (open-ish, 3rd position)"}],

    # ── 7th ──
    ("A", "7"):  [{"frets": [-1, 0, 2, 0, 2, 0], "fingers": [0, 0, 2, 0, 3, 0], "label": "Open A7"}],
    ("B", "7"):  [{"frets": [-1, 2, 1, 2, 0, 2], "fingers": [0, 2, 1, 3, 0, 4], "label": "Open B7"}],
    ("C", "7"):  [{"frets": [-1, 3, 2, 3, 1, 0], "fingers": [0, 3, 2, 4, 1, 0], "label": "Open C7"}],
    ("D", "7"):  [{"frets": [-1, -1, 0, 2, 1, 2], "fingers": [0, 0, 0, 2, 1, 3], "label": "Open D7"}],
    ("E", "7"):  [{"frets": [0, 2, 0, 1, 0, 0],  "fingers": [0, 2, 0, 1, 0, 0], "label": "Open E7"}],
    ("G", "7"):  [{"frets": [3, 2, 0, 0, 0, 1],  "fingers": [3, 2, 0, 0, 0, 1], "label": "Open G7"}],

    # ── Maj7 ──
    ("C", "Maj7"): [{"frets": [-1, 3, 2, 0, 0, 0], "fingers": [0, 3, 2, 0, 0, 0], "label": "Open Cmaj7"}],
    ("D", "Maj7"): [{"frets": [-1, -1, 0, 2, 2, 2], "fingers": [0, 0, 0, 1, 2, 3], "label": "Open Dmaj7"}],
    ("E", "Maj7"): [{"frets": [0, 2, 1, 1, 0, 0],  "fingers": [0, 3, 2, 1, 0, 0], "label": "Open Emaj7"}],
    ("F", "Maj7"): [{"frets": [-1, -1, 3, 2, 1, 0], "fingers": [0, 0, 3, 2, 1, 0], "label": "Open Fmaj7"}],
    ("G", "Maj7"): [{"frets": [3, 2, 0, 0, 0, 2],  "fingers": [3, 2, 0, 0, 0, 1], "label": "Open Gmaj7"}],
    ("A", "Maj7"): [{"frets": [-1, 0, 2, 1, 2, 0], "fingers": [0, 0, 2, 1, 3, 0], "label": "Open Amaj7"}],

    # ── Min7 ──
    ("A", "Min7"): [{"frets": [-1, 0, 2, 0, 1, 0], "fingers": [0, 0, 2, 0, 1, 0], "label": "Open Am7"}],
    ("D", "Min7"): [{"frets": [-1, -1, 0, 2, 1, 1], "fingers": [0, 0, 0, 2, 1, 1], "label": "Open Dm7"}],
    ("E", "Min7"): [{"frets": [0, 2, 0, 0, 0, 0],  "fingers": [0, 2, 0, 0, 0, 0], "label": "Open Em7"}],
    ("B", "Min7"): [{"frets": [-1, 2, 0, 2, 0, 2], "fingers": [0, 2, 0, 3, 0, 4], "label": "Open Bm7"}],

    # ── Sus2 ──
    ("A", "Sus2"): [{"frets": [-1, 0, 2, 2, 0, 0], "fingers": [0, 0, 1, 2, 0, 0], "label": "Open Asus2"}],
    ("D", "Sus2"): [{"frets": [-1, -1, 0, 2, 3, 0], "fingers": [0, 0, 0, 1, 2, 0], "label": "Open Dsus2"}],
    ("E", "Sus2"): [{"frets": [0, 2, 4, 4, 0, 0],  "fingers": [0, 1, 3, 4, 0, 0], "label": "Open Esus2"}],

    # ── Sus4 ──
    ("A", "Sus4"): [{"frets": [-1, 0, 2, 2, 3, 0], "fingers": [0, 0, 1, 2, 3, 0], "label": "Open Asus4"}],
    ("D", "Sus4"): [{"frets": [-1, -1, 0, 2, 3, 3], "fingers": [0, 0, 0, 1, 2, 3], "label": "Open Dsus4"}],
    ("E", "Sus4"): [{"frets": [0, 2, 2, 2, 0, 0],  "fingers": [0, 2, 3, 4, 0, 0], "label": "Open Esus4"}],

    # ── Power ──
    ("E", "Power"): [{"frets": [0, 2, 2, -1, -1, -1], "fingers": [0, 2, 3, 0, 0, 0], "label": "Open E5"}],
    ("A", "Power"): [{"frets": [-1, 0, 2, 2, -1, -1], "fingers": [0, 0, 1, 2, 0, 0], "label": "Open A5"}],
    ("D", "Power"): [{"frets": [-1, -1, 0, 2, 3, -1], "fingers": [0, 0, 0, 1, 2, 0], "label": "Open D5"}],
    ("G", "Power"): [{"frets": [3, 5, 5, -1, -1, -1], "fingers": [1, 3, 4, 0, 0, 0], "label": "G5"}],

    # ── 9th ──
    ("A", "9"):  [{"frets": [-1, 0, 2, 0, 2, 2], "fingers": [0, 0, 2, 0, 3, 4], "label": "Open A9"}],
    ("D", "9"):  [{"frets": [-1, -1, 0, 2, 1, 2], "fingers": [0, 0, 0, 2, 1, 3], "label": "Open D9"}],
    ("E", "9"):  [{"frets": [0, 2, 0, 1, 0, 2], "fingers": [0, 2, 0, 1, 0, 3], "label": "Open E9"}],
    ("G", "9"):  [{"frets": [3, 0, 0, 0, 0, 1], "fingers": [3, 0, 0, 0, 0, 1], "label": "Open G9"}],
}
# fmt: on


def _barre_fret_for_root(root_semitone, template):
    """
    Calculate the barre fret for a given root using the template's root string.
    E-shape root string = 0 (open = E = semitone 4)
    A-shape root string = 1 (open = A = semitone 9)
    """
    open_notes = [4, 9, 2, 7, 11, 4]  # Semitones for open strings E A D G B E
    root_string = template["root_string"]
    open_semitone = open_notes[root_string]
    barre_fret = (root_semitone - open_semitone) % 12
    return barre_fret


def _apply_barre_template(template, barre_fret):
    """
    Apply a barre template at the given fret position.
    Returns frets and fingers lists.
    """
    base_frets = template["frets"]
    base_fingers = template["fingers"]
    frets = []
    fingers = list(base_fingers)

    for i, f in enumerate(base_frets):
        if f == -1:
            frets.append(-1)
        else:
            frets.append(f + barre_fret)

    return frets, fingers


def get_voicings(root_name, quality):
    """
    Get all voicings for a chord.
    Returns list of dicts: {frets, fingers, label, position}

    Priority: open overrides first, then barre shapes sorted by fret position.
    """
    # Normalize root name (take first part of enharmonic)
    if "/" in root_name:
        root_name = root_name.split("/")[0]
    root_semi = note_name_to_semitone(root_name)

    voicings = []

    # 1. Check for open overrides
    open_key = (root_name, quality)
    if open_key in OPEN_OVERRIDES:
        for ov in OPEN_OVERRIDES[open_key]:
            voicings.append({
                "frets": ov["frets"],
                "fingers": ov["fingers"],
                "label": ov.get("label", "Open"),
                "position": 0,
            })

    # 2. Generate barre shapes from templates
    if quality in BARRE_TEMPLATES:
        for shape_name, template in BARRE_TEMPLATES[quality].items():
            barre_fret = _barre_fret_for_root(root_semi, template)

            # Skip barre at fret 0 if we already have an open override
            if barre_fret == 0 and voicings:
                continue

            frets, fingers = _apply_barre_template(template, barre_fret)

            # Only include if the position is reasonable (frets 1-12)
            max_fret = max(f for f in frets if f > 0) if any(f > 0 for f in frets) else 0
            if max_fret <= 15:
                label = f"{shape_name}-shape (fret {barre_fret})"
                voicings.append({
                    "frets": frets,
                    "fingers": fingers,
                    "label": label,
                    "position": barre_fret,
                })

    # Sort: open voicings first, then by position
    voicings.sort(key=lambda v: (v["position"] > 0, v["position"]))

    # Deduplicate by fret pattern
    seen = set()
    unique = []
    for v in voicings:
        key = tuple(v["frets"])
        if key not in seen:
            seen.add(key)
            unique.append(v)

    # Limit to 4 voicings
    return unique[:4]


def get_chord_display_name(root_name, quality):
    """Get the display name for a chord (e.g., 'Am7', 'F#dim')."""
    suffix_map = {
        "Major":   "",
        "Minor":   "m",
        "7":       "7",
        "Maj7":    "maj7",
        "Min7":    "m7",
        "Sus2":    "sus2",
        "Sus4":    "sus4",
        "Dim":     "dim",
        "Aug":     "aug",
        "Add9":    "add9",
        "Power":   "5",
        "9":       "9",
        "Maj9":    "maj9",
        "Min9":    "m9",
        "Dim7":    "dim7",
        "Min7b5":  "m7b5",
    }
    suffix = suffix_map.get(quality, quality)
    return f"{root_name}{suffix}"


def parse_chord_name(name):
    """
    Parse a chord name string into (root, quality).
    Examples: 'Am7' -> ('A', 'Min7'), 'F#' -> ('F#', 'Major'), 'Cmaj7' -> ('C', 'Maj7')
    Returns (root_name, quality) or (None, None) if unparseable.
    """
    name = name.strip()
    if not name:
        return None, None

    # Extract root (1 or 2 chars)
    root = name[0].upper()
    rest = name[1:]

    if rest and rest[0] in ("#", "b"):
        root += rest[0]
        rest = rest[1:]

    # Validate root
    try:
        note_name_to_semitone(root)
    except ValueError:
        return None, None

    # Parse quality from remaining string
    rest_lower = rest.lower().strip()

    quality_map = {
        "": "Major",
        "m": "Minor",
        "min": "Minor",
        "minor": "Minor",
        "maj": "Major",
        "major": "Major",
        "7": "7",
        "dom7": "7",
        "maj7": "Maj7",
        "major7": "Maj7",
        "m7": "Min7",
        "min7": "Min7",
        "minor7": "Min7",
        "sus2": "Sus2",
        "sus4": "Sus4",
        "dim": "Dim",
        "diminished": "Dim",
        "aug": "Aug",
        "augmented": "Aug",
        "+": "Aug",
        "add9": "Add9",
        "5": "Power",
        "power": "Power",
        "9": "9",
        "dom9": "9",
        "maj9": "Maj9",
        "major9": "Maj9",
        "m9": "Min9",
        "min9": "Min9",
        "minor9": "Min9",
        "dim7": "Dim7",
        "diminished7": "Dim7",
        "m7b5": "Min7b5",
        "min7b5": "Min7b5",
        "halfdim": "Min7b5",
        "half-dim": "Min7b5",
        "ø": "Min7b5",
    }

    quality = quality_map.get(rest_lower)
    if quality is None:
        return None, None

    return root, quality
