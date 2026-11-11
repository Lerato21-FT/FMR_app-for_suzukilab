# FMR acquisition

A local web app that runs field-swept ferromagnetic resonance (FMR)
measurements on the Suzuki Lab co-planar waveguide setup. It replaces the
LabVIEW program `Labview_fmr/Suzuki_FMR_v06M.vi`.

At each fixed microwave frequency, the app steps the magnet field and records
the lock-in signal:

- **Agilent 83640B** (GPIB): CW microwave excitation.
- **SR830 lock-in** (GPIB):
  - Aux Out 1 programs the **Kepco** supply that drives the electromagnet;
  - the sine output drives the modulation coil through an amplifier;
  - X and θ at that reference frequency are the FMR signal.
- **Lake Shore 425** gaussmeter (serial): reads back the field.

The app runs on the lab's Windows computer and is served only on
`127.0.0.1`. The backend does every calculation; the page displays the
results and the live data.

## Requirements

These are installed on the lab computer and are not installed by this
project:

- Windows 11, 64-bit.
- Python 3.14, 64-bit, through the `py` launcher.
- NI-VISA with NI-488.2 (GPIB drivers).
- Git, which includes Git Bash.
- GNU Make 4.4 or later.

Run `make` in the repository folder from any terminal: PowerShell, the VS
Code terminal, cmd or Git Bash. The Makefile finds Git for Windows' `sh`
itself. If `make` is "not recognized", the terminal was opened before Make
was installed: close it and open a new one. For VS Code, quit and restart
VS Code entirely. Python packages
go only into the repository's `.venv/`, at the exact versions in
`requirements.lock`, and tool caches stay in `.cache/`. Nothing is written
outside the repository.

## Run it

```sh
cp .env.example .env    # optional: port, instrument mode, addresses, limits
make run                # creates .venv, installs the lock, fetches Plotly, starts
```

Open <http://127.0.0.1:8766>. Ctrl+C stops the app. `make run-sim` starts
it with simulated instruments even when `.env` selects hardware. The API contract is at
<http://127.0.0.1:8766/docs>.

By default the app uses **simulated instruments**. They produce a synthetic
FMR line, so you can try everything without hardware. To use the real setup,
set `FMR_INSTRUMENTS=hardware` in `.env` and check the VISA addresses:

| Instrument | Variable | Default |
|---|---|---|
| SR830 lock-in | `FMR_SR830_ADDRESS` | `GPIB0::8::INSTR` |
| Agilent 83640B | `FMR_RF_SOURCE_ADDRESS` | `GPIB0::19::INSTR` |
| Lake Shore 425 | `FMR_LAKESHORE_ADDRESS` | `ASRL3::INSTR` (COM3) |

`make hardware-check` opens each instrument and prints its identification,
without changing any output. Use it before your first real run.

## Taking a measurement

The page is laid out like the LabVIEW front panel, in four quadrants:

| | |
|---|---|
| **Data**: signal and phase against H | **Instrument setup**: tabs *H field setup*, *A83640B*, *SR830*, *Stepper Motor* |
| **Measurement list**: frequencies, orientation, angle, field range and step, save folder | **Run**: Measure / Skip / Stop All, status and the preview |

On a narrow window the quadrants stack.

1. In **Measurement list**, enter the frequencies (GHz, separated by commas,
   spaces or new lines), the orientation, the angle (used only in the file
   name until the stepper motor is ported), the **field range** and **field
   step** (Oe), and the **save folder**. In the instrument tabs, set the RF
   power (*A83640B*), the **modulation field** in Oe rms (*SR830*), and the
   g-factor, Meff, calibration and waits (*H field setup*).
   Each frequency gets its own sweep, centred on its Kittel resonance
   estimate `Hres` and run from `Hres + range/2` down to `Hres − range/2`.
   For example, a 1000 Oe range around `Hres = 1500 Oe` sweeps from 2000 Oe
   to 1000 Oe. The supply is bipolar, so a sweep may cross zero.
2. Check the preview in the **Run** quadrant:
   - a table row per frequency with `Hres`, the start and end field, the
     point count and the file it will be saved to;
   - the field step after rounding to 1 mV of Aux Out;
   - the modulation field you set (Oe rms), as the sine amplitude the
     backend will send and the field that amplitude actually gives;
   - the estimated duration.

   Settings that break a safety limit are listed in red, and the run will
   refuse to start.
