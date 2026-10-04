import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from data.chords import CHORD_INTERVALS, get_voicings, parse_chord_name
from data.notes import SHARP_NAMES, fret_to_semitone, note_name_to_semitone
from data.triads import TRIAD_TEMPLATES, get_triad_voicing
from data.scales import get_caged_positions, get_full_fretboard_scale, get_scale_tone_names
from data.arpeggios import get_full_fretboard_arpeggio
from data.timeline import note_sequence, scale_events
from data.instrument import instrument, TUNINGS, get_tuning
from services.storage import read_json, write_json, StorageError, safe_filename
from services.documents import ExportJob, render_spec
from diagrams.chord_diagram import render_chord_diagram
from diagrams.export import export_diagram
from audio.engine import export_wav, generate_scale_audio


def chord_job():
    v = get_voicings('C','Major')[0]
    image = render_chord_diagram(v['frets'], fingers=v['fingers'], chord_name='C', root_semitone=0)
    return dict(name='C', frets=v['frets'], fingers=v['fingers'], tone='Acoustic',
                note_ms=120, play_style_raw=['arpeggio','down'], volume=.8,
                render_spec=image.info['render_spec'], tone_settings={}, portrait=False)


class MusicTests(unittest.TestCase):
    def test_all_chord_tones_and_defining_intervals(self):
        for root in SHARP_NAMES:
            for quality, intervals in CHORD_INTERVALS.items():
                voicings = get_voicings(root, quality)
                self.assertTrue(voicings, (root, quality))
                expected = {(note_name_to_semitone(root)+i)%12 for i in intervals}
                required = expected - ({(note_name_to_semitone(root)+7)%12}
                                      if quality in ('7','9','Maj9','Min9') else set())
                for v in voicings:
                    actual = {fret_to_semitone(i,f) for i,f in enumerate(v['frets']) if f>=0}
                    self.assertFalse(actual-expected, (root,quality,v))
                    self.assertFalse(required-actual, (root,quality,v))
                    self.assertTrue(all(finger==0 for f,finger in zip(v['frets'],v['fingers']) if f<=0))

    def test_all_triads_preserve_pitch_and_compact_shape(self):
        for root in SHARP_NAMES:
            for name, template in TRIAD_TEMPLATES.items():
                for quality in template['offsets']:
                    v = get_triad_voicing(root,quality,name)
                    actual = {fret_to_semitone(i,f) for i,f in enumerate(v['frets']) if f>=0}
                    self.assertEqual(actual,{(note_name_to_semitone(root)+i)%12 for i in CHORD_INTERVALS[quality]})
                    frets = [f for f in v['frets'] if f>=0]
                    self.assertLessEqual(max(frets)-min(frets),5)

    def test_pentatonic_positions(self):
        for root in SHARP_NAMES:
            for name in ['Pentatonic Minor','Pentatonic Major']:
                for position in get_caged_positions(root,name):
                    for string in range(6):
                        self.assertEqual(sum(n['string']==string for n in position['notes']),2)
        first=get_caged_positions('A','Pentatonic Minor')[0]
        self.assertEqual([n['fret'] for n in first['notes'] if n['string']==3],[5,7])

    def test_spelling_and_parser(self):
        self.assertEqual(parse_chord_name('CM7'),('C','Maj7'))
        self.assertEqual(parse_chord_name('Cm7'),('C','Min7'))
        self.assertEqual(get_scale_tone_names('F','Major'),['F','G','A','Bb','C','D','E'])
        self.assertEqual(get_scale_tone_names('F#','Major')[-1],'E#')
        self.assertIn('Bb',{n['note_name'] for n in get_full_fretboard_scale('F','Major')})

    def test_position_notes_stay_within_guitar_and_drawn_bounds(self):
        from data.arpeggios import get_arpeggio_positions
        for capo in (0,7,12):
            with instrument(dict(tuning='Standard',capo=capo,left_handed=False)):
                for root in SHARP_NAMES:
                    for getter,name in [(get_caged_positions,'Major'),(get_caged_positions,'Pentatonic Minor'),
                                        (get_arpeggio_positions,'Major')]:
                        for position in getter(root,name):
                            self.assertTrue(position['notes'])
                            for note in position['notes']:
                                self.assertGreaterEqual(note['fret'],0)
                                self.assertLessEqual(note['fret'],24-capo)
                                if note['fret']:
                                    self.assertGreaterEqual(note['fret'],position['start_fret'])
                                    self.assertLessEqual(note['fret'],position['end_fret'])

    def test_tunings_and_capo(self):
        for tuning in TUNINGS:
            for capo in (0,2,7):
                with instrument(dict(tuning=tuning,capo=capo,left_handed=True)):
                    for root in ['C','F#','Bb']:
                        for quality in CHORD_INTERVALS:
                            voicings=get_voicings(root,quality)
                            self.assertTrue(voicings,(tuning,capo,root,quality))
                            expected={(note_name_to_semitone(root)+i)%12 for i in CHORD_INTERVALS[quality]}
                            for v in voicings:
                                self.assertFalse({fret_to_semitone(i,f) for i,f in enumerate(v['frets']) if f>=0}-expected)
                        render_chord_diagram(voicings[0]['frets'], fingers=voicings[0]['fingers'])


