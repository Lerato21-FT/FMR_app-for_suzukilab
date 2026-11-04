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
  NI-488.2, Git and GNU Make. These are lab-maintained prerequisites (see
  AGENTS.md). Make is not yet on the lab computer (TASKS.md, Q1).
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
                       gaussmeter scale/offset correction
  measurement.py       the sweep run engine (background task, skip/stop)
  storage.py           writes LabVIEW-compatible CSV files
  instruments/
    base.py            typed interfaces each driver implements
    sr830.py           lock-in: reference, sine output, filter, Aux Out, X/θ
    lakeshore425.py    gaussmeter: single field reading
    agilent83640b.py   RF source: CW frequency, power, output on/off
    magnet.py          Kepco supply driven through SR830 Aux Out
    stepper.py         TIMS rotation stage (only if still needed, Q4)
    simulated.py       simulated instruments with a synthetic FMR line
src/web/               the page: index.html, app.js, styles.css
tests/YYYY-MM-DD/      pytest, one folder per task day (see AGENTS.md)
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
  sequence; `measurement.py` does.

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
  errors. Errors are recorded on the run and returned by the API.
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

- `GET /api/instruments`: mode, configured addresses and identification
  strings.
- `POST /api/runs`: start a run from `RunSettings` (HTTP 409 if one is
  active, 422 if invalid or out of limits).
- `GET /api/runs/{run_id}?since=N`: state, current frequency and step, error,
  and the data points after index `N`, for live plotting by polling.
- `POST /api/runs/{run_id}/skip`, `POST /api/runs/{run_id}/stop`.
- `GET /api/calibration/preview`: field and modulation values for given
  settings, so the page can show them without calculating them.

## Browser

- A settings form, start/skip/stop controls, run status, and live plots of
  signal and phase against the measured field. All plotted values come from
  the API.

## Makefile

`make help` (the default) lists every target.

- `install`: create `.venv/` with `py -3.14` and install `requirements.lock`.
  `vendor`: fetch the pinned Plotly file and check its hash.
- `run`: start the app on `127.0.0.1:${FMR_PORT:-8765}`; Ctrl+C stops it.
- `verify`: lint, test, smoke and browser, with simulated instruments. Must
  pass from a fresh clone with only the host prerequisites installed.
- `test` (`TEST_PATHS` selects files), `lint` (Ruff, changes nothing), `fmt`.
- `smoke`: start the app in simulated mode, run a short sweep through the API,
  check the returned data, and stop the app.
- `browser`: Playwright and Chromium inside `.venv/` and `.cache/`, checking
  the page at desktop and mobile widths.
- `hardware-check`: only when asked, identify each real instrument (`*IDN?`
  and equivalents) without changing any output.
- `lock`: after changing `pyproject.toml`, regenerate `requirements.lock`.
- `review`, `fresh-verify` (clone the committed branch into `.cache/` and
  run `verify`), `clean` (remove `.venv/`, caches and generated files; keep
  `data/` and `.env`).
- The Makefile runs under Git Bash (`/bin/sh`) on Windows and calls the
  environment's Python as `.venv/Scripts/python.exe`.
