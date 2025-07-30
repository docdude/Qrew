# Qrew_dialogs.py
"""This module contains various dialog classes for the Qrew application."""

import os
import datetime
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QCheckBox,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QApplication,
    QDialog,
    QSizePolicy,
    QScrollArea,
    QGroupBox,
    QFrame,
    QComboBox,
)


from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QPixmap

try:
    from .Qrew_button import Button
    from .Qrew_styles import (
        BUTTON_STYLES,
        HTML_ICONS,
        set_background_image,
        get_dark_palette,
        get_light_palette,
        COMBOBOX_STYLE,
        CHECKBOX_STYLE,
        load_high_quality_image,
    )
    from .Qrew_common import SPEAKER_LABELS, SPEAKER_CONFIGS
    from .Qrew_messagebox import QrewMessageBox, QrewFileDialog
    from . import Qrew_settings as qs
    from .Qrew_micwidget_icons import MicPositionWidget
    from .Qrew_vlc_helper_v2 import (
        is_vlc_backend_locked,
        get_available_backends,
    )
except ImportError:
    from Qrew_button import Button
    from Qrew_styles import (
        BUTTON_STYLES,
        HTML_ICONS,
        set_background_image,
        get_light_palette,
        get_dark_palette,
        COMBOBOX_STYLE,
        CHECKBOX_STYLE,
        load_high_quality_image,
    )
    from Qrew_common import SPEAKER_LABELS, SPEAKER_CONFIGS
    from Qrew_messagebox import (
        QrewMessageBox,
        QrewFileDialog,
    )
    import Qrew_settings as qs
    from Qrew_micwidget_icons import MicPositionWidget
    from Qrew_vlc_helper_v2 import is_vlc_backend_locked, get_available_backends

# import Qrew_resources

# expose speaker configs for MainWindow


def get_speaker_configs():
    """Get speaker configurations for the application."""
    return SPEAKER_CONFIGS


# ----


def center_dialog_on_parent(dialog, parent):
    """Center dialog on parent window, ensuring it stays on screen"""
    if not parent:
        return

    # Get parent geometry
    parent_rect = parent.geometry()
    dialog_rect = dialog.geometry()

    # Calculate center position
    x = parent_rect.x() + (parent_rect.width() - dialog_rect.width()) // 2
    y = parent_rect.y() + (parent_rect.height() - dialog_rect.height()) // 2

    # Ensure dialog stays on screen
    screen = QApplication.primaryScreen().geometry()

    # Clamp to screen bounds
    x = max(0, min(x, screen.width() - dialog_rect.width()))
    y = max(0, min(y, screen.height() - dialog_rect.height()))

    dialog.move(x, y)


def place_dialog_beside_parent(dialog, parent, side="right", gap=20):
    """
    Position *dialog* beside *parent*.

    side = "right" | "left"
    gap  = pixels between the two windows
    """
    if parent is None:
        return  # nothing to anchor to

    # 1) parent’s geometry on screen (incl. window frame)
    p_geo: QRect = parent.frameGeometry()

    # 2) choose target point
    if side == "right":
        x = p_geo.right() + gap
    else:  # "left"
        x = p_geo.left() - gap - dialog.width()
    y = p_geo.top()  # align top edges

    # 3) keep inside the same screen’s available area
    screen_number = QApplication.desktop().screenNumber(parent)
    screen_geo = QApplication.desktop().screenGeometry(screen_number)

    # right edge overflow ?
    if x + dialog.width() > screen_geo.right():
        x = screen_geo.right() - dialog.width() - 1
    # left edge overflow ?
    if x < screen_geo.left():
        x = screen_geo.left()

    # optional: keep title-bar visible
    if y + 30 > screen_geo.bottom():
        y = screen_geo.bottom() - 30

    # 4) move + (optionally) raise
    dialog.move(QPoint(x, y))


class PositionDialog(QDialog):
    """
    Microphone position dialog class
    """

    def __init__(self, position, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Position Change")
        self.setFixedSize(450, 180)
        self.setModal(True)
        center_dialog_on_parent(self, parent)

        # ── main vertical layout ──────────────────────────────────
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 20, 0, 20)
        vbox.setSpacing(10)  # space between label & button

        # message label
        msg = (
            "Make sure REW is running and mic is at position 0 (MLP)"
            if position == 0
            else f"Move mic to position {position} and press OK to continue"
        )

        label = QLabel(msg)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(False)
        vbox.addWidget(label)

        # ── centred button row ───────────────────────────────────
        btn = Button("OK")
        btn.setMinimumWidth(200)
        btn.clicked.connect(self.accept)
        btn.setStyleSheet(BUTTON_STYLES["primary"])

        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(btn)
        hbox.addStretch()

        vbox.addLayout(hbox)  # add the centred row to the dialog


