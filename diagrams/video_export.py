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

    canvas = _Image.new("RGB", (target_w, target_h), img.info.get('background','#12161c'))
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

    canvas = _Image.new("RGB", (tw, th), diagram_img.info.get('background','#12161c'))

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
        fill='#445260',
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


from data.timeline import note_sequence as _build_note_sequence, scale_events, chord_events
from services.jobs import check_cancelled


def _encode_states(states, render, audio_data, output_path, fps=30, sr=SAMPLE_RATE):
    """Encode unique images with absolute, frame-rounded transition timestamps.

    Each state is (start_seconds, hashable_render_key). Audio defines duration.
    Only one PNG per unique state is written, irrespective of hold duration.
    """
    import math
    import time
    import os
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError('FFmpeg not found. Install FFmpeg and add its bin directory to PATH.')
    if fps <= 0 or sr <= 0 or len(audio_data) == 0:
        raise ValueError('Invalid frame rate, sample rate or empty audio')
    duration = len(audio_data) / sr
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gemba-video-') as directory:
        directory = Path(directory)
        frames = {}
        transitions = {}
        for start, key in sorted(states, key=lambda item: item[0]):
            # Quantize each absolute boundary; rounding never accumulates.
            transitions[min(round(start * fps), math.ceil(duration * fps))] = key
        if not transitions or min(transitions) != 0:
            transitions[0] = None
        boundaries = sorted(transitions)
        end_frame = math.ceil(duration * fps)
        manifest = ['ffconcat version 1.0']
        last = None
        for index, boundary in enumerate(boundaries):
            check_cancelled()
            end = boundaries[index+1] if index+1 < len(boundaries) else end_frame
            if end <= boundary:
                continue
            key = transitions[boundary]
            if key not in frames:
                name = f'state_{len(frames):04d}.png'
                render(key).convert('RGB').save(directory / name)
                frames[key] = name
            last = frames[key]
            manifest += [f"file '{last}'", f'option framerate {fps}', f'duration {(end-boundary)/fps:.9f}']
        if last is None:
            raise ValueError('Empty video timeline')
        manifest += [f"file '{last}'", f'option framerate {fps}']
        (directory / 'frames.txt').write_text('\n'.join(manifest)+'\n', encoding='utf-8')
        export_wav(audio_data, directory / 'audio.wav', sr=sr)
        # Encode beside the destination, then replace only on success.
        fd, temporary = tempfile.mkstemp(suffix='.mp4', prefix='.gemba-', dir=output_path.parent)
        os.close(fd)
        try:
            cmd = [ffmpeg, '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                   '-i', str(directory/'frames.txt'), '-i', str(directory/'audio.wav'),
                   '-r', str(fps), '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
                   '-c:a', 'aac', '-b:a', '192k', '-pix_fmt', 'yuv420p',
                   '-t', str(duration), '-movflags', '+faststart', temporary]
            with (directory/'ffmpeg.log').open('w+b') as errors:
                process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=errors,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                started = time.monotonic()
                try:
                    while process.poll() is None:
                        check_cancelled()
                        if time.monotonic() - started > 1800:
                            raise TimeoutError('FFmpeg exceeded 30 minutes')
                        time.sleep(.1)
                except BaseException:
                    process.kill()
                    process.wait()
                    raise
                if process.returncode:
                    errors.seek(0)
                    raise RuntimeError('FFmpeg: '+errors.read().decode('utf-8', errors='replace')[-4000:])
            check_cancelled()
            os.replace(temporary, output_path)
            from audio.sampler import write_credit
            write_credit(output_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return output_path


def _frame(image, portrait=False, tab_img=None):
    return (_prepare_combined_frame(image, tab_img, portrait) if tab_img is not None
            else _prepare_frame(image, portrait))


def export_scale_video(notes_data, render_fn, render_kwargs, audio_data, output_path,
                       note_duration_ms=300, portrait=False, tab_img=None, fps=30, sr=SAMPLE_RATE):
    kwargs = dict(render_kwargs)
    options = {name: kwargs.pop(name, default) for name, default in
               [('ascending', True), ('descending', False), ('root_to_root', True),
                ('stop_at_high_e_root', False)]}
    events = scale_events(notes_data, note_duration_ms, **options)
    states = [(e.start, (e.string, e.fret)) for e in events]
    if events:
        states.append((events[-1].start + note_duration_ms/1000, None))
    def render(key):
        image = render_fn(**kwargs, highlighted_notes={key} if key is not None else set())
        return _frame(image, portrait, tab_img)
    return _encode_states(states, render, audio_data, output_path, fps, sr)


def export_chord_video(frets, render_fn, render_kwargs, audio_data, output_path,
                       play_style='strum', strum_delay_ms=20, arpeggio_delay_ms=200,
                       chord_sustain_s=2.0, portrait=False, tab_img=None, fps=30, sr=SAMPLE_RATE):
    kwargs = dict(render_kwargs)
    direction = kwargs.pop('strum_direction', 'down')
    events = chord_events(frets, chord_sustain_s, play_style, direction,
                          strum_delay_ms, arpeggio_delay_ms)
    changes = sorted({0., *(e.start for e in events), *(e.start+e.duration for e in events)})
    states = [(t, frozenset(e.string for e in events if e.start <= t < e.start+e.duration))
              for t in changes]
    def render(key):
        return _frame(render_fn(**kwargs, highlighted_strings=set(key or ())), portrait, tab_img)
    return _encode_states(states, render, audio_data, output_path, fps, sr)


def export_progression_video(chords, title, audio_data, output_path, chord_duration_ms=2000,
                             strum_delay_ms=20, dot_label='note', show_barre=True,
                             barre_style='rect', show_string_names=True, show_finger_numbers=True,
                             portrait=False, tab_img=None, fps=30, sr=SAMPLE_RATE,
                             item_durations=None):
    from diagrams.progression_diagram import render_progression_strip
    def render(index):
        return _frame(render_progression_strip(chords, title=title, highlighted_idx=index,
            dot_label=dot_label, show_barre=show_barre, barre_style=barre_style,
            show_string_names=show_string_names, show_finger_numbers=show_finger_numbers), portrait, tab_img)
    return _encode_states(_panel_states(len(chords), item_durations or [chord_duration_ms/1000]*len(chords)),
                          render, audio_data, output_path, fps, sr)


def _panel_states(count, durations):
    if len(durations) != count or any(d <= 0 for d in durations):
        raise ValueError('Each panel needs a positive audio duration')
    states = []
    elapsed = 0.
    for index, duration in enumerate(durations):
        states.append((elapsed, index))
        elapsed += duration
    states.append((elapsed, None))
    return states


def export_scale_arp_progression_video(items, title, audio_data, output_path, strip_render_fn,
                                      position_num=1, item_duration_ms=2000, portrait=False,
                                      tab_img=None, fps=30, sr=SAMPLE_RATE, item_durations=None):
    def render(index):
        return _frame(strip_render_fn(items, title=title, highlighted_idx=index,
                                      position_num=position_num), portrait, tab_img)
    durations = item_durations or [item_duration_ms/1000]*len(items)
    return _encode_states(_panel_states(len(items), durations), render, audio_data, output_path, fps, sr)


def export_tab_video(notes_data_or_frets, render_tab_fn, tab_render_kwargs, audio_data,
                     output_path, note_duration_ms=300, fps=30, sr=SAMPLE_RATE, is_chord=False):
    kwargs = dict(tab_render_kwargs)
    if is_chord:
        return export_chord_video(notes_data_or_frets, render_tab_fn, kwargs, audio_data,
                                  output_path, fps=fps, sr=sr)
    options = {name: kwargs.get(name, default) for name, default in
               [('ascending', True), ('descending', False), ('root_to_root', True),
                ('stop_at_high_e_root', False)]}
    events = scale_events(notes_data_or_frets, note_duration_ms, **options)
    states = [(event.start, i) for i, event in enumerate(events)]
    if events:
        states.append((events[-1].start+note_duration_ms/1000, None))
    return _encode_states(states, lambda key: _frame(render_tab_fn(**kwargs, highlighted_idx=key)),
                          audio_data, output_path, fps, sr)
