# Qrew_measurement_metrics.py
""" """
import numpy as np
import pandas as pd
import base64


def _scale(value, low, high, max_pts, inverse=False):
    """
    Linearly map *value* from [low … high] to 0 … max_pts
    (clamped).  If inverse=True low/high are swapped so that
    *smaller* values score higher (useful for THD etc.).
    """
    if inverse:
        value = high - value + low  # flip the axis
    frac = (value - low) / (high - low)
    return float(np.clip(frac, 0.0, 1.0) * max_pts)


def calculate_rew_metrics_from_ir(ir, harm_factor=0.5):
    """
    Calculate metrics exactly like REW using impulse response data.
    """

    ir_base64 = ir["data"]
    sample_rate = ir["sampleRate"]
    start_time = ir["startTime"]
    timing_ref_time = ir.get("timingRefTime", 0.0)
    timing_offset = ir.get("timingOffset", 0.0)
    delay = ir.get("delay", 0.0)
    effective_timing_ref = timing_ref_time + timing_offset + delay

    ir_bytes = base64.b64decode(ir_base64)
    ir_array = np.frombuffer(ir_bytes, dtype=">f4")  # REW uses big-endian float32
    ir_array = ir_array / 100  # change from percentage values
    # Handle NaN/Inf values
    if np.isnan(ir_array).sum() > 0 or np.isinf(ir_array).sum() > 0:
        ir_array = np.nan_to_num(ir_array, nan=0.0, posinf=0.0, neginf=0.0)
    """
    # Normalize if values are too large
    max_val = np.max(np.abs(ir_array))
    if max_val > 10.0:
        ir_array = ir_array / max_val
    
    ir_array = np.clip(ir_array, -1.0, 1.0)

    """
    T = 1.0 / sample_rate  # Sample interval

    # Step 1: Find the absolute maximum (peak) index
    abs_max_idx = np.argmax(np.abs(ir_array))
    peak_value = np.abs(ir_array[abs_max_idx])
    peak_time_sec = start_time + (abs_max_idx * T)

    # Convert to milliseconds
    peak_time_ms = peak_time_sec * 1000
    # Step 2: Calculate time window based on harmonic factor
    time_window = harm_factor * np.log(2.0)
    window_samples = int(round(time_window / T))

    # Step 3: Define analysis regions
    analysis_start = abs_max_idx - window_samples // 4
    window_size = len(ir_array) // 4

    # Ensure we don't go out of bounds
    analysis_start = max(0, analysis_start)
    window_size = min(window_size, len(ir_array) - analysis_start)

    # Step 4: Calculate power in each region

    # SIGNAL REGION: After the peak (direct sound)
    signal_start = analysis_start
    signal_end = min(signal_start + window_size, len(ir_array))
    signal_power = np.sum(ir_array[signal_start:signal_end] ** 2)
    peak_signal_power = np.max(ir_array[signal_start:signal_end] ** 2)

    # DISTORTION REGION: Before the peak (early reflections)
    dist_start = max(0, analysis_start - window_size)
    dist_end = analysis_start
    if dist_end > dist_start:
        dist_power = np.max(ir_array[dist_start:dist_end] ** 2)
    else:
        dist_power = 1e-10  # Avoid log(0)

    # NOISE REGION: Further before the peak
    noise_start = max(0, dist_start - window_size)
    noise_end = dist_start
    if noise_end > noise_start:
        noise_power = np.sum(ir_array[noise_start:noise_end] ** 2)
    else:
        noise_power = 1e-10  # Avoid log(0)

    # Step 5: Convert to dBFS
    signal_dbfs = 10 * np.log10(signal_power)
    dist_dbfs = 10 * np.log10(dist_power)
    noise_dbfs = 10 * np.log10(noise_power)

    # Step 6: Calculate ratios (exactly like REW)
    signal_to_noise_db = signal_dbfs - noise_dbfs
    signal_to_dist_db = 10 * np.log10(peak_signal_power) - dist_dbfs
    peak_dbfs = 20 * np.log10(max(peak_value, 1e-12))  # protect log(0)
    ir_pk_noise = peak_dbfs - noise_dbfs  # dB difference

    return {
        "detail": {
            "signal_dbfs": signal_dbfs,
            "dist_dbfs": dist_dbfs,
            "noise_dbfs": noise_dbfs,
            "snr_dB": signal_to_noise_db,
            "sdr_dB": signal_to_dist_db,
            "peak_idx": abs_max_idx,
            "peak_value": peak_value,
            "peak_time_ms": peak_time_ms,
            "ir_pk_noise_dB": ir_pk_noise,
            "analysis_regions": {
                "signal": (signal_start, signal_end),
                "distortion": (dist_start, dist_end),
                "noise": (noise_start, noise_end),
            },
        }
    }


