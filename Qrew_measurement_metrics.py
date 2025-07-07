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
        The JSON REW returns after `/postTHD`.
    ir_json : dict
        JSON from `/impulseResponse` – requires key ``signalToNoisedB``.
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

    # band-limited stats
    band  = thd[(freqs >= freq_band[0]) & (freqs <= freq_band[1])]
    mean_thd = band.mean()
    max_thd  = band.max()
    low_thd  = thd[freqs < 200].mean()
    h2 = data.get("H2 (%)", pd.Series(np.zeros(len(thd))))
    h3 = data.get("H3 (%)", pd.Series(np.zeros(len(thd))))
    h3_h2_ratio = (h3 / h2.replace(0, np.nan)).median()

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
            "mean_thd_% "  : mean_thd,
            "max_thd_% "   : max_thd,
            "low_thd_% "   : low_thd,
            "h3/h2_ratio"  : h3_h2_ratio
        }
    }
