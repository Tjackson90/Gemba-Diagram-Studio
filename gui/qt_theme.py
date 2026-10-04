"""Shared desktop typography, colors and small vector icons."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

STYLE = '''
* { font-family: "DM Sans", "Segoe UI"; font-size: 13px; color: #282b32; }
QMainWindow, QDialog { background: #f6f5f1; }
QWidget#Root, QWidget#Center { background: #f6f5f1; }
QWidget#InspectorPage { background: #fcfbf8; }
QFrame#Rail { background: #eeede7; border-right: 1px solid #deded7; }
QFrame#Inspector { background: #fcfbf8; border-left: 1px solid #deded7; }
QFrame#Header { background: #fcfbf8; border-bottom: 1px solid #deded7; }
QFrame#Transport { background: #fcfbf8; border: 1px solid #e0e0d9; border-radius: 12px; }
QLabel#Brand { font-size: 24px; font-weight: 700; letter-spacing: -1px; }
QLabel#PageTitle { font-size: 23px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#Caption { color: #787c7c; font-size: 11px; }
QLabel#Section { color: #81857f; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; }
QLabel#PanelTitle { font-size: 17px; font-weight: 700; }
QLabel#Hint { color: #777c7b; font-size: 12px; }
QLabel#Badge { background: #ebe9df; color: #62644f; border-radius: 6px; padding: 5px 9px; font-size: 11px; }
QPushButton { background: #fcfbf8; border: 1px solid #d9dcd5; border-radius: 7px; padding: 8px 12px; font-weight: 500; }
QPushButton:hover { background: #eeeee5; border-color: #afb8a5; }
QPushButton:pressed { background: #e0e3d6; }
QPushButton:focus { border: 1px solid #63845b; }
QPushButton:disabled { color: #a2a49f; background: #eeeee9; }
QPushButton#Primary { background: #284f40; border-color: #284f40; color: white; font-weight: 700; }
QPushButton#Primary:hover { background: #36644f; }
QPushButton#Primary:disabled { background: #809487; border-color: #809487; }
QPushButton#Nav { text-align: left; padding: 11px 12px; border: 0; background: transparent; color: #6b706b; }
QPushButton#Nav:hover { background: #e6e6dd; color: #263f35; }
QPushButton#Nav:checked { background: #dde5d6; color: #244732; font-weight: 700; }
QPushButton#Quiet { background: transparent; border: 0; color: #666e67; }
QPushButton#Quiet:hover { background: #e8eae2; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background: #fffefa; border: 1px solid #dcded6; border-radius: 6px; padding: 8px; min-height: 18px; selection-background-color: #dce7d5; selection-color: #263e31; }
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus { border-color: #718d64; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #fffefa; selection-background-color: #e1e9d8; selection-color: #263e31; border: 1px solid #d8ddcf; padding: 4px; }
QCheckBox { spacing: 9px; padding: 5px 0; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #b4bca9; border-radius: 3px; background: #fffefa; }
QCheckBox::indicator:checked { background: #476643; border: 3px solid #b7c7a9; }
QGroupBox { border: 0; border-top: 1px solid #e4e5dd; margin-top: 22px; padding-top: 18px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; top: 3px; }
QScrollArea { background: transparent; border: 0; }
QScrollBar:vertical { width: 7px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: #c7cec1; border-radius: 3px; min-height: 35px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QSlider::groove:horizontal { height: 4px; background: #dce0d5; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #627c52; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; margin: -4px 0; border-radius: 6px; background: #38533a; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 10px 14px; color: #84887e; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #294d35; border-bottom: 2px solid #547144; }
QListWidget { background: #fffefa; border: 1px solid #dedfd7; border-radius: 8px; padding: 5px; outline: 0; }
QListWidget::item { padding: 10px; border-radius: 5px; }
QListWidget::item:selected { background: #e0e8d7; color: #2e4d36; }
QMenu { background: #fffefa; border: 1px solid #d8ddd0; padding: 6px; }
QMenu::item { padding: 8px 26px 8px 12px; }
QMenu::item:selected { background: #e0e8d7; border-radius: 4px; }
QMenuBar { background: #fcfbf8; }
QMenuBar::item:selected { background: #e0e8d7; }
QStatusBar { background: #f6f5f1; color: #6c7369; font-size: 11px; border-top: 1px solid #e1e3da; }
QProgressBar { border: 0; background: #e4e8db; border-radius: 2px; max-height: 3px; }
QProgressBar::chunk { background: #648453; }
QToolTip { color: #f8f7f2; background: #2e3d32; border: 0; padding: 6px; }
'''


def icon(kind, color='#667263'):
    pix = QPixmap(40,40)
    pix.fill(Qt.GlobalColor.transparent)
    pix.setDevicePixelRatio(2)
    p=QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color),1.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
    if kind in ('Chord','ChordLookup','ChordID'):
        for x in (4,8,12,16): p.drawLine(x,3,x,17)
        for y in (4,9,14): p.drawLine(4,y,16,y)
        p.setBrush(QColor(color)); p.drawEllipse(6,6,4,4); p.drawEllipse(10,11,4,4)
    elif kind in ('Scale','Arpeggio','Triads'):
        for i in range(3):
            p.drawLine(3,5+i*5,17,5+i*5)
            p.setBrush(QColor(color)); p.drawEllipse(4+i*4,3+i*5,4,4)
    elif kind in ('undo','redo'):
        if kind=='redo': p.translate(20,0); p.scale(-1,1)
        p.drawArc(4,5,12,11,-60*16,235*16)
        p.drawLine(3,3,3,9); p.drawLine(3,9,9,9)
    elif kind=='star':
        from math import sin, cos, pi
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        points=[QPointF(10+(8 if i%2==0 else 3.7)*sin(i*pi/5),10-(8 if i%2==0 else 3.7)*cos(i*pi/5)) for i in range(10)]
        p.drawPolygon(QPolygonF(points))
    elif kind=='play':
        from PySide6.QtGui import QPolygon
        from PySide6.QtCore import QPoint
        p.setBrush(QColor(color)); p.drawPolygon(QPolygon([QPoint(6,3),QPoint(16,10),QPoint(6,17)]))
    else:
        for i in range(3): p.drawRoundedRect(3+i*5,4,3,12,1,1)
    p.end()
    return QIcon(pix)
