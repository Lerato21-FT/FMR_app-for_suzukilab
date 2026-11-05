# Architecture

How this project is put together, and why. For a new project this is the
specification to build from; afterwards it is kept true as the project
changes. The rules that apply to every task are in AGENTS.md.

The app replaces the LabVIEW program `Labview_fmr/Suzuki_FMR_v06M.vi` for
field-swept, lock-in detected co-planar waveguide FMR. What that program does
is recorded in `notes/2026-11-03.md`. Parts of this design are not built yet;
the open questions that affect them are listed in TASKS.md.

## Why it runs on the host

The instruments are on GPIB (SR830, Agilent 83640B) and serial (Lake Shore
425). PyVISA reaches them through the NI-VISA and NI-488.2 drivers installed
on the Windows lab computer. Docker Desktop containers cannot use those
drivers or the GPIB interface, so the app runs natively. To keep the host
clean, every Python package lives in the repository's `.venv/`, and nothing
is written outside the repository.

## Stack

- Host: Windows 11, Python 3.14 (64-bit, via the `py` launcher), NI-VISA with
  NI-488.2, Git and GNU Make 4.4 (ezwinports build, installed for the user on
  2026-11-04 with approval). These are lab-maintained prerequisites (see
  AGENTS.md). Make is run from Git Bash, which provides `sh`.
- Backend: FastAPI served by uvicorn on `127.0.0.1`, with typed Pydantic
  request and response models; `/docs` is the contract.
- Instruments: PyVISA using the NI-VISA backend (`visa64.dll`). It is the
  standard Python interface to VISA and lets one code path drive GPIB and
  serial. pyserial is not needed; the Lake Shore is opened as a VISA
  `ASRL` resource.
- Frontend: static HTML and JavaScript, with no build step for our own code.
  Plotly draws the live plots. A pinned, checksum-verified copy is fetched by
  `make vendor` into gitignored `src/web/vendor/`; no browser CDN is used.
- Dependencies: declared in `pyproject.toml` and pinned with hashes in
  `requirements.lock`. `make install` creates `.venv/` and installs exactly
  the lock.

## Layout

```text
src/app/
  api.py               routes only; also serves src/web/
  models.py            Pydantic request/response and settings models
  config.py            reads .env: instrument mode, VISA addresses, limits
  calibration.py       Oe <-> V conversions, modulation RMS field,
                       gaussmeter correction, sweep/ramp voltages,
                       Kittel resonance estimate
  measurement.py       limit checks and the sweep run engine
  preview.py           derived values shown before a run
  storage.py           writes LabVIEW-compatible sweep files
  hardware_check.py    identifies real instruments (make hardware-check)
  instruments/
    base.py            typed interfaces each driver implements
    hardware.py        opens the real instruments through PyVISA
    sr830.py           lock-in: reference, sine output, filter, Aux Out, X/θ
    lakeshore425.py    gaussmeter: single field reading
    agilent83640b.py   RF source: CW frequency, power, output on/off
    magnet.py          Kepco supply driven through SR830 Aux Out (ramps)
    simulated.py       simulated instruments with a synthetic FMR line
    (stepper.py        TIMS rotation stage: not built; only if needed, Q4)
src/web/               the page: index.html, app.js, styles.css
tests/YYYY-MM-DD/      pytest, one folder per task day (see AGENTS.md);
                       tests/2026-11-04/smoke_check.py is run by make smoke
notes/                 daily implementation records, named YYYY-MM-DD.md
docs/                  decisions worth remembering, one short file each
data/measurements/     gitignored; saved sweeps
Labview_fmr/           the original LabVIEW VI, kept for reference only
artifacts/             gitignored browser screenshots
.cache/                gitignored tool caches (pip, Playwright browsers)
.venv/                 gitignored Python environment
Makefile  README.md  ARCHITECTURE.md  AGENTS.md  CLAUDE.md  TASKS.md
pyproject.toml  requirements.lock  .gitignore  .env.example
```

## Instruments

- Each driver implements the interface in `instruments/base.py` and has a
  simulated twin in `simulated.py`. `FMR_INSTRUMENTS=simulated` (the default,
  and always in tests) or `hardware`, set in `.env`, selects which ones the app
  builds. VISA addresses come from `.env`; the LabVIEW defaults are SR830
  `GPIB0::8::INSTR`, 83640B `GPIB0::19::INSTR` and Lake Shore `ASRL3::INSTR`
  (COM3).
- The simulated lock-in returns a derivative-Lorentzian signal around a
  resonance field set by a Kittel-like relation, plus noise. Field readback
  follows Aux Out through the calibration. This lets the whole run engine and
  page be tested without hardware.
- Drivers send instrument commands only. They do not decide limits or
  sequence; `measurement.py` does. Driver tests check the exact command
  strings against a fake VISA resource.
- The SR830 is never sent `*RST`, because it zeroes the Aux outputs and would
  step the magnet instead of ramping it. The magnet ramp starts from the Aux
  Out voltage read back from the lock-in.
