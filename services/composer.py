"""UI-independent editor settings, diagram composition and legacy lesson migration."""
from copy import deepcopy
from data.chords import CHORD_INTERVALS, get_voicings, get_chord_display_name
from data.notes import note_name_to_semitone, SHARP_NAMES
from data.instrument import instrument, get_tuning
from data.scales import get_full_fretboard_scale, get_caged_positions, get_three_note_per_string_scale
from data.arpeggios import get_full_fretboard_arpeggio, get_arpeggio_positions
from data.progressions import (MAJOR_PROGRESSIONS, MINOR_PROGRESSIONS, parse_roman,
    get_progression_chords, get_progression_scales, get_progression_arpeggios)
from data.triads import (TRIAD_VOICING_NAMES, get_triad_voicing, get_diatonic_triads,
    get_diatonic_minor_triads, get_diatonic_harmonic_minor_triads, get_diatonic_melodic_minor_triads)
from diagrams.chord_diagram import render_chord_diagram
from diagrams.scale_diagram import render_scale_box, render_scale_full_fretboard
from diagrams.progression_diagram import render_progression_strip
from diagrams.scale_progression_diagram import render_scale_progression_strip, render_arpeggio_progression_strip


DEFAULTS = dict(mode='Chord', root='A', quality='Min7', scale='Pentatonic Minor', arp='Minor',
    voicing=0, view='Position', position=1, invert=False, progression=next(iter(MAJOR_PROGRESSIONS)),
    roman='', key_mode='major', override='Auto', triad=TRIAD_VOICING_NAMES[0], triad_scope='Single chord',
    tuning='Standard', capo=0, left_handed=False, dot_label='note', show_barre=True,
    barre_style='arch', show_string_names=True, show_finger_numbers=True, show_muted_x=True,
    show_open_o=True, tone='Studio Acoustic', tempo=110, volume=80, play_style='arpeggio', direction='down',
    note_direction='Asc + Desc', root_to_root=True, high_e_root=False, duration=2.0,
    portrait=False, with_tab=False, resolution='1080p', background='theme',
    frets=[-1,0,2,0,1,0], custom_title='', tone_settings={}, panel_directions=[], diagram_theme='Volt')


