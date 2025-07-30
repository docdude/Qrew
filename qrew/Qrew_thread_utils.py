"""
Thread utility functions for Qrew application.
Provides common thread safety checks and operations.
"""

from PyQt5.QtCore import QThread, QTimer, pyqtSlot
from PyQt5.QtWidgets import QApplication


def is_main_thread():
    """
    Check if the current thread is the main/GUI thread.

    Returns:
        bool: True if on main thread, False otherwise
    """
    qapp = QApplication.instance()
    if qapp:
        return qapp.thread() == QThread.currentThread()
    return False


def run_on_main_thread(func, *args, **kwargs):
    """
    Execute a function on the main thread, either directly or via QTimer.

    Args:
        func: The function to execute
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
    """
    if is_main_thread():
        # Already on main thread, execute directly
        return func(*args, **kwargs)
    else:
        # Schedule execution on main thread
        QTimer.singleShot(0, lambda: func(*args, **kwargs))


def ensure_main_thread(func):
    """
    Decorator to ensure a method runs on the main thread.

    Usage:
        @ensure_main_thread
        def my_gui_method(self):
            # This will always run on main thread
            pass
    """

    def wrapper(self, *args, **kwargs):
        if is_main_thread():
            return func(self, *args, **kwargs)
        else:
            # Use QTimer to schedule on main thread
            QTimer.singleShot(0, lambda: func(self, *args, **kwargs))

    return wrapper


def disconnect_all_signals(obj, signal_names):
    """
    Safely disconnect all connections for the given signals.

    Args:
        obj: The object containing the signals
        signal_names: List of signal attribute names to disconnect
    """
    for signal_name in signal_names:
        if hasattr(obj, signal_name):
            try:
                signal = getattr(obj, signal_name)
                signal.disconnect()
            except TypeError:
                # No connections to disconnect
                pass
            except RuntimeError:
                # Object already deleted
                pass
