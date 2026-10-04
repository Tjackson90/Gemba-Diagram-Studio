"""Desktop project, job, history and export workflows."""
import json
import logging
from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import config
from services.jobs import JobRunner
from services.documents import ExportJob, render_spec, validate_project, validate_snapshots
from services.storage import read_json, write_json, safe_filename, unique_path
from services.media import build_audio, build_tab, export_video


class WorkflowMixin:
    def _init_workflows(self):
        self._jobs = JobRunner()
        self._restoring = False
        self._undo = []
        self._redo = []
        self._pending_status = ''
        self._queue_file = config.DATA_DIR / 'queue.json'
        self._preview_zoom = 1.
        self._preview_source = None
        self._preview_timer = None
        self.tuning_var = ctk.StringVar(value='Standard')
        self.capo_var = ctk.IntVar(value=0)
        self.left_handed_var = ctk.BooleanVar(value=False)

    def _start_workflows(self):
        menu = tk.Menu(self)
        project = tk.Menu(menu, tearoff=False)
        project.add_command(label='Open lesson...', command=self._open_project, accelerator='Ctrl+O')
        project.add_command(label='Save lesson...', command=self._save_project, accelerator='Ctrl+Shift+S')
        project.add_command(label='Export MIDI...', command=self._save_midi)
        project.add_command(label='Export PDF...', command=lambda: self._save_document_format('pdf'))
        project.add_command(label='Export SVG...', command=lambda: self._save_document_format('svg'))
        project.add_separator()
        project.add_command(label='Manage export queue...', command=self._manage_queue)
        project.add_command(label='Cancel current job', command=self._cancel_job)
        project.add_command(label='Diagnostics', command=self._diagnostics)
        menu.add_cascade(label='Project', menu=project)
        edit = tk.Menu(menu, tearoff=False)
        edit.add_command(label='Undo', command=self._undo_edit, accelerator='Ctrl+Z')
        edit.add_command(label='Redo', command=self._redo_edit, accelerator='Ctrl+Y')
        menu.add_cascade(label='Edit', menu=edit)
        view = tk.Menu(menu, tearoff=False)
        view.add_command(label='Fit preview', command=lambda: self._zoom_preview(0))
        view.add_command(label='Zoom in', command=lambda: self._zoom_preview(1.25))
        view.add_command(label='Zoom out', command=lambda: self._zoom_preview(.8))
        view.add_command(label='Export framing preview', command=self._preview_export)
        menu.add_cascade(label='View', menu=view)
        presets = tk.Menu(menu, tearoff=False)
        for label, resolution, background in [('YouTube landscape','1080p','navy'),
                ('YouTube Shorts','Shorts','navy'), ('Transparent overlay','4K','transparent'),
                ('Print A4','Print A4','navy')]:
            presets.add_command(label=label, command=lambda r=resolution,b=background: self._apply_preset(r,b))
        menu.add_cascade(label='Presets', menu=presets)
        instrument_menu = tk.Menu(menu, tearoff=False)
        from data.instrument import TUNINGS
        for name in TUNINGS:
            instrument_menu.add_radiobutton(label=name, variable=self.tuning_var, value=name,
                                            command=self._instrument_changed)
        capo = tk.Menu(instrument_menu, tearoff=False)
        for fret in range(13):
            capo.add_radiobutton(label=str(fret), variable=self.capo_var, value=fret,
                                 command=self._instrument_changed)
        instrument_menu.add_cascade(label='Capo (frets shown relative to capo)', menu=capo)
        instrument_menu.add_checkbutton(label='Left-handed layout', variable=self.left_handed_var,
                                       command=self._instrument_changed)
        menu.add_cascade(label='Instrument', menu=instrument_menu)
        self.configure(menu=menu)
        self.bind_all('<Control-o>', lambda e: self._open_project())
        self.bind_all('<Control-Shift-S>', lambda e: self._save_project())
        self.bind_all('<Control-z>', lambda e: self._undo_edit())
        self.bind_all('<Control-y>', lambda e: self._redo_edit())
        self.protocol('WM_DELETE_WINDOW', self._close_app)
        try:
            self._batch_queue = read_json(self._queue_file, [], self._validate_queue)
        except ValueError as exc:
            self._set_status(str(exc))
        self._update_queue_label()
        self.after(80, self._poll_jobs)
        self._undo = [self._snapshot()]
        if self._pending_status:
            self._set_status(self._pending_status)

    def _poll_jobs(self):
        try:
            self._jobs.poll()
        finally:
            self.after(80, self._poll_jobs)

    def _run_job(self, label, work, done=None):
        if self._jobs.busy:
            self._set_status('A job is running; cancel it or wait for completion.')
            return
        self._show_progress()
        self._set_status(label)
        def finished(result):
            self._hide_progress()
            if done:
                done(result)
            else:
                self._set_status(f'Saved: {result}')
        def failed(error):
            self._hide_progress()
            self._set_status(error)
        self._jobs.submit(work, finished, failed)

    def _cancel_job(self):
        self._jobs.cancel()
        from audio.engine import stop_audio
        stop_audio()
        self._set_status('Cancelling...')

    def _close_app(self):
        self._cancel_job()
        self._jobs.close()
        self.destroy()

    def _set_status(self, text):
        if hasattr(self, 'status_label'):
            self.status_label.configure(text=text)
        else:
            self._pending_status = text
        if 'error' in text.lower():
            logging.getLogger(__name__).error(text)

    def _capture_job(self):
        if self._preview_timer is not None:
            self.after_cancel(self._preview_timer)
            self._preview_timer = None
            self._set_mode(self.mode_var.get())
        snapshot = self._snapshot_current_state()
        if not snapshot or not snapshot.get('render_spec'):
            raise ValueError('Generate a diagram first')
        return ExportJob.capture(snapshot)

    def _play_audio(self):
        try:
            job = self._capture_job()
        except ValueError as exc:
            self._set_status(str(exc)); return
        def work():
            from audio.engine import play_audio
            audio, _ = build_audio(job.unpack())
            from services.jobs import check_cancelled
            check_cancelled()
            play_audio(audio)
        self._run_job('Playing...', work, lambda _: self._set_status('Playback complete'))

    def _stop_audio(self):
        self._cancel_job()

    def _export_audio(self, fmt):
        try:
            job = self._capture_job()
        except ValueError as exc:
            self._set_status(str(exc)); return
        path = filedialog.asksaveasfilename(title='Save audio', defaultextension='.'+fmt,
            initialfile=safe_filename(self._current_name)+'.'+fmt,
            filetypes=[(fmt.upper(), '*.'+fmt)])
        if not path:
            return
        def work():
            from audio.engine import export_wav, export_mp3
            audio, _ = build_audio(job.unpack())
            return (export_wav if fmt == 'wav' else export_mp3)(audio, path)
        self._run_job('Exporting audio...', work)

    def _export_size(self):
        width, height = self.custom_w_var.get().strip(), self.custom_h_var.get().strip()
        if width or height:
            return config.validate_size(int(width), int(height))
        return config.RESOLUTIONS[self.res_var.get()]

    def _save_png_as(self):
        try:
            job = self._capture_job()
            target = self._export_size()
        except (ValueError, KeyError) as exc:
            self._set_status(str(exc)); return
        background = self.bg_var.get()
        path = filedialog.asksaveasfilename(title='Save PNG', defaultextension='.png',
            initialfile=safe_filename(self._current_name)+'.png', filetypes=[('PNG', '*.png')])
        if not path:
            return
        def work():
            from diagrams.export import export_diagram
            image = render_spec(job.unpack()['render_spec'], target)
            return export_diagram(image, path, background=background, custom_size=target)
        self._run_job('Rendering export...', work)

    def _export_all(self):
        try:
            job = self._capture_job()
        except ValueError as exc:
            self._set_status(str(exc)); return
        directory = filedialog.askdirectory(title='Export all sizes')
        if not directory:
            return
        def work():
            from diagrams.export import export_diagram
            from services.jobs import check_cancelled
            snap = job.unpack()
            paths = []
            for label, size in config.RESOLUTIONS.items():
                check_cancelled()
                image = render_spec(snap['render_spec'], size)
                for bg in ('transparent', 'navy'):
                    path = unique_path(Path(directory)/(safe_filename(snap['name'])+f'_{label}_{bg}.png'))
                    paths.append(export_diagram(image, path, background=bg, custom_size=size))
            return paths
        self._run_job('Rendering all sizes...', work,
                      lambda paths: self._set_status(f'Saved {len(paths)} images in {directory}'))

    def _save_video_as(self):
        try:
            job = self._capture_job()
        except ValueError as exc:
            self._set_status(str(exc)); return
        path = filedialog.asksaveasfilename(title='Save video', defaultextension='.mp4',
            initialfile=safe_filename(self._current_name)+'.mp4', filetypes=[('MP4', '*.mp4')])
        if path:
            self._run_job('Rendering video...', lambda: export_video(job.unpack(), path))

    def _preview_tab(self):
        try:
            job = self._capture_job()
        except ValueError as exc:
            self._set_status(str(exc)); return
        self._run_job('Rendering tab...', lambda: build_tab(job.unpack()),
                      lambda image: self._show_preview(image))

    def _save_tab_as(self):
        try:
            job = self._capture_job()
        except ValueError as exc:
            self._set_status(str(exc)); return
        path = filedialog.asksaveasfilename(title='Save tab', defaultextension='.png',
            initialfile=safe_filename(self._current_name)+'_tab.png', filetypes=[('PNG','*.png')])
        if path:
            def work():
                build_tab(job.unpack()).save(path)
                return path
            self._run_job('Rendering tab...', work)

    @staticmethod
    def _validate_queue(value):
        if not isinstance(value, list):
            raise ValueError('Invalid queue')
        for item in value:
            if not isinstance(item, dict) or not isinstance(item.get('name'), str) or 'render_spec' not in item:
                raise ValueError('Invalid queued export')

    def _persist_queue(self):
        try:
            write_json(self._queue_file, self._batch_queue, self._validate_queue)
        except (OSError, ValueError) as exc:
            self._set_status(str(exc))
        self._update_queue_label()

    def _update_queue_label(self):
        self._batch_export_btn.configure(text=f'Export Queue ({len(self._batch_queue)})')

    def _add_to_batch_queue(self):
        try:
            snap = self._capture_job().unpack()
        except ValueError as exc:
            self._set_status(str(exc)); return
        import uuid
        snap['id'] = str(uuid.uuid4())
        self._batch_queue.append(snap)
        self._persist_queue()
        self._set_status(f'Queued {snap["name"]}')

    def _clear_batch_queue(self):
        if self._jobs.busy:
            self._set_status('Wait for the current job before clearing the queue'); return
        self._batch_queue.clear()
        self._persist_queue()

    def _export_batch_queue(self):
        if not self._batch_queue or self._jobs.busy:
            self._set_status('Queue is empty or a job is already running'); return
        directory = filedialog.askdirectory(title='Export queue to folder')
        if not directory:
            return
        self._batch_results = {'saved': 0, 'failed': 0}
        pending = list(self._batch_queue)
        def next_item():
            if not pending:
                counts = self._batch_results
                self._set_status(f'Batch complete: {counts["saved"]} saved, {counts["failed"]} failed; failures remain queued')
                return
            snap = pending.pop(0)
            path = unique_path(Path(directory)/(safe_filename(snap['name'])+'.mp4'))
            self._show_progress()
            self._set_status(f'Exporting {snap["name"]} ({len(pending)} remaining)')
            def done(result):
                self._hide_progress()
                self._batch_results['saved'] += 1
                self._batch_queue = [s for s in self._batch_queue if s.get('id') != snap.get('id')]
                self._persist_queue()
                next_item()
            def failed(error):
                self._hide_progress()
                self._batch_results['failed'] += 1
                for item in self._batch_queue:
                    if item.get('id') == snap.get('id'):
                        item['error'] = error
                self._persist_queue()
                if self._jobs.cancel_event.is_set():
                    self._set_status('Batch cancelled; unfinished items remain queued')
                else:
                    next_item()
            job = ExportJob.capture(snap)
            self._jobs.submit(lambda: export_video(job.unpack(), path), done, failed)
        next_item()

    def _manage_queue(self):
        window = ctk.CTkToplevel(self)
        window.title('Export queue')
        window.geometry('650x420')
        listing = tk.Listbox(window, bg=config.HEX_NAVY_DEEP, fg=config.HEX_CREAM)
        listing.pack(fill='both', expand=True, padx=12, pady=12)
        def refresh():
            listing.delete(0, 'end')
            for item in self._batch_queue:
                listing.insert('end', item['name'] + (' - '+item['error'] if item.get('error') else ''))
        def change(delta=None):
            if self._jobs.busy or not listing.curselection():
                return
            index = listing.curselection()[0]
            if delta is None:
                self._batch_queue.pop(index)
            else:
                other = max(0, min(len(self._batch_queue)-1, index+delta))
                self._batch_queue[index], self._batch_queue[other] = self._batch_queue[other], self._batch_queue[index]
            self._persist_queue(); refresh()
        for label, callback in [('Move up',lambda: change(-1)),('Move down',lambda: change(1)),
                                ('Remove',change),('Export / retry',self._export_batch_queue)]:
            ctk.CTkButton(window, text=label, command=callback).pack(side='left', padx=5, pady=8)
        refresh()

    def _snapshot(self):
        variables = {name: value.get() for name, value in vars(self).items()
                     if isinstance(value, tk.Variable)}
        directions = {name: [v.get() for v in getattr(self, name, [])]
                      for name in ('_prog_dir_vars','_scale_prog_dir_vars','_arp_prog_dir_vars')}
        return dict(version=1, mode=self.mode_var.get(), label=self._current_name or self.mode_var.get(),
                    variables=variables, directions=directions,
                    identifier=dict(fingers=deepcopy(self._ci_fingers), open_muted=list(self._ci_open_muted),
                        strings=self._ci_strings, frets_visible=self._ci_frets_visible,
                        start_fret=self._ci_start_fret, orientation=self._ci_orientation),
                    lookup=dict(root=self._cl_root, quality=self._cl_qual))

    def _restore_snapshot(self, snap):
        if 'variables' not in snap:
            return self._restore_legacy_snapshot(snap)
        self._restoring = True
        try:
            for name, value in snap['variables'].items():
                variable = vars(self).get(name)
                if isinstance(variable, tk.Variable):
                    variable.set(value)
            for name, value in snap.get('identifier', {}).items():
                if name in ('fingers','open_muted','strings','frets_visible','start_fret','orientation'):
                    setattr(self, '_ci_'+name, deepcopy(value))
            self._cl_root = snap.get('lookup', {}).get('root', 'A')
            self._cl_qual = snap.get('lookup', {}).get('quality', 'Major')
            from data.instrument import set_instrument
            set_instrument(self._instrument_settings())
            self._set_mode(snap['mode'])
            for name, values in snap.get('directions', {}).items():
                for variable, value in zip(getattr(self, name, []), values):
                    variable.set(value)
        finally:
            self._restoring = False

    def _record_history(self, snapshot):
        if self._restoring:
            return
        if not self._history or self._history[0] != snapshot:
            self._history.insert(0, deepcopy(snapshot))
            self._history = self._history[:self._MAX_HISTORY]
            if hasattr(self, '_history_list_frame'):
                self._refresh_history_panel()
        if not self._undo or self._undo[-1] != snapshot:
            self._undo.append(deepcopy(snapshot))
            self._undo = self._undo[-50:]
            self._redo.clear()

    def _undo_edit(self):
        if len(self._undo) > 1:
            self._redo.append(self._undo.pop())
            self._restore_snapshot(self._undo[-1])

    def _redo_edit(self):
        if self._redo:
            snap = self._redo.pop()
            self._undo.append(snap)
            self._restore_snapshot(snap)

    def _load_favorites(self):
        source = self._favorites_file
        if not source.exists():
            source = config.PROJECT_ROOT/'output'/'favorites.json'
        try:
            return read_json(source, [], validate_snapshots)
        except ValueError as exc:
            self._set_status(str(exc))
            return []

    def _save_favorites(self):
        try:
            write_json(self._favorites_file, self._favorites, validate_snapshots)
        except (OSError, ValueError) as exc:
            self._set_status(str(exc))

    def _save_project(self):
        path = filedialog.asksaveasfilename(title='Save lesson project', defaultextension='.gemba.json',
            filetypes=[('Gemba lesson', '*.gemba.json')])
        if path:
            try:
                import data.custom_library as library
                write_json(path, dict(version=1, snapshot=self._snapshot(), queue=self._batch_queue,
                                      custom_library=library.load_raw()), validate_project)
                self._set_status(f'Lesson saved: {path}')
            except (OSError, ValueError) as exc:
                self._set_status(str(exc))

    def _open_project(self):
        path = filedialog.askopenfilename(title='Open lesson project', filetypes=[('Gemba lesson','*.json')])
        if path:
            try:
                project = read_json(path, None, validate_project)
                self._validate_queue(project['queue'])
                from services.projects import import_library
                project = import_library(project)
                self._restore_snapshot(project['snapshot'])
                self._batch_queue = project['queue']
                self._persist_queue()
                self._set_status(f'Lesson opened: {path}')
            except (OSError, ValueError, KeyError) as exc:
                self._set_status(str(exc))

    def _apply_preset(self, resolution, background):
        self.res_var.set(resolution)
        self.bg_var.set(background)
        self.custom_w_var.set(''); self.custom_h_var.set('')
        self.video_portrait_var.set(resolution == 'Shorts')
        self._set_status(f'Preset: {resolution}, {background}')

    def _zoom_preview(self, factor):
        self._preview_zoom = 1. if factor == 0 else max(.25, min(4., self._preview_zoom*factor))
        if self._preview_source is not None:
            self._show_preview(self._preview_source)

    def _preview_export(self):
        try:
            job, size, background = self._capture_job(), self._export_size(), self.bg_var.get()
        except ValueError as exc:
            self._set_status(str(exc)); return
        def work():
            from PIL import Image, ImageDraw
            target = (max(64, round(size[0]*min(900/size[0],650/size[1]))),
                      max(64, round(size[1]*min(900/size[0],650/size[1]))))
            image = render_spec(job.unpack()['render_spec'], target)
            canvas = Image.new('RGBA', target, config.NAVY_DEEP+(255,))
            canvas.alpha_composite(image, ((target[0]-image.width)//2,(target[1]-image.height)//2))
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((target[0]*.05,target[1]*.05,target[0]*.95,target[1]*.95), outline=config.GOLD, width=1)
            return canvas
        self._run_job('Rendering framing preview...', work, self._show_preview)

    def _save_midi(self):
        try:
            job = self._capture_job()
        except ValueError as exc:
            self._set_status(str(exc)); return
        path = filedialog.asksaveasfilename(title='Export MIDI', defaultextension='.mid', filetypes=[('MIDI','*.mid')])
        if path:
            from services.formats import export_midi
            self._run_job('Exporting MIDI...', lambda: export_midi(job.unpack(), path))

    def _save_document_format(self, fmt):
        try:
            job = self._capture_job()
        except ValueError as exc:
            self._set_status(str(exc)); return
        path = filedialog.asksaveasfilename(title='Export '+fmt.upper(), defaultextension='.'+fmt,
                                          filetypes=[(fmt.upper(), '*.'+fmt)])
        if path:
            from services.formats import export_print
            self._run_job('Exporting '+fmt.upper(), lambda: export_print(job.unpack(), path, fmt))

    def _diagnostics(self):
        from services.diagnostics import diagnostics
        messagebox.showinfo('Diagnostics', diagnostics())

    def _instrument_settings(self):
        return dict(tuning=self.tuning_var.get(), capo=self.capo_var.get(),
                    left_handed=self.left_handed_var.get())

    def _instrument_changed(self):
        from data.instrument import set_instrument
        set_instrument(self._instrument_settings())
        self._set_mode(self.mode_var.get())

    def _schedule_preview(self, mode):
        if self._preview_timer is not None:
            self.after_cancel(self._preview_timer)
        def update():
            self._preview_timer = None
            if self.mode_var.get() == mode:
                self._set_mode(mode)
        self._preview_timer = self.after(100, update)
