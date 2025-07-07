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

# HTML Icons for UI
HTML_ICONS = {
    'warning': '&#9888;',        # ⚠️
    'check': '&#10004;',         # ✓
    'cross': '&#10060;',         # ❌
    'circle_red': '&#11044;',    # ⭕ (colored via CSS)
    'circle_green': '&#11044;',  # ⭕ (colored via CSS)
    'circle_yellow': '&#11044;', # ⭕ (colored via CSS)
    'info': '&#8505;',           # ℹ️
    'star': '&#9733;',           # ★
    'bullet': '&#8226;',         # •
    'arrow_right': '&#8594;',    # →
    'arrow_up': '&#8593;',       # ↑
    'arrow_down': '&#8595;',     # ↓
    'gear': '&#9881;',           # ⚙️
    'home': '&#8962;',           # ⌂
    'play': '&#9654;',           # ▶
    'stop': '&#9632;',           # ■
    'pause': '&#9208;',          # ⏸
}


REW_API_BASE_URL = "http://127.0.0.1:4735"
WAV_STIMULUS_FILENAME = "1MMeasSweep_0_to_24000_-12_dBFS_48k_Float_L_refR.wav"


# Global variables 
global selected_stimulus_path
global stimulus_dir

selected_stimulus_path = None
stimulus_dir = None
show_vlc_gui = False 

def set_vlc_gui_preference(show_gui):
    """Set the VLC GUI preference from main app"""
    global show_vlc_gui
    show_vlc_gui = show_gui

