# Qrew_message_handlers.py
import numpy as np
import time
from flask import Flask, request, jsonify
from collections import deque
from threading import Event
from PyQt5.QtCore import QObject, pyqtSignal
from gevent.pywsgi import WSGIServer

try:
    from .Qrew_api_helper import get_last_error, get_last_warning
    from .Qrew_vlc_helper_v2 import play_sweep
except ImportError:
    from Qrew_api_helper import get_last_error, get_last_warning
    from Qrew_vlc_helper_v2 import play_sweep

status_log = deque(maxlen=100)


class MessageBridge(QObject):
    message_received = pyqtSignal(str)  # Regular status messages
    warning_received = pyqtSignal(str)  # Warning messages
    error_received = pyqtSignal(str)  # Error messages
    rta_distortion_received = pyqtSignal(dict)  # New signal for RTA data

    def emit_message(self, msg):
        print(f"MessageBridge: Emitting Message: {msg}")
        self.message_received.emit(msg)

    def emit_warning(self, warning):
        print(f"MessageBridge: Emitting Warning: {warning}")
        self.warning_received.emit(warning)

    def emit_error(self, error):
        print(f"MessageBridge: Emitting Error: {error}")
        self.error_received.emit(error)


# Global bridge instance
message_bridge = MessageBridge()


# Keep the same MeasurementCoordinator class
class MeasurementCoordinator:
    def __init__(self):
        self.event = Event()
        self.channel = None
        self.position = None
        self.status = None  # 'success', 'abort', 'error', 'timeout'
        self.error_message = None
        self.playback_requested = False

    def reset(self, channel, position):
        if isinstance(position, str):
            print(f"Coordinator: Reset to {channel}_{position}")
        else:
            print(f"Coordinator: Reset to {channel}_pos{position}")

        self.channel = channel
        self.position = position
        self.status = None
        self.error_message = None
        self.playback_requested = False
        self.event.clear()

    def trigger_playback(self):
        """Signal that it's time to play the sweep"""
        print(f"Coordinator: Triggering playback for {self.channel}_pos{self.position}")
        self.playback_requested = True

    def trigger_success(self):
        if isinstance(self.position, str):
            print(f"Coordinator: Triggered for {self.channel}_{self.position}")
        else:
            print(f"Coordinator: Triggered for {self.channel}_pos{self.position}")

        self.status = "success"
        self.error_message = None
        self.event.set()

    def trigger_abort(self, message=None):
        self.status = "abort"
        self.error_message = message
        self.event.set()

    def trigger_error(self, message=None):
        self.status = "error"
        self.error_message = message
        self.event.set()

    def trigger_timeout(self):
        self.status = "timeout"
        self.error_message = "Operation timed out"
        self.event.set()

    def wait_for_result(self, timeout=300):  # 5 minutes default
        if isinstance(self.position, str):
            print(f"Coordinator: Waiting for {self.channel}_{self.position}")
        else:
            print(f"Coordinator: Waiting for {self.channel}_pos{self.position}")

        result = self.event.wait(timeout)
        if not result:
            self.trigger_timeout()

        return self.status, self.error_message


# Global coordinator instance
coordinator = MeasurementCoordinator()


