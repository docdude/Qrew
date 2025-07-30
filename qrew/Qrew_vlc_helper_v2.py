# Qrew_vlc_helper_v2.py – non-blocking VLC wrapper
import os
import sys
import platform
import subprocess
import threading
import queue
import time
import shutil
import re
import signal
import ctypes
from pathlib import Path
from typing import Callable, Optional

# Import PyQt5 signals
try:
    from PyQt5.QtCore import QTimer, pyqtSignal, QObject
    from PyQt5.QtWidgets import QApplication
except ImportError:
    try:
        from PySide2.QtCore import QTimer, Signal as pyqtSignal, QObject
        from PySide2.QtWidgets import QApplication
    except ImportError:
        QTimer = None
        QApplication = None
        QObject = object
        pyqtSignal = None

try:
    from . import Qrew_common
    from . import Qrew_settings as qs
    from .Qrew_find_vlc import find_vlc_lib_dir
    from .Qrew_messagebox import QrewMessageBox  # Import message box
    from .Qrew_vlc_widget import (
        AudioPlayerWidget,
        invoke_on_gui,
    )  # Import custom audio player widget
except ImportError:
    import Qrew_common
    import Qrew_settings as qs
    from Qrew_find_vlc import find_vlc_lib_dir
    from Qrew_messagebox import QrewMessageBox

    try:
        from Qrew_vlc_widget import (
            AudioPlayerWidget,
            invoke_on_gui,
        )  # Import custom audio player widget
    except ImportError:
        AudioPlayerWidget = None

# ----------------------------------------------------------------------
# VLC environment setup and discovery
# ----------------------------------------------------------------------


def debug_vlc_paths():
    """Print diagnostic information about VLC paths"""
    print("\n----- VLC PATH DIAGNOSTICS -----")

    # Check environment variables
    for var in ["PYTHON_VLC_LIB_PATH", "VLC_PLUGIN_PATH", "PATH"]:
        value = os.environ.get(var)
        if value:
            print(f"{var} = {value}")
            if var == "PYTHON_VLC_LIB_PATH" and platform.system() == "Windows":
                if os.path.isfile(value):
                    print(f"SUCCESS: PYTHON_VLC_LIB_PATH points to file: {value}")
                elif os.path.exists(os.path.join(value, "libvlc.dll")):
                    print(
                        f"FAILED: PYTHON_VLC_LIB_PATH points to directory instead of file"
                    )
                else:
                    print(f"FAILED: libvlc.dll NOT found at {value}")

    # Check if we can find VLC
    lib_dir = find_vlc_lib_dir()
    print(f"find_vlc_lib_dir() returned: {lib_dir}")
    if lib_dir:
        if platform.system() == "Windows":
            dll_path = os.path.join(lib_dir, "libvlc.dll")
            if os.path.exists(dll_path):
                print(f"SUCCESS: Found libvlc.dll at {dll_path}")
            else:
                print(f"FAILED: libvlc.dll NOT found in {lib_dir}")
        elif platform.system() == "Darwin":
            dylib_path = os.path.join(lib_dir, "libvlc.dylib")
            if os.path.exists(dylib_path):
                print(f"SUCCESS: Found libvlc.dylib at {dylib_path}")
            else:
                print(f"FAILED: libvlc.dylib NOT found in {lib_dir}")
        elif platform.system() == "Linux":
            so_path = os.path.join(lib_dir, "libvlc.so")
            if os.path.exists(so_path):
                print(f"SUCCESS: Found libvlc.so at {so_path}")
            else:
                print(f"FAILED: libvlc.so NOT found in {lib_dir}")
    print("--------------------------------\n")


