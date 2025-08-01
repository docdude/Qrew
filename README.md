# Qrew

**Automated Loudspeaker Measurement System using REW API**

This project is a single Python‑based GUI application that automates capturing and processing loudspeaker measurements through Room EQ Wizard (REW) API. 

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

### Platform-Specific Installers

Pre-built installers are available for:

- **macOS**: `.dmg` installer with native app bundle
  - Intel (x86_64): `Qrew-*-macos-x86_64.dmg`
  - Apple Silicon (arm64): `Qrew-*-macos-arm64.dmg` 
  - Universal: `Qrew-*-macos-universal.dmg` (when available)
- **Windows**: `.exe` installer with desktop integration  
- **Linux**: `.deb` and `.rpm` packages with desktop files

Download the latest installer from the [Releases](https://github.com/docdude/Qrew/releases) page.

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

```

### 3. Load Stimulus File
- Click **"Load Stimulus File"**
- Select your measurement sweep WAV file
- The directory containing this file will be searched for channel-specific sweep files, make sure you have the sweeps you need for a given channel. Channels are selected on the main UI

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

## Tips for New Contributors

- Familiarity with PyQt5's event loop, signals/slots, and QThreads will help when modifying the GUI or worker logic
- Qrew uses Flask to bridge REW's HTTP callbacks to Qt signals; understanding this interaction is key when debugging measurement flow
- REW API request structures can be found on REW API documentation page
- Measurement quality scoring is defined below; consult the scoring table below for threshold rationale, input on improving scoring system welcome 

## Loudspeaker Measurement Quality Scoring

This document summarises the **heuristic thresholds** applied in `evaluate_measurement()`
to decide whether an individual REW measurement (impulse response + THD export)
is *good*, *caution*, or *retake*.

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

**Quality Ratings**: 
- **PASS** (≥ 70 points): Measurement meets professional standards
- **CAUTION** (50-69 points): Usable but may need verification 
- **RETAKE** (< 50 points): Measurement quality insufficient for analysis

The scoring uses linear scaling within each component's range, with inverse scaling for distortion metrics (lower values score higher). Coherence analysis uses Welch's method for magnitude-squared coherence estimation. THD calculations include both harmonic distortion and noise floor contributions (THD+N).

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
