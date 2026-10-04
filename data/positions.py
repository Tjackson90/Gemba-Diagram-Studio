"""Explicit two-note-per-string pentatonic patterns, low E to high E."""
MINOR_PENTATONIC = (
    ((0,3),(0,2),(0,2),(0,2),(0,3),(0,3)),
    ((3,5),(2,5),(2,5),(2,4),(3,5),(3,5)),
    ((5,7),(5,7),(5,7),(4,7),(5,8),(5,7)),
    ((7,10),(7,10),(7,9),(7,9),(8,10),(7,10)),
    ((10,12),(10,12),(9,12),(9,12),(10,12),(10,12)),
)


def pentatonic_positions(root, scale_name, get_notes):
    from data.notes import note_name_to_semitone
    from data.instrument import get_tuning, settings
    base = (note_name_to_semitone(root) - get_tuning()[0] % 12 - (3 if scale_name == 'Pentatonic Major' else 0)) % 12
    limit = 24-settings()['capo']
    notes = get_notes(root, scale_name, limit)
    result = []
    for index, pattern in enumerate(MINOR_PENTATONIC):
        shift = base
        if max(max(row) for row in pattern) + shift > limit:
            shift -= 12
        cells = {(s, f+shift) for s, row in enumerate(pattern) for f in row}
        if min(f for _, f in cells) < 0:
            return fret_windows(root, scale_name, get_notes)
        selected = [n for n in notes if (n['string'], n['fret']) in cells]
        result.append(dict(position_num=index+1, start_fret=min(f for _, f in cells),
                           end_fret=max(f for _, f in cells), notes=selected))
    return result


def fret_windows(root, name, get_notes):
    """Exploratory pitch-class windows; these are not prescribed CAGED fingerings."""
    from data.notes import note_name_to_semitone
    from data.instrument import get_tuning, settings
    limit = 24-settings()['capo']
    base = (note_name_to_semitone(root)-get_tuning()[0]) % 12
    all_notes = get_notes(root, name, limit)
    if not all_notes:
        return []
    result = []
    for index, offset in enumerate((0,2,5,7,10)):
        start = base+offset
        while start+4 > limit and start>=12:
            start -= 12
        start = max(0,min(start,limit-4))
        selected = [n for n in all_notes if start<=n['fret']<=start+4]
        for string in range(6):
            if not any(n['string']==string for n in selected):
                nearby = [n for n in all_notes if n['string']==string and start-1<=n['fret']<=start+5]
                if nearby:
                    selected.append(min(nearby,key=lambda n:abs(n['fret']-(start+2))))
        if not selected:
            continue
        held = [n['fret'] for n in selected if n['fret']>0]
        result.append(dict(position_num=index+1, start_fret=min(held,default=1),
                           end_fret=max(held,default=4),
                           notes=sorted(selected,key=lambda n:(n['string'],n['fret']))))
    return result
