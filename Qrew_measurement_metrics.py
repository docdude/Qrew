# Qrew_measurement_metrics.py
"""

"""
import numpy as np
import pandas as pd

def evaluate_measurement(thd_json: dict,
                         ir_json: dict,
                         coherence_array: np.ndarray | None = None,
                         freq_band: tuple = (20, 20000)) -> dict:
    """
    Combine THD, impulse-response SNR and (optionally) coherence
    into a single 0-100 ‘measurement-quality’ score.

    Parameters
    ----------
    thd_json : dict
        The JSON REW returns after `/measurement/{id}/distortion`.
    ir_json : dict
        JSON from `/measurements/{id}` – requires key ``signalToNoisedB``.
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
    cols  = thd_json["columnHeaders"]
    data  = pd.DataFrame(thd_json["data"], columns=cols)
    freqs = data["Freq (Hz)"]
    thd   = data["THD (%)"]

    # Fix REW API bug - THD values appear to be multiplied by 10000
    # Check if values are unreasonably high (>100% THD is very rare)
    if thd.max() > 100:
        print(f"THD values appear to be scaled incorrectly (max: {thd.max():.1f}%), dividing by 10000")
        thd = thd / 10000
        # Also fix harmonic columns if present
        for col in ["H2 (%)", "H3 (%)", "H4 (%)", "H5 (%)", "H6 (%)", "H7 (%)", "H8 (%)", "H9 (%)"] :
            if col in data.columns:
                data[col] = data[col] / 10000
    
    # band-limited stats
    band  = thd[(freqs >= freq_band[0]) & (freqs <= freq_band[1])]
    mean_thd = band.mean()
    max_thd  = band.max()
    low_thd  = thd[freqs < 200].mean()
    h2 = data.get("H2 (%)", pd.Series(np.zeros(len(thd))))
    h3 = data.get("H3 (%)", pd.Series(np.zeros(len(thd))))
    # Calculate harmonic ratio
    valid_mask = (h2 > 0)
    if valid_mask.any():
        h3_h2_ratio = (h3[valid_mask] / h2[valid_mask]).median()
    else:
        h3_h2_ratio = 0
    # --- impulse-response SNR ----------------------------------------
    snr = ir_json.get("signalToNoisedB", 0.0)

    # --- coherence ---------------------------------------------------
    if coherence_array is not None:
        coh_mean = np.nanmean(coherence_array)
    else:
        coh_mean = None

    # --- scoring -----------------------------------------------------
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

    # clamp & rating
    score = float(np.clip(score, 0, 100))
    if score >= 70:
        rating = "PASS"
    elif score >= 50:
        rating = "CAUTION"
    else:
        rating = "RETAKE"

    return {
        "score" : score,
        "rating": rating,
        "detail": {
            "snr_dB"       : snr,
            "coh_mean"     : coh_mean,
            "mean_thd_%"  : mean_thd,
            "max_thd_%"   : max_thd,
            "low_thd_%"   : low_thd,
            "h3/h2_ratio"  : h3_h2_ratio
        }
    }


def combine_sweep_and_rta_results(sweep_result, rta_result):
    """Combine sweep measurement and RTA verification results"""
    if not rta_result:
        return sweep_result
    
    # Start with sweep score
    combined_score = sweep_result['score']
    
    # RTA-based adjustments
    rta_thd = rta_result['thd_mean']
    rta_stability = rta_result['stability_good']
    rta_enob = rta_result['enob_mean']
    rta_snr = rta_result['snr_mean']
    rta_thd_plus_n = rta_result.get('thdPlusN', {}).get('value', 0) 
    rta_snr = rta_result.get('snrdB', 0)
    enob = rta_result.get('enob', 0)
    imd = rta_result.get('imd', {}).get('value', 0)  

    # ENOB bonus (max 15 points)
    combined_score += np.clip((enob - 12) / 4 * 15, 0, 15)  # 12-16 ENOB range
    
    # IMD penalty (subtract up to 10 points)
    combined_score -= np.clip(imd * 2, 0, 10)  # IMD > 5% = -10 points
    
    # THD+N consideration (use if better than sweep THD)
    if rta_thd_plus_n < sweep_result['detail']['mean_thd_%']:
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
    sweep_thd = sweep_result['detail']['mean_thd_%']
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
    enhanced_detail = sweep_result['detail'].copy()
    enhanced_detail.update({
        'rta_thd_mean_%': round(rta_thd, 3),
        'rta_thd_plus_n_%': round(rta_result['thd_plus_n_mean'], 3),
        'rta_snr_dB': round(rta_snr, 2),
        'rta_enob': round(rta_enob, 2),
        'rta_stability': stability_note,
        'thd_consistency': consistency_note,
        'rta_samples': rta_result['stable_samples'],
        'verification_method': 'sweep_plus_rta'
    })
    
    return {
        'score': combined_score,
        'rating': rating,
        'detail': enhanced_detail
    }