def normalize_settings(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid editor settings')
    result = deepcopy(DEFAULTS)
    result.update({k: deepcopy(v) for k,v in value.items() if k in result})
    if result['mode'] not in ('Chord','Scale','Arpeggio','Progression','ScaleProg','ArpProg','Triads','ChordID','ChordLookup'):
        raise ValueError('Unknown editor mode')
    for key, low, high in [('tempo',20,400),('capo',0,12),('position',1,7),('volume',0,100),('voicing',0,100)]:
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise ValueError(f'Invalid {key}')
    if not isinstance(result['frets'],list) or len(result['frets']) != 6 or any(type(f) is not int or not -1<=f<=24 for f in result['frets']):
        raise ValueError('A fingering needs six fret values between -1 and 24')
    if not isinstance(result['duration'],(int,float)) or not .1 <= result['duration'] <= 30:
        raise ValueError('Panel duration must be between 0.1 and 30 seconds')
    return result


def identify(frets):
    pitches = {(get_tuning()[i]+f)%12 for i,f in enumerate(frets) if f>=0}
    matches = []
    for root in range(12):
        for quality, intervals in CHORD_INTERVALS.items():
            if pitches == {(root+i)%12 for i in intervals}:
                matches.append((get_chord_display_name(SHARP_NAMES[root],quality),root))
    return matches


def compose(settings):
    """Return a preview image, immutable-export-compatible snapshot and editor metadata."""
    s = normalize_settings(settings)
    ins = {k:s[k] for k in ('tuning','capo','left_handed')}
    from diagrams.style import theme
    with instrument(ins), theme(s['diagram_theme']):
        return _compose(s, ins)


def _compose(s, ins):
    mode, root = s['mode'], s['root'].split('/')[0]
    semi = note_name_to_semitone(root)
    display = {k:s[k] for k in ('dot_label','show_barre','barre_style','show_string_names','show_finger_numbers')}
    snap = dict(name='', instrument=ins, tone=s['tone'], note_ms=60000/s['tempo'], volume=s['volume']/100,
        tone_settings=s['tone_settings'], play_style_raw=[s['play_style'],s['direction']],
        portrait=s['portrait'], with_tab=s['with_tab'], prog_duration=s['duration'],
        prog_strum_dirs=s['panel_directions'], root_semitone=semi,
        note_options=dict(ascending=s['note_direction']!='Desc', descending=s['note_direction']!='Asc',
                          root_to_root=s['root_to_root'],stop_at_high_e_root=s['high_e_root']))
    meta = dict(voicings=[], detail='', notes=[])
    if mode in ('Chord','ChordLookup','ChordID') or (mode=='Triads' and s['triad_scope']=='Single chord'):
        if mode=='ChordID':
            matches=identify(s['frets'])
            name = s['custom_title'].strip() or (matches[0][0] if matches else 'Custom chord')
            semi = matches[0][1] if matches else semi
            v = dict(frets=s['frets'],fingers=[0]*6)
            meta['detail'] = ' / '.join(m[0] for m in matches) or 'Custom voicing'
        elif mode=='Triads':
            v = get_triad_voicing(root,s['quality'],s['triad'])
            name = v['display_name']
            meta['detail'] = s['triad']
        else:
            voicings = get_voicings(root,s['quality'])
            if not voicings:
                raise ValueError('No voicing available for this chord')
            meta['voicings'] = [v['label'] for v in voicings]
            v = voicings[min(s['voicing'],len(voicings)-1)]
            name = get_chord_display_name(root,s['quality'])
            meta['detail'] = v['label']
        image = render_chord_diagram(v['frets'],fingers=v.get('fingers'),chord_name=name,
            root_semitone=semi,width=600,height=800,bg_color=None,**display,
            show_muted_x=s['show_muted_x'],show_open_o=s['show_open_o'])
        snap.update(frets=v['frets'],fingers=v.get('fingers'),root_semitone=semi)
        meta['notes'] = [SHARP_NAMES[(get_tuning()[i]+f)%12] for i,f in enumerate(v['frets']) if f>=0]
    elif mode in ('Scale','Arpeggio'):
        arp = mode=='Arpeggio'
        kind = s['arp'] if arp else s['scale']
        from data.scales import SCALE_NAMES
        from data.arpeggios import ARPEGGIO_NAMES
        if kind not in (ARPEGGIO_NAMES if arp else SCALE_NAMES):
            raise ValueError('Choose a definition from the library')
        name = f'{root} {kind}' + (' arpeggio' if arp else '')
        if s['view']=='Full fretboard':
            notes=(get_full_fretboard_arpeggio if arp else get_full_fretboard_scale)(root,kind,num_frets=15)
            image=render_scale_full_fretboard(notes,scale_name=kind,root_name=root,width=1600,height=500,invert=s['invert'])
        else:
            if s['view']=='3 notes per string' and not arp:
                notes=get_three_note_per_string_scale(root,kind,position=s['position'])
                if not notes:
                    raise ValueError('This scale does not have a playable 3NPS shape at this position')
                start=max(1,min(n['fret'] for n in notes))
                end=max(n['fret'] for n in notes)
            else:
                positions=(get_arpeggio_positions if arp else get_caged_positions)(root,kind)
                if s['position']>len(positions):
                    raise ValueError(f'Choose a position from 1 to {len(positions)}')
                pos=positions[s['position']-1]
                notes,start,end=pos['notes'],pos['start_fret'],pos['end_fret']
            image=render_scale_box(notes,start_fret=start,end_fret=end,scale_name=kind,root_name=root,
                position_num=s['position'],width=600,height=800)
        snap.update(scale_notes=notes,is_arpeggio=arp)
        meta['detail']=s['view']+(f" {s['position']}" if s['view']!='Full fretboard' else '')
        meta['notes']=list(dict.fromkeys(n['note_name'] for n in notes))
    else:
        key_mode=s['key_mode']
        if mode=='Triads':
            getter={'Major key':get_diatonic_triads,'Natural minor':get_diatonic_minor_triads,
                    'Harmonic minor':get_diatonic_harmonic_minor_triads,'Melodic minor':get_diatonic_melodic_minor_triads}[s['triad_scope']]
            items=getter(root,s['triad'])
            name=f"{root} {s['triad_scope']} / {s['triad']}"
        else:
            if s['roman'].strip():
                degrees=parse_roman(s['roman'],key_mode)
                if not degrees:
                    raise ValueError('Use Roman numerals such as I-V-vi-IV')
                label=s['roman']
            else:
                label=s['progression']
                key_mode='minor' if label in MINOR_PROGRESSIONS else 'major'
                degrees=(MINOR_PROGRESSIONS if key_mode=='minor' else MAJOR_PROGRESSIONS)[label]
            getter={'Progression':get_progression_chords,'ScaleProg':get_progression_scales,'ArpProg':get_progression_arpeggios}[mode]
            items=getter(root,key_mode,degrees)
            name=f'{root} {key_mode} / {label}'
        if mode in ('Progression','Triads'):
            if mode=='Progression' and s['override']!='Auto':
                for item in items:
                    v=get_voicings(item['chord_root'],s['override'])[0]
                    item.update(quality=s['override'],frets=v['frets'],fingers=v.get('fingers'),
                        display_name=get_chord_display_name(item['chord_root'],s['override']))
            image=render_progression_strip(items,title=name,**display)
            snap['progression']=items
        else:
            arp=mode=='ArpProg'
            if arp and s['override']!='Auto':
                for item in items:
                    item.update(arp_name=s['override'],display_name=f"{item['chord_root']} {s['override']}")
            prefix='arp_prog' if arp else 'scale_prog'
            image=(render_arpeggio_progression_strip if arp else render_scale_progression_strip)(items,title=name,position_num=s['position'])
            snap.update({prefix+'_items':items,prefix+'_pos':s['position'],prefix+'_duration':s['duration']*1000,
                         prefix+'_dirs':s['panel_directions'] or [s['note_direction']]*len(items)})
        meta['detail']='  /  '.join(i['display_name'] for i in items)
        meta['panels']=[i['display_name'] for i in items]
    snap.update(name=name,render_spec=image.info['render_spec'])
    return image,snap,meta


def from_legacy(snapshot):
    """Read existing Tk lessons without constructing or importing any Tk widgets."""
    if 'editor' in snapshot:
        return normalize_settings(snapshot['editor'])
    mode=snapshot.get('mode','Chord')
    s=deepcopy(DEFAULTS)
    s['mode']=mode if mode!='Custom' else 'Scale'
    v=snapshot.get('variables',{})
    prefix={'Chord':'','ChordLookup':'','Scale':'scale_','Arpeggio':'arp_','Progression':'prog_',
            'ScaleProg':'_scale_prog_','ArpProg':'_arp_prog_','Triads':'triads_'}.get(mode,'')
    for key, old in [('root','root'),('quality','quality'),('scale','scale_type'),('arp','arp_type'),
                      ('tone','tone'),('tempo','tempo'),('tuning','tuning'),('capo','capo'),('left_handed','left_handed')]:
        candidate=prefix+old+'_var' if key in ('root','quality') else old+'_var'
        if candidate in v:
            s[key]=v[candidate]
    for key in ('dot_label','show_barre','barre_style','show_string_names','show_finger_numbers','show_muted_x','show_open_o','invert'):
        s[key]=v.get(prefix+key+'_var',v.get(key+'_var',s[key]))
    s['barre_style']='arch' if s['barre_style'].lower()=='arch' else 'rect'
    s['tempo']=int(s['tempo'])
    s['volume']=round(float(v.get('volume_var',.8))*100)
    voicing=v.get('voicing_var',snapshot.get('voicing','1'))
    try: s['voicing']=max(0,int(str(voicing).split(':')[0])-1)
    except ValueError: pass
    s['position']=int(v.get(prefix+'pos_var',1))
    s['duration']=float(v.get(prefix+'duration_var',2))
    s['portrait']=v.get('video_portrait_var',False)
    s['with_tab']=v.get('video_with_tab_var',False)
    play=v.get('play_style_var','Arpeggiate').lower()
    s['play_style']='arpeggio_strum' if 'arpegg' in play and 'strum' in play else 'arpeggio' if 'arpegg' in play else 'strum'
    s['direction']='up' if 'up' in play else 'down'
    s['tone_settings']={key.removeprefix('tone_').removesuffix('_var'):value for key,value in v.items() if key.startswith('tone_') and key.endswith('_var')}
    if mode=='Triads':
        s['root']=v.get('triads_key_var','C')
        s['triad']=v.get('triads_voicing_var',s['triad'])
        scope=v.get('triads_scale_var','Major')
        s['triad_scope']={'Major':'Major key','Natural Minor':'Natural minor','Harmonic Minor':'Harmonic minor','Melodic Minor':'Melodic minor'}.get(scope,'Single chord')
        if s['quality'] not in ('Major','Minor','Dim','Aug','Sus2','Sus4'): s['quality']='Major'
    if mode=='ChordLookup':
        s.update(root=snapshot.get('lookup',{}).get('root','A'),quality=snapshot.get('lookup',{}).get('quality','Major'))
    if mode=='ChordID':
        identifier=snapshot.get('identifier',{})
        if identifier.get('strings',6)!=6:
            raise ValueError('This lesson uses the legacy 4/5/7/8-string editor. Open it with studio.py --legacy-ui.')
        om=identifier.get('open_muted',['O']*6)
        s['frets']=[0 if mark=='O' else -1 for mark in reversed(om)]
        for finger in identifier.get('fingers',[]):
            s['frets'][6-finger['string']]=finger['fret']
    direction_key={'Progression':'_prog_dir_vars','ScaleProg':'_scale_prog_dir_vars','ArpProg':'_arp_prog_dir_vars'}.get(mode)
    if direction_key:
        s['panel_directions']=snapshot.get('directions',{}).get(direction_key,[])
    s['roman']=v.get(prefix+'custom_var','')
    s['progression']=v.get(prefix+'name_var',s['progression'])
    s['key_mode']=v.get(prefix+'key_mode_var','major')
    view=v.get(prefix+'view_var','')
    if view:
        s['view']='Full fretboard' if view=='Full Fretboard' else '3 notes per string' if view.startswith('3NPS') else 'Position'
        if view[-1:].isdigit():
            s['position']=int(view[-1])
    for key in ('root','quality','scale','voicing'):
        if key in snapshot and key!='voicing':
            s[key]=snapshot[key]
    return normalize_settings(s)
