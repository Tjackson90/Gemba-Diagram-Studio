"""
Video export — renders animated diagrams + audio as MP4 via ffmpeg.

Each note/beat gets its own frame with the active note highlighted.
ffmpeg stitches the frame sequence with the pre-generated audio track.

Requirements:
  - ffmpeg must be on the system PATH (https://ffmpeg.org/download.html)
  - numpy (already required by audio engine)
  - Pillow (already required by diagram renderers)
"""

import io
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

import config
from data.notes import STANDARD_TUNING_MIDI
from audio.engine import SAMPLE_RATE, export_wav

# Output resolution — landscape 16:9 and portrait 9:16
VIDEO_W          = 1920
VIDEO_H          = 1080
VIDEO_W_PORTRAIT = 1080
VIDEO_H_PORTRAIT = 1920
# Brand navy background colour in hex for ffmpeg pad filter
_NAVY_HEX = "0b1e3d"
# Render frames at this multiplier above the diagram's base size for crispness
RENDER_SCALE = 2


# ── Helpers ────────────────────────────────────────────────

def _dims(portrait=False):
    """Return (output_w, output_h) for the chosen aspect ratio."""
    return (VIDEO_W_PORTRAIT, VIDEO_H_PORTRAIT) if portrait else (VIDEO_W, VIDEO_H)


def _paste_centered(canvas, src, mask=None):
    """Paste *src* centred on *canvas* in-place."""
    x = (canvas.width  - src.width)  // 2
    y = (canvas.height - src.height) // 2
    canvas.paste(src, (x, y), mask)


def _prepare_frame(img, portrait=False):
    """
    Composite a diagram image onto a navy background (letterboxed).

    portrait=False → 1920×1080 (16:9)
    portrait=True  → 1080×1920 (9:16)

    Renders at RENDER_SCALE × then downsamples for crispness.
    """
    from PIL import Image as _Image

    out_w, out_h = _dims(portrait)
    target_w = out_w * RENDER_SCALE
    target_h = out_h * RENDER_SCALE

    scale = min(target_w / img.width, target_h / img.height)
    diag_w = int(img.width  * scale)
    diag_h = int(img.height * scale)
    scaled_diag = img.resize((diag_w, diag_h), _Image.Resampling.LANCZOS)

    canvas = _Image.new("RGB", (target_w, target_h), config.NAVY_DEEP)
    mask = scaled_diag.split()[3] if scaled_diag.mode == "RGBA" else None
    _paste_centered(canvas, scaled_diag.convert("RGB"), mask)

    return canvas.resize((out_w, out_h), _Image.Resampling.LANCZOS)


def _prepare_combined_frame(diagram_img, tab_img, portrait=False):
    """
    Composite diagram (top) + tab (bottom) onto a navy background.

    Portrait (9:16 1080×1920): diagram occupies top 65%, tab bottom 35%.
    Landscape (16:9 1920×1080): diagram occupies top 68%, tab bottom 32%.
    Both sections are letterboxed/centred within their allocated band.
    """
    from PIL import Image as _Image, ImageDraw as _ImageDraw

    out_w, out_h = _dims(portrait)
    tw = out_w * RENDER_SCALE
    th = out_h * RENDER_SCALE

    diag_frac = 0.65 if portrait else 0.68
    diag_band_h = int(th * diag_frac)
    tab_band_h  = th - diag_band_h

    canvas = _Image.new("RGB", (tw, th), config.NAVY_DEEP)

    # ── Diagram band ─────────────────────────────────────────
    d_scale = min(tw / diagram_img.width, diag_band_h / diagram_img.height)
    dw = int(diagram_img.width  * d_scale)
    dh = int(diagram_img.height * d_scale)
    scaled_diag = diagram_img.resize((dw, dh), _Image.Resampling.LANCZOS)
    dx = (tw - dw) // 2
    dy = (diag_band_h - dh) // 2
    mask = scaled_diag.split()[3] if scaled_diag.mode == "RGBA" else None
    canvas.paste(scaled_diag.convert("RGB"), (dx, dy), mask)

    # Thin gold separator line
    sep_y = diag_band_h
    _ImageDraw.Draw(canvas).rectangle(
        [int(tw * 0.05), sep_y, int(tw * 0.95), sep_y + max(2, RENDER_SCALE)],
        fill=config.GOLD,
    )

    # ── Tab band ─────────────────────────────────────────────
    t_scale = min(tw / tab_img.width, tab_band_h / tab_img.height)
    ttw = int(tab_img.width  * t_scale)
    tth = int(tab_img.height * t_scale)
    scaled_tab = tab_img.resize((ttw, tth), _Image.Resampling.LANCZOS)
    tx = (tw - ttw) // 2
    ty = diag_band_h + (tab_band_h - tth) // 2
    tab_mask = scaled_tab.split()[3] if scaled_tab.mode == "RGBA" else None
    canvas.paste(scaled_tab.convert("RGB"), (tx, ty), tab_mask)

    return canvas.resize((out_w, out_h), _Image.Resampling.LANCZOS)


