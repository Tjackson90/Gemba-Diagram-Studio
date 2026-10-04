"""Modern readable tablature; direct event order shared with playback and video."""
from math import ceil
from diagrams.artwork import Artwork
from data.instrument import string_names
from data.timeline import note_sequence
from services.documents import record_render


def _tab(sequence,title,bg,width,height,watermark,highlight=None,chord=False):
    unit=height/420
    capacity=min(24,max(8,int(width/(48*unit)))) if not chord else 1
    rows=max(1,ceil(len(sequence)/capacity))
    per_row=max(1,ceil(len(sequence)/rows))
    total_h=round(height+(rows-1)*height*.65)
    a=Artwork(width,total_h,bg)
    margin=width*.05
    a.text(margin,height*.07,'TABLATURE / '+('CHORD' if chord else 'MELODY'),12*unit,'root',True)
    a.text(width*.5 if chord else margin,height*.135,title or 'Tablature',29*unit,bold=True,anchor='mt' if chord else 'lt',max_width=width*.9)
    for row in range(rows):
        y0=height*.35+row*height*.65; y1=y0+height*.4
        a.rect((margin,y0-height*.055,width-margin,y1+height*.055),'panel',14*unit)
        left=margin+width*.05; right=width-margin-width*.03; dy=(y1-y0)/5
        for i in range(6):
            y=y0+(5-i)*dy
            a.line((left,y,right,y),'grid',unit)
            a.text(margin+width*.023,y,string_names()[i],23*unit,'ink',True,anchor='mm')
        entries=sequence[row*per_row:(row+1)*per_row]
        for col,entry in enumerate(entries):
            x=(left+right)/2 if chord else left+(col+.5)*(right-left)/max(per_row,4)
            notes=entry if chord else [entry]
            for si,fret in notes:
                y=y0+(5-si)*dy; active=(si in (highlight or set())) if chord else row*per_row+col==highlight
                size=min(dy*.72,(right-left)/max(len(entries),4)*.65)
                a.rect((x-size*.62,y-size*.65,x+size*.62,y+size*.65),'root' if active else 'panel',size*.25,
                       None if active else 'grid',unit)
                a.text(x,y,'x' if fret<0 else str(fret),size*.9,'on_root' if active else 'ink',True,'mm')
    a.footer(watermark=watermark)
    return a.finish()


@record_render
def render_chord_tab(frets,chord_name='',bg_color=None,width=500,height=420,show_watermark=True,highlighted_strings=None):
    return _tab([list(enumerate(frets))],chord_name,bg_color,width,height,show_watermark,highlighted_strings,True)


@record_render
def render_scale_tab(notes_data,title='',bg_color=None,width=1600,height=420,show_watermark=True,
    ascending=True,descending=False,root_to_root=True,highlighted_idx=None,stop_at_high_e_root=False,events=None):
    sequence=([(e.string,e.fret) for e in events] if events is not None else
              [(s,f) for _,s,f in note_sequence(notes_data,ascending,descending,root_to_root,stop_at_high_e_root)])
    return _tab(sequence,title,bg_color,width,height,show_watermark,highlighted_idx)


def render_event_tab(events,title=''):
    notes=[dict(string=e.string,fret=e.fret,midi=e.midi) for e in events]
    return render_scale_tab(notes,title=title,events=events)
