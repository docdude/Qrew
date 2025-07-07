# Qrew_message_handlers.py
import requests
from flask import Flask, request, jsonify
from collections import deque
from threading import Event, Thread
from PyQt5.QtCore import QObject, pyqtSignal, QCoreApplication
from Qrew_api_helper import get_last_error, get_last_warning

from Qrew_vlc_helper import play_file, play_file_old, find_sweep_file
from Qrew_common import show_vlc_gui

status_log = deque(maxlen=100)

class MessageBridge(QObject):
    message_received = pyqtSignal(str)  # Regular status messages
    warning_received = pyqtSignal(str)  # Warning messages  
    error_received = pyqtSignal(str)    # Error messages
    
    def emit_message(self, msg):
        print(f"MessageBridge: Emitting message: {msg}")
        self.message_received.emit(msg)
    
    def emit_warning(self, warning):
        print(f"MessageBridge: Emitting warning: {warning}")
        self.warning_received.emit(warning)
    
    def emit_error(self, error):
        print(f"MessageBridge: Emitting error: {error}")
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

    def reset(self, channel, position):
        if isinstance(position, str): 
            print(f"Coordinator: Reset to {channel}_{position}")
        else: 
            print(f"Coordinator: Reset to {channel}_pos{position}")
           
        self.channel = channel
        self.position = position
        self.status = None
        self.error_message = None
        self.event.clear()

    def trigger_success(self):      
        if isinstance(self.position, str): 
            print(f"Coordinator: Triggered for {self.channel}_{self.position}")
        else: 
            print(f"Coordinator: Triggered for {self.channel}_pos{self.position}")    

        self.status = 'success'
        self.error_message = None
        self.event.set()

    def trigger_abort(self, message=None):
        self.status = 'abort'
        self.error_message = message
        self.event.set()

    def trigger_error(self, message=None):
        self.status = 'error'
        self.error_message = message
        self.event.set()

    def trigger_timeout(self):
        self.status = 'timeout'
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


# Flask server code 
app = Flask(__name__)

@app.route('/rew-status', methods=['POST'])
def handle_status():
    msg = request.data.decode().strip('"')
    status_log.appendleft(msg)
    print(f"REW status update: {msg}")

    # Send messages directly via Qt signal (thread-safe)
    if "Capturing noise floor...100%" in msg:
        message_bridge.emit_message("Noise floor captured")
        
    elif "100% Measurement complete" in msg:
        if coordinator.channel and coordinator.position is not None:
            print(f"Triggering completion for {coordinator.channel}_pos{coordinator.position}")
            coordinator.trigger_success()
            message_bridge.emit_message(f"Completed {coordinator.channel}_pos{coordinator.position}")
            
    elif "Waiting for timing reference" in msg and "6%" in msg:
        message_bridge.emit_message("Waiting for timing reference...")
        
    elif "Remaining sweeps: 1" in msg and "8%" in msg:
        message_bridge.emit_message("Sweep in progress...")
        
    # Handle REW errors that might cause measurement to fail
    elif "Measurement aborted" in msg or "Measurement cancelled" in msg:
        # Handle measurement aborts
        coordinator.trigger_abort("Measurement was aborted")
        message_bridge.emit_error("Measurement aborted - will retry")
        
    elif any(error_phrase in msg.lower() for error_phrase in [
        "error", "failed", "timeout", "cannot", "unable", "invalid"
    ]):
        if coordinator.channel and coordinator.position is not None:
            coordinator.trigger_error(f"REW error: {msg}")
            message_bridge.emit_error(f"REW error detected: {msg}")

    # Handle processing completion messages
    if "processName" in msg:
        if "Cross corr align" in msg:
            if "Completed" in msg:
                if coordinator.channel and coordinator.position == 'cross_corr':
                    coordinator.trigger_success()
                    message_bridge.emit_message(f"Cross correlation completed for {coordinator.channel}")
            elif "Failed" in msg or "Error" in msg:
                if coordinator.channel and coordinator.position == 'cross_corr':
                    coordinator.trigger_error("Cross correlation failed")
                    message_bridge.emit_error(f"Cross correlation failed for {coordinator.channel}")
                    
        elif "Vector average" in msg:
            if "Completed" in msg:
                if coordinator.channel and coordinator.position == 'vector_avg':
                    coordinator.trigger_success()
                    message_bridge.emit_message(f"Vector averaging completed for {coordinator.channel}")
            elif "Failed" in msg or "Error" in msg:
                if coordinator.channel and coordinator.position == 'vector_avg':
                    coordinator.trigger_error("Vector averaging failed")
                    message_bridge.emit_error(f"Vector averaging failed for {coordinator.channel}")

    # Play sweep file when needed
    if "100%" in msg and "Capturing noise floor" in msg:
        ch = coordinator.channel
        pos = coordinator.position
        if ch and pos is not None:
            sweep_file = find_sweep_file(ch)
            if sweep_file:
                print(f"Playing sweep file for {ch}: {sweep_file}")
                play_file(sweep_file, show_interface=show_vlc_gui)
                message_bridge.emit_message(f"Playing sweep for {ch}")



    return '', 200


