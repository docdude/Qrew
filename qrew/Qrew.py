# Qrew.py
import os
import requests
from threading import Thread
import sys
import time
import tempfile
import faulthandler
import signal
import platform

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QCheckBox,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QDialog,
    QSizePolicy,
    QComboBox,
    QScrollArea,
    QGroupBox,
    QFrame,
    QToolButton,
    QToolTip,
)


from PyQt5.QtCore import Qt, QTimer, QSettings, QSize, QEvent, pyqtSignal, QEventLoop
from PyQt5.QtGui import QPixmap, QPalette, QBrush, QColor, QFont, QIcon, QPainter

try:
    from .Qrew_common import SPEAKER_LABELS, TaskbarFlasher
    from . import Qrew_common
    from . import Qrew_settings as qs

    from .Qrew_api_helper import (
        get_measurement_count,
        get_measurement_by_uuid,
        get_all_measurements_with_uuid,
        get_selected_channels_with_measurements_uuid,
        get_measurement_distortion_by_uuid,
        save_all_measurements,
        delete_all_measurements,
        delete_measurements_by_uuid,
        get_ir_for_measurement,
        check_rew_connection,
        initialize_rew_subscriptions,
    )

    from .Qrew_measurement_metrics import (
        evaluate_measurement,
        calculate_rew_metrics_from_ir,
        combine_and_score_metrics,
    )
    from .Qrew_workers_v2 import (
        MeasurementWorker,
        ProcessingWorker,
        REWConnectionWorker,
        LoadMeasurementsQualityWorker,
        GetChannelMeasurementsWorker,
    )

    from .Qrew_styles import (
        GLOBAL_STYLE,
        COMBOBOX_STYLE,
        BUTTON_STYLES,
        GROUPBOX_STYLE,
        CHECKBOX_STYLE,
        tint,
        HTML_ICONS,
        set_background_image,
        get_dark_palette,
        get_light_palette,
        load_high_quality_image,
    )
    from .Qrew_button import Button

    from .Qrew_messagebox import QrewMessageBox

    from .Qrew_message_handlers import (
        run_flask_server,
        stop_flask_server,
        message_bridge,
        #  rta_coordinator,
    )

    from .Qrew_dialogs import (
        SettingsDialog,
        PositionDialog,
        MeasurementQualityDialog,
        ClearMeasurementsDialog,
        SaveMeasurementsDialog,
        RepeatMeasurementDialog,
        DeleteSelectedMeasurementsDialog,
        REWConnectionDialog,
        get_speaker_configs,
        MicPositionVisualizationDialog,
    )

    from .Qrew_micwidget_icons import MicPositionWidget, SofaWidget
    from .Qrew_vlc_helper_v2 import stop_vlc_and_exit, _global_player
    from .Qrew_vlc_widget import AudioPlayerWidget

    # import Qrew_resources
except ImportError:
    from Qrew_common import SPEAKER_LABELS, TaskbarFlasher
    import Qrew_common
    import Qrew_settings as qs

    from Qrew_api_helper import (
        get_measurement_count,
        get_measurement_by_uuid,
        get_all_measurements_with_uuid,
        get_selected_channels_with_measurements_uuid,
        get_measurement_distortion_by_uuid,
        save_all_measurements,
        delete_all_measurements,
        delete_measurements_by_uuid,
        get_ir_for_measurement,
        check_rew_connection,
        initialize_rew_subscriptions,
    )

    from Qrew_measurement_metrics import (
        evaluate_measurement,
        calculate_rew_metrics_from_ir,
        combine_and_score_metrics,
    )

    from Qrew_workers_v2 import (
        MeasurementWorker,
        ProcessingWorker,
        REWConnectionWorker,
        LoadMeasurementsQualityWorker,
        GetChannelMeasurementsWorker,
    )
    from Qrew_styles import (
        GLOBAL_STYLE,
        COMBOBOX_STYLE,
        BUTTON_STYLES,
        GROUPBOX_STYLE,
        CHECKBOX_STYLE,
        tint,
        HTML_ICONS,
        set_background_image,
        get_dark_palette,
        get_light_palette,
        load_high_quality_image,
    )
    from Qrew_button import Button

    from Qrew_messagebox import QrewMessageBox

    from Qrew_message_handlers import (
        run_flask_server,
        stop_flask_server,
        message_bridge,
        # rta_coordinator,
    )

    from Qrew_dialogs import (
        SettingsDialog,
        PositionDialog,
        MeasurementQualityDialog,
        ClearMeasurementsDialog,
        SaveMeasurementsDialog,
        RepeatMeasurementDialog,
        DeleteSelectedMeasurementsDialog,
        REWConnectionDialog,
        get_speaker_configs,
        MicPositionVisualizationDialog,
    )

    from Qrew_micwidget_icons import MicPositionWidget, SofaWidget
    from Qrew_vlc_helper_v2 import stop_vlc_and_exit, _global_player
    from Qrew_vlc_widget import AudioPlayerWidget

    # import Qrew_resources


# --- crash diagnostics -------------------------------------------------
# Ensure log directory exists in frozen apps
if getattr(sys, "frozen", False):
    # When running as PyInstaller bundle, use a temp dir that's guaranteed to exist and be writeable
    log_dir = os.path.join(tempfile.gettempdir(), "qrew_logs")
    os.makedirs(log_dir, exist_ok=True)
    _CRASHLOG = os.path.join(log_dir, "crash_trace.log")
else:
    # In development mode, use the module directory
    _CRASHLOG = os.path.join(os.path.dirname(__file__), "crash_trace.log")
    # Make sure the directory exists
    os.makedirs(os.path.dirname(_CRASHLOG), exist_ok=True)

# append mode so multiple runs accumulate
try:
    _fh = open(_CRASHLOG, "a", buffering=1, encoding="utf-8")
except Exception as e:
    print(f"Error opening crash log: {e}")
    # Fallback to stderr
    _fh = sys.stderr
faulthandler.enable(file=_fh, all_threads=True)
# optional: manual dump on SIGUSR1 (Linux/macOS)
try:
    faulthandler.register(signal.SIGUSR1, file=_fh, all_threads=True)
except AttributeError:
    pass
# ----------------------------------------------------------------------


# Force Windows to use IPv4 for all requests
if platform.system() == "Windows":
    import socket

    # import requests.packages.urllib3.util.connection as urllib3_cn  # this is for older versions
    import urllib3.util.connection as urllib3_cn

    def allowed_gai_family():
        """Force IPv4 only for Windows to avoid issues with IPv6"""
        return socket.AF_INET  # Force IPv4 only

    urllib3_cn.allowed_gai_family = allowed_gai_family


