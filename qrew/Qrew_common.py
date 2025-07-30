# Qrew_common.py
import platform
from PyQt5.QtCore import QTimer

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
    "SW4": "Subwoofer 4",
}

# Qrew_dialogs.py  – add/replace this block
# ----------------------------------------------------------
SPEAKER_CONFIGS = {
    # ───── basic ─────
    "Manual Select": [],
    "Stereo 2.0": ["FL", "FR"],
    "Stereo 2.1": ["FL", "FR", "SW1"],
    "3.0 LCR": ["FL", "FR", "C"],
    "3.1": ["FL", "FR", "C", "SW1"],
    "Quadraphonic 4.0": ["FL", "FR", "SLA", "SRA"],
    "4.1": ["FL", "FR", "SLA", "SRA", "SW1"],
    # ───── Dolby Surround beds ─────
    "5.0": ["FL", "FR", "C", "SLA", "SRA"],
    "5.1": ["FL", "FR", "C", "SW1", "SLA", "SRA"],
    "6.1 (EX / DTS-ES)": [
        "FL",
        "FR",
        "C",
        "SW1",
        "SLA",
        "SRA",
        "SBL",
    ],  # rear-centre → SBL
    "7.1": ["FL", "FR", "C", "SW1", "SLA", "SRA", "SBL", "SBR"],
    # ───── Dolby Atmos Home ─────
    "5.1.2 Atmos": ["FL", "FR", "C", "SW1", "SLA", "SRA", "TFL", "TFR"],
    "5.1.4 Atmos": ["FL", "FR", "C", "SW1", "SLA", "SRA", "TFL", "TFR", "TRL", "TRR"],
    "7.1.2 Atmos": ["FL", "FR", "C", "SW1", "SLA", "SRA", "SBL", "SBR", "TFL", "TFR"],
    "7.1.4 Atmos": [
        "FL",
        "FR",
        "C",
        "SW1",
        "SLA",
        "SRA",
        "SBL",
        "SBR",
        "TFL",
        "TFR",
        "TRL",
        "TRR",
    ],
    "7.1.6 Atmos": [
        "FL",
        "FR",
        "C",
        "SW1",
        "SLA",
        "SRA",
        "SBL",
        "SBR",
        "TFL",
        "TFR",
        "TML",
        "TMR",
        "TRL",
        "TRR",
    ],
    "9.1.6 Atmos (wides)": [
        "FL",
        "FR",
        "C",
        "SW1",
        "SLA",
        "SRA",
        "SBL",
        "SBR",
        "FWL",
        "FWR",
        "TFL",
        "TFR",
        "TML",
        "TMR",
        "TRL",
        "TRR",
    ],
    "11.1.8 Atmos": [
        "FL",
        "FR",
        "C",
        "FHL",
        "FHR",
        "SW1",
        "SLA",
        "SRA",
        "SBL",
        "SBR",
        "SDL",
        "SDR",
        "FWL",
        "FWR",
        "TFL",
        "TFR",
        "TRL",
        "TRR",
        "RHL",
        "RHR",
    ],
    # ───── Auro-3D (13-strain) ─────
    "Auro-3D 9.1": ["FL", "FR", "C", "SW1", "SLA", "SRA", "FHL", "FHR", "SHL", "SHR"],
    "Auro-3D 10.1": [
        "FL",
        "FR",
        "C",
        "SW1",
        "SLA",
        "SRA",
        "FHL",
        "FHR",
        "SHL",
        "SHR",
        "TML",
    ],  # VOG ≈ TML
    "Auro-3D 11.1": [
        "FL",
        "FR",
        "C",
        "SW1",
        "SLA",
        "SRA",
        "FHL",
        "FHR",
        "SHL",
        "SHR",
        "TFL",
        "TFR",
    ],  # uses front-tops for CH pair
    "Auro-3D 13.1": [
        "FL",
        "FR",
        "C",
        "SW1",
        "SLA",
        "SRA",
        "SBL",
        "SBR",
        "FHL",
        "FHR",
        "SHL",
        "SHR",
        "TML",
    ],  # rear heights ≈ SBL/SBR
}
# ----------------------------------------------------------

REW_API_BASE_URL = "http://127.0.0.1:4735"
WAV_STIMULUS_FILENAME = "1MMeasSweep_0_to_24000_-12_dBFS_48k_Float_L_refR.wav"

# Global variables
selected_stimulus_path = None
stimulus_dir = None