- PyVISA is imported only when the hardware lab is opened, so simulated mode
  never loads NI-VISA.

## Measurement engine

- One run at a time, as a background task. Its inputs are a validated
  `RunSettings` model: frequencies (GHz), RF power (dBm), Aux Out begin, end
  and step (V), waits, ramp steps and saturation time, modulation amplitude
  and frequency, lock-in settings, orientation, file prefix and calibration
  constants.
- Sequence per frequency, following the VI: set RF CW frequency and turn on
  power; ramp the field to the start; wait to saturate; step Aux Out, waiting
  after each step, and read the corrected field (Lake Shore) and X and θ
  (SR830); then turn modulation and RF off, ramp the field to about 0, and
  save the sweep.
- Skip ends the current frequency and moves to the next. Stop ends the run
  after the safe shutdown. A `try/finally` guarantees the shutdown (RF off,
  modulation off, field ramped down) on every exit path, including driver
  errors. Each shutdown step is attempted even if an earlier one fails; every
  failure is logged and listed in `shutdown_errors`, and the run is `failed`.
- The points of a skipped, stopped or failed sweep are saved too; the sweep's
  `state` says which.
- The run executes in a thread, because VISA I/O blocks. The runner keeps one
  lab open, allows one active run, and keeps the last 20 runs in memory. A
  restart forgets past runs, but their files remain. While a run is active,
  `/api/instruments` returns the identities cached at its start rather than
  talking to busy instruments.
- Settings are checked against the limits in `config.py` before the run
  starts. Values are pending (TASKS.md, Q8).

## Calibration

The values here are results, so they are computed in `calibration.py`, not in
the browser. Starting values come from the VI and are editable settings,
not constants in code:

- field per Aux Out volt: about 996.3 Oe/V with one Kepco supply, about
  1984.4 Oe/V with two; the Aux Out sign is inverted;
- gaussmeter correction: scale 1.544, offset −11.956 Oe (08/20/2026);
- modulation: 5.219 Oe/V at 700 Hz, so modulation RMS field = sine amplitude
  × scale;
- the sweep-window estimate from the guesses for γ (MHz/Oe) and Meff.

## Data files

- One file per sweep in `data/measurements/`. Tab-delimited, `%.6e`, columns
  H (Oe), signal X (V) and phase (deg). The name follows the LabVIEW pattern,
  for example `prefix-10000MHz-In-plane-000.0deg-+0dBm2.0OeRMS-.csv`, so the
  analysis app can read the files unchanged (format details: Q6).
- Files are written once and never modified. An existing name is never
  overwritten; the run fails before measuring instead.

## API

- `GET /api/settings/defaults`: default `RunSettings`, resonance-estimate
  guesses, active limits and instrument mode.
- `POST /api/preview`: field range and step, points per sweep, modulation
  field, estimated duration, resonance estimates, file names and limit
  problems for given settings, so the page shows them without calculating.
- `GET /api/instruments`: mode, configured addresses and identification
  strings.
- `POST /api/runs`: start a run from `RunSettings` (HTTP 201; 409 if one is
  active; 422 if invalid, out of limits, or a file name is taken).
- `GET /api/runs/latest`: the most recent run, so a reloaded page resumes.
- `GET /api/runs/{run_id}?since=N`: state, sweeps, error, shutdown errors and
  the data points after index `N`, for live plotting by polling.
- `POST /api/runs/{run_id}/skip`, `POST /api/runs/{run_id}/stop` (HTTP 202).
- Models forbid unknown fields and non-finite numbers.

## Browser

- A settings form, start/skip/stop controls, run status, and live plots of
  signal and phase against the measured field. All plotted values come from
  the API.

## Makefile

`make help` (the default) lists every target.

- `install`: create `.venv/` with `py -3.14` and install `requirements.lock`.
  `vendor`: fetch the pinned Plotly file and check its hash.
- `run`: start the app on `127.0.0.1:${FMR_PORT:-8765}`; Ctrl+C stops it.
- `verify`: lint, test and smoke, with simulated instruments. Must pass from
  a fresh clone with only the host prerequisites installed.
- `test` (`TEST_PATHS` selects files), `lint` (Ruff, changes nothing), `fmt`.
- `smoke`: start the app with uvicorn in simulated mode, check the page and
  Plotly are served, run a short sweep over HTTP, check the returned data and
  saved file (under `.cache/smoke-data/`), and stop the app.
- `browser` (planned, not built yet): Playwright and Chromium inside
  `.venv/` and `.cache/`, checking the page at desktop and mobile widths.
  It will join `verify` when built.
- `hardware-check`: only when asked, identify each real instrument (`*IDN?`
  and equivalents) without changing any output.
- `lock`: after changing `pyproject.toml`, regenerate `requirements.lock`.
- `review`, `fresh-verify` (clone the committed branch into `.cache/` and
  run `verify`), `clean` (remove `.venv/`, caches and generated files; keep
  `data/` and `.env`).
- The Makefile runs under Git Bash (`/bin/sh`) on Windows and calls the
  environment's Python as `.venv/Scripts/python.exe`.
