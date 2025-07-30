# Qrew_api_helper.py
"""REW API Helper Module

This module provides functions to interact with the REW (Room EQ Wizard) API for measurement and processing tasks.
It includes functions to start measurements, process results, and manage subscriptions for status updates, warnings, and errors.
"""
import requests
import os
import re

try:
    from .Qrew_vlc_helper_v2 import find_sweep_file
    from .Qrew_common import REW_API_BASE_URL
    from . import Qrew_common
except ImportError:
    from Qrew_vlc_helper_v2 import find_sweep_file
    from Qrew_common import REW_API_BASE_URL
    import Qrew_common


# Helper functions
def get_measurements_for_channel(channel):
    """
    Get all measurements for a specific channel, sorted by position.
    Returns list of (measurement_id, position) tuples.
    """
    try:
        measurements, _ = get_all_measurements()
        if not measurements:
            return []

        channel_measurements = []

        for measurement in measurements:
            title = measurement.get("title", "")
            # Match pattern: channel_pos# (e.g., "FL_pos0", "FR_pos1")
            pattern = rf"^{re.escape(channel)}_pos(\d+)$"
            match = re.match(pattern, title, re.IGNORECASE)

            if match:
                position = int(match.group(1))
                measurement_id = measurement["id"]
                channel_measurements.append((measurement_id, position))

        # Sort by position (0 first, then 1, 2, etc.)
        channel_measurements.sort(key=lambda x: x[1])

        return channel_measurements

    except Exception as e:
        print(f"Error getting measurements for channel {channel}: {e}")
        return []


def get_selected_channels_with_measurements(selected_channels):
    """
    Get measurements for all selected channels that have actual measurement data.
    Returns dict: {channel: [(id, position), ...]}
    """
    channels_with_data = {}

    for channel in selected_channels:
        measurements = get_measurements_for_channel(channel)
        if measurements:  # Only include channels that have measurements
            channels_with_data[channel] = measurements
            print(
                f"Found {len(measurements)} measurements for {channel}: {measurements}"
            )
        else:
            print(f"No measurements found for channel {channel}")

    return channels_with_data


def get_vector_average_result():
    """
    Get the measurement ID of the latest vector average result.
    Returns measurement_id or None if no vector average result found.
    """
    process_name, measurement_id, message = get_measurement_process_result()

    if process_name and "Vector" in process_name and message == "Completed":
        return measurement_id

    return None


def get_cross_corr_result():
    """
    Get the result of the latest cross correlation alignment.
    Returns measurement_id or None if no cross correlation result found.
    """
    process_name, measurement_id, message = get_measurement_process_result()

    if process_name and "Cross corr" in process_name and message == "Completed":
        return measurement_id

    return None


# Updated start_capture function with proper error handling
def start_capture(channel, position, status_callback=None, error_callback=None):
    """
    Start capture process. Returns (success, error_message).
    Uses callbacks instead of direct message boxes for thread safety.
    """
    # global selected_stimulus_path, stimulus_dir

    sample_name = f"{channel}_pos{position}"
    # Show initial processing message
    if status_callback:
        status_callback(f"Processing {sample_name}...")

    # Confirm stimulus directory is valid
    if not Qrew_common.stimulus_dir or not os.path.isdir(Qrew_common.stimulus_dir):
        err_msg = "Stimulus directory is not set or invalid."
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Missing Stimulus Directory", err_msg)
        return False, err_msg

    # Locate sweep file (MLP or MP4)
    sweep_file = find_sweep_file(channel)

    if not sweep_file or not os.path.exists(sweep_file):
        err_msg = f"No .mlp or .mp4 sweep file found for channel '{channel}' in {Qrew_common.stimulus_dir}"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Sweep File Not Found", err_msg)
        return False, err_msg

    # Set stimulus WAV path (used by REW, not necessarily the sweep file)
    stimulus_path = Qrew_common.selected_stimulus_path
    if not os.path.exists(stimulus_path):
        err_msg = f"Stimulus WAV file not found: {stimulus_path}"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Stimulus File Not Found", err_msg)
        return False, err_msg

    # Start measurement using REW API
    success, err_msg = start_measurement(
        sample_name,
        stimulus_path,
        status_callback=status_callback,
        error_callback=error_callback,
    )

    return success, err_msg