def setup_vlc_environment():
    """
    Set up environment for VLC library loading.
    Must be called BEFORE importing vlc.
    Returns True if environment was set up successfully.
    """
    try:
        # Get VLC library directory
        from .Qrew_find_vlc import find_vlc_lib_dir
    except ImportError:
        from Qrew_find_vlc import find_vlc_lib_dir

    lib_dir = find_vlc_lib_dir()
    if not lib_dir:
        print("FAILED: VLC libraries not found in standard locations")

        # Set setting to force subprocess backend
        qs.set("vlc_backend", "subprocess")
        qs.set("vlc_backend_locked", True)  # Add a flag to lock the backend setting

        # We'll defer showing the message box until later when QApplication exists
        # Store the message details for later display
        qs.set(
            "vlc_error_message",
            {
                "title": "VLC Libraries Not Found",
                "text": "VLC libraries were not found in standard locations. "
                "Playback will fall back to using the VLC application if available.",
            },
        )

        return False

    system = platform.system()
    libvlc_loaded = False  # Track if libvlc loaded successfully

    # Set up environment based on platform
    if system == "Windows":
        # Normalize path for Windows
        lib_dir = os.path.normpath(lib_dir)

        # Add to DLL search path (Python 3.8+)
        try:
            os.add_dll_directory(lib_dir)
            print(f"SUCCESS: Added VLC directory to DLL search path: {lib_dir}")
        except (AttributeError, OSError) as e:
            print(f"FAILED: Error adding DLL directory: {e}")

        # Add to PATH
        os.environ["PATH"] = lib_dir + os.pathsep + os.environ.get("PATH", "")

        # Set plugin path
        plugin_path = os.path.join(lib_dir, "plugins")
        if os.path.isdir(plugin_path):
            os.environ["VLC_PLUGIN_PATH"] = plugin_path
            print(f"SUCCESS: Set VLC_PLUGIN_PATH to {plugin_path}")

        # Test load the DLL directly to check for dependency issues
        try:
            dll_path = os.path.join(lib_dir, "libvlc.dll")
            if os.path.exists(dll_path):
                # Check Python architecture before loading
                python_arch = "64-bit" if sys.maxsize > 2**32 else "32-bit"
                print(f"Python architecture: {python_arch}")

                try:
                    ctypes.CDLL(dll_path)
                    print(f"SUCCESS: Successfully loaded {dll_path} with ctypes")
                    libvlc_loaded = True  # Mark as successfully loaded
                    # Reset the vlc_backend_locked flag
                    qs.set("vlc_backend_locked", False)

                    # Clear PYTHON_VLC_LIB_PATH if it points to a directory
                    # (python-vlc expects a file path here, not a directory)
                    if "PYTHON_VLC_LIB_PATH" in os.environ and os.path.isdir(
                        os.environ["PYTHON_VLC_LIB_PATH"]
                    ):
                        del os.environ["PYTHON_VLC_LIB_PATH"]
                except Exception as e:
                    print(f"FAILED: Failed to load libvlc.dll: {e}")
                    error_message = f"Failed to load libvlc.dll: {e}"

                    # Check VLC DLL architecture
                    try:
                        import struct

                        with open(dll_path, "rb") as f:
                            # Read PE header to determine architecture
                            f.seek(0x3C)
                            pe_offset = struct.unpack("<I", f.read(4))[0]
                            f.seek(pe_offset + 4)
                            machine_type = struct.unpack("<H", f.read(2))[0]
                            vlc_arch = "64-bit" if machine_type == 0x8664 else "32-bit"
                            print(f"VLC architecture: {vlc_arch}")

                            if python_arch != vlc_arch:
                                arch_message = f"Architecture mismatch: Python is {python_arch} but VLC is {vlc_arch}"
                                print(f"FAILED: {arch_message}")
                                error_message += f"\n\n{arch_message}\n\nPlease install {python_arch} version of VLC."

                                # Fall back to subprocess mode if possible
                                if "PYTHON_VLC_LIB_PATH" in os.environ:
                                    print(
                                        "   Removing PYTHON_VLC_LIB_PATH to allow subprocess fallback"
                                    )
                                    del os.environ["PYTHON_VLC_LIB_PATH"]

                    except Exception as arch_error:
                        print(f"Could not determine VLC architecture: {arch_error}")
                        error_message += (
                            f"\n\nCould not determine VLC architecture: {arch_error}"
                        )

                    # Store error message for deferred display
                    qs.set(
                        "vlc_error_message",
                        {"title": "VLC Library Error", "text": error_message},
                    )

                    # Force subprocess backend
                    qs.set("vlc_backend", "subprocess")
                    qs.set("vlc_backend_locked", True)

                    return False
            else:
                error_message = f"VLC library not found: {dll_path}"
                print(f"FAILED: {error_message}")

                # Store error message for deferred display
                qs.set(
                    "vlc_error_message",
                    {"title": "VLC Library Missing", "text": error_message},
                )

                # Force subprocess backend
                qs.set("vlc_backend", "subprocess")
                qs.set("vlc_backend_locked", True)

                return False
        except Exception as e:
            error_message = f"Failed to load libvlc.dll: {e}"
            print(f"FAILED: {error_message}")

            # Store error message for deferred display
            qs.set(
                "vlc_error_message",
                {"title": "VLC Library Error", "text": error_message},
            )

            # Force subprocess backend
            qs.set("vlc_backend", "subprocess")
            qs.set("vlc_backend_locked", True)

            return False
    elif system == "Darwin":
        # macOS: Set DYLD_LIBRARY_PATH and VLC_PLUGIN_PATH
        os.environ["DYLD_LIBRARY_PATH"] = (
            lib_dir + os.pathsep + os.environ.get("DYLD_LIBRARY_PATH", "")
        )

        # Set plugin path
        plugin_path = os.path.join(lib_dir, "..", "plugins")
        if os.path.isdir(plugin_path):
            os.environ["VLC_PLUGIN_PATH"] = plugin_path
            print(f"✅ Set VLC_PLUGIN_PATH to {plugin_path}")

        # Pre-load libvlccore.dylib - often required on macOS
        try:
            core_path = os.path.join(lib_dir, "libvlccore.dylib")
            if os.path.exists(core_path):
                ctypes.CDLL(core_path)
                print(f"✅ Pre-loaded {core_path}")
        except Exception as e:
            print(f"❌ Failed to pre-load libvlccore.dylib: {e}")

    elif system == "Linux":
        # Linux: Set LD_LIBRARY_PATH and VLC_PLUGIN_PATH
        os.environ["LD_LIBRARY_PATH"] = (
            lib_dir + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
        )

        # Common plugin paths on Linux
        for plugin_path in [
            os.path.join(lib_dir, "vlc/plugins"),
            os.path.join(os.path.dirname(lib_dir), "vlc/plugins"),
            "/usr/lib/x86_64-linux-gnu/vlc/plugins",
            "/usr/lib/vlc/plugins",
        ]:
            if os.path.isdir(plugin_path):
                os.environ["VLC_PLUGIN_PATH"] = plugin_path
                print(f"✅ Set VLC_PLUGIN_PATH to {plugin_path}")
                break

    return True


# ----------------------------------------------------------------------
# Actual VLC loading
# ----------------------------------------------------------------------

# First run diagnostics
debug_vlc_paths()

