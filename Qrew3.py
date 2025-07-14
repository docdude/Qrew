# Qrew.py

from cProfile import label
import os
import re
import sys
import time

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, 
                            QCheckBox, QGridLayout,
                            QVBoxLayout, QHBoxLayout, QMessageBox, QFileDialog,
                            QDialog, QSizePolicy, QComboBox, QScrollArea, QGroupBox, QFrame, QToolButton, QToolTip)


from PyQt5.QtCore import Qt, QTimer, QSettings, QSize, QEvent
from PyQt5.QtGui import QPixmap, QPalette, QBrush, QColor, QFont, QIcon, QPainter
import platform
from threading import Thread
from Qrew_common import SPEAKER_LABELS
import Qrew_common
import Qrew_settings as qs

from Qrew_api_helper import (get_measurement_count, get_measurement_by_uuid, get_all_measurements_with_uuid, get_selected_channels_with_measurements_uuid, get_measurement_distortion_by_uuid,
                             save_all_measurements, delete_all_measurements, delete_measurement_by_uuid, delete_measurements_by_uuid,
                             check_rew_connection, initialize_rew_subscriptions)

from Qrew_measurement_metrics import evaluate_measurement
from Qrew_message_handlers import rta_coordinator

from Qrew_workers import MeasurementWorker, ProcessingWorker
from Qrew_styles import tint, HTML_ICONS
from Qrew_button import Button
from Qrew_gridwidget import GridWidget
from Qrew_messagebox import QrewMessageBox, QrewFileDialog
from Qrew_filedialog import get_open_file
from Qrew_message_handlers import run_flask_server, message_bridge

from Qrew_dialogs import (SettingsDialog, PositionDialog, MeasurementQualityDialog, ClearMeasurementsDialog, SaveMeasurementsDialog,
                           RepeatMeasurementDialog, DeleteSelectedMeasurementsDialog, REWConnectionDialog, get_speaker_configs, MicPositionVisualizationDialog)

from Qrew_micwidget_icons import MicPositionWidget

