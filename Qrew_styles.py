# Qrew_styles.py
"""Centralized style definitions for the application"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPainter, QPalette, QBrush, QColor

# HTML Icons for UI
HTML_ICONS = {
    'warning': '&#9888;',        # ⚠️
    'no_entry': '&#128683;',
    'check': '&#10004;',         # ✓
    'cross': '&#10060;',         # ❌
    'circle_red': '&#11044;',    # ⭕ (colored via CSS)
    'circle_green': '&#11044;',  # ⭕ (colored via CSS)
    'circle_yellow': '&#11044;', # ⭕ (colored via CSS)
    'info': '&#8505;',           # ℹ️
    'star': '&#9733;',           # ★
    'bullet': '&#8226;',         # •
    'arrow_right': '&#8594;',    # →
    'arrow_up': '&#8593;',       # ↑
    'arrow_down': '&#8595;',     # ↓
    'gear': '&#9881;',           # ⚙️
    'home': '&#8962;',           # ⌂
    'play': '&#9654;',           # ▶
    'stop': '&#9632;',           # ■
    'pause': '&#9208;',          # ⏸
    'raised_hand': '&#9995;'
}

def tint(pix: QPixmap, color: QColor) -> QPixmap:
    """Return a color-tinted copy of *pix* (preserves alpha)."""
    tinted = QPixmap(pix.size())
    #tinted = QtGui.QPixmap(pix.size())       # physical size
    tinted.setDevicePixelRatio(pix.devicePixelRatio())  # preserve DPR

    tinted.fill(Qt.transparent)

    p = QPainter(tinted)
    p.setCompositionMode(QPainter.CompositionMode_Source)
    p.drawPixmap(0, 0, pix)                    # alpha mask
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(tinted.rect(), color)           # tint
    p.end()
    return tinted



# qrew_styles.py  (already in your project)
def set_background_image(widget):
    if getattr(widget, "bg_source", None) is None:
        return

    if widget.bg_source.isNull():
        return                                            # missing file

    # --- scale -----------------------------------------
    scaled = widget.bg_source.scaled(
        widget.size(),
        Qt.KeepAspectRatioByExpanding,
        Qt.SmoothTransformation,
    )

    canvas = QPixmap(scaled.size())
    canvas.fill(Qt.transparent)

    p = QPainter(canvas)
    p.setOpacity(getattr(widget, "bg_opacity", 0.35))
    p.drawPixmap(0, 0, scaled)
    p.end()

    pal = widget.palette()
    pal.setBrush(QPalette.Window, QBrush(canvas))
    widget.setPalette(pal)
    widget.setAutoFillBackground(True)


BUTTON_STYLES = {
    'primary': '''
        QPushButton {
            background-color: #4CAF50;
            color: white;
            border: 1px solid #45a049;
            padding: 8px;
            font-size: 14px;
            font-weight: bold;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
    ''',
    
    'secondary': '''
        QPushButton {
            background-color: #7a7a7a;
            border: 1px solid #ccc;
            padding: 8px;
            font-size: 14px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #e5e5e5;
        }
    ''',
    
    'danger': '''
        QPushButton {
            background-color: #f44336;
            color: white;
            border: 1px solid #d32f2f;
            padding: 8px;
            font-size: 14px;
            font-weight: bold;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #d32f2f;
        }
    ''',
    
    'warning': '''
        QPushButton {
            background-color: #ff9800;
            color: white;
            border: 1px solid #f57c00;
            padding: 8px;
            font-size: 14px;
            font-weight: bold;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #f57c00;
        }
    ''',
    
    'info': '''
        QPushButton {
            background-color: #2196F3;
            color: white;
            border: 1px solid #1976D2;
            padding: 8px;
            font-size: 14px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #1976D2;
        }
    ''',
    
    'transparent': '''
        QPushButton { 
            background: rgba(51, 51, 51, 0.5); 
            color: white; 
            border: 1px solid #666;
            border-radius: 4px;
            padding: 6px 8px;
            font-size: 12px;
        }
    '''
}

CHECKBOX_STYLE = '''
    QCheckBox {
        padding: 3px;
    }
    QCheckBox::indicator {
        width: 15px;
        height: 15px;
        border: 1px solid #888;
        border-radius: 3px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 #eee, stop:1 #bbb);
    }
    QCheckBox::indicator:checked {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 #aaffaa, stop:1 #55aa55);
        border: 1px solid #444;
    }
'''

GROUPBOX_STYLE = '''
    QGroupBox {
        font-weight: bold;
        font-size: 14px;
        border: 2px solid #ccc;
        border-radius: 5px;
        margin-top: 10px;
        padding-top: 0px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px 0 5px;
    }
'''
