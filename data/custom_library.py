"""
Custom Scale & Arpeggio Library — persistent storage and runtime patching.

Saves user-defined scales and arpeggios to custom_library.json in the project
root.  At import time (called from scales.py and arpeggios.py) it merges any
saved custom entries into the live SCALE_INTERVALS / ARPEGGIO_INTERVALS dicts
so that every downstream function — diagrams, audio, tabs, progressions —
works with them automatically.
"""

import json
import config

CUSTOM_FILE = config.PROJECT_ROOT / "custom_library.json"

# ── Prefix used to mark custom entries (prevents collision with built-ins) ──
CUSTOM_PREFIX = "★ "


def load_raw() -> dict:
    """Return the raw dict from disk: {scales: {...}, arpeggios: {...}}"""
    if CUSTOM_FILE.exists():
        try:
            with open(CUSTOM_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("scales", {})
                data.setdefault("arpeggios", {})
                return data
        except Exception:
            pass
    return {"scales": {}, "arpeggios": {}}


def _save_raw(data: dict):
    """Write the raw dict to disk."""
    with open(CUSTOM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── Runtime patching ────────────────────────────────────────────────────────

def load_into_scale_dicts(scale_intervals: dict, scale_names: list):
    """
    Merge saved custom scales into the live SCALE_INTERVALS dict and
    SCALE_NAMES list.  Called once at scales.py import time.
    """
    data = load_raw()
    for name, intervals in data["scales"].items():
        tagged = CUSTOM_PREFIX + name
        if tagged not in scale_intervals:
            scale_intervals[tagged] = intervals
            scale_names.append(tagged)


def load_into_arpeggio_dicts(arpeggio_intervals: dict, arpeggio_names: list):
    """
    Merge saved custom arpeggios into the live ARPEGGIO_INTERVALS dict and
    ARPEGGIO_NAMES list.  Called once at arpeggios.py import time.
    """
    data = load_raw()
    for name, intervals in data["arpeggios"].items():
        tagged = CUSTOM_PREFIX + name
        if tagged not in arpeggio_intervals:
            arpeggio_intervals[tagged] = intervals
            arpeggio_names.append(tagged)


# ── CRUD ────────────────────────────────────────────────────────────────────

def add_custom_scale(display_name: str, intervals: list,
                     scale_intervals: dict, scale_names: list) -> str:
    """
    Save a new custom scale.  Patches the live dicts immediately.
    Returns the tagged name used as the dict key (with ★ prefix).
    Raises ValueError on bad input.
    """
    _validate(display_name, intervals)
    data = load_raw()
    if display_name in data["scales"]:
        raise ValueError(f"A custom scale named '{display_name}' already exists.")
    data["scales"][display_name] = intervals
    _save_raw(data)

    tagged = CUSTOM_PREFIX + display_name
    scale_intervals[tagged] = intervals
    if tagged not in scale_names:
        scale_names.append(tagged)
    return tagged


def delete_custom_scale(display_name: str,
                        scale_intervals: dict, scale_names: list):
    """Remove a custom scale by its display name (without ★ prefix)."""
    data = load_raw()
    data["scales"].pop(display_name, None)
    _save_raw(data)

    tagged = CUSTOM_PREFIX + display_name
    scale_intervals.pop(tagged, None)
    if tagged in scale_names:
        scale_names.remove(tagged)


def add_custom_arpeggio(display_name: str, intervals: list,
                        arpeggio_intervals: dict, arpeggio_names: list) -> str:
    """Save a new custom arpeggio. Patches the live dicts immediately."""
    _validate(display_name, intervals)
    data = load_raw()
    if display_name in data["arpeggios"]:
        raise ValueError(f"A custom arpeggio named '{display_name}' already exists.")
    data["arpeggios"][display_name] = intervals
    _save_raw(data)

    tagged = CUSTOM_PREFIX + display_name
    arpeggio_intervals[tagged] = intervals
    if tagged not in arpeggio_names:
        arpeggio_names.append(tagged)
    return tagged


def delete_custom_arpeggio(display_name: str,
                           arpeggio_intervals: dict, arpeggio_names: list):
    """Remove a custom arpeggio by its display name (without ★ prefix)."""
    data = load_raw()
    data["arpeggios"].pop(display_name, None)
    _save_raw(data)

    tagged = CUSTOM_PREFIX + display_name
    arpeggio_intervals.pop(tagged, None)
    if tagged in arpeggio_names:
        arpeggio_names.remove(tagged)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _validate(name: str, intervals: list):
    if not name or not name.strip():
        raise ValueError("Name cannot be empty.")
    if not isinstance(intervals, list) or len(intervals) < 2:
        raise ValueError("An interval set needs at least 2 notes.")
    for iv in intervals:
        if not isinstance(iv, int) or not (0 <= iv <= 11):
            raise ValueError(f"Each interval must be an integer 0-11. Got: {iv!r}")
    if intervals[0] != 0:
        raise ValueError("First interval must be 0 (the root).")
    if len(set(intervals)) != len(intervals):
        raise ValueError("Intervals must be unique.")


def parse_interval_string(raw: str) -> list:
    """
    Parse a user-typed interval string like "0, 2, 4, 5, 7, 9, 11"
    into a sorted list of ints.  Raises ValueError on bad input.
    """
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    if not parts:
        raise ValueError("No intervals entered.")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        raise ValueError("Intervals must be integers separated by commas.")
    nums = sorted(set(nums))
    return nums


def list_custom_scales() -> dict:
    """Return {display_name: intervals} for all saved custom scales."""
    return dict(load_raw()["scales"])


def list_custom_arpeggios() -> dict:
    """Return {display_name: intervals} for all saved custom arpeggios."""
    return dict(load_raw()["arpeggios"])
