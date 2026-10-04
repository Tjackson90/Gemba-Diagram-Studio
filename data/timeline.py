"""Shared musical events for sound, tablature, MIDI and video."""
from dataclasses import dataclass
from data.notes import STANDARD_TUNING_MIDI


@dataclass(frozen=True)
class NoteEvent:
    midi: int
    string: int
    fret: int
    start: float
    duration: float


def note_sequence(notes, ascending=True, descending=False, root_to_root=True,
                  stop_at_high_e_root=False):
    lookup = {}
    for note in sorted(notes, key=lambda n: (n['string'], n['fret'])):
        midi = note.get('midi', get_tuning()[note['string']] + note['fret'])
        lookup.setdefault(midi, note)
    pitches = sorted(lookup)
    if not pitches:
        return []
    if root_to_root:
        roots = sorted({n.get('midi', get_tuning()[n['string']] + n['fret'])
                        for n in notes if n.get('is_root')})
        low, high = (roots[0], roots[-1]) if roots else (pitches[0], pitches[-1])
        if stop_at_high_e_root:
            top = sorted(n.get('midi', get_tuning()[n['string']] + n['fret'])
                         for n in notes if n.get('is_root') and n['string'] == 5)
            if top:
                high = top[0]
        pitches = [p for p in pitches if low <= p <= high]
    sequence = list(pitches) if ascending else []
    if descending:
        sequence.extend(reversed(pitches[:-1] if ascending else pitches))
    return [(m, lookup[m]['string'], lookup[m]['fret']) for m in sequence]


def scale_events(notes, note_duration_ms=300, **options):
    if not 10 <= note_duration_ms <= 10000:
        raise ValueError('Note duration must be between 10 and 10000 ms')
    duration = note_duration_ms / 1000
    return tuple(NoteEvent(m, s, f, i * duration, duration * 1.5)
                 for i, (m, s, f) in enumerate(note_sequence(notes, **options)))


def chord_events(frets, duration=2.0, play_style='strum', strum_direction='down',
                 strum_delay_ms=20, arpeggio_delay_ms=200, tuning=None):
    tuning = tuning or get_tuning()
    if len(frets) != len(tuning) or duration <= 0:
        raise ValueError('Invalid chord or duration')
    if min(strum_delay_ms, arpeggio_delay_ms) < 0:
        raise ValueError('Note delays cannot be negative')
    order = range(len(frets)) if strum_direction == 'down' else reversed(range(len(frets)))
    played = [(s, frets[s]) for s in order if frets[s] >= 0]
    delay = arpeggio_delay_ms if play_style.startswith('arpeggio') else strum_delay_ms
    events = [NoteEvent(tuning[s] + f, s, f, i * delay / 1000,
                        duration if play_style.startswith('arpeggio') else max(.01, duration-i*delay/1000))
              for i, (s, f) in enumerate(played)]
    if play_style == 'arpeggio_strum' and events:
        start = events[-1].start + duration + .5
        events.extend(NoteEvent(tuning[s]+f, s, f, start+i*strum_delay_ms/1000,
                                max(.01, duration-i*strum_delay_ms/1000))
                      for i, (s, f) in enumerate(played))
    return tuple(events)

from data.instrument import get_tuning, string_names, string_column
