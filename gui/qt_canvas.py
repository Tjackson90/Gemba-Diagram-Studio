"""A scalable, pannable canvas and an interactive six-string fingering editor."""
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QImage, QFont
from PySide6.QtWidgets import QWidget


class DiagramCanvas(QWidget):
    zoomChanged=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.image=None
        self.zoom=1.
        self.offset=QPointF()
        self.drag=None
        self.guides=False
        self.art_background='#12161c'
        self.setMinimumSize(300,260)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAccessibleName('Diagram canvas. Drag to pan, Control plus wheel to zoom.')

    def set_image(self,image):
        self.art_background=image.info.get('background','#12161c')
        rgba=image.convert('RGBA')
        self.image=QImage(rgba.tobytes(),rgba.width,rgba.height,QImage.Format.Format_RGBA8888).copy()
        self.update()

    def fit(self):
        self.zoom=1.
        self.offset=QPointF()
        self.update()
        self.zoomChanged.emit('Fit')

    def zoom_by(self,factor):
        self.zoom=max(.3,min(5.,self.zoom*factor))
        self.zoomChanged.emit(f'{self.zoom*100:.0f}%')
        self.update()

    def wheelEvent(self,event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.12 if event.angleDelta().y()>0 else 1/1.12)
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.drag=event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self,event):
        if self.drag is not None:
            self.offset+=event.position()-self.drag
            self.drag=event.position()
            self.update()

    def mouseReleaseEvent(self,event):
        self.drag=None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#202b2b'))
        p.drawRoundedRect(self.rect(),14,14)
        p.setPen(QColor('#33403e'))
        for x in range(18,self.width(),22):
            for y in range(18,self.height(),22): p.drawPoint(x,y)
        if self.image:
            scale=min((self.width()-80)/self.image.width(),(self.height()-74)/self.image.height())*self.zoom
            w,h=self.image.width()*scale,self.image.height()*scale
            rect=QRectF((self.width()-w)/2+self.offset.x(),(self.height()-h)/2+self.offset.y(),w,h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0,0,0,35))
            p.drawRoundedRect(rect.adjusted(-5,0,7,11),8,8)
            p.setBrush(QColor(self.art_background))
            p.drawRoundedRect(rect.adjusted(-1,-1,1,1),6,6)
            p.drawImage(rect,self.image)
            if self.guides:
                p.setPen(QPen(QColor('#d1b775'),1,Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(rect.adjusted(w*.05,h*.05,-w*.05,-h*.05))
        p.setFont(QFont('DM Sans',9))
        p.setPen(QColor('#91a19a'))
        p.drawText(18,self.height()-17,'LIVE PREVIEW')
        p.drawText(self.width()-150,self.height()-17,'Ctrl + scroll to zoom')
        p.end()


class FingeringEditor(QWidget):
    changed=Signal(list)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.frets=[-1,0,2,0,1,0]
        self.start=1
        self.left_handed=False
        self.setFixedHeight(235)
        self.setAccessibleName('Fingering editor. Click a string and fret; click above the nut to toggle open or muted.')

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        left,right,top,step=25,self.width()-20,45,32
        for fret in range(6):
            p.setPen(QPen(QColor('#c1c8b7'),3 if fret==0 and self.start==1 else 1))
            p.drawLine(left,top+fret*step,right,top+fret*step)
        for i in range(6):
            col=5-i if self.left_handed else i
            x=left+col*(right-left)/5
            p.setPen(QPen(QColor('#75816b'),1.4-i*.14))
            p.drawLine(QPointF(x,top),QPointF(x,top+5*step))
            p.setPen(QColor('#58654f'))
            f=self.frets[i]
            p.drawText(QRectF(x-10,15,20,22),Qt.AlignmentFlag.AlignCenter,'×' if f<0 else '○' if f==0 else '')
            if self.start<=f<self.start+5:
                y=top+(f-self.start+.5)*step
                p.setBrush(QColor('#33543e')); p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(x,y),10,10)
                p.setPen(QColor('white'))
                p.drawText(QRectF(x-10,y-10,20,20),Qt.AlignmentFlag.AlignCenter,str(f))
        p.setPen(QColor('#78836e'))
        p.drawText(5,top+20,str(self.start))
        p.end()

    def mousePressEvent(self,event):
        x,y=event.position().x(),event.position().y()
        col=round((x-25)/(self.width()-45)*5)
        if not 0<=col<=5 or not 10<=y<=205: return
        i=5-col if self.left_handed else col
        fret=self.start+int((y-45)//32) if y>=45 else (0 if self.frets[i]<0 else -1)
        fret=min(24,fret)
        self.frets[i]=-1 if self.frets[i]==fret and fret>0 else fret
        self.changed.emit(list(self.frets)); self.update()
