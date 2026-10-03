"""
Audio engine — tone synthesis, chord strum, scale/arpeggio playback, and export.

Optional high-quality backends (installed):
  scipy      → 4th-order Butterworth IIR low-pass
  pedalboard → Freeverb reverb, master chain
  soundfile  → float32 WAV encoder (no quantisation noise)

All three are used automatically when present and fall back to the
pure-numpy implementations if they are ever unavailable.
"""

import numpy as np
from pathlib import Path
import config
from data.notes import midi_to_freq, STANDARD_TUNING_MIDI

SAMPLE_RATE = config.AUDIO_SAMPLE_RATE

# ── User-adjustable tone parameters (set by the GUI sliders) ─────────────────
TONE_SETTINGS = {
    "attack":     0.3,   # 0.0 = instant snap    →  1.0 = slow swell
    "decay":      0.5,   # 0.0 = short/staccato  →  1.0 = long/sustained
    "brightness": 0.5,   # 0.0 = very dark/warm  →  1.0 = bright/airy
    "warmth":     0.3,   # 0.0 = clean/cold      →  1.0 = saturated/warm
    "harmonics":  0.5,   # 0.0 = pure sine       →  1.0 = rich overtones
    "body":       0.5,   # 0.0 = thin/direct     →  1.0 = full/resonant
    "reverb":     0.4,   # 0.0 = dry             →  1.0 = very wet
}

# ── Optional backend detection ────────────────────────────────────────────────
_SCIPY = False
_PEDALBOARD = False

try:
    from scipy.signal import butter as _sp_butter, sosfilt as _sp_sosfilt
    _SCIPY = True
except ImportError:
    pass

try:
    import pedalboard as _pb
    _PEDALBOARD = True
except ImportError:
    pass


# ── Parameter helpers ─────────────────────────────────────────────────────────

def _ts(key, default=0.5):
    """Read a TONE_SETTINGS value, clipped 0–1."""
    return float(np.clip(TONE_SETTINGS.get(key, default), 0.0, 1.0))


# ── Core DSP helpers ──────────────────────────────────────────────────────────

def _lpf(signal, cutoff_hz, sr, order=4):
    """4th-order Butterworth IIR LPF (scipy) or Hamming-sinc FIR fallback."""
    if _SCIPY:
        nyq  = sr / 2.0
        freq = min(cutoff_hz / nyq, 0.98)
        sos  = _sp_butter(order, freq, btype="low", output="sos")
        return _sp_sosfilt(sos, signal).astype(np.float64)
    # FIR fallback
    n_taps = max(5, int(4 * sr / max(cutoff_hz, 10)) | 1)
    n_taps = min(n_taps, 255)
    k  = np.arange(n_taps) - (n_taps - 1) / 2
    fc = cutoff_hz / sr
    h  = 2 * fc * np.sinc(2 * fc * k) * np.hamming(n_taps)
    h /= h.sum()
    return np.convolve(signal, h, mode="same")


def _apply_warmth(signal, amount):
    """Tanh soft-saturation. amount 0→1 maps to drive 1.0→3.5."""
    drive = 1.0 + amount * 2.5
    norm  = float(np.tanh(np.float64(drive)))
    return np.tanh(signal * drive) / norm if norm > 0 else signal


def _apply_reverb(signal, sr, wet_base=0.04, wet_range=0.36,
                  room_base=0.25, room_range=0.50, damping=0.55):
    """Reverb using pedalboard Freeverb or multi-tap numpy fallback."""
    rv   = _ts("reverb")
    wet  = wet_base  + rv * wet_range
    room = room_base + rv * room_range
    if _PEDALBOARD:
        board = _pb.Pedalboard([
            _pb.Reverb(
                room_size=float(np.clip(room, 0.05, 0.95)),
                damping=float(np.clip(damping, 0.05, 0.95)),
                wet_level=float(np.clip(wet, 0.0, 0.95)),
                dry_level=float(np.clip(1.0 - wet * 0.7, 0.05, 1.0)),
                width=0.80,
            ),
        ])
        return board(signal.astype(np.float32), sample_rate=sr).astype(np.float64)
    # numpy multi-tap fallback
    delays_ms = [13.1, 22.7, 33.4, 47.2, 64.8, 87.0, 113.5, 144.7]
    out = signal.copy().astype(np.float64)
    for i, d_ms in enumerate(delays_ms):
        d    = int(d_ms * (0.5 + room * 0.8) * sr / 1000)
        gain = (0.78 ** (i + 1)) * wet
        if d < len(signal):
            out[d:] += signal[:len(signal) - d] * gain
    peak = np.max(np.abs(out))
    if peak > 1.0:
        out /= peak
    return out


def _norm(wave, target=0.88):
    """Peak-normalize to target amplitude."""
    peak = np.max(np.abs(wave))
    if peak > 0:
        wave = wave / peak * target
    return wave


