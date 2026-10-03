# GembaGuitar Diagram Studio

A local desktop tool for generating branded chord diagrams, scale diagrams, and audio files for the GembaGuitar YouTube channel.

## Quick Start

### 1. Install Python 3.11+
Download from [python.org](https://www.python.org/downloads/). During install, **check "Add Python to PATH"**.

### 2. Install Dependencies
Open a terminal in this folder and run:
```bash
pip install -r requirements.txt
```

### 3. Install Fonts
Download these Google Fonts and place the `.ttf` files in the `fonts/` folder:
- **Bebas Neue**: https://fonts.google.com/specimen/Bebas+Neue → download `BebasNeue-Regular.ttf`
- **DM Sans**: https://fonts.google.com/specimen/DM+Sans → download `DMSans-Regular.ttf` and `DMSans-Bold.ttf`

### 4. Install FFmpeg (for MP3 export)
- Download from [ffmpeg.org](https://ffmpeg.org/download.html)
- Extract and add the `bin` folder to your system PATH
- Or install via: `winget install ffmpeg` (Windows) / `brew install ffmpeg` (Mac)

### 5. Launch
```bash
python studio.py
```
This opens the GUI. Or use CLI commands (see below).

---

## GUI Features

- **Chord Mode**: Select root + quality or type a chord name directly (e.g., `Am7`, `F#dim`)
- **Scale Mode**: Select root + scale type, choose Full Fretboard or Position 1-5
- **Live Preview**: See the diagram before exporting
- **Audio**: Play chord strums or scale runs with 3 tone options (acoustic, electric, sine)
- **Export**: PNG (transparent or navy background) at 1080p, 4K, Square, or Square 4K
- **Audio Export**: WAV and MP3 files ready to drop into CapCut

---

## CLI Usage

### Single Chord
```bash
python studio.py chord Am7 --png --audio
python studio.py chord "F#" --png --res 4K --bg navy
python studio.py chord Cmaj7 --png --audio --tone electric --mp3
```

### Single Scale
```bash
python studio.py scale A pentatonic-minor --view full --png
python studio.py scale E blues --view box --position 3 --png --audio
python studio.py scale G major --png --res 4K --bg navy
```

### Batch Mode
Create a text file (one chord per line):
```
Am
C
G
F
Dm
Em
```
Then run:
```bash
python studio.py batch my_chords.txt --png --audio
```

---

## Output

All files are saved to the `output/` folder:
```
output/
├── chords/    ← Chord diagram PNGs
├── scales/    ← Scale diagram PNGs
└── audio/     ← WAV and MP3 files
```

---

## Supported Chords

12 roots × 10 qualities = 120 chords, each with up to 3 voicings:

**Roots:** C, C#/Db, D, D#/Eb, E, F, F#/Gb, G, G#/Ab, A, A#/Bb, B

**Qualities:** Major, Minor, 7th, Maj7, Min7, Sus2, Sus4, Dim, Aug, Add9

---

## Supported Scales

All 12 roots × 12 scale types:

- Pentatonic Minor / Major
- Major (Ionian)
- Natural Minor (Aeolian)
- Blues
- Dorian, Phrygian, Lydian, Mixolydian, Locrian
- Harmonic Minor
- Melodic Minor

Each with Full Fretboard view + 5 CAGED box positions.

---

## Brand

All diagrams use the GembaGuitar brand:
- Navy: `#0b1e3d`, `#122a52`, `#1a3a6e`
- Gold: `#c9a84c`, `#e8c96a`
- Cream: `#f5f0e8`
- Fonts: Bebas Neue (titles), DM Sans (labels)
- Watermark: "GembaGuitar.com" on all exports
