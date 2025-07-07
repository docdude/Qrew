# Qrew_workers.py

from PyQt5.QtCore import QThread, pyqtSignal, QTimer

from Qrew_api_helper import (start_capture, get_all_measurements, start_cross_corr_align, start_vector_avg, get_vector_average_result,  rename_measurement, 
                             get_measurement_by_uuid, get_measurement_distortion_by_uuid, get_measurement_uuid )
from Qrew_message_handlers import coordinator

from Qrew_measurement_metrics import evaluate_measurement

from Qrew_dialogs import SettingsDialog

class MeasurementWorker(QThread):
    """Worker thread for handling measurements with error recovery"""
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str)
    finished = pyqtSignal()
    show_position_dialog = pyqtSignal(int)
    continue_signal = pyqtSignal()
    grid_flash_signal = pyqtSignal(bool)  # Add signal for grid flash
    grid_position_signal = pyqtSignal(int)  # Add signal for grid position
    metrics_update = pyqtSignal(dict)  # Add signal for metrics
    show_quality_dialog = pyqtSignal(dict)  # Add this signal

    def __init__(self, measurement_state, parent_window=None):
        super().__init__()
        self.measurement_state = measurement_state
        self.parent_window = parent_window  # Add parent window reference

        self.running = True
        self.continue_signal.connect(self.continue_measurement)
        self.max_retries = 3
        self.current_retry = 0
        self.check_timer = None  # Add timer reference

    def run(self):
        self.continue_measurement()
        self.exec_()
       
    def continue_measurement(self):
        if not self.running:
            return
            
        state = self.measurement_state

        # Handle repeat mode first
        if state.get('repeat_mode', False):
            return self.handle_repeat_mode()  
          
        # Get initial count only once at the very beginning
        if state['initial_count'] == -1:
            _, count = get_all_measurements()
            if count == -1:
                self.status_update.emit("Failed to connect to REW API.")
                state['running'] = False
                self.finished.emit()
                self.quit()
                return
            state['initial_count'] = count
        
        pos = state['current_position']
        
        # Check if we've done all channels for this position
        if state['channel_index'] >= len(state['channels']):
            state['channel_index'] = 0
            state['current_position'] += 1
            self.current_retry = 0  # Reset retry count for new position
            
            if state['current_position'] < state['num_positions']:
                self.show_position_dialog.emit(state['current_position'])
            else:
                self.status_update.emit("All samples complete!")
                state['running'] = False
                self.grid_flash_signal.emit(False)  # Turn off flash
                self.finished.emit()
                self.quit()
            return
        
        # Process current channel
        ch = state['channels'][state['channel_index']]
        sample_name = f"{ch}_pos{pos}"
        
        # Update grid to show current position and start flash
        self.grid_position_signal.emit(pos)
        self.grid_flash_signal.emit(True)
        
        retry_msg = f" (Retry {self.current_retry + 1}/{self.max_retries})" if self.current_retry > 0 else ""
        self.status_update.emit(f"Starting measurement for {sample_name}{retry_msg}...")
        
        # Reset coordinator and start measurement
        coordinator.reset(ch, pos)
        
        success, error_msg = start_capture(
            ch, pos, 
            status_callback=self.status_update.emit,
            error_callback=self.error_occurred.emit
        )
        
        if not success:
            self.status_update.emit(f"Failed to start capture for {sample_name}")
            self.handle_measurement_failure("Failed to start capture")
            return

        # Start checking for completion with improved timing
        self.start_completion_check()

    def handle_repeat_mode(self):
        """Handle repeat measurement mode logic"""
        state = self.measurement_state
        
        # Check if we have more pairs to remeasure
        if not state.get('remeasure_pairs'):
            self.status_update.emit("All remeasurements complete!")
            state['running'] = False
            self.grid_flash_signal.emit(False)
            self.finished.emit()
            self.quit()
            return
        
        # If we don't have a current pair or we finished the current one, get the next
        if not state.get('current_remeasure_pair') or state.get('pair_completed', False):
            next_pair = state['remeasure_pairs'].pop(0)
            channel, position = next_pair
            
            state['current_remeasure_pair'] = next_pair
            state['channels'] = [channel]
            state['current_position'] = position
            state['channel_index'] = 0
            state['pair_completed'] = False

            # Stop any current flashing before showing position dialog
            self.grid_flash_signal.emit(False)
            # Show position dialog for this measurement
            self.show_position_dialog.emit(position)
            return
        
        # Continue with current measurement
        channel, position = state['current_remeasure_pair']
        sample_name = f"{channel}_pos{position}"
        
        # Update grid to show current position and start flash
        self.grid_position_signal.emit(position)
        self.grid_flash_signal.emit(True)
        
        retry_msg = f" (Retry {self.current_retry + 1}/{self.max_retries})" if self.current_retry > 0 else ""
        self.status_update.emit(f"Remeasuring {sample_name}{retry_msg}...")
        
        # Reset coordinator and start measurement
        coordinator.reset(channel, position)
        
        success, error_msg = start_capture(
            channel, position, 
            status_callback=self.status_update.emit,
            error_callback=self.error_occurred.emit
        )
        
        if not success:
            self.status_update.emit(f"Failed to start capture for {sample_name}")
            self.handle_measurement_failure("Failed to start capture")
            return

        # Start checking for completion
        self.start_completion_check()

    def check_measurement_quality_and_pause(self):
        """Check if measurement quality requires user intervention"""
        # Only check if setting is enabled
        settings = SettingsDialog.load()
        if not settings.get('auto_pause_on_quality_issue', False):
            return True  # Continue without checking
        
        # Get current measurement info
        current_ch = self.measurement_state['channels'][self.measurement_state['channel_index']]
        current_pos = self.measurement_state['current_position']
        
        # Check if we have quality data for this measurement
        quality_key = (current_ch, current_pos)
        # Check if we have quality data for this measurement
        if self.parent_window and hasattr(self.parent_window, 'measurement_qualities'):
            if quality_key in self.parent_window.measurement_qualities:
                quality = self.parent_window.measurement_qualities[quality_key]
                rating = quality['rating']
                
                if rating in ['CAUTION', 'RETAKE']:
                    self.grid_flash_signal.emit(False)

                    # Store current state for quality dialog
                    self.measurement_state['quality_check_pending'] = True
                    self.measurement_state['quality_check_channel'] = current_ch
                    self.measurement_state['quality_check_position'] = current_pos
                    
                    # Emit signal to show quality dialog
                    self.show_quality_dialog.emit({
                        'channel': current_ch,
                        'position': current_pos,
                        'rating': rating,
                        'score': quality['score'],
                        'detail': quality['detail'],
                        'uuid': quality['uuid']
                    })
                    return False  # Pause for user input
        
        return True  # Continue

    def handle_quality_dialog_response(self, action):
        """Handle response from quality dialog"""
        state = self.measurement_state
        # Clear the pending quality check
        state['quality_check_pending'] = False

        if action == 'remeasure':
            # Reset for remeasurement of the same position/channel
            self.current_retry = 0
            # Don't increment channel_index, stay on same measurement
            QTimer.singleShot(500, self.continue_measurement)
        elif action == 'continue':
            # Continue with next measurement
            self.grid_flash_signal.emit(False)

            self.current_retry = 0
            self.measurement_state['channel_index'] += 1
            QTimer.singleShot(500, self.continue_measurement)
        elif action == 'stop':
            # Stop the measurement process
            state['running'] = False
           # self.start_button.setEnabled(True)
        #    if self.flash_timer:
         #       self.flash_timer.stop()
            self.grid_flash_signal.emit(False)  
            self.finished.emit()
            self.quit()

    def start_completion_check(self):
        """Start checking for measurement completion"""
        self.timeout_count = 0
        if self.check_timer:
            self.check_timer.stop()
            self.check_timer = None
        self.check_measurement_complete()

    def check_measurement_complete(self):
        """Check if measurement is complete with better error handling"""
        if not self.running:
            return
            
        # Check if coordinator event is set
        if coordinator.event.is_set():
            status, error_msg = coordinator.status, coordinator.error_message
            
            if status == 'success':
                self.on_measurement_success()
            elif status in ['abort', 'error']:
                self.handle_measurement_failure(error_msg or f"Measurement {status}")
            elif status == 'timeout':
                self.handle_measurement_failure("Measurement timed out")
            else:
                # Unknown status, treat as success for backward compatibility
                self.on_measurement_success()
                
        elif self.timeout_count >= 1500:  # 5 minutes timeout (1500 * 200ms)
            coordinator.trigger_timeout()
            self.handle_measurement_failure("Measurement timed out after 5 minutes")
        else:
            self.timeout_count += 1
            # Schedule next check using a proper timer
            if self.running:
                self.check_timer = QTimer()
                self.check_timer.timeout.connect(self.check_measurement_complete)
                self.check_timer.setSingleShot(True)
                self.check_timer.start(200)

    def evaluate_measurement_metrics(self):
        """Evaluate and emit measurement metrics"""
        try:
            measurement_uuid = get_measurement_uuid()
            if not measurement_uuid:
                self.status_update.emit("No measurement UUID found for evaluation.")
                return

            measurements = get_measurement_by_uuid(measurement_uuid)
            if not measurements:
                self.status_update.emit(f"No measurements found for ID: {measurement_uuid}")
                return
                
            measurement_distortion = get_measurement_distortion_by_uuid(measurement_uuid)
            if not measurement_distortion:
                self.status_update.emit(f"No distortion data found for measurement ID: {measurement_uuid}")
                return
                
            # Extract data
            thd_json = measurement_distortion
            ir_json = measurements
            coherence_array = None
            
            if not thd_json or not ir_json:
                self.status_update.emit("Incomplete distortion data for evaluation.")
                return
                
            # Evaluate metrics
            result = evaluate_measurement(thd_json, ir_json, coherence_array)
            if not result:
                self.status_update.emit("Failed to evaluate measurement metrics.")
                return
                
            # Emit metrics for display
            result['uuid'] = measurement_uuid
            self.metrics_update.emit(result)
            
            # Send detailed info to status
            detail = result.get("detail", {})
            detail_str = ", ".join(f"{k}: {v:.2f}" if isinstance(v, (int, float)) else f"{k}: {v}" 
                                 for k, v in detail.items())
            self.status_update.emit(f"Metrics: {detail_str}")
            
        except Exception as e:
            print(f"Error in evaluate_measurement_metrics: {e}")
            self.status_update.emit(f"Error evaluating metrics: {str(e)}")

    def on_measurement_success(self):
        """Called when measurement completes successfully"""
        state = self.measurement_state
        
        if state.get('repeat_mode', False):
            # Handle repeat mode
            channel, position = state['current_remeasure_pair']
            self.status_update.emit(f"Completed remeasurement of {channel}_pos{position}")
            
            # Evaluate metrics before moving on
            self.evaluate_measurement_metrics()
            
            # Turn off flash after success
            self.grid_flash_signal.emit(False)
            
            # Mark current pair as completed
            state['pair_completed'] = True
            
            # Reset retry count and continue with next pair
            self.current_retry = 0
            QTimer.singleShot(500, self.continue_measurement)
        else:
            # Original logic for normal measurements
            current_ch = self.measurement_state['channels'][self.measurement_state['channel_index']]
            self.status_update.emit(f"Completed {current_ch}_pos{self.measurement_state['current_position']}")
            
            # Evaluate metrics before moving on
            self.evaluate_measurement_metrics()
            
            # Turn off flash after success
            self.grid_flash_signal.emit(False)
            
            # Check quality if enabled
            if not self.check_measurement_quality_and_pause():
                return
            
            # Reset retry count and move to next channel
            self.current_retry = 0
            self.measurement_state['channel_index'] += 1
            
            # Continue with next measurement
            QTimer.singleShot(500, self.continue_measurement)

    def handle_measurement_failure(self, error_msg):
        """Handle measurement failure with retry logic"""
        current_ch = self.measurement_state['channels'][self.measurement_state['channel_index']]
        current_pos = self.measurement_state['current_position']
        
        # Turn off flash on failure
        self.grid_flash_signal.emit(False)
        
        self.status_update.emit(f"Error: {error_msg} for {current_ch}_pos{current_pos}")
        
        if self.current_retry < self.max_retries:
            self.current_retry += 1
            self.status_update.emit(f"Retrying {current_ch}_pos{current_pos} ({self.current_retry}/{self.max_retries})...")
            # Retry the same measurement after a brief delay
            QTimer.singleShot(2000, self.continue_measurement)
        else:
            # Max retries reached, skip to next channel
            self.status_update.emit(f"Max retries reached for {current_ch}_pos{current_pos}, skipping...")
            self.current_retry = 0
            self.measurement_state['channel_index'] += 1
            QTimer.singleShot(1000, self.continue_measurement)
        
    def resume_after_position_dialog(self):
        """Called after position dialog is completed"""
        state = self.measurement_state
        
        if state.get('repeat_mode', False):
            # In repeat mode, we can continue immediately with the current pair
            QTimer.singleShot(100, self.continue_measurement)
        else:
            # Original logic
            QTimer.singleShot(100, self.continue_measurement)

        
    def stop(self):
        """Stop the worker thread"""
        self.running = False
        if self.check_timer:
            self.check_timer.stop()
            self.check_timer = None
        self.grid_flash_signal.emit(False)  # Turn off flash when stopping
        self.quit()
        self.wait()

