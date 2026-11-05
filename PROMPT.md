Follow AGENTS.md.

# Project brief: FMR acquisition app

Build a Python web app that runs our FMR measurements, replacing the LabVIEW
program in `Labview_fmr/Suzuki_FMR_v06M.vi`.

## The setup

- **Measurement:** co-planar waveguide FMR, with field sweeps at fixed
  microwave frequencies.
- **Microwaves:** an Agilent 83640B synthesized sweeper in CW mode (GPIB).
- **Static field:** an electromagnet powered by a Kepco supply. The supply's
  current is programmed by an SR830 Aux Out voltage, and the output is
  inverted, so a negative voltage gives a positive field.
- **Field modulation:** the SR830 sine output passes through an amplifier
  into a copper coil. The lock-in is referenced to that frequency (about
  700 Hz), so the signal is the field derivative of the absorption.
- **Signal:** X and θ from the SR830 (GPIB).
- **Field readback:** a Lake Shore 425 gaussmeter (serial, COM3), corrected
  by a scale and offset calibration.

## What the app must do

- Accept a list of frequencies and an Aux Out sweep (begin, end, step), the
  RF power, waits, lock-in and modulation settings, and calibration
  constants.
- For each frequency:
  - set RF and turn it on;
  - ramp the field to the start and saturate;
  - step the field, reading H, X and θ at each step;
  - then turn modulation and RF off, ramp the field to zero and save the
    sweep.
- Offer Skip and Stop, and always shut down safely, including after errors.
- Save files in the LabVIEW format so the FMR analysis app can read them.
  That format is tab-delimited field (Oe), signal and phase, with the
  frequency in MHz in the file name.
- Show a preview (field range, duration, estimated resonance field) and live
  plots of signal and phase against field.
- Be served only on `127.0.0.1`, on the lab computer.

## Constraints

- **No Docker:** the app runs natively on Windows, because PyVISA must reach
  the instruments through NI-VISA.
- **Dependencies:** Python 3.14, with packages only in the repository's
  `.venv/` from `requirements.lock`. The packages are FastAPI, uvicorn and
  PyVISA, with pytest, httpx and Ruff for development. GNU Make runs under
  Git Bash. Plotly is vendored by `make vendor`.
- **Calculations:** the backend computes every result; the page only draws.
- **Tests:** they and `make verify` use simulated instruments and never
  contact hardware.

## Progress

- **2026-11-03:** read the VI and planned the app (`notes/2026-11-03.md`).
- **2026-11-04:** native tooling, drivers and simulated instruments,
  calibration, the run engine, the API and the page; `make verify` green
  (`notes/2026-11-04.md`).
- **Next** (`TASKS.md`):
  - browser checks;
  - real-hardware bench tests through `make hardware-check`;
  - answers to the open questions, especially the safety limits.
