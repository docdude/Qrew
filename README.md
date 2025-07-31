# Qrew - Automated Loudspeaker Measurement System

Qrew is an automated loudspeaker measurement system that integrates with Room EQ Wizard (REW) to provide comprehensive acoustic analysis.

## Features

- Automated multi-position speaker measurements
- REW API integration for seamless workflow
- Real-time measurement quality assessment
- Multiple visualization modes
- Cross-platform support (Windows, macOS, Linux)

## Installation

### Prerequisites
- Python 3.8 or higher
- Room EQ Wizard (REW), requires Pro license
- VLC Media Player

### Install from PyPI
```bash
pip install qrew
```

### Install from Source
```bash
git clone https://github.com/docdude/Qrew.git
cd Qrew
pip install -e .
```

## Quick Start

1. Start REW and enable the API (port 4735)
2. Run Qrew: `python -m qrew`
3. Load your sweep file and configure speakers
4. Begin automated measurements

## Requirements

See `requirements.txt` for Python dependencies.

## License

GPL-3.0 - see LICENSE file for details.

## Contributing

See CONTRIBUTORS.md for contribution guidelines.
