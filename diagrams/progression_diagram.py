"""Coordinated progression layouts with numbered cards and active-panel accents."""
from diagrams.artwork import Artwork
from diagrams.chord_diagram import render_chord_diagram
from data.notes import note_name_to_semitone
from services.documents import record_render


def compose_strip(items,title,render,panel_w,panel_h,padding,title_height,label_height,bg_color,highlighted_idx):
    if not items: return Artwork(800,400,bg_color).finish()
    th=max(title_height,round(panel_h*.22))
    footer=max(label_height,round(panel_h*.12))
    width=len(items)*panel_w+(len(items)+1)*padding
    height=th+panel_h+footer+padding
    a=Artwork(width,height,bg_color); u=panel_w/420
    a.text(padding,th*.15,'SEQUENCE / '+f'{len(items):02} PANELS',12*u,'root',True)
    a.text(padding,th*.40,title or 'Progression',32*u,bold=True,max_width=width-2*padding)
    for i,item in enumerate(items):
        x=padding+i*(panel_w+padding)
        a.paste(render(item),x,th)
        active=i==highlighted_idx
        if active: a.rect((x,th,x+panel_w,th+panel_h),None,16*u,'active',3*u)
        a.rect((x+panel_w*.08,th+panel_h+4*u,x+panel_w*.92,th+panel_h+footer*.75),'root' if active else 'panel',10*u)
        a.text(x+panel_w*.13,th+panel_h+footer*.36,f'{i+1:02}',13*u,'on_root' if active else 'muted',anchor='lm')
        a.text(x+panel_w*.5,th+panel_h+footer*.36,item.get('roman',''),24*u,'on_root' if active else 'ink',True,'mm')
    return a.finish()


@record_render
def render_progression_strip(chords,title='',highlighted_idx=None,chord_w=420,chord_h=560,
    padding=24,title_height=80,roman_height=52,bg_color=None,dot_label='note',show_barre=True,
    barre_style='rect',show_string_names=True,show_finger_numbers=True):
    def render(chord):
        return render_chord_diagram(chord['frets'],chord.get('fingers'),chord['display_name'],
            note_name_to_semitone(chord['chord_root']),width=chord_w,height=chord_h,show_watermark=False,
            dot_label=dot_label,show_barre=show_barre,barre_style=barre_style,
            show_string_names=show_string_names,show_finger_numbers=show_finger_numbers)
    return compose_strip(chords,title,render,chord_w,chord_h,padding,title_height,roman_height,bg_color,highlighted_idx)


def make_progression_title(root_name,mode,prog_name):
    return f'{root_name} {mode.capitalize()} / {prog_name}'
