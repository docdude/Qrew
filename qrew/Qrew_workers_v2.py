# Qrew_workers_v2_fixed.py - Fixed version with thread-safe timer handling
import time
import re
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, QMetaObject, Qt, pyqtSlot

try:
    from .Qrew_api_helper import (
        start_capture,
        get_all_measurements,
        start_cross_corr_align,
        start_vector_avg,
        get_vector_average_result,
        rename_measurement,
        get_measurement_by_uuid,
        get_measurement_distortion_by_uuid,
        get_measurement_uuid,
        get_ir_for_measurement,
        delete_measurement_by_uuid,
        delete_measurements_by_uuid,
        get_all_measurements_with_uuid,
        subscribe_to_rta_distortion,
        start_rta,
        stop_rta,
        unsubscribe_from_rta_distortion,
        set_rta_configuration,
        set_rta_distortion_configuration_sine,
    )
    from .Qrew_message_handlers import coordinator, rta_coordinator
    from .Qrew_measurement_metrics import (
        evaluate_measurement,
        calculate_rew_metrics_from_ir,
        combine_sweep_and_rta_results,
        combine_and_score_metrics,
    )
    from .Qrew_vlc_helper_v2 import play_sweep
    from . import Qrew_settings as qs
    from .Qrew_common import SPEAKER_LABELS
except ImportError:
    from Qrew_api_helper import (
        start_capture,
        get_all_measurements,
        start_cross_corr_align,
        start_vector_avg,
        get_vector_average_result,
        rename_measurement,
        get_measurement_by_uuid,
        get_measurement_distortion_by_uuid,
        get_measurement_uuid,
        get_ir_for_measurement,
        delete_measurement_by_uuid,
        delete_measurements_by_uuid,
        get_all_measurements_with_uuid,
        subscribe_to_rta_distortion,
        start_rta,
        stop_rta,
        unsubscribe_from_rta_distortion,
        set_rta_configuration,
        set_rta_distortion_configuration_sine,
    )
    from Qrew_message_handlers import coordinator, rta_coordinator
    from Qrew_measurement_metrics import (
        evaluate_measurement,
        calculate_rew_metrics_from_ir,
        combine_sweep_and_rta_results,
        combine_and_score_metrics,
    )
    from Qrew_vlc_helper_v2 import play_sweep
    import Qrew_settings as qs
    from Qrew_common import SPEAKER_LABELS