class MeasurementQualityDialog(QDialog):
    """
    Measurement Dialog Class
    """

    def __init__(self, measurement_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Measurement Quality Issue")
        self.setFixedSize(500, 380)
        self.setModal(True)
        center_dialog_on_parent(self, parent)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Extract info
        channel = measurement_info["channel"]
        position = measurement_info["position"]
        rating = measurement_info["rating"]
        score = measurement_info["score"]
        detail = measurement_info["detail"]

        # Choose icon and color based on rating
        if rating == "CAUTION":
            icon = HTML_ICONS["warning"]
            color = "#ffaa00"
            title_text = "Measurement Quality: CAUTION"
        else:  # RETAKE
            icon = HTML_ICONS["cross"]
            color = "#ff0000"
            title_text = "Measurement Quality: RETAKE RECOMMENDED"

        # Title with icon
        title_layout = QHBoxLayout()
        icon_label = QLabel(
            f'<span style="color: {color}; font-size: 24px;">{icon}</span>'
        )
        icon_label.setTextFormat(Qt.RichText)
        title_layout.addWidget(icon_label)

        title_label = QLabel(title_text)
        title_label.setStyleSheet(
            f"font-weight: bold; font-size: 16px; color: {color};"
        )
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        detail_str = ", ".join(
            f"{k}: {v:.2f}" if isinstance(v, (int, float)) else f"{k}: {v}"
            for k, v in detail.items()
        )
        # Message
        message = (
            f"The measurement for <b>{channel}_pos{position}</b> received a "
            f"quality rating of <b>{rating}</b> with a score of <b>{score:.1f}</b>, "
            f"<b>{detail_str}<b>.<br><br>"
            "<br>"
            "You can choose to:<br>"
            "• <b>Remeasure</b> - Delete this measurement and repeat it<br>"
            "• <b>Continue</b> - Keep this measurement and proceed with the next one<br>"
            "• <b>Stop</b> - Stop the measurement process"
        )

        message_label = QLabel(message)
        message_label.setTextFormat(Qt.RichText)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("font-size: 14px; line-height: 1.4;")
        layout.addWidget(message_label)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.remeasure_button = Button("Remeasure")
        self.remeasure_button.clicked.connect(
            lambda: self.done(1)
        )  # Return 1 for remeasure
        self.remeasure_button.setStyleSheet(BUTTON_STYLES["warning"])

        self.continue_button = Button("Continue")
        self.continue_button.clicked.connect(
            lambda: self.done(2)
        )  # Return 2 for continue
        self.continue_button.setStyleSheet(BUTTON_STYLES["primary"])

        self.stop_button = Button("Stop")
        self.stop_button.clicked.connect(lambda: self.done(0))  # Return 0 for stop
        self.stop_button.setStyleSheet(BUTTON_STYLES["danger"])

        button_layout.addWidget(self.stop_button)
        button_layout.addSpacing(10)
        button_layout.addWidget(self.continue_button)
        button_layout.addSpacing(10)
        button_layout.addWidget(self.remeasure_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)


class SaveMeasurementsDialog(QDialog):
    """
    SavemeasurementsDialog Class
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Raw Measurements")
        self.setFixedSize(600, 300)  # Increased size
        self.setModal(True)
        center_dialog_on_parent(self, parent)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        default_name = f"Pre-processedMeasurements_{timestamp}"

        layout = QVBoxLayout()
        layout.setSpacing(15)  # More spacing between elements
        layout.setContentsMargins(20, 20, 20, 20)  # More padding

        # Title
        title_label = QLabel("Save Raw Measurements")
        title_label.setStyleSheet(
            "font-weight: bold; font-size: 18px; margin-bottom: 15px;"
        )
        layout.addWidget(title_label)

        # Filename section
        filename_layout = QHBoxLayout()
        filename_label = QLabel("Filename:")
        filename_label.setFixedWidth(100)
        filename_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.filename_input = QLineEdit(default_name)
        self.filename_input.setMinimumHeight(30)
        self.filename_input.setStyleSheet("padding: 5px; font-size: 14px;")
        filename_layout.addWidget(filename_label)
        filename_layout.addWidget(self.filename_input)
        layout.addLayout(filename_layout)

        # Directory section
        directory_layout = QHBoxLayout()
        directory_label = QLabel("Directory:")
        directory_label.setFixedWidth(100)
        directory_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.directory_input = QLineEdit()
        self.directory_input.setPlaceholderText("Select directory...")
        self.directory_input.setMinimumHeight(30)
        self.directory_input.setStyleSheet("padding: 5px; font-size: 14px;")
        self.browse_button = Button("Browse...")
        self.browse_button.clicked.connect(self.browse_directory)
        #   self.browse_button.setFixedWidth(100)
        #  self.browse_button.setMinimumHeight(30)
        self.browse_button.setStyleSheet(BUTTON_STYLES["secondary"])
        directory_layout.addWidget(directory_label)
        directory_layout.addWidget(self.directory_input)
        directory_layout.addWidget(self.browse_button)
        layout.addLayout(directory_layout)

        # Info section
        info_label = QLabel(
            "This will save all raw measurements before any processing "
            "(cross-correlation, vector averaging, etc.) to a .mdat file."
        )
        info_label.setStyleSheet("color: #666; font-size: 13px;")
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignCenter)
        wanted_h = info_label.sizeHint().height()
        info_label.setMinimumHeight(wanted_h)
        info_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(info_label, 0, Qt.AlignHCenter)
        layout.addStretch()

        # Button section
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = Button("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        #  self.cancel_button.setFixedSize(100, 35)
        self.cancel_button.setStyleSheet(BUTTON_STYLES["secondary"])

        self.save_button = Button("Save")
        self.save_button.clicked.connect(self.save_measurements)
        #  self.save_button.setFixedSize(100, 35)
        self.save_button.setDefault(True)
        self.save_button.setStyleSheet(BUTTON_STYLES["primary_default"])

        button_layout.addWidget(self.cancel_button)
        #  button_layout.addSpacing(10)
        button_layout.addWidget(self.save_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Set default directory
        default_dir = os.path.expanduser("~/Documents")
        self.directory_input.setText(default_dir)
        self.result_file_path = None

    def browse_directory(self):
        """
        browse directory
        """
        dir_text = self.directory_input.text()
        current_dir = dir_text or os.path.expanduser("~/Documents")
        directory = QrewFileDialog.getExistingDirectory(
            self, "Select Directory for Measurements", current_dir
        )
        if directory:
            self.directory_input.setText(directory)

    def save_measurements(self):
        """
        save measurement
        """
        filename = self.filename_input.text().strip()
        directory = self.directory_input.text().strip()

        if not filename:
            QrewMessageBox.warning(self, "Invalid Input", "Please enter a filename.")
            return

        if not directory:
            QrewMessageBox.warning(self, "Invalid Input", "Please select a directory.")
            return

        if not os.path.exists(directory):
            QrewMessageBox.warning(
                self, "Invalid Directory", "Selected directory does not exist."
            )
            return

        # Ensure .mdat extension
        if not filename.lower().endswith(".mdat"):
            filename += ".mdat"

        self.result_file_path = os.path.join(directory, filename)

        # Check if file exists
        if os.path.exists(self.result_file_path):
            reply = QrewMessageBox.question(
                self,
                "File Exists",
                f"File '{filename}' already exists. Overwrite?",
                QrewMessageBox.Yes | QrewMessageBox.No,
                QrewMessageBox.No,
            )
            if reply != QrewMessageBox.Yes:
                return

        self.accept()


class ClearMeasurementsDialog(QDialog):
    """
    ClearMeasurementsDialog Class
    """

    def __init__(self, measurement_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clear Existing Measurements")
        self.setFixedSize(450, 250)
        self.setModal(True)
        center_dialog_on_parent(self, parent)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 0, 20, 20)

        # Warning icon and title
        title_layout = QHBoxLayout()

        # Warning label
        warning_label = QLabel(
            f'<span style="color: #d32f2f;">{HTML_ICONS["warning"]}</span>'
        )
        warning_label.setStyleSheet("font-size: 50px;")
        title_layout.addWidget(warning_label)

        title_label = QLabel("Clear Existing Measurements")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #d32f2f;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        layout.addLayout(title_layout)
        layout.addSpacing(-15)
        # Message
        if measurement_count > 0:
            message_text = (
                f"REW currently contains {measurement_count} measurement"
                f'{"s" if measurement_count != 1 else ""}.\n\n'
                + (
                    "Do you want to delete all existing measurements before "
                    "starting new ones?\n\n"
                )
                + "This action cannot be undone."
            )
        else:
            message_text = (
                "REW contains no existing measurements.\n\n"
                "Proceed with new measurements?"
            )

        message_label = QLabel(message_text)
        message_label.setStyleSheet("font-size: 14px; line-height: 1.4;")
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(message_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = Button("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        #  self.cancel_button.setFixedSize(100, 35)
        self.cancel_button.setStyleSheet(BUTTON_STYLES["secondary"])

        if measurement_count > 0:
            self.proceed_button = Button("Keep && Proceed")
            self.proceed_button.clicked.connect(self.keep_and_proceed)
            #     self.proceed_button.setFixedSize(120, 35)
            self.proceed_button.setStyleSheet(BUTTON_STYLES["info"])

            self.delete_button = Button("Delete All")
            self.delete_button.clicked.connect(self.delete_and_proceed)
            #  self.delete_button.setFixedSize(100, 35)
            self.delete_button.setStyleSheet(BUTTON_STYLES["danger"])

            button_layout.addWidget(self.cancel_button)
            button_layout.addSpacing(10)
            button_layout.addWidget(self.proceed_button)
            button_layout.addSpacing(10)
            button_layout.addWidget(self.delete_button)
        else:
            self.proceed_button = Button("Proceed")
            self.proceed_button.clicked.connect(self.keep_and_proceed)
            #     self.proceed_button.setFixedSize(100, 35)
            self.proceed_button.setDefault(True)
            self.proceed_button.setStyleSheet(BUTTON_STYLES["primary"])

            button_layout.addWidget(self.cancel_button)
            button_layout.addSpacing(10)
            button_layout.addWidget(self.proceed_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.result = None  # 'cancel', 'keep', 'delete'

    def keep_and_proceed(self):
        """
        keep results
        """
        self.result = "keep"
        self.accept()

    def delete_and_proceed(self):
        """
        delete results
        """
        self.result = "delete"
        self.accept()


class RepeatMeasurementDialog(QDialog):
    """
    RepeatMeasurementDialog Class
    """

    def __init__(self, measurement_qualities, num_positions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Repeat Measurements")
        self.setFixedSize(700, 610)
        self.setModal(True)
        center_dialog_on_parent(self, parent)

        self.measurement_qualities = measurement_qualities
        self.num_positions = num_positions
        self.channel_checkboxes = {}
        self.position_checkboxes = {}
        self.selected_measurements = []

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 10, 20, 20)

        # Title
        title_label = QLabel("Select Measurements to Repeat")
        title_label.setStyleSheet(
            "font-weight: bold; font-size: 16px; margin-bottom: 0px;"
        )
        layout.addWidget(title_label)

        # Show problematic measurements
        self.create_quality_summary(layout)

        # Channel selection
        self.create_channel_selection(layout)

        # Position selection
        self.create_position_selection(layout)

        # Selected measurements display
        self.create_selection_display(layout)

        # Buttons
        self.create_buttons(layout)

        self.setLayout(layout)

        # Connect signals
        self.connect_signals()

        self.result = None  # 'cancel' or 'proceed'

    def create_quality_summary(self, layout):
        """Show summary of measurement qualities."""
        summary_group = QGroupBox("Measurement Quality Summary")
        summary_group.setStyleSheet(
            """
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: -5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """
        )
        summary_group.setFixedHeight(120)
        summary_layout = QVBoxLayout()
        # scroll-area for accumulating messages -----------------------------
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            """
            QScrollArea {
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #888;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #aaa;
            }       
        """
        )
        scroll.viewport().setAutoFillBackground(False)

        retake_measurements = []
        caution_measurements = []

        for (channel, position), quality in self.measurement_qualities.items():
            rating = quality["rating"]
            score = quality["score"]
            if rating == "RETAKE":
                retake_measurements.append(
                    f"{channel}_pos{position} (Score: {score:.1f})"
                )
            elif rating == "CAUTION":
                caution_measurements.append(
                    f"{channel}_pos{position} (Score: {score:.1f})"
                )

        if retake_measurements:
            retake_label = QLabel(
                f'<span style="color: #ff0000; font-size: 20px;">{HTML_ICONS["warning"]}</span> <b>RETAKE Recommended ({len(retake_measurements)}):</b>'
            )
            retake_label.setTextFormat(Qt.RichText)
            retake_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

            retake_label.setStyleSheet(
                "color: #ff0000; font-weight: bold; padding-bottom: 0px;"
            )
            summary_layout.addWidget(retake_label)

            retake_text = QLabel(", ".join(retake_measurements))
            retake_text.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            retake_text.setStyleSheet(
                "color: #ff6666; margin-left: 20px; margin-bottom: 0px;"
            )
            retake_text.setWordWrap(True)
            summary_layout.addWidget(retake_text)

        if caution_measurements:
            caution_label = QLabel(
                f'<span style="color: #ffaa00; font-size: 20px;">{HTML_ICONS["warning"]}</span> <b>CAUTION ({len(caution_measurements)}):</b>'
            )
            caution_label.setTextFormat(Qt.RichText)
            caution_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

            caution_label.setStyleSheet("color: #ffaa00; font-weight: bold;")
            summary_layout.addWidget(caution_label)

            caution_text = QLabel(", ".join(caution_measurements))
            caution_text.setStyleSheet(
                "color: #ffcc66; margin-left: 20px; margin-bottom: 0px;"
            )
            caution_text.setWordWrap(True)
            summary_layout.addWidget(caution_text)

        if not retake_measurements and not caution_measurements:
            no_issues_label = QLabel(
                f'<span style="color: #00aa00; font-size: 20px;">{HTML_ICONS["check"]}</span> <b>All measurements passed with good quality!</b>'
            )
            no_issues_label.setTextFormat(Qt.RichText)
            no_issues_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            no_issues_label.setStyleSheet("color: #00aa00; font-weight: bold;")
            summary_layout.addWidget(no_issues_label)
        # ---- wrap layout in a widget -------------------------------------
        content_widget = QWidget()
        content_widget.setLayout(summary_layout)

        scroll.setWidget(content_widget)

        # ---- put scroll area into the group ------------------------------
        group_vbox = QVBoxLayout(summary_group)
        group_vbox.addWidget(scroll)

        layout.addWidget(summary_group)
        layout.addSpacing(5)  # Add some space after the summary

    def create_channel_selection(self, layout):
        """Create channel selection area."""
        channel_group = QGroupBox("Select Channels to Remeasure")
        channel_group.setStyleSheet(
            """
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
        """
        )
        channel_group.setFixedHeight(120)
        channel_layout = QGridLayout()

        # Get unique channels from measurement qualities
        available_channels = set(
            channel for channel, pos in self.measurement_qualities.keys()
        )

        columns = 4
        for i, (abbr, full_name) in enumerate(SPEAKER_LABELS.items()):
            if abbr in available_channels:
                checkbox = QCheckBox(abbr)
                checkbox.setToolTip(full_name)
                checkbox.setMinimumWidth(75)

                checkbox.setStyleSheet(
                    """
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
                """
                )

                channel_layout.addWidget(
                    checkbox, i // columns, i % columns, Qt.AlignLeft
                )
                self.channel_checkboxes[abbr] = checkbox
        channel_layout.setRowStretch(channel_layout.rowCount(), 1)
        channel_layout.setColumnStretch(channel_layout.columnCount(), 1)
        # Add select all/none buttons
        button_layout = QVBoxLayout()
        select_all_btn = Button("Select All Channels")
        select_all_btn.setStyleSheet(BUTTON_STYLES["info"])
        select_all_btn.clicked.connect(self.select_all_channels)
        select_none_btn = Button("Select None")
        select_none_btn.setStyleSheet(BUTTON_STYLES["secondary"])
        select_none_btn.clicked.connect(self.select_no_channels)

        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(select_none_btn)
        # button_layout.addStretch()

        channel_widget_layout = QHBoxLayout()
        channel_widget_layout.addLayout(channel_layout)
        channel_widget_layout.addLayout(button_layout)

        channel_group.setLayout(channel_widget_layout)
        layout.addWidget(channel_group)
        layout.addSpacing(5)  # Add some space after the channel selection

    def create_position_selection(self, layout):
        """Create position selection area."""
        position_group = QGroupBox("Select Positions to Remeasure")
        position_group.setStyleSheet(
            """
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
        """
        )

        position_group.setFixedHeight(120)
        position_layout = QHBoxLayout()

        # Get unique positions from measurement qualities
        available_positions = set(
            pos for channel, pos in self.measurement_qualities.keys()
        )

        for pos in range(self.num_positions):
            if pos in available_positions:
                checkbox = QCheckBox(f"Pos {pos}")
                checkbox.setStyleSheet(
                    """
                    QCheckBox {
                        padding: 5px;
                        margin: 2px;
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
                """
                )

                position_layout.addWidget(checkbox)
                self.position_checkboxes[pos] = checkbox

        position_layout.addStretch()

        # Add select all/none buttons for positions
        pos_button_layout = QVBoxLayout()
        select_all_pos_btn = Button("Select All Positions")
        select_all_pos_btn.setStyleSheet(BUTTON_STYLES["info"])
        select_all_pos_btn.clicked.connect(self.select_all_positions)
        select_none_pos_btn = Button("Select None")
        select_none_pos_btn.setStyleSheet(BUTTON_STYLES["secondary"])
        select_none_pos_btn.clicked.connect(self.select_no_positions)

        pos_button_layout.addWidget(select_all_pos_btn)
        pos_button_layout.addWidget(select_none_pos_btn)

        position_layout.addLayout(pos_button_layout)

        position_group.setLayout(position_layout)
        layout.addWidget(position_group)
        layout.addSpacing(5)  # Add some space after the position selection

    def create_selection_display(self, layout):
        """Create area to display selected measurements."""
        selection_group = QGroupBox("Selected Measurements for Remeasurement")
        selection_group.setStyleSheet(
            """
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
        """
        )
        selection_group.setFixedHeight(120)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        scroll.viewport().setAutoFillBackground(False)

        self.selection_label = QLabel("<i>No measurements selected</i>")
        self.selection_label.setWordWrap(True)
        self.selection_label.setTextFormat(Qt.RichText)
        self.selection_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.selection_label.setStyleSheet("color:#666; padding:2px;")

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.selection_label)
        wrapper_layout.addStretch()

        scroll.setWidget(wrapper)

        selection_layout = QVBoxLayout()
        selection_layout = QVBoxLayout(selection_group)
        selection_layout.addWidget(scroll)
        layout.addWidget(selection_group)
        layout.addSpacing(5)  # Add some space after the selection display

    def create_buttons(self, layout):
        """Create dialog buttons."""
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = Button("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        #     self.cancel_button.setFixedSize(100, 35)
        self.cancel_button.setStyleSheet(BUTTON_STYLES["secondary"])

        self.proceed_button = Button("Remeasure Selected")
        self.proceed_button.clicked.connect(self.proceed_with_remeasurement)
        #    self.proceed_button.setFixedSize(150, 35)
        self.proceed_button.setEnabled(False)
        self.proceed_button.setStyleSheet(BUTTON_STYLES["primary_disabled"])

        button_layout.addWidget(self.cancel_button)
        button_layout.addSpacing(10)
        button_layout.addWidget(self.proceed_button)

        layout.addLayout(button_layout)

    def connect_signals(self):
        """Connect checkbox signals to update selection."""
        for checkbox in self.channel_checkboxes.values():
            checkbox.stateChanged.connect(self.update_selection)

        for checkbox in self.position_checkboxes.values():
            checkbox.stateChanged.connect(self.update_selection)

    def select_all_channels(self):
        """Select all channels"""
        for checkbox in self.channel_checkboxes.values():
            checkbox.setChecked(True)

    def select_no_channels(self):
        """Select no channels"""
        for checkbox in self.channel_checkboxes.values():
            checkbox.setChecked(False)

    def select_all_positions(self):
        """Select all positions"""
        for checkbox in self.position_checkboxes.values():
            checkbox.setChecked(True)

    def select_no_positions(self):
        """Select no positions"""
        for checkbox in self.position_checkboxes.values():
            checkbox.setChecked(False)

    def update_selection(self):
        """Update the list of selected measurements."""
        selected_channels = [
            ch for ch, cb in self.channel_checkboxes.items() if cb.isChecked()
        ]
        selected_positions = [
            pos for pos, cb in self.position_checkboxes.items() if cb.isChecked()
        ]

        self.selected_measurements = []
        for channel in selected_channels:
            for position in selected_positions:
                if (channel, position) in self.measurement_qualities:
                    quality = self.measurement_qualities[(channel, position)]
                    self.selected_measurements.append(
                        {
                            "channel": channel,
                            "position": position,
                            "uuid": quality["uuid"],
                            "rating": quality["rating"],
                            "score": quality["score"],
                        }
                    )

        # Update display
        if self.selected_measurements:
            n = len(self.selected_measurements)
            header = f'<b>Selected {n} measurement{"s" if n > 1 else ""}:</b><br>'
            lines = []
            for measurement in self.selected_measurements:
                # Use HTML entities for colored circles
                if measurement["rating"] == "RETAKE":
                    icon = f'<span style="color: #ff0000;">{HTML_ICONS["circle_red"]}</span>'
                elif measurement["rating"] == "CAUTION":
                    icon = f'<span style="color: #ffaa00;">{HTML_ICONS["circle_yellow"]}</span>'
                elif measurement["rating"] == "PASS":
                    icon = f'<span style="color: #00aa00;">{HTML_ICONS["circle_green"]}</span>'
                else:
                    icon = (
                        f'<span style="color: #888;">{HTML_ICONS["circle_gray"]}</span>'
                    )
                line = (
                    f'{icon} {measurement["channel"]}_pos{measurement["position"]} '
                    f'({measurement["rating"]}, Score: {measurement["score"]:.1f})'
                )
                lines.append(line)
            selection_text = header + "<br>".join(lines)
            self.selection_label.setText(selection_text)
            self.selection_label.setWordWrap(True)
            self.selection_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.selection_label.setTextFormat(Qt.RichText)
            self.selection_label.setStyleSheet("padding: 0px;")
            # Update button text to show channel info
            #  channel_names = sorted(set(m['channel'] for m in self.selected_measurements))
            # button_text = f'Remeasure Selected ({", ".join(channel_names)})'
            button_text = "Remeasure Selected"
            self.proceed_button.setText(button_text)

            self.proceed_button.setEnabled(True)
        else:
            self.selection_label.setText("<i>No measurements selected</i>")
            self.selection_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.selection_label.setTextFormat(Qt.RichText)
            self.selection_label.setStyleSheet(
                "color: #666; font-style: italic; padding: 2px;"
            )
            self.proceed_button.setText("Remeasure Selected")
            self.proceed_button.setEnabled(False)

    def proceed_with_remeasurement(self):
        """Show info about selected channels and positions, then proceed"""
        if self.selected_measurements:
            # Get unique channels and positions that user selected
            selected_channels = sorted(
                set(m["channel"] for m in self.selected_measurements)
            )
            selected_positions = sorted(
                set(m["position"] for m in self.selected_measurements)
            )

            channel_list = ", ".join(selected_channels)
            position_list = ", ".join(str(p) for p in selected_positions)

            # Show info message about visualization
            QrewMessageBox.information(
                self,
                "Repeat Measurement Selection",
                f"Theater view will show:\n\n"
                f"Channels: {channel_list}\n"
                f"Positions: {position_list}\n\n"
                f"Other channels and positions will be hidden during this repeat measurement session.",
            )

        self.result = "proceed"
        self.accept()


class DeleteSelectedMeasurementsDialog(QDialog):
    """
    DeleteSelectedMeasurementsDialog Class
    """

    def __init__(self, selected_measurements, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Selected Measurements")
        self.setFixedSize(500, 300)
        self.setModal(True)
        center_dialog_on_parent(self, parent)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 0, 20, 20)

        # Warning header
        title_layout = QHBoxLayout()
        warning_label = QLabel(
            f'<span style="color: #d32f2f;">{HTML_ICONS["warning"]}</span>'
        )
        warning_label.setStyleSheet("font-size: 24px;")
        title_layout.addWidget(warning_label)

        title_label = QLabel("Delete Selected Measurements")
        title_label.setStyleSheet(
            "font-weight: bold; font-size: 16px; " "color: #d32f2f;"
        )
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # Message
        message_text = f"The following {len(selected_measurements)} measurements will be deleted:\n\n"
        for measurement in selected_measurements:
            message_text += (
                f"• {measurement['channel']}_pos{measurement['position']} "
                f"({measurement['rating']}, Score: {measurement['score']:.1f}) "
                f"(UUID: {measurement['uuid']})\n"
            )
        message_text += "\nThis action cannot be undone."

        message_text += (
            "\nThese measurements will be permanently removed before remeasuring."
            "\n\nProceed?"
        )

        message_label = QLabel(message_text)
        message_label.setStyleSheet("font-size: 14px; line-height: 1.4;")
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = Button("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        #    self.cancel_button.setFixedSize(100, 35)
        self.cancel_button.setStyleSheet(BUTTON_STYLES["secondary"])

        self.delete_button = Button("Delete && Remeasure")
        self.delete_button.clicked.connect(self.accept)
        #   self.delete_button.setFixedSize(150, 35)
        self.delete_button.setStyleSheet(BUTTON_STYLES["danger"])

        button_layout.addWidget(self.cancel_button)
        button_layout.addSpacing(10)
        button_layout.addWidget(self.delete_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)


class SettingsDialog(QDialog):
    """
    SettingsDialog Class
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Application Settings")
        current_values = qs.as_dict()
        self.setFixedSize(400, 440)
        self.setModal(True)
        center_dialog_on_parent(self, parent)

        # --- available options ----------------------------------------
        self.options = [
            ("show_vlc_gui", "Show VLC GUI"),
            ("show_tooltips", "Show Tool Tips"),
            ("auto_pause_on_quality_issue", "Pause on Quality Issues (CAUTION/RETAKE)"),
            ("save_after_repeat", "Prompt to Save after Repeat Run"),
            ("use_light_theme", "Use Light Theme"),
        ]

        form = QVBoxLayout(self)
        form.setSpacing(15)
        form.setContentsMargins(20, 20, 20, 20)

        # Title
        title_label = QLabel("Settings")
        title_label.setStyleSheet(
            "font-weight: bold; font-size: 16px; margin-bottom: 10px;"
        )
        form.addWidget(title_label)

        # checkbox list with consistent styling
        self.checks = {}
        for key, label in self.options:
            cb = QCheckBox(label)
            cb.setChecked(current_values.get(key, False))
            # Use consistent checkbox style
            cb.setStyleSheet(CHECKBOX_STYLE["default"])
            self.checks[key] = cb
            form.addWidget(cb)

        # ──  speaker configuration row ────────────────────────
        cfg_row = QHBoxLayout()
        cfg_lab = QLabel("Speaker Configuration:")
        cfg_lab.setStyleSheet("font-size: 14px;")
        self.cfg_combo = QComboBox()
        self.cfg_combo.addItems(SPEAKER_CONFIGS.keys())
        self.cfg_combo.setCurrentText(
            current_values.get("speaker_config", "Manual Select")
        )
        self.cfg_combo.setStyleSheet(COMBOBOX_STYLE)
        self.cfg_combo.currentTextChanged.connect(self.preview_preset)

        if parent:
            locked = getattr(parent, "_GUI_LOCKED", False)  # property on MainWindow
            self.cfg_combo.setEnabled(not locked)
            parent.gui_lock_changed.connect(self.cfg_combo.setEnabled)

        cfg_row.addWidget(cfg_lab)
        cfg_row.addWidget(self.cfg_combo)
        cfg_row.addStretch()
        form.addLayout(cfg_row)

        # VLC Backend selection
        backend_layout = QHBoxLayout()
        self.backend_label = QLabel("VLC Backend:")
        self.backend_label.setStyleSheet("font-size: 14px; font-weight: normal;")

        self.backend_combo = QComboBox()

        # Check if VLC backend is locked due to compatibility issues
        if is_vlc_backend_locked():
            # If locked, only show subprocess option and disable the combobox
            self.backend_combo.addItems(["subprocess"])
            self.backend_combo.setEnabled(False)
            self.backend_label.setToolTip(
                "VLC library loading failed. Using subprocess mode only.\n"
                "This happens when the VLC architecture doesn't match Python's architecture."
            )
        else:
            # Get available backends and populate the combobox
            backends = get_available_backends()
            self.backend_combo.addItems(backends)
            if "auto" not in backends:
                self.backend_combo.insertItem(0, "auto")

        vlc_backend = current_values.get("vlc_backend", "auto")
        # If backend is locked, force subprocess
        if is_vlc_backend_locked():
            vlc_backend = "subprocess"

        self.backend_combo.setCurrentText(vlc_backend)
        self.backend_combo.setStyleSheet(COMBOBOX_STYLE)

        backend_layout.addWidget(self.backend_label)
        backend_layout.addWidget(self.backend_combo)
        backend_layout.addStretch()
        form.addLayout(backend_layout)

        form.addStretch()

        # Visualization
        viz_layout = QHBoxLayout()
        viz_label = QLabel("Visualization:")
        viz_label.setStyleSheet("font-size: 14px; font-weight: normal;")

        # Compact/Dialog toggle
        self.viz_mode_combo = QComboBox()
        self.viz_mode_combo.addItems(
            ["Sofa View", "Compact Theater View", "Full Theater View"]
        )
        viz_view = current_values.get("viz_view", "Sofa View")
        self.viz_mode_combo.setCurrentText(viz_view)
        self.viz_mode_combo.setMaximumWidth(220)
        self.viz_mode_combo.setStyleSheet(COMBOBOX_STYLE)
        viz_layout.addWidget(viz_label)
        viz_layout.addWidget(self.viz_mode_combo)

        viz_layout.addStretch()
        form.addLayout(viz_layout)
        form.addStretch()

        # buttons row using Button class
        row = QHBoxLayout()
        row.addStretch()

        cancel_btn = Button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(BUTTON_STYLES["secondary"])

        ok_btn = Button("OK")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setStyleSheet(BUTTON_STYLES["primary"])

        row.addWidget(cancel_btn)
        row.addSpacing(10)
        row.addWidget(ok_btn)
        form.addLayout(row)

        self.viz_mode_combo.currentTextChanged.connect(self.preview_visualization_mode)
        self.checks["use_light_theme"].stateChanged.connect(self.preview_theme)

    def preview_visualization_mode(self, mode):
        """Preview visualization mode change in real-time"""
        if self.parent():  # parent is MainWindow
            self.parent().switch_visualization_mode(mode)

    def preview_preset(self, name):
        """Preview preset"""
        presets = SPEAKER_CONFIGS
        if name in presets and self.parent():  # parent is MainWindow
            self.parent().apply_speaker_preset(presets[name])
            if hasattr(self.parent(), "set_channel_header"):
                self.parent().set_channel_header(name)

    def values(self) -> dict:
        """
        Return a dict with the current checkbox states and backend selection.
        """
        result = {k: cb.isChecked() for k, cb in self.checks.items()}
        result["vlc_backend"] = self.backend_combo.currentText()
        result["speaker_config"] = self.cfg_combo.currentText()
        result["viz_view"] = self.viz_mode_combo.currentText()
        return result

    def preview_theme(self):
        """Preview theme change in real-time"""
        use_light = self.checks["use_light_theme"].isChecked()
        app = QApplication.instance()
        palette = get_light_palette() if use_light else get_dark_palette()

        # Apply app-wide
        app.setPalette(palette)

        # Apply to this dialog
        self.setPalette(palette)
        app.style().polish(self)  # Refresh dialog's own style

        # Apply to child widgets
        for widget in self.findChildren(QWidget):
            widget.setPalette(palette)
            app.style().polish(widget)  # Ensure style updates

    def accept(self) -> None:
        """
        Persist all controls to settings.json via qs.set() and
        close the dialog.
        """
        print("DEBUG: SettingsDialog.accept() called")
        print(f"DEBUG: qs._FILE path = {qs._FILE}")

        # check-boxes
        for key, cb in self.checks.items():
            checked = cb.isChecked()
            print(f"DEBUG: Setting {key} = {checked}")
            qs.set(key, checked)

        # combos
        # If VLC backend is locked, ensure it stays set to subprocess
        if is_vlc_backend_locked():
            print("DEBUG: VLC backend is locked, setting to subprocess")
            qs.set("vlc_backend", "subprocess")
            # Maintain the lock flag
            qs.set("vlc_backend_locked", True)
        else:
            qs.set("vlc_backend", self.backend_combo.currentText())
        qs.set("speaker_config", self.cfg_combo.currentText())
        qs.set("viz_view", self.viz_mode_combo.currentText())
        super().accept()  # close the dialog


class REWConnectionDialog(QDialog):
    """
    REWConnectionDialog Class
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("REW Connection Required")
        self.setFixedSize(450, 270)
        self.setModal(True)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 5, 20, 15)

        # Warning header
        title_layout = QHBoxLayout()
        warning_icon = QLabel(
            f'<span style="color: #ff9500; font-size: 24px;">{HTML_ICONS["warning"]}</span>'
        )
        warning_icon.setTextFormat(Qt.RichText)
        title_layout.addWidget(warning_icon)

        title_label = QLabel("REW Not Detected")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #ff9500;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # Message
        message_text = (
            "REW API is not responding.\n\n"
            "Please start REW and ensure the API server is enabled:\n"
            "• Open REW\n"
            "• Go to Preferences → API\n"
            "• Enable 'Start Server'\n"
            "• Default port should be 4735"
        )

        message_label = QLabel(message_text)
        message_label.setStyleSheet("font-size: 14px; line-height: 1.4;")
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.exit_button = Button("Exit Application")
        self.exit_button.clicked.connect(lambda: self.done(0))  # Return 0 for exit
        self.exit_button.setStyleSheet(BUTTON_STYLES["danger"])

        self.retry_button = Button("Retry Connection")
        self.retry_button.clicked.connect(lambda: self.done(1))  # Return 1 for retry
        self.retry_button.setDefault(True)
        self.retry_button.setStyleSheet(BUTTON_STYLES["primary_default"])

        button_layout.addWidget(self.exit_button)
        button_layout.addSpacing(10)
        button_layout.addWidget(self.retry_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)


class MicPositionVisualizationDialog(QDialog):
    """
    MicPostionVisualizationDialog Class
    """

    MIN_W, MIN_H = 400, 350  # feel free to adjust

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Measurement Position Visualization")

        self.setModal(False)  # Non-modal so it can stay open during measurements
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        # place_dialog_beside_parent(self, parent, side="right")
        self.bg_source = load_high_quality_image(":/assets/images/banner_500x680.png")
        # self.bg_source = QPixmap(":/banner_500x680.png")
        self.bg_opacity = 0.10
        set_background_image(self)
        # Create the visualization widget
        self.mic_widget = MicPositionWidget(
            ":/assets/images/hometheater_base_persp.png",
            ":/assets/json_files/room_layout_persp.json",
        )
        self.mic_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Set to not show speaker icons for full view
        # self.mic_widget.set_show_speaker_icons(False)

        # Layout
        # layout = QVBoxLayout()
        # layout.setContentsMargins(0, 0, 0, 0)
        centre = QWidget()
        centre.setStyleSheet("background:  transparent")

        h = QHBoxLayout(centre)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch(1)
        h.addWidget(self.mic_widget, 0, Qt.AlignCenter)
        h.addStretch(1)
        # layout.addWidget(centre)
        #  main = QVBoxLayout(self)

        # main.addWidget(centre)
        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(10, 5, 10, 10)

        self.stay_on_top_check = QCheckBox("Stay on Top")
        self.stay_on_top_check.setStyleSheet(CHECKBOX_STYLE["main"])
        self.stay_on_top_check.setChecked(True)
        self.stay_on_top_check.stateChanged.connect(self.toggle_stay_on_top)

        self.close_button = Button("Close")
        self.close_button.setStyleSheet(BUTTON_STYLES["secondary"])
        self.close_button.clicked.connect(self.hide)  # Hide instead of close
        #   self.close_button.setMaximumWidth(100)

        button_layout.addWidget(self.stay_on_top_check)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(centre, 1)
        main.addLayout(button_layout)
        place_dialog_beside_parent(self, parent, side="right")

        # ── FINALISE GEOMETRY ──────────────────────────
        self.layout().activate()  # ensure stretches/spacers are honoured
        self.adjustSize()  # dialog now hugs the contents
        self.setMinimumSize(self.MIN_W, self.MIN_H)

    def toggle_stay_on_top(self, checked):
        """Toggle stay on top"""
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()  # Need to show again after changing window flags

    def update_visualization(
        self,
        active_mic=None,
        active_speakers=None,
        selected_channels=None,
        flash=False,
    ):
        """Update the visualization with current state"""
        if active_mic is not None:
            self.mic_widget.set_active_mic(active_mic)

        if active_speakers is not None:
            self.mic_widget.set_active_speakers(active_speakers)

        if selected_channels is not None:
            self.mic_widget.set_selected_channels(selected_channels)

        self.mic_widget.set_flash_state(flash)

    def resizeEvent(self, event):
        """Resize event"""
        super().resizeEvent(event)
        set_background_image(self)
        w = self.width() - 40  # a bit of margin for the frame
        h = self.height() - 120  # header + footer
        bgw = self.mic_widget.original_size.width()
        bgh = self.mic_widget.original_size.height()
        if bgw and bgh:
            scale = min(w / bgw, h / bgh)
            self.mic_widget.set_scale(scale)
