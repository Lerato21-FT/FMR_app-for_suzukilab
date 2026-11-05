# LabVIEW reference: `Suzuki_FMR_v06M.vi`

The original LabVIEW program that the Python acquisition app replaces. It is
kept for reference only: the app neither runs nor reads it, and it is never
modified.

## What it is

- **Title:** "Suzuki_FMR_v06 - invert Vaux output".
- **What it does:** a single VI that runs field-swept, lock-in detected FMR.
  The front panel has tabs for H field setup, the A83640B RF source, the
  SR830 lock-in and the stepper motor.
- **Libraries it uses:**
  - the NI instrument driver libraries `Stanford Research 830.lvlib` and
    `Lake Shore 425.lvlib`;
  - raw SCPI for the Agilent 83640B;
  - `TIMS_StepperMotor_BasicMove_withTerminals.vi` for sample rotation;
  - Write To Spreadsheet File for saving.
- **Default addresses:** SR830 `GPIB0::8::INSTR`, 83640B `GPIB0::19::INSTR`,
  Lake Shore `COM3`, and a multimeter at `GPIB0::16::INSTR` that appears to
  be unused.

## How it was read

The VI is a compiled binary. Its compressed front panel and block diagram
were unpacked, and the labels, defaults, comments and SCPI strings read
from them. The wiring was not read, so the reconstructed sequence should be
confirmed by opening the VI in LabVIEW.

The full findings are in [`notes/2026-11-03.md`](../notes/2026-11-03.md).
They cover:

- the instruments;
- the calibration constants;
- the measurement sequence;
- the saved-file format.

## Where each part lives in the Python app

| VI part | Python |
|---|---|
| SR830 Initialize/Configure/Read, Aux Out | `src/app/instruments/sr830.py` |
| Lake Shore Field Data (Single Reading) | `src/app/instruments/lakeshore425.py` |
| 83640B SCPI (`:FREQ:MODE CW`, `:POW:*`) | `src/app/instruments/agilent83640b.py` |
| Field ramp via Aux Out ("invert Vaux output") | `src/app/instruments/magnet.py` |
| H conversion, H read scale/offset, Modulation H scale | `src/app/calibration.py` |
| Hfmr guess from γ and Meff | `calibration.estimate_resonance_field_oe` |
| Measure / Skip / Stop All sequence | `src/app/measurement.py` |
| Write To Spreadsheet File, file-name pattern | `src/app/storage.py` |
| TIMS stepper motor (in-plane angles) | not ported yet (TASKS.md, Q4) |