def _fade_edges(signal, sr, fade_in_ms=5, fade_out_ms=30):
    """
    Apply a short linear fade-in and cosine fade-out to eliminate clicks
    at buffer boundaries caused by abrupt amplitude discontinuities.
    """
    n = len(signal)
    fi = min(int(fade_in_ms  * sr / 1000), n // 4)
    fo = min(int(fade_out_ms * sr / 1000), n // 4)

    out = signal.copy()
    if fi > 0:
        out[:fi] *= np.linspace(0.0, 1.0, fi)
    if fo > 0:
        # Cosine taper — smoother than linear for the tail
        out[-fo:] *= 0.5 * (1.0 + np.cos(np.linspace(0, np.pi, fo)))
    return out


def _master_chain(signal, sr):
    """Normalize the final mix and apply gentle edge fades to kill boundary clicks."""
    normed = _norm(signal)
    return _fade_edges(normed, sr)


# ── Envelope helpers ──────────────────────────────────────────────────────────

def _piano_env(n, sr):
    """
    Piano-style envelope: short attack + exponential decay (no sustain plateau).
    Attack: 2ms–150ms controlled by TONE_SETTINGS["attack"].
    Decay rate: 3.2 (short) → 0.8 (long) controlled by TONE_SETTINGS["decay"].
    """
    atk_ms  = 2 + _ts("attack") * 148        # 2ms → 150ms
    dec_val = _ts("decay")
    decay_rate = 3.2 - dec_val * 2.4          # 3.2 → 0.8

    a = int(atk_ms / 1000 * sr)
    env = np.empty(n, dtype=np.float64)
    if a > 0 and a < n:
        env[:a] = np.linspace(0.0, 1.0, a)
    elif a >= n:
        env[:] = np.linspace(0.0, 1.0, n)
        return env
    env[a:] = np.exp(-np.arange(n - a) / sr * decay_rate)
    return env


def _sustain_env(n, sr, sustain_level=0.80):
    """
    ADSR envelope with held sustain plateau — for organ, pad, sustained voices.
    Attack: 5ms–800ms from TONE_SETTINGS["attack"].
    Release: 100ms–600ms from TONE_SETTINGS["decay"].
    """
    atk_s  = 0.005 + _ts("attack") * 0.795   # 5ms → 800ms
    rel_s  = 0.10  + _ts("decay")  * 0.50    # 100ms → 600ms
    a = int(atk_s * sr)
    d = int(0.05  * sr)
    r = int(rel_s * sr)
    s = max(n - a - d - r, 0)

    env = np.zeros(n)
    idx = 0
    end = min(idx + a, n); env[idx:end] = np.linspace(0, 1, max(end - idx, 1)); idx = end
    end = min(idx + d, n); env[idx:end] = np.linspace(1, sustain_level, max(end - idx, 1)); idx = end
    end = min(idx + s, n); env[idx:end] = sustain_level; idx = end
    end = min(idx + r, n)
    if end > idx:
        t = np.linspace(0, 5, end - idx)
        env[idx:end] = sustain_level * np.exp(-t)
    return env


# ── Karplus-Strong core ───────────────────────────────────────────────────────

def _block_karplus_strong(buf_list, n_samples, loss):
    """Block-vectorised KS string loop — 50–100× faster than per-sample loop."""
    period = len(buf_list)
    buf    = np.array(buf_list, dtype=np.float64)
    output = np.empty(n_samples, dtype=np.float64)
    written = 0
    while written < n_samples:
        take = min(period, n_samples - written)
        output[written:written + take] = buf[:take]
        written += take
        new      = np.empty(period, dtype=np.float64)
        new[:-1] = loss * 0.5 * (buf[:-1] + buf[1:])
        new[-1]  = loss * 0.5 * (buf[-1]  + buf[0])
        buf = new
    return output


def _ks_voice(freq, duration, sr, loss_base, loss_brightness_scale,
              loss_decay_scale, excitation="noise", pick_pos=0.14,
              smoothing=True):
    """
    Shared Karplus-Strong voice core used by Acoustic, Nylon, and Harp.

    excitation: "noise" (steel), "triangular" (nylon), "narrow" (harp)
    """
    n_samples = int(sr * duration)
    period    = max(2, int(round(sr / freq)))

    br  = _ts("brightness")
    dec = _ts("decay")

    rng = np.random.default_rng(int(freq * 31.7) % (2**32 - 1))

    if excitation == "triangular":
        # Softer triangular pluck — nylon-string feel
        t_buf = np.linspace(-1, 1, period)
        noise = 1.0 - np.abs(t_buf)
        noise += rng.uniform(-0.05, 0.05, period)
    elif excitation == "narrow":
        # Sharp narrow pulse — harp pluck
        noise = rng.uniform(-1.0, 1.0, period).astype(np.float64)
        noise *= np.hanning(period)
        noise[period // 4:] *= 0.2
    else:
        # Uniform noise — steel string acoustic
        noise = rng.uniform(-1.0, 1.0, period).astype(np.float64)
        if period >= 4:
            noise *= np.hanning(period)
            noise  = np.convolve(noise, np.array([0.25, 0.50, 0.25]), mode="same")

    # Pick-position comb filter
    pick_idx = max(1, int(round(period * pick_pos)))
    if pick_idx < period:
        noise -= 0.38 * np.roll(noise, pick_idx)

    # Loss factor
    loss = loss_base - np.log2(max(freq, 55.0) / 220.0) * 0.0012
    loss += (br - 0.5) * loss_brightness_scale + (dec - 0.5) * loss_decay_scale
    loss = float(np.clip(loss, 0.9850, 0.9998))

    # Zero-mean the excitation buffer before KS so DC never builds up
    noise -= np.mean(noise)

    output = _block_karplus_strong(noise.tolist(), n_samples, loss)

    # DC blocking via one-pole high-pass (y[n] = x[n] - x[n-1] + 0.995*y[n-1])
    if _SCIPY:
        from scipy.signal import lfilter as _lfilter
        output = _lfilter([1.0, -1.0], [1.0, -0.995], output)
    else:
        hp = np.empty_like(output)
        hp[0] = output[0]
        hp[1:] = output[1:] - output[:-1]
        output = hp

    # 5 ms linear fade-in so output[0] is always exactly 0.
    fi = min(int(0.005 * sr), len(output) // 4)
    if fi > 0:
        output[:fi] *= np.linspace(0.0, 1.0, fi)

    # 80 ms cosine fade-out so the buffer always reaches exactly 0 at the end.
    # The KS loss factor applies per feedback-loop period, not per sample.
    # For low-frequency strings (~80 Hz), a 2-second buffer has only ~165
    # loop iterations, so the note can still be at 80 %+ of its initial
    # amplitude when the buffer ends — causing a hard-truncation click.
    # A gentle fade at the tail eliminates this without affecting the tone.
    fo = min(int(0.080 * sr), len(output) // 4)
    if fo > 0:
        output[-fo:] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fo)))

    return output


# ── Tone generators ───────────────────────────────────────────────────────────

def generate_acoustic(freq, duration=1.5, sr=SAMPLE_RATE, volume=0.5):
    """
    Steel-string acoustic guitar: Karplus-Strong with body resonance and reverb.
    """
    n_samples = int(sr * duration)
    output    = _ks_voice(freq, duration, sr,
                          loss_base=0.9992,
                          loss_brightness_scale=0.004,
                          loss_decay_scale=0.006,
                          excitation="noise",
                          pick_pos=0.14)

    # Guitar body resonance modes
    body_gain = 0.5 + _ts("body") * 0.5
    body_modes = [
        (95,  0.28, 12),
        (195, 0.16, 20),
        (295, 0.09, 30),
        (390, 0.05, 42),
    ]
    for bf, bg, bd in body_modes:
        if bf >= freq * 2.5:
            continue
        body_len = min(int(sr * 0.22), n_samples)
        t = np.arange(body_len) / sr
        output[:body_len] += np.sin(2 * np.pi * bf * t) * np.exp(-t * bd) * bg * body_gain

    output = _norm(output)
    output = _apply_reverb(output, sr,
                           wet_base=0.04, wet_range=0.36,
                           room_base=0.20, room_range=0.44, damping=0.58)
    return output * volume


def generate_nylon(freq, duration=1.5, sr=SAMPLE_RATE, volume=0.5):
    """
    Nylon-string classical guitar: softer excitation, warmer decay, less attack.
    """
    n_samples = int(sr * duration)
    output    = _ks_voice(freq, duration, sr,
                          loss_base=0.9988,
                          loss_brightness_scale=0.003,
                          loss_decay_scale=0.008,
                          excitation="triangular",
                          pick_pos=0.12)

    # Warmer, softer body modes
    body_gain = 0.4 + _ts("body") * 0.4
    body_modes = [
        (80,  0.22, 10),
        (170, 0.12, 16),
        (250, 0.06, 24),
    ]
    for bf, bg, bd in body_modes:
        if bf >= freq * 2.5:
            continue
        body_len = min(int(sr * 0.20), n_samples)
        t = np.arange(body_len) / sr
        output[:body_len] += np.sin(2 * np.pi * bf * t) * np.exp(-t * bd) * bg * body_gain

    # Warm LPF — nylon strings are naturally dark
    br = _ts("brightness")
    cutoff = 2200 + br * 3000     # 2200–5200 Hz
    output = _lpf(output, cutoff, sr)

    output = _norm(output)
    output = _apply_reverb(output, sr,
                           wet_base=0.05, wet_range=0.30,
                           room_base=0.18, room_range=0.38, damping=0.68)
    return output * volume


def generate_harp(freq, duration=2.0, sr=SAMPLE_RATE, volume=0.45):
    """
    Concert harp: long bright decay, narrow pluck impulse, shimmery reverb.
    """
    output = _ks_voice(freq, duration, sr,
                       loss_base=0.9996,
                       loss_brightness_scale=0.002,
                       loss_decay_scale=0.003,
                       excitation="narrow",
                       pick_pos=0.08)

    # Bright high-frequency content
    br     = _ts("brightness")
    cutoff = 4500 + br * 5000
    output = _lpf(output, cutoff, sr)

    output = _norm(output)
    # Shimmery reverb: low damping lets highs ring
    output = _apply_reverb(output, sr,
                           wet_base=0.10, wet_range=0.40,
                           room_base=0.40, room_range=0.40, damping=0.25)
    return output * volume


def generate_clean(freq, duration=1.5, sr=SAMPLE_RATE, volume=0.5):
    """
    Clean sine keyboard: pure tone with minimal overtones and piano envelope.
    """
    n   = int(sr * duration)
    t   = np.arange(n) / sr
    br  = _ts("brightness")
    hrm = _ts("harmonics")

    wave  = np.sin(2 * np.pi * freq * t)
    if freq * 2 < sr / 2:
        wave += (0.08 + hrm * 0.10) * np.sin(2 * np.pi * freq * 2 * t)
    if freq * 3 < sr / 2:
        wave += (0.02 + hrm * 0.04) * np.sin(2 * np.pi * freq * 3 * t)

    wave *= _piano_env(n, sr)

    warm = _ts("warmth")
    if warm > 0.05:
        wave = _apply_warmth(wave, warm * 0.4)

    wave = _norm(wave)
    wave = _apply_reverb(wave, sr,
                         wet_base=0.03, wet_range=0.25,
                         room_base=0.20, room_range=0.35, damping=0.60)
    return wave * volume


def generate_electric(freq, duration=1.5, sr=SAMPLE_RATE, volume=0.45):
    """
    Warm electric keyboard: soft additive voice, piano envelope, ambient reverb.
    Brightness adds upper harmonics. Warmth adds gentle saturation.
    """
    n   = int(sr * duration)
    t   = np.arange(n) / sr
    br  = _ts("brightness")
    hrm = _ts("harmonics")

    # Harmonic stack — moderate density, warm character
    wave  = np.sin(2 * np.pi * freq * t)
    if freq * 2 < sr / 2:
        wave += (0.20 + hrm * 0.15) * np.sin(2 * np.pi * freq * 2 * t)
    if freq * 3 < sr / 2:
        wave += (0.08 + hrm * 0.10) * np.sin(2 * np.pi * freq * 3 * t)
    if freq * 4 < sr / 2:
        wave += (0.03 + br  * 0.06) * np.sin(2 * np.pi * freq * 4 * t)
    if freq * 5 < sr / 2 and br > 0.4:
        wave += (br - 0.4) * 0.04   * np.sin(2 * np.pi * freq * 5 * t)

    wave *= _piano_env(n, sr)

    # Optional gentle warmth/saturation
    warm = _ts("warmth")
    if warm > 0.05:
        wave = _apply_warmth(wave, warm * 0.5)

    # Gentle brightness roll-off
    cutoff = 3500 + br * 4000
    wave   = _lpf(wave, cutoff, sr)

    wave = _norm(wave)
    wave = _apply_reverb(wave, sr,
                         wet_base=0.06, wet_range=0.22,
                         room_base=0.30, room_range=0.40, damping=0.40)
    return wave * volume


def generate_jazz(freq, duration=1.5, sr=SAMPLE_RATE, volume=0.45):
    """
    Jazz guitar: hollow-body warmth, strong 2nd harmonic, dark roll-off, short decay.
    """
    n   = int(sr * duration)
    t   = np.arange(n) / sr
    br  = _ts("brightness")
    hrm = _ts("harmonics")

    # Jazz: emphasize 2nd harmonic (hollow/round), less 3rd
    wave  = np.sin(2 * np.pi * freq * t)
    if freq * 2 < sr / 2:
        wave += (0.35 + hrm * 0.15) * np.sin(2 * np.pi * freq * 2 * t)
    if freq * 3 < sr / 2:
        wave += (0.08 + hrm * 0.08) * np.sin(2 * np.pi * freq * 3 * t)
    if freq * 4 < sr / 2:
        wave += (0.02 + br  * 0.04) * np.sin(2 * np.pi * freq * 4 * t)

    wave *= _piano_env(n, sr)

    # Warm saturation — jazz tones are thick
    warm = _ts("warmth")
    wave = _apply_warmth(wave, 0.3 + warm * 0.5)

    # Dark LPF — jazz is warm and mellow
    cutoff = 1800 + br * 2200
    wave   = _lpf(wave, cutoff, sr)

    # Body resonance — hollow-body characteristic
    body_gain = 0.3 + _ts("body") * 0.5
    body_len  = min(int(sr * 0.15), n)
    tb = np.arange(body_len) / sr
    wave[:body_len] += np.sin(2 * np.pi * 180 * tb) * np.exp(-tb * 18) * 0.18 * body_gain

    wave = _norm(wave)
    wave = _apply_reverb(wave, sr,
                         wet_base=0.05, wet_range=0.20,
                         room_base=0.25, room_range=0.30, damping=0.70)
    return wave * volume


def generate_piano(freq, duration=2.0, sr=SAMPLE_RATE, volume=0.5):
    """
    Acoustic piano: inharmonic partial series (stretched harmonics), piano envelope.
    Uses B=0.0002 inharmonicity coefficient for realistic piano stretch tuning.
    """
    n = int(sr * duration)
    t = np.arange(n) / sr

    br  = _ts("brightness")
    hrm = _ts("harmonics")
    B   = 0.0002   # inharmonicity coefficient

    # Inharmonic partial: f_k = f0 * k * sqrt(1 + B*k^2)
    n_partials = int(4 + hrm * 6)   # 4–10 partials
    wave = np.zeros(n)
    amp_rolloff = 0.65 + br * 0.20  # brighter = slower rolloff

    for k in range(1, n_partials + 1):
        f_k = freq * k * np.sqrt(1 + B * k * k)
        if f_k >= sr / 2:
            break
        amp = amp_rolloff ** (k - 1)
        wave += amp * np.sin(2 * np.pi * f_k * t)

    wave *= _piano_env(n, sr)

    warm = _ts("warmth")
    if warm > 0.05:
        wave = _apply_warmth(wave, warm * 0.4)

    wave = _norm(wave)
    wave = _apply_reverb(wave, sr,
                         wet_base=0.04, wet_range=0.28,
                         room_base=0.30, room_range=0.45, damping=0.50)
    return wave * volume


def generate_epiano(freq, duration=1.5, sr=SAMPLE_RATE, volume=0.45):
    """
    Rhodes-style electric piano: dual-layer (tine + body), different decay rates.
    Tine: bright fast-decay layer. Body: warm slow-decay layer.
    """
    n   = int(sr * duration)
    t   = np.arange(n) / sr
    br  = _ts("brightness")
    hrm = _ts("harmonics")
    dec = _ts("decay")
    bdy = _ts("body")

    # ── Tine layer (fast decay, bright) ─────────────────
    tine  = np.sin(2 * np.pi * freq * t)
    if freq * 2 < sr / 2:
        tine += (0.25 + br * 0.20) * np.sin(2 * np.pi * freq * 2 * t)
    if freq * 3 < sr / 2:
        tine += (0.06 + hrm * 0.08) * np.sin(2 * np.pi * freq * 3 * t)

    tine_rate  = 4.0 - dec * 2.0    # 4.0 → 2.0
    tine_atk   = int(0.003 * sr)    # 3ms snap
    tine_env   = np.empty(n)
    if tine_atk > 0 and tine_atk < n:
        tine_env[:tine_atk] = np.linspace(0, 1, tine_atk)
    tine_env[tine_atk:] = np.exp(-np.arange(n - tine_atk) / sr * tine_rate)
    tine *= tine_env

    # ── Body layer (slow decay, warm) ────────────────────
    body  = np.sin(2 * np.pi * freq * t)
    if freq * 2 < sr / 2:
        body += (0.40 + hrm * 0.10) * np.sin(2 * np.pi * freq * 2 * t)

    body_rate  = 1.2 - dec * 0.8    # 1.2 → 0.4
    body_atk   = int(0.010 * sr)    # 10ms softer attack
    body_env   = np.empty(n)
    if body_atk > 0 and body_atk < n:
        body_env[:body_atk] = np.linspace(0, 1, body_atk)
    body_env[body_atk:] = np.exp(-np.arange(n - body_atk) / sr * body_rate)
    body *= body_env

    # ── Mix tine + body ───────────────────────────────────
    tine_mix = 0.60 + br * 0.20     # brighter = more tine
    body_mix = 0.40 + bdy * 0.30
    wave = tine * tine_mix + body * body_mix

    warm = _ts("warmth")
    if warm > 0.05:
        wave = _apply_warmth(wave, warm * 0.45)

    wave = _norm(wave)
    wave = _apply_reverb(wave, sr,
                         wet_base=0.07, wet_range=0.28,
                         room_base=0.35, room_range=0.35, damping=0.45)
    return wave * volume


def generate_organ(freq, duration=1.5, sr=SAMPLE_RATE, volume=0.45):
    """
    Hammond drawbar organ: additive harmonics with flat sustain (no decay).
    Drawbar levels: 8', 4', 2-2/3', 2', 1-3/5', 1-1/3', 1' (partial 1–8).
    """
    n   = int(sr * duration)
    t   = np.arange(n) / sr
    hrm = _ts("harmonics")
    br  = _ts("brightness")

    # Hammond drawbar register levels (harmonic number : default level)
    # harmonics slider opens up the upper drawbars
    drawbars = [
        (1,  1.00),             # 8'    fundamental
        (2,  0.85),             # 4'    octave
        (3,  0.40 + hrm*0.30), # 2-2/3 quint
        (4,  0.50 + hrm*0.20), # 2'    super octave
        (5,  0.15 + hrm*0.20), # 1-3/5 tierce
        (6,  0.15 + hrm*0.15), # 1-1/3 larigot
        (8,  0.10 + hrm*0.10), # 1'    sifflute
    ]

    wave = np.zeros(n)
    for k, level in drawbars:
        if freq * k >= sr / 2:
            break
        wave += level * np.sin(2 * np.pi * freq * k * t)

    wave *= _sustain_env(n, sr, sustain_level=0.85)

    warm = _ts("warmth")
    if warm > 0.05:
        wave = _apply_warmth(wave, warm * 0.60)  # organs are often driven hard

    wave = _norm(wave)
    wave = _apply_reverb(wave, sr,
                         wet_base=0.04, wet_range=0.22,
                         room_base=0.25, room_range=0.30, damping=0.55)
    return wave * volume


def generate_bell(freq, duration=3.0, sr=SAMPLE_RATE, volume=0.40):
    """
    Bell/chime: inharmonic partial series with long natural decay.
    Partial ratios from physical bell acoustics.
    """
    n   = int(sr * duration)
    t   = np.arange(n) / sr
    br  = _ts("brightness")
    hrm = _ts("harmonics")
    dec = _ts("decay")

    # Bell inharmonic partial ratios and amplitudes
    # Based on typical church bell / tubular chime acoustic analysis
    bell_partials = [
        (1.000, 1.00, 0.8),    # Hum / fundamental
        (2.756, 0.60, 1.8),    # Tierce
        (3.413, 0.30, 2.5),    # Quint
        (4.074, 0.20, 3.5),    # Nominal / octave
        (5.404, 0.12, 5.0),    # Deciem
        (6.795, 0.08, 7.0),    # Upper octave tierce
    ]

    n_partials = int(3 + hrm * 3)   # 3–6 partials
    wave = np.zeros(n)
    for ratio, amp, decay_rate in bell_partials[:n_partials]:
        f_partial = freq * ratio
        if f_partial >= sr / 2:
            continue
        # Each partial decays at its own rate, slowed by dec slider
        effective_rate = decay_rate * (1.5 - dec * 0.8)
        partial_env    = np.exp(-t * effective_rate)
        wave += amp * np.sin(2 * np.pi * f_partial * t) * partial_env

    # Brief attack transient (mallet strike)
    atk = int(0.004 * sr)
    if atk > 0 and atk < n:
        wave[:atk] *= np.linspace(0, 1, atk)

    wave = _norm(wave)
    wave = _apply_reverb(wave, sr,
                         wet_base=0.12, wet_range=0.38,
                         room_base=0.50, room_range=0.35, damping=0.20)
    return wave * volume


def generate_pad(freq, duration=2.0, sr=SAMPLE_RATE, volume=0.40):
    """
    Ambient string/synth pad: slightly detuned layers, slow attack, full sustain.
    Static detune (no LFO) — warm without wobble.
    """
    n   = int(sr * duration)
    t   = np.arange(n) / sr
    br  = _ts("brightness")
    hrm = _ts("harmonics")

    # Three slightly detuned layers for width and warmth
    detune_cents = [0.0, +4.0, -4.0]   # static, no oscillation
    layer_amps   = [1.00, 0.65, 0.65]

    wave = np.zeros(n)
    for dc, la in zip(detune_cents, layer_amps):
        freq_d = freq * (2 ** (dc / 1200))
        layer  = np.sin(2 * np.pi * freq_d * t)
        if freq_d * 2 < sr / 2:
            layer += (0.30 + hrm * 0.20) * np.sin(2 * np.pi * freq_d * 2 * t)
        if freq_d * 3 < sr / 2:
            layer += (0.10 + hrm * 0.10) * np.sin(2 * np.pi * freq_d * 3 * t)
        wave += la * layer

    wave *= _sustain_env(n, sr, sustain_level=0.90)

    # LPF for lushness
    cutoff = 2000 + br * 3500
    wave   = _lpf(wave, cutoff, sr)

    warm = _ts("warmth")
    if warm > 0.05:
        wave = _apply_warmth(wave, warm * 0.35)

    wave = _norm(wave)
    wave = _apply_reverb(wave, sr,
                         wet_base=0.15, wet_range=0.50,
                         room_base=0.55, room_range=0.35, damping=0.30)
    return wave * volume


# ── Tone generator registry ───────────────────────────────────────────────────

TONE_GENERATORS = {
    # Primary names (shown in GUI)
    "Acoustic":  generate_acoustic,
    "Nylon":     generate_nylon,
    "Harp":      generate_harp,
    "Clean":     generate_clean,
    "Electric":  generate_electric,
    "Jazz":      generate_jazz,
    "Piano":     generate_piano,
    "E. Piano":  generate_epiano,
    "Organ":     generate_organ,
    "Bell":      generate_bell,
    "Pad":       generate_pad,
    # Backward-compatibility aliases
    "acoustic":  generate_acoustic,
    "electric":  generate_electric,
    "sine":      generate_clean,
}

TONE_NAMES = [
    "Acoustic", "Nylon", "Harp",
    "Clean", "Electric", "Jazz",
    "Piano", "E. Piano", "Organ",
    "Bell", "Pad",
]


# ── Chord & Scale Audio ───────────────────────────────────────────────────────

def generate_chord_audio(
    frets,
    tone="Acoustic",
    duration=2.0,
    play_style="strum",
    strum_direction="down",
    strum_delay_ms=20,
    arpeggio_delay_ms=200,
):
    """
    Generate audio for a chord.

    Args:
        frets: list of 6 fret numbers (-1=muted, 0=open, 1+=fret)
        tone: tone name string
        duration: sustain duration per note in seconds
        play_style: "strum" | "arpeggio" | "arpeggio_strum"
        strum_direction: "down" (low E first) or "up" (high e first)
        strum_delay_ms: ms between strings in a strum
        arpeggio_delay_ms: ms between strings in arpeggio mode
    """
    gen = TONE_GENERATORS.get(tone, generate_acoustic)
    sr  = SAMPLE_RATE

    string_order = list(range(6))
    if strum_direction == "up":
        string_order = list(reversed(string_order))

    played = [(i, frets[i]) for i in string_order if frets[i] >= 0]

    if play_style == "arpeggio":
        delay_samp  = int(arpeggio_delay_ms * sr / 1000)
        total       = len(played) * delay_samp + int(sr * duration)
        mix         = np.zeros(total)
        for idx, (i, f) in enumerate(played):
            note   = gen(midi_to_freq(STANDARD_TUNING_MIDI[i] + f), duration=duration, sr=sr)
            offset = idx * delay_samp
            end    = min(offset + len(note), total)
            mix[offset:end] += note[:end - offset]

    elif play_style == "arpeggio_strum":
        delay_samp  = int(arpeggio_delay_ms * sr / 1000)
        strum_samp  = int(strum_delay_ms    * sr / 1000)
        gap_samp    = int(0.50 * sr)
        last_start  = (len(played) - 1) * delay_samp
        arp_end     = last_start + int(sr * duration) + gap_samp
        total       = arp_end + int(sr * duration) + strum_samp * 5
        mix         = np.zeros(total)

        for idx, (i, f) in enumerate(played):
            note   = gen(midi_to_freq(STANDARD_TUNING_MIDI[i] + f), duration=duration, sr=sr)
            offset = idx * delay_samp
            end    = min(offset + len(note), total)
            mix[offset:end] += note[:end - offset]

        for si, (i, f) in enumerate(played):
            nd   = max(duration - strum_delay_ms * si / 1000, 0.1)
            note = gen(midi_to_freq(STANDARD_TUNING_MIDI[i] + f), duration=nd, sr=sr)
            offset = arp_end + si * strum_samp
            end    = min(offset + len(note), total)
            mix[offset:end] += note[:end - offset]

    else:  # strum
        strum_samp = int(strum_delay_ms * sr / 1000)
        total      = int(sr * duration) + strum_samp * 5
        mix        = np.zeros(total)
        for si, (i, f) in enumerate(played):
            nd   = duration - strum_delay_ms * si / 1000
            note = gen(midi_to_freq(STANDARD_TUNING_MIDI[i] + f), duration=nd, sr=sr)
            offset = si * strum_samp
            end    = min(offset + len(note), total)
            mix[offset:end] += note[:end - offset]

    return _master_chain(mix, sr)


def generate_scale_audio(
    notes_data,
    tone="Acoustic",
    note_duration_ms=300,
    ascending=True,
    descending=False,
    root_to_root=True,
    stop_at_high_e_root=False,
):
    """Generate audio for scale or arpeggio playback."""
    gen = TONE_GENERATORS.get(tone, generate_acoustic)
    sr  = SAMPLE_RATE
    note_samp = int(note_duration_ms * sr / 1000)

    all_midi = sorted(set(
        STANDARD_TUNING_MIDI[n["string"]] + n["fret"]
        for n in notes_data
    ))
    if not all_midi:
        return np.zeros(sr)

    if root_to_root:
        root_midis = sorted(set(
            STANDARD_TUNING_MIDI[n["string"]] + n["fret"]
            for n in notes_data if n.get("is_root", False)
        ))
        start_midi = root_midis[0] if root_midis else all_midi[0]
        end_midi   = root_midis[-1] if root_midis else all_midi[-1]

        if stop_at_high_e_root:
            he_roots = sorted(
                STANDARD_TUNING_MIDI[n["string"]] + n["fret"]
                for n in notes_data
                if n.get("is_root", False) and n["string"] == 5
            )
            if he_roots:
                end_midi = he_roots[0]

        asc = [m for m in all_midi if start_midi <= m <= end_midi] or all_midi
        seq = []
        if ascending:
            seq.extend(asc)
        if descending:
            desc = list(reversed(asc[:-1] if ascending else asc))
            seq.extend(desc)
            if seq[-1] != start_midi:
                seq.append(start_midi)
    else:
        seq = []
        if ascending:
            seq.extend(all_midi)
        if descending:
            seq.extend(reversed(all_midi[:-1] if ascending else all_midi))

    if not seq:
        return np.zeros(sr)

    total = len(seq) * note_samp + int(sr * 0.5)
    mix   = np.zeros(total)
    for i, midi in enumerate(seq):
        dur  = note_duration_ms / 1000 * 1.5
        note = gen(midi_to_freq(midi), duration=dur, sr=sr)
        off  = i * note_samp
        end  = min(off + len(note), total)
        mix[off:end] += note[:end - off]

    return _master_chain(mix, sr)


# ── Progression Audio ─────────────────────────────────────────────────────────

def generate_progression_audio(
    chords,
    tone="Acoustic",
    chord_duration_s=2.0,
    strum_delay_ms=20,
    strum_direction="down",
    strum_directions=None,
    play_styles=None,
):
    """Generate audio for a chord progression — each chord played in sequence."""
    if not chords:
        return np.zeros(SAMPLE_RATE)

    sr           = SAMPLE_RATE
    chord_samp   = int(chord_duration_s * sr)
    segments     = []

    for idx, chord in enumerate(chords):
        direction = (strum_directions[idx]
                     if strum_directions and idx < len(strum_directions)
                     else strum_direction)
        style = (play_styles[idx]
                 if play_styles and idx < len(play_styles)
                 else "strum")
        seg = generate_chord_audio(
            frets=chord["frets"],
            tone=tone,
            duration=chord_duration_s,
            play_style=style,
            strum_delay_ms=strum_delay_ms,
            strum_direction=direction,
        )
        if len(seg) < chord_samp:
            seg = np.concatenate([seg, np.zeros(chord_samp - len(seg))])
        else:
            # Fade out over last 30 ms before the hard cut to prevent click
            seg = seg[:chord_samp]
            fade_samp = min(int(0.030 * sr), chord_samp // 4)
            if fade_samp > 0:
                seg[-fade_samp:] *= 0.5 * (1.0 + np.cos(np.linspace(0, np.pi, fade_samp)))
        segments.append(seg)

    tail = np.zeros(int(sr * 1.0))
    full = np.concatenate(segments + [tail])

    peak = np.max(np.abs(full))
    if peak > 0:
        full = full / peak * 0.90
    return full


# ── Playback ──────────────────────────────────────────────────────────────────

def play_audio(audio_data, sr=SAMPLE_RATE, volume=1.0):
    """Play audio through speakers via sounddevice."""
    try:
        import sounddevice as sd
        scaled = np.clip(audio_data * volume, -1.0, 1.0).astype(np.float32)
        sd.play(scaled, sr)
        sd.wait()
    except ImportError:
        print("Warning: sounddevice not installed. Cannot play audio.")
    except Exception as e:
        print(f"Audio playback error: {e}")


def stop_audio():
    """Stop any currently playing audio."""
    try:
        import sounddevice as sd
        sd.stop()
    except ImportError:
        pass
    except Exception as e:
        print(f"Audio stop error: {e}")


# ── Export ────────────────────────────────────────────────────────────────────

def _wav_fallback(audio_data, output_path, sr=SAMPLE_RATE):
    """Write WAV using Python's built-in wave module (no extra deps)."""
    import wave
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(output_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return output_path


def export_wav(audio_data, output_path, sr=SAMPLE_RATE):
    """
    Export audio as WAV.
    soundfile: float32 PCM (no quantisation noise, full dynamic range).
    fallback:  built-in wave module (16-bit int PCM).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import soundfile as sf
        sf.write(str(output_path), audio_data.astype(np.float32), sr)
        return output_path
    except ImportError:
        return _wav_fallback(audio_data, output_path, sr)


def export_mp3(audio_data, output_path, sr=SAMPLE_RATE):
    """Export audio as MP3. Requires pydub + ffmpeg."""
    try:
        from pydub import AudioSegment
        import io, wave

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        buf = io.BytesIO()
        pcm = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(buf, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())
        buf.seek(0)
        AudioSegment.from_wav(buf).export(str(output_path), format="mp3", bitrate="192k")
        return output_path
    except ImportError:
        print("Warning: pydub not installed. Cannot export MP3.")
        return None
    except Exception as e:
        print(f"MP3 export error: {e}")
        return None