def _find_ffmpeg():
    """Return path to ffmpeg executable, or None if not found."""
    # Check PATH first
    found = shutil.which("ffmpeg")
    if found:
        return found
    # Winget installs to a known user-local location on Windows
    import os, glob
    winget_base = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
    )
    candidates = glob.glob(
        os.path.join(winget_base, "Gyan.FFmpeg*", "ffmpeg-*", "bin", "ffmpeg.exe")
    )
    if candidates:
        return candidates[0]
    return None


def _ffmpeg_available():
    """Return True if ffmpeg can be located."""
    return _find_ffmpeg() is not None


def _build_note_sequence(notes_data, ascending=True, descending=False, root_to_root=True):
    """
    Build the ordered MIDI sequence for scale/arpeggio playback.
    Returns list of (midi, string_idx, fret) tuples.
    Mirrors the logic in audio.engine.generate_scale_audio.
    """
    all_midi = sorted(set(
        STANDARD_TUNING_MIDI[n["string"]] + n["fret"]
        for n in notes_data
    ))

    # Build lookup: midi -> note dict (prefer lower string index for same pitch)
    midi_to_note = {}
    for n in sorted(notes_data, key=lambda x: x["string"]):
        m = STANDARD_TUNING_MIDI[n["string"]] + n["fret"]
        midi_to_note[m] = n

    if root_to_root:
        root_midi_values = sorted(set(
            STANDARD_TUNING_MIDI[n["string"]] + n["fret"]
            for n in notes_data if n.get("is_root", False)
        ))
        start_midi = root_midi_values[0] if root_midi_values else all_midi[0]
        end_midi = root_midi_values[-1] if root_midi_values else all_midi[-1]
        asc_notes = [m for m in all_midi if start_midi <= m <= end_midi]
        if not asc_notes:
            asc_notes = all_midi
    else:
        asc_notes = all_midi

    sequence_midi = []
    if ascending:
        sequence_midi.extend(asc_notes)
    if descending:
        desc = list(reversed(asc_notes[:-1] if ascending else asc_notes))
        sequence_midi.extend(desc)
        if root_to_root and sequence_midi and sequence_midi[-1] != (asc_notes[0] if asc_notes else 0):
            sequence_midi.append(asc_notes[0])

    result = []
    for m in sequence_midi:
        note = midi_to_note.get(m)
        if note:
            result.append((m, note["string"], note["fret"]))
    return result


def _wav_bytes(audio_data, sr=SAMPLE_RATE):
    """Convert float32 numpy array to WAV bytes (in-memory)."""
    buf = io.BytesIO()
    audio_16 = np.clip(audio_data, -1.0, 1.0)
    audio_16 = (audio_16 * 32767).astype(np.int16)
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_16.tobytes())
    buf.seek(0)
    return buf.read()


# ── Scale / Arpeggio Video ─────────────────────────────────