class MeasurementWorker(QThread):
    """Worker thread for handling measurements with error recovery"""

    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str)
    finished = pyqtSignal()
    show_position_dialog = pyqtSignal(int)
    continue_signal = pyqtSignal()
    visualization_update = pyqtSignal(
        int, list, bool
    )  # position, active_speakers, flash
    metrics_update = pyqtSignal(dict)  # Add signal for metrics
    show_quality_dialog = pyqtSignal(dict)  # Add this signal
    # Signal for safely stopping the timer
    timer_control_signal = pyqtSignal(str)

    def __init__(self, measurement_state, parent_window=None):
        super().__init__()
        self.measurement_state = measurement_state
        self.measurement_state.setdefault("pair_completed", False)
        self.parent_window = parent_window  # Add parent window reference
        self.running = True
        self.continue_signal.connect(self.continue_measurement)
        self.max_retries = 3
        self.current_retry = 0
        self.timer_control_signal.connect(self._handle_timer_control)
        self._waiting_for_position_dialog = False
        self._poll_timer = None
        self._playback_complete = False

    def run(self):
        QTimer.singleShot(0, self.continue_measurement)
        super().run()

    def continue_measurement(self):
        # Implementation remains the same as original
        # ... (existing implementation)
        if not self.running:
            return

        state = self.measurement_state

        # Handle repeat mode first
        if state.get("repeat_mode", False):
            return self.handle_repeat_mode()

        # Get initial count only once at the very beginning
        if state["initial_count"] == -1:
            _, count = get_all_measurements()
            if count == -1:
                self.status_update.emit("Failed to connect to REW API.")
                self.stop_and_finish()
                return
            state["initial_count"] = count

        pos = state["current_position"]

        # Check if we've done all channels for this position
        if state["channel_index"] >= len(state["channels"]):
            state["channel_index"] = 0
            state["current_position"] += 1
            self.current_retry = 0  # Reset retry count for new position

            # Clear any active animations before showing position dialog
            self.visualization_update.emit(pos, [], False)

            if state["current_position"] < state["num_positions"]:
                self._waiting_for_position_dialog = True
                self.show_position_dialog.emit(state["current_position"])
                # The MainWindow will call continue_measurement again after dialog
                return
            else:
                self.status_update.emit("All samples complete!")
                self.stop_and_finish()
            return

        # Process current channel
        ch = state["channels"][state["channel_index"]]
        sample_name = f"{ch}_pos{pos}"

        print(f"DEBUG: Measuring channel {ch} at position {pos}")

        retry_msg = (
            f" (Retry {self.current_retry + 1}/{self.max_retries})"
            if self.current_retry > 0
            else ""
        )
        self.status_update.emit(f"Starting measurement for {sample_name}{retry_msg}...")

        # Reset coordinator and start measurement
        coordinator.reset(ch, pos)
        self._playback_complete = False

        success, error_msg = start_capture(
            ch,
            pos,
            status_callback=self.status_update.emit,
            error_callback=self.error_occurred.emit,
        )

        if not success:
            self.status_update.emit(f"Failed to start capture for {sample_name}")
            self.handle_measurement_failure("Failed to start capture")
            return

        self.visualization_update.emit(pos, [ch], True)

        # Start checking for completion with improved timing
        self.start_completion_check()

    def continue_after_dialog(self):
        """Called by MainWindow after position dialog is closed"""
        if hasattr(self, "_waiting_for_position_dialog"):
            self._waiting_for_position_dialog = False

        # Continue with measurement
        QTimer.singleShot(100, self.continue_measurement)

    def handle_repeat_mode(self):
        """Handle repeat mode measurements"""
        # Implementation remains the same as original
        # ... (existing implementation)
        state = self.measurement_state
        pairs = state.get("remeasure_pairs", [])

        # ── initialise pointer once ──
        if "re_idx" not in state:
            state["re_idx"] = 0

        # ── done? ──
        if state["re_idx"] >= len(pairs):
            self.status_update.emit("All remeasurements complete!")
            self.stop_and_finish()
            return

        # ── if first time for this pair, prepare and show position dialog ──
        if not state.get("current_remeasure_pair") or state.get(
            "pair_completed", False
        ):

            channel, position, old_uuid = pairs[state["re_idx"]]
            state["current_remeasure_pair"] = (channel, position, old_uuid)
            state["channels"] = [channel]
            state["current_position"] = position
            state["channel_index"] = 0
            state["pair_completed"] = False

            # Show position but no active speakers yet - maintain only selected repeat channels
            self.visualization_update.emit(position, [], False)

            self._waiting_for_position_dialog = True

            self.show_position_dialog.emit(position)  # user moves mic
            return  # wait for dialog

        # ── continue measuring current pair ──
        channel, position, old_uuid = state["current_remeasure_pair"]
        sample_name = f"{channel}_pos{position}"

        # Debug print
        print(f"DEBUG: Repeat measuring channel {channel} at position {position}")

        # Emit the correct channel
        self.visualization_update.emit(position, [channel], True)

        retry_msg = (
            f" (Retry {self.current_retry + 1}/{self.max_retries})"
            if self.current_retry
            else ""
        )
        self.status_update.emit(f"Remeasuring {sample_name}{retry_msg}...")

        coordinator.reset(channel, position)
        success, err = start_capture(
            channel,
            position,
            status_callback=self.status_update.emit,
            error_callback=self.error_occurred.emit,
        )

        if not success:
            self.status_update.emit(f"Failed to start capture for {sample_name}")
            self.handle_measurement_failure("Failed to start capture")
            return

        self.visualization_update.emit(position, [channel], True)

        self.start_completion_check()  # poll coordinator

    # --- THREAD-SAFE TIMER METHODS ---

    def _handle_timer_control(self, command):
        """Handle timer control signals in the worker thread"""
        if command == "stop" and self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer.deleteLater()
            self._poll_timer = None

    def _init_poll_timer(self):
        """Thread-safe timer initialization"""
        if self._poll_timer is None:
            self._poll_timer = QTimer(self)  # Set parent for proper cleanup
            self._poll_timer.setInterval(200)  # ms
            self._poll_timer.timeout.connect(self._poll_measurement)
            # Ensure the timer runs in the worker thread
            self._poll_timer.moveToThread(self.thread())

    def start_completion_check(self):
        """Begin polling for measurement completion"""
        self.timeout_count = 0
        self._init_poll_timer()
        if self._poll_timer and not self._poll_timer.isActive():
            self._poll_timer.start()

    def _stop_poll_timer(self):
        """Thread-safe timer stopping"""
        if self._poll_timer is not None:
            # If we're in the worker thread, stop directly
            if QThread.currentThread() == self.thread():
                if self._poll_timer:
                    self._poll_timer.stop()
                    self._poll_timer.deleteLater()
                    self._poll_timer = None
            else:
                # We're in the main thread, use the signal to stop in worker thread
                self.timer_control_signal.emit("stop")

    def _poll_measurement(self):
        """Timer callback: check for measurement completion"""
        if not self.running:
            return
        # Check if we need to play the sweep
        if not self._playback_complete and coordinator.playback_requested:
            # Stop polling temporarily
            self._stop_poll_timer()

            channel = coordinator.channel
            self.status_update.emit(f"Playing sweep for {channel}...")

            # Play the sweep with callback
            success = play_sweep(
                channel,
                show_gui=qs.get("show_vlc_gui", False),
                backend=qs.get("vlc_backend", "auto"),
                on_finished=self._on_playback_complete,
            )

            if not success:
                self.handle_measurement_failure("Failed to play sweep file")
                return

            self._playback_complete = True
            return

        # finished? (coordinator event set by API helper)
        if coordinator.event.is_set():
            status, error_msg = coordinator.status, coordinator.error_message

            if status == "success":
                self.on_measurement_success()
            elif status in ("abort", "error"):
                self.handle_measurement_failure(error_msg or f"Measurement {status}")
            elif status == "timeout":
                self.handle_measurement_failure("Measurement timed out")
            else:
                # Unknown -> treat as success (backward compat)
                self.on_measurement_success()
            return  # handled; wait for next cycle to restart

        # not yet finished: check for overall timeout
        self.timeout_count += 1
        if self.timeout_count >= 1500:  # 5 min @200ms
            coordinator.trigger_timeout()
            self.handle_measurement_failure("Measurement timed out after 5 minutes")

    def _on_playback_complete(self):
        """Callback when VLC finishes playing the sweep"""
        print("Sweep playback completed")

        # Use QMetaObject.invokeMethod to ensure this runs in the worker thread
        QMetaObject.invokeMethod(
            self, "_handle_playback_complete_in_thread", Qt.QueuedConnection
        )

    @pyqtSlot()
    def _handle_playback_complete_in_thread(self):
        """Handle playback completion in the worker thread"""
        self.status_update.emit("Sweep playback completed, waiting for measurement...")

        # Resume polling for measurement completion
        if self.running:
            self._init_poll_timer()
            if self._poll_timer and not self._poll_timer.isActive():
                self._poll_timer.start()

    def calculate_measurement_metrics(self):
        """Evaluate and emit measurement metrics"""
        # Implementation remains the same as original
        # ... (existing implementation)
        try:
            measurement_uuid = get_measurement_uuid()
            if not measurement_uuid:
                self.status_update.emit("No measurement UUID found for evaluation.")
                return

            measurements = get_measurement_by_uuid(measurement_uuid)
            if not measurements:
                self.status_update.emit(
                    f"No measurements found for ID: {measurement_uuid}"
                )
                return

            measurement_distortion = get_measurement_distortion_by_uuid(
                measurement_uuid
            )
            if not measurement_distortion:
                self.status_update.emit(
                    f"No distortion data found for measurement ID: {measurement_uuid}"
                )
                return
            impulse_response = get_ir_for_measurement(measurement_uuid)

            if not impulse_response:
                self.status_update.emit(
                    f"No impulse response data found for measurement ID: {measurement_uuid}"
                )

            # Extract data
            thd_json = measurement_distortion
            info_json = measurements
            ir_json = impulse_response
            coherence_array = None

            if not thd_json or not info_json or not ir_json:
                self.status_update.emit("Incomplete measurement data for evaluation.")
                return
            channel = self.measurement_state["channels"][
                self.measurement_state["channel_index"]
            ]
            position = self.measurement_state["current_position"]
            # Evaluate metrics
            rew_metrics = calculate_rew_metrics_from_ir(ir_json)
            freq_metrics = evaluate_measurement(thd_json, info_json, coherence_array)
            combined_score = combine_and_score_metrics(rew_metrics, freq_metrics)
            if not freq_metrics:
                self.status_update.emit("Failed to evaluate measurement metrics.")
                return

            # Combine results
            result = {
                "score": combined_score["score"],
                "rating": combined_score["rating"],
                "channel": channel,
                "position": position,
                "uuid": measurement_uuid,
                "detail": {
                    **freq_metrics["detail"],
                    **rew_metrics["detail"],
                },
            }
            self.metrics_update.emit(result)

        except Exception as e:
            print(f"Error in calculate_measurement_metrics: {e}")
            self.status_update.emit(f"Error evaluating metrics: {str(e)}")

    def check_measurement_quality_and_pause(self):
        """Check if measurement quality requires user intervention"""
        # Only check if setting is enabled
        if not qs.get("auto_pause_on_quality_issue", False):
            return True  # Continue without checking

        # Get current measurement info
        current_ch = self.measurement_state["channels"][
            self.measurement_state["channel_index"]
        ]
        current_pos = self.measurement_state["current_position"]

        # Check if we have quality data for this measurement
        quality_key = (current_ch, current_pos)
        # Check if we have quality data for this measurement
        if self.parent_window and hasattr(self.parent_window, "measurement_qualities"):
            if quality_key in self.parent_window.measurement_qualities:
                quality = self.parent_window.measurement_qualities[quality_key]
                rating = quality["rating"]

                if rating in ["CAUTION", "RETAKE"]:
                    self.visualization_update.emit(current_pos, [], False)

                    # Store current state for quality dialog
                    self.measurement_state["quality_check_pending"] = True
                    self.measurement_state["quality_check_channel"] = current_ch
                    self.measurement_state["quality_check_position"] = current_pos

                    # Emit signal to show quality dialog
                    self.show_quality_dialog.emit(
                        {
                            "channel": current_ch,
                            "position": current_pos,
                            "rating": rating,
                            "score": quality["score"],
                            "detail": quality["detail"],
                            "uuid": quality["uuid"],
                        }
                    )
                    return False  # Pause for user input

        return True  # Continue

    def handle_quality_dialog_response(self, action):
        """Handle response from quality dialog"""
        state = self.measurement_state
        # Clear the pending quality check
        state["quality_check_pending"] = False

        if action == "remeasure":
            # Reset for remeasurement of the same position/channel
            self.current_retry = 0
            # Don't increment channel_index, stay on same measurement
            QTimer.singleShot(500, self.continue_measurement)
        elif action == "continue":
            # Continue with next measurement
            current_pos = self.measurement_state["current_position"]

            self.visualization_update.emit(current_pos, [], False)

            self.current_retry = 0
            self.measurement_state["channel_index"] += 1
            QTimer.singleShot(500, self.continue_measurement)
        elif action == "stop":
            # Stop the measurement process
            self.stop_and_finish()

    def on_measurement_success(self):
        """Called when measurement completes successfully"""
        # STOP the timer to prevent multiple calls
        self._stop_poll_timer()
        state = self.measurement_state

        if state.get("repeat_mode", False):
            # Handle repeat mode
            channel, position, old_uuid = state["current_remeasure_pair"]
            self.status_update.emit(
                f"Completed remeasurement of {channel}_pos{position}"
            )

            # Evaluate metrics before moving on
            self.calculate_measurement_metrics()
            rating_ok = (
                self.parent_window
                and (channel, position) in self.parent_window.measurement_qualities
                and self.parent_window.measurement_qualities[(channel, position)][
                    "rating"
                ]
                == "PASS"
            )

            if rating_ok:
                # 1) drop the stale failure row so it never re-appears
                self.parent_window.measurement_qualities.pop((channel, position), None)

                # 2) delete the old measurement file in REW (already existed)
                if old_uuid:
                    delete_measurement_by_uuid(old_uuid)

            self.visualization_update.emit(
                self.measurement_state["current_position"], [], False
            )
            # Mark current pair as completed
            state["pair_completed"] = True
            state["re_idx"] += 1
            # Reset retry count and continue with next pair
            self.current_retry = 0
            QTimer.singleShot(500, self.continue_measurement)
        else:
            # Original logic for normal measurements
            current_ch = self.measurement_state["channels"][
                self.measurement_state["channel_index"]
            ]
            self.status_update.emit(
                f"Completed {current_ch}_pos{self.measurement_state['current_position']}"
            )

            # Evaluate metrics before moving on
            self.calculate_measurement_metrics()

            self.visualization_update.emit(
                self.measurement_state["current_position"], [], False
            )
            # Check quality if enabled
            if not self.check_measurement_quality_and_pause():
                return

            # Reset retry count and move to next channel
            self.current_retry = 0
            self.measurement_state["channel_index"] += 1

            # Continue with next measurement
            QTimer.singleShot(500, self.continue_measurement)

    def handle_measurement_failure(self, error_msg):
        """Handle measurement failure with retry logic"""
        # STOP the timer to prevent multiple calls
        self._stop_poll_timer()
        if (
            "stimulus" in error_msg.lower()
            or "no stimulus" in error_msg.lower()
            or "sweep file" in error_msg.lower()
        ):
            self.status_update.emit("Measurement aborted: stimulus file not loaded.")
            self.error_occurred.emit(
                "Measurement Aborted", "Check VLC and sweep files."
            )
            # Don't call _abort_current_run() for VLC errors - just stop cleanly
            # This prevents the "Measurement process aborted" message on completion
            self.stop_and_finish()
            return
        current_ch = self.measurement_state["channels"][
            self.measurement_state["channel_index"]
        ]
        current_pos = self.measurement_state["current_position"]

        # Turn off flash on failure
        self.visualization_update.emit(
            self.measurement_state["current_position"], [], False
        )
        self.status_update.emit(f"Error: {error_msg} for {current_ch}_pos{current_pos}")

        if self.current_retry < self.max_retries:
            self.current_retry += 1
            self.status_update.emit(
                f"Retrying {current_ch}_pos{current_pos} ({self.current_retry}/{self.max_retries})..."
            )
            # Retry the same measurement after a brief delay
            QTimer.singleShot(2000, self.continue_measurement)
        else:
            # Max retries reached, skip to next channel
            self.status_update.emit(
                f"Max retries reached for {current_ch}_pos{current_pos}, skipping..."
            )
            self.current_retry = 0
            self.measurement_state["channel_index"] += 1
            QTimer.singleShot(1000, self.continue_measurement)

    def stop(self):
        """Immediate stop requested by UI (close / cancel)."""
        self.running = False
        self._stop_poll_timer()
        self.quit()
        self.wait()

    def stop_and_finish(self):
        """
        Graceful normal completion.
        Emits finished(), stops polling, ends thread loop.
        """
        if self.running:
            self.running = False
            self.finished.emit()
            # Clear visualization animations
            self.visualization_update.emit(
                self.measurement_state.get("current_position", 0),
                [],  # No active speakers
                False,  # No flash
            )
        self._stop_poll_timer()
        self.quit()