def evaluate_measurement(
    thd_json: dict,
    info_json: dict,
    coherence_array=None,  # Optional[np.ndarray]
    freq_band: tuple = (20, 20000),
) -> dict:
    """
    Combine THD, impulse-response SNR and (optionally) coherence
    into a single 0-100 ‘measurement-quality’ score.

    Parameters
    ----------
    thd_json : dict
        The JSON REW returns after `/measurement/{id}/distortion`.
    info_json : dict
        JSON from `/measurements/{id}` – requires key ``signalToNoisedB``.
    ir_json : dict
        JSON from `/impulse_response/{id}`
    coherence_array : 1-D np.ndarray, optional
        Magnitude-squared coherence over the FFT bins that match THD bins.
        If omitted the coherence term is skipped (score max = 85).
    freq_band : (low, high)
        Band over which “mean THD” is computed.

    Returns
    -------
    dict with keys
        score        : 0-100 float
        rating       : 'PASS' | 'CAUTION' | 'RETAKE'
        detail       : sub-scores for inspection
    """
    # --- unpack THD ---------------------------------------------------
    cols = thd_json["columnHeaders"]
    data = pd.DataFrame(thd_json["data"], columns=cols)
    freqs = data["Freq (Hz)"]
    thd = data["THD (%)"]

    if "Noise (%)" in data.columns:
        noise = data["Noise (%)"]
        noise = noise / 10000
        has_noise_data = True
    else:
        noise = pd.Series(np.zeros(len(thd)))
        has_noise_data = False
        print("Warning: No 'Noise (%)' column found, SDR will be THD-only")

    # Fix REW API bug - THD values appear to be multiplied by 10000
    # Check if values are unreasonably high (>100% THD is very rare)
    if thd.max() > 100:
        print(
            f"THD values appear to be scaled incorrectly (max: {thd.max():.1f}%), dividing by 10000"
        )
        thd = thd / 10000
        # Also fix harmonic columns if present
        for col in [
            "H2 (%)",
            "H3 (%)",
            "H4 (%)",
            "H5 (%)",
            "H6 (%)",
            "H7 (%)",
            "H8 (%)",
            "H9 (%)",
        ]:
            if col in data.columns:
                data[col] = data[col] / 10000

    # Band-limited THD statistics
    band_mask = (freqs >= freq_band[0]) & (freqs <= freq_band[1])
    thd_band = thd[band_mask]
    noise_band = noise[band_mask]

    # Calculate THD+N (Root Sum of Squares)
    thd_plus_n_band = (thd_band**2 + noise_band**2) ** 0.5

    mean_thd = thd_band.mean()
    max_thd = thd_band.max()
    mean_thd_n = thd_plus_n_band.mean()
    max_thd_n = thd_plus_n_band.max()

    # Low frequency analysis
    low_mask = freqs < 200
    if low_mask.any():
        thd_low = thd[low_mask]
        noise_low = noise[low_mask]
        thd_plus_n_low = (thd_low**2 + noise_low**2) ** 0.5
        low_thd = thd_low.mean()
        low_thd_n = thd_plus_n_low.mean()
    else:
        low_thd = mean_thd
        low_thd_n = mean_thd_n

    # Calculate REW-style SDR using THD+N
    def calculate_sdr(thd_n_percent):
        if thd_n_percent <= 0:
            return 100.0
        return -20 * np.log10(thd_n_percent)  # / 100)

    mean_sdr = calculate_sdr(mean_thd_n)
    max_sdr = calculate_sdr(max_thd_n)  # Worst SDR (highest distortion+noise)
    low_sdr = calculate_sdr(low_thd_n)

    # Harmonic analysis (unchanged)
    h2 = data.get("H2 (%)", pd.Series(np.zeros(len(thd))))
    h3 = data.get("H3 (%)", pd.Series(np.zeros(len(thd))))
    valid_mask = h2 > 0
    if valid_mask.any():
        h3_h2_ratio = (h3[valid_mask] / h2[valid_mask]).median()
    else:
        h3_h2_ratio = 0

    # SNR from measurement info
    snr = info_json.get("signalToNoisedB", 0.0)

    # Coherence (unchanged)
    if coherence_array is not None:
        coh_mean = np.nanmean(coherence_array)
    else:
        coh_mean = None
    """
    # Scoring (unchanged)
    score = 0
    # 1. SNR (max 25)
    score += np.clip((snr - 40) / 40 * 25, 0, 25)          # 40-80 dB → 0-25

    # 2. Coherence (max 15)
    if coh_mean is not None:
        score += np.clip((coh_mean - 0.9) / 0.1 * 15, 0, 15)

    # 3. THD metrics (max 45)
    score += np.clip((2.0 - mean_thd) / 2.0 * 25, 0, 25)   # mean ≤2 %
    score += np.clip((6.0 - max_thd)  / 6.0 * 10, 0, 10)   # spike <6 %
    score += np.clip((5.0 - low_thd)  / 5.0 * 5,  0,  5)   # LF  ≤5 %
    score += np.clip((0.7 - h3_h2_ratio) / 0.7 * 5, 0, 5)  # H3/H2 <0.7

    score = 0.0

    # 1 · Signal-to-Noise Ratio  (55-75 dB → 0-20 pts)
    score += _scale(snr, 55, 75, 20)

    # 2 · Signal-to-Distortion-Ratio (SDR)  (65-85 dB → 0-15 pts)
    score += _scale(sdr, 65, 85, 15)

    # 3 · Mean broadband THD  (2 %→0 pts … 0.2 %→15 pts)
    score += _scale(mean_thd, 2.0, 0.2, 15, inverse=True)

    # 4 · Worst narrow-band THD spike  (10 %→0 … 1 %→10)
    score += _scale(max_thd, 10.0, 1.0, 10, inverse=True)

    # 5 · Low-frequency THD (20-200 Hz)  (15 %→0 … 4 %→5)
    score += _scale(low_thd, 15.0, 4.0, 5, inverse=True)

    # 6 · Odd-order harshness  H3/H2 (1.0→0 … 0.2→5)
    score += _scale(h3_h2_ratio, 1.0, 0.2, 5, inverse=True)

    # 7 · Coherence mean  (0.90→0 … 0.99→15)
    score += _scale(coh_mean, 0.90, 0.99, 15)

    # 8 · IR peak-to-noise  (35 dB→0 … 55 dB→15)
    score += _scale(ir_peak_noise, 35, 55, 15)

    score = round(float(np.clip(score, 0, 100)), 1)

    if score >= 70:
        rating = "PASS"
    elif score >= 50:
        rating = "CAUTION"
    else:
        rating = "RETAKE"
    """
    return {
        #  "score": score,
        # "rating": rating,
        "detail": {
            "snr_dB": snr,
            "coh_mean": coh_mean,
            "mean_thd_%": mean_thd,
            "max_thd_%": max_thd,
            "low_thd_%": low_thd,
            "h3/h2_ratio": h3_h2_ratio,
            "mean_sdr_dB": mean_sdr,  # Now REW-compatible!
            "max_sdr_dB": max_sdr,  # Worst-case SDR
            "low_sdr_dB": low_sdr,  # Low-frequency SDR
            "mean_thd_n_%": mean_thd_n,  # THD+N values for reference
            "max_thd_n_%": max_thd_n,
            "low_thd_n_%": low_thd_n,
        }
    }


