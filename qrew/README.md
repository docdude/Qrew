# Qrew

**Automated Loudspeaker Measurement System using REW API**

This project is a single Python‑based GUI application that automates capturing and processing loudspeaker measurements through the Room EQ Wizard (REW) API. 

## Installation

### Prerequisites

- **Python 3.8 or higher**
- **Room EQ Wizard (REW)** with API enabled
- **VLC Media Player** (for audio playback)

### Install via pip

#### From PyPI (when published):
```bash
pip install qrew
```

#### From Source:
```bash
# Clone the repository
git clone https://github.com/docdude/Qrew_pro.git
cd qrew

# Install in development mode
pip install -e .

# Or install normally
pip install .
```

#### With Development Dependencies:
```bash
pip install -e ".[dev]"
```

### Platform-Specific Installers

Pre-built installers are available for:

- **macOS**: `.dmg` installer with native app bundle
- **Windows**: `.exe` installer with desktop integration  
- **Linux**: `.deb` and `.rpm` packages with desktop files

Download the latest installer from the [Releases](https://github.com/docdude/Qrew_pro/releases) page.

### Dependencies

The package automatically installs these dependencies:
- PyQt5 (GUI framework)
- requests (REW API communication)
- flask (status message handling)
- numpy, pandas, scipy (signal processing)
- python-vlc (audio playback)

## Quick Start

### 1. Enable REW API
- Open REW
- Go to **Preferences → API**
- Enable **"Start Server"**
- Default port should be **4735**

### 2. Launch Qrew
```bash
# If installed via pip
qrew

# If running from source
python -m qrew

# Development mode
python run_dev.py
```

### 3. Load Stimulus File
- Click **"Load Stimulus File"**
- Select your measurement sweep WAV file
- The directory containing this file will be searched for channel-specific sweep files

### 4. Configure Measurement
- Select speaker channels to measure
- Set number of microphone positions
- Click **"Start Measurement"**

## Usage Workflow

1. **Setup**: The application launches a Flask thread and PyQt GUI
2. **Configuration**: Users select channels and number of positions
3. **Measurement**: Press "Start Measurement" to begin automated capture
4. **Quality Check**: Each measurement is automatically scored for quality
5. **Processing**: Apply cross-correlation alignment and/or vector averaging
6. **Export**: Save raw measurements or processed results

## Repository Overview

### Key Modules

**Qrew.py** – Main Application  
Defines the MainWindow class (QMainWindow) for the PyQt5 GUI, loads user settings, creates controls (channel selection, measurement grid, status panes) and starts measurement/processing workers.

**Qrew_workers.py** – Worker Threads  
Contains two QThread classes for background tasks. MeasurementWorker manages capturing sweeps, retries and metric evaluation. ProcessingWorker handles cross‑correlation and vector averaging.

**Qrew_api_helper.py** – REW API Interface  
Provides all REST calls to REW. Implements measurement management functions (save_all_measurements, delete_measurements_by_uuid, etc.).

**Qrew_message_handlers.py** – Flask/Qt Bridge  
Runs a small Flask server so REW can POST status, warnings, and errors. MessageBridge converts these into Qt signals for the GUI.

### User Interface Components

**Qrew_dialogs.py** – Custom dialogs (position prompts, quality warning dialogs, save dialogs, etc.)  
**Qrew_messagebox.py** – Themed message boxes and file dialogs  
**Qrew_gridwidget.py** – Renders the position grid visualization  
**Qrew_button.py** and **Qrew_styles.py** – UI styling helpers  

### Audio and Processing

**Qrew_vlc_helper.py** – Cross‑platform playback helpers using VLC  
**Qrew_measurement_metrics.py** – Implements measurement quality scoring algorithm  
**rew_cross_align_FR_v2.py** – Stand‑alone script for advanced signal processing  

### Configuration

**Qrew_settings.py** – Persistent settings management  
**settings.json** – Stores UI preferences (VLC GUI, tooltips, etc.)

## Development

### Running from Source

```bash
# Clone repository
git clone https://github.com/docdude/Qrew_pro.git
cd qrew

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Run application
python -m qrew
# or
python run_dev.py
```

### Building Installers

```bash
# Install build dependencies
pip install pyinstaller

# macOS
python setup_macos.py bdist_dmg

# Windows  
python setup_windows.py bdist_exe

# Linux
python setup_linux.py bdist_deb
python setup_linux.py bdist_rpm
```

## Tips for New Contributors

- Familiarity with PyQt5's event loop, signals/slots, and QThreads will help when modifying the GUI or worker logic
- Qrew_message_handlers.py uses Flask to bridge REW's HTTP callbacks to Qt signals; understanding this interaction is key when debugging measurement flow
- REW API request structures live in Qrew_api_helper.py. See REW_API_BASE_URL in Qrew_common.py for the host
- Measurement quality scoring is defined in Qrew_measurement_metrics.py; consult the scoring table below for threshold rationale

## Loudspeaker Measurement Quality Scoring

This document summarises the **heuristic thresholds** applied in `evaluate_measurement()`
to decide whether an individual REW measurement (impulse response + THD export)
is *good*, *caution*, or *redo*.

| Metric | Pass Threshold | Rationale |
|--------|----------------|-----------|
| **Impulse SNR / INR** | ≥ 60 dB (full score at 80 dB) | 80 dB recommended for clear modal decay; below 40 dB modes are buried in noise |
| **Mean THD (200 Hz – 20 kHz)** | ≤ 2 % | Typical design goal for hi‑fi loudspeakers |
| **Max THD spike** | < 6 % | Spikes above indicate clipping, rub & buzz, or measurement error |
| **Low‑frequency THD (< 200 Hz)** | ≤ 5 % | Sub‑bass drivers often exceed 5 %; higher suggests port noise or room rattles |
| **Magnitude‑squared Coherence** | ≥ 0.95 in pass‑band | Values < 0.9 indicate poor SNR or time variance |
| **Harmonic ratio H3 / H2** | < 0.7 | IEC 60268‑21 weighting prefers low‐order harmonics |

The final score (0‑100) is a weighted sum:
The final score (0‑100) is a weighted sum:

```
25 % Impulse SNR  • 15 % Coherence  • 45 % THD metrics  • 15 % bonus / penalties
``

Measurements scoring ≥ 70 = PASS, 50‑69 = CAUTION, < 50 = RETAKE.

Technical Details
Magnitude-Squared Coherence
C_xy(f) = |P_xy(f)|² / (P_xx(f)P_yy(f)) using Welch averaging
1.0 means all of y is a linearly transformed, noise-free copy of x at that frequency.

Stimulus File Usage
Perfect SNR → upper bound
Single sweep → no need for loop-back hardware
Repeatability Coherence
Use when:

You forgot to save the stimulus WAV
You want to verify the room stayed quiet between takes
License
GNU General Public License v3.0

Contributing
Fork the repository
Create a feature branch
Make your changes
Add tests if applicable
Submit a pull request
Support
Issues: GitHub Issues
Documentation: Wiki
Discussions: GitHub Discussions
Last updated: 2025-01-03
``