class ExportTests(unittest.TestCase):
    def test_alpha_compositing(self):
        with tempfile.TemporaryDirectory() as d:
            source=Image.new('RGBA',(64,64),(255,255,255,128))
            p=export_diagram(source,Path(d)/'transparent.png',custom_size=(64,64))
            self.assertEqual(Image.open(p).getpixel((0,0)),(255,255,255,128))
            p=export_diagram(source,Path(d)/'navy.png',background='navy',custom_size=(64,64))
            self.assertEqual(Image.open(p).getpixel((0,0))[3],255)

    def test_native_render_and_immutable_capture(self):
        snap=chord_job();job=ExportJob.capture(snap)
        snap['frets'][0]=24
        captured=job.unpack()
        self.assertNotEqual(captured['frets'][0],24)
        image=render_spec(captured['render_spec'],(2160,2160))
        self.assertEqual(image.height,2160)

    def test_wav_format(self):
        import soundfile as sf
        with tempfile.TemporaryDirectory() as d:
            path=export_wav(np.zeros(1000),Path(d)/'test.wav',sr=22050)
            info=sf.info(path)
            self.assertEqual(info.subtype,'FLOAT')
            self.assertEqual(info.samplerate,22050)

    def test_shared_sequence_and_empty_input(self):
        notes=get_full_fretboard_arpeggio('E','Major')
        events=scale_events(notes,545,ascending=True,descending=True,stop_at_high_e_root=True)
        self.assertEqual(max(e.midi for e in events),64)
        self.assertEqual(events[10].start,5.45)
        self.assertEqual(note_sequence([]),[])
        self.assertGreater(len(generate_scale_audio([])),0)

    def test_video_absolute_timing_and_frame_deduplication(self):
        from diagrams.video_export import export_scale_video
        notes=get_full_fretboard_scale('A','Pentatonic Minor')
        options=dict(ascending=True,descending=True,stop_at_high_e_root=False)
        captured={}
        def encode(states,render,audio,path,fps,sr):
            captured['states']=states
            return path
        with patch('diagrams.video_export._encode_states',side_effect=encode):
            export_scale_video(notes,lambda **kw: None,dict(options),np.zeros(100),'ignored',note_duration_ms=545)
        self.assertAlmostEqual(captured['states'][10][0],5.45)

    def test_audio_tab_midi_svg_pdf(self):
        from services.media import build_audio,build_tab
        from services.formats import export_midi,export_print
        snap=chord_job()
        audio,durations=build_audio(snap)
        self.assertTrue(np.isfinite(audio).all())
        self.assertAlmostEqual(len(audio)/44100,sum(durations))
        self.assertGreater(build_tab(snap).width,0)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            self.assertTrue(export_midi(snap,root/'a.mid').read_bytes().startswith(b'MThd'))
            self.assertIn('<circle',export_print(snap,root/'a.svg','svg').read_text())
            self.assertTrue(export_print(snap,root/'a.pdf','pdf').read_bytes().startswith(b'%PDF'))


class StorageTests(unittest.TestCase):
    def test_project_import_keeps_scale_and_arpeggio_names_separate(self):
        from services.projects import import_library
        import data.custom_library as library
        tagged = library.CUSTOM_PREFIX + 'Lesson'
        project = dict(custom_library={'scales': {'Lesson': [0,2,4]},
                                       'arpeggios': {'Lesson': [0,4,7]}},
                       snapshot={'variables': {'scale_type_var': tagged,
                                               'arp_type_var': tagged}})
        existing = {'scales': {'Lesson': [0,2,3]}, 'arpeggios': {'Lesson': [0,4,7]}}
        with patch.object(library, 'load_raw', return_value=existing), \
             patch.object(library, '_save_raw'), \
             patch.object(library, 'load_into_scale_dicts'), \
             patch.object(library, 'load_into_arpeggio_dicts'):
            result = import_library(project)
        self.assertEqual(result['snapshot']['variables']['scale_type_var'], tagged+' (import 2)')
        self.assertEqual(result['snapshot']['variables']['arp_type_var'], tagged)
        self.assertEqual(project['snapshot']['variables']['scale_type_var'], tagged)

    def test_atomic_backup_and_corruption_protection(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'data.json'
            write_json(path,{'value':1});write_json(path,{'value':2})
            self.assertEqual(read_json(path.with_name('data.json.bak'),None),{'value':1})
            path.write_text('{broken')
            with self.assertRaises(StorageError):write_json(path,{'value':3})
            self.assertEqual(path.read_text(),'{broken')

    def test_filenames(self):
        for name in ['C/G','A: Minor','..\\escape','CON','a?b*']:
            safe=safe_filename(name)
            self.assertFalse(any(c in safe for c in '<>:"/\\|?*'))
            self.assertNotEqual(safe,'CON')


if __name__=='__main__':
    unittest.main()