def combine_and_score_metrics(rew_metrics, freq_metrics):
    """
    Score the IR-related metrics (`rew_metrics`) and the frequency-domain /
    THD metrics (`freq_metrics`) and return a single score / rating.
    """

    r_det = rew_metrics.get("detail", {})
    f_det = freq_metrics.get("detail", {})

    # IR-derived
    snr_dB = r_det.get("snr_dB", 0.0)
    sdr_dB = r_det.get("sdr_dB", 0.0)
    ir_peak_noise_dB = r_det.get("ir_pk_noise_dB", 0.0)

    # frequency-domain / THD derived
    coh_mean = f_det.get("coh_mean", 0.0)
    mean_thd = f_det.get("mean_thd_%", 0.0)
    max_thd = f_det.get("max_thd_%", 0.0)
    low_thd = f_det.get("low_thd_%", 0.0)
    h3_h2_ratio = f_det.get("h3/h2_ratio", 0.0)

    score = 0.0

    # 1 · Signal-to-Noise Ratio  (40-80 dB → 0-20 pts)
    score += _scale(snr_dB, 20, 75, 20)

    # 2 · Signal-to-Distortion-Ratio (SDR)  (35-55 dB → 0-15 pts)
    score += _scale(sdr_dB, 20, 55, 15)

    # 3 · Mean broadband THD  (2 %→0 pts … 0.0 %→15 pts)
    score += _scale(mean_thd, 2.0, 0.0, 15, inverse=True)

    # 4 · Worst narrow-band THD spike  (10 %→0 … 0 %→10)
    score += _scale(max_thd, 10.0, 0.0, 10, inverse=True)

    # 5 · Low-frequency THD (20-200 Hz)  (15 %→0 … 0 %→5)
    score += _scale(low_thd, 15.0, 0.0, 5, inverse=True)

    # 6 · Odd-order harshness  H3/H2 (1.0→0 … 0→5)
    score += _scale(h3_h2_ratio, 1.0, 0.0, 5, inverse=True)

    # 7 · Coherence mean  (0.90→0 … 0.99→15)
    if coh_mean is not None:
        score += _scale(coh_mean, 0.90, 0.99, 15)
    else:
        score += 0

    # 8 · IR peak-to-noise  (35 dB→0 … 55 dB→15)
    score += _scale(ir_peak_noise_dB, 35, 55, 15)

    score = round(float(np.clip(score, 0, 100)), 1)

    if score >= 70:
        rating = "PASS"
    elif score >= 50:
        rating = "CAUTION"
    else:
        rating = "RETAKE"

    return {"score": score, "rating": rating}