@app.route('/rew-result', methods=['POST'])
def handle_result():
    data = request.json
    print("Measurement result received:")
    print(data)
    return jsonify({"status": "received"}), 200

@app.route('/rew-status', methods=['GET'])
def show_last_status():
    log_html = '<br>'.join(f'<div class="entry">{msg}</div>' for msg in status_log)
    return f'''
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
    '''


@app.route('/rew-warnings', methods=['POST'])
def handle_warnings():
    """Handle REW warning notifications"""
    try:
        warning_data = request.json
        if not warning_data:
            return '', 400
            
        time_str = warning_data.get('time', 'Unknown time')
        title = warning_data.get('title', 'Unknown warning')
        message = warning_data.get('message', 'No message')
        
        warning_msg = f'REW Warning: {title} - {message}'
        print(f"\nREW Warning [{time_str}]: {title} - {message}")
        status_log.appendleft(f"WARNING: {title} - {message}")
        
        # Send to Qt interface
        message_bridge.emit_warning(f"Warning: {warning_msg}")
        
        # Handle specific warnings that might affect measurements
        if any(keyword in title.lower() for keyword in [
            'signal-to-noise', 'snr', 'noise', 'level', 'clipping'
        ]):
            # These are measurement quality warnings - log but don't abort
            print(f"Measurement quality warning: {title}")
            
        elif any(keyword in title.lower() for keyword in [
            'timeout', 'connection', 'device', 'hardware'
        ]):
            # These might indicate more serious issues
            print(f"Potential measurement issue: {title}")
            if coordinator.channel and coordinator.position is not None:
                # Don't automatically abort, but log for potential retry decision
                message_bridge.emit_warning(f"Warning may affect measurement: {title}")
        
        return '', 200
        
    except Exception as e:
        print(f"Error handling REW warning: {e}")
        return '', 500

@app.route('/rew-errors', methods=['POST'])
def handle_errors():
    """Handle REW error notifications"""
    try:
        error_data = request.json
        if not error_data:
            return '', 400
            
        time_str = error_data.get('time', 'Unknown time')
        title = error_data.get('title', 'Unknown error')
        message = error_data.get('message', 'No message')
        
        error_msg = f"REW Error: {title} - {message}"
        print(f"REW Error [{time_str}]: {title} - {message}")
        status_log.appendleft(f"ERROR: {title} - {message}")
        
        # Send to Qt interface
        message_bridge.emit_error(error_msg)
        
        # Handle specific errors that should trigger retries
        if any(keyword in title.lower() for keyword in [
            'measurement', 'capture', 'recording', 'input', 'output'
        ]):
            # These are measurement-related errors - trigger retry
            if coordinator.channel and coordinator.position is not None:
                coordinator.trigger_error(f"REW Error: {title} - {message}")
                message_bridge.emit_error(f"Measurement error detected, will retry: {title}")
                
        elif any(keyword in title.lower() for keyword in [
            'processing', 'analysis', 'calculation', 'vector', 'correlation'
        ]):
            # These are processing-related errors
            if coordinator.channel and coordinator.position in ['cross_corr', 'vector_avg']:
                coordinator.trigger_error(f"REW Processing Error: {title} - {message}")
                message_bridge.emit_error(f"Processing error detected, will retry: {title}")
                
        else:
            # General errors - log but may not need retry
            print(f"General REW error: {title}")
            
        return '', 200
        
    except Exception as e:
        print(f"Error handling REW error: {e}")
        return '', 500

@app.route('/test-endpoints', methods=['GET'])
def test_endpoints():
    """Test endpoint to check REW warning/error subscription status"""
    try:
        # Check last warning
        last_warning = get_last_warning()
        # Check last error  
        last_error = get_last_error()
        
        return f'''
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
        '''
    except Exception as e:
        return f"Error: {e}", 500


def run_flask_server():
    app.run(host="0.0.0.0", port=5555, debug=False, use_reloader=False, threaded=True)