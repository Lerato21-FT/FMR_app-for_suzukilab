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

Open <http://127.0.0.1:8765>. Ctrl+C stops the app. The API contract is at
<http://127.0.0.1:8765/docs>.

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

1. Enter the frequencies (GHz, comma separated), RF power, the Aux Out sweep
   range and step, and the waits.
2. Check the **Preview**:
   - the field range and step;
   - the modulation field in Oe rms;
   - the estimated duration;
   - the estimated resonance field at each frequency, from the γ and Meff
     guesses, with a flag when it falls outside the sweep.

   Settings that break a safety limit are listed in red, and the run will
   refuse to start.
3. Press **Measure**. For each frequency, the app:
   - sets the RF frequency and power, turns the RF on and sets the modulation;
   - ramps the field to the start and waits for the sample to saturate;
   - steps Aux Out, reading the corrected field and X/θ at every step;
   - turns the modulation and RF off, ramps the field to zero and saves the
     sweep.
4. **Skip current** ends the current frequency and moves to the next.
   **Stop all** ends the run.
5. Whenever a run ends, however it ends, the app turns RF and modulation off
   and ramps the field down. This includes an instrument error. Any problem
   during that shutdown is shown on the page.

Plots of signal and phase against the measured field update every half
second. Use **Show sweep** to look at earlier frequencies of the run.

## Saved data

Each sweep is saved in `data/measurements/` (gitignored; set with
`FMR_DATA_DIR`, which must stay inside the repository):

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
| Modulation | 5.219 Oe/V rms | at 700 Hz; `Hmod = sine amplitude × this` |

Resonance estimate (CGS), for planning only:

- in plane: `f = γ √(H (H + 4πMeff))`;
- saturated out of plane: `f = γ (H − 4πMeff)`.

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
