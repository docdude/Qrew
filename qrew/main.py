#!/usr/bin/env python3
"""
Main entry point for Qrew application
"""
import os
import sys
import time
import platform
import signal
import requests
from threading import Thread
from PyQt5.QtWidgets import QApplication

# Add the frozen application path for imports
if getattr(sys, "frozen", False):
    # Running as PyInstaller bundle
    application_path = sys._MEIPASS
    sys.path.insert(0, application_path)
    sys.path.insert(0, os.path.join(application_path, "qrew"))

# Force Windows to use IPv4 for all requests
if platform.system() == "Windows":
    import socket

    # import requests.packages.urllib3.util.connection as urllib3_cn  # this is for older versions
    import urllib3.util.connection as urllib3_cn

    def allowed_gai_family():
        """Force IPv4 only for Windows"""
        return socket.AF_INET  # Force IPv4 only

    urllib3_cn.allowed_gai_family = allowed_gai_family


try:
    # Try with qrew prefix first for PyInstaller bundles
    from qrew.Qrew import MainWindow, wait_for_rew_qt, shutdown_handler
    from qrew.Qrew_api_helper import initialize_rew_subscriptions
    from qrew.Qrew_message_handlers import run_flask_server, stop_flask_server
    from qrew.Qrew_styles import GLOBAL_STYLE, get_dark_palette, get_light_palette
    import qrew.Qrew_settings as qs
    from qrew.Qrew_messagebox import QrewMessageBox
except ImportError:
    try:
        # Try with direct imports for development mode
        from Qrew import MainWindow, wait_for_rew_qt, shutdown_handler
        from Qrew_api_helper import initialize_rew_subscriptions
        from Qrew_message_handlers import run_flask_server, stop_flask_server
        from Qrew_styles import GLOBAL_STYLE, get_dark_palette, get_light_palette
        import Qrew_settings as qs
        from Qrew_messagebox import QrewMessageBox
    except ImportError:
        try:
            # Try with relative imports as last resort
            from .Qrew import MainWindow, wait_for_rew_qt, shutdown_handler
            from .Qrew_api_helper import initialize_rew_subscriptions
            from .Qrew_message_handlers import run_flask_server, stop_flask_server
            from .Qrew_styles import GLOBAL_STYLE, get_dark_palette, get_light_palette
            from . import Qrew_settings as qs
            from Qrew_messagebox import QrewMessageBox
        except ImportError as e:
            print(f"Failed to import Qrew modules: {e}")
            print("Current sys.path:", sys.path)
            sys.exit(1)


def main():
    """Main application entry point"""
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


if __name__ == "__main__":
    main()
