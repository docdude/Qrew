import sys
from PyQt5.QtWidgets import QWidget, QLabel, QApplication
from PyQt5.QtGui import QPixmap, QPainter, QFont
from PyQt5.QtCore import Qt, QTimer

class MicPositionWidget(QWidget):
    def __init__(self, config="5_1"):
        super().__init__()
        self.setFixedSize(600, 400)
        self.config = None
        self.bg_pixmap = QPixmap()
        self.mic_coords = self._define_positions()
        self.labels = {}
        self.flash_timer = QTimer(self)
        self.flash_state = True
        self.active_mic = None
        self._setup_ui()
        self.set_speaker_configuration(config)

    def _define_positions(self):
        # Approx positions (center at ~300,200)
        return {
            1: (300, 180), 2: (260, 170), 3: (340, 170),
            4: (220, 200), 5: (380, 200),
            6: (260, 230), 7: (340, 230), 8: (300, 240),
        }

    def _setup_ui(self):
        for num, (x, y) in self.mic_coords.items():
            lbl = QLabel(str(num), self)
            lbl.setGeometry(x-12, y-12, 24, 24)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Sans", 10, QFont.Bold))
            lbl.setStyleSheet("background: rgba(0,0,0,150); color: white; border-radius:12px;")
            self.labels[num] = lbl

        self.flash_timer.timeout.connect(self._flash)
        self.flash_timer.start(500)

    def set_active_mic(self, mic_num):
        if mic_num not in self.labels:
            return
        self.active_mic = mic_num
        self._update_labels()

    def _update_labels(self):
        for num, lbl in self.labels.items():
            lbl.setStyleSheet(
                "background:" + ("red" if num == self.active_mic else "rgba(0,0,0,150)") +
                "; color:white; border-radius:12px;"
            )
            lbl.setVisible(True)

    def _flash(self):
        if self.active_mic is None:
            return
        self.flash_state = not self.flash_state
        self.labels[self.active_mic].setVisible(self.flash_state)

    def set_speaker_configuration(self, cfg):
        if cfg == self.config: return
        self.config = cfg
        fname = f"room_{cfg}.png"
        self.bg_pixmap = QPixmap(fname)
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        if not self.bg_pixmap.isNull():
            painter.drawPixmap(self.rect(), self.bg_pixmap)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MicPositionWidget(config="5_1")
    w.show()

    # Test cycling through mic positions every 2 seconds
    def cycle():
        current = w.active_mic or 0
        nxt = current + 1
        if nxt > 8: nxt = 1
        w.set_active_mic(nxt)
    timer = QTimer()
    timer.timeout.connect(cycle)
    timer.start(2000)

    sys.exit(app.exec_())