def combine_sweep_and_rta_results(sweep_result, rta_result):
    """Combine sweep measurement and RTA verification results"""
    if not rta_result:
        return sweep_result

    # Start with sweep score
    combined_score = sweep_result["score"]

    # RTA-based adjustments
    rta_thd = rta_result["thd_mean"]
    rta_stability = rta_result["stability_good"]
    rta_enob = rta_result["enob_mean"]
    rta_snr = rta_result["snr_mean"]
    rta_thd_plus_n = rta_result.get("thdPlusN", {}).get("value", 0)
    rta_snr = rta_result.get("snrdB", 0)
    enob = rta_result.get("enob", 0)
    imd = rta_result.get("imd", {}).get("value", 0)

    # ENOB bonus (max 15 points)
    combined_score += np.clip((enob - 12) / 4 * 15, 0, 15)  # 12-16 ENOB range

    # IMD penalty (subtract up to 10 points)
    combined_score -= np.clip(imd * 2, 0, 10)  # IMD > 5% = -10 points

    # THD+N consideration (use if better than sweep THD)
    if rta_thd_plus_n < sweep_result["detail"]["mean_thd_%"]:
        combined_score += 5  # Bonus for better real-time measurement

    # Stability bonus/penalty
    if rta_stability:
        combined_score += 5
        stability_note = "stable"
    else:
        combined_score -= 10
        stability_note = "unstable"

    # ENOB adjustment
    if rta_enob > 14:
        combined_score += 5
    elif rta_enob < 10:
        combined_score -= 10

    # SNR adjustment from RTA
    if rta_snr > 80:
        combined_score += 3
    elif rta_snr < 50:
        combined_score -= 5

    # Consistency check between sweep and RTA THD
    sweep_thd = sweep_result["detail"]["mean_thd_%"]
    thd_difference = abs(rta_thd - sweep_thd)

    if thd_difference < 0.5:
        combined_score += 3  # Good consistency
        consistency_note = "consistent"
    elif thd_difference > 2.0:
        combined_score -= 5  # Poor consistency
        consistency_note = "inconsistent"
    else:
        consistency_note = "moderate"

    # Clamp score
    combined_score = np.clip(combined_score, 0, 100)

    # Determine rating
    if combined_score >= 70:
        rating = "PASS"
    elif combined_score >= 50:
        rating = "CAUTION"
    else:
        rating = "RETAKE"

    # Enhanced detail
    enhanced_detail = sweep_result["detail"].copy()
    enhanced_detail.update(
        {
            "rta_thd_mean_%": round(rta_thd, 3),
            "rta_thd_plus_n_%": round(rta_result["thd_plus_n_mean"], 3),
            "rta_snr_dB": round(rta_snr, 2),
            "rta_enob": round(rta_enob, 2),
            "rta_stability": stability_note,
            "thd_consistency": consistency_note,
            "rta_samples": rta_result["stable_samples"],
            "verification_method": "sweep_plus_rta",
        }
    )

    return {"score": combined_score, "rating": rating, "detail": enhanced_detail}