# PyInstaller frozen environment handling
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    print("Running from PyInstaller bundle - using bundled VLC libraries")
    # Environment variables should be set by our runtime hook
    if os.environ.get("VLC_PLUGIN_PATH"):
        print(f"VLC_PLUGIN_PATH: {os.environ.get('VLC_PLUGIN_PATH')}")

# Set up environment BEFORE importing vlc
vlc = None
vlc_available = False
if setup_vlc_environment():
    try:
        print("Attempting to import vlc module...")
        import vlc

        vlc_available = True
        # Reset the vlc_backend_locked flag since we successfully loaded the library
        qs.set("vlc_backend_locked", False)
        print(
            f"SUCCESS: Successfully imported vlc module (version: {vlc.libvlc_get_version().decode()})"
        )
    except ImportError as e:
        print(f"FAILED: Failed to import vlc: {e}")
        error_message = f"Failed to import python-vlc module: {e}\n\nFalling back to VLC application."

        # Store error message for deferred display
        qs.set(
            "vlc_error_message", {"title": "VLC Import Error", "text": error_message}
        )

        # Force subprocess backend
        qs.set("vlc_backend", "subprocess")
        qs.set("vlc_backend_locked", True)

        # Additional diagnostics for architecture issues
        print("\nTrying to diagnose the issue...")
        python_arch = "64-bit" if sys.maxsize > 2**32 else "32-bit"
        print(f"Python architecture: {python_arch}")

        # Import struct for binary file analysis
        import struct

        # Reuse the already found lib_dir or find it again

        lib_dir = find_vlc_lib_dir()
        if lib_dir and platform.system() == "Windows":
            try:
                dll_path = os.path.join(lib_dir, "libvlc.dll")
                with open(dll_path, "rb") as f:
                    # Read PE header to determine architecture
                    f.seek(0x3C)
                    pe_offset = struct.unpack("<I", f.read(4))[0]
                    f.seek(pe_offset + 4)
                    machine_type = struct.unpack("<H", f.read(2))[0]
                    vlc_arch = "64-bit" if machine_type == 0x8664 else "32-bit"
                    print(f"VLC architecture: {vlc_arch}")
                    if python_arch != vlc_arch:
                        print(
                            f"FAILED: Architecture mismatch! Python is {python_arch} but VLC is {vlc_arch}"
                        )
                        print(
                            f"   Solution: Install {python_arch} version of VLC or use {vlc_arch} Python"
                        )
            except Exception as e:
                print(f"Could not determine VLC architecture: {e}")


# ----------------------------------------------------------------------
# Rest of the VLC player implementation
# All code after this point can assume vlc has been imported if available
# ----------------------------------------------------------------------