class MainWindow(QMainWindow):
    """Main application window for Qrew."""

    # Thread-safe signals for handling VLC callbacks
    abort_signal = pyqtSignal()

    gui_lock_changed = pyqtSignal(bool)
    # Add signal for VLC widget creation
    create_vlc_widget_signal = pyqtSignal(bool)  # show_gui

    def __init__(self):
        super().__init__()
        self.qsettings = QSettings("Docdude", "Qrew")
        self.setWindowTitle("Qrew")
        self.setWindowIcon(QIcon(":/assets/icons/Qrew_desktop_500x500.png"))
        self.resize(680, 900)
        self.setMinimumSize(660, 860)  # Allow more flexibility for resizing
        self.bg_source = load_high_quality_image(":/assets/images/banner_500x680.png")
        # self.bg_source = QPixmap(":/banner_500x680.png")  # original file
        self.bg_opacity = 0.35  # user-chosen α
        set_background_image(self)  # first fill
        # self.app_settings = qs._load()

        # Get settings path directly from Qrew_settings module instead of using __file__
        settings_path = str(qs._FILE)  # Use the path from Qrew_settings
        print(f"DEBUG: Loaded settings: {qs._load()}")
        print(f"DEBUG: Settings path: {settings_path}")

        # Register abort callback with VLCPlayer
        _global_player.set_abort_callback(self._abort_current_run)
        self._abort_called = False  # Track if abort was called

        # Connect the thread-safe abort signal
        self.abort_signal.connect(self._handle_abort_in_main_thread)

        print(f"DEBUG: Settings file exists: {os.path.exists(settings_path)}")
        # Message tracking
        self.current_warnings = []
        self.current_errors = []
        self.last_status_message = ""
        self.flasher = TaskbarFlasher(self)
        self._flash_state = False
        self._GUI_LOCKED = False
        # Add visualization dialog instance
        self.visualization_dialog = None
        self.vlc_widget = None
        # Initialize cancel-related attributes
        self._cancel_worker = None
        self._cancel_attempt = 0
        # Initialize remeasure info for quality dialog callbacks
        self._remeasure_info = None

        # Connect VLC widget creation signal
        self.create_vlc_widget_signal.connect(self._create_vlc_widget)
        # Connect VLC player error signal to our error handler
        try:
            if hasattr(_global_player, "error_occurred") and hasattr(
                _global_player.error_occurred, "connect"
            ):
                _global_player.error_occurred.connect(self.show_error_message)
                print("Successfully connected VLC error signal")
            else:
                print(
                    "VLC player error signal not available (normal for non-PyQt backends)"
                )
        except Exception as e:
            print(f"Could not connect VLC error signal: {e}")

        self.compact_mic_widget = None
        self.selected_channels_for_viz = (
            set()
        )  # Track selected channels for visualization

        # Initialize compact_wrapper to None
        self.compact_wrapper = None

        # Track the last valid position count
        self.last_valid_positions = 12  # Default
        self.measurement_qualities = (
            {}
        )  # {(channel, position): {'rating': 'PASS/CAUTION/RETAKE', 'score': float, 'uuid': str}}

        # Initialize visualization selection tracking
        self.selected_positions_for_viz = set(
            range(12)
        )  # Default to 12 positions (0-11)  # Track selected positions for visualization

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)

        # Initialize measurement state
        self.measurement_state = {
            "channels": [],
            "num_positions": 0,
            "current_position": 0,
            "initial_count": -1,
            "running": False,
            "channel_index": 0,
        }
        self.retake_pairs = []  # Track (channel, position) pairs needing retake

        # Channel header container
        channel_header_container = QWidget()
        channel_header_container.setStyleSheet("background: transparent;")
        channel_header_layout = QHBoxLayout(channel_header_container)
        channel_header_layout.setContentsMargins(5, 7, -5, 7)
        self.settings_btn = QToolButton()
        self.settings_btn.setAutoRaise(True)

        # self.settings_btn.setIcon(QIcon("gear@2x.png"))
        self.settings_btn.setIconSize(QSize(20, 20))
        self.settings_btn.setToolTip("Settings")
        base_pix = load_high_quality_image(":/assets/icons/gear@2x.png")

        # base_pix = QPixmap(":/icons/gear@2x.png")  # transparent PNG
        hover_pix = tint(base_pix, QColor("#00A2FF"))  # cyan tint

        icon = QIcon()
        icon.addPixmap(base_pix, QIcon.Normal, QIcon.Off)
        icon.addPixmap(hover_pix, QIcon.Active, QIcon.Off)
        icon.addPixmap(hover_pix, QIcon.Selected, QIcon.Off)
        self.settings_btn.setIcon(icon)

        # optional minimal CSS (no backdrop tint now)
        self.settings_btn.setStyleSheet(
            """
            QToolButton { border:none; background:transparent; padding:0; }
        """
        )
        self.settings_btn.clicked.connect(self.open_settings_dialog)

        channel_header_layout.addWidget(self.settings_btn, 0, Qt.AlignLeft)

        # Channel selection section
        self.channel_label = QLabel("Select Speaker Channels (Manual Select):")
        self.channel_label.setStyleSheet(
            "QLabel { color: white; background: transparent; padding: 0px 0px 0px 20px; text-align: left; }"
        )
        channel_header_layout.addWidget(self.channel_label)
        channel_header_layout.addStretch()

        # Clear button
        self.clear_button = Button("Clear")
        self.clear_button.clicked.connect(self.clear_selections)
        self.clear_button.setStyleSheet(BUTTON_STYLES["transparent_small"])

        self.clear_button.setMinimumHeight(20)
        self.clear_button.setMinimumWidth(50)
        self.clear_button.setToolTip("Clear all selected channels")
        channel_header_layout.addWidget(self.clear_button)
        main_layout.addWidget(channel_header_container)
        main_layout.addSpacing(0)

        # Channel CheckBoxes
        # Alternative: Better centering for different row lengths
        checkbox_widget = QWidget()
        checkbox_widget.setStyleSheet("background: transparent;")
        main_checkbox_layout = QVBoxLayout(checkbox_widget)

        main_checkbox_layout.setSpacing(0)
        main_checkbox_layout.setContentsMargins(0, 0, 0, 0)

        self.channel_checkboxes = {}

        # Row 1: Horizontal layout (7 items - odd)
        row1_speakers = ["FHL", "FL", "FDL", "C", "FDR", "FR", "FHR"]
        row1_layout = QHBoxLayout()
        row1_layout.setContentsMargins(8, 0, 0, 0)

        row1_layout.setSpacing(18)
        row1_layout.addStretch(1)

        for abbr in row1_speakers:
            if abbr in SPEAKER_LABELS:
                full_name = SPEAKER_LABELS[abbr]
                checkbox = QCheckBox(abbr)
                checkbox.setToolTip(full_name)
                checkbox.setMinimumWidth(65)
                checkbox.setMaximumWidth(85)

                checkbox.setStyleSheet(CHECKBOX_STYLE["main"])

                row1_layout.addWidget(checkbox)
                self.channel_checkboxes[abbr] = checkbox

        row1_layout.addStretch(1)
        row1_widget = QWidget()
        row1_widget.setLayout(row1_layout)
        row1_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        main_checkbox_layout.addWidget(row1_widget)
        main_checkbox_layout.addSpacing(-5)
        # Rows 2-5: Grid layout with smart centering
        grid_speaker_widget = QWidget()
        grid_layout = QGridLayout(grid_speaker_widget)
        grid_layout.setHorizontalSpacing(18)
        grid_layout.setVerticalSpacing(8)

        # Define grid rows with calculated positioning for centering
        grid_speaker_data = [
            {
                "speakers": ["TFL", "TML", "TRL", "TFR", "TMR", "TRR"],
                "start_col": 1,
            },  # 6 items, start at col 1
            {
                "speakers": ["FWL", "SDL", "SLA", "FWR", "SDR", "SRA"],
                "start_col": 1,
            },  # 6 items, start at col 1
            {
                "speakers": ["RHL", "SHL", "SBL", "BDL", "RHR", "SHR", "SBR", "BDR"],
                "start_col": 0,
            },  # 8 items, start at col 0
            {
                "speakers": ["SW1", "SW2", "SW3", "SW4"],
                "start_col": 2,
            },  # 4 items, start at col 2
        ]

        # Set up 8 columns
        max_grid_columns = 8
        for col in range(max_grid_columns):
            grid_layout.setColumnStretch(col, 1)

        # Add checkboxes to grid with smart positioning
        for row_idx, row_data in enumerate(grid_speaker_data):
            speakers = row_data["speakers"]
            start_col = row_data["start_col"]

            for col_offset, abbr in enumerate(speakers):
                if abbr in SPEAKER_LABELS:
                    full_name = SPEAKER_LABELS[abbr]
                    checkbox = QCheckBox(abbr)
                    checkbox.setToolTip(full_name)
                    checkbox.setMinimumWidth(75)
                    checkbox.setMaximumWidth(85)

                    checkbox.setStyleSheet(
                        """
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
                            background: qlineargradient(
                                x1:0, y1:0, x2:1, y2:1,
                                stop:0 #aaffaa,
                                stop:1 #55aa55
                            );
                            border: 1px solid #444;
                        }
                    """
                    )

                    actual_col = start_col + col_offset
                    grid_layout.addWidget(
                        checkbox,
                        row_idx,
                        actual_col,
                        Qt.AlignCenter,
                    )
                    self.channel_checkboxes[abbr] = checkbox

        main_checkbox_layout.addWidget(grid_speaker_widget)

        checkbox_widget.setMinimumSize(450, 150)
        checkbox_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        main_layout.addWidget(checkbox_widget, alignment=Qt.AlignTop)
        main_layout.addSpacing(-30)

        # ───────────────── num-positions row ───────────────── #
        pos_container = QWidget()
        pos_container.setStyleSheet("background: transparent;")

        pos_layout = QHBoxLayout(pos_container)
        pos_layout.setContentsMargins(0, 50, 0, 0)

        pos_label = QLabel("Number of Positions:")
        pos_label.setStyleSheet("color: white; font-weight: bold;")
        pos_layout.addWidget(pos_label)
        pos_layout.addSpacing(10)

        # ComboBox with fixed dropdown text visibility
        self.pos_selector = QComboBox()
        self.pos_selector.addItems(["1", "3", "6", "8", "10", "12"])
        self.pos_selector.setCurrentText("12")
        self.pos_selector.setMaximumWidth(70)

        self.pos_selector.setStyleSheet(COMBOBOX_STYLE)

        pos_layout.addWidget(self.pos_selector)

        # ───────────────── Metrics Display ───────────────── #
        metrics_container = QWidget()
        metrics_container.setStyleSheet("background: transparent;")
        metrics_layout = QVBoxLayout(metrics_container)
        metrics_layout.setContentsMargins(0, 50, 0, 0)
        metrics_layout.setSpacing(5)
        # Metrics label
        self.metrics_label = QLabel("")
        self.metrics_label.setStyleSheet(
            """
            QLabel { 
                background: rgba(0, 0, 0, 0.8); 
                color: white; 
                padding: 5px 10px; 
                border: 1px solid #444;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
        """
        )
        self.metrics_label.setTextFormat(Qt.RichText)
        self.metrics_label.setAlignment(Qt.AlignCenter)
        self.metrics_label.setMinimumSize(195, 40)
        self.metrics_label.setVisible(False)
        # Detail metrics label (expandable)
        self.metrics_detail_label = QLabel("")
        self.metrics_detail_label.setStyleSheet(
            """
            QLabel { 
                background: rgba(0, 0, 0, 0.8); 
                color: #ccc; 
                padding: 8px 12px; 
                border: 1px solid #333;
                border-radius: 4px;
                font-size: 11px;
            }
        """
        )
        self.metrics_detail_label.setTextFormat(Qt.RichText)
        self.metrics_detail_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.metrics_detail_label.setWordWrap(True)
        self.metrics_detail_label.setMinimumSize(195, 160)
        self.metrics_detail_label.setMaximumHeight(170)
        self.metrics_detail_label.setVisible(False)  # Initially hidden

        metrics_layout.addWidget(self.metrics_label)
        metrics_layout.addWidget(self.metrics_detail_label)

        # Grid widget container
        grid_container = QWidget()
        grid_container.setStyleSheet("background: transparent;")
        # grid_container.setMaximumHeight(260)
        grid_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        grid_container_layout = QVBoxLayout(grid_container)
        grid_container_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_container = grid_container
        self.grid_container_layout = grid_container_layout
        self.grid_container.installEventFilter(self)

        # Initial grid
        # n = int(self.pos_selector.currentText())
        # self.grid_widget = GridWidget(positions=n, current_pos=self.measurement_state['current_position'])
        #   self.grid_widget.setMinimumSize(0,0)
        self.sofa_widget = SofaWidget()
        self.sofa_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Add with proper alignment for centering
        grid_container_layout.addWidget(self.sofa_widget, 0, Qt.AlignCenter)

        # ---- positions + metrics (left)  /  grid (right) --------------
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(10, 0, 0, 0)
        row_layout.setSpacing(10)

        # left column  (positions + metrics)
        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(pos_container)
        left_layout.addWidget(metrics_container)
        left_layout.addStretch()

        row_layout.addWidget(left_col, 0)  # minimal width
        row_layout.addWidget(grid_container, 1)  # grid takes all spare space
        #   row_layout.setAlignment(grid_container, Qt.AlignTop)

        main_layout.addWidget(row_widget)  # ← replaces previous adds

        # main_layout.addWidget(pos_container)
        main_layout.addSpacing(-50)

        # React to user choice
        self.pos_selector.currentTextChanged.connect(self._rebuild_grid)
        # self.switch_visualization_mode(mode)

        # ---------- Command button container -----------------------------
        meas_container = QWidget()
        meas_container.setStyleSheet("background: transparent;")
        meas_layout = QHBoxLayout(meas_container)
        meas_layout.setContentsMargins(10, -10, 10, 10)
        meas_layout.setSpacing(10)

        # Load stimulus button
        self.load_button = Button("Load Stimulus File")
        self.load_button.clicked.connect(self.load_stimulus_file)
        self.load_button.setStyleSheet(BUTTON_STYLES["transparent"])
        self.load_button.setMaximumHeight(120)
        meas_layout.addWidget(self.load_button)

        # Start button
        self.start_button = Button("Start Measurement")
        self.start_button.clicked.connect(self.on_start)
        self.start_button.setStyleSheet(BUTTON_STYLES["transparent"])
        meas_layout.addWidget(self.start_button)

        # Repeat button
        self.repeat_button = Button("Repeat Measurement")
        self.repeat_button.setDisabled(True)
        self.repeat_button.clicked.connect(self.show_repeat_measurement_dialog)
        self.repeat_button.setStyleSheet(BUTTON_STYLES["transparent"])
        meas_layout.addWidget(self.repeat_button)

        # Cancel button
        self.cancel_button = Button("Cancel Run")
        self.cancel_button.setStyleSheet(BUTTON_STYLES["danger"])
        # Connect cancel button to directly call abort - this ensures all steps are performed
        self.cancel_button.clicked.connect(self._abort_current_run)
        # self.cancel_button.setVisible(False)          # only when running
        meas_layout.addWidget(self.cancel_button)

        main_layout.addWidget(meas_container, alignment=Qt.AlignCenter)
        main_layout.addSpacing(-15)

        # ---------- Process button container -----------------------------
        cmd_container = QWidget()
        cmd_container.setStyleSheet("background: transparent;")
        cmd_layout = QHBoxLayout(cmd_container)
        cmd_layout.setContentsMargins(10, -10, 10, 10)
        cmd_layout.setSpacing(20)

        # Cross button
        self.cross_button = Button("Cross Corr Align")
        self.cross_button.clicked.connect(self.on_cross_corr_align)
        self.cross_button.setStyleSheet(BUTTON_STYLES["transparent"])
        cmd_layout.addWidget(self.cross_button)

        # Vector button
        self.vector_button = Button("Vector Average")
        self.vector_button.clicked.connect(self.on_vector_average)
        self.vector_button.setStyleSheet(BUTTON_STYLES["transparent"])
        cmd_layout.addWidget(self.vector_button)

        # Full processing button
        self.full_button = Button("Cross+Vector")
        self.full_button.clicked.connect(self.on_full_processing)
        self.full_button.setStyleSheet(BUTTON_STYLES["transparent"])
        cmd_layout.addWidget(self.full_button)

        main_layout.addWidget(cmd_container, alignment=Qt.AlignCenter)
        main_layout.addSpacing(0)

        status_group = QGroupBox("Measurement Status")
        status_group.setStyleSheet(GROUPBOX_STYLE)
        # status_group.setMinimumHeight(80)
        # status_group.setMaximumHeight(80)
        status_group.setMinimumSize(450, 90)
        #  status_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Status layout
        status_layout = QVBoxLayout()
        # Status label
        self.status_label = QLabel("Please load stimulus file to begin...")
        self.status_label.setStyleSheet(
            """
            QLabel {
                color: #fff;
                font-weight: normal;
            }
        """
        )
        self.status_label.setWordWrap(True)
        # *  self.status_label.setMinimumHeight(80)
        # self.status_label.setMaximumHeight(80)
        # self.status_label.setFixedWidth(450)
        status_layout.addWidget(self.status_label)
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group, alignment=Qt.AlignTop)
        #        main_layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        # Warning/Error panel
        error_group = QGroupBox("Warnings & Errors")
        error_group.setStyleSheet(GROUPBOX_STYLE)
        # error_group.setMinimumHeight(110)
        #   error_group.setMaximumHeight(110)
        #  error_group.setMinimumWidth(450)

        error_group.setMinimumSize(450, 110)
        # --- layout inside the group --------------------------------------
        err_vbox = QVBoxLayout(error_group)
        err_vbox.setContentsMargins(10, 5, 5, 5)
        err_vbox.setSpacing(2)

        # header row (stretch + Clear button) ------------------------------
        header_hbox = QHBoxLayout()
        header_hbox.addStretch()

        self.clear_errors_button = Button("Clear")
        self.clear_errors_button.clicked.connect(self.clear_warnings_errors)
        #  self.clear_errors_button.setFixedHeight(20)
        # self.clear_errors_button.setFixedWidth(50)
        style = BUTTON_STYLES["transparent_small"]
        self.clear_errors_button.setStyleSheet(style)

        self.clear_errors_button.setToolTip("Clear all warnings and errors")
        header_hbox.addWidget(self.clear_errors_button)

        err_vbox.addLayout(header_hbox)  # <- first row in the group
        err_vbox.addSpacing(0)

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
        self.error_label = QLabel("No warnings or errors")
        self.error_label.setStyleSheet(
            """
            QLabel {
                background: transparent;
                color: white;
                font-size: 11px;
            }
        """
        )
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # Set the label to be larger than the scroll area
        self.error_label.setMinimumHeight(70)  # Ensure it can scroll
        size_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.error_label.setSizePolicy(size_policy)
        # put the label inside the scroll-area
        scroll.setWidget(self.error_label)
        scroll.setFixedHeight(70)  # visible window height
        err_vbox.addWidget(scroll)

        # add the new group to your main layout
        main_layout.addWidget(error_group, alignment=Qt.AlignTop)
        main_layout.addSpacing(0)

        self._refresh_repeat_button()

        # load persisted settings and apply once
        # self.app_settings = SettingsDialog.load()
        self.apply_settings()

        self.connect_visualization_signals()
        # Initialize widget visibility after a short delay to ensure proper layout
        QTimer.singleShot(200, self.ensure_widget_visibility)
        # make sure the initial ring is painted on all visible views
        QTimer.singleShot(250, self.update_mic_visualization)

        # Worker thread
        self.measurement_worker = None
        self.processing_worker = None
        self.quality_worker = None
        self.channel_measurements_worker = None
        self.count_worker = None
        self.delete_worker = None
        self.save_worker = None
        self.delete_uuid_worker = None
        self.delete_single_worker = None

        message_bridge.message_received.connect(self.update_status)
        message_bridge.warning_received.connect(self.add_warning)
        message_bridge.error_received.connect(self.add_error)
        QTimer.singleShot(
            1000, self.start_quality_loading_worker
        )  # Delay to ensure REW is connected

    # ---------- GUI lockdown helpers ---------------------------------

    def _set_controls_enabled(self, on: bool):
        """Enable/disable every control that must not be touched mid-run."""
        # global _GUI_LOCKED
        self._GUI_LOCKED = not on

        for widget in (
            self.load_button,
            self.start_button,
            self.repeat_button,
            self.vector_button,
            self.cross_button,
            self.full_button,
            self.clear_button,
            *self.channel_checkboxes.values(),
            self.pos_selector,
        ):
            widget.setEnabled(on)

        self.gui_lock_changed.emit(not on)

        if not on:
            self.flasher.start()  # stop flashing taskbar icon
        else:
            self.flasher.stop()

        # extra visual cue

    #  self.cancel_button.setVisible(not on)      # show only while locked

    def _abort_current_run(self):
        """
        Master abort function - can be called from UI or VLC thread.
        Handles both thread-safe operations directly and defers thread-sensitive
        operations to the main thread via signals.
        """
        # ------------------------------------------------------------------
        # 1) Track that abort was called so we skip the save dialog
        # ------------------------------------------------------------------
        self._abort_called = True

        # ------------------------------------------------------------------
        # 2) Tell REW to abort the *current* capture immediately
        #    Use worker to avoid blocking the main thread
        # ------------------------------------------------------------------
        # Cancel measurement - REW API sometimes requires double call
        # Create and start cancel worker
        try:
            from .Qrew_workers_v2 import CancelMeasurementWorker
        except ImportError:
            from Qrew_workers_v2 import CancelMeasurementWorker

        self._cancel_worker = CancelMeasurementWorker()
        self._cancel_worker.status_update.connect(self.update_status)
        self._cancel_worker.error_occurred.connect(self.add_error)
        self._cancel_worker.cancel_complete.connect(self._on_cancel_complete)
        self._cancel_worker.start()

        # Note: The retry logic will be handled in _on_cancel_complete
        self._cancel_attempt = 0

        # ------------------------------------------------------------------
        # 3) Make sure VLC stops playing the stimulus
        #    This is also thread-safe
        # ------------------------------------------------------------------
        try:
            # helper works for both back-ends ('libvlc' or 'subprocess')
            stop_vlc_and_exit()
        except Exception as e:
            print(f"Unable to stop VLC: {e}")

        # ------------------------------------------------------------------
        # 4) Use signal to stop worker threads from main thread
        #    This is the thread-sensitive part that needs to be handled
        #    in the main thread
        # ------------------------------------------------------------------

        # Import thread utility
        try:
            from .Qrew_thread_utils import is_main_thread
        except ImportError:
            from Qrew_thread_utils import is_main_thread

        # If we're in the main thread, call directly
        if is_main_thread():
            self._handle_abort_in_main_thread()
        else:
            # Otherwise emit signal to have it called in the main thread
            self.abort_signal.emit()

    def _handle_abort_in_main_thread(self):
        """This runs in the main thread via the signal connection"""
        """User pressed Cancel Run or VLC abort was triggered."""
        if self.measurement_worker and self.measurement_worker.isRunning():
            self.status_label.setText("Measurement run cancelled by user.")
            # turn off flash immediately
            self.measurement_worker.stop_and_finish()
        if (
            hasattr(self, "processing_worker")
            and self.processing_worker
            and self.processing_worker.isRunning()
        ):
            self.processing_worker.stop_and_finish()

        # Explicitly clear flash state and visualization
        self._flash_state = False
        if hasattr(self, "sofa_widget"):
            self.sofa_widget.set_flash(False)
            self.sofa_widget.set_active_speakers([])
        if (
            getattr(self, "compact_mic_widget", None)
            and self.compact_mic_widget.isVisible()
        ):
            self.compact_mic_widget.set_flash_state(False)
            self.compact_mic_widget.set_active_speakers([])
        if (
            getattr(self, "visualization_dialog", None)
            and self.visualization_dialog.isVisible()
        ):
            self.visualization_dialog.mic_widget.set_flash_state(False)
            self.visualization_dialog.mic_widget.set_active_speakers([])

        # tell repeat logic we ended mid-flight: keep remaining pairs
        if self.measurement_state.get("repeat_mode"):
            # nothing to do, state['re_idx'] remains where it is
            pass

        self._set_controls_enabled(True)

    def _on_cancel_complete(self, success, message):
        """Handle cancel measurement completion"""
        if success:
            print(f"REW measurement cancelled: {message}")
            # Even on success, REW often needs a second cancel command
            # Always do a second attempt for measurements
            if hasattr(self, "_cancel_attempt") and self._cancel_attempt == 0:
                self._cancel_attempt = 1
                print("Sending second cancel command (REW workaround)...")
                # Small delay before second attempt
                QTimer.singleShot(100, self._send_second_cancel)
        else:
            print(f"REW cancel failed: {message}")
            # Also retry on failure
            if hasattr(self, "_cancel_attempt") and self._cancel_attempt == 0:
                self._cancel_attempt = 1
                print("Retrying cancel measurement...")
                QTimer.singleShot(100, self._send_second_cancel)

    def _send_second_cancel(self):
        """Send the second cancel command"""
        try:
            from .Qrew_workers_v2 import CancelMeasurementWorker
        except ImportError:
            from Qrew_workers_v2 import CancelMeasurementWorker

        self._cancel_worker = CancelMeasurementWorker()
        self._cancel_worker.status_update.connect(self.update_status)
        self._cancel_worker.error_occurred.connect(self.add_error)
        self._cancel_worker.cancel_complete.connect(
            lambda success, msg: print(
                f"Second cancel {'succeeded' if success else 'failed'}: {msg}"
            )
        )
        self._cancel_worker.start()

    def _on_single_delete_complete(self, success, error_msg):
        """Handle single measurement deletion completion"""
        if success:
            # Remove from quality tracking
            if hasattr(self, "_remeasure_info"):
                key = (
                    self._remeasure_info["channel"],
                    self._remeasure_info["position"],
                )
                if key in self.measurement_qualities:
                    del self.measurement_qualities[key]

            # Tell worker to remeasure
            if self.measurement_worker:
                self.measurement_worker.handle_quality_dialog_response("remeasure")
        else:
            self.add_error(f"Failed to delete measurement: {error_msg}")
            # Still continue with measurement
            if self.measurement_worker:
                self.measurement_worker.handle_quality_dialog_response("continue")

        # Clean up
        if hasattr(self, "_remeasure_info"):
            del self._remeasure_info

    def eventFilter(self, source, event):
        # A single left-click anywhere inside the grid-container
        # pops the Full-Theatre window to the front, but does **not**
        # change the current visualisation mode or persist anything.
        if source is self.grid_container and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self.show_visualization_dialog()  # just open / raise it
                return True  # stop further handling
        return super().eventFilter(source, event)

    def _toggle_flash(self):
        self._flash_state = not self._flash_state
        if hasattr(self, "sofa_widget"):
            self.sofa_widget.set_flash(self._flash_state)
        if (
            getattr(self, "compact_mic_widget", None)
            and self.compact_mic_widget.isVisible()
        ):
            self.compact_mic_widget.set_flash_state(self._flash_state)
        if (
            getattr(self, "visualization_dialog", None)
            and self.visualization_dialog.isVisible()
        ):
            self.visualization_dialog.mic_widget.set_flash_state(self._flash_state)

    def _refresh_repeat_button(self):
        """Enable the Repeat button only if a valid stimulus WAV is set."""
        path = getattr(Qrew_common, "selected_stimulus_path", "")
        self.repeat_button.setEnabled(bool(path) and os.path.exists(path))

    def _set_channel_header(self, cfg_name: str):
        """Update the header to show current speaker configuration."""
        if not cfg_name or cfg_name.startswith("Manual"):
            suffix = " (Manual Select)"
        else:
            suffix = f" ({cfg_name})"
        self.channel_label.setText(f"Select Speaker Channels{suffix}:")

    def apply_speaker_preset(self, label_list):
        for cb in self.channel_checkboxes.values():
            cb.setChecked(False)
        for lbl in label_list:
            if lbl in self.channel_checkboxes:
                self.channel_checkboxes[lbl].setChecked(True)

    def _rebuild_grid(self, text: str):
        """
        The combo-box changed.  Just tell the sofa widget how many
        positions are active; no rebuilding / relayout is required.
        """
        try:
            n = int(text)
        except ValueError:
            return
        #  was_flashing = self.flash_timer.isActive()
        self.sofa_widget.set_visible_positions(n)
        if self._flash_state:
            self.sofa_widget.set_flash(self._flash_state)

    def update_metrics_display(self, metrics: dict):
        """Update the metrics display with the latest measurement results.

        Args:
            metrics (dict): A dictionary containing measurement metrics.
        """
        try:
            score = metrics.get("score", 0)
            rating = metrics.get("rating", "Unknown")
            channel = metrics.get("channel")  # ← from result
            position = metrics.get("position")
            uuid = metrics.get("uuid")
            detail = metrics.get("detail", {})
            # Track quality
            if channel is not None and position is not None and uuid:
                self.measurement_qualities[(channel, position)] = {
                    "rating": rating,
                    "score": score,
                    "uuid": uuid,
                    "detail": detail,
                    "title": f"{channel}_pos{position}",
                }
                print(
                    f"Tracked quality for {channel}_pos{position}: {rating} ({score:.1f}) UUID: {uuid}"
                )

            # Choose colour …
            colour = {
                "PASS": "#00ff00",
                "CAUTION": "#ffff00",
                "RETAKE": "#ff0000",
            }.get(rating, "#ffffff")

            html = (
                f"<span style='color:{colour}; font-size:18px;font-weight:bold;'>"
                f"{rating}</span> "
                f"<span style='color:#ccc;font-size:14px;'>({score:.1f})</span>"
            )

            if channel and position is not None:
                html += (
                    f"<br><span style='color:#aaa; font-size:12px;'>"
                    f"{channel} Position {position}</span>"
                )

            self.metrics_label.setText(html)
            self.metrics_label.show()

            # Format detail information with proper units and formatting
            if detail:
                detail_lines = []

                # SNR
                snr = detail.get("snr_dB")
                if snr is not None:
                    detail_lines.append(
                        f"<span style='color:#99ccff;'>SNR:</span> {snr:.1f} dB"
                    )

                # Signal to Distortion Ratio
                sdr = detail.get("sdr_dB")
                if sdr is not None:
                    detail_lines.append(
                        f"<span style='color:#99ccff;'>SDR:</span> {sdr:.1f} dB"
                    )

                # Peak Value
                peak_value = detail.get("peak_value")
                if peak_value is not None:
                    detail_lines.append(
                        (
                            f"<span style='color:#99ccff;'>Peak Value:</span> "
                            f"{peak_value:.9f}"
                        )
                    )

                # Peak Time (ms)
                peak_time_ms = detail.get("peak_time_ms")
                if peak_time_ms is not None:
                    detail_lines.append(
                        (
                            f"<span style='color:#99ccff;'>Peak Time:</span> "
                            f"{peak_time_ms:.6f} ms"
                        )
                    )

                # IR peak_to_noise
                ir_peak_noise = detail.get("ir_pk_noise_dB")
                if ir_peak_noise is not None:
                    detail_lines.append(
                        (
                            (
                                (
                                    f"<span style='color:#99ccff;'>IR Peak-to-Noise:</span> "
                                    f"{ir_peak_noise:.1f} dB"
                                )
                            )
                        )
                    )

                # Coherence (can be None)
                coh_mean = detail.get("coh_mean")
                if coh_mean is not None:
                    detail_lines.append(
                        (
                            f"<span style='color:#99ccff;'>Coherence:</span> "
                            f"{coh_mean:.3f}"
                        )
                    )

                # THD metrics
                # Show THD+N instead of just THD for better understanding
                mean_thd_n = detail.get("mean_thd_n_%")
                if mean_thd_n is not None:
                    detail_lines.append(
                        (
                            f"<span style='color:#99ccff;'>THD+N:</span> "
                            f"{mean_thd_n:.3f}%"
                        )
                    )

                mean_thd = detail.get("mean_thd_%")
                if mean_thd is not None:
                    detail_lines.append(
                        (
                            f"<span style='color:#99ccff;'>Mean THD:</span> "
                            f"{mean_thd:.3f}%"
                        )
                    )

                max_thd = detail.get("max_thd_%")
                if max_thd is not None:
                    detail_lines.append(
                        (
                            f"<span style='color:#99ccff;'>Max THD:</span> "
                            f"{max_thd:.3f}%"
                        )
                    )

                low_thd = detail.get("low_thd_%")
                if low_thd is not None:
                    detail_lines.append(
                        (
                            f"<span style='color:#99ccff;'>Low THD:</span> "
                            f"{low_thd:.3f}%"
                        )
                    )

                # Harmonic ratio
                h3_h2_ratio = detail.get("h3/h2_ratio")
                if h3_h2_ratio is not None:
                    detail_lines.append(
                        (
                            f"<span style='color:#99ccff;'>H3/H2 Ratio:</span> "
                            f"{h3_h2_ratio:.3f}"
                        )
                    )

                if detail_lines:
                    detail_html = "<br>".join(detail_lines)
                    self.metrics_detail_label.setText(detail_html)
                    self.metrics_detail_label.show()
                else:
                    self.metrics_detail_label.hide()
            else:
                self.metrics_detail_label.hide()

        except ValueError as e:
            print("Error updating metrics display:", e)
        except TypeError as e:
            print("Type error updating metrics display:", e)

    def update_quality_entry(self, result: dict):
        """
        Update self.measurement_qualities for (channel, position)
        with the score/rating of the *new* measurement.
        """
        key = (result["channel"], result["position"])
        # overwrite / create
        self.measurement_qualities[key] = {
            "rating": result["rating"],
            "score": result["score"],
            "detail": result["detail"],
            "uuid": result["uuid"],
        }

    def update_status(self, msg):
        """Update regular status messages (white text)"""
        self.last_status_message = msg
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(
            """
            QLabel { 
                color: white; 

                font-weight: normal;
            }
        """
        )

    def add_warning(self, warning_msg):
        """Add a warning message (yellow text, persistent)"""
        timestamp = time.strftime("%H:%M:%S")
        warning_with_time = f"[{timestamp}] {warning_msg}"

        # Keep only last 3 warnings
        self.current_warnings.append(warning_with_time)
        if len(self.current_warnings) > 3:
            self.current_warnings.pop(0)

        self.update_error_display()

    def add_error(self, error_msg):
        """Add an error message (red text, persistent)"""
        timestamp = time.strftime("%H:%M:%S")
        error_with_time = f"[{timestamp}] {error_msg}"

        # Keep only last 3 errors
        self.current_errors.append(error_with_time)
        if len(self.current_errors) > 3:
            self.current_errors.pop(0)

        self.update_error_display()

    def update_error_display(self):
        """Update the warning/error display"""
        if not self.current_warnings and not self.current_errors:
            self.error_label.setText("No warnings or errors")
            self.error_label.setStyleSheet(
                """
                QLabel { 
                    background: transparent;
                    color: #fff; 

                    font-size: 11px;
                }
            """
            )
            return

        # Build display text with HTML for colors
        display_parts = []

        # Add errors (red)
        for error in self.current_errors:
            display_parts.append(
                f'<span style="color: #ff6b6b;">{HTML_ICONS["cross"]} {error}</span>'
            )

        # Add warnings (yellow)
        for warning in self.current_warnings:
            display_parts.append(
                f'<span style="color: #ffd93d;">{HTML_ICONS["warning"]} {warning}</span>'
            )

        display_text = "<br>".join(display_parts)
        self.error_label.setTextFormat(Qt.RichText)
        self.error_label.setText(display_text)
        self.error_label.setStyleSheet(
            """
            QLabel { 
                background: transparent;
                color: white; 
                font-size: 11px;
            }
        """
        )

    def clear_warnings_errors(self):
        """Clear all warnings and errors"""
        self.current_warnings.clear()
        self.current_errors.clear()
        self.update_error_display()

    def set_background_image_opaque(self, image_path, opacity=0.35):
        """
        Set a semi-transparent background image.
        `opacity` = 0.0 (invisible) … 1.0 (full strength)
        """
        if not (0.0 <= opacity <= 1.0):
            raise ValueError("opacity must be 0.0 – 1.0")

        if not os.path.exists(image_path):
            return

        # 1) load & scale
        pix = QPixmap(image_path).scaled(
            self.width(),
            self.height(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )

        # 2) paint it onto a transparent canvas with the desired alpha
        result = QPixmap(pix.size())
        result.fill(Qt.transparent)  # RGBA buffer
        painter = QPainter(result)
        painter.setOpacity(opacity)  # 0-1 float
        painter.drawPixmap(0, 0, pix)
        painter.end()

        # 3) install as window background
        pal = self.palette()
        pal.setBrush(QPalette.Window, QBrush(result))
        self.setPalette(pal)
        self.setAutoFillBackground(True)  # palette actually used

    def clear_selections(self):
        """Clear all channel selections and reset the label."""
        for checkbox in self.channel_checkboxes.values():
            checkbox.setChecked(False)
        self.channel_label.setText("Select Speaker Channels (Manual Select):")
        # self.app_settings['speaker_config'] = 'Manual Select'
        # SettingsDialog.save(self.app_settings)
        qs.set("speaker_config", "Manual Select")

    def load_stimulus_file(self):
        """Load a stimulus WAV file using a file dialog."""
        # Get last directory from settings, default to empty string
        last_dir = self.qsettings.value("last_stimulus_directory", "")
        file_path, _ = QFileDialog.getOpenFileName(
            # file_path = get_open_file(
            self,
            "Select Stimulus WAV File",
            last_dir,
            "WAV Files (*.wav);;All Files (*.*)",
        )
        if not file_path:
            # User pressed Cancel – keep the previous state but refresh button
            self._refresh_repeat_button()
            return

        # Normalize paths for the current OS
        Qrew_common.selected_stimulus_path = os.path.normpath(file_path)
        Qrew_common.stimulus_dir = os.path.normpath(os.path.dirname(file_path))
        self.qsettings.setValue("last_stimulus_directory", Qrew_common.stimulus_dir)
        stimulus_name = os.path.basename(file_path)
        self.status_label.setText(f"Selected stimulus: {stimulus_name}")
        self._refresh_repeat_button()

    def show_error_message(self, title, message):
        """Thread-safe method to show error messages"""
        QrewMessageBox.critical(self, title, message)

    def on_start(self):
        """User pressed Start Measurement."""
        if not Qrew_common.selected_stimulus_path:
            QrewMessageBox.critical(
                self, "No Stimulus File", ("Please load a stimulus WAV file first.")
            )
            return

        try:
            num_pos = int(self.pos_selector.currentText())
            if num_pos <= 0:
                raise ValueError
        except ValueError:
            QrewMessageBox.critical(
                self, "Invalid Input", "Select 1 – 9 microphone positions."
            )
            return

        self.last_valid_positions = num_pos

        selected = [
            abbr
            for abbr, checkbox in self.channel_checkboxes.items()
            if checkbox.isChecked()
        ]
        if not selected:
            QrewMessageBox.critical(
                self, "No Channels", ("Please select at least one speaker channel.")
            )
            return

        # Check for existing measurements using worker thread
        self.status_label.setText("Checking for existing measurements...")

        # Import worker
        try:
            from .Qrew_workers_v2 import MeasurementCountWorker
        except ImportError:
            from Qrew_workers_v2 import MeasurementCountWorker

        # Create and connect worker
        self.count_worker = MeasurementCountWorker()
        self.count_worker.count_received.connect(
            lambda count: self._handle_measurement_count(count, selected, num_pos)
        )
        self.count_worker.error_occurred.connect(
            lambda err: QrewMessageBox.critical(
                self, "Error", f"Failed to get measurement count: {err}"
            )
        )
        self.count_worker.start()

    def _handle_measurement_count(
        self, measurement_count, selected_channels, num_positions
    ):
        """Handle measurement count received from worker"""
        # Import dialog
        try:
            from .Qrew_dialogs import ClearMeasurementsDialog
        except ImportError:
            from Qrew_dialogs import ClearMeasurementsDialog

        dialog = ClearMeasurementsDialog(measurement_count, self)

        if dialog.exec_() != QDialog.Accepted:
            return  # User cancelled

        # Handle user's choice
        if dialog.result == "delete":
            self.status_label.setText("Clearing existing measurements...")

            # Import worker
            try:
                from .Qrew_workers_v2 import DeleteMeasurementsWorker
            except ImportError:
                from Qrew_workers_v2 import DeleteMeasurementsWorker

            # Create delete worker
            self.delete_worker = DeleteMeasurementsWorker()
            self.delete_worker.status_update.connect(self.update_status)
            self.delete_worker.delete_complete.connect(
                lambda success, count, err: self._handle_delete_complete(
                    success, count, err, selected_channels, num_positions
                )
            )
            self.delete_worker.start()
        else:
            # Continue without deleting
            self._start_measurements_after_dialog(selected_channels, num_positions)

    def _handle_delete_complete(
        self, success, count_deleted, error_msg, selected_channels, num_positions
    ):
        """Handle delete completion"""
        if not success:
            QrewMessageBox.critical(
                self,
                "Delete Failed",
                f"Failed to delete measurements:\n{error_msg}",
            )
            return
        if count_deleted > 0:
            QrewMessageBox.information(
                self,
                "Measurements Cleared",
                (f"Successfully deleted {count_deleted} existing " "measurements."),
            )

        # Continue with starting measurements
        self._start_measurements_after_dialog(selected_channels, num_positions)

    def _start_measurements_after_dialog(self, selected_channels, num_positions):
        """Start measurements after dialog handling"""
        # Reset abort flag when starting new measurements
        self._abort_called = False

        # Reset measurement state
        self.measurement_state.update(
            {
                "channels": selected_channels,
                "num_positions": num_positions,
                "current_position": 0,
                "initial_count": -1,
                "running": True,
                "channel_index": 0,
                "repeat_mode": False,  # clean slate
            }
        )

        # Hide metrics when starting new measurement
        self.retake_pairs.clear()  # clear any stale repeat list
        self.retake_pairs = []  # clear any stale repeat list

        self.start_button.setEnabled(False)
        # lock UI while the worker is active
        self._set_controls_enabled(False)
        self.status_label.setText("Starting measurement process...")
        print("DEBUG channels :", self.measurement_state["channels"])
        print("DEBUG positions:", self.last_valid_positions)

        # Show initial position dialog
        self.show_position_dialog(0)

    def show_position_dialog(self, position):
        """Show position dialog and handle user response"""
        dialog = PositionDialog(position, self)

        if dialog.exec_():
            # User clicked OK - continue measurement
            # For repeat mode, don't reset channel_index
            if not self.measurement_state.get("repeat_mode", False):
                if position == 0:
                    # First position in normal mode - reset channel index
                    self.measurement_state["channel_index"] = 0

            # Update the current position in state
            self.measurement_state["current_position"] = position

            # Start or continue the measurement
            if not self.measurement_worker or not self.measurement_worker.isRunning():
                # No worker running - start a new one
                self.start_worker()
            else:
                # Worker is already running - just signal it to continue
                # The worker should be waiting for this signal
                self.measurement_worker.continue_after_dialog()
        else:
            # User cancelled - stop everything
            self.measurement_state["running"] = False
            self.start_button.setEnabled(True)
            # Stop flash
            #  if self.flash_timer:
            #     self.flash_timer.stop()
            self.sofa_widget.set_flash(False)
            # Stop worker if running
            if self.measurement_worker and self.measurement_worker.isRunning():
                self.measurement_worker.stop()

    def start_worker(self):
        self.measurement_worker = MeasurementWorker(self.measurement_state, self)
        self.measurement_worker.status_update.connect(self.update_status)
        self.measurement_worker.error_occurred.connect(self.show_error_message)
        self.measurement_worker.finished.connect(self.on_measurement_finished)
        self.measurement_worker.show_position_dialog.connect(self.show_position_dialog)
        # self.measurement_worker.grid_flash_signal.connect(self.update_grid_flash)
        # self.measurement_worker.grid_position_signal.connect(self.update_grid_position)
        self.measurement_worker.metrics_update.connect(self.update_metrics_display)
        self.measurement_worker.metrics_update.connect(
            self.update_quality_entry, Qt.DirectConnection
        )
        self.measurement_worker.show_quality_dialog.connect(
            self.show_measurement_quality_dialog
        )
        # Add visualization update connection
        self.measurement_worker.visualization_update.connect(
            self.update_visualization_from_worker
        )

        self.measurement_worker.start()

    def on_measurement_finished(self):
        """Measurement worker finished – update UI and state."""
        self.start_button.setEnabled(True)
        # unlock the GUI
        self._set_controls_enabled(True)

        # Disconnect signals to prevent memory leaks
        if self.measurement_worker:
            try:
                self.measurement_worker.status_update.disconnect()
                self.measurement_worker.error_occurred.disconnect()
                self.measurement_worker.finished.disconnect()
                self.measurement_worker.show_position_dialog.disconnect()
                self.measurement_worker.metrics_update.disconnect()
                self.measurement_worker.show_quality_dialog.disconnect()
                self.measurement_worker.visualization_update.disconnect()
            except TypeError:
                # Signal was already disconnected
                pass

        # Remember if abort was called and reset the flag
        was_aborted = self._abort_called
        self._abort_called = False

        save_after_repeat = qs.get("save_after_repeat", False)

        repeat = self.measurement_state.pop("repeat_mode", False)
        repeat_channels = self.measurement_state.pop("repeat_channels", [])
        repeat_positions = self.measurement_state.pop("repeat_positions", [])

        self.build_retake_caution_list()  # refresh list first

        if repeat:
            if was_aborted:
                self.status_label.setText("Repeat measurements aborted.")
            elif not self.retake_pairs:  # everything passed!
                self.status_label.setText("All repeat measurements passed.")
            else:
                self.status_label.setText(
                    "Repeat measurements completed – some still need re-take."
                )
            # Only show save dialog if not aborted and save_after_repeat is true
            if save_after_repeat and not was_aborted:
                self.show_save_measurements_dialog()
            # Keep ONLY the user-selected repeat channels and positions visible after completion
            self.selected_channels_for_viz = set(repeat_channels)
            self.selected_positions_for_viz = set(repeat_positions)

            # Keep ONLY repeat channel checkboxes checked
            for abbr, checkbox in self.channel_checkboxes.items():
                checkbox.setChecked(abbr in repeat_channels)

        else:
            # For normal measurements, don't reset user selections
            # Keep the channels and positions the user selected
            if was_aborted:
                self.status_label.setText("Measurement process aborted.")
            else:
                self.status_label.setText("Measurement process completed.")
                # Only show save dialog if not aborted
                if not was_aborted:
                    self.show_save_measurements_dialog()

        #   if self.flash_timer:
        #      self.flash_timer.stop()
        self.sofa_widget.set_flash(False)

        if hasattr(self, "sofa_widget") and self.sofa_widget:
            self.sofa_widget.set_active_speakers([])
            self.sofa_widget.set_flash(False)
            self.sofa_widget.set_current_pos(
                self.measurement_state.get("current_position", 0)
            )
            self.sofa_widget.update()

        # Clear animations and update visualization with final selections
        if hasattr(self, "compact_mic_widget") and self.compact_mic_widget:
            self.compact_mic_widget.set_active_speakers([])  # Clear active speakers
            self.compact_mic_widget.set_flash_state(False)  # Stop flash
            self.compact_mic_widget.set_selected_channels(
                list(self.selected_channels_for_viz)
            )
            self.compact_mic_widget.set_active_mic(None)  # ← clear dot ■
            self.compact_mic_widget.update()  # ② repaint now

            # Update position visibility
            if hasattr(self, "selected_positions_for_viz"):
                self.compact_mic_widget.set_visible_positions_list(
                    list(self.selected_positions_for_viz)
                )
            else:
                # Reset to show all positions from selector
                current_positions = int(self.pos_selector.currentText())
                self.compact_mic_widget.set_visible_positions(current_positions)

            self.compact_mic_widget.update()

        if hasattr(self, "visualization_dialog") and self.visualization_dialog:
            # Update position visibility for dialog too
            if hasattr(self, "selected_positions_for_viz"):
                self.visualization_dialog.mic_widget.set_visible_positions_list(
                    list(self.selected_positions_for_viz)
                )
            else:
                current_positions = int(self.pos_selector.currentText())
                self.visualization_dialog.mic_widget.set_visible_positions(
                    current_positions
                )

            self.visualization_dialog.update_visualization(
                None,
                [],  # No active speakers
                list(
                    self.selected_channels_for_viz
                ),  # Only user-selected repeat channels
                False,  # No flash
            )

        if self.measurement_worker:
            self.measurement_worker = None

    def build_retake_caution_list(self):
        """
        Re-scan self.measurement_qualities and build a list of
        (channel, position) pairs that are still rated RETAKE or CAUTION.

        The list is stored in self.retake_pairs so the Repeat-Measurement
        dialog can use it later.
        """
        qualities = getattr(self, "measurement_qualities", {})
        self.retake_pairs = [
            (ch, pos)
            for (ch, pos), q in qualities.items()
            if q.get("rating") in ("RETAKE", "CAUTION")
        ]

    def show_save_measurements_dialog(self):
        """Show dialog to save raw measurements"""
        dialog = SaveMeasurementsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            file_path = dialog.result_file_path
            if file_path:
                self.save_raw_measurements(file_path)

    def save_raw_measurements(self, file_path):
        """Save raw measurements to file"""
        self.status_label.setText("Saving raw measurements...")

        # Disable buttons during save
        self.start_button.setEnabled(False)
        self.cross_button.setEnabled(False)
        self.vector_button.setEnabled(False)
        self.full_button.setEnabled(False)

        # Import worker
        try:
            from .Qrew_workers_v2 import SaveMeasurementsWorker
        except ImportError:
            from Qrew_workers_v2 import SaveMeasurementsWorker

        # Create save worker
        self.save_worker = SaveMeasurementsWorker(file_path)
        self.save_worker.status_update.connect(self.update_status)
        self.save_worker.save_complete.connect(
            lambda success, err: self._handle_save_complete(success, err, file_path)
        )
        self.save_worker.start()

    def _handle_save_complete(self, success, error_msg, file_path):
        """Handle save completion"""
        # Re-enable buttons
        self.start_button.setEnabled(True)
        self.cross_button.setEnabled(True)
        self.vector_button.setEnabled(True)
        self.full_button.setEnabled(True)

        if success:
            self.update_status(
                f"Raw measurements saved successfully to: {os.path.basename(file_path)}"
            )
            QrewMessageBox.information(
                self, "Save Successful", f"Raw measurements saved to:\n{file_path}"
            )
        else:
            self.update_status(f"Failed to save measurements: {error_msg}")
            QrewMessageBox.critical(
                self, "Save Failed", f"Failed to save measurements:\n{error_msg}"
            )

    def _handle_delete_by_uuid_complete(
        self, deleted_count, failed_count, selected_measurements
    ):
        """Handle delete by UUID completion"""
        if failed_count > 0:
            QrewMessageBox.warning(
                self,
                "Deletion Issues",
                f"Deleted {deleted_count} measurements, but {failed_count} failed to delete.",
            )

        # Remove deleted measurements from quality tracking
        for measurement in selected_measurements:
            key = (measurement["channel"], measurement["position"])
            if key in self.measurement_qualities:
                del self.measurement_qualities[key]

        # Continue with the rest of the repeat logic
        # (the visualization updates will happen in the main thread after this)

    def on_cross_corr_align(self):
        """Handle cross correlation alignment button click"""
        selected = [
            abbr
            for abbr, checkbox in self.channel_checkboxes.items()
            if checkbox.isChecked()
        ]
        if not selected:
            QrewMessageBox.critical(
                self, "No Channels", "Please select at least one speaker channel."
            )
            return

        self.start_processing_async(selected, "cross_corr_only")

    def on_vector_average(self):
        """Handle vector average button click"""
        selected = [
            abbr
            for abbr, checkbox in self.channel_checkboxes.items()
            if checkbox.isChecked()
        ]
        if not selected:
            QrewMessageBox.critical(
                self, "No Channels", "Please select at least one speaker channel."
            )
            return

        self.start_processing_async(selected, "vector_avg_only")

    def on_full_processing(self):
        """Handle full processing (cross corr + vector avg) button click"""
        selected = [
            abbr
            for abbr, checkbox in self.channel_checkboxes.items()
            if checkbox.isChecked()
        ]
        if not selected:
            QrewMessageBox.critical(
                self, "No Channels", "Please select at least one speaker channel."
            )
            return

        self.start_processing_async(selected, "full")

    def start_processing_async(self, selected_channels, mode):
        """Start processing workflow asynchronously"""
        # Disable buttons during initial data gathering
        self._set_processing_buttons_enabled(False)
        self.update_status("Preparing for processing...")

        # Start worker to get channel measurements
        self.channel_measurements_worker = GetChannelMeasurementsWorker(
            selected_channels, mode
        )
        self.channel_measurements_worker.status_update.connect(self.update_status)
        self.channel_measurements_worker.measurements_received.connect(
            self.on_channel_measurements_received
        )
        self.channel_measurements_worker.error_occurred.connect(
            self.on_channel_measurements_error
        )
        self.channel_measurements_worker.start()

    def on_channel_measurements_received(self, channels_with_data, mode):
        """Handle channel measurements received from worker"""
        # Continue with the original start_processing logic
        self.start_processing_with_data(channels_with_data, mode)

    def on_channel_measurements_error(self, title, message):
        """Handle error getting channel measurements"""
        self._set_processing_buttons_enabled(True)
        QrewMessageBox.critical(self, title, message)

    def _set_processing_buttons_enabled(self, enabled):
        """Enable/disable processing buttons"""
        self.cross_button.setEnabled(enabled)
        self.vector_button.setEnabled(enabled)
        self.full_button.setEnabled(enabled)
        self.start_button.setEnabled(enabled)

    def start_processing_with_data(self, channels_with_data, mode):
        """Start processing workflow with pre-loaded data"""
        # Convert to the format expected by processing worker (just UUIDs)
        channels_with_uuids = {}
        for channel, measurements in channels_with_data.items():
            channels_with_uuids[channel] = [m["uuid"] for m in measurements]

        # Determine starting step based on mode
        if mode == "cross_corr_only":
            start_step = "cross_corr"
        elif mode == "vector_avg_only":
            start_step = "vector_avg"
        else:  # 'full'
            start_step = "cross_corr"

        # Initialize processing state
        self.processing_state = {
            "channels": list(channels_with_data.keys()),
            "channel_measurements": channels_with_data,
            "current_step": start_step,
            "channel_index": 0,
            "running": True,
            "mode": mode,
        }

        # Disable buttons during processing
        self._set_processing_buttons_enabled(False)
        # lock UI while the worker is active
        self._set_controls_enabled(False)

        # Start processing worker
        self.processing_worker = ProcessingWorker(self.processing_state)
        self.processing_worker.status_update.connect(self.update_status)
        self.processing_worker.error_occurred.connect(self.show_error_message)
        self.processing_worker.finished.connect(self.on_processing_finished)
        self.processing_worker.start()

    def on_processing_finished(self):
        """Called when processing is complete"""
        self.cross_button.setEnabled(True)
        self.vector_button.setEnabled(True)
        self.full_button.setEnabled(True)
        self.start_button.setEnabled(True)
        # Enable GUI Controls
        self._set_controls_enabled(True)
        self.status_label.setText("Processing completed.")

        # Disconnect signals to prevent memory leaks
        if hasattr(self, "processing_worker") and self.processing_worker:
            try:
                self.processing_worker.status_update.disconnect()
                self.processing_worker.error_occurred.disconnect()
                self.processing_worker.finished.disconnect()
            except TypeError:
                # Signal was already disconnected
                pass
            self.processing_worker = None

    def closeEvent(self, event):
        """Handle window close event"""
        print("DEBUG: MainWindow closeEvent called")

        # Clean up VLC widget properly
        if self.vlc_widget:
            try:
                print("DEBUG: Cleaning up VLC widget")
                # Request shutdown which will handle cleanup and closing
                self.vlc_widget.shutdown()
                # Give it a moment to clean up
                QApplication.processEvents()
                self.vlc_widget = None
            except Exception as e:
                print(f"Error cleaning up VLC widget: {e}")

        # Also clean up the global VLC player
        try:
            print("DEBUG: Stopping global VLC player")
            stop_vlc_and_exit()
        except Exception as e:
            print(f"Error stopping global VLC player: {e}")

        # Stop measurement worker if running
        if self.measurement_worker and self.measurement_worker.isRunning():
            print("DEBUG: Stopping measurement worker")
            self.measurement_worker.stop()
            self.measurement_worker.wait(2000)  # Wait up to 2 seconds

        # Stop processing worker if running
        if (
            hasattr(self, "processing_worker")
            and self.processing_worker
            and self.processing_worker.isRunning()
        ):
            print("DEBUG: Stopping processing worker")
            self.processing_worker.stop()
            self.processing_worker.wait(2000)  # Wait up to 2 seconds

        # Stop Flask server
        print("DEBUG: Stopping Flask server")
        stop_flask_server()  # make sure the port is released

        # Accept the event and continue with default cleanup
        event.accept()
        super().closeEvent(event)  # default tidy-up

    #  event.accept()

    def show_repeat_measurement_dialog(self):
        """Show the repeat measurement dialog."""
        print("DEBUG channels :", self.measurement_state["channels"])
        print("DEBUG positions:", self.last_valid_positions)

        if not self.measurement_qualities:
            QrewMessageBox.information(
                self,
                "No Measurements",
                "No completed measurements available for repeat.",
            )
            return

        dialog = RepeatMeasurementDialog(
            self.measurement_qualities,
            # self.measurement_state.get('num_positions', 9),
            self.last_valid_positions,
            self,
        )

        if dialog.exec_() == QDialog.Accepted and dialog.result == "proceed":
            selected_measurements = dialog.selected_measurements
            if selected_measurements:
                self.handle_repeat_measurements(selected_measurements)

    def handle_repeat_measurements(self, selected_measurements):
        """Handle the repeat measurement process."""
        if not Qrew_common.selected_stimulus_path:
            message = (
                "You must load the sweep WAV before repeating measurements.\n"
                "Load it now?"
            )
            if (
                QrewMessageBox.question(
                    self,
                    "Stimulus file required",
                    message,
                    QrewMessageBox.Yes | QrewMessageBox.No,
                )
                == QrewMessageBox.Yes
            ):
                self.load_stimulus_file()  # your existing loader
                if not Qrew_common.selected_stimulus_path:
                    return  # user cancelled
            else:
                return  # aborted by user

        # Show deletion confirmation
        delete_dialog = DeleteSelectedMeasurementsDialog(selected_measurements, self)
        if delete_dialog.exec_() != QDialog.Accepted:
            return

        # Delete selected measurements
        self.status_label.setText("Deleting selected measurements...")
        uuid_list = [m["uuid"] for m in selected_measurements]

        # Import worker
        try:
            from .Qrew_workers_v2 import DeleteMeasurementsByUuidWorker
        except ImportError:
            from Qrew_workers_v2 import DeleteMeasurementsByUuidWorker

        # Create delete worker
        self.delete_uuid_worker = DeleteMeasurementsByUuidWorker(uuid_list)
        self.delete_uuid_worker.status_update.connect(self.update_status)
        self.delete_uuid_worker.delete_complete.connect(
            lambda deleted, failed: self._handle_delete_by_uuid_complete(
                deleted, failed, selected_measurements
            )
        )
        self.delete_uuid_worker.start()

        remeasure_pairs = []
        user_selected_repeat_channels = set()
        user_selected_repeat_positions = set()
        for m in selected_measurements:
            remeasure_pairs.append((m["channel"], m["position"], m["uuid"]))
            user_selected_repeat_channels.add(m["channel"])
            user_selected_repeat_positions.add(m["position"])

        # Clear ALL previous channel selections first
        for abbr, checkbox in self.channel_checkboxes.items():
            checkbox.setChecked(False)

        # Only check the channels the user selected for repeat
        for channel in user_selected_repeat_channels:
            if channel in self.channel_checkboxes:
                self.channel_checkboxes[channel].setChecked(True)

        # Update position selector to show max position needed
        max_position = (
            max(user_selected_repeat_positions) if user_selected_repeat_positions else 0
        )
        # Find the minimum number of positions that includes all selected positions
        min_positions_needed = max_position + 1  # +1 because positions are 0-indexed

        # Set the position selector to show at least the needed positions
        current_positions = int(self.pos_selector.currentText())
        if min_positions_needed > current_positions:
            self.pos_selector.setCurrentText(str(min_positions_needed))

        # Update visualization to show only user-selected repeat channels and positions
        self.selected_channels_for_viz = user_selected_repeat_channels
        self.selected_positions_for_viz = (
            user_selected_repeat_positions  # Track selected positions
        )
        self.update_channel_visualization()
        self.update_position_visualization_for_repeat()

        # Reset abort flag when starting repeat measurements
        self._abort_called = False

        # Update measurement state for remeasurement
        self.measurement_state.update(
            {
                "channels": [],
                "num_positions": 0,
                "current_position": 0,
                "initial_count": -1,
                "running": True,
                "channel_index": 0,
                "repeat_mode": True,
                "remeasure_pairs": remeasure_pairs,
                "repeat_channels": list(
                    user_selected_repeat_channels
                ),  # Only user-selected channels
                "repeat_positions": list(
                    user_selected_repeat_positions
                ),  # Store selected positions
                "current_remeasure_pair": None,
                "pair_completed": False,
                "re_idx": 0,
            }
        )

        self.start_button.setEnabled(False)
        # Create summary message
        channel_list = ", ".join(sorted(user_selected_repeat_channels))
        position_list = ", ".join(
            str(p) for p in sorted(user_selected_repeat_positions)
        )
        self.status_label.setText(
            f"Starting remeasurement for channels: {channel_list} at positions: {position_list}..."
        )

        # Start with the first position to remeasure
        # first_position = min(positions_to_remeasure)
        # self.show_position_dialog(first_position)
        self.start_worker()

    def update_position_visualization_for_repeat(self):
        """Update position visualization specifically for repeat measurements"""
        if not hasattr(self, "selected_positions_for_viz"):
            return

        # Update sofa view to show only selected positions
        if hasattr(self, "sofa_widget") and self.sofa_widget:
            self.sofa_widget.set_visible_positions_list(
                list(self.selected_positions_for_viz)
            )

        # Update compact view to show only selected positions
        if hasattr(self, "compact_mic_widget") and self.compact_mic_widget:
            self.compact_mic_widget.set_visible_positions_list(
                list(self.selected_positions_for_viz)
            )

        # Update full theater view to show only selected positions
        if hasattr(self, "visualization_dialog") and self.visualization_dialog:
            self.visualization_dialog.mic_widget.set_visible_positions_list(
                list(self.selected_positions_for_viz)
            )

    def start_quality_loading_worker(self):
        """Start worker to load existing measurement qualities"""
        self.status_label.setText("Loading existing measurements...")

        # Disable buttons while loading
        self._set_loading_state(True)

        self.quality_worker = LoadMeasurementsQualityWorker()
        self.quality_worker.status_update.connect(self.update_status)
        self.quality_worker.quality_loaded.connect(self.on_quality_loaded)
        self.quality_worker.start()

    def on_quality_loaded(self, measurement_qualities):
        """Handle loaded quality data"""
        self.measurement_qualities = measurement_qualities

        # Re-enable buttons
        self._set_loading_state(False)

        if measurement_qualities:
            count = len(measurement_qualities)
            self.status_label.setText(f"Loaded quality data for {count} measurements")
            print(f"Loaded quality data for {count} existing measurements")
        else:
            self.status_label.setText("Please load stimulus file to begin...")

    def _set_loading_state(self, loading):
        """Enable/disable buttons during loading operations"""
        # Don't disable everything, just the main action buttons
        buttons_to_control = [
            self.start_button,
            self.repeat_button,
            self.cross_button,
            self.vector_button,
            self.full_button,
        ]

        for button in buttons_to_control:
            button.setEnabled(not loading)

        if loading:
            # Change cursor to indicate loading
            self.setCursor(Qt.WaitCursor)
        else:
            self.unsetCursor()

    def show_measurement_quality_dialog(self, measurement_info):
        """Show quality dialog and handle user choice"""
        dialog = MeasurementQualityDialog(measurement_info, self)
        result = dialog.exec_()

        if result == 1:  # Remeasure
            # Delete the current measurement using worker
            uuid = measurement_info["uuid"]

            # Import worker dynamically
            try:
                from .Qrew_workers_v2 import DeleteMeasurementByUuidWorker
            except ImportError:
                from Qrew_workers_v2 import DeleteMeasurementByUuidWorker

            # Store measurement info for callback
            self._remeasure_info = measurement_info

            # Create and start delete worker
            self.delete_single_worker = DeleteMeasurementByUuidWorker(uuid)
            self.delete_single_worker.status_update.connect(self.update_status)
            self.delete_single_worker.delete_complete.connect(
                self._on_single_delete_complete
            )
            self.delete_single_worker.start()

        elif result == 2:  # Continue
            # Tell worker to remeasure
            if self.measurement_worker:
                self.measurement_worker.handle_quality_dialog_response("continue")

        else:  # Stop (0)
            # Stop the measurement process
            if self.measurement_worker:
                self.measurement_worker.handle_quality_dialog_response("stop")

    def open_settings_dialog(self):
        """Open the settings dialog to configure application settings."""
        settings_dlg = SettingsDialog(self)

        if settings_dlg.exec_():
            # for key, value in dlg.values().items():
            #   qs.set(key, value)          # persist + share
            self.apply_settings()  # read straight from qs

    def apply_settings(self):
        """Apply settings after load / save."""
        if qs.get("show_tooltips", True):
            QToolTip.setFont(QFont("Arial", 10))
        else:
            QToolTip.hideText()
        use_light = qs.get("use_light_theme", False)
        palette = get_light_palette() if use_light else get_dark_palette()
        qt_app = QApplication.instance()
        qt_app.setPalette(palette)
        cfg_name = qs.get("speaker_config", "Manual Select")
        self._set_channel_header(cfg_name)

        cfg_map = get_speaker_configs()
        if cfg_name in cfg_map and cfg_map[cfg_name]:
            wanted = set(cfg_map[cfg_name])
            for lbl, cb in self.channel_checkboxes.items():
                cb.setChecked(lbl in wanted)
        self.update_channel_visualization()
        # Apply visualization mode
        viz_mode = self.get_current_viz_mode()
        # Defer mode switching to ensure UI is fully initialized
        QTimer.singleShot(100, lambda: self.switch_visualization_mode(viz_mode))

    def switch_visualization_mode(self, mode):
        """Switch between Sofa / Compact / Full theatre views."""
        qs.set("viz_view", mode)  # persist the choice

        if mode == "Sofa View":  # ───── ① Sofa  ─────
            self.show_sofa_visualization()

        elif mode == "Compact Theater View":  # ───── ② COMPACT ─────

            self.show_compact_visualization()  # (creates if needed)

        elif mode == "Full Theater View":  # ───── ③ FULL ─────
            self.show_sofa_visualization()
            self.show_visualization_dialog()

    def ensure_widget_visibility(self):
        """Ensure widgets are in the correct visibility state for current mode"""
        current_mode = self.get_current_viz_mode()

        if current_mode == "Sofa View":
            if hasattr(self, "sofa_widget") and self.sofa_widget:
                self.sofa_widget.show()
            if hasattr(self, "compact_mic_widget") and self.compact_mic_widget:
                self.compact_mic_widget.hide()
        elif current_mode == "Compact Theater View":
            if hasattr(self, "sofa_widget") and self.sofa_widget:
                self.sofa_widget.hide()
            if hasattr(self, "compact_mic_widget") and self.compact_mic_widget:
                self.compact_mic_widget.show()

    def get_current_viz_mode(self):
        """Get the current visualization mode"""
        return qs.get("viz_view", "Sofa View")

    def show_compact_visualization(self):
        """Show the compact mic position visualization."""
        # Ensure state is synchronized
        self.sync_visualization_state()

        # Prevent layout bouncing by disabling updates during widget switch
        # self.setUpdatesEnabled(False)

        # 1) kick Sofa out of the layout
        self._detach_from_grid(self.sofa_widget)

        # 2) build the wrapper once
        if not getattr(self, "compact_wrapper", None):
            self.compact_wrapper = QWidget()
            hbox = QHBoxLayout(self.compact_wrapper)
            hbox.setContentsMargins(0, 0, 0, 0)

            self.compact_wrapper.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )

            if not getattr(self, "compact_mic_widget", None):
                self.compact_mic_widget = MicPositionWidget(
                    ":/assets/images/hometheater_base_persp.png",
                    ":/assets/json_files/room_layout_persp.json",
                )
            # Scale the widget immediately instead of using timer
            self.scale_compact_widget()

            hbox.addStretch()  # Center the widget
            hbox.addWidget(self.compact_mic_widget)
            hbox.addStretch()  # Center the widget

        # 3) (re-)attach the wrapper
        self._attach_to_grid(self.compact_wrapper)

        # 4) channels, positions, flashing
        self.compact_mic_widget.set_selected_channels(
            list(self.selected_channels_for_viz)
        )
        # Use same logic as full theater view for positions
        if (
            hasattr(self, "selected_positions_for_viz")
            and self.selected_positions_for_viz
        ):  # Check if not empty
            self.compact_mic_widget.set_visible_positions_list(
                list(self.selected_positions_for_viz)
            )
        else:
            self.compact_mic_widget.set_visible_positions(
                int(self.pos_selector.currentText())
            )

        # Re-enable updates and force a single update
        #  self.setUpdatesEnabled(True)
        self.update_mic_visualization()

    def show_sofa_visualization(self):
        """Show the Sofa position visualization."""
        # Ensure state is synchronized
        self.sync_visualization_state()

        # Prevent layout bouncing by disabling updates during widget switch
        #  self.setUpdatesEnabled(False)

        # make sure compact wrapper is out
        if getattr(self, "compact_wrapper", None):
            self._detach_from_grid(self.compact_wrapper)

        # Scale the widget immediately instead of using timer
        self.scale_compact_widget()

        self._attach_to_grid(self.sofa_widget)

        # Use current position selection state
        if (
            hasattr(self, "selected_positions_for_viz")
            and self.selected_positions_for_viz
        ):
            self.sofa_widget.set_visible_positions_list(
                list(self.selected_positions_for_viz)
            )
        else:
            self.sofa_widget.set_visible_positions(int(self.pos_selector.currentText()))

        # Scale immediately instead of using timer
        self.scale_sofa_widget()

        # Re-enable updates and force a single update
        #   self.setUpdatesEnabled(True)
        self.update_mic_visualization()  # draw ring immediately

    def _scale_current_grid_container_widget(self):
        """Scale whichever visual-widget is currently attached."""
        if getattr(self, "sofa_widget", None) and self.sofa_widget.parent():
            self.scale_sofa_widget()
        elif getattr(self, "compact_wrapper", None) and self.compact_wrapper.parent():
            self.scale_compact_widget()

    def scale_sofa_widget(self):
        """Shrink / grow the sofa picture so it fills its container."""
        if not getattr(self, "sofa_widget", None):
            return
        if not self.sofa_widget.isVisible():
            return
        grid_container = self.grid_container  # we stored this earlier
        if grid_container is None:
            return

        avail_w = max(50, grid_container.width() - 12)  # 6-px margin left+right
        avail_h = max(50, grid_container.height() - 12)

        ow = self.sofa_widget.original_size.width()
        oh = self.sofa_widget.original_size.height()
        if ow == 0 or oh == 0:
            return

        scale = min(avail_w / ow, avail_h / oh)
        scale = max(scale, 0.05)  # never disappear completely
        self.sofa_widget.set_scale(scale)

    # Method for scaling compact widget:
    def scale_compact_widget(self):
        """Scale the compact widget to fit in the container"""
        if not hasattr(self, "compact_mic_widget") or not self.compact_mic_widget:
            return

        grid_container = self.grid_container
        if grid_container is None:
            return
        # Ensure we have valid dimensions
        container_width = max(grid_container.width(), 400)  # Minimum width
        container_height = max(grid_container.height(), 300)  # Minimum height

        # optional frame-margin (in logical pixels)
        margin = 6
        aw = container_width - margin * 2
        ah = container_height - margin * 2

        # ––––– scaling that keeps aspect ratio –––––
        ow = self.compact_mic_widget.original_size.width()
        oh = self.compact_mic_widget.original_size.height()

        scale = min(aw / ow, ah / oh)  # nothing is clamped ⇢ 1.0 max
        scale = max(scale, 0.1)  # but never smaller than 10 %

        self.compact_mic_widget.set_scale(scale)

    def show_visualization_dialog(self):
        """Show full visualization in a separate dialog"""
        # Ensure state is synchronized
        self.sync_visualization_state()

        if not self.visualization_dialog:
            self.visualization_dialog = MicPositionVisualizationDialog(self)

        # initial channels
        self.visualization_dialog.mic_widget.set_selected_channels(
            list(self.selected_channels_for_viz)
        )

        # ── NEW: correct number of mic positions ──────────────────
        if (
            hasattr(self, "selected_positions_for_viz")
            and self.selected_positions_for_viz
        ):  # Check if not empty
            self.visualization_dialog.mic_widget.set_visible_positions_list(
                list(self.selected_positions_for_viz)
            )
        else:
            self.visualization_dialog.mic_widget.set_visible_positions(
                int(self.pos_selector.currentText())
            )
        self.visualization_dialog.show()
        self.visualization_dialog.raise_()
        self.visualization_dialog.activateWindow()
        self.visualization_dialog.mic_widget.set_flash_state(self._flash_state)

        self.update_mic_visualization()

    def update_mic_visualization(self):
        """Update all visualization widgets with current state"""
        # Get current position
        current_pos = self.measurement_state.get("current_position", 0)

        # Get current active speaker (only during measurement)
        active_speakers = []
        if self.measurement_state.get("running", False):
            channels = self.measurement_state.get("channels", [])
            channel_index = self.measurement_state.get("channel_index", 0)
            if 0 <= channel_index < len(channels):
                active_speakers = [channels[channel_index]]
        flash = self._flash_state
        # Get selected channels for display
        selected_channels = list(self.selected_channels_for_viz)
        # --- Sofa ---------------------------------
        if hasattr(self, "sofa_widget"):
            self.sofa_widget.set_active_mic(current_pos)
            self.sofa_widget.set_active_speakers(active_speakers)
            self.sofa_widget.set_flash(flash)
            # self.sofa_widget.update()

        # --- Compact view ------------------------------------
        if (
            getattr(self, "compact_mic_widget")
            and self.compact_mic_widget
            and self.compact_mic_widget.isVisible()
        ):
            self.compact_mic_widget.set_active_mic(current_pos)
            self.compact_mic_widget.set_active_speakers(active_speakers)
            self.compact_mic_widget.set_flash_state(flash)
            # self.compact_mic_widget.update()
            # self.compact_mic_widget.set_selected_channels(selected_channels)

        # --- Full-theatre dialog -----------------------------
        if (
            getattr(self, "visualization_dialog")
            and self.visualization_dialog
            and self.visualization_dialog.isVisible()
        ):
            self.visualization_dialog.update_visualization(
                current_pos, active_speakers, selected_channels, flash
            )

    def update_visualization_from_worker(self, position, active_speakers, is_flashing):
        self._flash_state = is_flashing
        if hasattr(self, "sofa_widget"):
            self.sofa_widget.set_active_mic(position)
            self.sofa_widget.set_active_speakers(active_speakers if is_flashing else [])
            self.sofa_widget.set_flash(is_flashing)

        if (
            getattr(self, "compact_mic_widget", None)
            and self.compact_mic_widget.isVisible()
        ):
            self.compact_mic_widget.set_active_mic(position)
            self.compact_mic_widget.set_active_speakers(
                active_speakers if is_flashing else []
            )
            self.compact_mic_widget.set_flash_state(is_flashing)

        if (
            getattr(self, "visualization_dialog", None)
            and self.visualization_dialog.isVisible()
        ):
            self.visualization_dialog.update_visualization(
                position, active_speakers if is_flashing else [], flash=is_flashing
            )

    def resizeEvent(self, event):
        """Handle window resize to scale both views and maintain centering"""
        super().resizeEvent(event)
        set_background_image(self)
        # Scale whichever widget is currently active
        QTimer.singleShot(0, self._scale_current_grid_container_widget)

    def _detach_from_grid(self, widget):
        """Remove *widget* from grid_container_layout (hide but keep alive)."""
        if widget and widget.parent() is self.grid_container:
            self.grid_container_layout.removeWidget(widget)
            widget.setParent(None)
        # widget.hide()

    def _attach_to_grid(self, widget):
        """Add *widget* to grid_container_layout if it is not inside yet."""
        if widget and widget.parent() is None:
            # Add with center alignment for proper positioning
            self.grid_container_layout.addWidget(widget, 0, Qt.AlignCenter)
            widget.show()

    def sync_visualization_state(self):
        """Ensure visualization tracking variables match current UI state"""
        # Sync channels from checkboxes
        selected_channels = [
            abbr
            for abbr, checkbox in self.channel_checkboxes.items()
            if checkbox.isChecked()
        ]
        self.selected_channels_for_viz = set(selected_channels)

        # Sync positions from selector
        try:
            num_positions = int(self.pos_selector.currentText())
            self.selected_positions_for_viz = set(range(num_positions))
        except ValueError:
            pass

    def connect_visualization_signals(self):
        """Connect UI controls to visualization updates"""
        # Connect channel checkboxes with immediate update
        for checkbox in self.channel_checkboxes.values():
            checkbox.stateChanged.connect(
                lambda: QTimer.singleShot(0, self.update_channel_visualization)
            )

        # Connect position selector
        self.pos_selector.currentTextChanged.connect(self.update_position_visualization)

    def update_channel_visualization(self):
        """Update visualization when channels are selected/deselected"""
        selected_channels = [
            abbr
            for abbr, checkbox in self.channel_checkboxes.items()
            if checkbox.isChecked()
        ]

        self.selected_channels_for_viz = set(selected_channels)

        # Update compact view
        if (
            hasattr(self, "compact_mic_widget")
            and self.compact_mic_widget
            and self.compact_mic_widget.isVisible()
        ):
            self.compact_mic_widget.set_selected_channels(selected_channels)

        # Update full theater view
        if (
            hasattr(self, "visualization_dialog")
            and self.visualization_dialog
            and self.visualization_dialog.isVisible()
        ):
            self.visualization_dialog.mic_widget.set_selected_channels(
                selected_channels
            )

    def update_position_visualization(self, positions_text):
        """Update visualization when position count changes"""
        try:
            num_positions = int(positions_text)

            # Update selected positions for visualization
            self.selected_positions_for_viz = set(range(num_positions))

            if hasattr(self, "sofa_widget") and self.sofa_widget:
                self.sofa_widget.set_visible_positions(num_positions)
            # Update both views to show only the selected number of positions
            if hasattr(self, "compact_mic_widget") and self.compact_mic_widget:
                self.compact_mic_widget.set_visible_positions(num_positions)

            if hasattr(self, "visualization_dialog") and self.visualization_dialog:
                self.visualization_dialog.mic_widget.set_visible_positions(
                    num_positions
                )
        except ValueError:
            pass

    def _create_vlc_widget(self, show_gui):
        """Create VLC widget in main thread and give it to global player"""
        try:

            print(f"DEBUG: Creating VLC widget in main thread, show_gui={show_gui}")

            # Check if we need to create a new widget
            widget_needs_creation = True
            if hasattr(self, "vlc_widget") and self.vlc_widget:
                try:
                    # Check if widget is still valid (not deleted)
                    self.vlc_widget.isVisible()
                    widget_needs_creation = False
                    print("DEBUG: Existing VLC widget is still valid")
                except RuntimeError:
                    # Widget has been deleted
                    print("DEBUG: Previous VLC widget was deleted, creating new one")
                    self.vlc_widget = None

            # Create widget if needed
            if widget_needs_creation:
                self.vlc_widget = AudioPlayerWidget()
                self.vlc_widget.setFixedSize(600, 210)
                self.vlc_widget.setStyleSheet("background-color: #263238;")
                print("DEBUG: VLC widget created in main thread")

            # Give widget to global player
            _global_player.set_widget_from_main_thread(self.vlc_widget)

        except Exception as e:
            print(f"ERROR: Failed to create VLC widget in main thread: {e}")


