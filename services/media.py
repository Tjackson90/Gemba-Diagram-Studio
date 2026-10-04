"""Create audio and exports using only captured data, never GUI widgets."""
from copy import deepcopy
import numpy as np
import config
from data.timeline import chord_events, scale_events
from audio.engine import render_events, tone_settings, SAMPLE_RATE
from services.jobs import check_cancelled
from services.documents import render_spec
from data.instrument import for_snapshot


def note_options(snap):
    if 'note_options' in snap:
        return dict(snap['note_options'])
    return dict(ascending=True, descending=True, root_to_root=True,
                stop_at_high_e_root=snap.get('is_arpeggio', False))


@for_snapshot
def musical_segments(snap):
    """Return (events, minimum_hold_seconds) for each displayed panel."""
    style, direction = snap['play_style_raw']
    options = dict(play_style=style, strum_direction=direction, arpeggio_delay_ms=snap['note_ms'])
    if snap.get('frets'):
        return [(chord_events(snap['frets'], **options), 0)]
    if snap.get('scale_notes'):
        return [(scale_events(snap['scale_notes'], snap['note_ms'], **note_options(snap)), 0)]
    if snap.get('progression'):
        result = []
        for i, chord in enumerate(snap['progression']):
            dirs = snap.get('prog_strum_dirs', [])
            options['strum_direction'] = dirs[i].lower() if i < len(dirs) else direction
            result.append((chord_events(chord['frets'], duration=snap['prog_duration'], **options), snap['prog_duration']))
        return result
    arp = bool(snap.get('arp_prog_items'))
    prefix = 'arp_prog' if arp else 'scale_prog'
    items = snap.get(prefix+'_items') or []
    from data.scales import get_caged_positions
    from data.arpeggios import get_arpeggio_positions
    getter = get_arpeggio_positions if arp else get_caged_positions
    result = []
    for i, item in enumerate(items):
        positions = getter(item['chord_root'], item['arp_name' if arp else 'scale_name'])
        notes = positions[min(snap[prefix+'_pos']-1, len(positions)-1)]['notes']
        directions = snap.get(prefix+'_dirs', [])
        direction = directions[i] if i < len(directions) else 'Asc'
        events = scale_events(notes, snap['note_ms'], ascending=direction != 'Desc',
                              descending=direction != 'Asc', stop_at_high_e_root=arp)
        result.append((events, snap.get(prefix+'_duration', 0)/1000))
    return result


@for_snapshot
def build_audio(snap):
    chunks, durations = [], []
    with tone_settings(snap.get('tone_settings', {})):
        for events, minimum in musical_segments(snap):
            check_cancelled()
            chunk = render_events(events, snap['tone'])
            if len(chunk) < round(minimum*SAMPLE_RATE):
                chunk = np.pad(chunk, ((0, round(minimum*SAMPLE_RATE)-len(chunk)), (0,0)))
            chunks.append(chunk)
            durations.append(len(chunk)/SAMPLE_RATE)
    if not chunks:
        raise ValueError('Nothing to play or export')
    return np.clip(np.concatenate(chunks)*snap.get('volume', .8), -1, 1), durations


@for_snapshot
def export_video(snap, path):
    from diagrams.video_export import _encode_states, _frame
    audio, durations = build_audio(snap)
    segments = musical_segments(snap)
    spec = snap['render_spec']
    states = []
    if len(segments) > 1 or snap.get('progression') or snap.get('scale_prog_items') or snap.get('arp_prog_items'):
        elapsed = 0.
        for index, duration in enumerate(durations):
            states.append((elapsed, index))
            elapsed += duration
        highlight = 'highlighted_idx'
    elif snap.get('frets'):
        events = segments[0][0]
        for t in sorted({0., *(e.start for e in events), *(e.start+e.duration for e in events)}):
            states.append((t, frozenset(e.string for e in events if e.start <= t < e.start+e.duration)))
        highlight = 'highlighted_strings'
    else:
        events = segments[0][0]
        states = [(e.start, (e.string, e.fret)) for e in events]
        if events:
            states.append((events[-1].start+snap['note_ms']/1000, None))
        highlight = 'highlighted_notes'
    tab = build_tab(snap) if snap.get('with_tab') else None
    target = (1080, 1500) if snap.get('portrait') else (1800, 950)
    def render(key):
        check_cancelled()
        value = ({key} if key is not None else set()) if highlight == 'highlighted_notes' else key
        image = render_spec(spec, target, **{highlight: value})
        return _frame(image, snap.get('portrait', False), tab)
    return _encode_states(states, render, audio, path)


@for_snapshot
def build_tab(snap):
    from diagrams.tab_diagram import render_chord_tab, render_scale_tab
    from PIL import Image
    tabs = []
    for events, _ in musical_segments(snap):
        # Explicit event pitches preserve the exact same fingering/order as sound.
        notes = [dict(string=e.string, fret=e.fret, midi=e.midi, is_root=False) for e in events]
        if snap.get('frets'):
            return render_chord_tab(snap['frets'], chord_name=snap['name'])
        if snap.get('progression'):
            chord = snap['progression'][len(tabs)]
            tabs.append(render_chord_tab(chord['frets'], chord_name=chord['display_name']))
        else:
            # Use source notes and shared options to retain ascending/descending order.
            from diagrams.tab_diagram import render_event_tab
            tabs.append(render_event_tab(events, title=snap['name']))
    if not tabs:
        raise ValueError('Nothing to render')
    if len(tabs) == 1:
        return tabs[0]
    width = max(t.width for t in tabs)
    height = sum(t.height for t in tabs)
    config.validate_size(width, height)
    from diagrams.artwork import Artwork
    artwork = Artwork(width,height)
    y = 0
    for tab in tabs:
        artwork.paste(tab,0,y)
        y += tab.height
    return artwork.finish()