def start_measurement(
    sample_name, stimulus_path, status_callback=None, error_callback=None
):
    try:
        # Configure REW via API
        requests.post(
            f"{REW_API_BASE_URL}/measure/measurement-mode", json="Single"
        ).raise_for_status()
        requests.post(
            f"{REW_API_BASE_URL}/measure/naming",
            json={
                "title": sample_name,
                "namingOption": "Use as entered",
                "prefixMeasNameWithOutput": "false",
            },
        ).raise_for_status()
        requests.post(
            f"{REW_API_BASE_URL}/measure/playback-mode", json="From file"
        ).raise_for_status()
        requests.post(
            f"{REW_API_BASE_URL}/measure/timing/reference", json="Acoustic"
        ).raise_for_status()
        requests.post(
            f"{REW_API_BASE_URL}/measure/file-playback-stimulus", json=stimulus_path
        ).raise_for_status()
        requests.post(
            f"{REW_API_BASE_URL}/generator/signal", json={"signal": "meassweep"}
        ).raise_for_status()

        # Do NOT launch sweep or trigger next — handled by REW status subscriber
        requests.post(
            f"{REW_API_BASE_URL}/measure/command", json={"command": "SPL"}
        ).raise_for_status()

        return True, None

    except requests.RequestException as e:
        err_msg = f"Error starting measurement '{sample_name}': {e}"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Measurement Error", err_msg)
        return False, err_msg
    except Exception as e:
        err_msg = f"Unexpected error: {e}"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Error", err_msg)
        return False, err_msg


def cancel_measurement(status_callback=None, error_callback=None):
    """
    Ask REW to abort the running measurement.
    Returns (success_bool, message_or_None)
    """
    try:
        if status_callback:
            status_callback("Cancelling measurement...")

        requests.post(
            f"{REW_API_BASE_URL}/measure/command", json={"command": "Cancel"}
        ).raise_for_status()

        return True, None

    except requests.RequestException as e:
        err_msg = f"Error canceling measurement': {e}"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Measurement Error", err_msg)
        return False, err_msg
    except Exception as e:
        err_msg = f"Unexpected error: {e}"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Error", err_msg)
        return False, err_msg


def get_ir_for_measurement(measurement_uuid):
    try:
        response = requests.get(
            f"{REW_API_BASE_URL}/measurements/{measurement_uuid}/impulse-response?normalised=false"
        )
        response.raise_for_status()
        ir = response.json()

        if not ir:
            print(f"No impulse response found for UUID: {measurement_uuid}")
            return None

        return ir

    except requests.RequestException as e:
        print(f"REW API Error getting impulse response for {measurement_uuid}: {e}")
        return None
    except Exception as e:
        print(f"Error parsing impulse response for {measurement_uuid}: {e}")
        return None


def get_all_measurements():
    try:
        response = requests.get(f"{REW_API_BASE_URL}/measurements")
        response.raise_for_status()
        ids = response.json()
        num_measurements = len(ids)
        measurements = []
        for m_id in ids:
            meta = requests.get(f"{REW_API_BASE_URL}/measurements/{m_id}").json()
            meta["id"] = m_id
            measurements.append(meta)
        return measurements, num_measurements
    except requests.RequestException as e:
        print(f"REW API Error: {e}")
        return None, -1