class ProcessingWorker(QThread):
    """Worker thread for handling cross correlation and vector averaging with error recovery"""

    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str)
    finished = pyqtSignal()
    timer_control_signal = pyqtSignal(str)

    def __init__(self, processing_state):
        super().__init__()
        self.processing_state = processing_state
        self.running = True
        self.timeout_count = 0
        self.max_retries = 2
        self.current_retry = 0
        self._poll_timer = None
        self.timer_control_signal.connect(self._handle_timer_control)

    def run(self):
        QTimer.singleShot(0, self.start_processing)
        super().run()

    def _handle_timer_control(self, command):
        """Handle timer control signals in the worker thread"""
        if command == "stop" and self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer.deleteLater()
            self._poll_timer = None

    def _init_poll_timer(self):
        """Thread-safe timer initialization"""
        if self._poll_timer is None:
            self._poll_timer = QTimer(self)  # Set parent for proper cleanup
            self._poll_timer.setInterval(200)
            self._poll_timer.timeout.connect(self._poll_processing)
            # Ensure the timer runs in the worker thread
            self._poll_timer.moveToThread(self.thread())

    def start_completion_check(self):
        """Begin polling for processing completion"""
        self.timeout_count = 0
        self._init_poll_timer()
        if self._poll_timer and not self._poll_timer.isActive():
            self._poll_timer.start()

    def _stop_poll_timer(self):
        """Thread-safe timer stopping"""
        if self._poll_timer is not None:
            # If we're in the worker thread, stop directly
            if QThread.currentThread() == self.thread():
                if self._poll_timer:
                    self._poll_timer.stop()
                    self._poll_timer.deleteLater()
                    self._poll_timer = None
            else:
                # We're in the main thread, use the signal to stop in worker thread
                self.timer_control_signal.emit("stop")

    def start_processing(self):
        """Start the processing workflow"""
        if not self.running:
            return

        state = self.processing_state

        # Check if we've processed all channels
        if state["channel_index"] >= len(state["channels"]):
            self.status_update.emit("All processing complete!")
            self.stop_and_finish()
            return

        current_channel = state["channels"][state["channel_index"]]
        measurements = state["channel_measurements"].get(current_channel, [])

        if not measurements:
            self.status_update.emit(
                f"No measurements found for {current_channel}, skipping..."
            )
            state["channel_index"] += 1
            QTimer.singleShot(100, self.start_processing)
            return

        # Sort by mic position (0 first) and keep only the UUIDs
        try:
            measurement_ids = [
                m["uuid"]
                for m in sorted(measurements, key=lambda x: x.get("position", 0))
            ]
        except (TypeError, KeyError):
            # backward-compatibility with the old tuple format: (uuid, position, ...)
            measurement_ids = [
                m[0]
                for m in sorted(measurements, key=lambda x: x[1] if len(m) > 1 else 0)
            ]
        mode = state["mode"]

        retry_msg = (
            f" (Retry {self.current_retry + 1}/{self.max_retries})"
            if self.current_retry > 0
            else ""
        )

        if state["current_step"] == "cross_corr":
            # Start cross correlation alignment
            coordinator.reset(current_channel, "cross_corr")
            self.status_update.emit(
                f"Starting cross correlation for {current_channel}{retry_msg}..."
            )

            success, error_msg = start_cross_corr_align(
                current_channel,
                measurement_ids,
                status_callback=self.status_update.emit,
                error_callback=self.error_occurred.emit,
            )

            if success:
                self.start_completion_check()
            else:
                self.handle_processing_failure(
                    f"Failed to start cross correlation: {error_msg}"
                )

        elif state["current_step"] == "vector_avg":
            # Start vector averaging
            coordinator.reset(current_channel, "vector_avg")
            self.status_update.emit(
                f"Starting vector averaging for {current_channel}{retry_msg}..."
            )

            success, error_msg = start_vector_avg(
                current_channel,
                measurement_ids,
                status_callback=self.status_update.emit,
                error_callback=self.error_occurred.emit,
            )

            if success:
                self.start_completion_check()
            else:
                self.handle_processing_failure(
                    f"Failed to start vector averaging: {error_msg}"
                )

    def _poll_processing(self):
        if not self.running:
            return

        if coordinator.event.is_set():
            status, error_msg = coordinator.status, coordinator.error_message

            if status == "success":
                self.on_operation_success()
            elif status in ("abort", "error"):
                self.handle_processing_failure(error_msg or f"Processing {status}")
            elif status == "timeout":
                self.handle_processing_failure("Processing timed out")
            else:
                self.on_operation_success()
            return

        self.timeout_count += 1
        if self.timeout_count >= 1500:
            coordinator.trigger_timeout()
            self.handle_processing_failure("Operation timed out after 5 minutes")

    def on_operation_success(self):
        """Called when current operation completes successfully"""
        self._stop_poll_timer()

        state = self.processing_state
        current_channel = state["channels"][state["channel_index"]]
        mode = state["mode"]

        # Reset retry count
        self.current_retry = 0

        if state["current_step"] == "cross_corr":
            self.status_update.emit(
                f"Cross correlation completed for {current_channel}"
            )

            # Handle next step based on mode
            if mode == "cross_corr_only":
                state["channel_index"] += 1
            elif mode == "full":
                state["current_step"] = "vector_avg"

            QTimer.singleShot(500, self.start_processing)

        elif state["current_step"] == "vector_avg":
            self.status_update.emit(f"Vector averaging completed for {current_channel}")

            # Get and rename the vector average result
            vector_avg_id = get_vector_average_result()
            if vector_avg_id:
                new_name = f"{current_channel}_VectorAvg"
                success = rename_measurement(
                    vector_avg_id, new_name, self.status_update.emit
                )
                if success:
                    self.status_update.emit(f"Renamed vector average to: {new_name}")

            # Handle next step based on mode
            if mode == "vector_avg_only":
                state["channel_index"] += 1
            elif mode == "full":
                state["channel_index"] += 1
                state["current_step"] = "cross_corr"

            QTimer.singleShot(500, self.start_processing)

    def handle_processing_failure(self, error_msg):
        """Handle processing failure with retry logic"""
        self._stop_poll_timer()

        self.status_update.emit(f"Processing error: {error_msg}")

        if self.current_retry < self.max_retries:
            self.current_retry += 1
            self.status_update.emit(
                f"Retrying... ({self.current_retry}/{self.max_retries})"
            )
            QTimer.singleShot(2000, self.start_processing)
        else:
            # Max retries reached, skip this operation
            state = self.processing_state
            self.status_update.emit(
                f"Max retries reached, skipping {state['current_step']} for {state['channels'][state['channel_index']]}"
            )
            self.current_retry = 0

            # Move to next operation
            if state["current_step"] == "cross_corr" and state["mode"] == "full":
                state["current_step"] = "vector_avg"
            else:
                state["channel_index"] += 1
                if state["mode"] == "full":
                    state["current_step"] = "cross_corr"

            QTimer.singleShot(1000, self.start_processing)

    def stop(self):
        self.running = False
        self._stop_poll_timer()
        self.quit()
        self.wait()

    def stop_and_finish(self):
        if self.running:
            self.running = False
            self.finished.emit()
        self._stop_poll_timer()
        self.quit()


