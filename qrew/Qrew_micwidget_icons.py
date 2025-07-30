import sys
import json

from PyQt5.QtWidgets import QWidget, QLabel, QApplication
from PyQt5.QtGui import QPixmap, QPainter, QFont, QPen, QColor
from PyQt5.QtCore import Qt, QTimer, QPoint, QFile, QTextStream

try:
    from . import Qrew_resources
    from .Qrew_styles import load_high_quality_image
except ImportError:
    import Qrew_resources
    from Qrew_styles import load_high_quality_image


class MicPositionWidget(QWidget):
    """Widget to display mic positions and speaker icons on a background image.
    Allows scaling, flashing effects, and selection of active mic/speakers.
    """

    def __init__(self, image_path, layout_path):
        super().__init__()
        self.setWindowTitle("Home Theater Speaker + Mic Layout")
        self.original_background = load_high_quality_image(image_path)
        #  self.original_background = QPixmap(image_path)  # pristine copy
        self.background = self.original_background  # keep existing name
        self.original_size = self.background.size()
        self.current_scale = 1.0
        self.setFixedSize(self.background.size())

        self.layout_data = self._load_json(layout_path)
        self.speakers = self.layout_data["speakers"]
        self.mics = self.layout_data["mics"]
        self.labels = {}
        self.mic_labels = {}
        self.speaker_pixmaps = {}
        self.active_mic = None
        self.active_speakers = set()
        self.visible_positions = 12  # Default to show all positions
        self.selected_channels = set()  # Track selected channels
        self.flash_state = False  # Track flash state
        self.show_speaker_icons = True  # Control speaker icon visibility

        self._painting = False  # Prevent re-entrant paintEvent calls

        self.icon_size = 85
        self.base_icon_size = 85  # Store original size for scaling

        self.ripple_phase = 0

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update)
        self.animation_timer.start(33)

        self.init_labels()

    # ────────────────────────────────────────────────────────────
    # helper that understands both normal paths and Qt resources
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def _load_json(path):
        if path.startswith(":/"):  # Qt resource
            qf = QFile(path)
            if not qf.open(QFile.ReadOnly | QFile.Text):
                raise FileNotFoundError(f"Cannot open Qt-resource {path}")
            data = bytes(qf.readAll()).decode("utf-8")
            qf.close()
            return json.loads(data)
        else:  # normal file
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    def set_flash_state(self, is_flashing):
        """Set whether animations should be flashing"""
        self.flash_state = is_flashing
        self.update()

    def set_show_speaker_icons(self, show):
        """Control whether speaker icons are shown"""
        self.show_speaker_icons = show
        self.update_speaker_visibility()

    def update_speaker_visibility(self):
        """Update visibility of speaker labels based on selection"""
        for key, label in self.labels.items():
            # Simply show or hide based on selection
            if key in self.selected_channels:
                label.show()
            else:
                label.hide()

    def set_scale(self, scale_factor):
        """Scale the entire widget and all its elements"""
        if scale_factor <= 0:
            scale_factor = 0.1  # Minimum scale
        scale_factor = max(0.05, scale_factor - 0.002)

        self.current_scale = scale_factor

        # Scale background
        new_size = self.original_size * scale_factor
        #  self.background = QPixmap(self.background).scaled(
        #     new_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        # )
        self.setFixedSize(new_size)  # size of the widget itself

        # ----------------------------------------------------------------
        #  Hi-DPI fix:
        #  Scale the ORIGINAL picture to *physical* pixels and then
        #  tag the pixmap with its DPR so Qt will blit it 1:1.
        # ----------------------------------------------------------------
        dpr = self.devicePixelRatioF()  # usually 1.0 or 2.0 on macOS
        phys_w = int(new_size.width() * dpr)
        phys_h = int(new_size.height() * dpr)

        scaled_img = self.original_background.toImage().scaled(
            phys_w,
            phys_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,  # high-quality resize once
        )
        sharp_pix = QPixmap.fromImage(scaled_img)
        sharp_pix.setDevicePixelRatio(dpr)  # <<< tell Qt the real DPR
        self.background = sharp_pix
        # Scale icon size
        self.icon_size = max(
            int(self.base_icon_size * scale_factor), 10
        )  # Minimum icon size

        # Resize widget
        self.setFixedSize(new_size)

        # Store current selections before recreating
        current_selected = self.selected_channels.copy()
        current_visible_positions = self.visible_positions

        # Recreate labels with new scale
        self.clear_labels()
        self.init_labels()

        # Restore selections and visibility
        self.set_selected_channels(list(current_selected))
        self.set_visible_positions(current_visible_positions)

        self.update()

    # Add new method to set visible positions from a specific list:
    def set_visible_positions_list(self, position_list):
        """Show only the positions specified in the list"""
        # Update mic label visibility based on specific position list
        for mic_id, label in self.mic_labels.items():
            try:
                mic_num = int(str(mic_id))
                label.setVisible(mic_num in position_list)
            except ValueError:
                label.setVisible(False)  # Hide if can't parse as number

        self.update()

    # Keep the existing set_visible_positions method for normal operation:
    def set_visible_positions(self, num_positions):
        """Show only the specified number of mic positions (0 to num_positions-1)"""
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
        self.update_speaker_visibility()
        self.update()

    def clear_labels(self):
        """Clear all existing labels"""
        for label in list(self.labels.values()) + list(self.mic_labels.values()):
            label.deleteLater()
        self.labels.clear()
        self.mic_labels.clear()

    def init_labels(self):
        """Initialize speaker and mic labels based on layout data"""

        for key, data in self.speakers.items():
            x, y = data["x"], data["y"]
            # Scale coordinates
            x = int(x * self.current_scale)
            y = int(y * self.current_scale)

            # pix = QPixmap(f":/icons/{key}.png")
            pix = load_high_quality_image(
                f":/assets/spkr_icons/{key}.png",
                scale_to=(self.icon_size, self.icon_size),
            )
            self.speaker_pixmaps[key] = pix

            lbl = QLabel(self)
            if not pix.isNull():
                lbl.setPixmap(pix)
            else:
                lbl.setText(key)
            #  lbl.setStyleSheet("background-color: black; color: white; border-radius: 10px;")

            lbl.setGeometry(
                x - self.icon_size // 2,
                y - self.icon_size // 2,
                self.icon_size,
                self.icon_size,
            )
            lbl.setToolTip(data["name"])
            self.labels[key] = lbl
            # Only show if it's selected AND we're showing icons
            lbl.hide()
            # lbl.show()

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
            lbl.setGeometry(x - dot_size // 2, y - dot_size // 2, dot_size, dot_size)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(QFont("Arial", font_size, QFont.Bold))
            lbl.setStyleSheet(
                f"""
                background-color: red;
                color: white;
                border-radius: {dot_size // 2}px;
                font-family: Arial;
                font-size: {font_size}px;
                font-weight: 600;
                """
            )

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
        if not self.isVisible():  # <-- guard ①
            return
        if getattr(self, "_painting", False):
            return  # <-- guard ②   (re-entrancy blocker)
        self._painting = True
        try:
            p = QPainter(self)
            ...
        finally:
            p.end()
            self._painting = False
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, self.background)
        # Only animate ripple if flash state is true
        if self.flash_state and (self.active_mic is not None or self.active_speakers):
            self.ripple_phase = (self.ripple_phase + 1) % 60
        else:
            self.ripple_phase = 0  # Reset phase when not flashing
        # Scale animation elements
        dot_wave_base = int(12 * self.current_scale)
        #   dot_wave_max = int(20 * self.current_scale)
        dot_glow_radius = int(20 * self.current_scale)
        glow_radius = int(30 * self.current_scale)
        wave_base = int(20 * self.current_scale)
        wave_max = int(60 * self.current_scale)
        dot_wave_max = int(12 * self.current_scale)  # how far outside dot

        # Mic animation
        if self.flash_state and self.active_mic:
            data = self.mics.get(self.active_mic)
            if data:
                x = int(data["x"] * self.current_scale)
                y = int(data["y"] * self.current_scale)
                # Glow Effect
                glow_color = QColor(255, 0, 0, 80)
                painter.setBrush(glow_color)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPoint(x, y), dot_glow_radius, dot_glow_radius)
                for i in range(3):
                    #   max_extra = int(12 * self.current_scale)   # how far outside dot
                    tri = (self.ripple_phase % 30) / 30.0  # 0..1

                    tri = 1.0 - tri  # shrink

                    phase = (self.ripple_phase + i * 20) % 60
                    #   tri = abs((self.ripple_phase % 30) - 15) / 15.0  # 0..1..0
                    #  tri = 1.0 - tri
                    opacity = int(250 * (1 - phase / 60))
                    # radius = dot_wave_base + int((phase / 60) * dot_wave_max)
                    radius = dot_wave_base + int(
                        dot_wave_max * tri
                    )  # int(4 * tri * self.current_scale)

                    pen = QPen(QColor(255, 0, 0, opacity))
                    pen.setWidth(max(1, int(2 * self.current_scale)))
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                    # painter.drawEllipse(QPoint(x + offset_x, y + offset_y), radius, radius)
                    painter.drawEllipse(QPoint(x, y), radius, radius)

        # Speaker animations
        if self.flash_state and self.active_speakers:
            steps = 4
            for key in self.active_speakers:
                lbl = self.labels.get(key)
                if not lbl or not lbl.isVisible():  # << guard: skip if no label
                    continue
                # if key in self.speakers:
                #  x = int(self.speakers[key]["x"] * self.current_scale)
                # y = int(self.speakers[key]["y"] * self.current_scale)
                cx = lbl.x() + lbl.width() // 2  # label centre in *widget* coords
                cy = lbl.y() + lbl.height() // 2
                # Glow Effect
                glow_color = QColor(0, 255, 0, 80)
                painter.setBrush(glow_color)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPoint(cx, cy), glow_radius, glow_radius)

                # Pulse Ring Wave
                # steps = 4
                #   offset_x = int(2 * self.current_scale)
                #  offset_y = int(-1 * self.current_scale)

                for i in range(steps):
                    phase = (self.ripple_phase + i * 20) % 60
                    opacity = int(250 * (1 - phase / 60))
                    radius = wave_base + int((phase / 60) * wave_max)
                    pen = QPen(QColor(0, 255, 0, opacity))
                    pen.setWidth(max(1, int(2 * self.current_scale)))
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                    # painter.drawEllipse(QPoint(x + offset_x, y + offset_y), radius, radius)
                    painter.drawEllipse(QPoint(cx, cy), radius, radius)
        painter.end()


