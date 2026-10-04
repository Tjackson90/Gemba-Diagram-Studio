"""Shared drawing primitives produce matching raster and genuine vector artwork."""
from html import escape
from PIL import Image, ImageDraw, ImageColor
import config
from diagrams.fonts import load_font
from diagrams.style import palette, name


class Artwork:
    def __init__(self,width,height,bg=None):
        config.validate_size(int(width),int(height))
        self.w,self.h=int(width),int(height)
        self.p=palette()
        self.image=Image.new('RGBA',(self.w,self.h),(0,0,0,0))
        self.draw=ImageDraw.Draw(self.image)
        self.svg=[]
        if bg is not None:
            self.rect((0,0,width,height),bg)

    def color(self,color):
        if isinstance(color,str) and color in self.p: color=self.p[color]
        if isinstance(color,(tuple,list)): return '#%02x%02x%02x'%tuple(color[:3])
        return color

    def rect(self,box,fill,radius=0,outline=None,stroke=1):
        x,y,r,b=box; fill=self.color(fill); outline=self.color(outline) if outline else None
        self.draw.rounded_rectangle(box,radius=max(0,radius),fill=fill,outline=outline,width=max(1,round(stroke)))
        self.svg.append(f'<rect x="{x:g}" y="{y:g}" width="{r-x:g}" height="{b-y:g}" rx="{radius:g}" fill="{fill or "none"}" stroke="{outline or "none"}" stroke-width="{stroke:g}"/>')

    def line(self,xy,fill='grid',width=1):
        fill=self.color(fill); self.draw.line(xy,fill=fill,width=max(1,round(width)))
        self.svg.append(f'<line x1="{xy[0]:g}" y1="{xy[1]:g}" x2="{xy[2]:g}" y2="{xy[3]:g}" stroke="{fill}" stroke-width="{width:g}" stroke-linecap="round"/>')

    def circle(self,x,y,r,fill,outline=None,width=1):
        fill=self.color(fill); outline=self.color(outline) if outline else None
        self.draw.ellipse((x-r,y-r,x+r,y+r),fill=fill,outline=outline,width=max(1,round(width)))
        self.svg.append(f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{fill or "none"}" stroke="{outline or "none"}" stroke-width="{width:g}"/>')

    def arch(self,left,right,y,rise,color='note',width=2):
        color=self.color(color)
        points=[]
        for i in range(41):
            t=i/40
            points.append((left+(right-left)*t,y-4*rise*t*(1-t)))
        self.draw.line(points,fill=color,width=max(1,round(width)),joint='curve')
        self.svg.append(f'<path d="M {left:g} {y:g} Q {(left+right)/2:g} {y-2*rise:g} {right:g} {y:g}" fill="none" stroke="{color}" stroke-width="{width:g}" stroke-linecap="round"/>')

    def text(self,x,y,text,size,fill='ink',bold=False,anchor='lt',max_width=None):
        size=max(8,int(size)); text=str(text)
        font=load_font(config.FONT_BODY_BOLD if bold else config.FONT_BODY,size)
        if max_width:
            while font.getlength(text)>max_width and size>8:
                size-=1; font=load_font(config.FONT_BODY_BOLD if bold else config.FONT_BODY,size)
        fill=self.color(fill)
        # Top/middle anchor conversion is identical for exported SVG labels.
        bounds=self.draw.textbbox((x,y),text,font=font,anchor=anchor)
        self.draw.text((x,y),text,font=font,fill=fill,anchor=anchor)
        self.svg.append(f'<text x="{bounds[0]:g}" y="{bounds[1]+self.draw.textbbox((0,0),text,font=font)[3]-self.draw.textbbox((0,0),text,font=font)[1]:g}" font-family="DM Sans, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{fill}">{escape(text)}</text>')

    def paste(self,image,x,y):
        self.image.alpha_composite(image,(round(x),round(y)))
        self.draw=ImageDraw.Draw(self.image)
        if 'svg_body' in image.info:
            self.svg.append(f'<g transform="translate({x:g},{y:g})">{image.info["svg_body"]}</g>')

    def finish(self):
        self.image.info.update(svg_body=''.join(self.svg),diagram_theme=name(),background=self.p['bg'])
        return self.image

    def header(self,title,kicker='CHORD',detail='',compact=False,center_title=False):
        w,h=self.w,self.h; unit=min(w/600,h/800) if h>w else h/500
        margin=w*.08
        self.rect((margin,h*.055,margin+24*unit,h*.055+4*unit),'root',radius=2*unit)
        self.text(margin+36*unit,h*.05,kicker,13*unit,'muted',True,max_width=w*.55)
        self.text(w*.5 if center_title else margin,h*.094,title,(60 if h>w else 42)*unit,bold=True,anchor='mt' if center_title else 'lt',max_width=w*.84)
        if detail: self.text(margin,h*.192 if h>w else h*.218,detail,14*unit,'muted',max_width=w*.84)

    def footer(self,left='',watermark=True):
        y=self.h*.938
        self.line((self.w*.08,y-self.h*.018,self.w*.92,y-self.h*.018),'grid',max(1,self.h/800))
        self.text(self.w*.08,y,left,max(10,min(self.w/42,self.h/58)),'muted',max_width=self.w*.6)
        if watermark: self.text(self.w*.92,y,'gembaguitar.com',max(11,min(self.w/37,self.h/50)),'muted',True,'rt')


def marker(a,x,y,r,label,root=False,active=False):
    color='active' if active else 'root' if root else 'note'
    if active:
        a.circle(x,y,r+4*a.h/800,None,'active',1.5*a.h/800)
    if root:
        a.rect((x-r,y-r,x+r,y+r),color,radius=r*.35)
    else: a.circle(x,y,r,color)
    a.text(x,y,str(label),r*.94,'on_root' if root and not active else 'on_note',True,'mm',max_width=r*1.65)
