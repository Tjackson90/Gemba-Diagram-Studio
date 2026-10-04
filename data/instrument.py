"""Instrument settings captured independently for each rendering/export job."""
from contextvars import ContextVar
from contextlib import contextmanager
from itertools import product

STANDARD = (40,45,50,55,59,64)
TUNINGS = {'Standard': STANDARD, 'Drop D': (38,45,50,55,59,64),
           'DADGAD': (38,45,50,55,57,62), 'Open G': (38,43,50,55,59,62)}
_settings = ContextVar('instrument', default={'tuning':'Standard','capo':0,'left_handed':False})


def settings():
    return dict(_settings.get())


def set_instrument(value):
    if value.get('tuning') not in TUNINGS or type(value.get('capo')) is not int or not 0 <= value['capo'] <= 12:
        raise ValueError('Choose a supported tuning and capo from 0 to 12')
    return _settings.set(dict(value))


@contextmanager
def instrument(value):
    token = set_instrument(value)
    try:
        yield
    finally:
        _settings.reset(token)


def get_tuning():
    value = _settings.get()
    return tuple(pitch+value['capo'] for pitch in TUNINGS[value['tuning']])


def string_names():
    names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    return [names[n%12] for n in get_tuning()]


def string_column(index):
    return 5-index if _settings.get().get('left_handed') else index


def for_snapshot(function):
    from functools import wraps
    @wraps(function)
    def run(snapshot, *args, **kwargs):
        from diagrams.style import theme
        with instrument(snapshot.get('instrument', {'tuning':'Standard','capo':0,'left_handed':False})), theme((snapshot.get('render_spec') or {}).get('theme','Volt')):
            return function(snapshot, *args, **kwargs)
    return run


def adapt_voicing(frets, fingers):
    """Retain each voice's pitch class while finding a compact tuned fingering."""
    tuning = get_tuning()
    if tuning == STANDARD:
        return list(frets), list(fingers)
    choices = []
    for i, fret in enumerate(frets):
        if fret < 0:
            choices.append([-1]); continue
        pitch = STANDARD[i]+fret
        choices.append([f for f in range(25-_settings.get()['capo']) if (tuning[i]+f-pitch)%12 == 0])
    candidates = []
    for candidate in product(*choices):
        held = [f for f in candidate if f>0]
        span = max(held,default=0)-min(held,default=0)
        if span > 5:
            continue
        deviation = sum(abs(tuning[i]+f-(STANDARD[i]+frets[i])) for i,f in enumerate(candidate) if f>=0)
        candidates.append(((span, deviation, max(held,default=0)),candidate))
    if not candidates:
        raise ValueError('This voicing has no compact fingering in the selected tuning/capo')
    candidate = min(candidates)[1]
    held = sorted(set(f for f in candidate if f>0))
    fingers = [min(4,held.index(f)+1) if f>0 else 0 for f in candidate]
    return list(candidate), fingers
