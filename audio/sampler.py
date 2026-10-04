"""Recorded-instrument voices with band-limited resampling and a stereo room bus."""
from functools import lru_cache
from fractions import Fraction
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, butter, sosfilt, fftconvolve

SAMPLE_DIR=Path(__file__).parent/'samples'
VOICES={
    'Studio Acoustic': ('guitar-acoustic',1.0),
    'Fingerstyle Nylon': ('guitar-nylon',.83),
    'Clean Electric': ('guitar-electric',.85),
    'Warm Jazz': ('guitar-electric',.48),
    'Grand Piano': ('piano',1.0),
    'Felt Piano': ('piano',.48),
    'Concert Harp': ('harp',.86),
    'Tonewheel Organ': ('organ',.72),
    'Ambient Guitar': ('guitar-electric',.56),
}
ALIASES={'Acoustic':'Studio Acoustic','Nylon':'Fingerstyle Nylon','Electric':'Clean Electric',
    'Clean':'Clean Electric','Jazz':'Warm Jazz','Piano':'Grand Piano','E. Piano':'Felt Piano',
    'Harp':'Concert Harp','Organ':'Tonewheel Organ','Bell':'Concert Harp','Pad':'Ambient Guitar',
    'acoustic':'Studio Acoustic','electric':'Clean Electric','sine':'Clean Electric'}


@lru_cache(maxsize=12)
def bank_notes(bank):
    notes=tuple(sorted(int(p.stem) for p in (SAMPLE_DIR/bank).glob('*.flac')))
    if not notes: raise RuntimeError(f'Recorded instrument files are missing: {bank}. Reinstall the complete application folder.')
    return notes


@lru_cache(maxsize=64)
def sample(bank,midi,sr):
    source=min(bank_notes(bank),key=lambda note:abs(note-midi))
    sound,rate=sf.read(SAMPLE_DIR/bank/f'{source}.flac',dtype='float32',always_2d=True)
    sound=sound.mean(axis=1)  # Stable mono image per string; pan/room are applied once to the mix.
    ratio=Fraction(sr/(rate*2**((midi-source)/12))).limit_denominator(1000)
    sound=resample_poly(sound,ratio.numerator,ratio.denominator).astype(np.float32)
    sound-=np.mean(sound)
    # Keep the recorded attack and decay; only balance gain across sample files.
    rms=np.sqrt(np.mean(sound[:min(len(sound),int(sr*.18))]**2))
    gain=min(3.5,.13/max(float(rms),.025))
    sound*=gain
    sound.setflags(write=False)
    return sound


def voice(midi,duration,tone,sr,settings,release=.16):
    tone=ALIASES.get(tone,tone)
    if tone not in VOICES: raise ValueError(f'Unknown instrument voice: {tone}')
    bank,warmth=VOICES[tone]
    source=sample(bank,midi,sr)
    total=max(2,round((duration+release)*sr))
    sound=np.zeros(total,dtype=np.float32)
    take=min(total,len(source)); sound[:take]=source[:take]
    bright=float(settings.get('brightness',.5))
    cutoff=min(sr*.43,(3500+bright*12500)*warmth)
    sound=sosfilt(butter(2,cutoff,fs=sr,output='sos'),sound).astype(np.float32)
    body=float(settings.get('body',.5))
    if abs(body-.5)>.01:
        low=sosfilt(butter(1,330,fs=sr,output='sos'),sound)
        sound+=low.astype(np.float32)*(body-.5)*.65
    attack=max(.0008,float(settings.get('attack',.3))*.012)
    if tone=='Ambient Guitar': attack=.1+float(settings.get('attack',.3))*.25
    ramp=min(len(sound),max(2,round(attack*sr)))
    sound[:ramp]*=np.sin(np.linspace(0,np.pi/2,ramp))**2
    # Damping adds an adjustable natural decay, never a looped synthetic sustain.
    decay=float(settings.get('decay',.5))
    sound*=np.exp(-np.arange(total)/sr*(1-decay)*.38)
    gate=min(total,round(duration*sr)); remaining=total-gate
    if remaining: sound[gate:]*=np.cos(np.linspace(0,np.pi/2,remaining))**2
    warmth_control=float(settings.get('warmth',.3))
    drive=1+warmth_control*.3+float(settings.get('harmonics',.5))*.12
    sound=np.tanh(sound*drive)/drive
    sound[-1]=0
    return sound


@lru_cache(maxsize=16)
def room_impulse(sr,amount):
    length=round(sr*(.17+.22*amount))
    rng=np.random.default_rng(712)
    ir=rng.normal(0,1,(length,2))
    ir=sosfilt(butter(2,4200,fs=sr,output='sos'),ir,axis=0)
    t=np.arange(length)/sr
    envelope=np.exp(-t/(.038+.045*amount))
    envelope[:round(sr*.012)]=0
    ir*=envelope[:,None]
    ir/=max(1,np.sqrt(np.sum(ir**2)))
    for channel in range(2):
        for delay,gain in [(0.017,.16),(.029,.09),(.043,.055)]:
            ir[round((delay+channel*.0017)*sr),channel]+=gain
    return ir


def render(events,tone,sr,settings,tail=.5):
    from services.jobs import check_cancelled
    if not events: return np.zeros((sr//2,2),dtype=np.float32)
    total=round((max(e.start+e.duration for e in events)+tail)*sr)
    if total>sr*3600: raise ValueError('Audio exceeds the one-hour export limit')
    mix=np.zeros((total,2),dtype=np.float32)
    ordered=sorted(events,key=lambda e:e.start)
    for index,event in enumerate(ordered):
        check_cancelled()
        # A new fretting on the same physical string damps the preceding note.
        later=next((n.start for n in ordered[index+1:] if n.string==event.string and n.start>event.start),None)
        duration=min(event.duration,later-event.start) if later is not None else event.duration
        release=min(.16,max(.035,duration*.25))
        note=voice(event.midi,duration,tone,sr,settings,release)
        velocity=.94+.045*np.sin(index*2.399+event.string*.7)
        pan=(event.string-2.5)*.035
        gains=np.array([np.cos((pan+1)*np.pi/4),np.sin((pan+1)*np.pi/4)],dtype=np.float32)
        offset=round(event.start*sr); end=min(total,offset+len(note))
        mix[offset:end]+=note[:end-offset,None]*gains*velocity*.72
    check_cancelled()
    reverb=float(np.clip(settings.get('reverb',.25),0,1))
    if reverb:
        ir=room_impulse(sr,round(reverb,2)); mono=mix.mean(axis=1)
        for ch in range(2): mix[:,ch]+=fftconvolve(mono,ir[:,ch])[:total]*(.12+reverb*.3)
    # Fixed monitor gain preserves dynamics across notes, unlike peak normalization.
    mix*=1.5
    # Never normalize quiet passages upwards. Preserve dynamics and keep headroom.
    peak=float(np.max(np.abs(mix)))
    if peak>.89: mix*=.89/peak
    fade=min(round(sr*.025),total//4)
    mix[-fade:]*=np.linspace(1,0,fade)[:,None]
    return mix


def write_credit(output):
    """Carry attribution alongside standalone audio/video files intended for sharing."""
    from services.storage import unique_path
    text=(SAMPLE_DIR/'ATTRIBUTION.md').read_text(encoding='utf-8')
    path=Path(output).parent/'Gemba-instrument-credits.txt'
    if path.exists():
        try:
            if path.read_text(encoding='utf-8')==text: return
        except UnicodeError: pass
    path=unique_path(path)
    path.write_text(text,encoding='utf-8')
