"""
Movable triad voicing system for guitar.

5 voicing types × 6 qualities (Major, Minor, Dim, Aug, Sus2, Sus4) across all 12 keys.
Also provides diatonic harmonization for major, natural minor, harmonic minor,
and melodic minor keys.

Voicing derivations (offsets are relative to root_fret on root_string):
  - The entire shape moves up an octave when any computed fret would be < 0.
  - Strings listed low-to-high (0 = low E, 5 = high e).
"""

from data.notes import note_name_to_semitone, semitone_to_name, FLAT_ROOTS

# Open-string semitones: indices 0-5 = E A D G B e
_OPEN_SEMI = [4, 9, 2, 7, 11, 4]

# ── Voicing templates ─────────────────────────────────────────────────
#
# strings      3 string indices in the voicing (low → high)
# root_string  which of those strings carries the root note
# string_label human-readable string set label
# offsets      quality → [fret-offset-per-string relative to root_fret]
#              offset formula: interval_semitones - (open_midi[str] - open_midi[root_str])
#              choosing the octave that keeps the triad in ascending pitch order

TRIAD_TEMPLATES = {
    # ── 1. Root Position — Low Strings (E-A-D) ─────────────────────
    # Formula 1-3-5 ascending on strings 6-5-4
    "Root Pos (Low)": {
        "strings": [0, 1, 2],
        "root_string": 0,
        "string_label": "E-A-D",
        "offsets": {
            "Major": [ 0, -1, -3],   # root, maj3, p5
            "Minor": [ 0, -2, -3],   # root, min3, p5
            "Dim":   [ 0, -2, -4],   # root, min3, dim5
            "Aug":   [ 0, -1, -2],   # root, maj3, aug5
            "Sus2":  [ 0, -3, -3],   # root, maj2, p5  (A+D share fret)
            "Sus4":  [ 0,  0, -3],   # root, p4, p5   (E+A share fret)
        },
    },

    # ── 2. First Inversion (A-D-G) ─────────────────────────────────
    # Formula 3-5-1 ascending on strings 5-4-3
    "1st Inversion": {
        "strings": [1, 2, 3],
        "root_string": 3,            # root is the highest note in this voicing
        "string_label": "A-D-G",
        "offsets": {
            "Major": [+2,  0,  0],   # maj3(bass), p5, root
            "Minor": [+1,  0,  0],   # min3(bass), p5, root
            "Dim":   [+1, -1,  0],   # min3(bass), dim5, root
            "Aug":   [+2, +1,  0],   # maj3(bass), aug5, root
            "Sus2":  [ 0,  0,  0],   # maj2(bass), p5, root  (full barre)
            "Sus4":  [+3,  0,  0],   # p4(bass), p5, root
        },
    },

    # ── 3. Second Inversion (D-G-B) ────────────────────────────────
    # Formula 5-1-3 ascending on strings 4-3-2
    "2nd Inversion": {
        "strings": [2, 3, 4],
        "root_string": 3,            # root is the middle note in this voicing
        "string_label": "D-G-B",
        "offsets": {
            "Major": [ 0,  0,  0],   # p5(bass), root, maj3  — all same fret!
            "Minor": [ 0,  0, -1],   # p5(bass), root, min3
            "Dim":   [-1,  0, -1],   # dim5(bass), root, min3
            "Aug":   [+1,  0,  0],   # aug5(bass), root, maj3
            "Sus2":  [ 0,  0, -2],   # p5(bass), root, maj2
            "Sus4":  [ 0,  0, +1],   # p5(bass), root, p4
        },
    },

    # ── 4. Root Position — High Strings (G-B-e) ────────────────────
    # Formula 1-3-5 ascending on strings 3-2-1
    "Root Pos (High)": {
        "strings": [3, 4, 5],
        "root_string": 3,            # root is the lowest string here
        "string_label": "G-B-e",
        "offsets": {
            "Major": [ 0,  0, -2],   # root, maj3, p5
            "Minor": [ 0, -1, -2],   # root, min3, p5
            "Dim":   [ 0, -1, -3],   # root, min3, dim5
            "Aug":   [ 0,  0, -1],   # root, maj3, aug5
            "Sus2":  [ 0, -2, -2],   # root, maj2, p5  (B+e share fret)
            "Sus4":  [ 0, +1, -2],   # root, p4, p5
        },
    },

    # ── 5. Spread Triad — Drop-2 feel (E-D-B) ──────────────────────
    # Formula 1-5-3 on strings 6-4-2 (skip-string, wide voicing)
    "Spread Triad": {
        "strings": [0, 2, 4],
        "root_string": 0,
        "string_label": "E-D-B",
        "offsets": {
            "Major": [ 0, -3, -3],   # root, p5, maj3(+8va)
            "Minor": [ 0, -3, -4],   # root, p5, min3(+8va)
            "Dim":   [ 0, -4, -4],   # root, dim5, min3(+8va)
            "Aug":   [ 0, -2, -3],   # root, aug5, maj3(+8va)
            "Sus2":  [ 0, -3, -5],   # root, p5, maj2(+8va)
            "Sus4":  [ 0, -3, -2],   # root, p5, p4(+8va)
        },
    },
}

