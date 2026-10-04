"""Opt-in real-window tests: GEMBA_GUI_TESTS=1 python -m unittest discover -s tests."""
import os
import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import patch
import config


@unittest.skipUnless(os.environ.get('GEMBA_GUI_TESTS') == '1', 'requires a desktop/Tcl installation')
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.old_data = config.DATA_DIR
        config.DATA_DIR = Path(cls.temp.name)
        from gui.app import DiagramStudioApp
        cls.app = DiagramStudioApp()
        cls.app.withdraw()
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls.app._jobs.close()
        cls.app.destroy()
        config.DATA_DIR = cls.old_data
        cls.temp.cleanup()

    def test_all_modes_capture_and_restore(self):
        from services.media import build_audio, build_tab
        from services.documents import render_spec
        app=self.app
        for mode in ['Chord','Scale','Arpeggio','Progression','ScaleProg','ArpProg','Triads']:
            app._set_mode(mode)
            snapshot=app._snapshot()
            job=app._capture_job().unpack()
            audio,durations=build_audio(job)
            self.assertGreater(len(audio),0,mode)
            self.assertGreater(build_tab(job).height,0,mode)
            self.assertGreater(render_spec(job['render_spec'],(1280,720)).width,0,mode)
            app._set_mode('Chord')
            app._restore_snapshot(snapshot)
            self.assertEqual(app.mode_var.get(),mode)
            self.assertEqual(app._snapshot(),snapshot)

    def test_scale_clears_progression(self):
        self.app._set_mode('Progression')
        self.app._set_mode('Scale')
        self.assertIsNone(self.app.document.progression)
        self.assertTrue(self.app.document.scale_notes)

    def test_actual_legacy_snapshots_migrate_to_qt_composer(self):
        from services.composer import from_legacy, compose
        for mode in ['Chord','Scale','Arpeggio','Progression','ScaleProg','ArpProg','Triads','ChordID','ChordLookup']:
            self.app._set_mode(mode)
            settings=from_legacy(self.app._snapshot())
            image,snap,_=compose(settings)
            self.assertGreater(image.width,0,mode)
            self.assertTrue(snap['render_spec'],mode)

    def test_batch_failure_keeps_only_failed_job(self):
        app=self.app
        app._batch_queue=[]
        app._set_mode('Chord')
        app._add_to_batch_queue(); app._add_to_batch_queue()
        failed_id=app._batch_queue[0]['id']
        with patch('gui.workflows.filedialog.askdirectory',return_value=self.temp.name), \
             patch('gui.workflows.export_video',side_effect=[RuntimeError('Encoder failed'),Path(self.temp.name)/'ok.mp4']):
            app._export_batch_queue()
            for _ in range(200):
                app.update()
                if not app._jobs.busy:
                    break
                time.sleep(.01)
        self.assertEqual(len(app._batch_queue),1)
        self.assertEqual(app._batch_queue[0]['id'],failed_id)
        self.assertEqual(app._batch_queue[0]['error'],'Encoder failed')
        self.assertEqual(app._batch_results,{'saved':1,'failed':1})
        app._clear_batch_queue()

    def test_tuning_capo_roundtrip(self):
        from data.instrument import get_tuning
        app=self.app
        app.tuning_var.set('Drop D');app.capo_var.set(2);app.left_handed_var.set(True)
        app._instrument_changed()
        snapshot=app._snapshot()
        app.tuning_var.set('Standard');app.capo_var.set(0);app._instrument_changed()
        app._restore_snapshot(snapshot)
        self.assertEqual(get_tuning()[0],40)
        self.assertTrue(app.left_handed_var.get())
        app.tuning_var.set('Standard');app.capo_var.set(0);app.left_handed_var.set(False)
        app._instrument_changed()

    def test_project_roundtrip_and_queue(self):
        from services.storage import read_json
        app=self.app
        app._set_mode('Chord');app._add_to_batch_queue()
        path=Path(self.temp.name)/'lesson.gemba.json'
        with patch('gui.workflows.filedialog.asksaveasfilename',return_value=str(path)):
            app._save_project()
        self.assertEqual(len(read_json(path,None)['queue']),1)
        app._batch_queue=[];app._set_mode('Scale')
        with patch('gui.workflows.filedialog.askopenfilename',return_value=str(path)):
            app._open_project()
        self.assertEqual(app.mode_var.get(),'Chord')
        self.assertEqual(len(app._batch_queue),1)
        app._clear_batch_queue()

    def test_identifier_undo_redo(self):
        app=self.app
        app._set_mode('ChordID')
        before=list(app._ci_fingers)
        app._ci_toggle_finger(1,3)
        after=list(app._ci_fingers)
        app._undo_edit();self.assertEqual(app._ci_fingers,before)
        app._redo_edit();self.assertEqual(app._ci_fingers,after)
