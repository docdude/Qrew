import sys
import json
import math
from PyQt5.QtWidgets import QWidget, QLabel, QApplication
from PyQt5.QtGui import QPixmap, QPainter, QFont, QPen, QColor
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect

class MicPositionWidget(QWidget):
    def __init__(self, image_path, layout_path):
        super().__init__()
        self.setWindowTitle("Home Theater Speaker + Mic Layout")
        self.background = QPixmap(image_path)
        self.original_size = self.background.size()
        self.current_scale = 1.0
        self.setFixedSize(self.background.size())

        with open(layout_path, "r") as f:
            self.layout_data = json.load(f)

        self.speakers = self.layout_data["speakers"]
        self.mics = self.layout_data["mics"]
        self.labels = {}
        self.mic_labels = {}
        self.speaker_pixmaps = {}
        self.active_mic = None
        self.active_speakers = set()
        self.visible_positions = 9  # Default to show all positions
        self.selected_channels = set()  # Track selected channels

        self.icon_size = 85
        self.base_icon_size = 85  # Store original size for scaling
        self.icon_folder = "../icons_85x85/"
        self.ripple_phase = 0

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update)
        self.animation_timer.start(33)

        self.init_labels()
        
    def set_scale(self, scale_factor):
        """Scale the entire widget and all its elements"""
        self.current_scale = scale_factor
        
        # Scale background
        new_size = self.original_size * scale_factor
        self.background = QPixmap(self.background).scaled(
            new_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        
        # Scale icon size
        self.icon_size = int(self.base_icon_size * scale_factor)
        
        # Resize widget
        self.setFixedSize(new_size)
        
        # Recreate labels with new scale
        self.clear_labels()
        self.init_labels()
        self.update()

    def set_visible_positions(self, num_positions):
        """Show only the specified number of mic positions"""
        self.visible_positions = num_positions
        
        # Update mic label visibility
        for mic_id, label in self.mic_labels.items():
            try:
                mic_num = int(str(mic_id))
                label.setVisible(mic_num < num_positions)
            except ValueError:
                pass
        
        self.update()

    def set_selected_channels(self, channels):
        """Update which channels are selected (for highlighting)"""
        self.selected_channels = set(channels)
        
        # Update speaker label styling
        for key, label in self.labels.items():
            if key in self.selected_channels:
                # Highlight selected speakers
                label.setStyleSheet("""
                    QLabel {
                        background-color: rgba(0, 255, 0, 100);
                        border: 2px solid #00ff00;
                        border-radius: 10px;
                    }
                """)
            else:
                # Normal styling for unselected
                label.setStyleSheet("""
                    QLabel {
                        background-color: transparent;
                        border: 1px solid #666;
                        border-radius: 5px;
                    }
                """)
        
        self.update()

    def clear_labels(self):
        """Clear all existing labels"""
        for label in list(self.labels.values()) + list(self.mic_labels.values()):
            label.deleteLater()
        self.labels.clear()
        self.mic_labels.clear()
        
    def init_labels(self):
        # Speaker labels
        for key, data in self.speakers.items():
            x, y = data["x"], data["y"]
            # Scale coordinates
            x = int(x * self.current_scale)
            y = int(y * self.current_scale)
            
            pix = QPixmap(f"{self.icon_folder}{key}.png")
            self.speaker_pixmaps[key] = pix

            lbl = QLabel(self)
            if not pix.isNull():
                lbl.setPixmap(pix.scaled(self.icon_size, self.icon_size, 
                                       Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                lbl.setText(key)
                lbl.setStyleSheet("background-color: black; color: white; border-radius: 10px;")
            
            lbl.setGeometry(x - self.icon_size // 2, y - self.icon_size // 2, 
                          self.icon_size, self.icon_size)
            lbl.setToolTip(data["name"])
            self.labels[key] = lbl
            lbl.show()

        # Mic dots
        for mic_id, data in self.mics.items():
            x, y = data["x"], data["y"]
            # Scale coordinates
            x = int(x * self.current_scale)
            y = int(y * self.current_scale)
            
            # Scale mic dot size
            dot_size = int(20 * self.current_scale)
            font_size = max(8, int(11 * self.current_scale))
            
            lbl = QLabel(str(mic_id), self)
            lbl.setGeometry(x - dot_size//2, y - dot_size//2, dot_size, dot_size)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Monaco", font_size, QFont.Bold))
            lbl.setStyleSheet("background-color: red; color: white; border-radius: 10px;")
            
            # Set initial visibility based on visible_positions
            try:
                mic_num = int(str(mic_id))
                lbl.setVisible(mic_num < self.visible_positions)
            except ValueError:
                lbl.setVisible(True)
            
            self.mic_labels[mic_id] = lbl
            lbl.show()

    def set_active_mic(self, mic_id):
        self.active_mic = str(mic_id)

    def set_active_speakers(self, keys):
        self.active_speakers = set(keys)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.background)
        self.ripple_phase = (self.ripple_phase + 1) % 60

        # Scale animation elements
        base_radius = int(12 * self.current_scale)
        glow_radius = int(30 * self.current_scale)
        wave_base = int(20 * self.current_scale)
        wave_max = int(60 * self.current_scale)

        # Mic animation
        if self.active_mic:
            data = self.mics.get(self.active_mic)
            if data:
                x = int(data["x"] * self.current_scale)
                y = int(data["y"] * self.current_scale)
                radius = base_radius + int(4 * abs((self.ripple_phase % 30) - 15) / 15 * self.current_scale)
                pen = QPen(QColor(255, 0, 0, 180))
                pen.setWidth(max(1, int(2 * self.current_scale)))
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPoint(x, y), radius, radius)

        # Speaker animations  
        for key in self.active_speakers:
            if key in self.speakers:
                x = int(self.speakers[key]["x"] * self.current_scale)
                y = int(self.speakers[key]["y"] * self.current_scale)

                # Glow Effect
                glow_color = QColor(0, 255, 0, 80)
                painter.setBrush(glow_color)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPoint(x, y), glow_radius, glow_radius)

                # Pulse Ring Wave
                steps = 4
                offset_x = int(2 * self.current_scale)
                offset_y = int(-1 * self.current_scale)

                for i in range(steps):
                    phase = (self.ripple_phase + i * 20) % 60
                    opacity = int(250 * (1 - phase / 60))
                    radius = wave_base + int((phase / 60) * wave_max)
                    pen = QPen(QColor(0, 255, 0, opacity))
                    pen.setWidth(max(1, int(2 * self.current_scale)))
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(QPoint(x + offset_x, y + offset_y), radius, radius)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = MicPositionWidget("hometheater_base_persp.png", "room_layout_persp.json")
    widget.set_active_mic(0)

    # Test: Cycle mic + animate 2 speakers
    test_speakers = ["TML", "FR"]
    mic_keys = list(widget.mic_labels.keys())
    mic_index = [0]

    def update_animation():
        mic_index[0] = (mic_index[0] + 1) % len(mic_keys)
        widget.set_active_mic(mic_keys[mic_index[0]])
        widget.set_active_speakers(test_speakers)

    test_timer = QTimer()
    test_timer.timeout.connect(update_animation)
    test_timer.start(2000)

    widget.show()
    sys.exit(app.exec_())