TRIAD_VOICING_NAMES = list(TRIAD_TEMPLATES.keys())

# ── Diatonic major-key harmonization ─────────────────────────────────
# I  ii  iii  IV  V  vi  vii°
_DIATONIC_DEGREES   = [0, 2, 4, 5, 7, 9, 11]
_DIATONIC_QUALITIES = ["Major", "Minor", "Minor", "Major", "Major", "Minor", "Dim"]
_ROMAN_NUMERALS     = ["I", "ii", "iii", "IV", "V", "vi", "vii°"]

# ── Diatonic natural-minor harmonization ─────────────────────────────
# i  ii°  III  iv  v  VI  VII
_MINOR_DEGREES   = [0, 2, 3, 5, 7, 8, 10]
_MINOR_QUALITIES = ["Minor", "Dim", "Major", "Minor", "Minor", "Major", "Major"]
_MINOR_ROMANS    = ["i", "ii°", "III", "iv", "v", "VI", "VII"]

_QUALITY_SUFFIX = {
    "Major": "",
    "Minor": "m",
    "Dim":   "°",
    "Aug":   "+",
    "Sus2":  "sus2",
    "Sus4":  "sus4",
}

# ── Diatonic harmonic-minor harmonization ─────────────────────────
# i  ii°  III+  iv  V  VI  vii°
_HARM_MINOR_DEGREES   = [0, 2, 3, 5, 7, 8, 11]
_HARM_MINOR_QUALITIES = ["Minor", "Dim", "Aug", "Minor", "Major", "Major", "Dim"]
_HARM_MINOR_ROMANS    = ["i", "ii°", "III+", "iv", "V", "VI", "vii°"]

# ── Diatonic melodic-minor harmonization (ascending) ─────────────
# i  ii  bIII+  IV  V  vi°  vii°
_MELO_MINOR_DEGREES   = [0, 2, 3, 5, 7, 9, 11]
_MELO_MINOR_QUALITIES = ["Minor", "Minor", "Aug", "Major", "Major", "Dim", "Dim"]
_MELO_MINOR_ROMANS    = ["i", "ii", "bIII+", "IV", "V", "vi°", "vii°"]


# ── Core computation ──────────────────────────────────────────────────

def _compute_triad_frets(root_semi, quality, voicing_name):
    """
    Compute the 6-element frets list for one triad voicing.

    Strings not in the voicing are set to -1 (muted).
    The entire shape shifts up an octave when any fret would be negative.
    """
    tmpl = TRIAD_TEMPLATES[voicing_name]
    strings = tmpl["strings"]
    root_string = tmpl["root_string"]
    offsets = tmpl["offsets"][quality]

    root_fret = (root_semi - _OPEN_SEMI[root_string]) % 12

    if root_fret + min(offsets) < 0:
        root_fret += 12
    frets = [-1] * 6
    for i, s in enumerate(strings):
        frets[s] = root_fret + offsets[i]
    from data.instrument import adapt_voicing
    return adapt_voicing(frets, [0]*6)[0]