3. Press **Measure**. For each frequency, the app:
   - sets the RF frequency and power, turns the RF on and sets the modulation;
   - ramps the field to the start and waits for the sample to saturate;
   - steps Aux Out, reading the corrected field and X/θ at every step;
   - turns the modulation and RF off, ramps the field to zero and saves the
     sweep.
4. **Skip** ends the current frequency and moves to the next.
   **Stop All** ends the run.
5. Whenever a run ends, however it ends, the app turns RF and modulation off
   and ramps the field down. This includes an instrument error. Any problem
   during that shutdown is shown on the page.

Plots of signal and phase against the measured field update every half
second. Use **Sweep** above the plots to look at earlier frequencies of the
run.

## Saved data

Each sweep is saved in `data/measurements/<save folder>/` (gitignored). The
base directory is set with `FMR_DATA_DIR`, which must stay inside the
repository. The save folder is a relative name such as `2026-11-11_CoFeB`
or `CoFeB/run_2`. Leave it empty to save in the base directory. Names with
`..`, a drive letter, a leading `/` or a `\` are refused, so data can never
be written outside the repository.

- **Name:** the LabVIEW pattern, for example
  `fmr-10000MHz-In-plane-000.0deg-+0dBm2.1OeRMS-.csv`.
- **Content:** tab-delimited rows of field (Oe), X (V) and phase (deg), in
  `%.6e` format, with no header.
- **Compatibility:** the FMR analysis app reads the first two columns and the
  frequency in the name unchanged.

Existing files are never overwritten. If a name is already taken, the run is
refused before anything is measured, so change the prefix. A sweep that was
skipped, stopped or interrupted by an error keeps the points it measured.

## Calibration

The defaults below come from the LabVIEW front panel. You can edit them on
the page, and every conversion is done by the backend.

| Setting | Default | Meaning |
|---|---|---|
| Field per Aux volt | 996.3 Oe/V | one Kepco supply (≈1984.4 Oe/V with two) |
| Aux Out inverted | yes | a negative voltage gives a positive field |
| Gaussmeter scale / offset | 1.544 / −11.956 Oe | `H = scale × reading + offset` (08/20/2026) |
| Modulation | 5.219 Oe/V rms | at 700 Hz; you set `Hmod` (default 2.0 Oe rms) and the sine amplitude is `Hmod ÷ this` |

Resonance estimate (CGS), used to centre each sweep, with `γ = g μB / h`
(default `g = 2`, Meff 140 emu/cc):

- in plane: `f = γ √(H (H + 4πMeff))` (Appl. Phys. Lett. 127, 032406,
  Eq. 2, with the in-plane fourfold anisotropy set to zero);
- saturated out of plane: `f = γ (H − 4πMeff)`.

Details are in `docs/fmr-model.md`.

## Safety limits

Every run is checked against these before any command is sent. Set them in
`.env`:

| Variable | Default |
|---|---|
| `FMR_MAX_AUX_VOLTAGE_V` | 5.0 V |
| `FMR_MAX_FIELD_OE` | 10000 Oe |
| `FMR_MAX_RF_POWER_DBM` | 20 dBm |
| `FMR_MAX_RAMP_STEP_V` | 0.1 V per step (also limits the sweep step) |
| `FMR_MAX_POINTS_PER_SWEEP` | 20000 |

The defaults are placeholders until the lab confirms its values.

## Developing

`make help` lists every target. The main ones:

- `make verify`: the gate. It runs Ruff, the pytest suite, and a smoke check
  that starts the app and runs a short simulated sweep over HTTP. It uses
  simulated instruments and never opens a VISA session.
- `make test TEST_PATHS=tests/2026-11-04/test_measurement.py`: run selected
  tests.
- `make fmt`: format the code. `make lint`: check without changing anything.
- `make lock`: after editing `pyproject.toml`, regenerate
  `requirements.lock`, and commit both files together.
- `make clean`: remove `.venv/`, caches and the vendored Plotly. `data/` and
  `.env` are kept.

How the code is organized is described in `ARCHITECTURE.md`; the working
rules are in `AGENTS.md`; daily records are in `notes/`.
