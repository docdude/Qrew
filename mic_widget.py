import sys
import json
from PyQt5.QtWidgets import QWidget, QLabel, QApplication
from PyQt5.QtGui import QPixmap, QPainter, QFont, QPen
from PyQt5.QtCore import Qt, QTimer, QPoint

class MicPositionWidget(QWidget):
    def __init__(self, image_path, layout_path):
        super().__init__()
        self.setWindowTitle("Home Theater Speaker + Mic Layout")
        self.background = QPixmap(image_path)
        self.setFixedSize(self.background.size())

        with open(layout_path, "r") as f:
            self.layout_data = json.load(f)

        self.speakers = self.layout_data["speakers"]
        self.mics = self.layout_data["mics"]
        self.labels = {}
        self.mic_labels = {}
        self.active_mic = None
        self.flash_state = True

        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self.toggle_flash)
        self.flash_timer.start(500)

        self.init_labels()

    def init_labels(self):
        icon_size = 40  # Size of speaker icons
        icon_folder = "/Users/juanloya/Documents/qrew/icons/"  # Folder containing your speaker PNGs

        # Load speaker PNGs at given positions
        for key, data in self.speakers.items():
            x, y = data["x"], data["y"]
            lbl = QLabel(self)
            pix = QPixmap(f"{icon_folder}{key}.png")
            if not pix.isNull():
                lbl.setPixmap(pix.scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                lbl.setText(key)
                lbl.setStyleSheet("background-color: black; color: white; border-radius: 10px;")
            lbl.setGeometry(x - icon_size // 2, y - icon_size // 2, icon_size, icon_size)
            lbl.setToolTip(data["name"])
            self.labels[key] = lbl
            lbl.show()

        # Mic labels remain as red dots
        for mic_id, data in self.mics.items():
            x, y = data["x"], data["y"]
            lbl = QLabel(str(mic_id), self)
            lbl.setGeometry(x - 10, y - 10, 20, 20)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Arial", 8, QFont.Bold))
            lbl.setStyleSheet("background-color: red; color: white; border-radius: 10px;")
            self.mic_labels[mic_id] = lbl
            lbl.show()


        # Mic position placeholders
        for mic_id, data in self.mics.items():
            x, y = data["x"], data["y"]
            lbl = QLabel(str(mic_id), self)
            lbl.setGeometry(x - 10, y - 10, 20, 20)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Arial", 8, QFont.Bold))
            lbl.setStyleSheet("background-color: red; color: white; border-radius: 10px;")
            self.mic_labels[mic_id] = lbl
            lbl.show()

    def set_active_mic(self, mic_id):
        if mic_id not in self.mic_labels:
            return
        self.active_mic = str(mic_id)
        for k, lbl in self.mic_labels.items():
            lbl.setStyleSheet("background-color: red; color: white; border-radius: 10px;")
            lbl.setVisible(True)

    def toggle_flash(self):
        if self.active_mic is not None:
            lbl = self.mic_labels.get(self.active_mic)
            if lbl:
                self.flash_state = not self.flash_state
                lbl.setVisible(self.flash_state)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.background)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = MicPositionWidget("/Users/juanloya/Documents/qrew/qrew/hometheater_base_persp.png", "/Users/juanloya/Documents/qrew/qrew/room_layout_persp.jsonroom_layout_persp.json")
    widget.set_active_mic(0)  # Default flashing MLP (0)
    widget.show()

    # Optional: cycle through mic positions
    def next_mic():
        current = int(widget.active_mic or 0)
        next_id = str((current + 1) % len(widget.mics))
        widget.set_active_mic(next_id)

    cycle_timer = QTimer()
    cycle_timer.timeout.connect(next_mic)
    cycle_timer.start(2000)  # Switch every 2 seconds

    sys.exit(app.exec_())