def save_all_measurements(file_path, status_callback=None):
    """
    Save all measurements to file using REW API

    Args:
        file_path (str): Full path where to save the measurements
        status_callback: Optional callback for status updates

    Returns:
        tuple: (success, error_message)
    """
    try:
        if status_callback:
            status_callback("Saving all measurements...")

        # Ensure file has .mdat extension
        if not file_path.lower().endswith(".mdat"):
            file_path += ".mdat"

        # Use REW API to save all measurements
        payload = {"command": "Save all", "parameters": [file_path]}

        response = requests.post(
            f"{REW_API_BASE_URL}/measurements/command", json=payload
        )
        response.raise_for_status()

        # Check response
        result = response.json()
        message = result.get("message", "")

        if "Saved all measurements" in message:
            if status_callback:
                status_callback(
                    f"All measurements saved successfully to: {os.path.basename(file_path)}"
                )
            return True, None
        else:
            error_msg = f"Unexpected response: {message}"
            if status_callback:
                status_callback(f"ERROR: {error_msg}")
            return False, error_msg

    except requests.RequestException as e:
        error_msg = f"Error saving measurements: {e}"
        if status_callback:
            status_callback(f"ERROR: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error saving measurements: {e}"
        if status_callback:
            status_callback(f"ERROR: {error_msg}")
        return False, error_msg


def delete_all_measurements(status_callback=None):
    """
    Delete all measurements from REW.
    Returns (success, count_deleted, error_message).
    """
    try:
        if status_callback:
            status_callback("Deleting all existing measurements...")

        response = requests.delete(f"{REW_API_BASE_URL}/measurements")
        response.raise_for_status()

        result = response.json()
        message = result.get("message", "")

        # Extract number from message like "5 measurements deleted"
        import re

        match = re.search(r"(\d+) measurements deleted", message)
        count_deleted = int(match.group(1)) if match else 0

        if status_callback:
            if count_deleted > 0:
                status_callback(
                    f"Successfully deleted {count_deleted} existing measurements"
                )
            else:
                status_callback("No existing measurements to delete")

        return True, count_deleted, None

    except requests.RequestException as e:
        error_msg = f"Error deleting measurements: {e}"
        if status_callback:
            status_callback(f"ERROR: {error_msg}")
        return False, 0, error_msg
    except Exception as e:
        error_msg = f"Unexpected error deleting measurements: {e}"
        if status_callback:
            status_callback(f"ERROR: {error_msg}")
        return False, 0, error_msg


def get_measurement_count():
    """Get the current number of measurements in REW."""
    try:
        measurements, count = get_all_measurements()
        return count if count != -1 else 0
    except Exception:
        return 0


def get_all_measurements_with_uuid():
    """
    Get all measurements with UUID tracking.
    Returns (measurements_list, total_count) where measurements_list contains UUID and metadata.
    """
    try:
        response = requests.get(f"{REW_API_BASE_URL}/measurements")
        response.raise_for_status()
        measurement_uuids = response.json()

        measurements = []
        for id in measurement_uuids:
            try:
                meta_response = requests.get(f"{REW_API_BASE_URL}/measurements/{id}")
                meta_response.raise_for_status()
                meta = meta_response.json()
                # meta["uuid"] = uuid
                measurements.append(meta)
            except Exception as e:
                print(f"Error getting metadata for ID {id}: {e}")
                continue

        return measurements, len(measurements)
    except requests.RequestException as e:
        print(f"REW API Error: {e}")
        return None, -1


def delete_measurement_by_uuid(uuid, status_callback=None):
    """Delete a specific measurement by UUID."""
    try:
        if status_callback:
            status_callback(f"Deleting measurement {uuid}...")

        response = requests.delete(f"{REW_API_BASE_URL}/measurements/{uuid}")
        response.raise_for_status()

        result = response.json()
        message = result.get("message", "")

        if status_callback:
            status_callback(f"Deleted measurement: {message}")

        return True, None

    except requests.RequestException as e:
        error_msg = f"Error deleting measurement {uuid}: {e}"
        if status_callback:
            status_callback(f"ERROR: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error deleting measurement {uuid}: {e}"
        if status_callback:
            status_callback(f"ERROR: {error_msg}")
        return False, error_msg


def delete_measurements_by_uuid(uuid_list, status_callback=None):
    """Delete multiple measurements by UUID list."""
    deleted_count = 0
    failed_count = 0

    for uuid in uuid_list:
        success, error_msg = delete_measurement_by_uuid(uuid, status_callback)
        if success:
            deleted_count += 1
        else:
            failed_count += 1

    if status_callback:
        status_callback(f"Deleted {deleted_count} measurements, {failed_count} failed")

    return deleted_count, failed_count


def get_measurements_for_channel_with_uuid(channel):
    """
    Get all measurements for a specific channel using UUID, sorted by position.
    Returns list of {'uuid': str, 'position': int, 'title': str} dictionaries.
    """
    try:
        measurements, _ = get_all_measurements_with_uuid()
        if not measurements:
            return []

        channel_measurements = []

        for measurement in measurements:
            title = measurement.get("title", "")
            uuid = measurement.get("uuid", "")

            # Match pattern: channel_pos# (e.g., "FL_pos0", "FR_pos1")
            pattern = rf"^{re.escape(channel)}_pos(\d+)$"
            match = re.match(pattern, title, re.IGNORECASE)

            if match:
                position = int(match.group(1))
                channel_measurements.append(
                    {
                        "uuid": uuid,
                        "position": position,
                        "title": title,
                        "measurement": measurement,
                    }
                )

        # Sort by position (0 first, then 1, 2, etc.)
        channel_measurements.sort(key=lambda x: x["position"])

        return channel_measurements

    except Exception as e:
        print(f"Error getting measurements for channel {channel}: {e}")
        return []


def get_selected_channels_with_measurements_uuid(
    selected_channels, status_callback=None
):
    """
    Get measurements for all selected channels that have actual measurement data using UUIDs.
    Returns dict: {channel: [{'uuid': str, 'position': int, 'title': str}, ...]}

    Args:
        selected_channels: List of channel names to check
        status_callback: Optional callback function to report status updates
    """
    channels_with_data = {}
    channels_without_data = []

    for channel in selected_channels:
        measurements = get_measurements_for_channel_with_uuid(channel)
        if measurements:  # Only include channels that have measurements
            channels_with_data[channel] = measurements
            titles = [m["title"] for m in measurements]
            message = f"Found {len(measurements)} measurements for {channel}: {titles}"
            print(message)
            if status_callback:
                status_callback(f"✓ {channel}: {len(measurements)} measurements")
        else:
            channels_without_data.append(channel)
            message = f"No measurements found for channel {channel}"
            print(message)
            if status_callback:
                status_callback(f"⚠ {channel}: No measurements found")

    # Provide summary if callback is available
    if status_callback:
        if channels_with_data:
            summary = (
                f"Summary: {len(channels_with_data)} channels have data, "
                f"{len(channels_without_data)} channels missing"
            )
            status_callback(summary)
        else:
            status_callback("No measurements found for any selected channels")

    return channels_with_data


def start_cross_corr_align(
    channel, measurement_ids, status_callback=None, error_callback=None
):
    """
    Start cross correlation alignment process for a specific channel.
    Position 0 is used as the reference for alignment.
    """
    if status_callback:
        status_callback(f"Starting cross correlation alignment for {channel}...")

    if not measurement_ids:
        err_msg = f"No measurement IDs provided for {channel} cross correlation"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Cross Correlation Error", err_msg)
        return False, err_msg

    payload = {
        "processName": "Cross corr align",
        "measurementUUIDs": measurement_ids,
        "parameters": {},
        "resultUrl": "http://127.0.0.1:5555/rew-status",
    }

    try:
        response = requests.post(
            f"{REW_API_BASE_URL}/measurements/process-measurements", json=payload
        )
        response.raise_for_status()

        if status_callback:
            status_callback(f"Cross correlation alignment started for {channel}")

        return True, None

    except requests.RequestException as e:
        # Try to extract the error message from the response body
        err_details = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                # Try to parse JSON error response from REW
                error_data = e.response.json()
                if isinstance(error_data, dict) and "message" in error_data:
                    err_details = error_data["message"]
                elif isinstance(error_data, str):
                    err_details = error_data
            except:
                # If JSON parsing fails, try to get plain text
                err_details = e.response.text or str(e)

        err_msg = (
            f"Error starting cross correlation alignment for '{channel}': {err_details}"
        )
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Cross Correlation Error", err_details)
        return False, err_msg
    except Exception as e:
        err_msg = f"Unexpected error in cross correlation: {e}"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Error", err_msg)
        return False, err_msg


def start_vector_avg(
    channel, measurement_ids, status_callback=None, error_callback=None
):
    """
    Start vector average process for a specific channel.
    """
    if status_callback:
        status_callback(f"Starting vector averaging for {channel}...")

    if not measurement_ids:
        err_msg = f"No measurement IDs provided for {channel} vector averaging"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Vector Average Error", err_msg)
        return False, err_msg

    payload = {
        "processName": "Vector Average",
        "measurementUUIDs": measurement_ids,
        "parameters": {},
        "resultUrl": "http://127.0.0.1:5555/rew-status",
    }

    try:
        response = requests.post(
            f"{REW_API_BASE_URL}/measurements/process-measurements", json=payload
        )
        response.raise_for_status()

        if status_callback:
            status_callback(f"Vector averaging started for {channel}")

        return True, None

    except requests.RequestException as e:
        # Try to extract the error message from the response body
        err_details = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                # Try to parse JSON error response from REW
                error_data = e.response.json()
                if isinstance(error_data, dict) and "message" in error_data:
                    err_details = error_data["message"]
                elif isinstance(error_data, str):
                    err_details = error_data
            except:
                # If JSON parsing fails, try to get plain text
                err_details = e.response.text or str(e)

        err_msg = f"Error starting vector averaging for '{channel}': {err_details}"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Vector Average Error", err_details)
        return False, err_msg
    except Exception as e:
        err_msg = f"Unexpected error in vector averaging: {e}"
        if status_callback:
            status_callback(f"ERROR: {err_msg}")
        if error_callback:
            error_callback("Error", err_msg)
        return False, err_msg


def get_measurement_process_result():
    """
    Get the latest measurement process result from REW.
    Returns (process_name, new_measurement_id, message) or (None, None, None) if no result.
    """
    try:
        response = requests.get(f"{REW_API_BASE_URL}/measurements/process-result")
        response.raise_for_status()
        process_result = response.json()

        if not process_result:
            return None, None, None

        process_name = process_result.get("processName", "")
        message = process_result.get("message", "")
        results = process_result.get("results", {})

        # Extract the new measurement ID (first key in results dict)
        new_measurement_id = None
        if results:
            # The key in results dict is the new measurement ID
            new_measurement_id = next(iter(results.keys()))
            # Convert to int if it's a string
            if isinstance(new_measurement_id, str) and new_measurement_id.isdigit():
                new_measurement_id = int(new_measurement_id)

        return process_name, new_measurement_id, message

    except requests.RequestException as e:
        print(f"REW API Error getting process result: {e}")
        return None, None, None
    except Exception as e:
        print(f"Error parsing process result: {e}")
        return None, None, None


def get_measurement_uuid():
    """
    Get the latest measurement UUID from REW.
    Returns measurement_uuid or None if no result.
    """
    try:
        response = requests.get(f"{REW_API_BASE_URL}/measurements/selected-uuid")
        response.raise_for_status()
        measurement_uuid = response.json()

        if not measurement_uuid:
            return None

        return measurement_uuid

    except requests.RequestException as e:
        print(f"REW API Error getting measurement uuid: {e}")
        return None
    except Exception as e:
        print(f"Error parsing measurement uuid: {e}")
        return None


def get_measurement_by_uuid(measurement_uuid):
    """
    Get the latest measurement UUID from REW.
    Returns measurement_uuid or None if no result.
    """
    try:
        response = requests.get(f"{REW_API_BASE_URL}/measurements/{measurement_uuid}")
        response.raise_for_status()
        measurements = response.json()

        if not measurements:
            print(f"No measurements found for UUID: {measurement_uuid}")
            return None

        return measurements

    except requests.RequestException as e:
        print(f"REW API Error getting measurements for {measurement_uuid}: {e}")
        return None
    except Exception as e:
        print(f"Error parsing measurements for {measurement_uuid}: {e}")
        return None


def get_measurement_distortion_by_uuid(measurement_uuid, ppo=96):
    """
    Get the latest measurement distortion from REW with maximum resolution.

    Args:
        measurement_uuid: The measurement UUID
        ppo: Points per octave for sweep distortion (default 96 for maximum resolution)
    """
    try:
        response = requests.get(
            f"{REW_API_BASE_URL}/measurements/{measurement_uuid}/distortion?ppo={ppo}"
        )
        response.raise_for_status()
        measurement_distortion = response.json()

        if not measurement_distortion:
            print(f"No measurement distortion found for UUID: {measurement_uuid}")
            return None

        return measurement_distortion

    except requests.RequestException as e:
        print(
            f"REW API Error getting measurement distortion for {measurement_uuid}: {e}"
        )
        return None
    except Exception as e:
        print(f"Error parsing measurement distortion for {measurement_uuid}: {e}")
        return None


def rename_measurement(measurement_id, new_name, status_callback=None):
    """
    Rename a measurement in REW.
    """
    try:
        payload = {"title": new_name}
        response = requests.put(
            f"{REW_API_BASE_URL}/measurements/{measurement_id}", json=payload
        )
        response.raise_for_status()

        if status_callback:
            status_callback(f"Renamed measurement to: {new_name}")

        return True

    except Exception as e:
        print(f"Error renaming measurement {measurement_id}: {e}")
        return False


def get_last_warning():
    """Get the last warning from REW"""
    try:
        response = requests.get(f"{REW_API_BASE_URL}/application/last-warning")
        response.raise_for_status()
        warning_data = response.json()

        if warning_data:
            time_str = warning_data.get("time", "Unknown time")
            title = warning_data.get("title", "No title")
            message = warning_data.get("message", "No message")
            return f"[{time_str}] {title}: {message}"
        else:
            return "No recent warnings"

    except requests.RequestException as e:
        return f"Error getting last warning: {e}"
    except Exception as e:
        return f"Error parsing warning: {e}"


def get_last_error():
    """Get the last error from REW"""
    try:
        response = requests.get(f"{REW_API_BASE_URL}/application/last-error")
        response.raise_for_status()
        error_data = response.json()

        if error_data:
            time_str = error_data.get("time", "Unknown time")
            title = error_data.get("title", "No title")
            message = error_data.get("message", "No message")
            return f"[{time_str}] {title}: {message}"
        else:
            return "No recent errors"

    except requests.RequestException as e:
        return f"Error getting last error: {e}"
    except Exception as e:
        return f"Error parsing error: {e}"


def subscribe_to_rew_status():
    try:
        r = requests.post(
            f"{REW_API_BASE_URL}/measure/subscribe",
            json={"url": "http://127.0.0.1:5555/rew-status"},
        )
        if r.ok:
            print("✅ Subscribed to REW status updates")
        else:
            print(f"⚠️ Failed to subscribe: {r.status_code} {r.text}")
    except Exception as e:
        print(f"❌ Subscription error: {e}")


def subscribe_to_rew_warnings():
    """Subscribe to REW warnings"""
    try:
        payload = {"url": "http://127.0.0.1:5555/rew-warnings"}
        response = requests.post(
            f"{REW_API_BASE_URL}/application/warnings/subscribe", json=payload
        )
        response.raise_for_status()
        print("✅ Subscribed to REW warnings")
        return True
    except Exception as e:
        print(f"❌ Failed to subscribe to REW warnings: {e}")
        return False


def subscribe_to_rew_errors():
    """Subscribe to REW errors"""
    try:
        payload = {"url": "http://127.0.0.1:5555/rew-errors"}
        response = requests.post(
            f"{REW_API_BASE_URL}/application/errors/subscribe", json=payload
        )
        response.raise_for_status()
        print("✅ Subscribed to REW errors")
        return True
    except Exception as e:
        print(f"❌ Failed to subscribe to REW errors: {e}")
        return False


def subscribe_to_rta_distortion():
    """Subscribe to RTA distortion updates"""
    try:
        payload = {
            "url": "http://127.0.0.1:5555/rta-distortion",
            "parameters": {"unit": "SPL", "distortion": "percent"},
        }
        response = requests.post(
            f"{REW_API_BASE_URL}/rta/distortion/subscribe", json=payload
        )
        response.raise_for_status()
        print("✅ Subscribed to RTA distortion updates")
        return True
    except Exception as e:
        print(f"❌ Failed to subscribe to RTA distortion: {e}")
        return False


def unsubscribe_from_rta_distortion():
    """Unsubscribe from RTA distortion updates"""
    try:
        payload = {
            "url": "http://127.0.0.1:5555/rta-distortion",
            "parameters": {"unit": "SPL", "distortion": "percent"},
        }
        response = requests.post(
            f"{REW_API_BASE_URL}/rta/distortion/unsubscribe", json=payload
        )
        response.raise_for_status()
        print("✅ Unsubscribed from RTA distortion updates")
        return True
    except Exception as e:
        print(f"❌ Failed to unsubscribe from RTA distortion: {e}")
        return False


def set_rta_configuration(show_gui: bool = True) -> bool:
    """
    Push an RTA configuration that is well-suited for THD / THD-N work.
    Returns True on success.
    """
    payload = {
        # ── Spectrum display ──────────────────────────────────────────
        "mode": "RTA 1/24 octave",  # finer bins = better harmonic ID
        "smoothing": "None",  # keep raw
        "fftLength": "64k",
        "window": "Rectangular",  # needed for coherent THD
        # ── Averaging ─────────────────────────────────────────────────
        "averaging": "None",  # rely on coherent / x-corr modes
        "maximumOverlap": "93.75%",  # fastest update
        # ── Distortion calculation ───────────────────────────────────
        "calcDistortionEnabled": True,
        "fundamentalFromSineGen": True,  # auto-tracks REW’s generator
        # ── Auto-stop not used; we stop when VLC finishes ────────────
        "stopAt": False,
        "stopAtValue": 100,
        # ── Misc ──────────────────────────────────────────────────────
        "use64BitFFT": True,
        "restartCaptureOnGeneratorChange": False,
        "stopGeneratorWithRTA": False,  # keep generator running if user wants GUI
        "adjustRTALevels": False,
    }

    try:
        r = requests.post(
            f"{REW_API_BASE_URL}/rta/configuration", json=payload, timeout=5
        )
        r.raise_for_status()
        print("✅ RTA configured for distortion measurement")
        return True
    except Exception as e:
        print("❌  Could not configure RTA:", e)
        return False


def set_rta_distortion_configuration_sine():
    "Set RTA Distortion for Single Tone Sine Signal"
    try:
        payload = {
            "lowPass": 20000,
            "highPass": 20,
            "enableLowPass": True,
            "enableHighPass": True,
            "useManualFundamental": False,  # let REW detect the sine
            "useAES17StandardNotch": False,  # only needed for electronics THD+N
            "showHarmonicPhase": True,
            "highlightFundamental": True,
            "distortionUnit": "percent",
            "useCoherentAveraging": True,  # big S/N improvement
            "useCrossCorrelationAveraging": False,  # unnecessary with single-tone
            "monitorClockRateMatch": True,  # warns if sound-card drifts
        }

        response = requests.post(
            f"{REW_API_BASE_URL}/rta/distortion-configuration", json=payload
        )
        print("✅ RTA distortion configured for single tone sine")
        return True
    except Exception as e:
        print(f"❌ Failed to configure RTA distortion: {e}")
        return False


def set_rta_distortion_configuration_sweep():
    "Set RTA Distortion for Sweep Signal"
    try:
        payload = {
            "lowPass": 20000,
            "highPass": 20,
            "enableLowPass": True,
            "enableHighPass": True,
            "useManualFundamental": True,  # fix the Vrms of the sweep
            "manualFundamentalVrms": -12.0,  # set to the sweep’s RMS level
            "useAES17StandardNotch": False,
            "showHarmonicPhase": False,  # phase is meaningless while sweeping
            "highlightFundamental": True,
            "distortionUnit": "percent",
            "useCoherentAveraging": False,  # sweep = non-stationary
            "useCrossCorrelationAveraging": True,  # helps noise rejection
            "monitorClockRateMatch": True,
        }

        response = requests.post(
            f"{REW_API_BASE_URL}/rta/distortion-configuration", json=payload
        )
        print("✅ RTA distortion configureed")
        return True
    except Exception as e:
        print(f"❌ Failed to configure RTA distortion: {e}")
        return False


def start_rta():
    """Start RTA mode"""
    try:
        payload = {"command": "Start"}
        response = requests.post(f"{REW_API_BASE_URL}/rta/command", json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"❌ Failed to start RTA: {e}")
        return False


def stop_rta():
    """Stop RTA mode"""
    try:
        payload = {"command": "Stop"}
        response = requests.post(f"{REW_API_BASE_URL}/rta/command", json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"❌ Failed to stop RTA: {e}")
        return False


def check_rew_health():
    """Check REW's current health status"""
    try:
        last_warning = get_last_warning()
        last_error = get_last_error()

        print(f"🔍 REW Health Check:")
        print(f"   Last Warning: {last_warning}")
        print(f"   Last Error: {last_error}")

        # Return status info
        return {
            "last_warning": last_warning,
            "last_error": last_error,
            "healthy": "Error" not in last_error or "No recent errors" in last_error,
        }
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return {"healthy": False, "error": str(e)}


def check_rew_connection():
    try:
        r = requests.get(f"{REW_API_BASE_URL}", timeout=3)
        if r.ok:
            return True
    except Exception:
        pass
    return False


def initialize_rew_subscriptions():
    """Initialize all REW subscriptions"""
    print("🔄 Initializing REW subscriptions...")

    # Subscribe to status updates
    subscribe_to_rew_status()

    # Subscribe to warnings
    subscribe_to_rew_warnings()

    # Subscribe to errors
    subscribe_to_rew_errors()

    # Check initial health
    health = check_rew_health()
    if health["healthy"]:
        print("✅ REW appears healthy")
    else:
        print(f"⚠️ REW health check shows issues: {health}")