# Keep the RTAWorker class implementation as it was in the original file
# (The original implementation is not shown here but should be added back)
class RTAWorker(QThread):
    """Worker thread for RTA verification measurements"""

    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str)
    finished = pyqtSignal()
    verification_complete = pyqtSignal(dict)  # Emits enhanced measurement result

    def __init__(self, channel, initial_result, duration=8):
        super().__init__()
        self.channel = channel
        self.initial_result = initial_result
        self.duration = duration
        self.running = True
        self.rta_samples = []
        self.start_time = None
        self.min_samples = 20
        self.collecting = False

    def run(self):
        QTimer.singleShot(0, self.start_rta_measurement)
        super().run()

    def start_rta_measurement(self):
        """Main RTA verification workflow"""
        try:
            self.status_update.emit(f"Starting RTA verification for {self.channel}...")

            # Subscribe to RTA distortion
            if not subscribe_to_rta_distortion():
                self.error_occurred.emit(
                    "RTA Error", "Failed to subscribe to RTA distortion"
                )
                return
            if not set_rta_configuration():
                self.error_occurred.emit("RTA Error", "Failed to set RTA configuration")
            if not set_rta_distortion_configuration_sine():
                self.error_occurred.emit(
                    "RTA Error", "Failed to set RTA distortion configuration"
                )

            # Start RTA mode
            if not start_rta():
                self.error_occurred.emit("RTA Error", "Failed to start RTA mode")
                self.cleanup()
                return

            # Brief delay to let RTA settle
            time.sleep(0.5)

            # Start collecting samples
            self.start_collection()

            # Play verification sweep with callback
            self.status_update.emit(f"Playing verification sweep for {self.channel}")
            success = play_sweep(
                self.channel,
                show_gui=True,
                backend="auto",
                on_finished=self.on_playback_complete,  # This was previously completion_callback
            )
            if not success:
                self.error_occurred.emit(
                    "Playback Error", "Failed to start verification sweep"
                )
                self.cleanup()
                return

            # Wait for completion or timeout
            self.wait_for_completion()

        except Exception as e:
            self.error_occurred.emit("RTA Error", f"Unexpected error: {str(e)}")
        finally:
            self.cleanup()
            self.stop_and_finish

    def start_collection(self):
        """Start collecting RTA samples"""
        self.collecting = True
        self.rta_samples = []
        self.start_time = time.time()
        self.status_update.emit("Collecting RTA distortion data...")

        # Connect to the global RTA coordinator
        rta_coordinator.start_collection(duration=self.duration)

    def on_playback_complete(self):
        """Called when VLC playback finishes"""
        self.status_update.emit("Playback complete, finalizing RTA collection...")
        print("RTA verification sweep finished")
        # Give a brief moment for final samples
        QTimer.singleShot(1000, self.stop_collection)

    def wait_for_completion(self):
        """Wait for collection to complete with timeout"""
        timeout_count = 0
        max_timeout = (self.duration + 5) * 10  # Add 5 second buffer, check every 100ms

        while self.collecting and self.running and timeout_count < max_timeout:
            time.sleep(0.1)
            timeout_count += 1

            # Check if we have enough samples and minimum time has passed
            elapsed = time.time() - self.start_time if self.start_time else 0
            if (
                elapsed >= self.duration
                and len(rta_coordinator.samples) >= self.min_samples
            ):
                self.stop_collection()
                break

        if timeout_count >= max_timeout:
            self.status_update.emit("RTA verification timed out")

    def stop_collection(self):
        """Stop collecting and analyze results"""
        if not self.collecting:
            return

        self.collecting = False

        # Get results from global coordinator
        rta_result = rta_coordinator.stop_collection()

        if rta_result and rta_result["stable_samples"] >= self.min_samples:
            self.status_update.emit(
                f"RTA verification complete: {rta_result['stable_samples']} samples analyzed"
            )

            # Combine with initial sweep result
            enhanced_result = combine_sweep_and_rta_results(
                self.initial_result, rta_result
            )
            self.verification_complete.emit(enhanced_result)
        else:
            self.status_update.emit("RTA verification failed - insufficient data")
            self.verification_complete.emit(
                self.initial_result
            )  # Return original result

    def cleanup(self):
        """Cleanup RTA resources"""
        try:
            stop_rta()
            unsubscribe_from_rta_distortion()
            if hasattr(rta_coordinator, "collecting") and rta_coordinator.collecting:
                rta_coordinator.stop_collection()
        except (ConnectionError, TimeoutError) as e:
            print(f"RTA cleanup connection error: {e}")
        except RuntimeError as e:
            print(f"RTA cleanup runtime error: {e}")
        except OSError as e:
            print(f"RTA cleanup I/O error: {e}")
        except ValueError as e:
            print(f"RTA cleanup value error: {e}")

    def stop(self):
        """External hard-stop (e.g. MainWindow.closeEvent)"""
        if not self.running:  # already stopped
            return
        self.stop_and_finish()  # <- delegate, emits `finished` & quits

    def stop_and_finish(self):
        """Safely stop the worker and emit finished signal"""
        if self.running:
            self.running = False
            self.collecting = False
            # Cleanup before quitting
            self.cleanup()
            self.finished.emit()
        self.quit()


