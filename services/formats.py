"""Portable MIDI, vector SVG and printable PDF exports."""
from pathlib import Path
import struct
from xml.sax.saxutils import escape
from services.media import musical_segments
from services.documents import render_spec
from data.instrument import for_snapshot, string_column


def _vlq(value):
    result = [value & 127]
    value >>= 7
    while value:
        result.insert(0, (value & 127) | 128)
        value >>= 7
    return bytes(result)


def export_midi(snap, path):
    """SMF type 0, 480 ticks/quarter at 120 BPM; event times remain in seconds."""
    events = []
    elapsed = 0.
    for notes, minimum in musical_segments(snap):
        for note in notes:
            events.append((round((elapsed+note.start)*960), bytes((0x90, note.midi, 90))))
            events.append((round((elapsed+note.start+note.duration)*960), bytes((0x80, note.midi, 0))))
        elapsed += max(minimum, max((n.start+n.duration for n in notes), default=0)+.5)
    track = bytearray(b'\x00\xff\x51\x03\x07\xa1\x20')
    previous = 0
    for tick, message in sorted(events, key=lambda pair: (pair[0], pair[1][0])):
        track.extend(_vlq(tick-previous)); track.extend(message)
        previous = tick
    track.extend(b'\x00\xff\x2f\x00')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'MThd'+struct.pack('>IHHH', 6,0,1,480)+b'MTrk'+struct.pack('>I',len(track))+track)
    return path


@for_snapshot
def export_print(snap,path,fmt):
    from PIL import Image
    from diagrams.style import palette
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    if fmt=='pdf':
        image=render_spec(snap['render_spec'],(2480,3508))
        page=Image.new('RGB',(2480,3508),image.info.get('background',palette()['bg']))
        page.paste(image,((2480-image.width)//2,(3508-image.height)//2),image.getchannel('A'))
        page.save(path,'PDF',resolution=300)
    elif fmt=='svg':
        import base64
        import config
        image=render_spec(snap['render_spec'])
        body=image.info.get('svg_body')
        if body is None: raise ValueError('This legacy diagram does not support vector export')
        font=base64.b64encode(Path(config.get_font_path(config.FONT_BODY)).read_bytes()).decode('ascii')
        font_license=escape((config.FONT_DIR/'DMSans-OFL.txt').read_text(encoding='utf-8'))
        css="@font-face{font-family:'DM Sans';src:url(data:font/ttf;base64,"+font+") format('truetype');font-weight:100 900;}"
        width,height=image.size
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
            f'<metadata>{font_license}</metadata><defs><style>{css}</style></defs><rect width="100%" height="100%" fill="{image.info["background"]}"/>'
            +body+'</svg>',encoding='utf-8')
    else: raise ValueError('Unknown print format')
    return path
