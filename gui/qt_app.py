"""Gemba Studio: Qt desktop workspace over the shared music/export services."""
import json
import logging
import sys
import uuid
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QFont, QFontDatabase, QKeySequence, QDesktopServices, QPainter, QPen, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea, QComboBox,
    QSpinBox, QDoubleSpinBox, QLineEdit, QCheckBox, QSlider, QTabWidget, QGroupBox,
    QFileDialog, QDialog, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QInputDialog, QMenu)
import config
from data.chords import CHORD_QUALITIES, parse_chord_name
from data.notes import ROOT_NAMES
from data.scales import SCALE_NAMES
from data.arpeggios import ARPEGGIO_NAMES
from data.instrument import TUNINGS
from data.triads import TRIAD_VOICING_NAMES, TRIAD_QUALITIES
from data.progressions import MAJOR_PROGRESSIONS, MINOR_PROGRESSIONS
from audio.engine import TONE_GENERATORS
from services.composer import DEFAULTS, compose, normalize_settings, from_legacy
from services.documents import ExportJob
from services.storage import read_json, write_json, safe_filename, unique_path
from services.jobs import JobRunner
from gui.qt_theme import STYLE, icon
from gui.qt_canvas import DiagramCanvas, FingeringEditor

MODES = [('Chord','Chords'),('Scale','Scales'),('Arpeggio','Arpeggios'),('Triads','Triads'),
         ('Progression','Chord progressions'),('ScaleProg','Scale progressions'),('ArpProg','Arp. progressions'),
         ('ChordLookup','Voicing explorer'),('ChordID','Chord identifier')]


class SelectBox(QComboBox):
    """Use a crisp vector chevron on all platforms and display scale factors."""
    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#829078'),1.4))
        x,y=self.width()-17,self.height()//2
        p.drawLine(x-3,y-2,x,y+1); p.drawLine(x,y+1,x+3,y-2); p.end()


def label(text, role=None):
    w=QLabel(text)
    if role: w.setObjectName(role)
    return w


def button(text, callback, role=None):
    w=QPushButton(text)
    if role: w.setObjectName(role)
    w.setCursor(Qt.CursorShape.PointingHandCursor)
    w.clicked.connect(lambda checked=False: callback())
    return w


def validate_queue(value):
    if not isinstance(value,list): raise ValueError('Expected an export queue')
    for item in value:
        if not isinstance(item,dict) or not isinstance(item.get('render_spec'),dict) or not item.get('name'):
            raise ValueError('Invalid queued diagram')


def validate_lesson(value):
    if not isinstance(value,dict): raise ValueError('Invalid lesson')
    if value.get('version')==2:
        normalize_settings(value['editor'])
        validate_queue(value.get('queue',[]))
    elif value.get('version')==1:
        from services.documents import validate_project
        validate_project(value)
        validate_queue(value.get('queue',[]))
    else: raise ValueError('Unsupported lesson version')
    if 'custom_library' in value:
        from data.custom_library import _validate_library
        _validate_library(value['custom_library'])


class StudioWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Gemba Studio')
        self.resize(1460,940)
        self.setMinimumSize(1100,740)
        self.settings=deepcopy(DEFAULTS)
        self.image=None; self.snapshot=None; self.meta={}
        self.history=[]; self.redo_stack=[]; self.favorites=[]; self.queue=[]
        self.project_path=None; self.saved_settings=deepcopy(self.settings)
        self.jobs=JobRunner(); self.controls={}; self.nav={}; self._batch_cancelled=False
        self._loading_errors=[]
        try: self.queue=read_json(config.DATA_DIR/'queue.json',[],validate_queue)
        except (ValueError,OSError) as exc: self._loading_errors.append(str(exc))
        try:
            for item in read_json(config.DATA_DIR/'favorites.json',[]):
                try: self.favorites.append(dict(label=item.get('label','Saved diagram'),editor=from_legacy(item)))
                except (ValueError,TypeError,KeyError): self._loading_errors.append('A legacy favorite could not be migrated; the original file is preserved.')
            self.favorites=read_json(config.DATA_DIR/'qt-favorites.json',self.favorites)
        except (ValueError,OSError) as exc: self._loading_errors.append(str(exc))
        self.preview_timer=QTimer(self); self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(140); self.preview_timer.timeout.connect(self.refresh)
        self.poll_timer=QTimer(self); self.poll_timer.setInterval(50)
        self.poll_timer.timeout.connect(self.jobs.poll); self.poll_timer.start()
        self._build_ui(); self._build_menu(); self._build_inspector(); self.refresh()
        if self._loading_errors: self.statusBar().showMessage('  '.join(self._loading_errors))

    def _build_ui(self):
        root=QWidget(); root.setObjectName('Root'); self.setCentralWidget(root)
        outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        rail=QFrame(); rail.setObjectName('Rail'); rail.setFixedWidth(194)
        nav=QVBoxLayout(rail); nav.setContentsMargins(15,25,15,18); nav.setSpacing(4)
        brand=label('gemba.', 'Brand'); nav.addWidget(brand)
        nav.addWidget(label('DIAGRAM STUDIO', 'Section')); nav.addSpacing(33)
        nav.addWidget(label('CREATE', 'Section')); nav.addSpacing(8)
        for i,(mode,title) in enumerate(MODES):
            if i in (4,7): nav.addSpacing(18)
            b=button(title,lambda checked=False,m=mode:self.set_mode(m),'Nav')
            b.setCheckable(True); b.setIcon(icon(mode)); b.setIconSize(QSize(18,18))
            self.nav[mode]=b; nav.addWidget(b)
        nav.addStretch(1)
        nav.addWidget(button('Custom library',self.library_dialog,'Quiet'))
        nav.addWidget(button('Favorites & recent',self.saved_dialog,'Quiet'))
        self.queue_button=button(f'Export queue  ·  {len(self.queue)}',self.queue_dialog,'Quiet')
        nav.addWidget(self.queue_button)
        nav.addSpacing(14); nav.addWidget(label('Made for your next lesson.', 'Caption'))
        outer.addWidget(rail)
        workspace=QWidget(); main=QVBoxLayout(workspace); main.setContentsMargins(0,0,0,0); main.setSpacing(0)
        header=QFrame(); header.setObjectName('Header'); header.setFixedHeight(77)
        top=QHBoxLayout(header); top.setContentsMargins(25,12,25,12)
        heading=QVBoxLayout(); heading.setSpacing(3)
        self.lesson_label=label('Untitled lesson','PanelTitle'); heading.addWidget(self.lesson_label)
        heading.addWidget(label('A little theory. A lot of possibility.','Caption')); top.addLayout(heading); top.addStretch()
        top.addWidget(button('Open',self.open_project,'Quiet')); top.addWidget(button('Save lesson',self.save_project))
        self.export_button=button('Export  ↗',self.export_dialog,'Primary'); top.addWidget(self.export_button)
        main.addWidget(header)
        body=QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)
        center=QWidget(); center.setObjectName('Center'); content=QVBoxLayout(center)
        content.setContentsMargins(25,23,25,20); content.setSpacing(16)
        title_row=QHBoxLayout(); titles=QVBoxLayout(); titles.setSpacing(5)
        self.title_label=label('A minor 7','PageTitle'); self.title_label.setWordWrap(True); titles.addWidget(self.title_label)
        self.subtitle=label('Open voicing','Hint'); self.subtitle.setWordWrap(True); titles.addWidget(self.subtitle)
        title_row.addLayout(titles); title_row.addStretch()
        self.star_button=button('',self.favorite,'Quiet'); self.star_button.setIcon(icon('star')); self.star_button.setToolTip('Save this diagram to favorites')
        self.star_button.setFixedWidth(36); title_row.addWidget(self.star_button)
        self.undo_button=button('',self.undo,'Quiet'); self.undo_button.setIcon(icon('undo')); self.undo_button.setToolTip('Undo · Ctrl+Z')
        self.redo_button=button('',self.redo,'Quiet'); self.redo_button.setIcon(icon('redo')); self.redo_button.setToolTip('Redo · Ctrl+Shift+Z')
        for b in (self.star_button,self.undo_button,self.redo_button): b.setFixedWidth(34); b.setAccessibleName(b.toolTip())
        title_row.addWidget(self.undo_button); title_row.addWidget(self.redo_button); content.addLayout(title_row)
        self.canvas=DiagramCanvas(); content.addWidget(self.canvas,1)
        toolbar=QHBoxLayout(); toolbar.setSpacing(6)
        self.badge=label('CHORD DIAGRAM','Badge'); toolbar.addWidget(self.badge); toolbar.addStretch()
        guide=QCheckBox('Safe area'); guide.toggled.connect(self._guides); toolbar.addWidget(guide)
        toolbar.addSpacing(14)
        toolbar.addWidget(button('−',lambda:self.canvas.zoom_by(1/1.2),'Quiet'))
        self.fit_button=button('Fit',self.canvas.fit,'Quiet'); self.fit_button.setFixedWidth(65)
        self.canvas.zoomChanged.connect(self.fit_button.setText); toolbar.addWidget(self.fit_button)
        toolbar.addWidget(button('+',lambda:self.canvas.zoom_by(1.2),'Quiet')); content.addLayout(toolbar)
        transport=QFrame(); transport.setObjectName('Transport'); player=QHBoxLayout(transport)
        player.setContentsMargins(14,12,14,12); player.setSpacing(12)
        self.play_button=button('Listen',self.play,'Primary'); self.play_button.setIcon(icon('play','#ffffff')); player.addWidget(self.play_button)
        self.stop_button=button('Stop',self.cancel,'Quiet'); player.addWidget(self.stop_button)
        player.addWidget(label('TEMPO','Section')); self.tempo=QSpinBox(); self.tempo.setRange(20,400)
        self.tempo.setValue(self.settings['tempo']); self.tempo.setSuffix(' bpm'); self.tempo.setFixedWidth(102)
        self.tempo.valueChanged.connect(lambda v:self.change('tempo',v)); player.addWidget(self.tempo)
        player.addStretch(); player.addWidget(label('Volume','Caption'))
        self.volume=QSlider(Qt.Orientation.Horizontal); self.volume.setRange(0,100); self.volume.setValue(80)
        self.volume.setFixedWidth(80); self.volume.setAccessibleName('Playback volume')
        self.volume.valueChanged.connect(lambda v:self.change('volume',v)); player.addWidget(self.volume)
        content.addWidget(transport); body.addWidget(center,1)
        inspector=QFrame(); inspector.setObjectName('Inspector'); inspector.setFixedWidth(304)
        il=QVBoxLayout(inspector); il.setContentsMargins(19,23,19,12); il.setSpacing(14)
        il.addWidget(label('Make it yours','PanelTitle')); il.addWidget(label('Your diagram, down to the details.','Caption'))
        self.tabs=QTabWidget(); il.addWidget(self.tabs,1); body.addWidget(inspector)
        main.addLayout(body,1); outer.addWidget(workspace,1)
        self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.setFixedWidth(130); self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().addPermanentWidget(label('GEMBA STUDIO  /  0.4','Caption'))

    def _build_menu(self):
        for title,entries in [
            ('File',[('New lesson',self.new_project,'Ctrl+N'),('Open lesson…',self.open_project,'Ctrl+O'),
                     ('Save lesson',self.save_project,'Ctrl+S'),('Save lesson as…',lambda:self.save_project(True),'Ctrl+Shift+S'),
                     ('Export…',self.export_dialog,'Ctrl+E')]),
            ('Edit',[('Undo',self.undo,'Ctrl+Z'),('Redo',self.redo,'Ctrl+Shift+Z'),('Favorite this diagram',self.favorite,'Ctrl+D')]),
            ('Playback',[('Listen',self.play,'Ctrl+Space'),('Stop',self.cancel,'Esc')]),
            ('View',[('Fit canvas',self.canvas.fit,'Ctrl+0'),('Favorites and recent',self.saved_dialog,''),('Export queue',self.queue_dialog,'')]),
            ('Help',[('Open export folder',self.open_exports,''),('Instrument credits',self.instrument_credits,''),('Diagnostics',self.diagnostics,'')])]:
            menu=self.menuBar().addMenu(title)
            for name,callback,shortcut in entries:
                action=QAction(name,self); action.triggered.connect(callback)
                if shortcut: action.setShortcut(QKeySequence(shortcut))
                menu.addAction(action)

    def _page(self,title):
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        widget=QWidget(); widget.setObjectName('InspectorPage')
        layout=QVBoxLayout(widget); layout.setContentsMargins(0,15,5,15); layout.setSpacing(14)
        scroll.setWidget(widget); self.tabs.addTab(scroll,title)
        return layout

    def _field(self,layout,key,title,values=None,bounds=None):
        box=QVBoxLayout(); box.setSpacing(5); box.addWidget(label(title,'Hint'))
        if values is not None:
            w=SelectBox(); w.addItems([str(v) for v in values])
            w.setCurrentText(str(self.settings.get(key,'')))
            w.currentTextChanged.connect(lambda value,k=key:self.change(k,value))
        elif bounds:
            w=QDoubleSpinBox() if key=='duration' else QSpinBox(); w.setRange(*bounds)
            w.setValue(self.settings[key]); w.valueChanged.connect(lambda value,k=key:self.change(k,value))
        else:
            w=QLineEdit(str(self.settings.get(key,'')))
            w.editingFinished.connect(lambda k=key,widget=w:self.change(k,widget.text()))
        w.setAccessibleName(title); box.addWidget(w); layout.addLayout(box); self.controls[key]=w
        return w

    def _check(self,layout,key,title):
        w=QCheckBox(title); w.setChecked(self.settings[key]); w.toggled.connect(lambda value:self.change(key,value))
        layout.addWidget(w); self.controls[key]=w

    def _section(self,layout,title):
        g=QGroupBox(title); inner=QVBoxLayout(g); inner.setContentsMargins(0,9,0,0); inner.setSpacing(9)
        layout.addWidget(g); return inner

    def _build_inspector(self):
        active=max(0,self.tabs.currentIndex())
        while self.tabs.count():
            widget=self.tabs.widget(0); self.tabs.removeTab(0); widget.deleteLater()
        self.controls={}; s=self.settings; mode=s['mode']
        edit=self._page('Diagram')
        if mode in ('Chord','ChordLookup'):
            quick=QLineEdit(); quick.setPlaceholderText('Jump to a chord, e.g. F#m7'); quick.setAccessibleName('Find chord')
            quick.returnPressed.connect(lambda:self.quick_chord(quick.text())); edit.addWidget(quick)
        if mode!='ChordID': self._field(edit,'root','Root note',ROOT_NAMES)
        if mode in ('Chord','ChordLookup','Triads'):
            self._field(edit,'quality','Chord quality',TRIAD_QUALITIES if mode=='Triads' else CHORD_QUALITIES)
        if mode in ('Chord','ChordLookup'):
            self.voicing_combo=SelectBox(); self.voicing_combo.setAccessibleName('Voicing')
            edit.addWidget(label('Voicing','Hint')); edit.addWidget(self.voicing_combo)
            self.voicing_combo.currentIndexChanged.connect(lambda v:self.change('voicing',max(0,v)))
            edit.addWidget(button('Compare voicings',self.voicing_dialog))
        if mode in ('Scale','Arpeggio'):
            self._field(edit,'scale' if mode=='Scale' else 'arp','Scale' if mode=='Scale' else 'Arpeggio',SCALE_NAMES if mode=='Scale' else ARPEGGIO_NAMES)
            self._field(edit,'view','Fretboard view',['Position','Full fretboard']+(['3 notes per string'] if mode=='Scale' else []))
            self._field(edit,'position','Position',(None),bounds=(1,7 if mode=='Scale' else 5))
            self._check(edit,'invert','Reverse fretboard string order')
        if mode=='Triads':
            self._field(edit,'triad','String set / inversion',TRIAD_VOICING_NAMES)
            self._field(edit,'triad_scope','Show',['Single chord','Major key','Natural minor','Harmonic minor','Melodic minor'])
        if mode in ('Progression','ScaleProg','ArpProg'):
            self._field(edit,'progression','Progression',list(MAJOR_PROGRESSIONS)+list(MINOR_PROGRESSIONS))
            roman=self._field(edit,'roman','Or write your own'); roman.setPlaceholderText('I-V-vi-IV')
            self._field(edit,'key_mode','Custom progression key',['major','minor'])
            if mode!='ScaleProg': self._field(edit,'override','Quality override',['Auto']+(CHORD_QUALITIES if mode=='Progression' else ARPEGGIO_NAMES))
            if mode!='Progression': self._field(edit,'position','Position',bounds=(1,5))
            self._field(edit,'duration','Minimum seconds per panel',bounds=(.1,30))
            edit.addWidget(button('Playback per panel…',self.directions_dialog))
        if mode=='ChordID':
            hint=label('Click a fret to place a note. Click above a string to open or mute it.','Hint'); hint.setWordWrap(True); edit.addWidget(hint)
            editor=FingeringEditor(); editor.frets=list(s['frets']); editor.left_handed=s['left_handed']
            editor.changed.connect(lambda frets:self.change('frets',frets)); edit.addWidget(editor)
            row=QHBoxLayout(); row.addWidget(label('Starting fret','Hint')); start=QSpinBox(); start.setRange(1,20)
            start.valueChanged.connect(lambda v:(setattr(editor,'start',v),editor.update())); row.addWidget(start); edit.addLayout(row)
            self._field(edit,'custom_title','Custom chord title')
        instrument_group=self._section(edit,'Instrument')
        self._field(instrument_group,'tuning','Tuning',list(TUNINGS))
        self._field(instrument_group,'capo','Capo fret',bounds=(0,12)); self._check(instrument_group,'left_handed','Left-handed layout')
        edit.addStretch()
        style=self._page('Style')
        style.addWidget(label('Keep the music easy to read.','Hint'))
        from diagrams.style import THEMES
        self._field(style,'diagram_theme','Artwork theme',list(THEMES))
        self._field(style,'dot_label','Note labels',['note','finger','none'])
        for key,title in [('show_string_names','String names'),('show_finger_numbers','Finger numbers'),('show_barre','Barre markings'),('show_muted_x','Muted string symbols'),('show_open_o','Open string symbols')]:
            self._check(style,key,title)
        self._field(style,'barre_style','Barre shape',['arch','rect'])
        style.addWidget(label('Chord appearance controls apply to chord and triad diagrams.','Hint'))
        style.itemAt(style.count()-1).widget().setWordWrap(True)
        style.addWidget(button('Save settings preset…',self.save_preset)); style.addWidget(button('Load settings preset…',self.load_preset)); style.addStretch()
        audio=self._page('Sound')
        from audio.sampler import VOICES, ALIASES
        self.settings['tone']=ALIASES.get(self.settings['tone'],self.settings['tone'])
        self._field(audio,'tone','Recorded instrument',list(VOICES))
        note=label('Real instrument recordings, with a subtle stereo room.','Hint'); note.setWordWrap(True); audio.addWidget(note)
        self._field(audio,'play_style','Chord playback',['arpeggio','strum','arpeggio_strum'])
        self._field(audio,'direction','Strum direction',['down','up'])
        self._field(audio,'note_direction','Scale direction',['Asc','Desc','Asc + Desc'])
        self._check(audio,'root_to_root','Start and finish on the root'); self._check(audio,'high_e_root','Stop at the first high E-string root')
        shaping=self._section(audio,'Tone shaping')
        from audio.engine import TONE_SETTINGS
        for key,default in TONE_SETTINGS.items():
            shaping.addWidget(label(key.capitalize(),'Hint')); slider=QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0,100); slider.setValue(round(s['tone_settings'].get(key,default)*100)); slider.setAccessibleName(key)
            slider.valueChanged.connect(lambda value,k=key:self.change_tone(k,value/100)); shaping.addWidget(slider)
        audio.addStretch(); self.tabs.setCurrentIndex(min(active,2))
        for mode,b in self.nav.items(): b.setChecked(mode==s['mode'])

    def change_tone(self,key,value):
        settings=deepcopy(self.settings['tone_settings']); settings[key]=value; self.change('tone_settings',settings)

    def change(self,key,value):
        if self.settings.get(key)==value: return
        self.settings[key]=value
        if key in ('root','quality'): self.settings['voicing']=0
        if key in ('progression','roman','key_mode'): self.settings['panel_directions']=[]
        self.snapshot=None; self.play_button.setEnabled(False); self.export_button.setEnabled(False)
        self.preview_timer.start()

    def set_mode(self,mode):
        if mode==self.settings['mode']: return
        self.settings['mode']=mode; self.settings['override']='Auto'; self.settings['panel_directions']=[]
        if mode=='Triads' and self.settings['quality'] not in TRIAD_QUALITIES: self.settings['quality']='Major'
        if mode in ('Arpeggio','ScaleProg','ArpProg'): self.settings['position']=min(5,self.settings['position'])
        if mode=='Arpeggio' and self.settings['view']=='3 notes per string': self.settings['view']='Position'
        self.canvas.fit(); self._build_inspector(); self.refresh()

    def quick_chord(self,text):
        root,quality=parse_chord_name(text.strip())
        if root is None: self.statusBar().showMessage('Try a chord such as Am7, F#dim, or CM7.'); return
        root=next((r for r in ROOT_NAMES if root in r.split('/')),root)
        self.settings.update(root=root,quality=quality,voicing=0)
        self._build_inspector(); self.refresh()

    def refresh(self,record=True):
        self.preview_timer.stop()
        try:
            image,snap,meta=compose(self.settings)
            self.image,self.snapshot,self.meta=image,snap,meta
            self.canvas.set_image(image); self.title_label.setText(snap['name'])
            self.subtitle.setText(meta['detail']); self.badge.setText(dict(MODES)[self.settings['mode']].upper())
            if self.settings['mode'] in ('Chord','ChordLookup'):
                self.voicing_combo.blockSignals(True); self.voicing_combo.clear(); self.voicing_combo.addItems(meta['voicings'])
                self.voicing_combo.setCurrentIndex(min(self.settings['voicing'],len(meta['voicings'])-1)); self.voicing_combo.blockSignals(False)
            if record and (not self.history or self.history[-1]!=self.settings):
                self.history.append(deepcopy(self.settings)); self.history=self.history[-60:]; self.redo_stack.clear()
            self.statusBar().showMessage('Ready  ·  '+('  ·  '.join(dict.fromkeys(meta['notes'])) or 'Diagram updated'))
        except Exception as exc:
            self.snapshot=None
            logging.getLogger(__name__).exception('Diagram preview failed')
            self.statusBar().showMessage(str(exc)); self.subtitle.setText('Check the settings: '+str(exc))
        self.play_button.setEnabled(self.snapshot is not None and not self.jobs.busy)
        self.export_button.setEnabled(self.snapshot is not None and not self.jobs.busy)
        self.undo_button.setEnabled(len(self.history)>1); self.redo_button.setEnabled(bool(self.redo_stack))
        self.lesson_label.setText((self.project_path.name.removesuffix('.gemba.json') if self.project_path else 'Untitled lesson')+('  •' if self.settings!=self.saved_settings else ''))
        if self.settings['mode'] in ('Scale','Arpeggio'):
            self.controls['position'].setEnabled(self.settings['view']!='Full fretboard')
            self.controls['invert'].setEnabled(self.settings['view']=='Full fretboard')
        chord_style=self.settings['mode'] in ('Chord','ChordLookup','ChordID','Triads','Progression')
        for key in ('dot_label','show_barre','barre_style','show_string_names','show_finger_numbers','show_muted_x','show_open_o'):
            self.controls[key].setEnabled(chord_style)
        if self.settings['mode']=='ChordID':
            editor=self.findChild(FingeringEditor)
            if editor: editor.left_handed=self.settings['left_handed']; editor.update()

    def restore(self,settings,record=True):
        self.settings=normalize_settings(settings)
        self.tempo.blockSignals(True); self.tempo.setValue(self.settings['tempo']); self.tempo.blockSignals(False)
        self.volume.blockSignals(True); self.volume.setValue(self.settings['volume']); self.volume.blockSignals(False)
        self._build_inspector(); self.canvas.fit(); self.refresh(record)

    def undo(self):
        if self.preview_timer.isActive(): self.refresh()
        if len(self.history)>1:
            self.redo_stack.append(self.history.pop()); self.restore(self.history[-1],False)

    def redo(self):
        if self.redo_stack:
            state=self.redo_stack.pop(); self.history.append(deepcopy(state)); self.restore(state,False)

    def _guides(self,value):
        self.canvas.guides=value; self.canvas.update()

    def capture(self):
        if self.preview_timer.isActive(): self.refresh()
        if self.snapshot is None: raise ValueError('Choose valid diagram settings before exporting')
        return ExportJob.capture(self.snapshot)

    def _job(self,title,work,done=None,failed=None):
        if self.jobs.busy:
            self.statusBar().showMessage('A job is running. Stop it or wait for it to finish.'); return False
        self.progress.show(); self.statusBar().showMessage(title)
        self.play_button.setEnabled(False); self.export_button.setEnabled(False)
        def finish(result):
            self.progress.hide(); self.play_button.setEnabled(self.snapshot is not None); self.export_button.setEnabled(self.snapshot is not None)
            self.statusBar().showMessage('Complete'+(f'  ·  {result}' if result else ''))
            if done: done(result)
        def error(message):
            self.progress.hide(); self.play_button.setEnabled(self.snapshot is not None); self.export_button.setEnabled(self.snapshot is not None)
            self.statusBar().showMessage(message)
            if failed: failed(message)
        self.jobs.submit(work,finish,error); return True

    def play(self):
        try: job=self.capture()
        except ValueError as exc: self.statusBar().showMessage(str(exc)); return
        def work():
            from services.media import build_audio
            from audio.engine import play_audio
            from services.jobs import check_cancelled
            audio,_=build_audio(job.unpack()); check_cancelled(); play_audio(audio)
        self._job('Playing your diagram…',work)

    def cancel(self):
        self._batch_cancelled=True; self.jobs.cancel()
        from audio.engine import stop_audio
        stop_audio(); self.statusBar().showMessage('Stopping…')

    def export_dialog(self):
        if self.jobs.busy: return
        try: job=self.capture()
        except ValueError as exc: self.statusBar().showMessage(str(exc)); return
        dialog=QDialog(self); dialog.setWindowTitle('Export diagram'); dialog.setMinimumWidth(420)
        box=QVBoxLayout(dialog); box.setContentsMargins(25,25,25,25); box.setSpacing(16)
        box.addWidget(label('Ready to share.','PageTitle')); box.addWidget(label(job.unpack()['name'],'Hint'))
        form=QFormLayout(); fmt=QComboBox(); fmt.addItems(['PNG image','MP4 video','WAV audio','MP3 audio','MIDI','SVG vector','PDF print','PNG tablature'])
        res=QComboBox(); res.addItems(list(config.RESOLUTIONS)); res.setCurrentText(self.settings['resolution'])
        bg=QComboBox(); bg.addItems(['theme','transparent','navy']); bg.setCurrentText(self.settings['background'])
        portrait=QCheckBox('Portrait video · 9:16'); portrait.setChecked(self.settings['portrait'])
        tab=QCheckBox('Include tablature in video'); tab.setChecked(self.settings['with_tab'])
        form.addRow('Format',fmt); form.addRow('Image size',res); form.addRow('Background',bg); box.addLayout(form); box.addWidget(portrait); box.addWidget(tab)
        note=label('PNG size applies to images. PDF uses A4; video uses HD.','Hint'); note.setWordWrap(True); box.addWidget(note)
        credits=label('Audio and video include a sample-credit file for sharing.','Hint'); credits.setWordWrap(True); box.addWidget(credits)
        def enabled():
            res.setEnabled(fmt.currentText()=='PNG image'); bg.setEnabled(res.isEnabled())
            portrait.setEnabled(fmt.currentText()=='MP4 video'); tab.setEnabled(portrait.isEnabled())
        fmt.currentTextChanged.connect(enabled); enabled()
        def save():
            index=fmt.currentIndex(); ext=['png','mp4','wav','mp3','mid','svg','pdf','png'][index]
            path,_=QFileDialog.getSaveFileName(dialog,'Export diagram',str(config.OUTPUT_DIR/(safe_filename(job.unpack()['name'])+'.'+ext)),f'{fmt.currentText()} (*.{ext})')
            if not path: return
            if not Path(path).suffix: path+='.'+ext
            snapshot=job.unpack(); snapshot.update(portrait=portrait.isChecked(),with_tab=tab.isChecked())
            resolution,background=res.currentText(),bg.currentText()
            self.settings.update(resolution=resolution,background=background,portrait=portrait.isChecked(),with_tab=tab.isChecked())
            def work():
                return self.export_snapshot(snapshot,path,index,resolution,background)
            dialog.accept(); self._job('Exporting '+Path(path).name+'…',work)
        box.addWidget(button('Choose location & export',save,'Primary'))
        box.addWidget(button('Add video to queue',lambda:(self.add_queue(job.unpack(),portrait.isChecked(),tab.isChecked()),dialog.accept())))
        dialog.exec()

    @staticmethod
    def export_snapshot(snap,path,index,resolution='1080p',background='navy'):
        from services.media import build_audio, build_tab, export_video
        from services.formats import export_midi, export_print
        from services.documents import render_spec
        from diagrams.export import export_diagram
        from audio.engine import export_wav, export_mp3
        if index==0: return export_diagram(render_spec(snap['render_spec']),path,resolution,background)
        if index==1: return export_video(snap,path)
        if index in (2,3): return (export_wav if index==2 else export_mp3)(build_audio(snap)[0],path)
        if index==4: return export_midi(snap,path)
        if index in (5,6): return export_print(snap,path,'svg' if index==5 else 'pdf')
        Path(path).parent.mkdir(parents=True,exist_ok=True); build_tab(snap).save(path); return Path(path)

    def _persist_queue(self):
        try: write_json(config.DATA_DIR/'queue.json',self.queue,validate_queue)
        except (ValueError,OSError) as exc: self.statusBar().showMessage(str(exc)); return False
        self.queue_button.setText(f'Export queue  ·  {len(self.queue)}'); return True

    def add_queue(self,snap,portrait=False,tab=False):
        snap=deepcopy(snap); snap.update(id=str(uuid.uuid4()),portrait=portrait,with_tab=tab)
        self.queue.append(snap)
        if self._persist_queue(): self.statusBar().showMessage('Added to the video export queue')

    def queue_dialog(self):
        dialog=QDialog(self); dialog.setWindowTitle('Export queue'); dialog.resize(650,470)
        box=QVBoxLayout(dialog); box.addWidget(label('Your next exports','PageTitle'))
        box.addWidget(label('Successful videos leave the queue. Failed items stay here to retry.','Hint'))
        listing=QListWidget(); box.addWidget(listing,1)
        def refresh():
            listing.clear()
            for item in self.queue: listing.addItem(item['name']+('  ·  '+item['error'] if item.get('error') else '  ·  Ready'))
        def change(delta=None):
            if self.jobs.busy: return
            index=listing.currentRow()
            if index<0: return
            if delta is None: self.queue.pop(index)
            else:
                other=max(0,min(len(self.queue)-1,index+delta)); self.queue[index],self.queue[other]=self.queue[other],self.queue[index]; index=other
            self._persist_queue(); refresh(); listing.setCurrentRow(index)
        row=QHBoxLayout()
        for title,callback in [('Move up',lambda:change(-1)),('Move down',lambda:change(1)),('Remove',change)]: row.addWidget(button(title,callback))
        box.addLayout(row)
        box.addWidget(button('Export queued videos',lambda:self.export_queue(refresh),'Primary'))
        box.addWidget(button('Stop after cancelling current job',self.cancel,'Quiet')); refresh(); dialog.exec()

    def export_queue(self,refresh=lambda:None):
        if not self.queue or self.jobs.busy: return
        directory=QFileDialog.getExistingDirectory(self,'Choose export folder',str(config.OUTPUT_DIR))
        if not directory: return
        self._batch_cancelled=False; pending=list(self.queue); counts=[0,0]
        def update():
            try: refresh()
            except RuntimeError: pass  # The queue dialog may have closed while exporting.
        def next_item():
            if self._batch_cancelled or not pending:
                self.statusBar().showMessage(f'Queue finished: {counts[0]} exported, {counts[1]} failed. Unfinished items remain queued.'); return
            item=pending.pop(0); path=unique_path(Path(directory)/(safe_filename(item['name'])+'.mp4'))
            def done(result):
                self.queue=[v for v in self.queue if v is not item]; counts[0]+=1; self._persist_queue(); update(); next_item()
            def failed(error):
                item['error']=error; counts[1]+=1; self._persist_queue(); update(); next_item()
            captured=ExportJob.capture(item)
            self._job('Exporting '+item['name'],lambda:self.export_snapshot(captured.unpack(),path,1),done,failed)
        next_item()

    def save_project(self,save_as=False):
        path=self.project_path
        if path is None or save_as:
            name,_=QFileDialog.getSaveFileName(self,'Save lesson',str(path or config.OUTPUT_DIR/'Untitled.gemba.json'),'Gemba lesson (*.gemba.json)')
            if not name: return False
            path=Path(name if name.endswith('.json') else name+'.gemba.json')
        try:
            import data.custom_library as library
            write_json(path,dict(version=2,editor=self.settings,queue=self.queue,custom_library=library.load_raw()),validate_lesson)
            self.project_path=path; self.saved_settings=deepcopy(self.settings); self.refresh(False)
            self.statusBar().showMessage('Lesson saved  ·  '+str(path)); return True
        except (ValueError,OSError) as exc: self.statusBar().showMessage(str(exc)); return False

    def _can_discard(self):
        if self.settings==self.saved_settings: return True
        answer=QMessageBox.question(self,'Save your lesson?','Save your changes before continuing?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Save)
        return self.save_project() if answer==QMessageBox.StandardButton.Save else answer==QMessageBox.StandardButton.Discard

    def new_project(self):
        if not self._can_discard(): return
        self.project_path=None; self.saved_settings=deepcopy(DEFAULTS); self.history=[]; self.redo_stack=[]; self.restore(DEFAULTS)

    def open_project(self):
        if not self._can_discard(): return
        name,_=QFileDialog.getOpenFileName(self,'Open lesson',str(config.OUTPUT_DIR),'Gemba lesson (*.json)')
        if name: self.load_project(Path(name))

    def load_project(self,path):
        try:
            from services.projects import import_library
            project=read_json(path,None,validate_lesson); project=import_library(project)
            settings=project['editor'] if project['version']==2 else from_legacy(project['snapshot'])
            compose(settings)  # Verify the imported lesson before replacing the open editor.
            self.project_path=Path(path); self.saved_settings=normalize_settings(settings)
            self.history=[]; self.redo_stack=[]; self.restore(settings)
            # Merge saved exports so opening a lesson never discards the current queue.
            ids={q.get('id') for q in self.queue}
            for item in project.get('queue',[]):
                if not item.get('id') or item['id'] not in ids:
                    item.setdefault('id',str(uuid.uuid4())); self.queue.append(item); ids.add(item['id'])
            self._persist_queue(); self.statusBar().showMessage('Opened '+str(path)); return True
        except (ValueError,OSError,KeyError,TypeError) as exc: self.statusBar().showMessage(str(exc)); return False

    def favorite(self):
        if not self.snapshot: return
        item=dict(label=self.snapshot['name'],editor=deepcopy(self.settings))
        if item not in self.favorites: self.favorites.append(item)
        try: write_json(config.DATA_DIR/'qt-favorites.json',self.favorites)
        except (ValueError,OSError) as exc: self.statusBar().showMessage(str(exc)); return
        self.statusBar().showMessage('Saved to favorites')

    def saved_dialog(self):
        dialog=QDialog(self); dialog.setWindowTitle('Favorites & recent'); dialog.resize(550,500)
        layout=QVBoxLayout(dialog); layout.addWidget(label('Pick up where you left off.','PanelTitle'))
        tabs=QTabWidget(); layout.addWidget(tabs)
        for title,entries in [('Favorites',self.favorites),('Recent',[dict(label=dict(MODES)[v['mode']]+' / '+v['root'],editor=v) for v in reversed(self.history)])]:
            listing=QListWidget(); tabs.addTab(listing,title)
            for item in entries:
                row=QListWidgetItem(item['label']); row.setData(Qt.ItemDataRole.UserRole,item['editor']); listing.addItem(row)
            listing.itemDoubleClicked.connect(lambda item:(self.restore(item.data(Qt.ItemDataRole.UserRole)),dialog.accept()))
        layout.addWidget(label('Double-click a diagram to restore all its settings.','Hint')); dialog.exec()

    def save_preset(self):
        name,ok=QInputDialog.getText(self,'Save preset','Preset name')
        if not ok or not name.strip(): return
        try:
            path=config.DATA_DIR/'qt-presets.json'; presets=read_json(path,{})
            presets[name.strip()]=deepcopy(self.settings); write_json(path,presets); self.statusBar().showMessage('Preset saved')
        except (ValueError,OSError) as exc: self.statusBar().showMessage(str(exc))

    def load_preset(self):
        try:
            presets=read_json(config.DATA_DIR/'qt-presets.json',{})
            if not presets: self.statusBar().showMessage('Save a settings preset first.'); return
            name,ok=QInputDialog.getItem(self,'Load preset','Preset',list(presets),editable=False)
            if ok: self.restore(presets[name])
        except (ValueError,OSError) as exc: self.statusBar().showMessage(str(exc))

    def directions_dialog(self):
        if not self.meta.get('panels'): return
        dialog=QDialog(self); dialog.setWindowTitle('Playback per panel'); box=QVBoxLayout(dialog)
        form=QFormLayout(); boxes=[]
        choices=['Down','Up'] if self.settings['mode'] in ('Progression','Triads') else ['Asc','Desc','Asc + Desc']
        for i,title in enumerate(self.meta['panels']):
            w=QComboBox(); w.addItems(choices)
            dirs=self.settings['panel_directions']; w.setCurrentText(dirs[i] if i<len(dirs) else choices[0]); boxes.append(w); form.addRow(title,w)
        box.addLayout(form); box.addWidget(button('Apply',lambda:(self.change('panel_directions',[w.currentText() for w in boxes]),dialog.accept()),'Primary')); dialog.exec()

    def voicing_dialog(self):
        dialog=QDialog(self); dialog.setWindowTitle('Explore voicings'); dialog.resize(980,540)
        layout=QHBoxLayout(dialog)
        for i,title in enumerate(self.meta.get('voicings',[])):
            column=QVBoxLayout(); canvas=DiagramCanvas(); canvas.setMinimumWidth(210)
            state=deepcopy(self.settings); state['voicing']=i
            image,_,_=compose(state); canvas.set_image(image); column.addWidget(canvas,1)
            column.addWidget(button(title,lambda checked=False,index=i:(self.change('voicing',index),dialog.accept())))
            layout.addLayout(column)
        dialog.exec()

    def library_dialog(self):
        import data.custom_library as library
        from data.scales import SCALE_INTERVALS
        from data.arpeggios import ARPEGGIO_INTERVALS
        dialog=QDialog(self); dialog.setWindowTitle('Custom library'); dialog.resize(530,520)
        layout=QVBoxLayout(dialog); layout.addWidget(label('Build your own vocabulary.','PanelTitle'))
        listing=QListWidget(); layout.addWidget(listing,1)
        kind=QComboBox(); kind.addItems(['Scale','Arpeggio']); name=QLineEdit(); name.setPlaceholderText('Name')
        intervals=QLineEdit(); intervals.setPlaceholderText('Semitones, e.g. 0, 2, 4, 7, 9')
        layout.addWidget(kind); layout.addWidget(name); layout.addWidget(intervals); message=label('Root is 0. Enter unique semitones from 0 to 11.','Hint'); message.setWordWrap(True); layout.addWidget(message)
        def refresh():
            listing.clear()
            try:
                raw=library.load_raw()
                for k,entries in raw.items():
                    for n,values in entries.items():
                        item=QListWidgetItem(f'{n}  ·  {k}  ·  {values}'); item.setData(Qt.ItemDataRole.UserRole,(k,n)); listing.addItem(item)
            except (ValueError,OSError) as exc: message.setText(str(exc))
        def add():
            try:
                values=[int(v.strip()) for v in intervals.text().split(',')]
                if kind.currentIndex()==0: library.add_custom_scale(name.text(),values,SCALE_INTERVALS,SCALE_NAMES)
                else: library.add_custom_arpeggio(name.text(),values,ARPEGGIO_INTERVALS,ARPEGGIO_NAMES)
                refresh(); self._build_inspector(); message.setText('Saved to your library.')
            except (ValueError,OSError) as exc: message.setText(str(exc))
        def remove():
            if not listing.currentItem(): return
            k,n=listing.currentItem().data(Qt.ItemDataRole.UserRole)
            try:
                if k=='scales': library.delete_custom_scale(n,SCALE_INTERVALS,SCALE_NAMES)
                else: library.delete_custom_arpeggio(n,ARPEGGIO_INTERVALS,ARPEGGIO_NAMES)
                if self.settings['scale'] not in SCALE_NAMES: self.settings['scale']='Major'
                if self.settings['arp'] not in ARPEGGIO_NAMES: self.settings['arp']='Major'
                refresh(); self._build_inspector(); self.refresh()
            except (ValueError,OSError) as exc: message.setText(str(exc))
        layout.addWidget(button('Add to library',add,'Primary')); layout.addWidget(button('Remove selected',remove)); refresh(); dialog.exec()

    def diagnostics(self):
        from services.diagnostics import diagnostics
        QMessageBox.information(self,'Installation diagnostics',diagnostics())

    def instrument_credits(self):
        from audio.sampler import SAMPLE_DIR
        dialog=QMessageBox(self); dialog.setWindowTitle('Recorded instrument credits')
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText((SAMPLE_DIR/'ATTRIBUTION.md').read_text(encoding='utf-8')); dialog.exec()

    def open_exports(self):
        from PySide6.QtCore import QUrl
        config.OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(config.OUTPUT_DIR)))

    def closeEvent(self,event):
        if self.jobs.busy:
            answer=QMessageBox.question(self,'Job in progress','Cancel the current job and close?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes: event.ignore(); return
        if not self._can_discard(): event.ignore(); return
        self.cancel(); self.jobs.close(); self.poll_timer.stop(); event.accept()


def create_application():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('Gemba Studio'); app.setOrganizationName('GembaGuitar')
    app.setStyle('Fusion')
    for font in config.FONT_DIR.glob('*.ttf'): QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('DM Sans',10)); app.setStyleSheet(STYLE)
    return app


def run(smoke=False):
    app=create_application(); window=StudioWindow()
    if smoke:
        window.show(); app.processEvents()
        if not window.snapshot: raise RuntimeError('Startup diagram did not render')
        config.DATA_DIR.mkdir(parents=True,exist_ok=True)
        window.grab().save(str(config.DATA_DIR/'qt-smoke.png'))
        from services.media import build_audio
        from audio.engine import export_wav
        wave,_=build_audio(window.capture().unpack())
        if wave.ndim!=2 or wave.shape[1]!=2: raise RuntimeError('Recorded stereo audio did not render')
        export_wav(wave,config.DATA_DIR/'audio-smoke.wav')
        (config.DATA_DIR/'smoke-test.json').write_text(json.dumps({'gui':True,'snapshot':True,'framework':'Qt','recorded_audio':True,'channels':2}),encoding='utf-8')
        window.jobs.close(); window.saved_settings=deepcopy(window.settings); window.close(); return 0
    window.show()
    return app.exec()
