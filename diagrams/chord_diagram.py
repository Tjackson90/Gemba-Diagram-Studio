"""Modern chord cards: clear hierarchy, geometric root markers and quiet grids."""
from diagrams.artwork import Artwork, marker
from data.instrument import string_column, string_names, get_tuning
from data.notes import fret_to_note_name
from services.documents import record_render


@record_render
def render_chord_diagram(frets, fingers=None, chord_name='', root_semitone=None,
    bg_color=None, width=600, height=800, show_watermark=True, dot_label='note',
    show_muted_x=True, show_open_o=True, show_string_names=True,
    show_finger_numbers=True, show_barre=True, barre_style='rect', highlighted_strings=None):
    if len(frets)!=6: raise ValueError('A chord diagram needs six strings')
    fingers=fingers or [0]*6
    active=highlighted_strings or set()
    a=Artwork(width,height,bg_color); u=min(width/600,height/800)
    held=[f for f in frets if f>0]
    start=1 if max(held,default=0)<=5 else min(held)
    count=max(5,max(held,default=start)-start+1)
    pitches=list(dict.fromkeys(fret_to_note_name(i,f) for i,f in enumerate(frets) if f>=0))
    a.header(chord_name or 'Untitled chord','CHORD / '+('OPEN' if start==1 else f'POSITION {start}'),
             '  /  '.join(pitches),center_title=True)
    left,right=width*.22,width*.86
    top,bottom=height*.32,height*.765
    dx=(right-left)/5; dy=(bottom-top)/count; r=min(dx*.34,dy*.35)
    a.rect((width*.08,height*.26,width*.92,height*.87),'panel',radius=22*u)
    for j in range(count+1):
        y=top+j*dy
        a.line((left,y,right,y),'grid',u)
        if j==0: a.text(width*.135,y+dy/2,f'{start}fr',22*u,'ink',True,anchor='mm')
    for i in range(6):
        x=left+string_column(i)*dx
        a.line((x,top,x,bottom),'grid',(1.1+(5-i)*.12)*u)
    if start==1: a.rect((left-2*u,top-2*u,right+2*u,top+2*u),'ink',radius=2*u)
    # Capsule barres live behind the individual notes so labels stay legible.
    if show_barre:
        for finger in range(1,5):
            group=[i for i,(f,fg) in enumerate(zip(frets,fingers)) if fg==finger and f>0]
            if len(group)<2: continue
            common=min(frets[i] for i in group)
            same=[i for i in group if frets[i]==common]
            if len(same)<2: continue
            xs=[left+string_column(i)*dx for i in same]; y=top+(common-start+.5)*dy
            if barre_style=='arch':
                a.arch(min(xs),max(xs),y,r*.95,'note',4*u)
            else:
                thickness=r*.8
                a.rect((min(xs)-r*.7,y-thickness,max(xs)+r*.7,y+thickness),'note',radius=thickness)
    for i,f in enumerate(frets):
        x=left+string_column(i)*dx
        root=f>=0 and (get_tuning()[i]+f)%12==root_semitone
        if f<0 and show_muted_x:
            y=top-dy*.42; size=5*u
            a.line((x-size,y-size,x+size,y+size),'muted',1.6*u)
            a.line((x-size,y+size,x+size,y-size),'muted',1.6*u)
        elif f==0 and show_open_o:
            y=top-dy*.42
            if root or i in active: marker(a,x,y,8*u,'',root,i in active)
            else: a.circle(x,y,6*u,None,'muted',1.7*u)
        elif f>0:
            text=fret_to_note_name(i,f) if dot_label=='note' else (str(fingers[i]) if dot_label=='finger' and fingers[i] else '')
            marker(a,x,top+(f-start+.5)*dy,r,text,root,i in active)
        if show_string_names: a.text(x,bottom+height*.031,string_names()[i],25*u,'ink',True,anchor='mt')
        if show_finger_numbers and f>0 and fingers[i]:
            a.text(x,bottom+height*(.06 if show_string_names else .031),str(fingers[i]),12*u,'ink',anchor='mt')
    if show_watermark:
        a.footer()
    return a.finish()
