"""Modern positional and panoramic fretboard diagrams, shared by scales/arpeggios."""
from diagrams.artwork import Artwork, marker
from data.instrument import string_column, string_names, settings
from services.documents import record_render


@record_render
def render_scale_box(box_notes,start_fret,end_fret,scale_name='',root_name='',
    position_num=None,bg_color=None,width=600,height=800,show_watermark=True,highlighted_notes=None):
    a=Artwork(width,height,bg_color); u=min(width/600,height/800)
    active=highlighted_notes or set(); start=max(1,start_fret); end=max(start+3,end_fret)
    title=(root_name+' '+scale_name).strip() or 'Position study'
    detail=f'Frets {start} - {end}'
    a.header(title,'FRETBOARD / '+(f'POSITION {position_num}' if position_num else 'STUDY'),detail)
    left,right=width*.22,width*.86; top,bottom=height*.32,height*.785
    dx=(right-left)/5; dy=(bottom-top)/(end-start+1); r=min(dx*.35,dy*.36)
    a.rect((width*.08,height*.26,width*.92,height*.875),'panel',radius=22*u)
    for j in range(end-start+2):
        y=top+j*dy; a.line((left,y,right,y),'grid',u)
        if j==0: a.text(width*.135,y+dy/2,f'{start}fr',22*u,'ink',True,anchor='mm')
    for i in range(6):
        x=left+string_column(i)*dx; a.line((x,top,x,bottom),'grid',(1.1+(5-i)*.12)*u)
        a.text(x,bottom+height*.032,string_names()[i],25*u,'ink',True,anchor='mt')
    if start==1: a.rect((left-2*u,top-2*u,right+2*u,top+2*u),'ink',radius=2*u)
    for n in box_notes:
        f=n['fret']
        if f!=0 and not start<=f<=end: continue
        x=left+string_column(n['string'])*dx
        y=top-dy*.43 if f==0 else top+(f-start+.5)*dy
        marker(a,x,y,min(r,dy*.29) if f==0 else r,n.get('note_name',''),n.get('is_root',False),(n['string'],f) in active)
    if show_watermark: a.footer()
    return a.finish()


@record_render
def render_scale_full_fretboard(scale_notes,scale_name='',root_name='',bg_color=None,
    width=1600,height=500,num_frets=15,show_watermark=True,invert=False,highlighted_notes=None):
    a=Artwork(width,height,bg_color); u=min(width/1600,height/500)
    active=highlighted_notes or set()
    a.header((root_name+' '+scale_name).strip(),'FRETBOARD / FULL NECK')
    left,right=width*.105,width*.935; top,bottom=height*.355,height*.785
    dx=(right-left)/num_frets; dy=(bottom-top)/5
    a.rect((width*.035,height*.275,width*.965,height*.89),'panel',radius=19*u)
    flip=settings()['left_handed']
    def fret_x(f):
        x=left-dx*.55 if f==0 else left+(f-.5)*dx
        return width*1.04-x if flip else x
    def string_y(i): return top+(5-i if invert else i)*dy
    gx0,gx1=(width*1.04-right,width*1.04-left) if flip else (left,right)
    for f in range(num_frets+1):
        x=left+f*dx; x=width*1.04-x if flip else x
        a.line((x,top-12*u,x,bottom+12*u),'ink' if f==0 else 'grid',3*u if f==0 else u)
        if f>0: a.text(fret_x(f),height*.835,f'{f}fr',21*u,'ink',True,anchor='mt')
    for i in range(6):
        y=string_y(i)
        a.line((gx0,y,gx1,y),'grid',(1+(5-i)*.14)*u)
        a.text(width*.967 if flip else width*.032,y,string_names()[i],24*u,'ink',True,anchor='mm')
    for n in scale_notes:
        if n['fret']>num_frets: continue
        marker(a,fret_x(n['fret']),string_y(n['string']),min(dx*.29,dy*.39),n.get('note_name',''),
               n.get('is_root',False),(n['string'],n['fret']) in active)
    a.footer(watermark=show_watermark)
    return a.finish()
