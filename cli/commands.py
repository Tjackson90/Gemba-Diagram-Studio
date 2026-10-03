"""
CLI interface — generate diagrams and audio from the command line.

Usage:
    python studio.py chord Am7 --png --audio
    python studio.py chord "F#" --png --res 4K --bg navy
    python studio.py scale A pentatonic-minor --view full --png
    python studio.py scale E blues --view box --position 1 --png --audio
    python studio.py batch chords.txt --png --audio
    python studio.py gui   (launches the GUI)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from data.chords import parse_chord_name, get_voicings, get_chord_display_name, CHORD_QUALITIES
from data.notes import note_name_to_semitone, ROOT_NAMES
from data.scales import (
    SCALE_NAMES, get_full_fretboard_scale, get_caged_positions,
    get_scale_display_name, get_scale_interval_labels,
    get_three_note_per_string_scale,
)
from data.progressions import (
    PROGRESSION_NAMES, get_named_progression, get_progression_chords, parse_roman,
)
from diagrams.progression_diagram import render_progression_strip, make_progression_title
from data.arpeggios import (
    ARPEGGIO_NAMES, get_full_fretboard_arpeggio, get_arpeggio_positions,
    get_arpeggio_display_name,
)
from diagrams.chord_diagram import render_chord_diagram
from diagrams.scale_diagram import render_scale_full_fretboard, render_scale_box
from diagrams.export import export_diagram
from diagrams.tab_diagram import render_chord_tab, render_scale_tab
from diagrams.video_export import export_chord_video, export_scale_video, export_progression_video
from audio.engine import generate_chord_audio, generate_scale_audio, generate_progression_audio, export_wav, export_mp3


def _normalize_scale_name(raw):
    """Convert CLI scale name to proper name. e.g., 'pentatonic-minor' -> 'Pentatonic Minor'"""
    normalized = raw.replace("-", " ").replace("_", " ").title()
    # Find best match
    for name in SCALE_NAMES:
        if name.lower() == normalized.lower():
            return name
    # Partial match
    for name in SCALE_NAMES:
        if normalized.lower() in name.lower():
            return name
    return normalized


def cmd_chord(args):
    """Generate a chord diagram."""
    chord_str = " ".join(args.chord_name)
    root, quality = parse_chord_name(chord_str)

    if root is None:
        print(f"Error: Could not parse chord '{chord_str}'")
        print(f"Examples: Am7, F#dim, Cmaj7, Dsus4, Bb7")
        return

    voicings = get_voicings(root, quality)
    if not voicings:
        print(f"Error: No voicings found for {root} {quality}")
        return

    voicing_idx = min(args.voicing - 1, len(voicings) - 1)
    v = voicings[voicing_idx]
    chord_name = get_chord_display_name(root, quality)
    root_semi = note_name_to_semitone(root)

    print(f"Generating: {chord_name} — {v['label']}")
    print(f"  Frets: {v['frets']}")

    # Render
    bg_color = config.NAVY_DEEP if args.bg == "navy" else None
    img = render_chord_diagram(
        frets=v["frets"],
        fingers=v.get("fingers"),
        chord_name=chord_name,
        root_semitone=root_semi,
        bg_color=bg_color,
        width=600,
        height=800,
        dot_label=getattr(args, "dot_label", "note"),
        show_muted_x=not getattr(args, "no_muted_x", False),
        show_open_o=not getattr(args, "no_open_o", False),
        show_string_names=not getattr(args, "no_string_names", False),
        show_finger_numbers=not getattr(args, "no_finger_numbers", False),
        show_barre=not getattr(args, "no_barre", False),
    )

    if args.png:
        output_dir = Path(args.output) / "chords"
        filename = f"{chord_name}_{args.res}_{args.bg}.png"
        path = export_diagram(img, output_dir / filename, args.res, args.bg)
        print(f"  PNG saved: {path}")

    if args.audio or getattr(args, "video", False):
        raw_style = getattr(args, "play_style", "strum")
        strum_dir = "up" if raw_style == "strum_up" else "down"
        play_style = "strum" if raw_style in ("strum", "strum_up", "strum_down") else raw_style
        audio = generate_chord_audio(
            v["frets"], tone=args.tone,
            play_style=play_style, strum_direction=strum_dir,
        )
        if args.audio:
            output_dir = Path(args.output) / "audio"
            wav_path = export_wav(audio, output_dir / f"{chord_name}.wav")
            if wav_path:
                print(f"  WAV saved: {wav_path}")
            if args.mp3:
                mp3_path = export_mp3(audio, output_dir / f"{chord_name}.mp3")
                if mp3_path:
                    print(f"  MP3 saved: {mp3_path}")

        if getattr(args, "video", False):
            render_kwargs = dict(
                frets=v["frets"], fingers=v.get("fingers"),
                chord_name=chord_name, root_semitone=root_semi,
                bg_color=bg_color, width=600, height=800,
                dot_label=getattr(args, "dot_label", "note"),
                show_muted_x=not getattr(args, "no_muted_x", False),
                show_open_o=not getattr(args, "no_open_o", False),
                show_string_names=not getattr(args, "no_string_names", False),
                show_finger_numbers=not getattr(args, "no_finger_numbers", False),
                show_barre=not getattr(args, "no_barre", False),
                strum_direction=strum_dir,
            )
            print("  Rendering video…")
            out = Path(args.output) / "videos" / f"{chord_name}.mp4"
            path = export_chord_video(
                frets=v["frets"],
                render_fn=render_chord_diagram,
                render_kwargs=render_kwargs,
                audio_data=audio,
                output_path=out,
            )
            if path:
                print(f"  Video saved: {path}")
            else:
                print("  Video export failed — is ffmpeg on PATH?")

    if getattr(args, "tab", False):
        tab_img = render_chord_tab(
            frets=v["frets"], chord_name=chord_name, bg_color=bg_color,
            width=500, height=420,
        )
        out = Path(args.output) / "tabs" / f"{chord_name}_tab.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        tab_img.save(str(out))
        print(f"  Tab saved: {out}")


def cmd_scale(args):
    """Generate a scale diagram."""
    root = args.root
    scale_name = _normalize_scale_name(args.scale_name)

    if scale_name not in SCALE_NAMES:
        print(f"Error: Unknown scale '{scale_name}'")
        print(f"Available: {', '.join(SCALE_NAMES)}")
        return

    display_name = get_scale_display_name(root, scale_name)
    root_semi = note_name_to_semitone(root.split("/")[0])
    interval_labels = get_scale_interval_labels(scale_name)
    print(f"Generating: {display_name}  ({' '.join(interval_labels)})")

    bg_color = config.NAVY_DEEP if args.bg == "navy" else None
    safe_name = display_name.replace(" ", "_").replace("/", "-")

    if args.view == "full":
        notes = get_full_fretboard_scale(root, scale_name, num_frets=15)
        img = render_scale_full_fretboard(
            scale_notes=notes,
            scale_name=scale_name,
            root_name=root,
            bg_color=bg_color,
            width=1600, height=500,
            invert=getattr(args, "invert", False),
        )
        view_label = "full"
        scale_notes = notes
    elif args.view == "3nps":
        pos_num = args.position
        notes = get_three_note_per_string_scale(root, scale_name, position=pos_num)
        if not notes:
            print(f"Error: 3NPS position {pos_num} not available for this scale")
            return
        all_frets = [n["fret"] for n in notes]
        img = render_scale_box(
            box_notes=notes,
            start_fret=max(1, min(all_frets)),
            end_fret=max(all_frets),
            scale_name=f"{scale_name} (3NPS)",
            root_name=root,
            position_num=pos_num,
            bg_color=bg_color,
            width=600, height=800,
        )
        view_label = f"3nps{pos_num}"
        scale_notes = notes
    else:
        positions = get_caged_positions(root, scale_name)
        pos_num = args.position
        if pos_num > len(positions):
            print(f"Error: Only {len(positions)} positions available")
            return
        pos = positions[pos_num - 1]
        img = render_scale_box(
            box_notes=pos["notes"],
            start_fret=pos["start_fret"],
            end_fret=pos["end_fret"],
            scale_name=scale_name,
            root_name=root,
            position_num=pos_num,
            bg_color=bg_color,
            width=600, height=800,
        )
        view_label = f"pos{pos_num}"
        scale_notes = pos["notes"]

    if args.png:
        output_dir = Path(args.output) / "scales"
        filename = f"{safe_name}_{view_label}_{args.res}_{args.bg}.png"
        path = export_diagram(img, output_dir / filename, args.res, args.bg)
        print(f"  PNG saved: {path}")

    note_ms = int(60000 / max(args.tempo, 20))
    root_anchor = not getattr(args, "no_root_anchor", False)

    if args.audio or getattr(args, "video", False):
        audio = generate_scale_audio(
            scale_notes, tone=args.tone,
            note_duration_ms=note_ms,
            ascending=True, descending=True,
            root_to_root=root_anchor,
        )
        if args.audio:
            output_dir = Path(args.output) / "audio"
            wav_path = export_wav(audio, output_dir / f"{safe_name}_{view_label}.wav")
            if wav_path:
                print(f"  WAV saved: {wav_path}")
            if args.mp3:
                mp3_path = export_mp3(audio, output_dir / f"{safe_name}_{view_label}.mp3")
                if mp3_path:
                    print(f"  MP3 saved: {mp3_path}")

        if getattr(args, "video", False):
            render_kwargs = dict(
                scale_notes=scale_notes,
                scale_name=scale_name,
                root_name=root,
                bg_color=bg_color,
                width=1600, height=500,
                invert=getattr(args, "invert", False),
            )
            print("  Rendering video…")
            out = Path(args.output) / "videos" / f"{safe_name}_{view_label}.mp4"
            path = export_scale_video(
                notes_data=scale_notes,
                render_fn=render_scale_full_fretboard,
                render_kwargs=render_kwargs,
                audio_data=audio,
                output_path=out,
                note_duration_ms=note_ms,
            )
            if path:
                print(f"  Video saved: {path}")
            else:
                print("  Video export failed — is ffmpeg on PATH?")

    if getattr(args, "tab", False):
        tab_img = render_scale_tab(
            notes_data=scale_notes,
            title=display_name,
            bg_color=bg_color,
            width=1600, height=420,
            ascending=True, descending=True,
            root_to_root=root_anchor,
        )
        out = Path(args.output) / "tabs" / f"{safe_name}_{view_label}_tab.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        tab_img.save(str(out))
        print(f"  Tab saved: {out}")


def _normalize_arpeggio_name(raw):
    """Convert CLI arpeggio name to proper name. e.g., 'min7' -> 'Min7'"""
    normalized = raw.replace("-", " ").replace("_", " ").title()
    for name in ARPEGGIO_NAMES:
        if name.lower() == normalized.lower():
            return name
    for name in ARPEGGIO_NAMES:
        if normalized.lower() in name.lower():
            return name
    return normalized


def cmd_arpeggio(args):
    """Generate an arpeggio diagram."""
    root = args.root
    arp_name = _normalize_arpeggio_name(args.arpeggio_name)

    if arp_name not in ARPEGGIO_NAMES:
        print(f"Error: Unknown arpeggio '{arp_name}'")
        print(f"Available: {', '.join(ARPEGGIO_NAMES)}")
        return

    display_name = get_arpeggio_display_name(root, arp_name)
    print(f"Generating: {display_name}")

    bg_color = config.NAVY_DEEP if args.bg == "navy" else None
    safe_name = display_name.replace(" ", "_").replace("/", "-")

    if args.view == "full":
        notes = get_full_fretboard_arpeggio(root, arp_name, num_frets=15)
        img = render_scale_full_fretboard(
            scale_notes=notes,
            scale_name=f"{arp_name} Arpeggio",
            root_name=root,
            bg_color=bg_color,
            width=1600, height=500,
            invert=getattr(args, "invert", False),
        )
        view_label = "full"
        diagram_notes = notes
    else:
        positions = get_arpeggio_positions(root, arp_name)
        pos_num = args.position
        if pos_num > len(positions):
            print(f"Error: Only {len(positions)} positions available for this arpeggio")
            return
        pos = positions[pos_num - 1]
        img = render_scale_box(
            box_notes=pos["notes"],
            start_fret=pos["start_fret"],
            end_fret=pos["end_fret"],
            scale_name=f"{arp_name} Arpeggio",
            root_name=root,
            position_num=pos_num,
            bg_color=bg_color,
            width=600, height=800,
        )
        view_label = f"pos{pos_num}"
        diagram_notes = pos["notes"]

    if args.png:
        output_dir = Path(args.output) / "arpeggios"
        filename = f"{safe_name}_{view_label}_{args.res}_{args.bg}.png"
        path = export_diagram(img, output_dir / filename, args.res, args.bg)
        print(f"  PNG saved: {path}")

    note_ms = int(60000 / max(args.tempo, 20))
    root_anchor = not getattr(args, "no_root_anchor", False)

    if args.audio or getattr(args, "video", False):
        audio = generate_scale_audio(
            diagram_notes, tone=args.tone,
            note_duration_ms=note_ms,
            ascending=True, descending=True,
            root_to_root=root_anchor,
        )
        if args.audio:
            output_dir = Path(args.output) / "audio"
            wav_path = export_wav(audio, output_dir / f"{safe_name}_{view_label}.wav")
            if wav_path:
                print(f"  WAV saved: {wav_path}")

        if getattr(args, "video", False):
            render_kwargs = dict(
                scale_notes=diagram_notes,
                scale_name=f"{arp_name} Arpeggio",
                root_name=root,
                bg_color=bg_color,
                width=1600, height=500,
                invert=getattr(args, "invert", False),
            )
            print("  Rendering video…")
            out = Path(args.output) / "videos" / f"{safe_name}_{view_label}.mp4"
            path = export_scale_video(
                notes_data=diagram_notes,
                render_fn=render_scale_full_fretboard,
                render_kwargs=render_kwargs,
                audio_data=audio,
                output_path=out,
                note_duration_ms=note_ms,
            )
            if path:
                print(f"  Video saved: {path}")
            else:
                print("  Video export failed — is ffmpeg on PATH?")

    if getattr(args, "tab", False):
        tab_img = render_scale_tab(
            notes_data=diagram_notes,
            title=display_name,
            bg_color=bg_color,
            width=1600, height=420,
            ascending=True, descending=True,
            root_to_root=root_anchor,
        )
        out = Path(args.output) / "tabs" / f"{safe_name}_{view_label}_tab.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        tab_img.save(str(out))
        print(f"  Tab saved: {out}")


def cmd_progression(args):
    """Generate a chord progression diagram, audio, and/or video."""
    root = args.root.split("/")[0]
    mode = args.mode.lower()
    if mode not in ("major", "minor"):
        print(f"Error: mode must be 'major' or 'minor', got '{mode}'")
        return

    # Resolve progression degrees
    custom = getattr(args, "custom", None)
    if custom:
        degrees = parse_roman(custom, mode)
        if degrees is None:
            print(f"Error: Could not parse '{custom}' — use Roman numerals like I-V-vi-IV")
            return
        chords = get_progression_chords(root, mode, degrees)
        prog_name = custom.upper()
    else:
        prog_name = args.progression
        # Fuzzy match
        names = PROGRESSION_NAMES[mode]
        match = None
        for n in names:
            if n.lower() == prog_name.lower() or n.replace(" ", "").lower() == prog_name.replace("-", "").lower():
                match = n
                break
        if match is None:
            print(f"Error: Unknown progression '{prog_name}'")
            print(f"Available ({mode}): " + ", ".join(names))
            return
        degrees, chords = get_named_progression(root, match, mode)
        prog_name = match

    title = make_progression_title(root, mode, prog_name)
    safe = f"{root}_{mode}_{prog_name.replace(' ', '_').replace('–', '-')}"
    bg_color = config.NAVY_DEEP if args.bg == "navy" else None

    print(f"Generating: {title}")
    print("  Chords: " + "  |  ".join(c["display_name"] for c in chords))

    if args.png:
        img = render_progression_strip(chords, title=title, bg_color=bg_color)
        output_dir = Path(args.output) / "progressions"
        filename = f"{safe}_{args.res}_{args.bg}.png"
        path = export_diagram(img, output_dir / filename, args.res, args.bg)
        print(f"  PNG saved: {path}")

    chord_dur = getattr(args, "duration", 2.0)
    audio = None

    if args.audio or getattr(args, "video", False):
        audio = generate_progression_audio(
            chords,
            tone=args.tone,
            chord_duration_s=chord_dur,
        )

    if args.audio and audio is not None:
        output_dir = Path(args.output) / "audio"
        wav_path = export_wav(audio, output_dir / f"{safe}.wav")
        if wav_path:
            print(f"  WAV saved: {wav_path}")
        if getattr(args, "mp3", False):
            mp3_path = export_mp3(audio, output_dir / f"{safe}.mp3")
            if mp3_path:
                print(f"  MP3 saved: {mp3_path}")

    if getattr(args, "video", False) and audio is not None:
        print("  Rendering video…")
        out = Path(args.output) / "videos" / f"{safe}.mp4"
        path = export_progression_video(
            chords=chords,
            title=title,
            audio_data=audio,
            output_path=out,
            chord_duration_ms=int(chord_dur * 1000),
        )
        if path:
            print(f"  Video saved: {path}")
        else:
            print("  Video export failed — is ffmpeg on PATH?")


def _batch_chord(line, args, bg_color, note_ms):
    """Process a single chord line in a batch. Returns True on success."""
    root, quality = parse_chord_name(line)
    if not root:
        return False

    voicings = get_voicings(root, quality)
    if not voicings:
        print(f"  Skipping: no voicings for '{line}'")
        return True  # parsed ok, just no voicings

    v = voicings[0]
    chord_name = get_chord_display_name(root, quality)
    root_semi = note_name_to_semitone(root)

    img = render_chord_diagram(
        frets=v["frets"], fingers=v.get("fingers"),
        chord_name=chord_name, root_semitone=root_semi,
        bg_color=bg_color,
    )

    if args.png:
        path = export_diagram(
            img,
            Path(args.output) / "chords" / f"{chord_name}_{args.res}_{args.bg}.png",
            args.res, args.bg,
        )
        print(f"  PNG: {path}")

    audio = None
    if args.audio or getattr(args, "video", False):
        audio = generate_chord_audio(v["frets"], tone=args.tone)

    if args.audio and audio is not None:
        wav_path = export_wav(audio, Path(args.output) / "audio" / f"{chord_name}.wav")
        if wav_path:
            print(f"  WAV: {wav_path}")

    if getattr(args, "video", False) and audio is not None:
        render_kwargs = dict(
            frets=v["frets"], fingers=v.get("fingers"),
            chord_name=chord_name, root_semitone=root_semi,
            bg_color=bg_color,
        )
        out = Path(args.output) / "videos" / f"{chord_name}.mp4"
        path = export_chord_video(
            frets=v["frets"],
            render_fn=render_chord_diagram,
            render_kwargs=render_kwargs,
            audio_data=audio,
            output_path=out,
        )
        if path:
            print(f"  Video: {path}")
        else:
            print("  Video export failed — is ffmpeg on PATH?")

    return True


def _batch_scale(parts, args, bg_color, note_ms):
    """Process a 'scale ROOT NAME [--position N] [--view V]' batch line."""
    # parts: ['scale', 'A', 'pentatonic-minor', ...]
    if len(parts) < 3:
        print("  Skipping: scale line needs at least 'scale ROOT NAME'")
        return

    root = parts[1]
    # Collect remaining tokens; look for --position and --view flags
    rest = parts[2:]
    position = 1
    view = "full"
    name_parts = []
    i = 0
    while i < len(rest):
        if rest[i] in ("--position", "-p") and i + 1 < len(rest):
            try:
                position = int(rest[i + 1])
            except ValueError:
                pass
            i += 2
        elif rest[i] in ("--view", "-v") and i + 1 < len(rest):
            view = rest[i + 1]
            i += 2
        else:
            name_parts.append(rest[i])
            i += 1

    scale_name = _normalize_scale_name(" ".join(name_parts))
    if scale_name not in SCALE_NAMES:
        print(f"  Skipping: unknown scale '{scale_name}'")
        return

    display_name = get_scale_display_name(root, scale_name)
    safe_name = display_name.replace(" ", "_").replace("/", "-")
    print(f"  Scale: {display_name} ({view})")

    if view == "3nps":
        notes = get_three_note_per_string_scale(root, scale_name, position=position)
        all_frets = [n["fret"] for n in notes]
        img = render_scale_box(
            box_notes=notes,
            start_fret=max(1, min(all_frets)) if all_frets else 1,
            end_fret=max(all_frets) if all_frets else 5,
            scale_name=f"{scale_name} (3NPS)",
            root_name=root,
            position_num=position,
            bg_color=bg_color,
            width=600, height=800,
        )
        view_label = f"3nps{position}"
        scale_notes = notes
    elif view == "box":
        positions = get_caged_positions(root, scale_name)
        if position > len(positions):
            print(f"  Skipping: only {len(positions)} positions available")
            return
        pos = positions[position - 1]
        img = render_scale_box(
            box_notes=pos["notes"],
            start_fret=pos["start_fret"],
            end_fret=pos["end_fret"],
            scale_name=scale_name,
            root_name=root,
            position_num=position,
            bg_color=bg_color,
            width=600, height=800,
        )
        view_label = f"pos{position}"
        scale_notes = pos["notes"]
    else:  # full
        notes = get_full_fretboard_scale(root, scale_name, num_frets=15)
        img = render_scale_full_fretboard(
            scale_notes=notes,
            scale_name=scale_name,
            root_name=root,
            bg_color=bg_color,
            width=1600, height=500,
        )
        view_label = "full"
        scale_notes = notes

    if args.png:
        path = export_diagram(
            img,
            Path(args.output) / "scales" / f"{safe_name}_{view_label}_{args.res}_{args.bg}.png",
            args.res, args.bg,
        )
        print(f"  PNG: {path}")

    audio = None
    if args.audio or getattr(args, "video", False):
        audio = generate_scale_audio(
            scale_notes, tone=args.tone,
            note_duration_ms=note_ms,
            ascending=True, descending=True, root_to_root=True,
        )

    if args.audio and audio is not None:
        wav_path = export_wav(audio, Path(args.output) / "audio" / f"{safe_name}_{view_label}.wav")
        if wav_path:
            print(f"  WAV: {wav_path}")

    if getattr(args, "video", False) and audio is not None:
        render_fn = render_scale_full_fretboard if view == "full" else render_scale_box
        if view == "full":
            render_kwargs = dict(
                scale_notes=scale_notes, scale_name=scale_name,
                root_name=root, bg_color=bg_color,
                width=1600, height=500,
            )
        else:
            pos_data = positions[position - 1] if view == "box" else {"start_fret": min(all_frets), "end_fret": max(all_frets)}
            render_kwargs = dict(
                box_notes=scale_notes,
                start_fret=pos_data["start_fret"],
                end_fret=pos_data["end_fret"],
                scale_name=scale_name,
                root_name=root,
                position_num=position,
                bg_color=bg_color,
                width=600, height=800,
            )
        out = Path(args.output) / "videos" / f"{safe_name}_{view_label}.mp4"
        path = export_scale_video(
            notes_data=scale_notes,
            render_fn=render_fn,
            render_kwargs=render_kwargs,
            audio_data=audio,
            output_path=out,
            note_duration_ms=note_ms,
        )
        if path:
            print(f"  Video: {path}")
        else:
            print("  Video export failed — is ffmpeg on PATH?")


def _batch_arpeggio(parts, args, bg_color, note_ms):
    """Process an 'arpeggio ROOT NAME [--position N] [--view V]' batch line."""
    from data.arpeggios import get_full_fretboard_arpeggio, get_arpeggio_positions, get_arpeggio_display_name

    if len(parts) < 3:
        print("  Skipping: arpeggio line needs at least 'arpeggio ROOT NAME'")
        return

    root = parts[1]
    rest = parts[2:]
    position = 1
    view = "full"
    name_parts = []
    i = 0
    while i < len(rest):
        if rest[i] in ("--position", "-p") and i + 1 < len(rest):
            try:
                position = int(rest[i + 1])
            except ValueError:
                pass
            i += 2
        elif rest[i] in ("--view", "-v") and i + 1 < len(rest):
            view = rest[i + 1]
            i += 2
        else:
            name_parts.append(rest[i])
            i += 1

    arp_name = _normalize_arpeggio_name(" ".join(name_parts))
    if arp_name not in ARPEGGIO_NAMES:
        print(f"  Skipping: unknown arpeggio '{arp_name}'")
        return

    display_name = get_arpeggio_display_name(root, arp_name)
    safe_name = display_name.replace(" ", "_").replace("/", "-")
    print(f"  Arpeggio: {display_name} ({view})")

    if view == "box":
        positions = get_arpeggio_positions(root, arp_name)
        if position > len(positions):
            print(f"  Skipping: only {len(positions)} positions available")
            return
        pos = positions[position - 1]
        img = render_scale_box(
            box_notes=pos["notes"],
            start_fret=pos["start_fret"],
            end_fret=pos["end_fret"],
            scale_name=f"{arp_name} Arpeggio",
            root_name=root,
            position_num=position,
            bg_color=bg_color,
            width=600, height=800,
        )
        view_label = f"pos{position}"
        diagram_notes = pos["notes"]
    else:
        notes = get_full_fretboard_arpeggio(root, arp_name, num_frets=15)
        img = render_scale_full_fretboard(
            scale_notes=notes,
            scale_name=f"{arp_name} Arpeggio",
            root_name=root,
            bg_color=bg_color,
            width=1600, height=500,
        )
        view_label = "full"
        diagram_notes = notes

    if args.png:
        path = export_diagram(
            img,
            Path(args.output) / "arpeggios" / f"{safe_name}_{view_label}_{args.res}_{args.bg}.png",
            args.res, args.bg,
        )
        print(f"  PNG: {path}")

    audio = None
    if args.audio or getattr(args, "video", False):
        audio = generate_scale_audio(
            diagram_notes, tone=args.tone,
            note_duration_ms=note_ms,
            ascending=True, descending=True, root_to_root=True,
        )

    if args.audio and audio is not None:
        wav_path = export_wav(audio, Path(args.output) / "audio" / f"{safe_name}_{view_label}.wav")
        if wav_path:
            print(f"  WAV: {wav_path}")

    if getattr(args, "video", False) and audio is not None:
        render_kwargs = dict(
            scale_notes=diagram_notes,
            scale_name=f"{arp_name} Arpeggio",
            root_name=root, bg_color=bg_color,
            width=1600, height=500,
        )
        out = Path(args.output) / "videos" / f"{safe_name}_{view_label}.mp4"
        path = export_scale_video(
            notes_data=diagram_notes,
            render_fn=render_scale_full_fretboard,
            render_kwargs=render_kwargs,
            audio_data=audio,
            output_path=out,
            note_duration_ms=note_ms,
        )
        if path:
            print(f"  Video: {path}")
        else:
            print("  Video export failed — is ffmpeg on PATH?")


def cmd_batch(args):
    """Process a batch file of chords/scales/arpeggios.

    Batch file format (one item per line, # = comment):
        Am7                              # chord
        scale A pentatonic-minor         # full fretboard scale
        scale E blues --view box --position 2
        scale C major --view 3nps --position 1
        arpeggio A minor                 # full fretboard arpeggio
        arpeggio C major7 --view box --position 1
    """
    batch_file = Path(args.file)
    if not batch_file.exists():
        print(f"Error: File not found: {batch_file}")
        return

    lines = batch_file.read_text(encoding="utf-8").strip().split("\n")
    lines = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]

    if not lines:
        print("Batch file is empty.")
        return

    print(f"Processing {len(lines)} items from {batch_file.name}...")

    bg_color = config.NAVY_DEEP if args.bg == "navy" else None
    note_ms = int(60000 / max(getattr(args, "tempo", 100), 20))
    errors = 0

    for i, line in enumerate(lines):
        print(f"\n[{i+1}/{len(lines)}] {line}")
        parts = line.split()
        keyword = parts[0].lower() if parts else ""

        try:
            if keyword == "scale":
                _batch_scale(parts, args, bg_color, note_ms)
            elif keyword == "arpeggio":
                _batch_arpeggio(parts, args, bg_color, note_ms)
            else:
                # Try chord
                if not _batch_chord(line, args, bg_color, note_ms):
                    print(f"  Skipping: could not parse '{line}'")
                    errors += 1
        except Exception as exc:
            print(f"  Error: {exc}")
            errors += 1

    print(f"\nBatch complete! {len(lines) - errors}/{len(lines)} items processed successfully.")


def build_parser():
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="studio",
        description="GembaGuitar Diagram Studio — chord & scale diagram generator",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ── chord ──
    chord_p = subparsers.add_parser("chord", help="Generate a chord diagram")
    chord_p.add_argument("chord_name", nargs="+", help="Chord name (e.g., Am7, F#dim)")
    chord_p.add_argument("--png", action="store_true", help="Export PNG")
    chord_p.add_argument("--audio", action="store_true", help="Export audio")
    chord_p.add_argument("--mp3", action="store_true", help="Also export MP3 (in addition to WAV)")
    chord_p.add_argument("--res", default="1080p", choices=list(config.RESOLUTIONS.keys()))
    chord_p.add_argument("--bg", default="transparent", choices=["transparent", "navy"])
    chord_p.add_argument("--tone", default="acoustic", choices=["acoustic", "electric", "sine"])
    chord_p.add_argument("--voicing", type=int, default=1, help="Voicing number (1-3)")
    chord_p.add_argument("--dot-label", dest="dot_label", default="note",
                         choices=["note", "finger", "none"],
                         help="What to show inside fretted dots (default: note)")
    chord_p.add_argument("--no-muted-x", dest="no_muted_x", action="store_true",
                         help="Hide X markers above muted strings")
    chord_p.add_argument("--no-open-o", dest="no_open_o", action="store_true",
                         help="Hide O markers above open strings")
    chord_p.add_argument("--no-string-names", dest="no_string_names", action="store_true",
                         help="Hide string name labels (E A D G B e) below diagram")
    chord_p.add_argument("--no-finger-numbers", dest="no_finger_numbers", action="store_true",
                         help="Hide finger numbers below string names")
    chord_p.add_argument("--no-barre", dest="no_barre", action="store_true",
                         help="Draw individual dots instead of a barre bar")
    chord_p.add_argument(
        "--play-style", dest="play_style",
        choices=["strum", "strum_up", "arpeggio", "arpeggio_strum"],
        default="strum",
        help="Chord playback style: strum (default), strum_up, arpeggio, arpeggio_strum",
    )
    chord_p.add_argument("--tab", action="store_true",
                         help="Export guitar tab notation as PNG")
    chord_p.add_argument("--video", action="store_true",
                         help="Export animated MP4 video (requires ffmpeg)")
    chord_p.add_argument("--output", "-o", default=str(config.OUTPUT_DIR))

    # ── scale ──
    scale_p = subparsers.add_parser("scale", help="Generate a scale diagram")
    scale_p.add_argument("root", help="Root note (e.g., A, F#, Bb)")
    scale_p.add_argument("scale_name", help="Scale name (e.g., pentatonic-minor, blues, major)")
    scale_p.add_argument("--view", default="full", choices=["full", "box", "3nps"])
    scale_p.add_argument("--invert", action="store_true", help="Invert fretboard (high e at top, like guitar in lap)")
    scale_p.add_argument("--position", type=int, default=1, help="Box position (1-5)")
    scale_p.add_argument("--png", action="store_true", help="Export PNG")
    scale_p.add_argument("--audio", action="store_true", help="Export audio")
    scale_p.add_argument("--mp3", action="store_true", help="Also export MP3")
    scale_p.add_argument("--tempo", type=int, default=100, metavar="BPM",
                         help="Playback tempo in BPM (default: 100)")
    scale_p.add_argument("--no-root-anchor", dest="no_root_anchor", action="store_true",
                         help="Play all notes lowest to highest instead of anchoring on root")
    scale_p.add_argument("--tab", action="store_true",
                         help="Export guitar tab notation as PNG")
    scale_p.add_argument("--video", action="store_true",
                         help="Export animated MP4 video (requires ffmpeg)")
    scale_p.add_argument("--res", default="1080p", choices=list(config.RESOLUTIONS.keys()))
    scale_p.add_argument("--bg", default="transparent", choices=["transparent", "navy"])
    scale_p.add_argument("--tone", default="acoustic", choices=["acoustic", "electric", "sine"])
    scale_p.add_argument("--output", "-o", default=str(config.OUTPUT_DIR))

    # ── arpeggio ──
    arp_p = subparsers.add_parser("arpeggio", help="Generate an arpeggio diagram")
    arp_p.add_argument("root", help="Root note (e.g., A, F#, Bb)")
    arp_p.add_argument("arpeggio_name", help=f"Arpeggio type ({', '.join(ARPEGGIO_NAMES)})")
    arp_p.add_argument("--view", default="full", choices=["full", "box"])
    arp_p.add_argument("--position", type=int, default=1, help="Box position number")
    arp_p.add_argument("--invert", action="store_true", help="Invert fretboard (high e at top)")
    arp_p.add_argument("--png", action="store_true")
    arp_p.add_argument("--audio", action="store_true")
    arp_p.add_argument("--mp3", action="store_true")
    arp_p.add_argument("--tempo", type=int, default=100, metavar="BPM",
                         help="Playback tempo in BPM (default: 100)")
    arp_p.add_argument("--no-root-anchor", dest="no_root_anchor", action="store_true",
                         help="Play all notes lowest to highest instead of anchoring on root")
    arp_p.add_argument("--tab", action="store_true",
                         help="Export guitar tab notation as PNG")
    arp_p.add_argument("--video", action="store_true",
                         help="Export animated MP4 video (requires ffmpeg)")
    arp_p.add_argument("--res", default="1080p", choices=list(config.RESOLUTIONS.keys()))
    arp_p.add_argument("--bg", default="transparent", choices=["transparent", "navy"])
    arp_p.add_argument("--tone", default="acoustic", choices=["acoustic", "electric", "sine"])
    arp_p.add_argument("--output", "-o", default=str(config.OUTPUT_DIR))

    # ── progression ──
    prog_p = subparsers.add_parser("progression", help="Generate a chord progression diagram + audio")
    prog_p.add_argument("root", help="Key root note (e.g., C, F#, Bb)")
    prog_p.add_argument("mode", help="Key mode: 'major' or 'minor'")
    prog_p.add_argument("progression", nargs="?", default=None,
                        help="Named progression (e.g., 'I - V - vi - IV') — omit to list all")
    prog_p.add_argument("--custom", metavar="ROMAN",
                        help="Custom Roman-numeral progression (e.g., I-IV-V-I)")
    prog_p.add_argument("--list", action="store_true", help="List available progressions for the mode and exit")
    prog_p.add_argument("--duration", type=float, default=2.0, metavar="SEC",
                        help="Seconds per chord (default: 2.0)")
    prog_p.add_argument("--png", action="store_true", help="Export strip PNG")
    prog_p.add_argument("--audio", action="store_true", help="Export audio (WAV)")
    prog_p.add_argument("--mp3", action="store_true", help="Also export MP3")
    prog_p.add_argument("--video", action="store_true",
                        help="Export animated MP4 video (requires ffmpeg)")
    prog_p.add_argument("--res", default="1080p", choices=list(config.RESOLUTIONS.keys()))
    prog_p.add_argument("--bg", default="navy", choices=["transparent", "navy"])
    prog_p.add_argument("--tone", default="acoustic", choices=["acoustic", "electric", "sine"])
    prog_p.add_argument("--output", "-o", default=str(config.OUTPUT_DIR))

    # ── batch ──
    batch_p = subparsers.add_parser("batch", help="Batch process chords/scales/arpeggios from a file")
    batch_p.add_argument("file", help="Text file (one chord / 'scale ROOT NAME' / 'arpeggio ROOT NAME' per line)")
    batch_p.add_argument("--png", action="store_true", help="Export PNGs")
    batch_p.add_argument("--audio", action="store_true", help="Export audio (WAV)")
    batch_p.add_argument("--mp3", action="store_true", help="Also export MP3")
    batch_p.add_argument("--video", action="store_true", help="Export animated MP4 videos (requires ffmpeg)")
    batch_p.add_argument("--tempo", type=int, default=100, metavar="BPM",
                         help="Scale/arpeggio playback tempo in BPM (default: 100)")
    batch_p.add_argument("--res", default="1080p", choices=list(config.RESOLUTIONS.keys()))
    batch_p.add_argument("--bg", default="transparent", choices=["transparent", "navy"])
    batch_p.add_argument("--tone", default="acoustic", choices=["acoustic", "electric", "sine"])
    batch_p.add_argument("--output", "-o", default=str(config.OUTPUT_DIR))

    # ── gui ──
    subparsers.add_parser("gui", help="Launch the GUI application")

    return parser


def main(args=None):
    """Main CLI entry point."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.command == "chord":
        cmd_chord(parsed)
    elif parsed.command == "scale":
        cmd_scale(parsed)
    elif parsed.command == "arpeggio":
        cmd_arpeggio(parsed)
    elif parsed.command == "progression":
        if getattr(parsed, "list", False):
            names = PROGRESSION_NAMES.get(parsed.mode.lower(), [])
            print(f"Available {parsed.mode} progressions:")
            for n in names:
                print(f"  {n}")
        elif not parsed.progression and not getattr(parsed, "custom", None):
            names = PROGRESSION_NAMES.get(parsed.mode.lower(), [])
            print(f"Available {parsed.mode} progressions:")
            for n in names:
                print(f"  {n}")
            print("\nUse --custom ROMAN or specify a progression name.")
        else:
            cmd_progression(parsed)
    elif parsed.command == "batch":
        cmd_batch(parsed)
    elif parsed.command == "gui":
        from gui.app import run
        run()
    else:
        parser.print_help()