def export_scale_video(
    notes_data,
    render_fn,
    render_kwargs,
    audio_data,
    output_path,
    note_duration_ms=300,
    portrait=False,
    tab_img=None,
    fps=30,
    sr=SAMPLE_RATE,
):
    """
    Export a scale/arpeggio diagram video with per-note highlighting.

    Args:
        notes_data: list of dicts {string, fret, is_root, note_name}
        render_fn: diagram render function (render_scale_full_fretboard or render_scale_box)
        render_kwargs: dict of kwargs to pass to render_fn (excluding highlighted_notes)
        audio_data: numpy array of audio samples (from generate_scale_audio)
        output_path: output MP4 path (str or Path)
        note_duration_ms: duration per note in milliseconds (controls frame count per note)
        fps: video frame rate (default 30)
        sr: audio sample rate

    Returns:
        Path to exported MP4, or None if export failed
    """
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        print("Error: ffmpeg not found on PATH. Install from https://ffmpeg.org/download.html")
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build note sequence
    ascending = render_kwargs.pop("ascending", True)
    descending = render_kwargs.pop("descending", False)
    root_to_root = render_kwargs.pop("root_to_root", True)

    sequence = _build_note_sequence(
        notes_data, ascending=ascending, descending=descending, root_to_root=root_to_root
    )

    if not sequence:
        print("Error: empty note sequence")
        return None

    frames_per_note = max(int(fps * note_duration_ms / 1000), 1)
    total_frames = len(sequence) * frames_per_note + fps  # +1 sec tail

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # ── Render highlighted frames ────────────────────────
        frame_idx = 0
        for note_idx, (midi, si, fret) in enumerate(sequence):
            hi_set = {(si, fret)}
            hi_img = render_fn(**render_kwargs, highlighted_notes=hi_set)
            if tab_img is not None:
                frame = _prepare_combined_frame(hi_img, tab_img, portrait)
            else:
                frame = _prepare_frame(hi_img, portrait)
            for _ in range(frames_per_note):
                frame.save(tmpdir / f"frame_{frame_idx:06d}.png")
                frame_idx += 1

        # ── Tail frames (last note, no highlight) ────────────
        tail_img = render_fn(**render_kwargs, highlighted_notes=set())
        if tab_img is not None:
            tail_frame = _prepare_combined_frame(tail_img, tab_img, portrait)
        else:
            tail_frame = _prepare_frame(tail_img, portrait)
        for _ in range(fps):
            tail_frame.save(tmpdir / f"frame_{frame_idx:06d}.png")
            frame_idx += 1

        # ── Write audio WAV ──────────────────────────────────
        wav_path = tmpdir / "audio.wav"
        export_wav(audio_data, wav_path, sr=sr)

        # ── Call ffmpeg ──────────────────────────────────────
        cmd = [
            ffmpeg, "-y",
            "-framerate", str(fps),
            "-i", str(tmpdir / "frame_%06d.png"),
            "-i", str(wav_path),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(f"ffmpeg error:\n{result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            print("ffmpeg timed out")
            return None
        except Exception as e:
            print(f"ffmpeg failed: {e}")
            return None

    return output_path


# ── Chord Video ────────────────────────────────────────────

def export_chord_video(
    frets,
    render_fn,
    render_kwargs,
    audio_data,
    output_path,
    play_style="strum",
    strum_delay_ms=20,
    arpeggio_delay_ms=200,
    chord_sustain_s=2.0,
    portrait=False,
    tab_img=None,
    fps=30,
    sr=SAMPLE_RATE,
):
    """
    Export a chord diagram video with per-string highlight animation.

    Uses exact timeline matching so highlighted strings change at the same
    millisecond the corresponding note fires in the audio.

    Supports three play styles (mirrors audio/engine.py generate_chord_audio):
      - "strum":          strings fire at i * strum_delay_ms
      - "arpeggio":       strings fire at i * arpeggio_delay_ms
      - "arpeggio_strum": arp phase, then 500 ms gap, then strum phase

    Args:
        frets:              list of 6 fret values
        render_fn:          render_chord_diagram function
        render_kwargs:      dict of kwargs (excluding highlighted_strings)
        audio_data:         numpy array of chord audio
        output_path:        output MP4 path
        play_style:         "strum" | "arpeggio" | "arpeggio_strum"
        strum_delay_ms:     ms between strings during strum phase
        arpeggio_delay_ms:  ms between strings during arpeggio phase
        chord_sustain_s:    sustain duration used by the audio engine (default 2.0)
        fps:                video frame rate

    Returns:
        Path to exported MP4, or None if failed
    """
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        print("Error: ffmpeg not found on PATH. Install from https://ffmpeg.org/download.html")
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    strum_direction = render_kwargs.pop("strum_direction", "down")
    string_order = list(range(6)) if strum_direction == "down" else list(range(5, -1, -1))
    played = [i for i in string_order if frets[i] >= 0]
    n = len(played)
    sustain_ms = chord_sustain_s * 1000.0

    # ── Build event timeline ──────────────────────────────────
    # Each event: (start_ms, frozenset of highlighted strings at that time)
    # Events are sorted by start_ms and walked frame-by-frame.
    events = []  # list of (float ms, frozenset)

    if play_style == "arpeggio":
        cumulative = set()
        for idx, si in enumerate(played):
            cumulative = cumulative | {si}
            events.append((idx * arpeggio_delay_ms, frozenset(cumulative)))
        total_ms = (n - 1) * arpeggio_delay_ms + sustain_ms

    elif play_style == "arpeggio_strum":
        # Phase 1: arpeggio — matches engine's arp loop
        cumulative = set()
        for idx, si in enumerate(played):
            cumulative = cumulative | {si}
            events.append((idx * arpeggio_delay_ms, frozenset(cumulative)))

        # Strum starts at: (n-1)*arp_delay + sustain + 500 ms gap
        # (exact mirror of engine's arp_end calculation)
        strum_start_ms = (n - 1) * arpeggio_delay_ms + sustain_ms + 500.0
        events.append((strum_start_ms, frozenset()))  # gap: clear highlights

        # Phase 2: strum — matches engine's strum loop
        cumulative = set()
        for idx, si in enumerate(played):
            cumulative = cumulative | {si}
            events.append((strum_start_ms + idx * strum_delay_ms, frozenset(cumulative)))
        total_ms = strum_start_ms + sustain_ms + strum_delay_ms * 5

    else:  # strum
        cumulative = set()
        for idx, si in enumerate(played):
            cumulative = cumulative | {si}
            events.append((idx * strum_delay_ms, frozenset(cumulative)))
        total_ms = sustain_ms + strum_delay_ms * 5

    # Add tail sentinel: clear highlights after audio ends
    events.append((total_ms, frozenset()))
    events.sort(key=lambda e: e[0])

    # ── Generate frames via timeline walk ────────────────────
    ms_per_frame  = 1000.0 / fps
    # Include a 1-second static tail buffer beyond the audio
    total_frames  = int((total_ms + 1000) * fps / 1000) + 1

    render_cache  = {}   # frozenset → prepared PIL frame
    event_idx     = 0
    current_hi    = frozenset()
    frames        = []

    for frame_num in range(total_frames):
        frame_ms = frame_num * ms_per_frame
        # Advance events whose timestamp has been reached
        while event_idx < len(events) and events[event_idx][0] <= frame_ms:
            current_hi = events[event_idx][1]
            event_idx += 1

        if current_hi not in render_cache:
            img = render_fn(**render_kwargs, highlighted_strings=set(current_hi))
            if tab_img is not None:
                render_cache[current_hi] = _prepare_combined_frame(img, tab_img, portrait)
            else:
                render_cache[current_hi] = _prepare_frame(img, portrait)
        frames.append(render_cache[current_hi])

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        for frame_idx, frame in enumerate(frames):
            frame.save(tmpdir / f"frame_{frame_idx:06d}.png")

        # ── Write audio ───────────────────────────────────────
        wav_path = tmpdir / "audio.wav"
        export_wav(audio_data, wav_path, sr=sr)

        # ── Call ffmpeg ───────────────────────────────────────
        cmd = [
            ffmpeg, "-y",
            "-framerate", str(fps),
            "-i", str(tmpdir / "frame_%06d.png"),
            "-i", str(wav_path),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(f"ffmpeg error:\n{result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            print("ffmpeg timed out")
            return None
        except Exception as e:
            print(f"ffmpeg failed: {e}")
            return None

    return output_path


# ── Progression Video ──────────────────────────────────────

def export_progression_video(
    chords,
    title,
    audio_data,
    output_path,
    chord_duration_ms=2000,
    strum_delay_ms=20,
    dot_label="note",
    show_barre=True,
    barre_style="rect",
    show_string_names=True,
    show_finger_numbers=True,
    portrait=False,
    tab_img=None,
    fps=30,
    sr=SAMPLE_RATE,
):
    """
    Export a chord progression video.

    The progression strip is shown throughout. Each chord lights up in turn
    with a gold glow while its audio plays, then fades to static.
    Display options mirror the live preview settings.

    Args:
        chords:              list of chord dicts from get_progression_chords()
        title:               progression title string for the strip header
        audio_data:          numpy float32 audio (full progression)
        output_path:         output MP4 path
        chord_duration_ms:   how long each chord is held / highlighted (ms)
        strum_delay_ms:      delay between strum strings (ms)
        dot_label:           "note" | "finger" | "none"
        show_barre:          draw barre indicators
        barre_style:         "rect" | "arch"
        show_string_names:   draw string name circles below the grid
        show_finger_numbers: draw finger numbers below string names
        fps:                 video frame rate
        sr:                  audio sample rate

    Returns:
        Path to MP4, or None if failed
    """
    from diagrams.progression_diagram import render_progression_strip

    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        print("Error: ffmpeg not found on PATH.")
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _render(highlighted_idx):
        img = render_progression_strip(
            chords, title=title, highlighted_idx=highlighted_idx,
            dot_label=dot_label, show_barre=show_barre, barre_style=barre_style,
            show_string_names=show_string_names, show_finger_numbers=show_finger_numbers,
        )
        if tab_img is not None:
            return _prepare_combined_frame(img, tab_img, portrait)
        return _prepare_frame(img, portrait)

    # Pre-render one frame per chord highlight state + the un-highlighted tail
    rendered = [_render(i) for i in range(len(chords))]
    rendered_tail = _render(None)

    # Timeline: each chord highlighted for chord_duration_ms, then 1 s tail
    ms_per_frame   = 1000.0 / fps
    total_ms       = len(chords) * chord_duration_ms + 1000
    total_frames   = int(total_ms * fps / 1000) + 1
    chord_duration_frames = max(int(chord_duration_ms * fps / 1000), 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        frame_idx = 0

        for chord_idx, frame in enumerate(rendered):
            for _ in range(chord_duration_frames):
                frame.save(tmpdir / f"frame_{frame_idx:06d}.png")
                frame_idx += 1

        # Tail
        tail_frames = max(int(fps), 1)
        for _ in range(tail_frames):
            rendered_tail.save(tmpdir / f"frame_{frame_idx:06d}.png")
            frame_idx += 1

        # ── Write audio ────────────────────────────────────────
        wav_path = tmpdir / "audio.wav"
        export_wav(audio_data, wav_path, sr=sr)

        # ── Call ffmpeg ────────────────────────────────────────
        cmd = [
            ffmpeg, "-y",
            "-framerate", str(fps),
            "-i", str(tmpdir / "frame_%06d.png"),
            "-i", str(wav_path),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                print(f"ffmpeg error:\n{result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            print("ffmpeg timed out")
            return None
        except Exception as e:
            print(f"ffmpeg failed: {e}")
            return None

    return output_path


# ── Scale / Arpeggio Progression Video ────────────────────

def export_scale_arp_progression_video(
    items,
    title,
    audio_data,
    output_path,
    strip_render_fn,
    position_num=1,
    item_duration_ms=2000,
    portrait=False,
    tab_img=None,
    fps=30,
    sr=SAMPLE_RATE,
):
    """
    Export a scale or arpeggio progression video.

    Each degree panel in the strip lights up in turn with a gold glow while
    its audio plays, then the strip holds static at the end.

    Args:
        items:            list of dicts from get_progression_scales / get_progression_arpeggios
        title:            strip header title string
        audio_data:       numpy audio array (full concatenated progression audio)
        output_path:      output MP4 path
        strip_render_fn:  render_scale_progression_strip or render_arpeggio_progression_strip
        position_num:     which neck position box to display (1-5)
        item_duration_ms: how long each degree is highlighted (ms)
        fps:              video frame rate
        sr:               audio sample rate

    Returns:
        Path to MP4, or None on failure
    """
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        print("Error: ffmpeg not found on PATH.")
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    hold_frames = max(int(fps * item_duration_ms / 1000), fps // 2)
    tail_frames = fps  # 1-second static tail

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        frame_idx = 0

        for idx in range(len(items)):
            img = strip_render_fn(items, title=title,
                                  highlighted_idx=idx, position_num=position_num)
            if tab_img is not None:
                frame = _prepare_combined_frame(img, tab_img, portrait)
            else:
                frame = _prepare_frame(img, portrait)
            for _ in range(hold_frames):
                frame.save(tmpdir / f"frame_{frame_idx:06d}.png")
                frame_idx += 1

        # Tail: no highlight
        tail_img = strip_render_fn(items, title=title,
                                   highlighted_idx=None, position_num=position_num)
        if tab_img is not None:
            tail_frame = _prepare_combined_frame(tail_img, tab_img, portrait)
        else:
            tail_frame = _prepare_frame(tail_img, portrait)
        for _ in range(tail_frames):
            tail_frame.save(tmpdir / f"frame_{frame_idx:06d}.png")
            frame_idx += 1

        wav_path = tmpdir / "audio.wav"
        export_wav(audio_data, wav_path, sr=sr)

        cmd = [
            ffmpeg, "-y",
            "-framerate", str(fps),
            "-i", str(tmpdir / "frame_%06d.png"),
            "-i", str(wav_path),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                print(f"ffmpeg error:\n{result.stderr}")
                return None
        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"ffmpeg failed: {e}")
            return None

    return output_path


# ── Tab Video ──────────────────────────────────────────────

def export_tab_video(
    notes_data_or_frets,
    render_tab_fn,
    tab_render_kwargs,
    audio_data,
    output_path,
    note_duration_ms=300,
    fps=30,
    sr=SAMPLE_RATE,
    is_chord=False,
):
    """
    Export an animated tab video — the highlighted column advances with the audio.

    Args:
        notes_data_or_frets: notes_data list (scale/arp) or frets list (chord)
        render_tab_fn: render_scale_tab or render_chord_tab
        tab_render_kwargs: dict of kwargs (excluding highlighted_idx / highlighted_strings)
        audio_data: numpy audio array
        output_path: output MP4 path
        note_duration_ms: ms per note (scale/arp only)
        fps: video frame rate
        sr: audio sample rate
        is_chord: if True, render chord tab (single-column, strum animation)

    Returns:
        Path to exported MP4, or None if failed
    """
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        print("Error: ffmpeg not found on PATH.")
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        frame_idx = 0

        if is_chord:
            frets = notes_data_or_frets
            strum_dir = tab_render_kwargs.pop("strum_direction", "down")
            string_order = list(range(6)) if strum_dir == "down" else list(range(5, -1, -1))
            played = [i for i in string_order if frets[i] >= 0]
            frames_per_string = max(int(fps * 0.02), 1)  # 20ms per string
            hold_frames = fps * 2

            cumulative = set()
            for si in played:
                cumulative.add(si)
                img = render_tab_fn(**tab_render_kwargs, highlighted_strings=set(cumulative))
                frame = _prepare_frame(img)
                for _ in range(frames_per_string):
                    frame.save(tmpdir / f"frame_{frame_idx:06d}.png")
                    frame_idx += 1

            static_img = render_tab_fn(**tab_render_kwargs, highlighted_strings=set())
            static_frame = _prepare_frame(static_img)
            for _ in range(hold_frames):
                static_frame.save(tmpdir / f"frame_{frame_idx:06d}.png")
                frame_idx += 1

        else:
            notes_data = notes_data_or_frets
            ascending = tab_render_kwargs.pop("ascending", True)
            descending = tab_render_kwargs.pop("descending", False)
            root_to_root = tab_render_kwargs.pop("root_to_root", True)

            sequence = _build_note_sequence(
                notes_data, ascending=ascending, descending=descending, root_to_root=root_to_root
            )
            frames_per_note = max(int(fps * note_duration_ms / 1000), 1)

            for note_idx in range(len(sequence)):
                img = render_tab_fn(
                    **tab_render_kwargs,
                    highlighted_idx=note_idx,
                    ascending=ascending,
                    descending=descending,
                    root_to_root=root_to_root,
                )
                frame = _prepare_frame(img)
                for _ in range(frames_per_note):
                    frame.save(tmpdir / f"frame_{frame_idx:06d}.png")
                    frame_idx += 1

            # Tail
            tail_img = render_tab_fn(**tab_render_kwargs, highlighted_idx=None,
                                     ascending=ascending, descending=descending,
                                     root_to_root=root_to_root)
            tail_frame = _prepare_frame(tail_img)
            for _ in range(fps):
                tail_frame.save(tmpdir / f"frame_{frame_idx:06d}.png")
                frame_idx += 1

        # ── Write audio ───────────────────────────────────────
        wav_path = tmpdir / "audio.wav"
        export_wav(audio_data, wav_path, sr=sr)

        # ── Call ffmpeg ───────────────────────────────────────
        cmd = [
            ffmpeg, "-y",
            "-framerate", str(fps),
            "-i", str(tmpdir / "frame_%06d.png"),
            "-i", str(wav_path),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(f"ffmpeg error:\n{result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            print("ffmpeg timed out")
            return None
        except Exception as e:
            print(f"ffmpeg failed: {e}")
            return None

    return output_path