class SofaWidget(MicPositionWidget):
    """
    A MicPositionWidget pre-loaded with sofa.png + sofa_coordinates.json
    and exposing the same two methods (set_flash / set_current_pos)
    that the old GridWidget offered, so the rest of the program does
    not have to change.
    """

    DOT_BASE = 56

    def __init__(
        self,
        png=":/assets/images/sofa.png",
        json_file=":/assets/json_files/sofa_coordinates.json",
    ):
        super().__init__(png, json_file)
        self._flash = False

    # --- API expected by MainWindow -------------------------------
    def set_flash(self, on: bool):
        """Set whether the sofa widget should flash"""
        self._flash = on
        self.set_flash_state(on)

    def set_current_pos(self, pos: int):
        """Set the current position to highlight"""
        self.set_active_mic(pos)
        self.update()

    @property
    def flash_on(self):
        """Check if the sofa widget is currently flashing"""
        return self._flash

    #  def set_current_pos(self, pos: int):
    #     self.set_active_mic(pos)

    # -------- override the mic-label creation so the dots start larger
    def init_labels(self):
        super().init_labels()
        for lbl in self.mic_labels.values():
            old_w = lbl.width()  # ← size that super() gave us
            new_w = max(int(self.DOT_BASE * self.current_scale), 14)
            font_size = max(8, int(32 * self.current_scale))

            lbl.setFixedSize(new_w, new_w)
            lbl.setFont(QFont("Arial", font_size, QFont.Bold))

            lbl.setStyleSheet(
                f"""
                background-color: red;
                color: white;
                border-radius: {new_w // 2}px;
                font-family: Arial;
                font-size: {font_size}px;
                font-weight: 600;
                """
            )

            # shift back so the centre stays at the same (x, y)
            dx = (new_w - old_w) // 2
            lbl.move(lbl.x() - dx, lbl.y() - dx)  # same delta for x and y

    # ──────────────────────────────────────────────────────
    #  make the active-mic ring sit *outside* the dot
    # ──────────────────────────────────────────────────────
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.flash_state or self.active_mic is None:
            return
        if str(self.active_mic) not in self.mics:
            return

        # Use original coordinates, not label geometry
        # --- OLD -------------------------------------------------
        # coords  = self.mics[str(self.active_mic)]
        # center_x = int(coords['x'] * self.current_scale)
        # center_y = int(coords['y'] * self.current_scale)

        # --- NEW -------------------------------------------------
        dot_label = self.mic_labels[str(self.active_mic)]
        center_x = dot_label.x() + dot_label.width() // 2
        center_y = dot_label.y() + dot_label.height() // 2

        #  dot_label = self.mic_labels[str(self.active_mic)]
        dot_radius = dot_label.width() // 2
        # pulse_offset = abs(self.ripple_phase % 30 - 15) / 15
        # ring_radius = dot_radius + int(8 * pulse_offset * self.current_scale) + max(int(14 * self.current_scale), 3)

        painter = QPainter(self)
        # pen = QPen(QColor(255, 0, 0, 180))
        #  pen.setWidth(max(2, int(3 * self.current_scale)))
        # painter.setPen(pen)
        #  painter.setBrush(Qt.NoBrush)
        #   painter.drawEllipse(QPoint(center_x, center_y), ring_radius, ring_radius)
        # painter.end()

        # Glow Effect
        glow_radius = dot_radius + int(30 * self.current_scale)
        glow_color = QColor(255, 0, 0, 80)
        painter.setBrush(glow_color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPoint(center_x, center_y), glow_radius, glow_radius)
        dot_wave_base = int(30 * self.current_scale)
        dot_wave_max = int(80 * self.current_scale)
        for i in range(3):
            tri = (self.ripple_phase % 30) / 30.0  # 0..1

            tri = 1.0 - tri  # shrink

            phase = (self.ripple_phase + i * 20) % 60

            opacity = int(250 * (1 - phase / 60))
            # radius = dot_wave_base + int((phase / 60) * dot_wave_max)
            radius = dot_wave_base + int(
                dot_wave_max * tri
            )  # int(4 * tri * self.current_scale)

            #    radius = dot_wave_base + int((phase / 60) * dot_wave_max)
            pen = QPen(QColor(255, 0, 0, opacity))
            pen.setWidth(max(1, int(2 * self.current_scale)))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            # painter.drawEllipse(QPoint(x + offset_x, y + offset_y), radius, radius)
            painter.drawEllipse(QPoint(center_x, center_y), radius, radius)


#   def set_flash(self, on: bool):
#      self._flash = on
#     self.set_flash_state(on)
#    self.update()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = MicPositionWidget(
        ":/assets/images/hometheater_base_persp.png",
        ":/assets/json_files/room_layout_persp.json",
    )
    widget.set_active_mic(0)

    # Test: Cycle mic + animate 2 speakers
    test_speakers = ["TML", "FR"]
    #  test_speakers = []
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
