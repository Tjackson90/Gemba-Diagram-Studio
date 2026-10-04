"""Cross-export art direction and recorded-instrument regression coverage."""
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree
import numpy as np
import soundfile as sf
from scipy.signal import correlate
from audio.sampler import VOICES, sample, render, SAMPLE_DIR
from data.timeline import NoteEvent
from services.composer import compose, DEFAULTS
from services.documents import render_spec, ExportJob
from services.media import build_audio, build_tab
from services.formats import export_print
from diagrams.style import theme, THEMES


class ArtworkTests(unittest.TestCase):
    def test_theme_roundtrip_all_modes_and_real_vector_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            for skin in THEMES:
                for mode in ['Chord','Scale','Arpeggio','Progression','ScaleProg','ArpProg','Triads','ChordID']:
                    image,snap,_=compose(dict(DEFAULTS,mode=mode,diagram_theme=skin,quality='Major'))
                    self.assertEqual(image.info['diagram_theme'],skin)
                    with theme('Prism' if skin!='Prism' else 'Paper'):
                        result=render_spec(ExportJob.capture(snap).unpack()['render_spec'])
                        self.assertEqual(result.info['diagram_theme'],skin)
                        self.assertEqual(build_tab(snap).info['diagram_theme'],skin)
                    path=export_print(snap,Path(tmp)/f'{mode}.svg','svg')
                    root=ElementTree.fromstring(path.read_text())
                    self.assertFalse(root.findall('.//{http://www.w3.org/2000/svg}image'))
                    self.assertTrue(root.findall('.//{http://www.w3.org/2000/svg}text'))

    def test_scale_views_have_distinct_vector_geometry(self):
        box,_,_=compose(dict(DEFAULTS,mode='Scale',view='Position'))
        neck,_,_=compose(dict(DEFAULTS,mode='Scale',view='Full fretboard'))
        self.assertLess(box.width,box.height)
        self.assertGreater(neck.width,neck.height)
        self.assertNotEqual(box.info['svg_body'],neck.info['svg_body'])


class SampleAudioTests(unittest.TestCase):
    def test_manifest_matches_bundled_assets(self):
        import hashlib
        manifest=json.loads((SAMPLE_DIR/'manifest.json').read_text())
        self.assertGreater(len(manifest['samples']),100)
        for row in manifest['samples']:
            file=SAMPLE_DIR/row['bank']/f"{row['midi']}.flac"
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),row['sha256'])

    def test_voices_are_tuned_and_stereo_without_clipping(self):
        for name,(bank,_) in VOICES.items():
            note=sample(bank,57,44100)[4000:16000]
            c=correlate(note,note,mode='full',method='fft')[len(note)-1:]
            target=44100/220
            lo,hi=round(target*.9),round(target*1.1)
            k=lo+int(np.argmax(c[lo:hi]))
            fraction=.5*(c[k-1]-c[k+1])/(c[k-1]-2*c[k]+c[k+1])
            error=1200*np.log2(target/(k+fraction))
            self.assertLess(abs(error),20,(name,error))
            events=[NoteEvent(57,2,2,0,.4),NoteEvent(64,5,0,.2,.4)]
            sound=render(events,name,44100,{},tail=.5)
            self.assertEqual(sound.shape,(48510,2))
            self.assertTrue(np.isfinite(sound).all())
            self.assertGreater(float(np.max(np.abs(sound))),.02)
            self.assertLessEqual(float(np.max(np.abs(sound))),.891)
            self.assertTrue(np.allclose(sound[-1],0))
            self.assertFalse(np.allclose(sound[:,0],sound[:,1]))

    def test_nylon_d5_mapping_does_not_play_a_semitone_high(self):
        note=sample('guitar-nylon',74,44100)[4000:14000]
        c=correlate(note,note,mode='full',method='fft')[len(note)-1:]
        target=44100/(440*2**((74-69)/12))
        k=round(target*.9)+int(np.argmax(c[round(target*.9):round(target*1.1)]))
        self.assertLess(abs(1200*np.log2(target/k)),25)

    def test_progression_holds_and_stereo_wav_and_attribution(self):
        from audio.engine import export_wav, generate_progression_audio
        _,snap,_=compose(dict(DEFAULTS,mode='Progression',duration=8,tempo=400))
        sound,durations=build_audio(snap)
        self.assertEqual(sound.shape[1],2)
        self.assertAlmostEqual(len(sound)/44100,sum(durations))
        self.assertTrue(all(d>=8 for d in durations))
        cli=generate_progression_audio(snap['progression'],chord_duration_s=.3)
        self.assertEqual(cli.shape[1],2)
        with tempfile.TemporaryDirectory() as tmp:
            path=export_wav(sound,Path(tmp)/'lesson.wav')
            self.assertEqual(sf.info(path).channels,2)
            self.assertTrue((Path(tmp)/'Gemba-instrument-credits.txt').exists())
