# Gemba Studio

A desktop workspace for guitar lessons: chord diagrams, scales, arpeggios,
triads, progressions, tablature, audio, and animated video. Version 0.4 combines the PySide6/Qt workspace with new diagram artwork and
recorded-instrument stereo playback.

## Run on Windows

Open `dist/refined/GembaStudio/GembaStudio.exe`. Keep the entire `GembaStudio` folder,
including `_internal`, together. Python, Qt, dependencies and fonts are bundled.
FFmpeg is a separate prerequisite for MP4 and MP3 export.

From source (Python 3.11+; tested on Windows with Python 3.14):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe studio.py
```

Optional legacy synthesis effects (the new recorded voices do not require these):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-audio.txt
```

The base installation includes SciPy resampling and 140 recorded samples.
Playback works offline; no sample downloads occur when using the app. Install FFmpeg and
add its `bin` directory to PATH; the app also detects common WinGet installations.

## Artwork and sound

Choose **Style > Artwork theme**:

- **Volt:** charcoal, electric lime roots and ice-blue notes.
- **Paper:** a light print-friendly surface with blue roots.
- **Prism:** deep violet with lilac roots and teal notes.

Chord cards, scale positions, full fretboards, arpeggios, triads, progressions and
tablature share the new flat design. Square markers identify roots independently
of color. Roman-numeral progression cards and active playback accents remain
coordinated across themes. PNG, PDF and video use the same renderers; SVG now
exports the same drawing geometry as real vectors with an embedded font. Choose
**theme** in the PNG background option to use the selected artwork's background;
**transparent** preserves transparent space around the fretboard panels.

Choose **Sound > Recorded instrument** for Studio Acoustic, Fingerstyle Nylon,
Clean Electric, Warm Jazz, Grand Piano, Felt Piano, Concert Harp, Tonewheel Organ,
or Ambient Guitar. These use actual recordings with band-limited pitch conversion,
string-aware note damping, smooth releases, subtle stereo placement and a room bus.
Original voice names in saved lessons/CLI commands map to the new instruments.
The former Bell and Pad options map to Concert Harp and Ambient Guitar.

The sample collection is CC BY 3.0. Audio/video export creates
`Gemba-instrument-credits.txt` alongside the output; include the credit when sharing
recordings. **Help > Instrument credits** shows the attribution. Source filenames,
checksums and the pinned upstream commit are in `audio/samples/manifest.json`.
The original recordings are single-layer samples, not a full articulations library.

## The redesigned workspace

- **Navigation rail:** chords, scales, arpeggios, triads, three progression modes,
  a voicing explorer, and an interactive chord identifier.
- **Canvas:** live diagram preview, drag to pan, Ctrl+scroll to zoom, Fit, and
  optional 5% safe-area guides. Guides never appear in exported artwork.
- **Inspector:** Diagram for musical settings and instrument setup, Style for
  chord appearance and saved presets, Sound for recorded voices, playback and tone shaping.
- **Playback bar:** Listen, Stop, tempo and volume. Tempo means one note per beat.
- **Export:** one dialog for PNG, MP4, WAV, MP3, MIDI, vector SVG, A4 PDF and PNG
  tablature. PNG offers landscape, portrait, square and print resolutions.
- **Library:** custom scales/arpeggios, favorites, recent diagrams and export queue.

Tuning supports Standard, Drop D, DADGAD and Open G, with capo and left-handed
layouts. Frets are relative to the capo; names describe sounding pitches.
Suggested alternate-tuning fingerings should be reviewed for the intended lesson.
The chord identifier supports six strings and connects directly to all export types.

Only one playback/export job runs at a time. Stop cancels background work. Failed
queue items remain available to retry; completed outputs remain saved. Opening a
lesson merges its saved queue with pending work instead of replacing the queue.

Keyboard shortcuts: Ctrl+N new lesson, Ctrl+O open, Ctrl+S save, Ctrl+Shift+S save
as, Ctrl+E export, Ctrl+Z undo, Ctrl+Shift+Z redo, Ctrl+D favorite, Ctrl+0 fit,
Ctrl+Space listen, Esc stop. Closing a changed lesson offers save/discard/cancel.

## Lessons and compatibility

Save lesson writes `.gemba.json` with the editor settings, custom definitions and
export queue. Qt writes version 2 lessons and imports version 1 lessons from the
previous interface. Conflicting custom definitions receive an import suffix.
Legacy favorites are imported when a Qt favorites file does not already exist.
Original files are preserved. New Qt lessons are not readable by the legacy UI.

For existing 4/5/7/8-string chord-identifier documents or the legacy identifier's
specialized layout controls, the old interface remains available:

```powershell
.\.venv\Scripts\python.exe studio.py --legacy-ui
# The packaged executable also accepts --legacy-ui.
```

The redesigned identifier uses six strings. It explicitly directs unsupported
legacy string counts to the old editor rather than silently changing them.

## Data and recovery

Libraries, queues, presets, favorites and logs live in
`%LOCALAPPDATA%/GembaGuitarStudio` on Windows. Default exports go to
`~/Documents/GembaGuitar Exports`. Override these with `GEMBA_DATA_DIR` and
`GEMBA_OUTPUT_DIR`. JSON writes are atomic and retain a last-good `.bak` file.
Corrupted files are reported and preserved rather than overwritten.

Use **Help > Diagnostics** for runtime/dependency information. Errors are recorded
in rotating `studio.log` files. Existing repository `custom_library.json` data is
read as a fallback until a user library has been saved.

## Command line

```powershell
python studio.py chord Am7 --png --audio
python studio.py scale F major --png --audio
python studio.py scale A pentatonic-minor --view box --position 1 --video
python studio.py arpeggio E major --png --video
python studio.py batch lesson.txt --png --audio
python studio.py --help
```

Batch files contain one chord, scale, arpeggio or progression command per line.
Lines beginning with # are comments; sharps in chord names are preserved. Failures
produce a nonzero exit status. CLI commands use standard tuning; saved lessons,
queues and instrument settings are desktop workflows.

## Development and packaging

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# Include legacy Tk GUI tests and actual legacy-to-Qt snapshot migration:
$env:GEMBA_GUI_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip install "pyinstaller>=6,<7" "ruff>=0.11,<1"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist/refined packaging/GembaStudio.spec
```

Qt tests run offscreen by default and exercise navigation, pending edits,
undo/redo, fingering clicks, project migration, queue failures, and real exports.
The music/media suite covers voicing correctness, positions, spelling, timing,
alpha compositing, storage recovery and cancellation.

`GembaStudio.exe --smoke-test` verifies Qt startup and stereo sample playback,
saves a window screenshot plus an audio preview, and writes `smoke-test.json` to
the configured data directory, then exits. Build from
an account able to read the Python runtime's Tcl/Tk installation for legacy mode.
The portable Windows application is unsigned, without an installer or updater.

Architecture: `data/` owns music theory/events, `diagrams/` renders artwork,
`audio/` renders recorded instruments (and retains legacy synthesizers), `services/` composes documents and manages jobs/storage,
`gui/qt_*` implements the new desktop, and `cli/` serves batch workflows. The
legacy Tk components remain in `gui/app.py`, `workflows.py` and `identifier.py`.
Qt license notices are in `packaging/licenses`; font licenses are in `fonts`.
