# Qrew_common.py

SPEAKER_LABELS = {
    "C": "Center",
    "FL": "Front Left",
    "FR": "Front Right",
    "SLA": "Surround Left",
    "SRA": "Surround Right",
    "SBL": "Surround Back Left",
    "SBR": "Surround Back Right",
    "TFL": "Top Front Left",
    "TFR": "Top Front Right",
    "TML": "Top Middle Left",
    "TMR": "Top Middle Right",
    "TRL": "Top Rear Left",
    "TRR": "Top Rear Right",
    "FDL": "Front Dolby Left",
    "FDR": "Front Dolby Right",
    "FHL": "Front Height Left",
    "FHR": "Front Height Right",
    "FWL": "Front Wide Left",
    "FWR": "Front Wide Right",
    "RHL": "Rear Height Left",
    "RHR": "Rear Height Right",
    "SDL": "Surround Dolby Left",
    "SDR": "Surround Dolby Right",
    "SHL": "Surround Height Left",
    "SHR": "Surround Height Right",
    "BDL": "Back Dolby Left",
    "BDR": "Back Dolby Right",
    "SW1": "Subwoofer 1",
    "SW2": "Subwoofer 2",
    "SW3": "Subwoofer 3",
    "SW4": "Subwoofer 4"
}

# Qrew_dialogs.py  – add/replace this block
# ----------------------------------------------------------
SPEAKER_CONFIGS = {
    # ───── basic ─────
    "Manual Select": [],
    "Stereo 2.0":        ["FL", "FR"],
    "Stereo 2.1":        ["FL", "FR", "SW1"],
    "3.0 LCR":           ["FL", "FR", "C"],
    "3.1":               ["FL", "FR", "C", "SW1"],
    "Quadraphonic 4.0":  ["FL", "FR", "SLA", "SRA"],
    "4.1":               ["FL", "FR", "SLA", "SRA", "SW1"],

    # ───── Dolby Surround beds ─────
    "5.0":               ["FL", "FR", "C", "SLA", "SRA"],
    "5.1":               ["FL", "FR", "C", "SW1", "SLA", "SRA"],
    "6.1 (EX / DTS-ES)": ["FL", "FR", "C", "SW1", "SLA", "SRA", "SBL"],   # rear-centre → SBL
    "7.1":               ["FL", "FR", "C", "SW1", "SLA", "SRA",
                          "SBL", "SBR"],

    # ───── Dolby Atmos Home ─────
    "5.1.2 Atmos":       ["FL", "FR", "C", "SW1", "SLA", "SRA",
                          "TFL", "TFR"],
    "5.1.4 Atmos":       ["FL", "FR", "C", "SW1", "SLA", "SRA",
                          "TFL", "TFR", "TRL", "TRR"],
    "7.1.2 Atmos":       ["FL", "FR", "C", "SW1", "SLA", "SRA",
                          "SBL", "SBR", "TFL", "TFR"],
    "7.1.4 Atmos":       ["FL", "FR", "C", "SW1", "SLA", "SRA",
                          "SBL", "SBR", "TFL", "TFR", "TRL", "TRR"],
    "7.1.6 Atmos":       ["FL", "FR", "C", "SW1", "SLA", "SRA",
                          "SBL", "SBR",
                          "TFL", "TFR", "TML", "TMR", "TRL", "TRR"],
    "9.1.6 Atmos (wides)": ["FL", "FR", "C", "SW1", "SLA", "SRA",
                            "SBL", "SBR", "FWL", "FWR",
                            "TFL", "TFR", "TML", "TMR", "TRL", "TRR"],
    "11.1.8 Atmos":      ["FL", "FR", "C", "FHL", "FHR", "SW1", "SLA", "SRA",
                            "SBL", "SBR", "SDL", "SDR", "FWL", "FWR",
                            "TFL", "TFR", "TRL", "TRR", "RHL", "RHR"],

    # ───── Auro-3D (13-strain) ─────
    "Auro-3D 9.1":  ["FL", "FR", "C", "SW1", "SLA", "SRA",
                     "FHL", "FHR", "SHL", "SHR"],
    "Auro-3D 10.1": ["FL", "FR", "C", "SW1", "SLA", "SRA",
                     "FHL", "FHR", "SHL", "SHR", "TML"],      # VOG ≈ TML
    "Auro-3D 11.1": ["FL", "FR", "C", "SW1", "SLA", "SRA",
                     "FHL", "FHR", "SHL", "SHR", "TFL", "TFR"],  # uses front-tops for CH pair
    "Auro-3D 13.1": ["FL", "FR", "C", "SW1", "SLA", "SRA",
                     "SBL", "SBR",
                     "FHL", "FHR", "SHL", "SHR", "TML"],      # rear heights ≈ SBL/SBR
}
# ----------------------------------------------------------

REW_API_BASE_URL = "http://127.0.0.1:4735"
WAV_STIMULUS_FILENAME = "1MMeasSweep_0_to_24000_-12_dBFS_48k_Float_L_refR.wav"

# Global variables
selected_stimulus_path = None
stimulus_dir = None