def wait_for_rew_qt():
    """Wait for REW connection using custom dialog"""

    while True:
        # Create worker and event loop for synchronous-like behavior
        worker = REWConnectionWorker()
        loop = QEventLoop()
        connection_result = [False]

        def on_connection_checked(is_connected):
            connection_result[0] = is_connected
            loop.quit()

        def on_worker_finished():
            loop.quit()

        worker.connection_status.connect(on_connection_checked)
        worker.finished.connect(on_worker_finished)
        worker.start()

        # Create a timeout timer
        timeout_timer = QTimer()
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(loop.quit)
        timeout_timer.start(3000)  # 3 second timeout

        # Run the event loop until worker finishes or timeout
        loop.exec_()

        # Clean up
        timeout_timer.stop()
        if worker.isRunning():
            worker.terminate()
            worker.wait()

        # If connected, we're done
        if connection_result[0]:
            break

        # Show dialog for retry/exit
        dialog = REWConnectionDialog()
        dialog_result = dialog.exec_()

        if dialog_result == 0:  # Exit button clicked
            sys.exit(1)
        # Continue loop to retry


def shutdown_handler(signum, frame):
    print("🔔 Signal received – shutting down …")

    # Clean up VLC player first
    try:
        print("DEBUG: Stopping VLC player...")
        stop_vlc_and_exit()
    except Exception as e:
        print(f"Error stopping VLC player: {e}")

    # Stop Flask server
    try:
        print("DEBUG: Stopping Flask server...")
        stop_flask_server()
    except Exception as e:
        print(f"Error stopping Flask server: {e}")

    # Quit Qt application
    QApplication.quit()  # orderly Qt shutdown


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Start Flask in a background thread with error handling
    try:
        flask_thread = Thread(target=run_flask_server, daemon=True)
        flask_thread.start()
        print("🔄 Flask server thread started...")

        # Give Flask server more time to start under PyInstaller
        time.sleep(2)

        # Check Flask server in a non-blocking way
        def check_flask_async():
            """Check Flask server asynchronously"""

            def check():
                try:
                    response = requests.get("http://127.0.0.1:5555/health", timeout=2)
                    if response.status_code == 200:
                        print("✅ Flask server verified running")
                    else:
                        print(f"⚠️  Flask server code {response.status_code}")
                except Exception as e:
                    print(f"⚠️  Flask server verification failed: {e}")
                    print("   Continuing anyway, REW subscriptions may not work")

            Thread(target=check, daemon=True).start()

    except Exception as e:
        print(f"❌ Failed to start Flask server: {e}")
        print("   Application will continue but REW integration may not work")

    check_flask_async()
    # Create Qt application
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(GLOBAL_STYLE)
    use_light = qs.get("use_light_theme", False)
    palette = get_light_palette() if use_light else get_dark_palette()

    app.instance().setPalette(palette)
    # Check for deferred VLC error messages that couldn't be shown during import
    try:
        # Check for stored error messages
        vlc_error = qs.get("vlc_error_message", None)
        if vlc_error and isinstance(vlc_error, dict):
            QrewMessageBox.critical(
                None,
                vlc_error.get("title", "VLC Error"),
                vlc_error.get("text", "An error occurred with VLC."),
            )
            # Clear the error after showing it
            qs.set("vlc_error_message", None)
    except Exception as e:
        print(f"Failed to display deferred VLC error message: {e}")

    # Check REW connection
    wait_for_rew_qt()

    # Initialize all subscriptions in background thread
    def init_subscriptions():
        try:
            initialize_rew_subscriptions()
            print("✅ REW subscriptions initialized")
        except Exception as e:
            print(f"⚠️  Failed to initialize REW subscriptions: {e}")
            print("   You may need to restart the application")

    init_thread = Thread(target=init_subscriptions)
    init_thread.daemon = True
    init_thread.start()

    # Create and show main window
    window = MainWindow()
    window.show()

    try:
        exit_code = app.exec_()
    finally:
        # Ensure Flask server is stopped on exit
        print("🛑 Shutting down Flask server...")
        stop_flask_server()

    sys.exit(exit_code)