class ProcessingWorker(QThread):
    """Worker thread for handling cross correlation and vector averaging with error recovery"""
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str)
    finished = pyqtSignal()
    
    def __init__(self, processing_state):
        super().__init__()
        self.processing_state = processing_state
        self.running = True
        self.timeout_count = 0
        self.max_retries = 2
        self.current_retry = 0
        self.check_timer = None

    def run(self):
        self.start_processing()
        self.exec_()

    def start_processing(self):
        """Start the processing workflow"""
        if not self.running:
            return
            
        state = self.processing_state
        
        # Check if we've processed all channels
        if state['channel_index'] >= len(state['channels']):
            self.status_update.emit("All processing complete!")
            state['running'] = False
            self.finished.emit()
            self.quit()
            return
        
        current_channel = state['channels'][state['channel_index']]
        measurements = state['channel_measurements'].get(current_channel, [])
        
        if not measurements:
            self.status_update.emit(f"No measurements found for {current_channel}, skipping...")
            state['channel_index'] += 1
            QTimer.singleShot(100, self.start_processing)
            return
        
        # Extract just the measurement IDs
        measurement_ids = [m[0] for m in measurements]
        mode = state['mode']
        
        retry_msg = f" (Retry {self.current_retry + 1}/{self.max_retries})" if self.current_retry > 0 else ""
        
        if state['current_step'] == 'cross_corr':
            # Start cross correlation alignment
            coordinator.reset(current_channel, 'cross_corr')
            self.status_update.emit(f"Starting cross correlation for {current_channel}{retry_msg}...")
            
            success, error_msg = start_cross_corr_align(
                current_channel, 
                measurement_ids,
                status_callback=self.status_update.emit,
                error_callback=self.error_occurred.emit
            )
            
            if success:
                self.start_completion_check()
            else:
                self.handle_processing_failure(f"Failed to start cross correlation: {error_msg}")
                
        elif state['current_step'] == 'vector_avg':
            # Start vector averaging
            coordinator.reset(current_channel, 'vector_avg')
            self.status_update.emit(f"Starting vector averaging for {current_channel}{retry_msg}...")
            
            success, error_msg = start_vector_avg(
                current_channel, 
                measurement_ids,
                status_callback=self.status_update.emit,
                error_callback=self.error_occurred.emit
            )
            
            if success:
                self.start_completion_check()
            else:
                self.handle_processing_failure(f"Failed to start vector averaging: {error_msg}")

    def start_completion_check(self):
        """Start checking for operation completion"""
        self.timeout_count = 0
        if self.check_timer:
            self.check_timer.stop()
            self.check_timer = None
        self.check_operation_complete()

    def check_operation_complete(self):
        """Check if current operation is complete with error handling"""
        if not self.running:
            return
            
        if coordinator.event.is_set():
            status, error_msg = coordinator.status, coordinator.error_message
            
            if status == 'success':
                self.on_operation_success()
            elif status in ['abort', 'error']:
                self.handle_processing_failure(error_msg or f"Processing {status}")
            elif status == 'timeout':
                self.handle_processing_failure("Processing timed out")
            else:
                # Unknown status, treat as success for backward compatibility
                self.on_operation_success()
                
        elif self.timeout_count >= 1500:  # 5 minutes timeout
            coordinator.trigger_timeout()
            self.handle_processing_failure("Operation timed out after 5 minutes")
        else:
            self.timeout_count += 1
            if self.running:
                self.check_timer = QTimer()
                self.check_timer.timeout.connect(self.check_operation_complete)
                self.check_timer.setSingleShot(True)
                self.check_timer.start(200)

    def on_operation_success(self):
        """Called when current operation completes successfully"""
        state = self.processing_state
        current_channel = state['channels'][state['channel_index']]
        mode = state['mode']
        
        # Reset retry count
        self.current_retry = 0
        
        if state['current_step'] == 'cross_corr':
            self.status_update.emit(f"Cross correlation completed for {current_channel}")
            
            # Handle next step based on mode
            if mode == 'cross_corr_only':
                state['channel_index'] += 1
            elif mode == 'full':
                state['current_step'] = 'vector_avg'
            
            QTimer.singleShot(500, self.start_processing)
            
        elif state['current_step'] == 'vector_avg':
            self.status_update.emit(f"Vector averaging completed for {current_channel}")
            
            # Get and rename the vector average result
            vector_avg_id = get_vector_average_result()
            if vector_avg_id:
                new_name = f"{current_channel}_VectorAvg"
                success = rename_measurement(vector_avg_id, new_name, self.status_update.emit)
                if success:
                    self.status_update.emit(f"Renamed vector average to: {new_name}")
            
            # Handle next step based on mode
            if mode == 'vector_avg_only':
                state['channel_index'] += 1
            elif mode == 'full':
                state['channel_index'] += 1
                state['current_step'] = 'cross_corr'
            
            QTimer.singleShot(500, self.start_processing)

    def handle_processing_failure(self, error_msg):
        """Handle processing failure with retry logic"""
        self.status_update.emit(f"Processing error: {error_msg}")
        
        if self.current_retry < self.max_retries:
            self.current_retry += 1
            self.status_update.emit(f"Retrying... ({self.current_retry}/{self.max_retries})")
            QTimer.singleShot(2000, self.start_processing)
        else:
            # Max retries reached, skip this operation
            state = self.processing_state
            self.status_update.emit(f"Max retries reached, skipping {state['current_step']} for {state['channels'][state['channel_index']]}")
            self.current_retry = 0
            
            # Move to next operation
            if state['current_step'] == 'cross_corr' and state['mode'] == 'full':
                state['current_step'] = 'vector_avg'
            else:
                state['channel_index'] += 1
                if state['mode'] == 'full':
                    state['current_step'] = 'cross_corr'
            
            QTimer.singleShot(1000, self.start_processing)

    def stop(self):
        """Stop the worker thread"""
        self.running = False
        if self.check_timer:
            self.check_timer.stop()
            self.check_timer = None
        self.quit()
        self.wait()