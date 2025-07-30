# vlc_player_widget.py
import sys
import pathlib
import vlc  # pip install python-vlc
from PyQt5.QtCore import (
    Qt,
    QTimer,
    QSize,
    pyqtSignal,
    QThread,
    pyqtSlot,
    QMetaObject,
    Q_ARG,
)
from PyQt5.QtGui import QIcon, QPalette, QColor, QPainter, QRadialGradient
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSlider,
    QDial,
    QLabel,
    QStyle,
)

try:
    from . import Qrew_resources
    from .Qrew_button import Button
    from .Qrew_styles import BUTTON_STYLES, load_high_quality_image
except ImportError:
    import Qrew_resources
    from Qrew_button import Button
    from Qrew_styles import BUTTON_STYLES, load_high_quality_image


class LimitedDial(QDial):
    """Custom QDial that truly limits rotation between min and max values"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWrapping(False)
        self._last_value = 0

    def wheelEvent(self, event):
        """Override wheel event to prevent wrapping"""
        # Get the current value
        current = self.value()

        # Calculate the change
        delta = event.angleDelta().y() / 120  # Standard wheel step
        new_value = current + delta * self.singleStep()

        # Clamp the value
        new_value = max(self.minimum(), min(self.maximum(), new_value))

        # Set the new value
        self.setValue(int(new_value))

        # Accept the event
        event.accept()

    def mousePressEvent(self, event):
        """Override to store the starting value"""
        self._last_value = self.value()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Override to prevent wrap-around when dragging"""
        # Let the parent handle the event first
        super().mouseMoveEvent(event)

        # Check if we've wrapped around
        current = self.value()

        # If we jumped from high to low or vice versa, restore the boundary value
        if abs(current - self._last_value) > (self.maximum() - self.minimum()) / 2:
            if self._last_value > (self.maximum() + self.minimum()) / 2:
                self.setValue(self.maximum())
            else:
                self.setValue(self.minimum())
        else:
            # Clamp the value to ensure it stays in range
            if current < self.minimum():
                self.setValue(self.minimum())
            elif current > self.maximum():
                self.setValue(self.maximum())

        self._last_value = self.value()