class APIWorker(QThread):
    """Worker thread for non-blocking API operations"""

    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str)  # title, message
    operation_complete = pyqtSignal(object)  # result

    def __init__(self, operation, *args, **kwargs):
        super().__init__()
        self.operation = operation
        self.args = args
        self.kwargs = kwargs
        self.result = None

    def run(self):
        """Execute the API operation"""
        try:
            # Add status callback if the operation supports it
            if "status_callback" in self.kwargs:
                self.kwargs["status_callback"] = self.emit_status

            self.result = self.operation(*self.args, **self.kwargs)
            self.operation_complete.emit(self.result)

        except Exception as e:
            self.error_occurred.emit("API Error", str(e))

    def emit_status(self, message):
        """Emit status update"""
        self.status_update.emit(message)


class MeasurementCountWorker(QThread):
    """Worker for getting measurement count without blocking"""

    count_received = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def run(self):
        """Get measurement count"""
        try:
            try:
                from .Qrew_api_helper import get_measurement_count
            except ImportError:
                from Qrew_api_helper import get_measurement_count

            count = get_measurement_count()
            self.count_received.emit(count)
        except Exception as e:
            self.error_occurred.emit(str(e))


class DeleteMeasurementsWorker(QThread):
    """Worker for deleting measurements without blocking"""

    status_update = pyqtSignal(str)
    delete_complete = pyqtSignal(bool, int, str)  # success, count, error_msg

    def __init__(self):
        super().__init__()

    def run(self):
        """Delete all measurements"""
        try:
            try:
                from .Qrew_api_helper import delete_all_measurements
            except ImportError:
                from Qrew_api_helper import delete_all_measurements

            success, count, error_msg = delete_all_measurements(
                status_callback=lambda msg: self.status_update.emit(msg)
            )
            self.delete_complete.emit(success, count, error_msg)
        except Exception as e:
            self.delete_complete.emit(False, 0, str(e))