class VLCPlayer(QObject):
    """
    Play a media file either with python-vlc (libvlc) or by launching the
    VLC executable.  Non-blocking; calls *on_finished* when playback ends.
    """

    # Class-level variable to track if VLC has been pre-initialized
    _vlc_initialized = False
    _vlc_init_lock = threading.Lock()

    # Class-level callback for measurement abort
    _abort_callback = None

    # Define signals
    if pyqtSignal is not None:
        error_occurred = pyqtSignal(str, str)
        request_widget_creation = pyqtSignal(bool)  # show_gui parameter

    def __init__(self):
        if QObject is not None:
            super().__init__()

        # Initialize properties
        self._thread = None
        self._playing = False
        self._player = None  # libvlc player
        self._instance = None  # libvlc instance
        self._process = None  # subprocess
        self._system = platform.system()
        self._player_widget = None  # AudioPlayerWidget instance
        self._widget_creation_requested = False
        self._widget_ready = False
        self._cleanup_in_progress = False  # Prevent double cleanup

        # Preload VLC in background thread if available and not already initialized
        if vlc and not VLCPlayer._vlc_initialized:
            self._preload_vlc_library()

    def _preload_vlc_library(self):
        """Initialize VLC in a background thread to prevent blocking on first use"""

        def _initialize_vlc():
            with VLCPlayer._vlc_init_lock:
                if not VLCPlayer._vlc_initialized:
                    try:
                        # Create a minimal VLC instance to load the library
                        temp_instance = vlc.Instance("--quiet")
                        temp_player = temp_instance.media_player_new()
                        # Clean up immediately
                        temp_player.release()
                        temp_instance.release()
                        VLCPlayer._vlc_initialized = True
                        print("VLC library pre-initialized successfully")
                    except Exception as e:
                        print(f"VLC pre-initialization failed: {e}")
                        # Don't mark as initialized if it failed

        # Start the initialization in a background thread
        threading.Thread(
            target=_initialize_vlc, daemon=True, name="VLC_Preload"
        ).start()

    @classmethod
    def set_abort_callback(cls, callback: Callable[[], None]):
        """
        Set a callback function to be called when playback errors occur.
        This is typically used to abort measurements in progress.

        Args:
            callback: A function that will be called with no arguments
                     when playback errors occur.
        """
        cls._abort_callback = callback

    # -------------------- public entry point --------------------------
    def play(
        self,
        path: str,
        show_gui: bool = True,
        backend: str = "auto",  # "libvlc" | "subprocess" | "auto"
        on_finished: Optional[Callable[[], None]] = None,
    ):
        """
        Start playback and return immediately.
        *on_finished* is called in a background thread when playback ends.
        """
        # Clean up any previous playback completely
        if self._playing or self._player_widget:
            # For libvlc, clean up the widget completely
            if self._player_widget and not self._cleanup_in_progress:
                self._cleanup_in_progress = True
                try:
                    widget = self._player_widget
                    self._player_widget = None
                    self._player = None
                    self._instance = None
                    widget.request_cleanup()
                    print("DEBUG: Cleaned up previous VLC widget")
                except Exception as e:
                    print(f"Error cleaning up previous widget: {e}")
                finally:
                    self._cleanup_in_progress = False

            # For subprocess, terminate the process
            if self._process:
                try:
                    if self._system == "Windows":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(self._process.pid)],
                            capture_output=True,
                        )
                    else:
                        self._process.terminate()
                        self._process.wait(timeout=1)
                except Exception:
                    pass
                self._process = None

            self._playing = False

        # Check if backend is locked to subprocess
        if qs.get("vlc_backend_locked", False) and backend != "subprocess":
            print("⚠️ VLC backend locked to subprocess mode due to library issues")
            backend = "subprocess"

        # Determine backend
        if backend == "auto":
            backend = "libvlc" if vlc_available else "subprocess"

        # Use a separate thread for libvlc initialization to prevent blocking
        if backend == "libvlc" and vlc:
            # Start playback in a separate thread to avoid blocking
            def _start_playback():
                try:
                    if not vlc:
                        raise RuntimeError("python-vlc not installed")
                    self._play_libvlc(path, show_gui, on_finished)
                except Exception as e:
                    print(f"Playback error in thread: {e}")

                    # Use our thread-safe method to show error message
                    error_text = f"Error starting VLC: {str(e)}"
                    self.show_error_message(
                        "VLC Error", error_text + "\nPlease install VLC."
                    )

                    # Don't call stop_and_exit() - let natural cleanup happen
                    self._playing = False
                    # Call the callback on error too
                    if on_finished:
                        on_finished()

            threading.Thread(
                target=_start_playback, daemon=True, name="VLC_Playback"
            ).start()
            # Return True to indicate playback was initiated successfully
            return True
        else:
            # For subprocess backend, we can start directly
            try:
                if backend == "libvlc":
                    if not vlc:
                        raise RuntimeError("python-vlc not installed")
                    self._play_libvlc(path, show_gui, on_finished)
                    return True
                elif backend == "subprocess":
                    self._play_subproc(path, show_gui, on_finished)
                    return True
                else:
                    raise ValueError(
                        "backend must be 'libvlc', 'subprocess', or 'auto'"
                    )
            except Exception as e:
                print(f"Playback error: {e}")

                # Use our thread-safe method to show error message
                error_text = f"Error starting VLC: {str(e)}"
                self.show_error_message(
                    "VLC Error", error_text + "\nPlease install VLC."
                )

                # Don't call stop_and_exit() - let caller handle cleanup
                self._playing = False
                # Call the callback on error too
                if on_finished:
                    on_finished()
                return False

    # -------------------- libvlc path --------------------------------
    def _play_libvlc(self, path, show_gui, on_finished):
        try:
            from PyQt5.QtCore import QThread
            from PyQt5.QtWidgets import QApplication

            # Check if we're on the main thread
            app = QApplication.instance()
            is_main_thread = app and app.thread() == QThread.currentThread()
            print(f"DEBUG: _play_libvlc called from main thread: {is_main_thread}")

            # Widget creation logic - handle threading
            # Check if widget exists and is still valid (not cleaned up)
            widget_needs_creation = (
                not hasattr(self, "_player_widget")
                or not self._player_widget
                or (
                    hasattr(self._player_widget, "is_valid")
                    and not self._player_widget.is_valid()
                )
            )

            if widget_needs_creation:
                if not is_main_thread:
                    print("DEBUG: Requesting widget creation from main thread")
                    self._widget_ready = False

                    # Find main window and request widget creation
                    main_window_found = False
                    for widget in app.topLevelWidgets():
                        if hasattr(widget, "create_vlc_widget_signal"):
                            widget.create_vlc_widget_signal.emit(show_gui)
                            main_window_found = True
                            break

                    if not main_window_found:
                        print("ERROR: Could not find main window for widget creation")
                        return False

                    # Wait for widget creation with timeout
                    max_wait = 50  # 5 seconds at 100ms intervals
                    wait_count = 0
                    while not self._widget_ready and wait_count < max_wait:
                        QThread.msleep(100)
                        app.processEvents()
                        wait_count += 1

                    if not self._widget_ready:
                        print("ERROR: Widget creation timeout")
                        return False
                else:
                    # We're on main thread, create directly
                    print("DEBUG: Creating widget directly on main thread")
                    self._create_widget_direct(show_gui)

            # Verify we have a widget
            if not hasattr(self, "_player_widget") or not self._player_widget:
                print("ERROR: No player widget available after creation attempt")
                return False

            # Store references to the internal VLC objects for consistency with rest of the class
            self._player = self._player_widget.get_player()
            self._instance = self._player_widget.get_vlc_instance()

            # Verify the widget is properly initialized
            if not self._player or not self._instance:
                print("ERROR: Widget VLC objects are not initialized")
                print(f"DEBUG: _player = {self._player}, _instance = {self._instance}")
                # Try to reinitialize the widget
                if hasattr(self._player_widget, "reinitialize"):
                    print("DEBUG: Attempting to reinitialize widget")
                    self._player_widget.reinitialize()
                    # Get the objects again
                    self._player = self._player_widget.get_player()
                    self._instance = self._player_widget.get_vlc_instance()
                    if not self._player or not self._instance:
                        print("ERROR: Reinitialize failed")
                        return False
                    print("DEBUG: Widget reinitialized successfully")
                else:
                    return False

            # Open the media file
            # self._player_widget.open_media(Path(path).as_posix())
            invoke_on_gui(self._player_widget, "open_media", Path(path).as_posix())

            # Handle GUI visibility using signal (thread-safe)
            if show_gui:
                print("DEBUG: Requesting GUI visibility via signal")
                self._player_widget.show_gui(show_gui)
            time.sleep(0.1)  # Allow time for GUI to update
            # Finish queue + callback
            done_q = queue.Queue()

            def _on_end(ev):
                done_q.put(True)

            def _on_error(ev):
                print(f"VLC playback error event: {ev.type}")
                done_q.put(False)  # Signal error

            # Attach to multiple events to make sure we catch all endings
            # Need to access the actual VLC player object inside the widget
            evmgr = self._player.event_manager()
            evmgr.event_attach(vlc.EventType.MediaPlayerEndReached, _on_end)
            evmgr.event_attach(vlc.EventType.MediaPlayerStopped, _on_end)
            evmgr.event_attach(vlc.EventType.MediaPlayerEncounteredError, _on_error)

            # Play using the widget's play method
            success = self._player_widget.play()
            if success is False:
                print("Error starting VLC playback")
                return False

            self._playing = True

            # watchdog thread waits for queue then fires callback
            def _watch():
                cleanup_done = False
                try:
                    # Add timeout to prevent indefinite blocking
                    result = done_q.get(timeout=300)  # 5 minute timeout for long sweeps
                    if not result:
                        print("VLC playback reported an error")
                    else:
                        print("Sweep playback completed")
                        print("DEBUG: Playback ended, stopping player")
                except queue.Empty:
                    print("Warning: VLC playback timeout after 5 minutes")
                finally:
                    self._playing = False

                    # Clean up the widget after playback completes
                    # This ensures each measurement gets a fresh player
                    if not cleanup_done and not self._cleanup_in_progress:
                        cleanup_done = True
                        self._cleanup_in_progress = True
                        try:
                            if self._player_widget:
                                print("[_watch] Requesting cleanup after playback")
                                # Store widget reference before cleanup
                                widget = self._player_widget
                                # Clear references first
                                self._player_widget = None
                                self._player = None
                                self._instance = None
                                # Now request cleanup which will close the widget
                                widget.request_cleanup()
                                print("[_watch] Cleanup completed")
                        except Exception as e:
                            print(f"Error during post-playback cleanup: {e}")
                        finally:
                            self._cleanup_in_progress = False

                    # Call the callback after cleanup
                    if on_finished:
                        on_finished()

            # Start the watchdog thread (only once)
            threading.Thread(target=_watch, daemon=True).start()
            # Return success to indicate the player started correctly
            return True
        except Exception as e:
            print(f"Error in _play_libvlc: {e}")
            # Don't call stop_and_exit() here - let the caller handle cleanup
            # This prevents premature cleanup when retrying
            self._playing = False
            # Call the callback even if we had an error
            if on_finished:
                on_finished()
            return False

    # -------------------- subprocess path ----------------------------
    def _play_subproc(self, path, show_gui, on_finished):
        vlc_path = self._find_vlc_exe()
        if not vlc_path:
            raise RuntimeError("VLC executable not found")
        if self._system == "Darwin":
            cmd = [vlc_path, "--play-and-exit", "--auhal-volume=256", path]
            if not show_gui:
                cmd += ["--intf", "dummy"]
        else:
            cmd = [vlc_path, "--play-and-exit", "--volume-step=256", path]
            if not show_gui:
                cmd += ["--intf", "dummy"]

        try:
            # Ensure process group for better termination on Unix-like systems
            if self._system != "Windows":
                self._process = subprocess.Popen(cmd, start_new_session=True)
            else:
                self._process = subprocess.Popen(cmd)

            self._playing = True

            def _watch():
                self._process.wait()
                self._playing = False
                if on_finished:
                    on_finished()
                # Don't call stop_and_exit() - let the process be reused

            threading.Thread(target=_watch, daemon=True).start()
            return True  # Successfully started playback
        except Exception as e:
            print(f"Error starting subprocess playback: {e}")
            return False

    def _create_widget_direct(self, show_gui):
        """Create widget directly when on main thread"""
        try:
            self._player_widget = AudioPlayerWidget()
            #  self._player_widget.resize(600, 210)
            # self._player_widget.setStyleSheet("background-color: #263238;")
            self._widget_ready = True
            print("DEBUG: Widget created directly on main thread")
        except Exception as e:
            print(f"ERROR: Failed to create widget directly: {e}")
            self._widget_ready = False

    def set_widget_from_main_thread(self, widget):
        """Called by main thread after widget creation via signal"""
        self._player_widget = widget
        self._widget_ready = True
        print("DEBUG: Widget set from main thread via signal")

    def stop_and_exit(self):
        """
        Stop playback and clean up all resources.
        This method is designed to be safe to call multiple times.
        """
        try:
            proc = self._process  # local copy

            # Check if we have an AudioPlayerWidget
            if (
                hasattr(self, "_player_widget")
                and self._player_widget
                and not self._cleanup_in_progress
            ):
                self._cleanup_in_progress = True
                try:
                    # Request proper cleanup from the widget
                    print("DEBUG: stop_and_exit - cleaning up AudioPlayerWidget")
                    widget = self._player_widget

                    # Clear references immediately
                    self._player_widget = None
                    self._player = None
                    self._instance = None
                    self._playing = False

                    # Now request cleanup on the widget
                    widget.request_cleanup()

                    print("SUCCESS: Widget cleanup requested")
                    return
                except Exception as e:
                    print(f"Error cleaning up AudioPlayerWidget: {e}")
                finally:
                    self._cleanup_in_progress = False
            # Otherwise handle standard VLC player
            elif self._player and hasattr(self._player, "stop"):
                try:
                    self._player.stop()
                    # Wait briefly for player to stop
                    stop_timeout = time.time() + 2.0
                    while (
                        hasattr(self._player, "is_playing")
                        and time.time() < stop_timeout
                    ):
                        if not self._player.is_playing():
                            break
                        time.sleep(0.1)
                except Exception as e:
                    print(f"Error stopping libvlc player: {e}")

                # Release libvlc player resources
                if self._player:
                    try:
                        self._player.release()
                    except Exception as e:
                        print(f"Error releasing libvlc player: {e}")
                    finally:
                        self._player = None

                # Release libvlc instance resources
                if self._instance:
                    try:
                        self._instance.release()
                    except Exception as e:
                        print(f"Error releasing libvlc instance: {e}")
                    finally:
                        self._instance = None

            # Handle subprocess VLC
            if proc is not None and isinstance(proc, subprocess.Popen):
                try:
                    # Try to send quit command first
                    if hasattr(proc, "stdin") and proc.stdin:
                        try:
                            proc.stdin.write(b"q\n")
                            proc.stdin.flush()
                        except Exception:
                            pass  # Ignore if we can't write to stdin

                    # Check if process is running
                    if proc.poll() is None:
                        try:
                            if self._system == "Windows":
                                # Windows specific process termination
                                subprocess.call(
                                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)]
                                )
                            else:
                                # Unix/Mac termination with process group
                                try:
                                    # Try SIGTERM first
                                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

                                    # Wait briefly for termination (1 second max)
                                    for _ in range(10):
                                        if proc.poll() is not None:
                                            break  # Process ended
                                        time.sleep(0.1)

                                    # Force kill if still running
                                    if proc.poll() is None:
                                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                                except (ProcessLookupError, OSError) as e:
                                    # Process might have ended between checks
                                    print(f"Process already ended: {e}")
                        except Exception as e:
                            print(f"Error terminating process: {e}")
                    else:
                        print("Process already terminated")
                except Exception as e:
                    print(f"Error checking process status: {e}")

            # Always clear references regardless of cleanup success
            self._process = None
            self._playing = False

        except Exception as e:
            print(f"Unexpected error in stop_and_exit: {e}")

    @property
    def widget(self):
        """
        Returns the AudioPlayerWidget instance if one exists.

        Returns:
            AudioPlayerWidget or None: The audio player widget if it exists
        """
        if hasattr(self, "_player_widget") and self._player_widget:
            return self._player_widget
        return None

    def is_playing(self):
        """
        Check if media is currently playing.

        Returns:
            bool: True if media is currently playing, False otherwise
        """
        # Check if we're using AudioPlayerWidget
        if hasattr(self, "_player_widget") and self._player_widget:
            return self._player_widget.is_playing()

        # Otherwise check our own playing flag
        if not self._playing:
            return False

        # Then double-check with the player object if we have it
        if self._player and hasattr(self._player, "is_playing"):
            try:
                return self._player.is_playing()
            except Exception:
                pass

        # Default to our own tracking
        return self._playing

    def show_error_message(self, title, message):
        """
        Thread-safe method to emit the error signal or fall back to other methods
        """
        # Call the abort callback if set
        if self._abort_callback is not None:
            try:
                print("Calling abort callback to cancel measurement")
                self._abort_callback()
            except Exception as e:
                print(f"Error calling abort callback: {e}")

        # First try to emit the signal if available
        try:
            # Check if the signal exists AND we're running in a QApplication context
            if hasattr(self, "error_occurred") and hasattr(self.error_occurred, "emit"):
                print(f"Emitting error signal: {title}")
                self.error_occurred.emit(title, message)
                return
        except Exception as e:
            print(f"Error emitting signal: {e}")

        # If signal emission fails or signal doesn't exist, use QTimer directly
        if QApplication and QApplication.instance():
            try:
                print(f"Using QTimer to show dialog: {title}")
                QTimer.singleShot(200, lambda: self._display_dialog(title, message))
                return
            except Exception as e:
                print(f"Error scheduling with QTimer: {e}")

        # Final fallback: store message in settings for deferred display
        try:
            print(f"Using deferred message system: {title}")
            qs.set(
                "vlc_error_message",
                {
                    "title": title,
                    "text": message,
                },
            )
        except Exception as e:
            print(f"Error storing message: {e}")
            # Last resort, print to console
            print(f"ERROR: {title} - {message}")

    def _display_dialog(self, title, message):
        """Internal method to actually display the dialog"""
        try:
            QrewMessageBox.critical(None, title, message)
            print("Dialog shown successfully")
        except Exception as e:
            print(f"Failed to show dialog: {e}")
            # Fall back to deferred message system
            qs.set(
                "vlc_error_message",
                {
                    "title": title,
                    "text": message,
                },
            )

    # -------------------- helpers ------------------------------------
    @staticmethod
    def _find_vlc_exe() -> Optional[str]:
        """
        Comprehensive cross-platform VLC executable finder

        Returns:
            str: Path to VLC executable or 'vlc' if found in PATH
            None: If no VLC executable found
        """
        # Try PATH first (most reliable method)
        vlc_path = shutil.which("vlc")
        if vlc_path:
            return vlc_path

        system = platform.system()

        # Expanded macOS search paths
        if system == "Darwin":
            possible_paths = [
                "/Applications/VLC.app/Contents/MacOS/VLC",
                "/opt/homebrew/bin/vlc",
                "/usr/local/bin/vlc",
                "/Applications/VLC.app/Contents/MacOS/VLC.app/Contents/MacOS/VLC",
                os.path.expanduser("~/Applications/VLC.app/Contents/MacOS/VLC"),
                "/Applications/VLC.app/Contents/MacOS/VLC",
            ]

        # Expanded Windows search paths
        elif system == "Windows":
            possible_drives = ["C:", "D:"]
            possible_program_files = [
                os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
            ]
            possible_paths = []
            for drive in possible_drives:
                for pf in possible_program_files:
                    possible_paths.extend(
                        [
                            rf"{pf}\VideoLAN\VLC\vlc.exe",
                            rf"{drive}\Program Files\VideoLAN\VLC\vlc.exe",
                            rf"{drive}\Program Files (x86)\VideoLAN\VLC\vlc.exe",
                        ]
                    )

        # Expanded Linux search paths
        elif system == "Linux":
            possible_paths = [
                "/usr/bin/vlc",
                "/usr/local/bin/vlc",
                "/snap/bin/vlc",
                "/opt/vlc/bin/vlc",
                os.path.expanduser("~/.local/bin/vlc"),
            ]

        else:
            possible_paths = []

        # Additional PATH search
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        possible_paths.extend([os.path.join(path_dir, "vlc") for path_dir in path_dirs])

        # Check each possible path
        for p in possible_paths:
            # Expand user directory and normalize path
            full_path = os.path.abspath(os.path.expanduser(p))
            if os.path.exists(full_path) and os.access(full_path, os.X_OK):
                return full_path

        return None

    # -------------------- status -------------------------------------
    def is_playing(self) -> bool:
        return self._playing