class GlowingDialWidget(QWidget):
    """Custom widget that contains a dial with a glowing background"""

    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None, glow_width=8):
        super().__init__(parent)
        self.dial = LimitedDial()
        self.dial.setRange(0, 125)
        self.dial.setValue(100)
        self.dial.setFixedSize(46, 46)
        self.dial.setNotchesVisible(True)
        self.dial.setNotchTarget(10.0)
        self.dial.setSingleStep(1)
        self.dial.setPageStep(5)

        # Connect dial signal to our signal
        self.dial.valueChanged.connect(self.valueChanged.emit)

        # Adjustable glow width
        self._glow_width = glow_width

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self._glow_width + 2,
            self._glow_width + 2,
            self._glow_width + 2,
            self._glow_width + 2,
        )  # Space for glow
        layout.addWidget(self.dial, 0, Qt.AlignCenter)

        # Set widget size based on dial size + glow
        dial_size = 46
        widget_size = dial_size + (self._glow_width * 2) + 4
        self.setFixedSize(widget_size, widget_size)

        # Current glow color
        self._glow_color = QColor("#263238")
        self._glow_intensity = 100.0  # Can be adjusted for brightness

    def value(self):
        return self.dial.value()

    def setValue(self, value):
        self.dial.setValue(value)

    def setGlowColor(self, color):
        """Set the glow color from hex string"""
        self._glow_color = QColor(color)
        self.update()  # Trigger repaint

    def setGlowWidth(self, width):
        """Adjust the glow width"""
        self._glow_width = width
        # Update margins
        self.layout().setContentsMargins(width + 2, width + 2, width + 2, width + 2)
        # Update widget size
        dial_size = 46
        widget_size = dial_size + (width * 2) + 4
        self.setFixedSize(widget_size, widget_size)
        self.update()

    def setGlowIntensity(self, intensity):
        """Set glow intensity (0.0 to 1.0)"""
        self._glow_intensity = max(0.0, min(100.0, intensity))
        self.update()

    def paintEvent(self, event):
        """Custom paint event to draw circular glow behind the dial"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate center of the widget
        center = self.rect().center()

        # Dial radius (half of dial size)
        dial_radius = 23

        # Draw multiple concentric circles for smooth glow effect
        glow_layers = 4  # Number of glow layers
        for i in range(glow_layers):
            # Calculate radius for this glow layer
            layer_progress = (i + 1) / glow_layers
            glow_radius = dial_radius + (self._glow_width * layer_progress)

            # Create radial gradient for this layer
            gradient = QRadialGradient(center, glow_radius)

            # Set gradient colors with transparency
            glow_color = QColor(self._glow_color)

            # Inner color (more opaque)
            inner_alpha = int(80 * self._glow_intensity * (1 - layer_progress * 0.7))
            glow_color.setAlpha(inner_alpha)
            gradient.setColorAt(0, glow_color)

            # Mid color
            mid_alpha = int(40 * self._glow_intensity * (1 - layer_progress * 0.7))
            glow_color.setAlpha(mid_alpha)
            gradient.setColorAt(0.5, glow_color)

            # Outer color (transparent)
            glow_color.setAlpha(0)
            gradient.setColorAt(1, glow_color)

            # Draw the glow circle
            painter.setBrush(gradient)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(center, int(glow_radius), int(glow_radius))

        # Call parent paint event to draw child widgets
        super().paintEvent(event)


class ClickableLabel(QLabel):
    """Custom QLabel that properly handles click events"""

    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)

    def mousePressEvent(self, event):
        """Override to emit clicked signal on left click"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def invoke_on_gui(obj, method_name, *args):
    """Call obj.method_name(*args) in the GUI thread, blocking."""
    QMetaObject.invokeMethod(
        obj,
        method_name,
        Qt.BlockingQueuedConnection,
        *[Q_ARG(type(a), a) for a in args],
    )