def _assign_fingers(strings, frets):
    """
    Assign practical finger numbers (0-4) for a 3-note triad.

    0 = open / muted, 1 = index, 2 = middle, 3 = ring, 4 = pinky.
    """
    fingers = [0] * 6
    played_non_open = sorted(
        [(s, frets[s]) for s in strings if frets[s] > 0],
        key=lambda x: x[1],
    )
    if not played_non_open:
        return fingers

    unique_frets = sorted(set(f for _, f in played_non_open))
    span = unique_frets[-1] - unique_frets[0]

    if span == 0:
        # Same-fret barre — all finger 1
        for s, _ in played_non_open:
            fingers[s] = 1
    elif span <= 2:
        # Compact shape — 1, 2, 3
        fret_to_finger = {f: i + 1 for i, f in enumerate(unique_frets)}
        for s, f in played_non_open:
            fingers[s] = fret_to_finger[f]
    elif span == 3:
        # 4-fret window — 1, 3, 4 (skip index-to-ring then ring-to-pinky)
        mapping = [1, 3, 4]
        fret_to_finger = {f: mapping[i] for i, f in enumerate(unique_frets)}
        for s, f in played_non_open:
            fingers[s] = fret_to_finger[f]
    else:
        # Wider span — 1, 2, 4
        mapping = [1, 2, 4]
        fret_to_finger = {f: mapping[min(i, 2)] for i, f in enumerate(unique_frets)}
        for s, f in played_non_open:
            fingers[s] = fret_to_finger.get(f, 4)

    return fingers


# ── Public API ────────────────────────────────────────────────────────

def get_diatonic_triads(key_root_name, voicing_name):
    """
    Return 7 chord dicts for the diatonic major-key triads (I–vii°) using
    the given voicing type.

    Each dict: {chord_root, quality, frets, fingers, display_name, roman}
    Compatible with render_progression_strip().
    """
    if "/" in key_root_name:
        key_root_name = key_root_name.split("/")[0]

    key_semi = note_name_to_semitone(key_root_name)
    prefer_flat = key_semi in FLAT_ROOTS

    tmpl = TRIAD_TEMPLATES[voicing_name]

    chords = []
    for degree, quality, roman in zip(_DIATONIC_DEGREES, _DIATONIC_QUALITIES, _ROMAN_NUMERALS):
        chord_semi = (key_semi + degree) % 12
        chord_root = semitone_to_name(chord_semi, prefer_flat=prefer_flat)

        frets   = _compute_triad_frets(chord_semi, quality, voicing_name)
        fingers = _assign_fingers(tmpl["strings"], frets)

        chords.append({
            "chord_root":   chord_root,
            "quality":      quality,
            "frets":        frets,
            "fingers":      fingers,
            "display_name": f"{chord_root}{_QUALITY_SUFFIX[quality]}",
            "roman":        roman,
        })

    return chords


def get_diatonic_minor_triads(key_root_name, voicing_name):
    """
    Return 7 chord dicts for the diatonic natural minor triads (i–VII) using
    the given voicing type.

    Natural minor harmonization: i  ii°  III  iv  v  VI  VII
    Scale degrees (semitones):   0   2    3   5   7   8  10

    Each dict: {chord_root, quality, frets, fingers, display_name, roman}
    Compatible with render_progression_strip().
    """
    if "/" in key_root_name:
        key_root_name = key_root_name.split("/")[0]

    key_semi = note_name_to_semitone(key_root_name)
    prefer_flat = key_semi in FLAT_ROOTS

    tmpl = TRIAD_TEMPLATES[voicing_name]

    chords = []
    for degree, quality, roman in zip(_MINOR_DEGREES, _MINOR_QUALITIES, _MINOR_ROMANS):
        chord_semi = (key_semi + degree) % 12
        chord_root = semitone_to_name(chord_semi, prefer_flat=prefer_flat)

        frets   = _compute_triad_frets(chord_semi, quality, voicing_name)
        fingers = _assign_fingers(tmpl["strings"], frets)

        chords.append({
            "chord_root":   chord_root,
            "quality":      quality,
            "frets":        frets,
            "fingers":      fingers,
            "display_name": f"{chord_root}{_QUALITY_SUFFIX[quality]}",
            "roman":        roman,
        })

    return chords