class RTAVerificationCoordinator:
    def __init__(self):
        self.collecting = False
        self.samples = []
        self.start_time = None
        self.target_duration = 10  # seconds
        self.min_samples = 20

    def start_collection(self, duration=10):
        """Start collecting RTA samples"""
        self.collecting = True
        self.samples = []
        self.start_time = time.time()
        self.target_duration = duration
        print(f"🎯 Starting RTA verification collection for {duration}s")

    def add_sample(self, rta_data):
        """Add RTA sample if collecting"""
        if not self.collecting:
            return

        # Skip samples with too few processed samples (settling)
        if rta_data.get("samples_processed", 0) < 50000:
            return

        elapsed = time.time() - self.start_time
        if elapsed <= self.target_duration:
            self.samples.append({"elapsed_time": elapsed, **rta_data})
            print(
                f"📊 RTA sample {len(self.samples)}: THD={rta_data.get('thd_percent', 0):.3f}%"
            )
        # Auto-stop when duration reached AND we have enough samples
        if elapsed >= self.target_duration and len(self.samples) >= self.min_samples:
            print(
                f"🏁 Auto-stopping RTA: {elapsed:.1f}s elapsed, {len(self.samples)} samples"
            )
            self.stop_collection()

    def stop_collection(self):
        """Stop collecting and return results"""
        if not self.collecting:
            return None

        self.collecting = False
        print(f"🏁 RTA collection complete: {len(self.samples)} samples")
        return self.analyze_samples()

    def analyze_samples(self):
        """Analyze collected RTA samples"""
        print(f"🔍 Analyzing {len(self.samples)} total samples")

        if len(self.samples) < self.min_samples:
            print(
                f"⚠️ Insufficient RTA samples: {len(self.samples)} < {self.min_samples}"
            )
            return None

        # Skip first 25% of samples (settling time)
        stable_start = len(self.samples) // 4
        stable_samples = self.samples[stable_start:]
        print(
            f"📈 Using {len(stable_samples)} stable samples (skipped first {stable_start})"
        )

        if not stable_samples:
            return None

        # Extract metrics
        thd_values = [s["thd_percent"] for s in stable_samples]
        thd_plus_n_values = [s["thd_plus_n_percent"] for s in stable_samples]
        snr_values = [s["snr_db"] for s in stable_samples]
        enob_values = [s["enob"] for s in stable_samples]
        imd_values = [s["imd_percent"] for s in stable_samples]

        return {
            "total_samples": len(self.samples),
            "stable_samples": len(stable_samples),
            "duration": self.samples[-1]["elapsed_time"] if self.samples else 0,
            "thd_mean": np.mean(thd_values),
            "thd_max": np.max(thd_values),
            "thd_std": np.std(thd_values),
            "thd_plus_n_mean": np.mean(thd_plus_n_values),
            "snr_mean": np.mean(snr_values),
            "snr_min": np.min(snr_values),
            "enob_mean": np.mean(enob_values),
            "imd_mean": np.mean(imd_values),
            "stability_good": np.std(thd_values) < 0.05,  # THD variation < 0.05%
            "signal_quality": (
                "excellent"
                if np.mean(snr_values) > 80
                else "good" if np.mean(snr_values) > 60 else "poor"
            ),
        }

    def is_collecting(self):
        """Check if currently collecting samples"""
        return self.collecting

    def get_sample_count(self):
        """Get current sample count"""
        return len(self.samples)


# Global RTA coordinator
rta_coordinator = RTAVerificationCoordinator()

# Flask server code
app = Flask(__name__)


# Server manager class to avoid global variables
class ServerManager:
    def __init__(self):
        self.http_server = None

    def stop(self, timeout=2.0):
        if self.http_server and not self.http_server.closed:
            print("🛑  Stopping REW-API server …")
            self.http_server.stop(timeout)
            self.http_server = None


# Create a singleton instance
server_manager = ServerManager()


@app.route("/rew-status", methods=["POST"])
def handle_status():
    msg = request.data.decode().strip('"')
    status_log.appendleft(msg)
    print(f"REW status update: {msg}")

    # Send messages directly via Qt signal (thread-safe)
    # Send messages directly via Qt signal (thread-safe)
    if "Capturing noise floor...100%" in msg:
        message_bridge.emit_message("Noise floor captured")
        # Trigger playback in the worker instead of playing here
        if coordinator.channel and coordinator.position is not None:
            print(f"Triggering playback for {coordinator.channel}")
            coordinator.trigger_playback()
            message_bridge.emit_message(
                f"Ready to play sweep for {coordinator.channel}"
            )

    elif "100% Measurement complete" in msg:
        if coordinator.channel and coordinator.position is not None:
            print(
                f"Triggering completion for {coordinator.channel}_pos{coordinator.position}"
            )
            coordinator.trigger_success()
            message_bridge.emit_message(
                f"Completed {coordinator.channel}_pos{coordinator.position}"
            )

    elif "Waiting for timing reference" in msg and "6%" in msg:
        message_bridge.emit_message("Waiting for timing reference...")

    elif "Remaining sweeps: 1" in msg and "8%" in msg:
        message_bridge.emit_message("Sweep in progress...")

    # Handle REW errors that might cause measurement to fail
    elif "Measurement aborted" in msg or "Measurement cancelled" in msg:
        # Handle measurement aborts
        coordinator.trigger_abort("Measurement was aborted")
        message_bridge.emit_error("Measurement aborted - will retry")

    elif any(
        error_phrase in msg.lower()
        for error_phrase in [
            "error",
            "failed",
            "timeout",
            "cannot",
            "unable",
            "invalid",
        ]
    ):
        if coordinator.channel and coordinator.position is not None:
            coordinator.trigger_error(f"REW error: {msg}")
            message_bridge.emit_error(f"REW error detected: {msg}")

    # Handle processing completion messages
    if "processName" in msg:
        if "Cross corr align" in msg:
            if "Completed" in msg:
                if coordinator.channel and coordinator.position == "cross_corr":
                    coordinator.trigger_success()
                    message_bridge.emit_message(
                        f"Cross correlation completed for {coordinator.channel}"
                    )
            elif "Failed" in msg or "Error" in msg:
                if coordinator.channel and coordinator.position == "cross_corr":
                    coordinator.trigger_error("Cross correlation failed")
                    message_bridge.emit_error(
                        f"Cross correlation failed for {coordinator.channel}"
                    )

        elif "Vector average" in msg:
            if "Completed" in msg:
                if coordinator.channel and coordinator.position == "vector_avg":
                    coordinator.trigger_success()
                    message_bridge.emit_message(
                        f"Vector averaging completed for {coordinator.channel}"
                    )
            elif "Failed" in msg or "Error" in msg:
                if coordinator.channel and coordinator.position == "vector_avg":
                    coordinator.trigger_error("Vector averaging failed")
                    message_bridge.emit_error(
                        f"Vector averaging failed for {coordinator.channel}"
                    )

    return "", 200