class AudioPlayerWidget(QMainWindow):
    """
    Stand-alone audio player window built on python-vlc.
    Controls are ALWAYS visible.  Use show_gui(True/False) to
    reveal or hide the whole window without destroying the player.
    """

    POLL_MS = 200  # UI refresh interval
    GLOW_WIDTH = 20  # Adjustable glow width (try values from 5 to 20)
    # Add signal for thread-safe GUI operations
    gui_visibility_requested = pyqtSignal(bool)
    play_requested = pyqtSignal()

    # Lifecycle signals for external modules
    player_closing = pyqtSignal()  # Emitted when player is about to close
    player_closed = pyqtSignal()  # Emitted after cleanup is complete
    playback_finished = pyqtSignal()  # Emitted when playback ends naturally

    # ------------------------------------------------------------------ init
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Qrew VLC Player")
        self.setWindowIcon(QIcon(":/assets/icons/Qrew_desktop_500x500.png"))

        # Don't delete on close - we want to reuse the widget
        # self.setAttribute(Qt.WA_DeleteOnClose)

        # --- VLC core ------------------------------------------------------
        self._vlc_instance = vlc.Instance(
            "--play-and-exit",
            "--network-caching=1000",
            "--no-interact",
            "--quiet",
            "--no-video",
        )
        self._player = self._vlc_instance.media_player_new()

        # We'll track the volume before muting to restore it when unmuting
        self._previous_volume = 100

        # Better mute state tracking
        self._is_muted = False

        # Track playback state
        self._playing = False
        self._cleanup_done = False  # Flag to indicate if we should clean up on close
        # Connect GUI visibility signal to handler
        self.gui_visibility_requested.connect(self._handle_gui_visibility)
        self.play_requested.connect(self._handle_play_request)
        self.playback_finished.connect(self._auto_close)

        self._build_ui()
        self._wire_signals()

        self._update_timer = None

        # Initialize the volume display with the correct colors
        self._player.audio_set_volume(100)
        self._player.audio_set_mute(False)
        self._is_muted = False
        self._update_volume_display(100)
        em = self._player.event_manager()
        em.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            lambda ev: QMetaObject.invokeMethod(
                self, "playback_finished", Qt.QueuedConnection
            ),
        )
        em.event_attach(
            vlc.EventType.MediaPlayerEncounteredError,
            lambda ev: QMetaObject.invokeMethod(
                self, "playback_finished", Qt.QueuedConnection
            ),
        )

    @pyqtSlot()
    def _auto_close(self):
        self.stop()  # stops timer & player
        self.cleanup()  # releases VLC objects
        self.close()  # destroys the window

    # --------------------------- public API
    @pyqtSlot(str)
    def open_media(self, source):
        """
        Load a file path or network URL (does NOT auto-play).
        source: Union[str, pathlib.Path]
        """
        # Reinitialize VLC if needed
        if not self.is_valid():
            print("DEBUG: VLC objects invalid, reinitializing")
            self.reinitialize()

        media = self._vlc_instance.media_new(str(source))
        self._player.set_media(media)

        # Try to use metadata title; fall back to file basename
        title = media.get_mrl()
        if title.startswith("file://"):
            title = pathlib.Path(source).name
        else:
            # strip scheme for http/https streams
            title = title.split("/")[-1]
        self.setWindowTitle(f"Qrew VLC Player – {title}")
        # Reset time labels
        self.time_label.setText("00:00")
        self.duration_label.setText("/ 00:00")

        # Reset volume display
        self._update_volume_display(self.volume_slider.value())

    @pyqtSlot()
    def _handle_play_request(self):
        """Handle play request from main thread"""
        print("DEBUG: _handle_play_request called on main thread")
        try:
            print("DEBUG: Starting VLC playback from main thread")
            result = self._player.play()
            if result == -1:
                print("ERROR: VLC player failed to start playback")
                self._playing = False
                return False

            self._playing = True
            print("DEBUG: Playback started successfully")
            self._ensure_timer_running()
            return True

        except (AttributeError, RuntimeError, ValueError, TypeError) as e:
            print(f"ERROR: Exception during playback start: {e}")
            self._playing = False
            return False

    def play(self):
        """Start playback - thread safe version"""
        print("DEBUG: AudioPlayerWidget.play() called")

        if not hasattr(self, "_player") or self._player is None:
            print("ERROR: Cannot play - VLC player object is missing")
            return False

        # Import thread utility
        try:
            from .Qrew_thread_utils import is_main_thread
        except ImportError:
            from Qrew_thread_utils import is_main_thread

        if is_main_thread():
            # We're on main thread, call directly
            print("DEBUG: On main thread, starting playback directly")
            return self._handle_play_request()
        else:
            # We're on worker thread, use signal
            print("DEBUG: On worker thread, using signal for playback")
            self.play_requested.emit()
            return True  # Assume success for now

    def _ensure_timer_running(self):
        """Start the update timer - simplified for main thread only"""
        if not self._update_timer:
            self._update_timer = QTimer(self)  # Set parent for proper cleanup
            self._update_timer.setInterval(self.POLL_MS)
            self._update_timer.timeout.connect(self._update_position)

        if not self._update_timer.isActive():
            self._update_timer.start()

    def pause(self):
        """Pause playback of the loaded media."""
        self._player.pause()
        self._playing = False

    def stop(self):
        """
        Stop playback of the loaded media.
        """
        # First stop the timer to prevent any callbacks during cleanup
        if hasattr(self, "_update_timer") and self._update_timer is not None:
            self._update_timer.stop()

        # Now stop the player
        if hasattr(self, "_player") and self._player is not None:
            self._player.stop()

        # Reset UI
        self.position_slider.setValue(0)
        self._playing = False

    def show_gui(self, show: bool):
        """
        Request GUI visibility change - thread safe version
        """
        print(f"DEBUG: show_gui({show}) called")

        # Check if we're on the main thread
        qapp = QApplication.instance()
        if qapp and qapp.thread() == QThread.currentThread():
            # We're on main thread, call directly
            print("DEBUG: On main thread, calling GUI operations directly")
            self._handle_gui_visibility(show)
        else:
            # We're on worker thread, use signal
            print("DEBUG: On worker thread, using signal for GUI operations")
            self.gui_visibility_requested.emit(show)

    @pyqtSlot(bool)
    def _handle_gui_visibility(self, show):
        """Actually show/hide the widget - only called from main thread"""
        print(f"DEBUG: _handle_gui_visibility({show}) called on main thread")
        try:
            if show:
                if not self.isVisible():
                    self.show()
                    print("DEBUG: Player window shown")
                self.raise_()
                self.activateWindow()
            else:
                if self.isVisible():
                    self.hide()
                    print("DEBUG: Player window hidden")
        except (RuntimeError, AttributeError, TypeError, ValueError) as e:
            print(f"ERROR: Failed to change GUI visibility: {e}")

    def is_playing(self):
        """
        Returns True if the player is currently playing media.
        """
        if self._player and hasattr(self._player, "is_playing"):
            return self._player.is_playing() == 1
        return False

    def request_cleanup(self):
        """
        Request cleanup from external modules - safe to call from any thread.
        This will stop playback, cleanup resources, and hide the window.
        """
        print("DEBUG: Cleanup requested from external module")

        # First, immediately stop playback regardless of thread
        try:
            if self._player:
                self._player.stop()
                print("DEBUG: Stopped VLC playback")
        except Exception as e:
            print(f"DEBUG: Error stopping playback: {e}")

        # If we're already on the main thread, perform cleanup directly
        qapp = QApplication.instance()
        if qapp and qapp.thread() == QThread.currentThread():
            print("DEBUG: On main thread, performing cleanup directly")
            self.cleanup()
            # Hide the window instead of closing/deleting it
            self.close()
        else:
            # If on a worker thread, use QTimer to execute on main thread
            print("DEBUG: On worker thread, scheduling immediate cleanup")
            QMetaObject.invokeMethod(self, "_do_cleanup_and_close", Qt.QueuedConnection)

    @pyqtSlot()
    def _do_cleanup_and_close(self):
        self.cleanup()
        self.close()  # or self.close() if you prefer the widget to disappear

    def shutdown(self):
        """
        Graceful shutdown method for external modules.
        This will stop playback, cleanup resources, and close the window.
        """
        print("DEBUG: Shutdown requested")

        try:
            # Stop playback first
            if self.is_playing():
                print("DEBUG: Stopping active playback before shutdown")
                self.stop()

            # Perform cleanup
            self.cleanup()

            # Close the window
            self.close()

        except Exception as e:
            print(f"ERROR: Error during shutdown: {e}")
            # Force cleanup even if there was an error
            try:
                self.cleanup()
            except Exception as cleanup_error:
                print(f"ERROR: Error during forced cleanup: {cleanup_error}")

    def get_player(self):
        """
        Returns the VLC media player instance.
        """
        return self._player

    def get_vlc_instance(self):
        """
        Returns the VLC instance.
        """
        return self._vlc_instance

    def is_valid(self):
        """
        Check if the widget has valid VLC objects.
        """
        return (
            hasattr(self, "_player")
            and self._player is not None
            and hasattr(self, "_vlc_instance")
            and self._vlc_instance is not None
        )

    def reinitialize(self):
        """
        Reinitialize VLC objects if they were cleaned up.
        """
        if not self.is_valid():
            print("DEBUG: Reinitializing VLC objects")
            # Create new VLC instance and player
            self._vlc_instance = vlc.Instance(
                "--play-and-exit",
                "--network-caching=1000",
                "--no-interact",
                "--quiet",
                "--no-video",
            )
            self._player = self._vlc_instance.media_player_new()
            # Reset state flags
            self._playing = False
            self._is_muted = False
            print("DEBUG: VLC objects reinitialized")

    # ------------------------------------------------------------------ internals
    def _build_ui(self):
        """Build the main UI layout for the audio player."""
        self._video_stub = QLabel()
        self._video_stub.setFixedHeight(80)  # give it some real estate
        self._video_stub.setAlignment(Qt.AlignCenter)
        self._video_stub.setStyleSheet("background:black")
        # Default pixmap (app icon) – replace path with your icon file
        self.bg_source = load_high_quality_image(
            ":/assets/icons/Qrew_desktop_500x500.png", scale_to=(80, 80)
        )
        if self.bg_source:
            self._video_stub.setPixmap(self.bg_source)

        # transport buttons
        self.play_btn = Button(self.style().standardIcon(QStyle.SP_MediaPlay), "")
        self.pause_btn = Button(self.style().standardIcon(QStyle.SP_MediaPause), "")
        self.stop_btn = Button(self.style().standardIcon(QStyle.SP_MediaStop), "")

        # Make buttons more compact and VLC-like
        for btn in [self.play_btn, self.pause_btn, self.stop_btn]:
            btn.setStyleSheet(BUTTON_STYLES["secondary"])

        # Position slider with VLC-style look
        self.position_slider = QSlider(Qt.Horizontal, minimum=0, maximum=1000)
        self.position_slider.setStyleSheet(
            """
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 6px;
                background: #4a4a4a;
                margin: 2px 0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00a2ff;
                border: 1px solid #5c5c5c;
                width: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #00a2ff;
                border-radius: 3px;
            }
        """
        )

        # Time labels
        self.time_label = QLabel("00:00")
        self.time_label.setStyleSheet("color: #616161;")
        self.duration_label = QLabel("/ 00:00")
        self.duration_label.setStyleSheet("color: #616161;")

        # Use our custom glowing dial widget with adjustable glow
        self.volume_slider_widget = GlowingDialWidget(glow_width=self.GLOW_WIDTH)
        self.volume_slider = self.volume_slider_widget.dial

        # You can adjust these values to experiment with different looks:
        # self.volume_slider_widget.setGlowWidth(15)  # Try values from 5 to 20
        # self.volume_slider_widget.setGlowIntensity(0.8)  # Try values from 0.3 to 1.0

        # Style the dial to look like VLC's volume control
        self.volume_slider.setStyleSheet(
            """
            QDial {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 23px;
            }
            QDial::handle {
                background-color: #4adc05;
                border: 2px solid white;
                border-radius: 4px;
                width: 8px;
                height: 8px;
            }
            """
        )

        # Add volume percentage label with proper click handling
        self.volume_percent = ClickableLabel("100%")
        self.volume_percent.setFixedWidth(32)
        self.volume_percent.setStyleSheet("color: #cccccc; font-size: 9px;")
        self.volume_percent.setAlignment(Qt.AlignCenter)
        self.volume_percent.setCursor(Qt.PointingHandCursor)

        # Volume icon with mute/unmute capability
        self.volume_icon = ClickableLabel("🔊")
        self.volume_icon.setStyleSheet("color: #cccccc; font-size: 14px;")
        self.volume_icon.setCursor(Qt.PointingHandCursor)

        # Create nested layouts for better organization
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.pause_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addSpacing(5)

        # Position layout with time labels
        position_layout = QHBoxLayout()
        position_layout.addWidget(self.time_label)
        position_layout.addWidget(self.position_slider, 1)  # 1 = stretch factor
        position_layout.addWidget(self.duration_label)

        # Create a vertical layout for the volume dial and percentage
        dial_layout = QVBoxLayout()
        dial_layout.setContentsMargins(0, 0, 0, 0)
        dial_layout.setSpacing(0)
        dial_layout.addWidget(self.volume_slider_widget, 0, Qt.AlignCenter)
        dial_layout.addWidget(self.volume_percent, 0, Qt.AlignCenter)

        # Volume layout with icon and dial in a compact layout
        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(3)
        volume_layout.addWidget(self.volume_icon)
        volume_layout.addLayout(dial_layout)

        # Main control layout
        ctrl = QHBoxLayout()
        ctrl.addLayout(controls_layout)
        ctrl.addLayout(position_layout, 1)  # 1 = stretch factor
        ctrl.addLayout(volume_layout)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self._video_stub)  # Video stub for VLC surface
        layout.addLayout(ctrl)
        self.setCentralWidget(root)

    def _wire_signals(self):
        self.play_btn.clicked.connect(self.play)
        self.pause_btn.clicked.connect(self.pause)
        self.stop_btn.clicked.connect(self.stop)

        self.position_slider.sliderMoved.connect(self._set_position)
        self.volume_slider_widget.valueChanged.connect(self._set_volume)

        # Connect click signals
        self.volume_icon.clicked.connect(self._toggle_mute)
        self.volume_percent.clicked.connect(self._toggle_mute)

    def closeEvent(self, event):
        """Handle window close event by cleaning up resources."""
        print("DEBUG: AudioPlayerWidget closeEvent called")

        # Emit signal to notify other modules that player is closing
        try:
            self.player_closing.emit()
        except (RuntimeError, AttributeError) as e:
            print(f"Warning: Could not emit player_closing signal: {e}")

        # Perform cleanup
        self.cleanup()

        # Emit signal to notify cleanup is complete
        try:
            self.player_closed.emit()
        except (RuntimeError, AttributeError) as e:
            print(f"Warning: Could not emit player_closed signal: {e}")

        # Accept the close event
        event.accept()

    # super().closeEvent(event)

    def cleanup(self):
        """Clean up all resources properly to avoid memory leaks."""
        print("DEBUG: AudioPlayerWidget cleanup() called")

        # Don't skip cleanup - always reset state for potential reuse
        # This allows the widget to be reused for the next measurement

        try:
            # First stop the timer to prevent any callbacks during cleanup
            if hasattr(self, "_update_timer") and self._update_timer is not None:
                print("DEBUG: Stopping update timer")
                try:
                    self._update_timer.stop()
                    self._update_timer.deleteLater()
                    self._update_timer = None
                except (RuntimeError, AttributeError) as e:
                    print(f"Warning: Error stopping timer: {e}")

            # Stop and cleanup the player
            if hasattr(self, "_player") and self._player is not None:
                print("DEBUG: Cleaning up VLC player")
                try:
                    # Stop playback if active
                    if self._player.is_playing():
                        print("DEBUG: Stopping active playback")
                        self._player.stop()

                    # Release the player
                    print("DEBUG: Releasing VLC player")
                    self._player.release()
                    self._player = None
                except (RuntimeError, AttributeError, ValueError) as e:
                    print(f"Error releasing player: {e}")

            # Release the VLC instance
            if hasattr(self, "_vlc_instance") and self._vlc_instance is not None:
                print("DEBUG: Releasing VLC instance")
                try:
                    self._vlc_instance.release()
                    self._vlc_instance = None
                except Exception as e:
                    print(f"Error releasing VLC instance: {e}")

            # Reset state variables
            self._playing = False
            self._is_muted = False

            # Don't set _cleanup_done flag - allow reuse
            print("DEBUG: Cleanup completed successfully - widget ready for reuse")

        except Exception as e:
            print(f"ERROR: Unexpected error during cleanup: {e}")

    def _set_position(self, value):
        self._player.set_position(value / 1000.0)

    def _set_volume(self, value):
        # Always remember previous non-zero volume
        if value > 0:
            self._previous_volume = value
            # If we're setting a non-zero volume, we're not muted
            self._is_muted = False
            self._player.audio_set_mute(False)
        elif value == 0:
            # Volume 0 means muted
            self._is_muted = True
            self._player.audio_set_mute(True)

        # Set the VLC volume (note: VLC accepts 0-100)
        actual_volume = min(100, value)  # Cap at 100 for VLC
        self._player.audio_set_volume(actual_volume)

        # Force update visual elements immediately
        self._update_volume_display(value)

    def _update_volume_display(self, value):
        # Update volume percentage
        self.volume_percent.setText(f"{value}%")

        # Get color based on volume level
        color = self._get_volume_color(value)

        # Update glow color
        self.volume_slider_widget.setGlowColor(color)

        # Adjust glow intensity based on volume (optional)
        if value > 100:
            # Increase glow intensity for volumes over 100%
            intensity = 0.6 + (value - 100) / 100 * 0.4  # 0.6 to 1.0
            self.volume_slider_widget.setGlowIntensity(intensity)
        else:
            # Normal glow for regular volumes
            self.volume_slider_widget.setGlowIntensity(0.7)

        # If muted or volume is 0, show muted state
        if self._is_muted or value == 0:
            self.volume_percent.setStyleSheet("color: #999999; font-size: 9px;")
            self.volume_slider.setStyleSheet(
                """
                QDial {
                    background-color: #2a2a2a;
                    border: 1px solid #3a3a3a;
                    border-radius: 23px;
                }
                QDial::handle {
                    background-color: #999999;
                    border: 2px solid #dddddd;
                    border-radius: 4px;
                    width: 8px;
                    height: 8px;
                }
                """
            )
            self.volume_icon.setText("🔇")
        elif value > 100:
            # Make the percentage text match the color for volumes over 100%
            self.volume_percent.setStyleSheet(
                f"color: {color}; font-size: 9px; font-weight: bold;"
            )

            # Enhanced dial for volumes over 100%
            self.volume_slider.setStyleSheet(
                f"""
                QDial {{
                    background-color: #2a2a2a;
                    border: 1px solid #3a3a3a;
                    border-radius: 23px;
                }}
                QDial::handle {{
                    background-color: {color};
                    border: 2px solid white;
                    border-radius: 4px;
                    width: 10px;
                    height: 10px;
                }}
                """
            )
            self.volume_icon.setText(self._get_volume_icon(value))
        else:
            # Apply gradient color to percentage label for volumes <= 100%
            self.volume_percent.setStyleSheet(f"color: {color}; font-size: 9px;")

            # Apply gradient color for normal volumes
            self.volume_slider.setStyleSheet(
                f"""
                QDial {{
                    background-color: #2a2a2a;
                    border: 1px solid #3a3a3a;
                    border-radius: 23px;
                }}
                QDial::handle {{
                    background-color: {color};
                    border: 2px solid white;
                    border-radius: 4px;
                    width: 8px;
                    height: 8px;
                }}
                """
            )
            self.volume_icon.setText(self._get_volume_icon(value))

    def _get_volume_icon(self, value):
        """Get the appropriate volume icon based on volume level."""
        if self._is_muted or value <= 0:
            return "🔇"
        elif value < 30:
            return "🔈"
        elif value < 70:
            return "🔉"
        else:
            return "🔊"

    def _get_volume_color(self, value):
        """Get the appropriate color for volume level."""
        if self._is_muted or value <= 0:
            return "#263238"  # Gray for muted or zero volume

        elif value <= 100:
            # Enhanced green gradient heatmap for normal volume
            # We'll create a gradient from dark green to bright green

            # Map volume 0-100 to color intensity
            ratio = value / 100.0

            # Start with dark green and transition to bright green
            # Using HSL-inspired calculations for smoother gradients
            if value < 25:
                # Very dark green to dark green
                red = int(20 + (value / 25) * 30)
                green = int(80 + (value / 25) * 40)
                blue = int(10 + (value / 25) * 10)
            elif value < 50:
                # Dark green to medium green
                red = int(50 + ((value - 25) / 25) * 24)
                green = int(120 + ((value - 25) / 25) * 50)
                blue = int(20 + ((value - 25) / 25) * 10)
            elif value < 75:
                # Medium green to bright green
                red = int(74 + ((value - 50) / 25) * 40)
                green = int(170 + ((value - 50) / 25) * 50)
                blue = int(30 + ((value - 50) / 25) * 10)
            else:
                # Bright green to very bright green
                red = int(114 + ((value - 75) / 25) * 40)
                green = int(220 + ((value - 75) / 25) * 35)
                blue = int(40 + ((value - 75) / 25) * 20)

            # Ensure values stay within valid range
            red = min(255, max(0, red))
            green = min(255, max(0, green))
            blue = min(255, max(0, blue))

            return f"#{red:02x}{green:02x}{blue:02x}"

        elif value <= 105:
            return "#ffd500"  # Light orange
        elif value <= 112:
            return "#ff8c00"  # Darker orange
        elif value <= 120:
            return "#ff2200"  # Very dark orange
        else:
            return "#ff0000"  # Red

    def _toggle_mute(self):
        """Toggle between muted and unmuted states."""
        if self._is_muted or self.volume_slider.value() == 0:
            # Unmute
            self._is_muted = False
            self._player.audio_set_mute(False)

            # Restore previous volume
            if self._previous_volume <= 0:
                self._previous_volume = 50

            self.volume_slider.setValue(self._previous_volume)

            # Set VLC volume
            actual_volume = min(100, self._previous_volume)
            self._player.audio_set_volume(actual_volume)

            # Update display
            self._update_volume_display(self._previous_volume)
        else:
            # Mute
            current_volume = self.volume_slider.value()
            if current_volume > 0:
                self._previous_volume = current_volume

            self._is_muted = True
            self._player.audio_set_mute(True)
            self.volume_slider.setValue(0)

            # Update display
            self._update_volume_display(0)

    def _update_position(self):
        """Update UI elements based on playback position"""
        try:
            # First check if player still exists
            if not hasattr(self, "_player") or self._player is None:
                if hasattr(self, "_update_timer") and self._update_timer.isActive():
                    print("DEBUG: Stopping timer because player is gone")
                    self._update_timer.stop()
                return

            # Check if player is still playing
            try:
                is_playing = self._player.is_playing()
            except (AttributeError, ValueError, RuntimeError) as e:
                print(f"ERROR: Exception checking playback status: {e}")
                is_playing = False

            if is_playing:
                try:
                    # Update position slider
                    pos = int(self._player.get_position() * 1000)
                    self.position_slider.blockSignals(True)
                    self.position_slider.setValue(pos)
                    self.position_slider.blockSignals(False)
                except (AttributeError, ValueError, RuntimeError, TypeError) as e:
                    print(f"Error updating slider position: {e}")

                try:
                    # Update time labels
                    current_ms = self._player.get_time()
                    duration_ms = self._player.get_length()

                    # Format time as MM:SS
                    if current_ms >= 0:
                        mins, secs = divmod(current_ms // 1000, 60)
                        current_str = f"{mins:02d}:{secs:02d}"
                        self.time_label.setText(current_str)

                    if duration_ms > 0:
                        mins, secs = divmod(duration_ms // 1000, 60)
                        duration_str = f"/ {mins:02d}:{secs:02d}"
                        self.duration_label.setText(duration_str)
                except (AttributeError, ValueError, TypeError, RuntimeError) as e:
                    print(f"Error updating time labels: {e}")

        except (AttributeError, ValueError, TypeError, RuntimeError) as e:
            print(f"ERROR: Error in _update_position: {e}")
            # Safety - stop the timer to prevent further errors
            try:
                if hasattr(self, "_update_timer") and self._update_timer.isActive():
                    print("DEBUG: Stopping timer due to error")
                    self._update_timer.stop()
            except RuntimeError as stop_error:
                print(f"ERROR: Failed to stop timer: {stop_error}")


# ---------------------------------------------------------------------- demo
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Instantiate but DON'T show yet
    player = AudioPlayerWidget()
    player.setFixedSize(600, 210)
    player.setStyleSheet("background-color: #263238;")  # Dark background

    # Load a file programmatically (replace with your own)
    #   player.open_media(
    #      r"C:\Users\jloya.LAFE\Downloads\REW Files\AudysseyX\Optimal Atmos Sweeps 256k (+4.5dB)\C.mp4"
    # )
    player.play()

    # Or just show the GUI and let user operate it
    player.show_gui(True)

    sys.exit(app.exec_())

# -----