class SaveMeasurementsWorker(QThread):
    """Worker for saving measurements without blocking"""

    status_update = pyqtSignal(str)
    save_complete = pyqtSignal(bool, str)  # success, error_msg

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        """Save all measurements"""
        try:
            try:
                from .Qrew_api_helper import save_all_measurements
            except ImportError:
                from Qrew_api_helper import save_all_measurements

            success, error_msg = save_all_measurements(
                self.file_path, status_callback=lambda msg: self.status_update.emit(msg)
            )
            self.save_complete.emit(success, error_msg)
        except Exception as e:
            self.save_complete.emit(False, str(e))


class DeleteMeasurementByUuidWorker(QThread):
    """Worker for deleting a single measurement by UUID"""

    status_update = pyqtSignal(str)
    delete_complete = pyqtSignal(bool, str)  # success, error_message

    def __init__(self, uuid):
        super().__init__()
        self.uuid = uuid

    def run(self):
        """Delete a single measurement by UUID"""
        try:
            success = delete_measurement_by_uuid(
                self.uuid, status_callback=lambda msg: self.status_update.emit(msg)
            )
            if success:
                self.delete_complete.emit(True, "")
            else:
                self.delete_complete.emit(False, "Failed to delete measurement")
        except Exception as e:
            self.delete_complete.emit(False, str(e))


