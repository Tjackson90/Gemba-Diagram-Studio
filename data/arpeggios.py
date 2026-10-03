"""
Arpeggio definitions and fretboard mapping.

Arpeggios are chord tones only (not scales).  We reuse the full-fretboard
and CAGED-box infrastructure from scales.py since the note-mapping logic
is identical — only the interval set differs.
"""

from data.notes import note_name_to_semitone, FLAT_NAMES, SHARP_NAMES, STANDARD_TUNING_MIDI

# ── Arpeggio Intervals (semitones from root) ─────────────────────────
#
# Priority 1 (Essential triads)
# Priority 2 (Important triads + sevenths — names locked by progressions.py)
# Priority 3 (Extended sevenths)
# Priority 4 (Suspensions)
#
ARPEGGIO_INTERVALS = {
    # ── Priority 1: Essential triads ──────────────────────────────
    "Major":     [0, 4, 7],           # 1 3 5
    "Minor":     [0, 3, 7],           # 1 b3 5

    # ── Priority 2: Important triads + sevenths ────────────────────
    "Dim":       [0, 3, 6],           # 1 b3 b5
    "Aug":       [0, 4, 8],           # 1 3 #5
    "Maj7":      [0, 4, 7, 11],       # 1 3 5 7   (Δ7)
    "Dom7":      [0, 4, 7, 10],       # 1 3 5 b7
    "Min7":      [0, 3, 7, 10],       # 1 b3 5 b7  (m7)

    # ── Priority 3: Extended sevenths ─────────────────────────────
    "Min7b5":    [0, 3, 6, 10],       # 1 b3 b5 b7  (ø7 / half-diminished)
    "Dim7":      [0, 3, 6, 9],        # 1 b3 b5 bb7 (°7 / diminished 7th)
    "MinMaj7":   [0, 3, 7, 11],       # 1 b3 5 7    (mΔ7 / minor-major 7th)
    "AugMaj7":   [0, 4, 8, 11],       # 1 3 #5 7    (Δ7#5 / augmented major 7th)
    "Aug7":      [0, 4, 8, 10],       # 1 3 #5 b7   (+7 / augmented dominant 7th)

    # ── Priority 4: Suspensions ────────────────────────────────────
    "Sus2":      [0, 2, 7],           # 1 2 5
    "Sus4":      [0, 5, 7],           # 1 4 5
    "7sus4":     [0, 5, 7, 10],       # 1 4 5 b7
}

ARPEGGIO_NAMES = list(ARPEGGIO_INTERVALS.keys())

# Merge any user-saved custom arpeggios into the live dicts at import time
try:
    from data.custom_library import load_into_arpeggio_dicts as _load_custom
    _load_custom(ARPEGGIO_INTERVALS, ARPEGGIO_NAMES)
except Exception:
    pass


def get_arpeggio_notes_set(root_semitone, arpeggio_name):
    """Return the set of semitones (0-11) in the arpeggio."""
    intervals = ARPEGGIO_INTERVALS.get(arpeggio_name, [])
    return {(root_semitone + i) % 12 for i in intervals}


def get_full_fretboard_arpeggio(root_name, arpeggio_name, num_frets=15):
    """
    Get all arpeggio notes on the full fretboard.

    Returns list of dicts:
        {string, fret, semitone, note_name, is_root}
    """
    if "/" in root_name:
        root_name = root_name.split("/")[0]
    root_semi = note_name_to_semitone(root_name)
    arp_notes = get_arpeggio_notes_set(root_semi, arpeggio_name)

    if not arp_notes:
        return []

    prefer_flat = root_semi in {1, 3, 6, 8, 10}
    result = []
    for string_idx in range(6):
        open_midi = STANDARD_TUNING_MIDI[string_idx]
        for fret in range(num_frets + 1):
            midi = open_midi + fret
            semi = midi % 12
            if semi in arp_notes:
                name = FLAT_NAMES[semi] if prefer_flat else SHARP_NAMES[semi]
                result.append({
                    "string": string_idx,
                    "fret": fret,
                    "semitone": semi,
                    "note_name": name,
                    "is_root": (semi == root_semi),
                })
    return result


def get_arpeggio_positions(root_name, arpeggio_name, num_frets=15):
    """
    Generate 5 CAGED box positions for an arpeggio.

    Uses the same standard CAGED spacing as scale positions: five box windows
    start at semitone offsets [0, 2, 5, 7, 10] above the root fret on the low
    E string, each covering a strict 4-fret window.

    Returns list of dicts:
        {position_num, start_fret, end_fret, notes}
    """
    if "/" in root_name:
        root_name = root_name.split("/")[0]
    root_semi = note_name_to_semitone(root_name)

    intervals = ARPEGGIO_INTERVALS.get(arpeggio_name, [])
    if not intervals:
        return []

    # ── Root fret on low E (open E = MIDI 40, semitone 4) ──────────
    open_e_semi = 4
    root_fret_on_low_e = (root_semi - open_e_semi) % 12

    # ── CAGED box start offsets from root fret ──────────────────────
    CAGED_OFFSETS = [0, 2, 5, 7, 10]

    # Fetch enough fretboard to cover all 5 boxes
    search_frets = max(num_frets, root_fret_on_low_e + 10 + 4)
    all_notes = get_full_fretboard_arpeggio(root_name, arpeggio_name, search_frets)

    positions = []
    for i, offset in enumerate(CAGED_OFFSETS):
        box_start = root_fret_on_low_e + offset
        box_end   = box_start + 4

        # All arpeggio notes within the strict 4-fret window
        box_notes = [n for n in all_notes if box_start <= n["fret"] <= box_end]

        # Grace-fret: extend one fret outside the window for any empty string
        strings_covered = {n["string"] for n in box_notes}
        for n in all_notes:
            if n["string"] not in strings_covered:
                if box_start - 1 <= n["fret"] <= box_end + 1:
                    box_notes.append(n)
                    strings_covered.add(n["string"])

        # Include open strings when the box is near the nut
        if box_start <= 2:
            for n in all_notes:
                if n["fret"] == 0 and n not in box_notes:
                    box_notes.append(n)

        positions.append({
            "position_num": i + 1,
            "start_fret": box_start,
            "end_fret": box_end,
            "notes": sorted(box_notes, key=lambda n: (n["string"], n["fret"])),
        })

    return positions


_INTERVAL_LABELS = {
    0: "R", 1: "b2", 2: "2", 3: "b3", 4: "3", 5: "4",
    6: "b5", 7: "5", 8: "b6", 9: "6", 10: "b7", 11: "7",
}


def get_arpeggio_interval_labels(arpeggio_name):
    """Return interval labels, e.g. ['R', 'b3', '5'] for Minor."""
    intervals = ARPEGGIO_INTERVALS.get(arpeggio_name, [])
    return [_INTERVAL_LABELS[i] for i in intervals]


def get_arpeggio_display_name(root_name, arpeggio_name):
    """e.g. 'A Minor Arpeggio'"""
    return f"{root_name} {arpeggio_name} Arpeggio"
