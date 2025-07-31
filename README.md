# Qrew

**Automated Loudspeaker Measurement System using REW API**

This project is a single Python‑based GUI application that automates capturing and processing loudspeaker measurements th**Total Score Range**: 0-100 points across 8 weighted components

**Quality Ratings**: 
- **PASS** (≥ 70 points): Measurement meets professional standards
- **CAUTION** (50-69 points): Usable but may need verification 
- **RETAKE** (< 50 points): Measurement quality insufficient for analysis

The scoring uses linear scaling within each component's range, with inverse scaling for distortion metrics (lower values score higher). Coherence analysis uses Welch's method for magnitude-squared coherence estimation. THD calculations include both harmonic distortion and noise floor contributions (THD+N).e Room EQ Wizard (REW) API. 

## Recent Changes

- Added automatic measurement abort when VLC playback errors occur, ensuring that measurements are properly cancelled in REW.

## Installation

### Prerequisites

- **Python 3.8 or higher**
- **Room EQ Wizard (REW)** with API enabled, Pro license is required 
- **VLC Media Player** (for audio playback)

### Install via pip

#### From PyPI (when published):
```bash
pip install qrew
```

#### From Source:
```bash
# Clone the repository
git clone https://github.com/docdude/Qrew.git
cd Qrew

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
  - Intel (x86_64): `Qrew-*-macos-x86_64.dmg`
  - Apple Silicon (arm64): `Qrew-*-macos-arm64.dmg` 
  - Universal: `Qrew-*-macos-universal.dmg` (when available)
- **Windows**: `.exe` installer with desktop integration  
- **Linux**: `.deb` and `.rpm` packages with desktop files

Download the latest installer from the [Releases](https://github.com/docdude/Qrew/releases) page.

### Dependencies

The package automatically installs these dependencies:
- PyQt5 (GUI framework)
- requests (REW API communication)
- flask, gevent (status message handling)
- numpy, pandas (signal processing)
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

**Qrew_workers_v2.py** – Worker Threads  
Contains two QThread classes for background tasks. MeasurementWorker manages capturing sweeps, retries and metric evaluation. ProcessingWorker handles cross‑correlation and vector averaging. Non-blocking API calls.

**Qrew_api_helper.py** – REW API Interface  
Provides all REST calls to REW. Implements measurement management functions (save_all_measurements, delete_measurements_by_uuid, etc.).

**Qrew_message_handlers.py** – Flask/Qt Bridge  
Runs a small Flask server so REW can POST status, warnings, and errors. MessageBridge converts these into Qt signals for the GUI.

### User Interface Components

**Qrew_dialogs.py** – Custom dialogs (position prompts, quality warning dialogs, save dialogs, etc.)  
**Qrew_messagebox.py** – Themed message boxes and file dialogs  
**Qrew_micwidget_icons.py** – Renders the position grid visualization  
**Qrew_button.py** and **Qrew_styles.py** – UI styling helpers  

### Audio and Processing

**Qrew_vlc_widget.py** - VLC libvlc player
**Qrew_vlc_helper_v2.py** – Cross‑platform playback helpers using VLC  
**Qrew_measurement_metrics.py** – Implements measurement quality scoring algorithm  

### Configuration

**Qrew_resources.py** - images, json files, icons .qrc resources
**Qrew_common.py** - Common functions and constants
**Qrew_settings.py** – Persistent settings management  
**settings.json** – Stores UI preferences (VLC GUI, tooltips, etc.)

## Development

### Running from Source

```bash
# Clone repository
git clone https://github.com/docdude/Qrew.git
cd Qrew

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Run application
python -m qrew
```

### Building Installers

Pre-built installers are available from the [Releases](https://github.com/docdude/Qrew/releases) page for:

- **macOS**: 
  - Intel (x86_64): `Qrew-*-macos-x86_64.dmg`
  - Apple Silicon (arm64): `Qrew-*-macos-arm64.dmg`
  - Universal: `Qrew-*-macos-universal.dmg` (when available)
- **Windows**: `.exe` installer with desktop integration
- **Linux**: `.deb` and `.rpm` packages

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
| **Signal-to-Noise Ratio** | ≥ 55 dB (20 pts max at 75 dB) | Adequate SNR ensures measurements aren't noise-limited |
| **Signal-to-Distortion Ratio** | ≥ 40 dB (15 pts max at 55 dB) | High SDR indicates clean signal path and low artifacts |
| **Mean THD (20 Hz - 20 kHz)** | ≤ 1% (15 pts max at 0%) | Primary distortion metric for loudspeaker linearity |
| **Peak THD Spike** | ≤ 3% (10 pts max at 0%) | Identifies resonances, breakup modes, or clipping |
| **Low-frequency THD (< 200 Hz)** | ≤ 8% (5 pts max at 0%) | Bass drivers typically have higher distortion |
| **Harmonic Ratio (H3/H2)** | ≤ 0.5 (5 pts max at 0) | IEC 60268-21: odd harmonics are more audible |
| **Magnitude-squared Coherence** | ≥ 0.95 (15 pts max at 0.99) | Indicates measurement repeatability and SNR |
| **IR Peak-to-Noise** | ≥ 45 dB (15 pts max at 55 dB) | Impulse response quality independent of frequency domain |

The final score (0‑100) is a weighted sum:
The final score (0‑100) is a weighted sum:

```
25 % Impulse SNR  • 15 % Coherence  • 45 % THD metrics  • 15 % bonus / penalties
``

Measurements scoring ≥ 70 = PASS, 50‑69 = CAUTION, < 50 = RETAKE.

## License

GNU General Public License v3.0

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Support

- **Issues**: [GitHub Issues](https://github.com/docdude/Qrew/issues)
- **Documentation**: [Wiki](https://github.com/docdude/Qrew/wiki)
- **Discussions**: [GitHub Discussions](https://github.com/docdude/Qrew/discussions)

---
*Last updated: 2025-07-30*