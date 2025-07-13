"""
Qrew - Automated loudspeaker measurement system using REW API

This package provides a PyQt5-based GUI for automated speaker measurements
through the Room EQ Wizard (REW) API.
"""

__version__ = "1.0.0"
__author__ = "Juan F. Loya, MD"

# Import main components for easier access
from .Qrew import MainWindow
from .Qrew_api_helper import check_rew_connection, initialize_rew_subscriptions
from .Qrew_common import SPEAKER_LABELS, SPEAKER_CONFIGS

__all__ = [
    "MainWindow",
    "check_rew_connection", 
    "initialize_rew_subscriptions",
    "SPEAKER_LABELS",
    "SPEAKER_CONFIGS",
]
