import requests
import numpy as np
import base64
from scipy.signal import correlate
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

REW_API_BASE_URL = "http://localhost:4735"

def get_all_measurements():
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

def get_ir_for_measurement(measurement_id):
    response = requests.get(f"{REW_API_BASE_URL}/measurements/{measurement_id}/impulse-response")
    response.raise_for_status()
    ir = response.json()
    ir_base64 = ir['data']
    sample_rate = ir['sampleRate']
    start_time = ir['startTime']
    timing_ref_time = ir.get('timingRefTime', 0.0)
    timing_offset = ir.get('timingOffset', 0.0)
    delay = ir.get('delay', 0.0)
    effective_timing_ref = timing_ref_time + timing_offset + delay
    
    ir_bytes = base64.b64decode(ir_base64)
    ir_array = np.frombuffer(ir_bytes, dtype='>f4')  # REW uses big-endian float32
    
    # Handle NaN/Inf values
    if np.isnan(ir_array).sum() > 0 or np.isinf(ir_array).sum() > 0:
        ir_array = np.nan_to_num(ir_array, nan=0.0, posinf=0.0, neginf=0.0)
    
    # Normalize if values are too large
    max_val = np.max(np.abs(ir_array))
    if max_val > 10.0:
        ir_array = ir_array / max_val
    
    ir_array = np.clip(ir_array, -1.0, 1.0)
    
    return ir_array, sample_rate, start_time, effective_timing_ref

def generate_rew_frequencies(start_freq, ppo, num_points):
    """Generate REW's logarithmic frequency array."""
    step = 2 ** (1.0 / ppo)
    frequencies = np.array([start_freq * (step ** i) for i in range(num_points)])
    return frequencies

def get_frequency_response(measurement_id):
    """Get frequency response data from REW with proper decoding."""
    response = requests.get(f"{REW_API_BASE_URL}/measurements/{measurement_id}/frequency-response")
    response.raise_for_status()
    fr_data = response.json()
    
    start_freq = fr_data['startFreq']
    ppo = fr_data['ppo']
    
    # Decode magnitude and phase data (REW uses big-endian float32)
    mag_bytes = base64.b64decode(fr_data['magnitude'])
    phase_bytes = base64.b64decode(fr_data['phase'])
    
    magnitudes_db = np.frombuffer(mag_bytes, dtype='>f4')
    phases_deg = np.frombuffer(phase_bytes, dtype='>f4')
    
    frequencies = generate_rew_frequencies(start_freq, ppo, len(magnitudes_db))
    
    # Convert to complex response
    mag_linear = 10 ** (magnitudes_db / 20.0)
    phase_rad = np.radians(phases_deg)
    complex_response = mag_linear * np.exp(1j * phase_rad)
    
    return frequencies, complex_response, start_freq, ppo

def post_frequency_response(frequencies, complex_response, name="Vector Average FR", start_freq=None, ppo=None):
    """Post frequency response back to REW in the correct format."""
    magnitudes_linear = np.abs(complex_response)
    phases_rad = np.angle(complex_response)
    
    magnitudes_db = 20 * np.log10(magnitudes_linear + 1e-10)
    phases_deg = np.degrees(phases_rad)
    
    # Encode as big-endian float32 (same as REW)
    mag_bytes = magnitudes_db.astype('>f4').tobytes()
    phase_bytes = phases_deg.astype('>f4').tobytes()
    
    mag_base64 = base64.b64encode(mag_bytes).decode('utf-8')
    phase_base64 = base64.b64encode(phase_bytes).decode('utf-8')
    
    if start_freq is None:
        start_freq = frequencies[0]
    if ppo is None:
        if len(frequencies) > 1:
            ratio = frequencies[1] / frequencies[0]
            ppo = np.log(2) / np.log(ratio)
        else:
            ppo = 96
    
    payload = {
        "identifier": name,
        "unit": "SPL", 
        "smoothing": "1/48",
        "startFreq": start_freq,
        "ppo": int(ppo),
        "magnitude": mag_base64,
        "phase": phase_base64
    }
    
    response = requests.post(f"{REW_API_BASE_URL}/import/frequency-response-data", json=payload)
    
    if response.status_code == 202:
        print(f"✅ Uploaded: {name}")
        return True
    else:
        print(f"❌ Failed: {response.status_code} — {response.text}")
        return False

