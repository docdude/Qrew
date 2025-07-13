# Qrew
Repository Overview

This project is a single Python‑based GUI application that automates capturing and processing loudspeaker measurements through the Room EQ Wizard (REW) API. All source files live in the repository root. The main executable is Qrew.py.

Key modules:

Qrew.py – Main Application
Defines the MainWindow class (QMainWindow) for the PyQt5 GUI, loads user settings, creates controls (channel selection, measurement grid, status panes) and starts measurement/processing workers. Initialization begins around line 49 where the window is set up with various widgets and settings storage. Commands such as starting measurements clear state and launch worker threads (see on_start handling around lines 780‑819).

Qrew_workers.py – Worker Threads
Contains two QThread classes for background tasks. MeasurementWorker manages capturing sweeps, retries and metric evaluation. Quality metrics are computed via evaluate_measurement_metrics, which fetches measurement data from the API and emits a summary back to the UI. On success it updates position/channel handling and optionally pauses based on quality. ProcessingWorker handles cross‑correlation and vector averaging of existing measurements.

Qrew_api_helper.py – REW API Interface
Provides all REST calls to REW. For example start_capture prepares REW, locates sweep files, and calls start_measurement to trigger the capture. It also implements measurement management functions (save_all_measurements, delete_measurements_by_uuid, etc.).

Qrew_message_handlers.py – Flask/Qt Bridge
Runs a small Flask server so REW can POST status, warnings, and errors. MessageBridge converts these into Qt signals for the GUI. The /rew-status handler parses messages, notifies the measurement coordinator, and plays sweep files when needed.

User dialogs and support utilities
Qrew_dialogs.py – Custom dialogs (position prompts, quality warning dialogs, save dialogs, etc.).

Qrew_gridwidget.py – Renders the position grid.

Qrew_button.py and Qrew_styles.py – UI styling helpers.

Qrew_vlc_helper.py – Cross‑platform playback helpers using VLC, falling back to OS commands.

Qrew_measurement_metrics.py – Implements the scoring algorithm for measurement quality. It computes a numeric score and rating using impulse‑response SNR, THD, and optional coherence data.

rew_cross_align_FR_v2.py – Stand‑alone script for REW‑style cross‑correlation alignment and vector averaging of impulse responses.

Settings and README
settings.json stores persistent UI preferences (e.g., show_vlc_gui, show_tooltips). The README explains the loudspeaker quality metrics and threshold values used in evaluate_measurement with a table summarizing each criterion and the weighted scoring formula.

Workflow Overview

The application launches a Flask thread and then the PyQt GUI (__main__ section in Qrew.py around the end).
Users select channels and the number of positions. Pressing Start Measurement sets up measurement state and shows a position dialog.
MeasurementWorker invokes API calls through Qrew_api_helper.py to capture sweeps. The Flask handlers receive REW status updates and signal the worker when a measurement completes or errors out.
After each capture, metrics are calculated. If a measurement fails quality thresholds, the user can remeasure or continue.
Once all measurements are acquired, the user may trigger processing: cross‑correlation alignment and/or vector averaging handled by ProcessingWorker.
Raw measurements can be saved to .mdat using the API; final results (vector averages, cross‑correlated responses) are uploaded back to REW.

Tips for New Contributors

Familiarity with PyQt5’s event loop, signals/slots, and QThreads will help when modifying the GUI or worker logic.
Qrew_message_handlers.py uses Flask to bridge REW’s HTTP callbacks to Qt signals; understanding this interaction is key when debugging measurement flow.
REW API request structures live in Qrew_api_helper.py. See REW_API_BASE_URL in Qrew_common.py for the host. The helper methods return (success, error_message) pairs to keep threadsafe error reporting.
Measurement quality scoring is defined in Qrew_measurement_metrics.py; consult the README table for threshold rationale.
rew_cross_align_FR_v2.py is a more advanced example of interacting with REW’s measurement data using NumPy and SciPy—useful for deeper processing tasks.

Next Steps to Explore

Study the REW API documentation to understand all endpoints used in Qrew_api_helper.py.
Experiment with the measurement workflow in a test environment to see how the GUI interacts with REW.
Review Qrew_dialogs.py and Qrew_styles.py for customizing UI appearance or adding new dialogs.
If extending the processing pipeline, check how ProcessingWorker orchestrates cross-correlation and vector averaging.
This repository provides a full example of a PyQt5 front end controlling REW through a REST API while performing real‑time measurement scoring and post‑processing.


# Loudspeaker Measurement Quality Scoring

This document summarises the **heuristic thresholds** applied in `evaluate_measurement()`
to decide whether an individual REW measurement (impulse response + THD export)
is *good*, *caution*, or *redo*.

| Metric | Pass Threshold | Rationale |
|--------|----------------|-----------|
| **Impulse SNR / INR** | ≥ 60 dB (full score at 80 dB) | 80 dB recommended for clear modal decay; below 40 dB modes are buried in noise |
| **Mean THD (200 Hz – 20 kHz)** | ≤ 2 % | Typical design goal for hi‑fi loudspeakers |
| **Max THD spike** | < 6 % | Spikes above indicate clipping, rub & buzz, or measurement error |
| **Low‑frequency THD (< 200 Hz)** | ≤ 5 % | Sub‑bass drivers often exceed 5 %; higher suggests port noise or room rattles |
| **Magnitude‑squared Coherence** | ≥ 0.95 in pass‑band | Values < 0.9 indicate poor SNR or time variance |
| **Harmonic ratio H3 / H2** | < 0.7 | IEC 60268‑21 weighting prefers low‐order harmonics |

The final score (0‑100) is a weighted sum:

```
25 % Impulse SNR  • 15 % Coherence  • 45 % THD metrics  • 15 % bonus / penalties
```

Measurements scoring **≥ 70** = **PASS**, **50‑69** = **CAUTION**, **< 50** = **RETAKE**.

_Last updated: 2025-07-03_

6 Quick cheat-sheet for the README

What is magnitude-squared coherence?
C 
xy
​	
 (f)=∣P 
xy
​	
 (f)∣ 
2
 /(P 
xx
​	
 (f)P 
yy
​	
 (f)) using Welch averaging
​    
  – 1.0 means all of y is a linearly transformed, noise-free copy of x at that frequency.
Why use the stimulus file?
• perfect SNR → upper bound
• single sweep → no need for loop-back hardware
When to use repeatability coherence?
• you forgot to save the stimulus WAV
• you want to verify the room stayed quiet between takes