def get_diatonic_harmonic_minor_triads(key_root_name, voicing_name):
    """
    Return 7 chord dicts for the diatonic harmonic minor triads (i–vii°) using
    the given voicing type.

    Harmonic minor harmonization: i  ii°  III+  iv  V  VI  vii°
    Scale degrees (semitones):    0   2    3    5   7   8   11

    Each dict: {chord_root, quality, frets, fingers, display_name, roman}
    Compatible with render_progression_strip().
    """
    if "/" in key_root_name:
        key_root_name = key_root_name.split("/")[0]

    key_semi = note_name_to_semitone(key_root_name)
    prefer_flat = key_semi in FLAT_ROOTS

    tmpl = TRIAD_TEMPLATES[voicing_name]

    chords = []
    for degree, quality, roman in zip(_HARM_MINOR_DEGREES, _HARM_MINOR_QUALITIES, _HARM_MINOR_ROMANS):
        chord_semi = (key_semi + degree) % 12
        chord_root = semitone_to_name(chord_semi, prefer_flat=prefer_flat)

        frets   = _compute_triad_frets(chord_semi, quality, voicing_name)
        fingers = _assign_fingers(tmpl["strings"], frets)

        chords.append({
            "chord_root":   chord_root,
            "quality":      quality,
            "frets":        frets,
            "fingers":      fingers,
            "display_name": f"{chord_root}{_QUALITY_SUFFIX[quality]}",
            "roman":        roman,
        })

    return chords


def get_diatonic_melodic_minor_triads(key_root_name, voicing_name):
    """
    Return 7 chord dicts for the diatonic melodic minor triads (i–vii°) using
    the given voicing type.

    Melodic minor harmonization: i  ii  bIII+  IV  V  vi°  vii°
    Scale degrees (semitones):   0   2    3    5   7   9   11

    Each dict: {chord_root, quality, frets, fingers, display_name, roman}
    Compatible with render_progression_strip().
    """
    if "/" in key_root_name:
        key_root_name = key_root_name.split("/")[0]

    key_semi = note_name_to_semitone(key_root_name)
    prefer_flat = key_semi in FLAT_ROOTS

    tmpl = TRIAD_TEMPLATES[voicing_name]

    chords = []
    for degree, quality, roman in zip(_MELO_MINOR_DEGREES, _MELO_MINOR_QUALITIES, _MELO_MINOR_ROMANS):
        chord_semi = (key_semi + degree) % 12
        chord_root = semitone_to_name(chord_semi, prefer_flat=prefer_flat)

        frets   = _compute_triad_frets(chord_semi, quality, voicing_name)
        fingers = _assign_fingers(tmpl["strings"], frets)

        chords.append({
            "chord_root":   chord_root,
            "quality":      quality,
            "frets":        frets,
            "fingers":      fingers,
            "display_name": f"{chord_root}{_QUALITY_SUFFIX[quality]}",
            "roman":        roman,
        })

    return chords


TRIAD_QUALITIES = list(_QUALITY_SUFFIX.keys())


def get_triad_voicing(root_name, quality, voicing_name):
    """
    Return a single triad voicing dict: {frets, fingers, display_name, position}
    Useful for integration with the main chord voicing system.
    """
    if "/" in root_name:
        root_name = root_name.split("/")[0]

    root_semi = note_name_to_semitone(root_name)
    tmpl = TRIAD_TEMPLATES[voicing_name]

    frets   = _compute_triad_frets(root_semi, quality, voicing_name)
    fingers = _assign_fingers(tmpl["strings"], frets)

    suffix = _QUALITY_SUFFIX.get(quality, "")
    root_fret = (root_semi - _OPEN_SEMI[tmpl["root_string"]]) % 12
    root_fret = frets[tmpl["root_string"]]
    label = f"{voicing_name} (fret {root_fret})"

    return {
        "frets":        frets,
        "fingers":      fingers,
        "label":        label,
        "display_name": f"{root_name}{suffix}",
        "position":     root_fret,
    }