# Force Windows to use IPv4 for all requests
if platform.system() == "Windows":
    import socket
    import requests.packages.urllib3.util.connection as urllib3_cn

    def allowed_gai_family():
        return socket.AF_INET  # Force IPv4 only
    
    urllib3_cn.allowed_gai_family = allowed_gai_family


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.qsettings = QSettings("Docdude", "Qrew")
        self.setWindowTitle("Qrew")
        self.resize(640, 880)
        self.setMinimumSize(600, 860)
        self.bg_source = QPixmap("banner_500x680.png")   # original file
        self.bg_opacity = 0.35                           # user-chosen α
        self.set_background_image()                                 # first fill
        #self.app_settings = qs._load()
        print(f"DEBUG: Loaded settings: {qs._load()}")
        print(f"DEBUG: Settings file exists: {os.path.exists('settings.json')}")
        # Message tracking
        self.current_warnings = []
        self.current_errors = []
        self.last_status_message = ""
        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(400)
        self.flash_timer.timeout.connect(self._toggle_flash)
        self._flash_state = False
        # Add visualization dialog instance
        self.visualization_dialog = None
        self.compact_mic_widget = None
        self.selected_channels_for_viz = set()  # Track selected channels for visualization

        # Track the last valid position count
        self.last_valid_positions = 9  # Default
        self.measurement_qualities = {}  # {(channel, position): {'rating': 'PASS/CAUTION/RETAKE', 'score': float, 'uuid': str}}

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Set background image
       # self.set_background_image_opaque("banner_500x680.png", opacity=0.3)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)


        # Initialize measurement state
        self.measurement_state = {
            'channels': [],
            'num_positions': 0,
            'current_position': 0,
            'initial_count': -1,
            'running': False,
            'channel_index': 0
        }
 
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
        base_pix = QPixmap("gear@2x.png")            # transparent PNG
        hover_pix = tint(base_pix, QColor("#00A2FF"))  # cyan tint

        icon = QIcon()
        icon.addPixmap(base_pix,  QIcon.Normal,  QIcon.Off)
        icon.addPixmap(hover_pix, QIcon.Active,  QIcon.Off)
        icon.addPixmap(hover_pix, QIcon.Selected,QIcon.Off)
        self.settings_btn.setIcon(icon)

        # optional minimal CSS (no backdrop tint now)
        self.settings_btn.setStyleSheet("""
            QToolButton { border:none; background:transparent; padding:0; }
        """)
        self.settings_btn.clicked.connect(self.open_settings_dialog)

        channel_header_layout.addWidget(self.settings_btn, 0, Qt.AlignLeft)
                
        # Channel selection section
        self.channel_label = QLabel("Select Speaker Channels (Manual Select):")
        self.channel_label.setStyleSheet("QLabel { color: white; background: transparent; padding: 0px 0px 0px 20px; text-align: left; }")
        channel_header_layout.addWidget(self.channel_label)
        channel_header_layout.addStretch()

        # Clear button
        self.clear_button = Button("Clear")
        self.clear_button.clicked.connect(self.clear_selections)
        self.clear_button.setStyleSheet("""
            QPushButton { 
                background: rgba(51, 51, 51, 0.5); 
                color: white; 
                border: 1px solid #666;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
            }
        """)

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
        row1_speakers = ['FHL', 'FL', 'FDL', 'C', 'FDR', 'FR', 'FHR']
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
                
                checkbox.setStyleSheet("""
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
                """)
                
                row1_layout.addWidget(checkbox)
                self.channel_checkboxes[abbr] = checkbox

        row1_layout.addStretch(1)
        row1_widget = QWidget()
        row1_widget.setLayout(row1_layout)
        row1_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        main_checkbox_layout.addWidget(row1_widget)
        main_checkbox_layout.addSpacing(-5)
        # Rows 2-5: Grid layout with smart centering
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setHorizontalSpacing(18)
        grid_layout.setVerticalSpacing(8)

        # Define grid rows with calculated positioning for centering
        grid_speaker_data = [
            {'speakers': ['TFL', 'TML', 'TRL', 'TFR', 'TMR', 'TRR'], 'start_col': 1},     # 6 items, start at col 1
            {'speakers': ['FWL', 'SDL', 'SLA', 'FWR', 'SDR', 'SRA'], 'start_col': 1},     # 6 items, start at col 1
            {'speakers': ['RHL', 'SHL', 'SBL', 'BDL', 'RHR', 'SHR', 'SBR', 'BDR'], 'start_col': 0},  # 8 items, start at col 0
            {'speakers': ['SW1', 'SW2', 'SW3', 'SW4'], 'start_col': 2}                    # 4 items, start at col 2
        ]

        # Set up 8 columns
        max_grid_columns = 8
        for col in range(max_grid_columns):
            grid_layout.setColumnStretch(col, 1)

        # Add checkboxes to grid with smart positioning
        for row_idx, row_data in enumerate(grid_speaker_data):
            speakers = row_data['speakers']
            start_col = row_data['start_col']
            
            for col_offset, abbr in enumerate(speakers):
                if abbr in SPEAKER_LABELS:
                    full_name = SPEAKER_LABELS[abbr]
                    checkbox = QCheckBox(abbr)
                    checkbox.setToolTip(full_name)
                    checkbox.setMinimumWidth(75)
                    checkbox.setMaximumWidth(85)
                    
                    checkbox.setStyleSheet("""
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
                    """)
                    
                    actual_col = start_col + col_offset
                    grid_layout.addWidget(checkbox, row_idx, actual_col, Qt.AlignCenter)
                    self.channel_checkboxes[abbr] = checkbox

        main_checkbox_layout.addWidget(grid_widget)

        checkbox_widget.setMinimumSize(450, 150)
        checkbox_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        main_layout.addWidget(checkbox_widget, alignment=Qt.AlignTop)
        main_layout.addSpacing(-25)

                
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
        self.pos_selector.addItems(["1", "3", "4", "5", "6", "7", "8", "9"])
        self.pos_selector.setCurrentText("9")
        self.pos_selector.setMaximumWidth(70)

        self.pos_selector.setStyleSheet("""
        /* ========== CLOSED COMBO ========== */
        QComboBox {
            border: 2px solid gray;
            border-radius: 4px;
            padding: 1px 22px 1px 6px;     /* leave space for arrow */
            background: rgba(0, 0, 0, 0.80);   /* 50 % opacity black */
            color: white;                       /* visible text      */
            font-size: 14px;
            font: 'arial'; /* font family       */
        }


        """)


        pos_layout.addWidget(self.pos_selector)

        # ───────────────── Metrics Display ───────────────── #
        metrics_container = QWidget()
        metrics_container.setStyleSheet("background: transparent;")
        metrics_layout = QHBoxLayout(metrics_container)
        metrics_layout.setContentsMargins(50, 100, 50, 0)
        
        # Metrics label
        self.metrics_label = QLabel("")
        self.metrics_label.setStyleSheet("""
            QLabel { 
                background: rgba(0, 0, 0, 0.8); 
                color: white; 
                padding: 5px 10px; 
                border: 1px solid #444;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        self.metrics_label.setTextFormat(Qt.RichText)
        self.metrics_label.setAlignment(Qt.AlignCenter)
        self.metrics_label.setMinimumSize(120,30)
       # self.metrics_label.hide()  # Initially hidden
        
        metrics_layout.addWidget(self.metrics_label)
      #  main_layout.addWidget(metrics_container, alignment=Qt.AlignCenter)
       # main_layout.addSpacing(5)

        mode = qs.get("viz_view",  "Grid View")
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
        n = int(self.pos_selector.currentText())
        self.grid_widget = GridWidget(positions=n, current_pos=self.measurement_state['current_position'])
    #   self.grid_widget.setMinimumSize(0,0)

        self.grid_widget.setSizePolicy(QSizePolicy.Expanding,
                                    QSizePolicy.Expanding)
    # self.grid_widget.setMaximumHeight(160)       # but no fixed width

        self.grid_widget.set_horizontal_stretch(1.3)
        grid_container_layout.addWidget(self.grid_widget)
#############
      #  pos_layout.addWidget(grid_container)
        # after you add the widgets to pos_layout  (label – combo – grid_container)
       # pos_layout.setStretchFactor(grid_container, 1)     # label column

    # pos_layout.addSpacing(0)
        # ---- positions + metrics (left)  /  grid (right) --------------
        row_widget   = QWidget()
        row_layout   = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(10, 0, 0, 0)
        row_layout.setSpacing(20)

        # left column  (positions + metrics)
        left_col     = QWidget()
        left_layout  = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(pos_container)
        left_layout.addWidget(metrics_container)
        left_layout.addStretch()

        row_layout.addWidget(left_col,          0)   # minimal width
        row_layout.addWidget(grid_container,    1)   # grid takes all spare space

        main_layout.addWidget(row_widget)            # ← replaces previous adds

       # main_layout.addWidget(pos_container)
        main_layout.addSpacing(-50)

        # React to user choice
        self.pos_selector.currentTextChanged.connect(self._rebuild_grid)
        self.switch_visualization_mode(mode)



        # Command button container
        meas_container = QWidget()
        meas_container.setStyleSheet("background: transparent;")
        meas_layout = QHBoxLayout(meas_container)
        meas_layout.setContentsMargins(10, -10, 10, 10)
        meas_layout.setSpacing(10)

        # Load stimulus button
        self.load_button = Button("Load Stimulus File")
        self.load_button.clicked.connect(self.load_stimulus_file)
        self.load_button.setStyleSheet("""
            QPushButton { 
                background: rgba(51, 51, 51, 0.5); 
                color: white; 
                border: 1px solid #666;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
        """)
        self.load_button.setMaximumHeight(120)
        meas_layout.addWidget(self.load_button)

        # Start button
        self.start_button = Button("Start Measurement")
        self.start_button.clicked.connect(self.on_start)
        self.start_button.setStyleSheet("""
            QPushButton { 
                background: rgba(51, 51, 51, 0.5); 
                color: white; 
                border: 1px solid #666;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
        """)
        meas_layout.addWidget(self.start_button)

        # Repeat button
        self.repeat_button = Button("Repeat Measurement")
        self.repeat_button.setDisabled(True)
        self.repeat_button.clicked.connect(self.show_repeat_measurement_dialog)
        self.repeat_button.setStyleSheet("""
            QPushButton { 
                background: rgba(51, 51, 51, 0.5); 
                color: white; 
                border: 1px solid #666;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
        """)
        meas_layout.addWidget(self.repeat_button)

        main_layout.addWidget(meas_container, alignment=Qt.AlignCenter)
        main_layout.addSpacing(-15)

        # Process button container
        cmd_container = QWidget()
        cmd_container.setStyleSheet("background: transparent;")
        cmd_layout = QHBoxLayout(cmd_container)
        cmd_layout.setContentsMargins(10, -10, 10, 10)
        cmd_layout.setSpacing(20)

        # Cross button
        self.cross_button = Button("Cross Corr Align")
        self.cross_button.clicked.connect(self.on_cross_corr_align)
        self.cross_button.setStyleSheet("""
            QPushButton { 
                background: rgba(51, 51, 51, 0.5); 
                color: white; 
                border: 1px solid #666;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
        """)
        cmd_layout.addWidget(self.cross_button)

        # Vector button
        self.vector_button = Button("Vector Average")
        self.vector_button.clicked.connect(self.on_vector_average)
        self.vector_button.setStyleSheet("""
            QPushButton { 
                background: rgba(51, 51, 51, 0.5); 
                color: white; 
                border: 1px solid #666;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
        """)
        cmd_layout.addWidget(self.vector_button)

        # Full processing button
        self.full_button = Button("Cross+Vector")
        self.full_button.clicked.connect(self.on_full_processing)
        self.full_button.setStyleSheet("""
            QPushButton { 
                background: rgba(51, 51, 51, 0.5); 
                color: white; 
                border: 1px solid #666;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
        """)
        cmd_layout.addWidget(self.full_button)

        main_layout.addWidget(cmd_container, alignment=Qt.AlignCenter)
        main_layout.addSpacing(0)

        status_group = QGroupBox("Measurement Status")
        status_group.setStyleSheet('''
            QGroupBox {
                background: rgba(0, 0, 0, 0.8); 
                color: #fff; 
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #999;
                border-radius: 5px;
                margin-top: 5px;
                padding-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        ''')
       # status_group.setMinimumHeight(80)
        #status_group.setMaximumHeight(80)
        status_group.setMinimumSize(450, 80)
      #  status_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Status layout
        status_layout = QVBoxLayout()
        # Status label
        self.status_label = QLabel("Please load stimulus file to begin...")
        self.status_label.setStyleSheet("""
            QLabel { 
               
                color: #fff; 

                font-weight: normal;
            }
        """)
        self.status_label.setWordWrap(True)
      #*  self.status_label.setMinimumHeight(80)
       # self.status_label.setMaximumHeight(80)
       # self.status_label.setFixedWidth(450)
        status_layout.addWidget(self.status_label)
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group, alignment=Qt.AlignTop)
#        main_layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        # Warning/Error panel
        error_group = QGroupBox("Warnings & Errors")
        error_group.setStyleSheet('''
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
                padding: 0 5px;
            }
        ''')
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
        self.clear_errors_button.setStyleSheet("""
            QPushButton {
                background: rgba(51, 51, 51, 0.5);
                color: white;
                border: 1px solid #666;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
            }
        """)

        self.clear_errors_button.setToolTip("Clear all warnings and errors")
        header_hbox.addWidget(self.clear_errors_button)

        err_vbox.addLayout(header_hbox)          # <- first row in the group
        err_vbox.addSpacing(0)

        # scroll-area for accumulating messages -----------------------------
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
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
 
        """)
        scroll.viewport().setAutoFillBackground(False)
        self.error_label = QLabel("No warnings or errors")
        self.error_label.setStyleSheet("""
            QLabel {
                background: transparent;
                color: white;
                font-size: 11px;
            }
        """)
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # Set the label to be larger than the scroll area
        self.error_label.setMinimumHeight(70)  # Ensure it can scroll
        self.error_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)    
        # put the label inside the scroll-area
        scroll.setWidget(self.error_label)
        scroll.setFixedHeight(70)          # visible window height
        err_vbox.addWidget(scroll)


        # add the new group to your main layout
        main_layout.addWidget(error_group, alignment=Qt.AlignTop)
        main_layout.addSpacing(0)

        self._refresh_repeat_button()

        # load persisted settings and apply once
       # self.app_settings = SettingsDialog.load()
        #self.apply_settings()


        self.connect_visualization_signals()
        # Initialize widget visibility after a short delay to ensure proper layout
        QTimer.singleShot(200, self.ensure_widget_visibility)
        # Worker thread
        self.measurement_worker = None
        self.processing_worker = None
        message_bridge.message_received.connect(self.update_status)
        message_bridge.warning_received.connect(self.add_warning)
        message_bridge.error_received.connect(self.add_error)
        QTimer.singleShot(1000, self.load_existing_measurement_qualities)  # Delay to ensure REW is connected


    def eventFilter(self, source, event):
        # A single left-click anywhere inside the grid-container
        # pops the Full-Theatre window to the front, but does **not**
        # change the current visualisation mode or persist anything.
        if source is self.grid_container and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self.show_visualization_dialog()   # just open / raise it
                return True                        # stop further handling
        return super().eventFilter(source, event)


    def _toggle_flash(self):
        """Centralized flash toggle to avoid state issues"""
        self._flash_state = not self._flash_state
        if hasattr(self, 'grid_widget'):
            self.grid_widget.set_flash(self._flash_state)
      #  self.mic_widget.flash = self._flash_state
       # self.mic_widget.update()

    def _refresh_repeat_button(self):
        """Enable the Repeat button only if a valid stimulus WAV is set."""
        path = getattr(Qrew_common, "selected_stimulus_path", "")
        self.repeat_button.setEnabled(bool(path) and os.path.exists(path))

    def _set_channel_header(self, cfg_name: str):
        """Update the header to show current speaker configuration."""
        if not cfg_name or cfg_name.startswith("Manual"):
            suffix = f" (Manual Select)"
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
        Re-create the GridWidget with the new number of positions.
        Works no matter which visualisation mode is currently active.
        """
        try:
            n = int(text)
        except ValueError:
            return

        was_flashing = self.flash_timer.isActive() if hasattr(self, "flash_timer") else False

        # ── remove & delete old grid widget ───────────────────────
        if getattr(self, "grid_widget", None):
            # take it out of the layout it *may* still be in
            if self.grid_widget.parent() is not None:
                try:
                    self.grid_container_layout.removeWidget(self.grid_widget)
                except Exception:
                    pass
            self.grid_widget.deleteLater()
            self.grid_widget = None

        # ── create the new widget ─────────────────────────────────
        self.grid_widget = GridWidget(
            positions=n,
            current_pos=self.measurement_state.get("current_position", 0)
        )
        self.grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.grid_widget.set_horizontal_stretch(1.3)

        # ── add it only if the current mode shows the grid ────────
        if self.get_current_viz_mode() in ("Grid View", "Full Theater View"):
            self.grid_container_layout.addWidget(self.grid_widget)

        # ── restore flashing if it was active ─────────────────────
        if was_flashing:
            self.grid_widget.set_flash(True)
            if not self.flash_timer.isActive():
                self.flash_timer.start(400)

    def update_grid_flash(self, on: bool):
        """Start or stop the single flashing timer."""
        if on:
            if not self.flash_timer.isActive():
                self.flash_timer.start()
        else:
            if self.flash_timer.isActive():
                self.flash_timer.stop()
                self.grid_widget.set_flash(False)

    def toggle_flash(self):
        """Toggle flash state"""
        current_flash = self.grid_widget.flash_on
        self.grid_widget.set_flash(not current_flash)

    def update_grid_position(self, position):
        """Update grid current position"""
        self.grid_widget.set_current_pos(position)

    def update_metrics_display(self, metrics: dict):
        try:
            score   = metrics.get("score", 0)
            rating  = metrics.get("rating", "Unknown")
            channel = metrics.get("channel")          # ← from result
            position= metrics.get("position")
            uuid    = metrics.get("uuid")

            # Track quality
            if channel is not None and position is not None and uuid:
                self.measurement_qualities[(channel, position)] = {
                    "rating": rating,
                    "score" : score,
                    "uuid"  : uuid,
                    "detail": metrics.get("detail"),
                    "title" : f"{channel}_pos{position}",
                }
                print(f"Tracked quality for {channel}_pos{position}: {rating} ({score:.1f}) UUID: {uuid}")


            # Choose colour …
            colour = {
                "PASS":   "#00ff00",
                "CAUTION":"#ffff00",
                "RETAKE":"#ff0000",
            }.get(rating, "#ffffff")

            html = (f"<span style='color:{colour}; font-size:16px;font-weight:bold;'>"
                    f"{rating}</span> "
                    f"<span style='color:#ccc;font-size:12px;'>({score:.1f})</span>")

            self.metrics_label.setText(html)
            self.metrics_label.show()

        except Exception as e:
            print("Error updating metrics display:", e)

    def update_quality_entry(self, result: dict):
        """
        Update self.measurement_qualities for (channel, position)
        with the score/rating of the *new* measurement.
        """
       # channel   = result['channel']     # or however you encode it
        #position  = result['position']
      #  key       = (channel, position)
        key = (result['channel'], result['position'])
        # overwrite / create
        self.measurement_qualities[key] = {
            "rating": result['rating'],
            "score" : result['score'],
            "detail": result['detail'],
            "uuid"  : result['uuid'],
        }

    def update_status(self, msg):
        """Update regular status messages (white text)"""
        self.last_status_message = msg
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("""
            QLabel { 
                color: white; 

                font-weight: normal;
            }
        """)

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
            self.error_label.setStyleSheet("""
                QLabel { 
                    background: transparent;
                    color: #fff; 

                    font-size: 11px;
                }
            """)
            return
        
        # Build display text with HTML for colors
        display_parts = []
        
        # Add errors (red)
        for error in self.current_errors:
            display_parts.append(f'<span style="color: #ff6b6b;">{HTML_ICONS["cross"]} {error}</span>')
        
        # Add warnings (yellow)
        for warning in self.current_warnings:
            display_parts.append(f'<span style="color: #ffd93d;">{HTML_ICONS["warning"]} {warning}</span>')
        
        display_text = f'<br>'.join(display_parts)
        self.error_label.setTextFormat(Qt.RichText)
        self.error_label.setText(display_text)
        self.error_label.setStyleSheet("""
            QLabel { 
                background: transparent;
                color: white; 
                font-size: 11px;
            }
        """)

    def clear_warnings_errors(self):
        """Clear all warnings and errors"""
        self.current_warnings.clear()
        self.current_errors.clear()  
        self.update_error_display()

    def set_background_image(self):
        if self.bg_source.isNull():
            return                                      # file missing?

        # -- scale to the *current* window size --------
        scaled = self.bg_source.scaled(
            self.size(),                       # full client area
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )

        # -- stamp the scaled image onto a transparent canvas
        canvas = QPixmap(scaled.size())
        canvas.fill(Qt.transparent)

        p = QPainter(canvas)
        p.setOpacity(self.bg_opacity)         # 0.0 … 1.0
        p.drawPixmap(0, 0, scaled)
        p.end()

        # -- install the brush --------------------------
        pal = self.palette()
        pal.setBrush(QPalette.Window, QBrush(canvas))
        self.setPalette(pal)
        self.setAutoFillBackground(True)       # important


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
            self.width(), self.height(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )

        # 2) paint it onto a transparent canvas with the desired alpha
        result = QPixmap(pix.size())
        result.fill(Qt.transparent)              # RGBA buffer
        painter = QPainter(result)
        painter.setOpacity(opacity)              # 0-1 float
        painter.drawPixmap(0, 0, pix)
        painter.end()

        # 3) install as window background
        pal = self.palette()
        pal.setBrush(QPalette.Window, QBrush(result))
        self.setPalette(pal)
        self.setAutoFillBackground(True)         # palette actually used

    def clear_selections(self):
        for checkbox in self.channel_checkboxes.values():
            checkbox.setChecked(False)
        self.channel_label.setText(f"Select Speaker Channels (Manual Select):")
        #self.app_settings['speaker_config'] = 'Manual Select'
        #SettingsDialog.save(self.app_settings)
        qs.set('speaker_config', 'Manual Select')

    def load_stimulus_file(self):
        # Get last directory from settings, default to empty string
        last_dir = self.qsettings.value("last_stimulus_directory", "")
        file_path = QrewFileDialog.getOpenFileName(
        #file_path = get_open_file(
            self,
            "Select Stimulus WAV File",
            last_dir,
            "WAV Files (*.wav);;All Files (*.*)"
        )
        if not file_path:
            # User pressed Cancel – keep the previous state but refresh button
            self._refresh_repeat_button()
            return
        

        # Normalize paths for the current OS
        Qrew_common.selected_stimulus_path = os.path.normpath(file_path)
        Qrew_common.stimulus_dir = os.path.normpath(os.path.dirname(file_path))
        self.qsettings.setValue("last_stimulus_directory", Qrew_common.stimulus_dir)
        self.status_label.setText(f"Selected stimulus: {os.path.basename(file_path)}")
        self._refresh_repeat_button()  

    def show_error_message(self, title, message):
        """Thread-safe method to show error messages"""
        QrewMessageBox.critical(self, title, message)
    
    def on_start(self):
        if not Qrew_common.selected_stimulus_path:
            QrewMessageBox.critical(self, "No Stimulus File", "Please load a stimulus WAV file first.")
            return
        
        try:
            num_pos = int(self.pos_selector.currentText())
            if num_pos <= 0:
                raise ValueError
        except ValueError:
                QrewMessageBox.critical(self, "Invalid Input",
                             "Select 1 – 9 microphone positions.")            
                return
        
        self.last_valid_positions = num_pos

                
        selected = [abbr for abbr, checkbox in self.channel_checkboxes.items() if checkbox.isChecked()]
        if not selected:
            QrewMessageBox.critical(self, "No Channels", "Please select at least one speaker channel.")
            return

        # Check for existing measurements and show confirmation dialog
        measurement_count = get_measurement_count()
        dialog = ClearMeasurementsDialog(measurement_count, self)
        
        if dialog.exec_() != QDialog.Accepted:
            return  # User cancelled
        
        # Handle user's choice
        if dialog.result == 'delete':
            self.status_label.setText('Clearing existing measurements...')
            success, count_deleted, error_msg = delete_all_measurements(status_callback=self.update_status)
            if not success:
                QrewMessageBox.critical(self, 'Delete Failed', f'Failed to delete measurements:\n{error_msg}')
                return
            if count_deleted > 0:
                QrewMessageBox.information(self, 'Measurements Cleared', f'Successfully deleted {count_deleted} existing measurements.')
                
        # Reset measurement state
        self.measurement_state.update({
            'channels': selected,
            'num_positions': num_pos,
            'current_position': 0,
            'initial_count': -1,
            'running': True,
            'channel_index': 0,
            'repeat_mode'     : False,          # clean slate

        })
        
        # Hide metrics when starting new measurement
     #   self.metrics_label.hide()
        self.retake_pairs = []                 # clear any stale repeat list

        
        self.start_button.setEnabled(False)
        self.status_label.setText("Starting measurement process...")
        print("DEBUG channels :", self.measurement_state['channels'])
        print("DEBUG positions:", self.last_valid_positions)

        # Show initial position dialog
        self.show_position_dialog(0)
    
    def show_position_dialog(self, position):
        """Show position dialog and handle user response"""
        dialog = PositionDialog(position, self)
        
        if dialog.exec_():
            # User clicked OK - continue measurement
            # For repeat mode, don't reset channel_index
            if not self.measurement_state.get('repeat_mode', False):
                if position == 0:
                    # First position in normal mode - reset channel index
                    self.measurement_state['channel_index'] = 0
            
            # Update the current position in state
            self.measurement_state['current_position'] = position
            
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
            self.measurement_state['running'] = False
            self.start_button.setEnabled(True)
            # Stop flash
            if self.flash_timer:
                self.flash_timer.stop()
            self.grid_widget.set_flash(False)
            # Stop worker if running
            if self.measurement_worker and self.measurement_worker.isRunning():
                self.measurement_worker.stop()
    
    def start_worker(self):
        self.measurement_worker = MeasurementWorker(self.measurement_state, self)
        self.measurement_worker.status_update.connect(self.update_status)
        self.measurement_worker.error_occurred.connect(self.show_error_message)
        self.measurement_worker.finished.connect(self.on_measurement_finished)
        self.measurement_worker.show_position_dialog.connect(self.show_position_dialog)
        self.measurement_worker.grid_flash_signal.connect(self.update_grid_flash)
        self.measurement_worker.grid_position_signal.connect(self.update_grid_position)
        self.measurement_worker.metrics_update.connect(self.update_metrics_display)
        self.measurement_worker.metrics_update.connect(self.update_quality_entry, Qt.DirectConnection)
        self.measurement_worker.show_quality_dialog.connect(self.show_measurement_quality_dialog)  
        # Add visualization update connection
        self.measurement_worker.visualization_update.connect(self.update_visualization_from_worker)

        self.measurement_worker.start()


    def on_measurement_finished(self):
        self.start_button.setEnabled(True)
        save_after_repeat = qs.get("save_after_repeat", False)

        repeat = self.measurement_state.pop("repeat_mode", False)
        repeat_channels = self.measurement_state.pop("repeat_channels", [])
        repeat_positions = self.measurement_state.pop("repeat_positions", [])

        self.build_retake_caution_list()          # refresh list first

        if repeat:
            if not self.retake_pairs:             # everything passed!
                self.status_label.setText("All repeat measurements passed.")
            else:
                self.status_label.setText(
                    "Repeat measurements completed – some still need re-take."
                )
            if save_after_repeat:
                self.show_save_measurements_dialog()
            # Keep ONLY the user-selected repeat channels and positions visible after completion
            self.selected_channels_for_viz = set(repeat_channels)
            self.selected_positions_for_viz = set(repeat_positions)
            
            # Keep ONLY repeat channel checkboxes checked
            for abbr, checkbox in self.channel_checkboxes.items():
                checkbox.setChecked(abbr in repeat_channels)
                
        else:
             # For normal measurements, reset to default visibility
            self.selected_channels_for_viz = set()
            if hasattr(self, 'selected_positions_for_viz'):
                delattr(self, 'selected_positions_for_viz')  # Remove position restriction
            for abbr, checkbox in self.channel_checkboxes.items():
                checkbox.setChecked(False)
            self.status_label.setText("Measurement process completed.")
            self.show_save_measurements_dialog()

        if self.flash_timer:
            self.flash_timer.stop()
        self.grid_widget.set_flash(False)

        # Clear animations and update visualization with final selections
        if hasattr(self, 'compact_mic_widget') and self.compact_mic_widget:
            self.compact_mic_widget.set_active_speakers([])  # Clear active speakers
            self.compact_mic_widget.set_flash_state(False)   # Stop flash
            self.compact_mic_widget.set_selected_channels(list(self.selected_channels_for_viz))
            self.compact_mic_widget.set_active_mic(None)   # ← clear dot ■
            self.compact_mic_widget.update()               # ② repaint now

            # Update position visibility
            if hasattr(self, 'selected_positions_for_viz'):
                self.compact_mic_widget.set_visible_positions_list(list(self.selected_positions_for_viz))
            else:
                # Reset to show all positions from selector
                current_positions = int(self.pos_selector.currentText())
                self.compact_mic_widget.set_visible_positions(current_positions)
                
            self.compact_mic_widget.update()
            
        if hasattr(self, 'visualization_dialog') and self.visualization_dialog:
            # Update position visibility for dialog too
            if hasattr(self, 'selected_positions_for_viz'):
                self.visualization_dialog.mic_widget.set_visible_positions_list(list(self.selected_positions_for_viz))
            else:
                current_positions = int(self.pos_selector.currentText())
                self.visualization_dialog.mic_widget.set_visible_positions(current_positions)
                
            self.visualization_dialog.update_visualization(
                None,
                [],  # No active speakers
                list(self.selected_channels_for_viz),  # Only user-selected repeat channels
                False  # No flash
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
        
        try:
            success, error_msg = save_all_measurements(
                file_path, 
                status_callback=self.update_status
            )
            
            if success:
                self.update_status(f"Raw measurements saved successfully to: {os.path.basename(file_path)}")
                QrewMessageBox.information(
                    self, 
                    "Save Successful", 
                    f"Raw measurements saved to:\n{file_path}"
                )
            else:
                self.update_status(f"Failed to save measurements: {error_msg}")
                QrewMessageBox.critical(
                    self, 
                    "Save Failed", 
                    f"Failed to save measurements:\n{error_msg}"
                )
                
        except Exception as e:
            error_msg = f"Unexpected error saving measurements: {str(e)}"
            self.update_status(error_msg)
            QrewMessageBox.critical(self, "Save Error", error_msg)
        
        finally:
            # Re-enable buttons
            self.start_button.setEnabled(True)
            self.cross_button.setEnabled(True)
            self.vector_button.setEnabled(True)
            self.full_button.setEnabled(True)

    def on_cross_corr_align(self):
        """Handle cross correlation alignment button click"""
        selected = [abbr for abbr, checkbox in self.channel_checkboxes.items() if checkbox.isChecked()]
        if not selected:
            QrewMessageBox.critical(self, "No Channels", "Please select at least one speaker channel.")
            return
        
        self.start_processing(selected, 'cross_corr_only')

    def on_vector_average(self):
        """Handle vector average button click"""
        selected = [abbr for abbr, checkbox in self.channel_checkboxes.items() if checkbox.isChecked()]
        if not selected:
            QrewMessageBox.critical(self, "No Channels", "Please select at least one speaker channel.")
            return
        
        self.start_processing(selected, 'vector_avg_only')

    def on_full_processing(self):
        """Handle full processing (cross corr + vector avg) button click"""
        selected = [abbr for abbr, checkbox in self.channel_checkboxes.items() if checkbox.isChecked()]
        if not selected:
            QrewMessageBox.critical(self, "No Channels", "Please select at least one speaker channel.")
            return
        
        self.start_processing(selected, 'full')

    def start_processing(self, selected_channels, mode):
        """Start processing workflow"""
        # Get measurements for selected channels
        channels_with_data = get_selected_channels_with_measurements_uuid(selected_channels)
        
        if not channels_with_data:
            QrewMessageBox.critical(self, "No Measurements", 
                            "No measurements found for the selected channels. Please run measurements first.")
            return
        # Convert to the format expected by processing worker (just UUIDs)
        channels_with_uuids = {}
        for channel, measurements in channels_with_data.items():
            channels_with_uuids[channel] = [m['uuid'] for m in measurements]
    
        # Determine starting step based on mode
        if mode == 'cross_corr_only':
            start_step = 'cross_corr'
        elif mode == 'vector_avg_only':
            start_step = 'vector_avg'
        else:  # 'full'
            start_step = 'cross_corr'
        
        # Initialize processing state
        self.processing_state = {
            'channels': list(channels_with_data.keys()),
            'channel_measurements': channels_with_data,
            'current_step': start_step,
            'channel_index': 0,
            'running': True,
            'mode': mode
        }
        
        # Disable buttons during processing
        self.cross_button.setEnabled(False)
        self.vector_button.setEnabled(False)
        self.full_button.setEnabled(False)
        self.start_button.setEnabled(False)
        
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
        self.status_label.setText("Processing completed.")
        if hasattr(self, 'processing_worker'):
            self.processing_worker = None

    def closeEvent(self, event):
        """Handle window close event"""
        if self.flash_timer:
            self.flash_timer.stop()
        if self.measurement_worker and self.measurement_worker.isRunning():
            self.measurement_worker.stop()
        if hasattr(self, 'processing_worker') and self.processing_worker and self.processing_worker.isRunning():
            self.processing_worker.stop()
        event.accept()

    def show_repeat_measurement_dialog(self):
        """Show the repeat measurement dialog."""
        print("DEBUG channels :", self.measurement_state['channels'])
        print("DEBUG positions:", self.last_valid_positions)

        if not self.measurement_qualities:
            QrewMessageBox.information(self, 'No Measurements', 'No completed measurements available for repeat.')
            return
        
        dialog = RepeatMeasurementDialog(
            self.measurement_qualities, 
            #self.measurement_state.get('num_positions', 9), 
            self.last_valid_positions,
            self
        )
        
        if dialog.exec_() == QDialog.Accepted and dialog.result == 'proceed':
            selected_measurements = dialog.selected_measurements
            if selected_measurements:
                self.handle_repeat_measurements(selected_measurements)

    def handle_repeat_measurements(self, selected_measurements):
        """Handle the repeat measurement process."""
        if not Qrew_common.selected_stimulus_path:
            if QrewMessageBox.question(
                    self, "Stimulus file required",
                    "You must load the sweep WAV before repeating measurements.\n"
                    "Load it now?",
                    QrewMessageBox.Yes | QrewMessageBox.No, QrewMessageBox.Yes
            ) == QrewMessageBox.Yes:
                self.load_stimulus_file()          # your existing loader
                if not Qrew_common.selected_stimulus_path:
                    return                         # user cancelled
            else:
                return                             # aborted by user

        # Show deletion confirmation
        delete_dialog = DeleteSelectedMeasurementsDialog(selected_measurements, self)
        if delete_dialog.exec_() != QDialog.Accepted:
            return
        
        # Delete selected measurements
        self.status_label.setText('Deleting selected measurements...')
        uuid_list = [m['uuid'] for m in selected_measurements]
        deleted_count, failed_count = delete_measurements_by_uuid(uuid_list, self.update_status)
        
        if failed_count > 0:
            QrewMessageBox.warning(self, 'Deletion Issues', 
                            f'Deleted {deleted_count} measurements, but {failed_count} failed to delete.')
        
        # Remove deleted measurements from quality tracking
        for measurement in selected_measurements:
            key = (measurement['channel'], measurement['position'])
            if key in self.measurement_qualities:
                del self.measurement_qualities[key]
        

        remeasure_pairs = []
        user_selected_repeat_channels = set()
        user_selected_repeat_positions = set()
        for m in selected_measurements:
            remeasure_pairs.append((m['channel'], m['position'], m['uuid']))
            user_selected_repeat_channels.add(m['channel'])
            user_selected_repeat_positions.add(m['position'])

        # Clear ALL previous channel selections first
        for abbr, checkbox in self.channel_checkboxes.items():
            checkbox.setChecked(False)
        
        # Only check the channels the user selected for repeat
        for channel in user_selected_repeat_channels:
            if channel in self.channel_checkboxes:
                self.channel_checkboxes[channel].setChecked(True)
        
        # Update position selector to show max position needed
        max_position = max(user_selected_repeat_positions) if user_selected_repeat_positions else 0
        # Find the minimum number of positions that includes all selected positions
        min_positions_needed = max_position + 1  # +1 because positions are 0-indexed
        
        # Set the position selector to show at least the needed positions
        current_positions = int(self.pos_selector.currentText())
        if min_positions_needed > current_positions:
            self.pos_selector.setCurrentText(str(min_positions_needed))
        
        # Update visualization to show only user-selected repeat channels and positions
        self.selected_channels_for_viz = user_selected_repeat_channels
        self.selected_positions_for_viz = user_selected_repeat_positions  # Track selected positions
        self.update_channel_visualization()
        self.update_position_visualization_for_repeat()


        # Update measurement state for remeasurement
        self.measurement_state.update({
            'channels': [],
            'num_positions': 0,
            'current_position': 0,
            'initial_count': -1,
            'running': True,
            'channel_index': 0,
            'repeat_mode': True,
            'remeasure_pairs': remeasure_pairs,
            'repeat_channels': list(user_selected_repeat_channels),  # Only user-selected channels
            'repeat_positions': list(user_selected_repeat_positions),  # Store selected positions
            'current_remeasure_pair': None,
            'pair_completed': False,
            're_idx': 0
        })
        
        self.start_button.setEnabled(False)
        # Create summary message
        channel_list = ', '.join(sorted(user_selected_repeat_channels))
        position_list = ', '.join(str(p) for p in sorted(user_selected_repeat_positions))
        self.status_label.setText(f'Starting remeasurement for channels: {channel_list} at positions: {position_list}...')
        
        # Start with the first position to remeasure
        #first_position = min(positions_to_remeasure)
        #self.show_position_dialog(first_position)
        self.start_worker()

    def update_position_visualization_for_repeat(self):
        """Update position visualization specifically for repeat measurements"""
        if not hasattr(self, 'selected_positions_for_viz'):
            return
            
        # Update compact view to show only selected positions
        if hasattr(self, 'compact_mic_widget') and self.compact_mic_widget:
            self.compact_mic_widget.set_visible_positions_list(list(self.selected_positions_for_viz))
        
        # Update full theater view to show only selected positions
        if hasattr(self, 'visualization_dialog') and self.visualization_dialog:
            self.visualization_dialog.mic_widget.set_visible_positions_list(list(self.selected_positions_for_viz))

    def load_existing_measurement_qualities(self):
        """Load quality data for existing measurements (useful when restarting the app)."""
        try:
            measurements, _ = get_all_measurements_with_uuid()
            if not measurements:
                return
            
            for measurement in measurements:
                title = measurement.get('title', '')
                uuid = measurement.get('uuid', '')
                
                # Parse channel and position from title
                for channel in SPEAKER_LABELS.keys():
                    pattern = rf'^{re.escape(channel)}_pos(\d+)$'
                    match = re.match(pattern, title, re.IGNORECASE)
                    if match:
                        position = int(match.group(1))
                        
                        # Try to get quality metrics for this measurement
                        try:
                            measurement_data = get_measurement_by_uuid(uuid)
                            distortion_data = get_measurement_distortion_by_uuid(uuid)
                            
                            if measurement_data and distortion_data:
                                result = evaluate_measurement(distortion_data, measurement_data, None)
                                if result:
                                    self.measurement_qualities[(channel, position)] = {
                                        'rating': result.get('rating', 'Unknown'),
                                        'score': result.get('score', 0),
                                        'uuid': uuid,
                                        'detail': result.get('detail', None),
                                        'title': title
                                    }
                        except Exception as e:
                            print(f"Could not evaluate quality for {title}: {e}")
                        break
            
            print(f"Loaded quality data for {len(self.measurement_qualities)} existing measurements")
            
        except Exception as e:
            print(f"Error loading existing measurement qualities: {e}")

    def show_measurement_quality_dialog(self, measurement_info):
        """Show quality dialog and handle user choice"""
        dialog = MeasurementQualityDialog(measurement_info, self)
        result = dialog.exec_()
        
        if result == 1:  # Remeasure
            # Delete the current measurement
            uuid = measurement_info['uuid']
            delete_measurement_by_uuid(uuid, self.update_status)
            
            # Remove from quality tracking
            key = (measurement_info['channel'], measurement_info['position'])
            if key in self.measurement_qualities:
                del self.measurement_qualities[key]
            
            # Tell worker to remeasure
            if self.measurement_worker:
                self.measurement_worker.handle_quality_dialog_response('remeasure')
                    
        elif result == 2:  # Continue
            # Tell worker to remeasure
            if self.measurement_worker:
                self.measurement_worker.handle_quality_dialog_response('continue')
                
        else:  # Stop (0)
            # Stop the measurement process
            if self.measurement_worker:
                self.measurement_worker.handle_quality_dialog_response('stop')

    def open_settings_dialog(self):
        dlg = SettingsDialog(self)
        if dlg.exec_():
            #for key, value in dlg.values().items():
             #   qs.set(key, value)          # persist + share
            self.apply_settings()           # read straight from qs


    def apply_settings(self):
        """Apply settings after load / save."""
        if qs.get("show_tooltips", True):
            QToolTip.setFont(QFont("Arial", 10))
        else:
            QToolTip.hideText()
        cfg_name = qs.get("speaker_config", "Manual Select")
        self._set_channel_header(cfg_name)

        cfg_map  = get_speaker_configs()
        if cfg_name in cfg_map and cfg_map[cfg_name]:
            wanted = set(cfg_map[cfg_name])
            for lbl, cb in self.channel_checkboxes.items():
                cb.setChecked(lbl in wanted)
        self.update_channel_visualization()
        # Apply visualization mode
        viz_mode = qs.get('viz_view', "Grid View")
        # Defer mode switching to ensure UI is fully initialized
        QTimer.singleShot(100, lambda: self.switch_visualization_mode(viz_mode))

    def switch_visualization_mode(self, mode):
        """Switch between Grid / Compact / Full theatre views."""
        qs.set('viz_view', mode)          # persist the choice

        if mode == "Grid View":           # ───── ① GRID  ─────
            self._attach_grid_widget()
            self.grid_widget.show()
            if getattr(self, 'compact_mic_widget', None):
                self.compact_mic_widget.hide()
            if getattr(self, 'visualization_dialog', None):
                self.visualization_dialog.hide()

        elif mode == "Compact Theater View":          # ───── ② COMPACT ─────
            self._detach_grid_widget()                # ← really remove
            self.show_compact_visualization()         # (creates if needed)

        elif mode == "Full Theater View":             # ───── ③ FULL ─────
            self._attach_grid_widget()
            self.grid_widget.show()
            if getattr(self, 'compact_mic_widget', None):
                self.compact_mic_widget.hide()
            self.show_visualization_dialog()

    def ensure_widget_visibility(self):
        """Ensure widgets are in the correct visibility state for current mode"""
        current_mode = self.get_current_viz_mode()
        
        if current_mode == "Grid View":
            if hasattr(self, 'grid_widget') and self.grid_widget:
                self.grid_widget.show()
            if hasattr(self, 'compact_mic_widget') and self.compact_mic_widget:
                self.compact_mic_widget.hide()
        elif current_mode == "Compact Theater View":
            if hasattr(self, 'grid_widget') and self.grid_widget:
                self.grid_widget.hide()
            if hasattr(self, 'compact_mic_widget') and self.compact_mic_widget:
                self.compact_mic_widget.show()

    def get_current_viz_mode(self):
        """Get the current visualization mode"""
        return qs.get('viz_view', "Grid View")
    
    def show_compact_visualization(self):
        # make sure the grid is out of the way
        self._detach_grid_widget()

        # ---- create the widget once ---------------------------------
        if not getattr(self, "compact_mic_widget", None):
            self.compact_mic_widget = MicPositionWidget(
                "/Users/juanloya/Documents/qrew/qrew/hometheater_base_persp.png",
                "/Users/juanloya/Documents/qrew/qrew/room_layout_persp.json"
            )

            # put the widget in a centring wrapper
            wrapper = QWidget()
            hbox    = QHBoxLayout(wrapper)
            hbox.setContentsMargins(0, 0, 0, 0)
            hbox.addStretch()
            hbox.addWidget(self.compact_mic_widget)
            hbox.addStretch()
            self.grid_container_layout.addWidget(wrapper)
            wrapper.hide()              # keep hidden until we switch modes
            self.compact_wrapper = wrapper   # remember it

        # ----------------------------------------------------------------
        # show the wrapper (and therefore the picture)
        self.compact_wrapper.show()

        # scale it once the container has its final geometry
        QTimer.singleShot(20, self.scale_compact_widget)

        # restore channel selection, flash, …
        self.compact_mic_widget.set_selected_channels(
            list(self.selected_channels_for_viz)
        )
        self.update_mic_visualization()

    # Method for scaling compact widget:
    def scale_compact_widget(self):
        """Scale the compact widget to fit in the container"""
        if not hasattr(self, 'compact_mic_widget') or not self.compact_mic_widget:
            return
            
        grid_container = self.grid_container
        if grid_container is None:
            return
        # Ensure we have valid dimensions
        container_width = max(grid_container.width(), 400)  # Minimum width
        container_height = max(grid_container.height(), 300)  # Minimum height
        
        # optional frame-margin (in logical pixels)
        margin = 6
        aw = container_width  - margin * 2
        ah = container_height - margin * 2

        # ––––– scaling that keeps aspect ratio –––––
        ow = self.compact_mic_widget.original_size.width()
        oh = self.compact_mic_widget.original_size.height()

        scale = min(aw / ow, ah / oh)           # nothing is clamped ⇢ 1.0 max
        scale = max(scale, 0.1)                 # but never smaller than 10 %

        self.compact_mic_widget.set_scale(scale)

    def show_visualization_dialog(self):
        """Show full visualization in a separate dialog"""
        if not self.visualization_dialog:
            self.visualization_dialog = MicPositionVisualizationDialog(self)

        # initial channels
        self.visualization_dialog.mic_widget.set_selected_channels(
            list(self.selected_channels_for_viz))

        # ── NEW: correct number of mic positions ──────────────────
        if hasattr(self, 'selected_positions_for_viz'):
            self.visualization_dialog.mic_widget.set_visible_positions_list(
                list(self.selected_positions_for_viz))
        else:
            self.visualization_dialog.mic_widget.set_visible_positions(
                int(self.pos_selector.currentText()))             
        self.visualization_dialog.show()
        self.visualization_dialog.raise_()
        self.visualization_dialog.activateWindow()
        self.update_mic_visualization()
        
    def update_mic_visualization(self):
        """Update all visualization widgets with current state"""
        # Get current position
        current_pos = self.measurement_state.get('current_position', 0)
        
        # Get current active speaker (only during measurement)
        active_speakers = []
        if self.measurement_state.get('running', False):
            channels = self.measurement_state.get('channels', [])
            channel_index = self.measurement_state.get('channel_index', 0)
            if 0 <= channel_index < len(channels):
                active_speakers = [channels[channel_index]]
        
        # Get selected channels for display
        selected_channels = list(self.selected_channels_for_viz)
        
        # Update compact widget
        if hasattr(self, 'compact_mic_widget') and self.compact_mic_widget and self.compact_mic_widget.isVisible():
            self.compact_mic_widget.set_active_mic(current_pos)
            self.compact_mic_widget.set_active_speakers(active_speakers)
            self.compact_mic_widget.set_selected_channels(selected_channels)
            
        # Update dialog
        if hasattr(self, 'visualization_dialog') and self.visualization_dialog and self.visualization_dialog.isVisible():
            self.visualization_dialog.update_visualization(current_pos, active_speakers, selected_channels)

    def update_visualization_from_worker(self, position, active_speakers, is_flashing):
        """Update visualization from worker thread with flash state"""
        if hasattr(self, 'compact_mic_widget') and self.compact_mic_widget and self.compact_mic_widget.isVisible():
            self.compact_mic_widget.set_active_mic(position)
            self.compact_mic_widget.set_active_speakers(active_speakers if is_flashing else [])
            self.compact_mic_widget.set_flash_state(is_flashing)
            
        if hasattr(self, 'visualization_dialog') and self.visualization_dialog and self.visualization_dialog.isVisible():
            self.visualization_dialog.update_visualization(position, active_speakers if is_flashing else [], flash=is_flashing)

    def resizeEvent(self, event):
        """Handle window resize to scale compact view and maintain proper widget visibility"""
        super().resizeEvent(event)
        self.set_background_image()
        
        current_mode = self.get_current_viz_mode()
        
        if current_mode == "Compact Theater View":
            # Ensure grid is hidden and compact view is properly scaled
            if hasattr(self, 'grid_widget') and self.grid_widget:
                self.grid_widget.hide()
            
            # Rescale compact theater view if visible
            if hasattr(self, 'compact_mic_widget') and self.compact_mic_widget and self.compact_mic_widget.isVisible():
                # Defer scaling to ensure proper container dimensions
                QTimer.singleShot(10, self.scale_compact_widget)
                
        elif current_mode == "Grid View":
            # Ensure grid is visible and compact is hidden
            if hasattr(self, 'grid_widget') and self.grid_widget:
                self.grid_widget.show()
            if hasattr(self, 'compact_mic_widget') and self.compact_mic_widget:
                self.compact_mic_widget.hide()

    def _detach_grid_widget(self):
        """Physically remove the grid widget from the container."""
        if getattr(self, 'grid_widget', None) and self.grid_widget.parent():
            self.grid_container_layout.removeWidget(self.grid_widget)
            self.grid_widget.setParent(None)          # keep the object alive
            self.grid_widget.hide()        # ← prevents 1-frame flicker

    def _attach_grid_widget(self):
        """Put the (already existing) grid widget back into the container."""
        if getattr(self, 'grid_widget', None) and self.grid_widget.parent() is None:
            self.grid_container_layout.addWidget(self.grid_widget)

    def get_scaled_mic_positions(self, num_positions):
        """Map grid positions to actual mic positions in the room"""
        # This maps the grid position numbers to the mic IDs in the JSON
        position_mapping = {
            1: [0],  # Just MLP
            2: [0, 1],  # MLP and front
            3: [0, 1, 2],  # Triangle
            4: [0, 1, 2, 3],  # Square
            5: [0, 1, 2, 3, 4],  # Cross pattern
            6: [0, 1, 2, 3, 4, 5],  # Hexagon
            7: [0, 1, 2, 3, 4, 5, 6],  # Heptagon
            8: [0, 1, 2, 3, 4, 5, 6, 7],  # Octagon
            9: [0, 1, 2, 3, 4, 5, 6, 7, 8],  # Full grid
        }
        
        return position_mapping.get(num_positions, list(range(num_positions)))


    def create_floating_viz_button(self):
        """Create a floating button to quickly toggle visualization"""
        self.viz_float_button = QToolButton(self)
        self.viz_float_button.setIcon(QIcon("icons/theater_view.png"))  # You'll need an icon
        self.viz_float_button.setIconSize(QSize(32, 32))
        self.viz_float_button.setToolTip("Toggle Theater Visualization")
        self.viz_float_button.clicked.connect(self.toggle_visualization)
        self.viz_float_button.setStyleSheet("""
            QToolButton {
                background: rgba(70, 70, 70, 0.8);
                border: 2px solid #555;
                border-radius: 20px;
                padding: 5px;
            }
            QToolButton:hover {
                background: rgba(90, 90, 90, 0.9);
                border: 2px solid #777;
            }
        """)
        
        # Position it in the top-right corner
        self.viz_float_button.move(self.width() - 50, 10)
        self.viz_float_button.raise_()
        
    def toggle_visualization(self):
        """Quick toggle between grid and theater view"""
        current_mode = self.get_current_viz_mode()

        if current_mode == "Full Theater View":
            self.viz_mode_combo.setCurrentText("Grid View")
        else:
            self.viz_mode_combo.setCurrentText("Full Theater View")
            
   # def resizeEvent(self, event):
    #    """Keep floating button in corner on resize"""
     #   super().resizeEvent(event)
      #  if hasattr(self, 'viz_float_button'):
       #     self.viz_float_button.move(self.width() - 50, 10)

    def connect_visualization_signals(self):
        """Connect UI controls to visualization updates"""
        # Connect channel checkboxes with immediate update
        for checkbox in self.channel_checkboxes.values():
            checkbox.stateChanged.connect(lambda: QTimer.singleShot(0, self.update_channel_visualization))
        
        # Connect position selector
        self.pos_selector.currentTextChanged.connect(self.update_position_visualization)

    def update_channel_visualization(self):
        """Update visualization when channels are selected/deselected"""
        selected_channels = [abbr for abbr, checkbox in self.channel_checkboxes.items() 
                           if checkbox.isChecked()]
        
        self.selected_channels_for_viz = set(selected_channels)
        
        # Update compact view
        if hasattr(self, 'compact_mic_widget') and self.compact_mic_widget and self.compact_mic_widget.isVisible():
            self.compact_mic_widget.set_selected_channels(selected_channels)
        
        # Update full theater view
        if hasattr(self, 'visualization_dialog') and self.visualization_dialog and self.visualization_dialog.isVisible():
            self.visualization_dialog.mic_widget.set_selected_channels(selected_channels)
    
    def update_position_visualization(self, positions_text):
        """Update visualization when position count changes"""
        try:
            num_positions = int(positions_text)
            # Update both views to show only the selected number of positions
            if hasattr(self, 'compact_mic_widget') and self.compact_mic_widget:
                self.compact_mic_widget.set_visible_positions(num_positions)
            
            if hasattr(self, 'visualization_dialog') and self.visualization_dialog:
                self.visualization_dialog.mic_widget.set_visible_positions(num_positions)
        except ValueError:
            pass

def wait_for_rew_qt():
    """Wait for REW connection using custom dialog"""
    while not check_rew_connection():
        dialog = REWConnectionDialog()
        result = dialog.exec_()
        
        if result == 0:  # Exit button clicked
            sys.exit(1)
        # If result == 1 (Retry), the while loop will continue and check again

if __name__ == "__main__":
    # Start Flask in a background thread
    flask_thread = Thread(target=run_flask_server, daemon=True)
    flask_thread.start()
    
    time.sleep(1)
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        * {
            font-family: "Monaco";
        }
    """)
    # Check REW connection
    wait_for_rew_qt()
    
    # Initialize all subscriptions
    initialize_rew_subscriptions()
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())
