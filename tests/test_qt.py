"""Offscreen integration tests for the Qt editor and existing export engine."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
import config
from gui.qt_app import create_application, StudioWindow, MODES, validate_lesson
from services.composer import DEFAULTS, compose, from_legacy
from services.storage import write_json
from services.media import musical_segments


class ComposerTests(unittest.TestCase):
    def test_legacy_settings_preserve_music_and_playback(self):
        snap=dict(mode='Scale',variables=dict(scale_root_var='F',scale_type_var='Major',
            scale_view_var='3NPS 2',tempo_var='120',volume_var=.65,play_style_var='Strum Up',
            capo_var=2,tuning_var='Drop D',left_handed_var=True,tone_attack_var=.7))
        s=from_legacy(snap)
        self.assertEqual((s['root'],s['scale'],s['position'],s['view']),('F','Major',2,'3 notes per string'))
        self.assertEqual((s['tempo'],s['volume'],s['direction'],s['capo']),(120,65,'up',2))
        self.assertEqual(s['tone_settings'],{'attack':.7})
        self.assertTrue(s['left_handed'])

    def test_identifier_legacy_fingering_conversion(self):
        s=from_legacy(dict(mode='ChordID',identifier=dict(strings=6,open_muted=['O','O','O','O','O','X'],
            fingers=[dict(string=2,fret=1),dict(string=4,fret=2)])))
        self.assertEqual(s['frets'],[-1,0,2,0,1,0])

    def test_all_views_and_harmonizations(self):
        for view in ['Position','Full fretboard','3 notes per string']:
            for mode in ['Scale','Arpeggio']:
                if mode=='Arpeggio' and view=='3 notes per string': continue
                state=dict(DEFAULTS,mode=mode,scale='Major',view=view)
                image,snap,_=compose(state)
                self.assertGreater(image.width,0)
                self.assertTrue(snap['scale_notes'])
        for scope in ['Major key','Natural minor','Harmonic minor','Melodic minor']:
            _,snap,_=compose(dict(DEFAULTS,mode='Triads',quality='Major',triad_scope=scope))
            self.assertEqual(len(snap['progression']),7)

    def test_direction_changes_actual_export_events(self):
        _,snap,_=compose(dict(DEFAULTS,mode='Scale',note_direction='Desc',root_to_root=False))
        events=musical_segments(snap)[0][0]
        self.assertGreater(events[0].midi,events[-1].midi)
        self.assertEqual([e.midi for e in events],sorted([e.midi for e in events],reverse=True))

    def test_invalid_lesson_does_not_pass_validation(self):
        for settings in [dict(DEFAULTS,tempo=0),dict(DEFAULTS,frets=[0]),dict(DEFAULTS,mode='Unknown')]:
            with self.assertRaises(ValueError): validate_lesson(dict(version=2,editor=settings,queue=[]))


class QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt=create_application()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch.object(config,'DATA_DIR',Path(self.temp.name)); self.patch.start()
        self.w=StudioWindow(); self.w.show(); self.qt.processEvents()

    def tearDown(self):
        self.w.saved_settings=deepcopy(self.w.settings)
        self.w.jobs.close(); self.w.close(); self.qt.processEvents()
        self.patch.stop(); self.temp.cleanup()

    def test_every_mode_renders_and_exports_snapshot(self):
        for mode,_ in MODES:
            self.w.set_mode(mode)
            self.assertIsNotNone(self.w.snapshot,mode)
            snap=self.w.capture().unpack()
            self.assertEqual(snap['render_spec'],self.w.image.info['render_spec'])
            self.assertTrue(musical_segments(snap))

    def test_pending_controls_are_captured_and_undo_restores_them(self):
        before=self.w.capture().unpack()['name']
        self.w.controls['root'].setCurrentText('D')
        self.assertIsNone(self.w.snapshot)
        self.assertNotEqual(self.w.capture().unpack()['name'],before)
        self.w.undo(); self.assertEqual(self.w.capture().unpack()['name'],before)
        self.w.redo(); self.assertEqual(self.w.settings['root'],'D')

    def test_mode_change_clears_progression_and_invalid_preview_cannot_export(self):
        self.w.set_mode('Progression'); self.assertIn('progression',self.w.snapshot)
        self.w.set_mode('Scale'); self.assertNotIn('progression',self.w.snapshot)
        self.w.change('scale','not a scale')
        with self.assertRaises(ValueError): self.w.capture()
        self.assertFalse(self.w.export_button.isEnabled())

    def test_identifier_clicks_and_undo(self):
        from gui.qt_canvas import FingeringEditor
        self.w.set_mode('ChordID')
        editor=self.w.findChild(FingeringEditor)
        QTest.mouseClick(editor,Qt.MouseButton.LeftButton,pos=QPoint(25,61))
        self.w.capture()
        self.assertEqual(self.w.settings['frets'][0],1)
        self.w.undo(); self.assertEqual(self.w.settings['frets'][0],-1)

    def test_lesson_save_open_and_queue_merge(self):
        self.w.change('root','D'); self.w.capture()
        self.w.add_queue(self.w.capture().unpack())
        path=Path(self.temp.name)/'lesson.gemba.json'; self.w.project_path=path
        self.assertTrue(self.w.save_project())
        self.w.change('root','F'); self.w.capture()
        self.w.add_queue(self.w.capture().unpack())
        self.assertTrue(self.w.load_project(path))
        self.assertEqual(self.w.settings['root'],'D')
        self.assertEqual(len(self.w.queue),2)

    def test_legacy_lesson_opens_in_qt(self):
        path=Path(self.temp.name)/'old.gemba.json'
        write_json(path,dict(version=1,snapshot=dict(mode='Scale',variables=dict(scale_root_var='F',
            scale_type_var='Major',scale_view_var='Box 2',tempo_var='120')),queue=[]))
        self.assertTrue(self.w.load_project(path))
        self.assertEqual(self.w.settings['mode'],'Scale'); self.assertEqual(self.w.settings['position'],2)

    def test_export_formats_use_current_instrument_settings(self):
        self.w.change('tuning','Drop D'); self.w.change('capo',2)
        snap=self.w.capture().unpack()
        for index,ext in [(0,'png'),(2,'wav'),(4,'mid'),(5,'svg'),(6,'pdf'),(7,'png')]:
            path=Path(self.temp.name)/f'export-{index}.{ext}'
            self.w.export_snapshot(snap,path,index,'Square','transparent')
            self.assertGreater(path.stat().st_size,30)
            if ext=='mid': self.assertTrue(path.read_bytes().startswith(b'MThd'))

    def test_queue_failure_retains_only_failed_export(self):
        self.w.add_queue(self.w.capture().unpack()); self.w.add_queue(self.w.capture().unpack())
        with patch('gui.qt_app.QFileDialog.getExistingDirectory',return_value=self.temp.name), \
             patch.object(self.w,'export_snapshot',side_effect=[Path('ok.mp4'),RuntimeError('Test encoder error')]):
            self.w.export_queue()
            deadline=time.monotonic()+5
            while self.w.jobs.busy and time.monotonic()<deadline:
                self.qt.processEvents(); time.sleep(.02)
        self.assertFalse(self.w.jobs.busy)
        self.assertEqual(len(self.w.queue),1)
        self.assertIn('Test encoder error',self.w.queue[0]['error'])

    def test_minimum_size_keeps_canvas_and_controls_visible(self):
        self.w.resize(1100,740); self.qt.processEvents()
        self.assertGreaterEqual(self.w.canvas.width(),300)
        self.assertGreaterEqual(self.w.canvas.height(),260)
        self.assertTrue(self.w.play_button.isVisible())
        self.assertTrue(self.w.export_button.isVisible())


if __name__=='__main__': unittest.main()