# REW-style cross-correlation functions
def rew_circular_shift(data, shift_samples):
    """REW's circular shift function (SweepAnalyser.B)"""
    if shift_samples == 0 or shift_samples == len(data):
        return data.copy()
    
    # Handle negative shifts
    while shift_samples < 0:
        shift_samples += len(data)
    
    # Handle shifts larger than array length
    if shift_samples > len(data):
        shift_samples %= len(data)
    
    # Perform circular shift
    temp = np.zeros(shift_samples)
    temp[:] = data[len(data) - shift_samples:]
    data[shift_samples:] = data[:len(data) - shift_samples]
    data[:shift_samples] = temp
    
    return data

def rew_hilbert_envelope(signal):
    """REW's Hilbert envelope detection (SweepAnalyser.D)"""
    n = len(signal)
    signal_copy = signal.copy()
    
    # Forward DHT 
    fft_signal = np.fft.fft(signal_copy)
    
    # Hilbert transform via frequency domain
    for i in range(1, n // 2):
        temp = fft_signal[i]
        fft_signal[i] = fft_signal[n - i]
        fft_signal[n - i] = -temp
    
    fft_signal[n // 2] = 0.0
    fft_signal[0] = 0.0
    
    # Inverse transform
    hilbert_signal = np.fft.ifft(fft_signal)
    
    # Combine with original for envelope
    envelope = np.sqrt(signal**2 + np.real(hilbert_signal)**2)
    
    return envelope

def rew_sinc_interpolate_peak(data, peak_idx, window_size=64):
    """REW's SINC interpolation for sub-sample peak detection"""
    if peak_idx <= window_size or peak_idx >= len(data) - window_size:
        # Use parabolic interpolation for edge cases
        if peak_idx == 0 or peak_idx == len(data) - 1:
            return peak_idx, data[peak_idx]
        
        y1, y2, y3 = data[peak_idx-1], data[peak_idx], data[peak_idx+1]
        denom = 2 * (2*y2 - y1 - y3)
        if abs(denom) < 1e-10:
            return peak_idx, y2
        
        offset = (y3 - y1) / denom
        refined_idx = peak_idx + offset
        
        # Parabolic interpolation for value
        a = 0.5 * (y1 + y3 - 2*y2)
        b = 0.5 * (y3 - y1)
        c = y2
        refined_val = a * offset**2 + b * offset + c
        
        return refined_idx, refined_val
    
    # Use SINC interpolation for interior points
    # Extract window around peak
    start = peak_idx - window_size
    end = peak_idx + window_size + 1
    window_data = data[start:end]
    
    # Find peak in window
    local_peak = np.argmax(window_data)
    
    # SINC interpolation (simplified version)
    x_vals = np.arange(-window_size, window_size + 1)
    peak_x = x_vals[local_peak]
    
    # Use quadratic fit around local peak for sub-sample accuracy
    if local_peak > 0 and local_peak < len(window_data) - 1:
        y1 = window_data[local_peak - 1]
        y2 = window_data[local_peak]
        y3 = window_data[local_peak + 1]
        
        denom = 2 * (2*y2 - y1 - y3)
        if abs(denom) > 1e-10:
            offset = (y3 - y1) / denom
            refined_peak_x = peak_x + offset
            
            # Calculate interpolated value
            a = 0.5 * (y1 + y3 - 2*y2)
            b = 0.5 * (y3 - y1) 
            c = y2
            refined_val = a * offset**2 + b * offset + c
            
            return start + local_peak + offset, refined_val
    
    return start + local_peak, window_data[local_peak]

def rew_prepare_ir_for_correlation(ir_data, sample_rate, start_time, timing_ref, fft_length, 
                                   reference_peak_time, ir_start_index=None, signal_squaring=True):
    """REW's IR preparation function (K.A)"""
    
    prepared = np.zeros(fft_length, dtype=np.float32)
    prepared[:len(ir_data)] = ir_data.copy()
    
    # Apply exponential decay after IR start (REW does this for better correlation)
    if ir_start_index is not None and ir_start_index > 0:
        decay_factor = 0.1
        min_decay_samples = max(int(0.01 / (1/sample_rate)), 100)  # L factor from REW
        decay_rate = np.log(decay_factor) / min_decay_samples
        
        decay_start = ir_start_index + max(int(0.001 / (1/sample_rate)), 10)
        if decay_start < len(prepared):
            for i in range(decay_start, min(len(prepared), decay_start + min_decay_samples)):
                decay_mult = np.exp(decay_rate * (i - decay_start))
                prepared[i] *= decay_mult
    
    # Calculate timing-based circular shift
    peak_time = reference_peak_time  # The G value from REW
    time_offset = (peak_time - start_time) / (1/sample_rate)
    shift_samples = int(np.round(time_offset))
    fractional_shift = time_offset - shift_samples
    
    # Apply fractional shift if needed (REW uses xI.B for this)
    if abs(fractional_shift) > 1e-6:
        # Simple linear interpolation for fractional shift
        if fractional_shift > 0:
            for i in range(len(prepared)-1, 0, -1):
                prepared[i] = prepared[i] * (1 - fractional_shift) + prepared[i-1] * fractional_shift
        else:
            fractional_shift = -fractional_shift
            for i in range(len(prepared)-1):
                prepared[i] = prepared[i] * (1 - fractional_shift) + prepared[i+1] * fractional_shift
    
    # Calculate circular shift position
    shift_pos = -shift_samples
    while shift_pos < 0:
        shift_pos += fft_length
    if shift_pos > fft_length:
        shift_pos %= fft_length
    
    # Apply circular shift
    prepared = rew_circular_shift(prepared, shift_pos)
    
    # Apply signal squaring (REW's var3 parameter)
    if signal_squaring:
        prepared = np.sign(prepared) * (prepared ** 2)
    
    # Apply FFT
    fft_data = np.fft.rfft(prepared)
    
    return fft_data

def rew_cross_correlate_fft(ref_fft, target_fft, use_hilbert=True):
    """REW's FFT-based cross-correlation"""
    min_len = min(len(ref_fft), len(target_fft))
    ref_fft = ref_fft[:min_len]
    target_fft = target_fft[:min_len]
    
    # Cross-correlation: target * conj(reference)
    correlation_fft = target_fft * np.conj(ref_fft)
    
    # Inverse FFT to get correlation
    correlation = np.fft.irfft(correlation_fft)
    
    # Apply Hilbert envelope detection if requested
    if use_hilbert:
        envelope = rew_hilbert_envelope(correlation)
    else:
        envelope = np.abs(correlation)
    
    # REW applies quarter-shift
    quarter_shift = len(correlation) // 4
    correlation = rew_circular_shift(correlation, quarter_shift)
    envelope = rew_circular_shift(envelope, quarter_shift)
    
    return {
        'correlation': correlation,
        'envelope': envelope,
        'rms': np.sqrt(np.mean(correlation**2))
    }

def rew_find_correlation_peak(correlation_result, time_limit_samples=None):
    """REW's peak finding with SINC interpolation"""
    envelope = correlation_result['envelope']
    correlation = correlation_result['correlation']
    rms = correlation_result['rms']
    
    # Find peak in envelope
    peak_idx = np.argmax(envelope)
    peak_val = envelope[peak_idx]
    
    # Apply time limit if specified (REW's var3 parameter)
    if time_limit_samples is not None:
        quarter_shift = len(correlation) // 4
        search_start = max(0, quarter_shift - time_limit_samples)
        search_end = min(len(envelope), quarter_shift + time_limit_samples + 1)
        
        # Find peak within time limit
        limited_envelope = envelope[search_start:search_end]
        if len(limited_envelope) > 0:
            local_peak_idx = np.argmax(limited_envelope)
            peak_idx = search_start + local_peak_idx
            peak_val = limited_envelope[local_peak_idx]
    
    # SINC interpolation for sub-sample accuracy
    refined_idx, refined_val = rew_sinc_interpolate_peak(envelope, peak_idx)
    
    # Convert to shift samples (handle circular correlation)
    n = len(correlation)
    shift_samples = refined_idx
    if shift_samples > n / 2:
        shift_samples -= n
    
    # Subtract quarter shift that was applied
    shift_samples -= n // 4
    
    # Calculate correlation coefficient
    corr_coeff = min(peak_val / (rms + 1e-10), 1.0)
    
    return {
        'shift_samples': shift_samples,
        'peak_value': refined_val,
        'correlation': corr_coeff
    }

def rew_cross_correlation_align(measurements_data, max_iterations=10, convergence_threshold=0.005):
    """REW's complete cross-correlation alignment algorithm"""
    
    if len(measurements_data) < 2:
        return [0.0] * len(measurements_data)
    
    # Get reference measurement
    ref_ir, sample_rate, ref_start_time, ref_timing_ref, ref_title = measurements_data[0]
    
    # Determine FFT length (REW uses max windowed span, min 16384)
    max_length = max(len(data[0]) for data in measurements_data)
    fft_length = max(2 ** int(np.ceil(np.log2(max_length))), 16384)
    
    # Calculate reference peak time (REW's G value)
    reference_peak_time = ref_timing_ref  # Use timing reference as peak time
    
    # Prepare reference FFT
    ref_fft_data = rew_prepare_ir_for_correlation(
        ref_ir, sample_rate, ref_start_time, ref_timing_ref, 
        fft_length, reference_peak_time
    )
    
    # Initialize shifts
    accumulated_shifts = [0.0]
    print(f"   Reference: {ref_title}")
    
    # Main alignment loop (up to 10 iterations like REW)
    for iteration in range(max_iterations):
        max_shift_this_iteration = 0.0
        iteration_shifts = [0.0]  # Reference has no shift
        
        # Process each measurement
        for i, (ir, sample_rate, start_time, timing_ref, title) in enumerate(measurements_data[1:], 1):
            # Prepare target FFT
            target_fft_data = rew_prepare_ir_for_correlation(
                ir, sample_rate, start_time, timing_ref,
                fft_length, reference_peak_time
            )
            
            # Cross-correlate
            correlation_result = rew_cross_correlate_fft(ref_fft_data, target_fft_data, use_hilbert=True)
            
            # Find peak with time limit (REW uses L factor)
            peak_info = rew_find_correlation_peak(correlation_result, time_limit_samples=None)
            
            # Calculate time shift
            time_shift = peak_info['shift_samples'] / sample_rate
            iteration_shifts.append(time_shift)
            max_shift_this_iteration = max(max_shift_this_iteration, abs(time_shift))
            
            print(f"   Iteration {iteration + 1}, {title}: shift = {time_shift * 1000:.2f}ms, corr = {peak_info['correlation']:.3f}")
        
        # Accumulate shifts
        for i in range(len(iteration_shifts)):
            if i >= len(accumulated_shifts):
                accumulated_shifts.append(0.0)
            accumulated_shifts[i] += iteration_shifts[i]
        
        # Check convergence
        if max_shift_this_iteration < convergence_threshold:
            print(f"   Converged after {iteration + 1} iterations (max shift: {max_shift_this_iteration * 1000:.2f}ms)")
            break
    
    return accumulated_shifts

def apply_time_shift_to_frequency_response(frequencies, complex_response, time_shift):
    """Apply time shift as phase correction to frequency response."""
    phase_correction = -2 * np.pi * frequencies * time_shift
    phase_corrected_response = complex_response * np.exp(1j * phase_correction)
    return phase_corrected_response

def fetch_align_upload_frequency_responses_rew_accurate(channel_prefix):
    print(f"🔍 Fetching measurements for: {channel_prefix}_")
    
    measurements, _ = get_all_measurements()
    selected = [(m['id'], m.get('title', '')) for m in measurements 
                if m.get('title', '').startswith(f"{channel_prefix}_pos")]
    selected = sorted(selected, key=lambda x: int(x[1].split("pos")[-1]))
    
    if not selected:
        print(f"⚠️  No matching measurements found")
        return
    
    print(f"\n📥 Downloading {len(selected)} measurements...")
    
    # Get IR data
    measurements_data = []
    for i, (m_id, m_title) in enumerate(selected):
        print(f"Processing {m_title}:")
        ir, sample_rate, start_time, timing_ref = get_ir_for_measurement(m_id)
        measurements_data.append((ir, sample_rate, start_time, timing_ref, m_title))
    
    # Perform REW-style cross-correlation alignment
    print(f"\n🔧 REW-style cross-correlation alignment...")
    shifts = rew_cross_correlation_align(measurements_data)
    
    # Process frequency responses
    print(f"\n📡 Processing frequency responses...")
    frequency_responses = []
    frequencies = None
    reference_start_freq = None
    reference_ppo = None
    
    for i, (m_id, m_title) in enumerate(selected):
        print(f"Getting FR for {m_title}:")
        freqs, complex_fr, start_freq, ppo = get_frequency_response(m_id)
        
        if frequencies is None:
            frequencies = freqs
            reference_start_freq = start_freq
            reference_ppo = ppo
        
        # Apply time shift as phase correction
        if shifts[i] != 0:
            complex_fr = apply_time_shift_to_frequency_response(freqs, complex_fr, shifts[i])
            print(f"   Applied {shifts[i] * 1000:.2f} ms phase correction")
        
        frequency_responses.append(complex_fr)
    
    # Compute vector average
    print(f"\n🧮 Computing vector average...")
    vector_average = np.mean(frequency_responses, axis=0)
    
    # Upload results
    print(f"\n📤 Uploading results...")
    for i, (complex_fr, shift, m_title) in enumerate(zip(frequency_responses, shifts, [title for _, title in selected])):
        aligned_name = f"{channel_prefix}_REW_aligned_FR_pos{i}"
        post_frequency_response(frequencies, complex_fr, name=aligned_name, 
                              start_freq=reference_start_freq, ppo=reference_ppo)
    
    post_frequency_response(frequencies, vector_average, name=f"{channel_prefix}_REW_vector_avg_FR",
                          start_freq=reference_start_freq, ppo=reference_ppo)
    
    # Plot results
    plot_frequency_responses(frequencies, frequency_responses, vector_average, selected, channel_prefix)
    
    print("\n✅ REW-accurate alignment complete!")

def plot_frequency_responses(frequencies, frequency_responses, vector_average, selected, channel_prefix):
    """Plot frequency responses and vector average."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    # Plot magnitude responses
    for i, (complex_fr, (_, title)) in enumerate(zip(frequency_responses, selected)):
        magnitude_db = 20 * np.log10(np.abs(complex_fr) + 1e-10)
        ax1.semilogx(frequencies, magnitude_db, alpha=0.6, label=title)
    
    # Plot vector average
    vector_mag_db = 20 * np.log10(np.abs(vector_average) + 1e-10)
    ax1.semilogx(frequencies, vector_mag_db, 'k-', linewidth=2, label='Vector Average')
    
    ax1.set_xlabel('Frequency (Hz)')
    ax1.set_ylabel('Magnitude (dB)')
    ax1.set_title(f'{channel_prefix} - REW-Style Phase-Aligned Frequency Responses')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(20, 20000)
    
    # Plot phase responses
    for i, (complex_fr, (_, title)) in enumerate(zip(frequency_responses, selected)):
        phase_deg = np.degrees(np.unwrap(np.angle(complex_fr)))
        ax2.semilogx(frequencies, phase_deg, alpha=0.6, label=title)
    
    # Plot vector average phase
    vector_phase_deg = np.degrees(np.unwrap(np.angle(vector_average)))
    ax2.semilogx(frequencies, vector_phase_deg, 'k-', linewidth=2, label='Vector Average')
    
    ax2.set_xlabel('Frequency (Hz)')
    ax2.set_ylabel('Phase (degrees)')
    ax2.set_title(f'{channel_prefix} - Phase Responses (After REW-Style Alignment)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(20, 20000)
    
    plt.tight_layout()
    plt.show()

def post_ir(ir_data, name="Aligned IR", sample_rate=48000, start_time=0):
    """Upload IR data back to REW using big-endian float32 format."""
    ir_bytes = ir_data.astype('>f4').tobytes()
    ir_base64 = base64.b64encode(ir_bytes).decode("utf-8")
    
    payload = {
        "identifier": name,
        "startTime": start_time,
        "sampleRate": sample_rate,
        "splOffset": 0,
        "applyCal": False,
        "data": ir_base64
    }

    response = requests.post(
        f"{REW_API_BASE_URL}/import/impulse-response-data",
        json=payload
    )

    if response.status_code == 202:
        print(f"✅ Uploaded: {name}")
        return True
    else:
        print(f"❌ Failed: {response.status_code} — {response.text}")
        return False

def apply_shift_to_ir(ir_data, time_shift, sample_rate):
    """Apply calculated time shift to IR data for upload."""
    shift_samples = int(time_shift * sample_rate)
    
    if shift_samples == 0:
        return ir_data.copy()
    elif shift_samples > 0:
        # Positive shift: add zeros at beginning
        return np.concatenate([np.zeros(shift_samples), ir_data])
    else:
        # Negative shift: remove samples from beginning
        return ir_data[-shift_samples:]

def calculate_rew_metrics_from_ir(ir_data, sample_rate, harm_factor=0.5):
    """
    Calculate metrics exactly like REW using impulse response data.
    """
    import base64
    import numpy as np
    
    # Decode the IR data
 #   ir_data_b64 = ir_json['data']
 #   ir_data = np.frombuffer(base64.b64decode(ir_data_b64), dtype=np.float32)
    
   # sample_rate = ir_json['sampleRate']
    T = 1.0 / sample_rate  # Sample interval
    
    # Step 1: Find the absolute maximum (peak) index
    abs_max_idx = np.argmax(np.abs(ir_data))
    
    # Step 2: Calculate time window based on harmonic factor
    time_window = harm_factor * np.log(2.0)
    window_samples = int(round(time_window / T))
    
    # Step 3: Define analysis regions
    analysis_start = abs_max_idx - window_samples // 4
    window_size = len(ir_data) // 4
    
    # Ensure we don't go out of bounds
    analysis_start = max(0, analysis_start)
    window_size = min(window_size, len(ir_data) - analysis_start)
    
    # Step 4: Calculate power in each region
    
    # SIGNAL REGION: After the peak (direct sound)
    signal_start = analysis_start
    signal_end = min(signal_start + window_size, len(ir_data))
    signal_power = np.sum(ir_data[signal_start:signal_end] ** 2)
    peak_signal_power = np.max(ir_data[signal_start:signal_end] ** 2)
    
    # DISTORTION REGION: Before the peak (early reflections)
    dist_start = max(0, analysis_start - window_size)
    dist_end = analysis_start
    if dist_end > dist_start:
        dist_power = np.max(ir_data[dist_start:dist_end] ** 2)
    else:
        dist_power = 1e-10  # Avoid log(0)
    
    # NOISE REGION: Further before the peak
    noise_start = max(0, dist_start - window_size)
    noise_end = dist_start
    if noise_end > noise_start:
        noise_power = np.sum(ir_data[noise_start:noise_end] ** 2)
    else:
        noise_power = 1e-10  # Avoid log(0)
    
    # Step 5: Convert to dBFS
    signal_dbfs = 10 * np.log10(signal_power)
    dist_dbfs = 10 * np.log10(dist_power)
    noise_dbfs = 10 * np.log10(noise_power)
    
    # Step 6: Calculate ratios (exactly like REW)
    signal_to_noise_db = signal_dbfs - noise_dbfs
    signal_to_dist_db = 10 * np.log10(peak_signal_power) - dist_dbfs
    
    return {
        'signal_dbfs': signal_dbfs,
        'dist_dbfs': dist_dbfs,
        'noise_dbfs': noise_dbfs,
        'snr_db': signal_to_noise_db,
        'sdr_db': signal_to_dist_db,
        'peak_idx': abs_max_idx,
        'analysis_regions': {
            'signal': (signal_start, signal_end),
            'distortion': (dist_start, dist_end), 
            'noise': (noise_start, noise_end)
        }
    }

def fetch_align_upload_impulse_response_rew_accurate(channel_prefix):
    print(f"🔍 Fetching measurements for: {channel_prefix}_")

    measurements, _ = get_all_measurements()
    selected = [(m['id'], m.get('title', '')) for m in measurements 
                if m.get('title', '').startswith(f"{channel_prefix}_pos")]
    selected = sorted(selected, key=lambda x: int(x[1].split("pos")[-1]))

    if not selected:
        print(f"⚠️  No matching measurements found")
        return

    print(f"\n📥 Downloading {len(selected)} impulse responses...")

    # Get IR data for REW-style alignment
    measurements_data = []
    original_irs = []
    original_start_times = []
    
    for i, (m_id, m_title) in enumerate(selected):
        print(f"Processing {m_title}:")
        ir, sample_rate, start_time, timing_ref = get_ir_for_measurement(m_id)
        rew_metrics = calculate_rew_metrics_from_ir(ir, sample_rate)

        measurements_data.append((ir, sample_rate, start_time, timing_ref, m_title))
        original_irs.append(ir)
        original_start_times.append(start_time)

    if len(measurements_data) < 2:
        print("❌ Need at least 2 measurements for alignment")
        return

    # Perform REW-style cross-correlation alignment
    print(f"\n🔧 REW-style cross-correlation alignment...")
    shifts = rew_cross_correlation_align(measurements_data)

    # Apply shifts to original IRs and prepare for upload
    print(f"\n📊 Preparing aligned IRs for upload...")
    aligned_irs = []
    final_start_times = []
    
    reference_start_time = original_start_times[0]
    
    for i, (original_ir, original_start_time, shift) in enumerate(zip(original_irs, original_start_times, shifts)):
        if i == 0:
            # Reference IR - no shift needed
            aligned_ir = original_ir.copy()
            final_start_time = original_start_time
        else:
            # Apply calculated shift to IR
            aligned_ir = apply_shift_to_ir(original_ir, shift, sample_rate)
            final_start_time = original_start_time + shift
            
            # Ensure same length as reference
            if len(aligned_ir) > len(original_irs[0]):
                aligned_ir = aligned_ir[:len(original_irs[0])]
            elif len(aligned_ir) < len(original_irs[0]):
                aligned_ir = np.pad(aligned_ir, (0, len(original_irs[0]) - len(aligned_ir)), mode='constant')
        
        aligned_irs.append(aligned_ir)
        final_start_times.append(final_start_time)
        
        sample_shift = int(shift * sample_rate)
        print(f"   {selected[i][1]}: shift = {sample_shift:+3d} samples ({shift*1000:+5.2f} ms)")

    # Compute vector average
    print(f"\n🧮 Computing vector average...")
    vector_average_ir = np.mean(aligned_irs, axis=0)

    # Upload aligned IRs
    print(f"\n📤 Uploading REW-aligned IRs and vector average...")
    
    for i, (aligned_ir, final_start_time, (_, title)) in enumerate(zip(aligned_irs, final_start_times, selected)):
        aligned_name = f"{channel_prefix}_REW_aligned_IR_pos{i}"
        print(f"   {aligned_name}: start_time = {final_start_time:.6f}s, max = {np.max(np.abs(aligned_ir)):.6f}")
        post_ir(aligned_ir, name=aligned_name, sample_rate=sample_rate, start_time=final_start_time)

    # Upload vector average with reference timing
    post_ir(vector_average_ir, name=f"{channel_prefix}_REW_vector_avg_IR", 
            sample_rate=sample_rate, start_time=reference_start_time)

    # Plot aligned IRs for verification
    plot_aligned_irs(aligned_irs, [title for _, title in selected], sample_rate, channel_prefix)

    print("\n✅ REW-accurate IR alignment complete!")

def plot_aligned_irs(aligned_irs, titles, sample_rate, channel_prefix):
    """Plot aligned impulse responses for verification."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    # Plot first 50ms
    plot_samples = int(0.05 * sample_rate)
    time_ms = np.arange(plot_samples) / sample_rate * 1000
    
    for ir, title in zip(aligned_irs, titles):
        ax1.plot(time_ms, ir[:plot_samples], alpha=0.7, label=title)
    
    # Plot vector average
    vector_avg = np.mean(aligned_irs, axis=0)
    ax1.plot(time_ms, vector_avg[:plot_samples], 'k-', linewidth=2, label='Vector Average')
    
    ax1.set_xlabel('Time (ms)')
    ax1.set_ylabel('Amplitude')
    ax1.set_title(f'{channel_prefix} - REW-Style Aligned Impulse Responses (0-50ms)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot onset detail (first 5ms)
    zoom_samples = int(0.005 * sample_rate)
    time_zoom = np.arange(zoom_samples) / sample_rate * 1000
    
    for ir, title in zip(aligned_irs, titles):
        # Find onset for each IR
        onset_idx = find_ir_onset_rew_style(ir, sample_rate)
        start = max(0, onset_idx - int(0.001 * sample_rate))
        end = min(len(ir), start + zoom_samples)
        
        if end > start:
            ax2.plot(time_zoom[:end-start], ir[start:end], alpha=0.7, label=title)
    
    # Plot vector average onset
    vector_onset_idx = find_ir_onset_rew_style(vector_avg, sample_rate)
    start = max(0, vector_onset_idx - int(0.001 * sample_rate))
    end = min(len(vector_avg), start + zoom_samples)
    if end > start:
        ax2.plot(time_zoom[:end-start], vector_avg[start:end], 'k-', linewidth=2, label='Vector Average')
    
    ax2.set_xlabel('Time (ms)')
    ax2.set_ylabel('Amplitude')
    ax2.set_title(f'{channel_prefix} - Onset Detail (REW-Style Aligned)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()

def find_ir_onset_rew_style(ir_data, sample_rate, harm_factor=0.0, threshold_db=-20):
    """REW-style impulse start detection for plotting."""
    envelope = np.abs(ir_data)
    
    # Smooth envelope
    window_size = int(0.001 * sample_rate)
    if window_size > 1:
        envelope = np.convolve(envelope, np.ones(window_size)/window_size, mode='same')
    
    max_val = np.max(envelope)
    max_idx = np.argmax(envelope)
    
    if max_val == 0:
        return 0
    
    # Calculate search window
    if harm_factor > 0.0:
        search_window = int(np.log(2.0) * harm_factor / 2.0 / (1/sample_rate))
        search_start = max(max_idx - search_window, 0)
    else:
        search_start = max(max_idx - int(0.15 * (1/sample_rate)), 0)
    
    if search_start < 1:
        search_start = 1
    
    # Find threshold crossing
    threshold = max_val * (10 ** (threshold_db / 20))
    
    for i in range(search_start, max_idx):
        if envelope[i] > threshold:
            return max(1, i-1)
    
    return max_idx

if __name__ == "__main__":
    fetch_align_upload_impulse_response_rew_accurate("C")
    fetch_align_upload_frequency_responses_rew_accurate("TRL")