@app.route("/rew-result", methods=["POST"])
def handle_result():
    data = request.json
    print("Measurement result received:")
    print(data)
    return jsonify({"status": "received"}), 200


@app.route("/rew-status", methods=["GET"])
def show_last_status():
    log_html = "<br>".join(f'<div class="entry">{msg}</div>' for msg in status_log)
    return f"""
    <html>
    <head>
        <title>REW Live Status</title>
        <style>
            body {{ font-family: sans-serif; background: #f4f4f4; padding: 20px; }}
            h2 {{ color: #333; }}
            .log {{ background: #fff; padding: 15px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); height: 70vh; overflow-y: scroll; }}
            .entry {{ margin-bottom: 8px; font-size: 14px; }}
            .controls {{ margin-bottom: 15px; }}
            button {{ padding: 5px 10px; font-size: 14px; }}
        </style>
        <script>
            let autoRefresh = true;

            function toggleRefresh() {{
                autoRefresh = !autoRefresh;
                document.getElementById("toggleBtn").textContent = autoRefresh ? "Pause" : "Resume";
            }}

            function refreshLoop() {{
                if (autoRefresh) {{
                    window.location.reload();
                }} else {{
                    setTimeout(refreshLoop, 1000);
                }}
            }}

            setTimeout(refreshLoop, 1000);
        </script>
    </head>
    <body>
        <h2>REW Status Log (Live)</h2>
        <div class="controls">
            <button id="toggleBtn" onclick="toggleRefresh()">Pause</button>
        </div>
        <div class="log">
            {log_html}
        </div>
    </body>
    </html>
    """


@app.route("/rta-distortion", methods=["POST"])
def handle_rta_distortion():
    """Handle RTA distortion subscription updates"""
    try:
        rta_data = request.json
        if not rta_data:
            return "", 400
        # print(rta_data)
        # Process RTA data
        if isinstance(rta_data, list) and len(rta_data) > 0:
            # Take first channel if stereo
            distortion_data = rta_data[0]
        else:
            distortion_data = rta_data

        # Extract key metrics
        processed_data = {
            "timestamp": distortion_data.get("nanotime", 0),
            "samples_processed": distortion_data.get("totalSamplesProcessed", 0),
            "fundamental_freq": distortion_data.get("fundamentalFrequency", 0),
            "fundamental_dbfs": distortion_data.get("fundamentaldBFS", 0),
            "thd_percent": distortion_data.get("thd", {}).get("value", 0),
            "thd_plus_n_percent": distortion_data.get("thdPlusN", {}).get("value", 0),
            "snr_db": distortion_data.get("snrdB", 0),
            "enob": distortion_data.get("enob", 0),
            "imd_percent": distortion_data.get("imd", {}).get("value", 0),
            "gain_db": distortion_data.get("gaindB", 0),
            "harmonics": distortion_data.get("harmonics", []),
            "coherent_averaging": distortion_data.get("coherentAveraging", False),
            "averages": distortion_data.get("averages", 0),
        }

        # Send to Qt interface
        message_bridge.rta_distortion_received.emit(processed_data)

        print(
            f"RTA Update: THD={processed_data['thd_percent']:.3f}%, SNR={processed_data['snr_db']:.1f}dB, ENOB={processed_data['enob']:.1f}"
        )

        return "", 200

    except Exception as e:
        print(f"Error handling RTA distortion: {e}")
        return "", 500


