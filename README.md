# Qrew
GUI python scripts that leverage REW API to automate measurement capture and processing 


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
