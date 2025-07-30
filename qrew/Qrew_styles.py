# Qrew_styles.py
"""Centralized style definitions for the application"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPainter, QPalette, QBrush, QColor, QImageReader


# HTML Icons for UI
HTML_ICONS = {
    "warning": "&#9888;",  # ⚠️
    "no_entry": "&#128683;",
    "check": "&#10004;",  # ✓
    "cross": "&#10060;",  # ❌
    "circle_red": "&#11044;",  # ⭕ (colored via CSS)
    "circle_green": "&#11044;",  # ⭕ (colored via CSS)
    "circle_yellow": "&#11044;",  # ⭕ (colored via CSS)
    "info": "&#8505;",  # ℹ️
    "star": "&#9733;",  # ★
    "bullet": "&#8226;",  # •
    "arrow_right": "&#8594;",  # →
    "arrow_up": "&#8593;",  # ↑
    "arrow_down": "&#8595;",  # ↓
    "gear": "&#9881;",  # ⚙️
    "home": "&#8962;",  # ⌂
    "play": "&#9654;",  # ▶
    "stop": "&#9632;",  # ■
    "pause": "&#9208;",  # ⏸
    "raised_hand": "&#9995;",
}


def get_dark_palette():
    """
    App dark theme
    """
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#262626"))
    pal.setColor(QPalette.WindowText, QColor("#f0f0f0"))
    pal.setColor(QPalette.Base, QColor("#1e1e1e"))
    pal.setColor(QPalette.Text, QColor("#ffffff"))
    pal.setColor(QPalette.Button, QColor("#3a3a3a"))
    pal.setColor(QPalette.ButtonText, QColor("#f0f0f0"))
    pal.setColor(QPalette.Highlight, QColor("#009fe3"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    return pal


def get_light_palette():
    """
    App light theme
    """
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#f0f0f0"))
    pal.setColor(QPalette.WindowText, QColor("#000000"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.Text, QColor("#000000"))
    pal.setColor(QPalette.Button, QColor("#e0e0e0"))
    pal.setColor(QPalette.ButtonText, QColor("#000000"))
    pal.setColor(QPalette.Highlight, QColor("#3399ff"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    return pal


def tint(pix: QPixmap, color: QColor) -> QPixmap:
    """Return a color-tinted copy of *pix* (preserves alpha)."""
    tinted = QPixmap(pix.size())
    # tinted = QtGui.QPixmap(pix.size())       # physical size
    tinted.setDevicePixelRatio(pix.devicePixelRatio())  # preserve DPR

    tinted.fill(Qt.transparent)

    p = QPainter(tinted)
    p.setCompositionMode(QPainter.CompositionMode_Source)
    p.drawPixmap(0, 0, pix)  # alpha mask
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(tinted.rect(), color)  # tint
    p.end()
    return tinted


def load_high_quality_image(
    path, scale_to=None, transform_mode=Qt.SmoothTransformation
):
    """
    Load an image with high quality settings.

    :param path: Path to the image file.
    :param scale_to: Tuple (width, height) if scaling is desired.
    :param transform_mode: Qt.FastTransformation or Qt.SmoothTransformation.
    :return: QPixmap with high-quality rendering.
    """
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    image = reader.read()

    if image.isNull():
        print(f"Warning: Failed to load image from {path}")
        return QPixmap()

    if scale_to:
        image = image.scaled(*scale_to, Qt.KeepAspectRatio, transform_mode)

    return QPixmap.fromImage(image)


def set_background_image(widget):
    """
    Set up background image for mainwindow and micpostion widget
    """
    if getattr(widget, "bg_source", None) is None:
        return

    if widget.bg_source.isNull():
        return  # missing file

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
    "primary": """
        QPushButton {
            background-color: #4CAF50;
            color: white;
            border: 1px solid #45a049;
            padding: 6px 8px;
            font-size: 14px;
            font-weight: bold;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
    """,
    "primary_default": """
                QPushButton {
                background-color: #4CAF50;
                color: white;
                border: 1px solid #45a049;
                padding: 6px 8px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:default {
                border: 2px solid #2e7d32;
            }
    """,
    "primary_disabled": """
                QPushButton {
                background-color: #4CAF50;
                color: white;
                border: 1px solid #45a049;
                padding: 6px 8px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
                border: 1px solid #999;
            }
    """,
    "secondary": """
        QPushButton {
            background-color: #7a7a7a;
            border: 1px solid #ccc;
            padding: 6px 8px;
            font-size: 14px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #e5e5e5;
        }
    """,
    "danger": """
        QPushButton {
            background-color: rgba(244, 67, 54, 0.8);
            color: white;
            border: 1px solid #d32f2f;
            padding: 6px 8px;
            font-size: 12px;
            font-weight: bold;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #d32f2f;
        }
    """,
    "warning": """
        QPushButton {
            background-color: #ff9800;
            color: white;
            border: 1px solid #f57c00;
            padding: 6px 8px;
            font-size: 12px;
            font-weight: bold;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #f57c00;
        }
    """,
    "info": """
        QPushButton {
            background-color: #2196F3;
            color: white;
            border: 1px solid #1976D2;
            padding: 6px 8px;
            font-size: 14px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #1976D2;
        }
    """,
    "transparent": """
        QPushButton { 
            background-color: rgba(51, 51, 51, 0.8);
            color: white;
            border: 1px solid #666;
            border-radius: 4px;
            padding: 6px 8px;
            font-size: 12px;
            font-weight: normal;
        }
    """,
    "transparent_small": """
        QPushButton {
            background-color: rgba(51, 51, 51, 0.8);
            color: white; 
            border: 1px solid #666;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 10px;
            font-weight: normal;
        }
    """,
}


CHECKBOX_STYLE = {
    "default": """
        QCheckBox {
            padding: 3px;
        }
        QCheckBox::indicator {
            width: 15px;
            height: 15px;
            border: 1px solid #888;
            border-radius: 3px;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #eee, 
                stop:1 #bbb
            );
        }
        QCheckBox::indicator:checked {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #aaffaa,
                stop:1 #55aa55);
                border: 1px solid #444;
        }
    """,
    "main": """
        QCheckBox {
        padding: 3px; 
        color: "#00A2FF";
        font-size: 14px;
        }
        QCheckBox::indicator {
            width: 15px;
            height: 15px;
            border: 1px solid #888;
            border-radius: 3px;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #eee,
                stop:1 #bbb
            );
        }
        QCheckBox::indicator:checked {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #aaffaa, 
                stop:1 #55aa55);
            border: 1px solid #444;
        }
    """,
}

GROUPBOX_STYLE = """
    QGroupBox {
        background: rgba(0, 0, 0, 0.8);
        color: #fff;
        font-weight: bold;
        font-size: 12px;
        border: 2px solid #999;
        border-radius: 5px;
        margin-top: 5px;          /* space above frame */
        padding-top: 0px;         /* space below title */
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0px 5px 0px 5px;
    }
"""

COMBOBOX_STYLE = """
    QComboBox {
        border: 2px solid gray;
        border-radius: 4px;
        padding: 1px 22px 1px 6px;    
        selection-background-color: #263238;
        selection-color: lightgreen;
        color: white;
        background: rgba(69, 90, 100, 0.80);   /* 50 % opacity black */
        color: white;
        font-size: 14px;
    }
    QComboBox QListView {
        background-color: #455A64;
    }

"""

GLOBAL_STYLE = """
    * {
        font-family: "Monaco";
    }
    QToolTip {
        color: white;
        background-color: #353535;
        border: 1px solid gray;
        border-radius: 2px;
        padding: 2px;
        opacity: 230;
    }
"""