# ----------------------------------------------------------------------
# Global player instance
_global_player = VLCPlayer()


def find_sweep_file(channel):
    """
    Locate the .mlp or .mp4 sweep file for the given channel in the stimulus_dir.
    Returns the full path if found, else None.
    Uses regex for precise matching with custom word boundaries.
    """
    if not Qrew_common.stimulus_dir or not os.path.isdir(Qrew_common.stimulus_dir):
        return None
    if "SW" in channel:
        channel = "LFE"
    # Custom pattern that treats common separators as boundaries
    # (?:^|[^A-Za-z0-9]) = start of string OR non-alphanumeric character
    # (?:[^A-Za-z0-9]|$) = non-alphanumeric character OR end of string
    pattern = r"(?:^|[^A-Za-z0-9])" + re.escape(channel) + r"(?:[^A-Za-z0-9]|$)"

    # First check for .mlp files (preferred format)
    for file in os.listdir(Qrew_common.stimulus_dir):
        if file.lower().endswith((".mlp", ".mp4", ".mp3", ".wav", ".flac")):
            if re.search(pattern, file, re.IGNORECASE):
                return os.path.join(Qrew_common.stimulus_dir, file)

    # If no match found
    return None


def play_sweep(channel, show_gui=True, backend="auto", on_finished=None):
    """
    Play the sweep file for the given channel.

    Args:
        channel: Channel name (e.g. "FL", "FR", "C", "LFE", etc.)
        show_gui: Whether to show the VLC GUI
        backend: Which backend to use ("libvlc", "subprocess", or "auto")
        on_finished: Callback to execute when playback ends

    Returns:
        bool: True if playback started successfully, False otherwise
    """
    sweep_file = find_sweep_file(channel)
    if not sweep_file:
        print(f"❌ No sweep file found for channel {channel}")

        # Store error message for deferred display
        qs.set(
            "vlc_error_message",
            {
                "title": "Sweep File Not Found",
                "text": f"No sweep file found for channel {channel} in {Qrew_common.stimulus_dir}",
            },
        )

        return False

    # Verify the file actually exists
    if not os.path.isfile(sweep_file):
        print(f"❌ Sweep file not found at path: {sweep_file}")

        # Store error message for deferred display
        qs.set(
            "vlc_error_message",
            {
                "title": "Sweep File Not Found",
                "text": f"Sweep file not found at path: {sweep_file}",
            },
        )

        return False

    try:
        # Check if we're running in a thread
        is_main_thread = False
        try:
            from PyQt5.QtCore import QThread
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            is_main_thread = app and app.thread() == QThread.currentThread()
            print(f"DEBUG: play_sweep called from main thread: {is_main_thread}")
        except ImportError:
            pass

        # Use provided backend or get from settings
        if backend == "auto":
            backend = qs.get("vlc_backend", "auto")

        # Use provided show_gui or get from settings
        if show_gui is None:
            show_gui = qs.get("show_vlc_gui", False)

        # Important thread-safety change: If called from a non-main thread,
        # we should initially create the player with GUI hidden, then show it
        # after a short delay to give it time to initialize safely
        show_gui_later = False

        if not is_main_thread and show_gui:
            print(
                "DEBUG: Running in worker thread, using two-phase GUI visibility for safety"
            )
            # Store original value to show GUI later
            show_gui_later = True
            # Set to False for initial playback to avoid thread-safety issues
            show_gui = False

        print(f"🎵 Playing sweep for {channel}: {os.path.basename(sweep_file)}")

        # First, attempt playback without showing GUI if from worker thread
        try:
            print(f"🚀 Starting playback with initial GUI visibility: {show_gui}")
            play_result = _global_player.play(
                path=sweep_file,
                show_gui=show_gui,
                backend=backend,
                on_finished=on_finished
                or (lambda: print(f"✅ Finished playing sweep for {channel}")),
            )

            if not play_result:
                print(f"⚠️ WARNING: Failed to start playback for {channel}")
                return False

            print(f"✅ Initial playback started successfully for {channel}")
        except Exception as play_error:
            print(f"❌ ERROR: Exception during play: {play_error}")
            return False

        # If this was called from a worker thread and GUI should be shown,
        # use a safe approach to schedule showing the GUI on the main thread
        if play_result and show_gui_later and not is_main_thread:
            print("DEBUG: Scheduling delayed GUI display for thread safety")
            try:
                # When called from a worker thread, we need to use a different approach
                # Instead of directly scheduling a timer, store a flag for the widget to check
                if hasattr(_global_player, "widget") and _global_player.widget:
                    print("DEBUG: Setting up deferred GUI show request")
                    # Set a flag on the widget that it should check during its normal update cycle
                    if hasattr(_global_player.widget, "_requested_visible"):
                        _global_player.widget._requested_visible = True
                        print(
                            "DEBUG: Successfully set visibility request flag on widget"
                        )

                    # If the widget has a method to handle visibility from main thread, use it
                    if hasattr(
                        _global_player.widget, "_ensure_visibility_from_main_thread"
                    ):
                        # This will be called from the main thread when the timer ticks
                        _global_player.widget._ensure_visibility_from_main_thread(True)
                        print("DEBUG: Requested visibility check on next UI cycle")
                else:
                    print("WARNING: No widget available to show GUI")

            except Exception as timer_err:
                print(f"ERROR: Could not schedule GUI display: {timer_err}")

        return play_result
    except Exception as e:
        print(f"❌ Playback failed: {e}")
        return False