class TaskbarFlasher:
    """
    🔧 PyInstaller-optimized TaskbarFlasher with lazy imports
    Only imports platform-specific modules when actually needed
    """

    def __init__(self, widget):
        self.widget = widget
        self.timer = None
        self.platform = platform.system()
        self._platform_initialized = False

        # Platform-specific variables (lazy loaded)
        self.platform_modules = None

    def _lazy_init_platform(self):
        """Initialize platform-specific imports only when needed"""
        if self._platform_initialized:
            return

        try:
            if self.platform == "Darwin":
                # 🔧 Lazy import AppKit only when needed
                try:
                    from AppKit import NSApp, NSCriticalRequest

                    self.NSApp = NSApp
                    self.NSCriticalRequest = NSCriticalRequest
                    print("[TaskbarFlasher] macOS AppKit initialized")
                except ImportError as e:
                    print(f"[TaskbarFlasher] AppKit not available: {e}")
                    self.NSApp = None

            elif self.platform == "Windows":
                # 🔧 Lazy import Windows modules only when needed
                try:
                    import ctypes
                    from ctypes import wintypes

                    class FLASHWINFO(ctypes.Structure):
                        _fields_ = [
                            ("cbSize", wintypes.UINT),
                            ("hwnd", wintypes.HWND),
                            ("dwFlags", wintypes.DWORD),
                            ("uCount", wintypes.UINT),
                            ("dwTimeout", wintypes.DWORD),
                        ]

                    self.FLASHWINFO = FLASHWINFO
                    self.FlashWindowEx = ctypes.windll.user32.FlashWindowEx
                    self.FLASHW_ALL = 3
                    self.FLASHW_STOP = 0
                    print("[TaskbarFlasher] Windows ctypes initialized")
                except ImportError as e:
                    print(f"[TaskbarFlasher] Windows ctypes not available: {e}")
                    self.FLASHWINFO = None

            elif self.platform == "Linux":
                # 🔧 Lazy import Linux X11 modules only when needed
                try:
                    import ctypes.util
                    import ctypes

                    self._load_linux_libs(ctypes)
                    print("[TaskbarFlasher] Linux X11 initialized")
                except Exception as e:
                    print(f"[TaskbarFlasher] Linux X11 not available: {e}")
                    self.X11 = None

        except Exception as e:
            print(f"[TaskbarFlasher] Platform initialization failed: {e}")

        self._platform_initialized = True

    def _load_linux_libs(self, ctypes):
        """Load Linux X11 libraries"""
        x11 = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11"))
        self.X11 = x11
        self.Display = x11.XOpenDisplay(None)
        self.X11.XSetWMHints.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
        ]
        self.X11.XFlush.argtypes = [ctypes.c_void_p]
        self.X11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    def start(self, interval_ms=3000):
        """Start taskbar flashing with lazy platform initialization"""
        # Only initialize platform-specific code when actually starting
        self._lazy_init_platform()

        if self.timer is None:
            self.timer = QTimer(self.widget)
            self.timer.timeout.connect(self.trigger)
            self.timer.start(interval_ms)

    def stop(self):
        """Stop taskbar flashing"""
        if self.timer:
            self.timer.stop()
            self.timer = None

        # Only call platform-specific stop if initialized
        if self._platform_initialized and self.platform == "Windows":
            try:
                hwnd = int(self.widget.winId())
                self._flash_windows(hwnd, stop=True)
            except:
                pass

    def trigger(self):
        """Trigger platform-specific attention getting"""
        if not self._platform_initialized:
            return

        try:
            if self.platform == "Darwin" and hasattr(self, "NSApp") and self.NSApp:
                self.NSApp.requestUserAttention_(self.NSCriticalRequest)

            elif (
                self.platform == "Windows"
                and hasattr(self, "FLASHWINFO")
                and self.FLASHWINFO
            ):
                hwnd = int(self.widget.winId())
                self._flash_windows(hwnd)

            elif self.platform == "Linux" and hasattr(self, "X11") and self.X11:
                self._set_urgency_hint_linux(True)

        except Exception as e:
            print(f"[TaskbarFlasher] Trigger failed: {e}")

    def _flash_windows(self, hwnd, stop=False):
        """Flash Windows taskbar"""
        try:
            import ctypes

            # Use ctypes.sizeof() instead of _sizeof_() method
            info = self.FLASHWINFO(
                ctypes.sizeof(self.FLASHWINFO),  # Correct way to get structure size
                hwnd,
                self.FLASHW_STOP if stop else self.FLASHW_ALL,
                5,
                0,
            )
            self.FlashWindowEx(info)
        except Exception as e:
            print(f"[TaskbarFlasher] Windows flash failed: {e}")

    def _set_urgency_hint_linux(self, urgent=True):
        """Set Linux urgency hint"""
        try:
            window = int(self.widget.winId())
            if self.X11 and self.Display:
                import ctypes

                XUrgencyHint = 1 << 8

                class XWMHints(ctypes.Structure):
                    _fields_ = [
                        ("flags", ctypes.c_long),
                        ("input", ctypes.c_bool),
                        ("initial_state", ctypes.c_int),
                        ("icon_pixmap", ctypes.c_ulong),
                        ("icon_window", ctypes.c_ulong),
                        ("icon_x", ctypes.c_int),
                        ("icon_y", ctypes.c_int),
                        ("icon_mask", ctypes.c_ulong),
                        ("window_group", ctypes.c_ulong),
                    ]

                hints = XWMHints()
                hints.flags = XUrgencyHint if urgent else 0
                self.X11.XSetWMHints(self.Display, window, ctypes.byref(hints))
                self.X11.XFlush(self.Display)
        except Exception as e:
            print(f"[TaskbarFlasher] Linux urgency hint failed: {e}")