class DeleteMeasurementsByUuidWorker(QThread):
    """Worker for deleting multiple measurements by UUID"""

    status_update = pyqtSignal(str)
    delete_complete = pyqtSignal(int, int)  # deleted_count, failed_count

    def __init__(self, uuid_list):
        super().__init__()
        self.uuid_list = uuid_list

    def run(self):
        """Delete multiple measurements by UUID"""
        deleted_count = 0
        failed_count = 0

        try:
            from .Qrew_api_helper import delete_measurement_by_uuid
        except ImportError:
            from Qrew_api_helper import delete_measurement_by_uuid

        for i, uuid in enumerate(self.uuid_list):
            try:
                self.status_update.emit(
                    f"Deleting measurement {i+1} of {len(self.uuid_list)}..."
                )
                success = delete_measurement_by_uuid(uuid)
                if success:
                    deleted_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                print(f"Error deleting UUID {uuid}: {e}")
                failed_count += 1

        self.delete_complete.emit(deleted_count, failed_count)


class LoadMeasurementsQualityWorker(QThread):
    """Worker for loading existing measurements quality"""

    status_update = pyqtSignal(str)
    quality_loaded = pyqtSignal(dict)  # measurement_qualities

    def __init__(self):
        super().__init__()

    def run(self):
        """Load quality data for existing measurements"""
        measurement_qualities = {}

        try:
            measurements, _ = get_all_measurements_with_uuid()
            if not measurements:
                self.quality_loaded.emit(measurement_qualities)
                return

            for measurement in measurements:
                title = measurement.get("title", "")
                uuid = measurement.get("uuid", "")

                # Parse channel and position from title
                for channel in SPEAKER_LABELS.keys():
                    pattern = rf"^{re.escape(channel)}_pos(\d+)$"
                    match = re.match(pattern, title, re.IGNORECASE)
                    if match:
                        position = int(match.group(1))

                        # Try to get quality metrics for this measurement
                        try:
                            measurement_data = get_measurement_by_uuid(uuid)
                            distortion_data = get_measurement_distortion_by_uuid(uuid)
                            ir_response = get_ir_for_measurement(uuid)

                            if distortion_data and measurement_data and ir_response:
                                # Calculate metrics
                                rew_metrics = calculate_rew_metrics_from_ir(ir_response)
                                freq_metrics = evaluate_measurement(
                                    distortion_data, measurement_data, None
                                )
                                combined_result = combine_and_score_metrics(
                                    rew_metrics, freq_metrics
                                )

                                # Store quality data
                                rating = combined_result.get("rating", "RETAKE")
                                score = combined_result.get("score", 0.0)
                                detail = {
                                    **freq_metrics.get("detail", {}),
                                    **rew_metrics.get("detail", {}),
                                }

                                measurement_qualities[(channel, position)] = {
                                    "rating": rating,
                                    "score": score,
                                    "uuid": uuid,
                                    "detail": detail,
                                    "title": title,
                                }

                                self.status_update.emit(
                                    f"Loaded quality for {channel}_pos{position}: {rating}"
                                )
                        except (ConnectionError, TimeoutError) as e:
                            print(f"API connection error evaluating {title}: {e}")
                        except (ValueError, TypeError, KeyError) as e:
                            print(f"Data error evaluating {title}: {e}")
                        except RuntimeError as e:
                            print(f"Runtime error evaluating {title}: {e}")

                        break  # Found channel match, move to next measurement

            self.quality_loaded.emit(measurement_qualities)

        except Exception as e:
            self.status_update.emit(f"Error loading measurements: {str(e)}")
            self.quality_loaded.emit(measurement_qualities)