def is_vlc_backend_locked():
    """
    Returns True if the VLC backend is locked to subprocess mode due to
    library loading or compatibility issues.

    This can be used by settings dialogs to disable the libvlc option.
    """
    return qs.get("vlc_backend_locked", False)


def get_available_backends():
    """
    Returns a list of available VLC backends.

    Returns:
        list: List of available backends ("libvlc", "subprocess")
    """
    backends = ["subprocess"]  # Always available

    if vlc_available and not is_vlc_backend_locked():
        backends.insert(0, "libvlc")

    return backends


def test_vlc_playback(test_file=None):
    """
    Test VLC playback with a test file or a default test sound.

    Args:
        test_file: Path to a test file, or None to use a default sweep file

    Returns:
        bool: True if playback was successful
    """
    print("🔍 Testing VLC playback...")

    # If no test file is provided, try to find a default sweep file
    if test_file is None:
        # Try to find any sweep file in the stimulus directory
        if Qrew_common.stimulus_dir and os.path.isdir(Qrew_common.stimulus_dir):
            for channel in ["C", "FL", "FR", "LFE"]:
                test_file = find_sweep_file(channel)
                if test_file:
                    print(f"Found test file for channel {channel}: {test_file}")
                    break

    # If we still don't have a test file, show an error
    if not test_file or not os.path.isfile(test_file):
        print("❌ No test file found. Please specify a valid audio file.")
        return False

    # Play the test file with GUI shown
    try:
        print(f"Playing test file: {os.path.basename(test_file)}")
        return _global_player.play(
            path=test_file,
            show_gui=True,
            backend="auto",
            on_finished=lambda: print("✅ Test playback complete"),
        )
    except Exception as e:
        print(f"❌ Test playback failed: {e}")
        return False
    """
    Test VLC playback functionality with a test file.

    Args:
        test_file: Path to test file. If None, uses a default test file.

    Returns:
        dict: Dictionary containing test results
    """
    results = {
        "vlc_available": vlc_available,
        "subprocess_available": False,
        "libvlc_test": False,
        "subprocess_test": False,
        "platform": platform.system(),
        "python_arch": "64-bit" if sys.maxsize > 2**32 else "32-bit",
    }

    # Test for VLC executable
    vlc_exe = VLCPlayer._find_vlc_exe()
    results["vlc_exe_path"] = vlc_exe
    results["subprocess_available"] = vlc_exe is not None

    # Use test file or look for a default one
    if not test_file:
        test_file = "example.mp4"  # Default test file name
        if Qrew_common.stimulus_dir and os.path.isdir(Qrew_common.stimulus_dir):
            for file in os.listdir(Qrew_common.stimulus_dir):
                if file.lower().endswith((".mp4", ".mp3", ".wav")):
                    test_file = os.path.join(Qrew_common.stimulus_dir, file)
                    break

    print(f"🔍 Testing VLC...")
    if vlc_exe:
        print(f"✅ VLC found at: {vlc_exe}")
    else:
        print("❌ VLC executable not found")

    if vlc_available:
        print("✅ python-vlc library available")
    else:
        print("⚠️ python-vlc library not available")

    print(f"🖥️ Platform: {results['platform']}")

    return results


def stop_vlc_and_exit():
    """stop vlc player either backend and kill process"""
    _global_player.stop_and_exit()


# For direct usage
if __name__ == "__main__":
    # Print diagnostics
    print("\nVLC Helper Diagnostics")
    print("-" * 50)

    # Test VLC functionality
    results = test_vlc_playback()

    print("\nAvailable backends:", get_available_backends())
    if is_vlc_backend_locked():
        print("⚠️ VLC backend is locked to subprocess mode")

    # Usage examples
    print("\nUsage Examples:")
    print("from qrew.Qrew_vlc_helper_v2 import _global_player as vlc_player")
    print("vlc_player.play('path/to/media.mp4', backend='auto')")
    print("# or")
    print("from qrew.Qrew_vlc_helper_v2 import play_sweep")
    print("play_sweep('FL', show_gui=True)")
