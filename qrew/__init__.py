"""
Qrew - Automated loudspeaker measurement system using REW API

This package provides a PyQt5-based GUI for automated speaker measurements
through the Room EQ Wizard (REW) API.
"""

__version__ = "1.0.0"
__author__ = "Juan F. Loya"

# Import main components for easier access
from .Qrew import MainWindow, shutdown_handler, wait_for_rew_qt
from .Qrew_api_helper import check_rew_connection, initialize_rew_subscriptions
from .Qrew_message_handlers import run_flask_server, stop_flask_server
from .Qrew_styles import GLOBAL_STYLE, get_dark_palette, get_light_palette
from .Qrew_messagebox import QrewMessageBox
from . import Qrew_settings as qs
from . import Qrew_common

__all__ = [
    "MainWindow",
    "shutdown_handler",
    "wait_for_rew_qt",
    "check_rew_connection",
    "initialize_rew_subscriptions",
    "run_flask_server",
    "stop_flask_server",
    "GLOBAL_STYLE",
    "get_dark_palette",
    "get_light_palette",
    "QrewMessageBox",
    "qs",
    "Qrew_common",
]