class REWConnectionWorker(QThread):
    """Worker for checking REW connection without blocking"""

    connection_status = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

    def run(self):
        """Check REW connection"""
        try:
            try:
                from .Qrew_api_helper import check_rew_connection
            except ImportError:
                from Qrew_api_helper import check_rew_connection

            is_connected = check_rew_connection()
            self.connection_status.emit(is_connected)
        except Exception as e:
            print(f"Error checking REW connection: {e}")
            self.connection_status.emit(False)


class GetMeasurementsWorker(QThread):
    """Worker for getting all measurements with UUID"""

    measurements_received = pyqtSignal(list, int)  # measurements, count
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def run(self):
        """Get all measurements"""
        try:
            measurements, count = get_all_measurements_with_uuid()
            if measurements is None:
                self.error_occurred.emit("Failed to get measurements")
            else:
                self.measurements_received.emit(measurements, count)
        except (ConnectionError, TimeoutError) as e:
            self.error_occurred.emit(f"Connection error: {str(e)}")
        except (ValueError, TypeError, KeyError) as e:
            self.error_occurred.emit(f"Data error: {str(e)}")
        except RuntimeError as e:
            self.error_occurred.emit(f"Runtime error: {str(e)}")
        except OSError as e:
            self.error_occurred.emit(f"I/O error: {str(e)}")


class GetChannelMeasurementsWorker(QThread):
    """Worker thread for getting measurements for selected channels"""

    status_update = pyqtSignal(str)
    measurements_received = pyqtSignal(dict, str)  # channels_with_data, mode
    error_occurred = pyqtSignal(str, str)  # title, message

    def __init__(self, selected_channels, mode):
        super().__init__()
        self.selected_channels = selected_channels
        self.mode = mode

    def run(self):
        """Get measurements for selected channels"""
        try:
            try:
                from .Qrew_api_helper import (
                    get_selected_channels_with_measurements_uuid,
                )
            except ImportError:
                from Qrew_api_helper import get_selected_channels_with_measurements_uuid

            self.status_update.emit("Getting measurements for selected channels...")

            channels_with_data = get_selected_channels_with_measurements_uuid(
                self.selected_channels, status_callback=self.status_update.emit
            )

            # Check which channels were excluded (have no measurements)
            channels_without_data = [
                ch for ch in self.selected_channels if ch not in channels_with_data
            ]

            if channels_without_data:
                # Emit warning about channels without measurements
                missing_channels = ", ".join(channels_without_data)
                warning_msg = f"No measurements found for channels: {missing_channels}"
                self.status_update.emit(f"Warning: {warning_msg}")

                # Use error_occurred for a more prominent notification
                self.error_occurred.emit(
                    "Missing Measurements",
                    f"{warning_msg}. These channels will be skipped.",
                )

            if not channels_with_data:
                # No channels have measurements at all
                self.error_occurred.emit(
                    "No Measurements",
                    "No measurements found for any selected channels. "
                    "Please run measurements first.",
                )
                return
            else:
                # We have at least some channels with data, continue processing
                found_channels = ", ".join(channels_with_data.keys())
                success_msg = f"Found measurements for channels: {found_channels}"
                self.status_update.emit(success_msg)
                self.measurements_received.emit(channels_with_data, self.mode)

        except Exception as e:
            self.error_occurred.emit(
                "Error", f"Failed to get channel measurements: {str(e)}"
            )


class CancelMeasurementWorker(QThread):
    """Worker for canceling measurements without blocking"""

    status_update = pyqtSignal(str)
    cancel_complete = pyqtSignal(bool, str)  # success, message
    error_occurred = pyqtSignal(str, str)  # title, message

    def __init__(self):
        super().__init__()

    def run(self):
        """Cancel measurement"""
        try:
            try:
                from .Qrew_api_helper import cancel_measurement
            except ImportError:
                from Qrew_api_helper import cancel_measurement

            self.status_update.emit("Cancelling measurement...")

            success, message = cancel_measurement(
                status_callback=lambda msg: self.status_update.emit(msg),
                error_callback=lambda title, msg: self.error_occurred.emit(title, msg),
            )

            if success:
                self.cancel_complete.emit(True, message or "Measurement cancelled")
            else:
                self.cancel_complete.emit(False, message or "Cancel failed")

        except Exception as e:
            self.error_occurred.emit("Error", f"Failed to cancel measurement: {str(e)}")
            self.cancel_complete.emit(False, str(e))