@app.route("/rew-warnings", methods=["POST"])
def handle_warnings():
    """Handle REW warning notifications"""
    try:
        warning_data = request.json
        if not warning_data:
            return "", 400

        time_str = warning_data.get("time", "Unknown time")
        title = warning_data.get("title", "Unknown warning")
        message = warning_data.get("message", "No message")

        warning_msg = f"REW Warning: {title} - {message}"
        print(f"\nREW Warning [{time_str}]: {title} - {message}")
        status_log.appendleft(f"WARNING: {title} - {message}")

        # Send to Qt interface
        message_bridge.emit_warning(f"{warning_msg}")

        # Handle specific warnings that might affect measurements
        if any(
            keyword in title.lower()
            for keyword in ["signal-to-noise", "snr", "noise", "level", "clipping"]
        ):
            # These are measurement quality warnings - log but don't abort
            print(f"Measurement quality warning: {title}")

        elif any(
            keyword in title.lower()
            for keyword in ["timeout", "connection", "device", "hardware"]
        ):
            # These might indicate more serious issues
            print(f"Potential measurement issue: {title}")
            if coordinator.channel and coordinator.position is not None:
                # Don't automatically abort, but log for potential retry decision
                message_bridge.emit_warning(f"Warning may affect measurement: {title}")

        return "", 200

    except Exception as e:
        print(f"Error handling REW warning: {e}")
        return "", 500


@app.route("/rew-errors", methods=["POST"])
def handle_errors():
    """Handle REW error notifications"""
    try:
        error_data = request.json
        if not error_data:
            return "", 400

        time_str = error_data.get("time", "Unknown time")
        title = error_data.get("title", "Unknown error")
        message = error_data.get("message", "No message")

        error_msg = f"REW Error: {title} - {message}"
        print(f"REW Error [{time_str}]: {title} - {message}")
        status_log.appendleft(f"ERROR: {title} - {message}")

        # Send to Qt interface
        message_bridge.emit_error(error_msg)

        # Handle specific errors that should trigger retries
        if any(
            keyword in title.lower()
            for keyword in ["measurement", "capture", "recording", "input", "output"]
        ):
            # These are measurement-related errors - trigger retry
            if coordinator.channel and coordinator.position is not None:
                coordinator.trigger_error(f"REW Error: {title} - {message}")
                message_bridge.emit_error(
                    f"Measurement error detected, will retry: {title}"
                )

        elif any(
            keyword in title.lower()
            for keyword in [
                "processing",
                "analysis",
                "calculation",
                "vector",
                "correlation",
            ]
        ):
            # These are processing-related errors
            if coordinator.channel and coordinator.position in [
                "cross_corr",
                "vector_avg",
            ]:
                coordinator.trigger_error(f"REW Processing Error: {title} - {message}")
                message_bridge.emit_error(
                    f"Processing error detected, will retry: {title}"
                )

        else:
            # General errors - log but may not need retry
            print(f"General REW error: {title}")

        return "", 200

    except Exception as e:
        print(f"Error handling REW error: {e}")
        return "", 500


@app.route("/test-endpoints", methods=["GET"])
def test_endpoints():
    """Test endpoint to check REW warning/error subscription status"""
    try:
        # Check last warning
        last_warning = get_last_warning()
        # Check last error
        last_error = get_last_error()

        return f"""
        <html>
        <head><title>REW Endpoints Test</title></head>
        <body>
            <h2>REW Warning/Error Status</h2>
            <h3>Last Warning:</h3>
            <pre>{last_warning}</pre>
            <h3>Last Error:</h3>
            <pre>{last_error}</pre>
            <h3>Recent Status Log:</h3>
            <div>{'<br>'.join(list(status_log)[:10])}</div>
        </body>
        </html>
        """
    except Exception as e:
        return f"Error: {e}", 500


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify Flask server is running"""
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "qrew-flask-server",
                "timestamp": time.time(),
            }
        ),
        200,
    )


# ------------------------------------------------------------------
# public helper so other modules (MainWindow / signal handler) can
# shut the server down cleanly
# ------------------------------------------------------------------
def stop_flask_server(timeout: float = 2.0):
    """
    Ask gevent's WSGIServer to shut down and wait (≤ *timeout* s).
    Safe to call more than once.
    """
    # Use server_manager instead of global http_server
    server_manager.stop(timeout)


def run_flask_server():
    import logging

    # Production
    app.config["ENV"] = "production"
    app.config["DEBUG"] = False

    server_manager.http_server = WSGIServer(
        ("127.0.0.1", 5555),
        app,
        log=logging.getLogger("http_server"),
        error_log=logging.getLogger("http_server_error"),
    )
    print("✅  REW-API server listening on http://127.0.0.1:5555")
    server_manager.http_server.serve_forever()
