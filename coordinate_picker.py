import sys
import json
from PyQt5.QtWidgets import QApplication, QLabel, QWidget, QPushButton
from PyQt5.QtGui import QPixmap, QPainter, QPen, QFont
from PyQt5.QtCore import Qt, QPoint

SPEAKER_LABELS = {
    "C": "Center",
    "FL": "Front Left",
    "FR": "Front Right",
    "SLA": "Surround Left",
    "SRA": "Surround Right",
    "SBL": "Surround Back Left",
    "SBR": "Surround Back Right",
    "TFL": "Top Front Left",
    "TFR": "Top Front Right",
    "TML": "Top Middle Left",
    "TMR": "Top Middle Right",
    "TRL": "Top Rear Left",
    "TRR": "Top Rear Right",
    "FDL": "Front Dolby Left",
    "FDR": "Front Dolby Right",
    "FHL": "Front Height Left",
    "FHR": "Front Height Right",
    "FWL": "Front Wide Left",
    "FWR": "Front Wide Right",
    "RHL": "Rear Height Left",
    "RHR": "Rear Height Right",
    "SDL": "Surround Dolby Left",
    "SDR": "Surround Dolby Right",
    "SHL": "Surround Height Left",
    "SHR": "Surround Height Right",
    "BDL": "Back Dolby Left",
    "BDR": "Back Dolby Right",
    "SW1": "Subwoofer 1",
    "SW2": "Subwoofer 2",
    "SW3": "Subwoofer 3",
    "SW4": "Subwoofer 4"
}


SPEAKER_KEYS = list(SPEAKER_LABELS.keys())
MIC_KEYS = [str(i) for i in range(12)]  # Mic positions 0–13

class CoordinatePicker(QWidget):
    def __init__(self, image_path):
        super().__init__()
        self.setWindowTitle("Precision Coordinate Picker Tool")
        self.image = QPixmap(image_path)
        self.setFixedSize(self.image.size())

        self.speakers = {}
        self.mics = {}
        self.mode = "speakers"
        self.speaker_idx = 0
        self.mic_idx = 0

        self.cursor_pos = QPoint(-1, -1)

        # Save Button
        self.save_button = QPushButton("Save to JSON", self)
        self.save_button.move(10, 10)
        self.save_button.clicked.connect(self.save_to_json)

        # Force repaint on mouse move
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        self.cursor_pos = event.pos()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            if self.mode == "speakers" and self.speaker_idx < len(SPEAKER_KEYS):
                acronym = SPEAKER_KEYS[self.speaker_idx]
                name = SPEAKER_LABELS[acronym]
                self.speakers[acronym] = {"name": name, "x": pos.x(), "y": pos.y()}
                print(f"[SPEAKER] {acronym} ({name}): ({pos.x()}, {pos.y()})")
                self.speaker_idx += 1
                if self.speaker_idx == len(SPEAKER_KEYS):
                    print("🎤 Done with speakers. Now click mic positions.")
                    self.mode = "mics"
            elif self.mode == "mics" and self.mic_idx < len(MIC_KEYS):
                mic_id = MIC_KEYS[self.mic_idx]
                self.mics[mic_id] = {"x": pos.x(), "y": pos.y()}
                print(f"[MIC] Position {mic_id}: ({pos.x()}, {pos.y()})")
                self.mic_idx += 1

            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.image)

        width, height = self.image.width(), self.image.height()
        grid_spacing = 50

        # === Draw grid lines ===
        grid_pen = QPen(Qt.lightGray, 1, Qt.DashLine)
        painter.setPen(grid_pen)

        for x in range(0, width, grid_spacing):
            painter.drawLine(x, 0, x, height)
        for y in range(0, height, grid_spacing):
            painter.drawLine(0, y, width, y)

        # === Draw crosshair ===
        if self.cursor_pos.x() >= 0:
            cross_pen = QPen(Qt.blue, 1, Qt.DotLine)
            painter.setPen(cross_pen)
            painter.drawLine(self.cursor_pos.x(), 0, self.cursor_pos.x(), height)
            painter.drawLine(0, self.cursor_pos.y(), width, self.cursor_pos.y())

            # Coordinate tooltip
            painter.setFont(QFont("Arial", 10))
            coord_text = f"({self.cursor_pos.x()}, {self.cursor_pos.y()})"
            painter.setPen(QPen(Qt.black))
            painter.drawText(self.cursor_pos.x() + 10, self.cursor_pos.y() - 10, coord_text)

        # === Draw points ===
        point_pen = QPen(Qt.red, 3)
        painter.setPen(point_pen)
        painter.setFont(QFont("Arial", 10, QFont.Bold))

        for acronym, data in self.speakers.items():
            x, y = data["x"], data["y"]
            painter.drawEllipse(QPoint(x, y), 6, 6)
            painter.drawText(x + 8, y - 8, acronym)

        for mic_id, data in self.mics.items():
            x, y = data["x"], data["y"]
            painter.drawEllipse(QPoint(x, y), 6, 6)
            painter.drawText(x + 8, y - 8, f"Mic {mic_id}")

    def save_to_json(self):
        layout = {"speakers": self.speakers, "mics": self.mics}
        with open("sofa_coordinates.json", "w") as f:
            json.dump(layout, f, indent=2)
        print("✅ Saved to room_layout.json")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    picker = CoordinatePicker("sofa.png")  # Replace with your PNG
    picker.show()
    sys.exit(app.exec_())
