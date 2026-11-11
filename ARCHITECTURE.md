# Architecture

How this project is put together, and why. For a new project this is the
specification to build from; afterwards it is kept true as the project
changes. The rules that apply to every task are in AGENTS.md.

## Stack

- Backend: Python 3.14 (base image `python:3.14.0-slim-bookworm`)
  and FastAPI, with typed request and response models; `/docs` is the
  contract.
- Frontend: static HTML and JavaScript, with no build step for our own code.
  Plotly is vendored into the image for the scientific plots; no browser CDN
  is used.
- The app runs in one development container, as the host user; browser
  validation uses a separate test container.

## Layout

```text

src/app/             the backend: api.py (routes only), pipeline.py, models.py
                     dataset_store.py manages validated, temporary uploads
src/web/             the page: index.html, app.js, styles.css
tests/               pytest
docs/                decisions worth remembering, one short file each
notes/               daily implementation records, named YYYY-MM-DD.md
artifacts/           gitignored browser screenshots and exported plots
.cache/buildx/       gitignored Docker builder metadata kept inside the repo
data/                for future datasets: raw/ is never modified,
                     processed/ is gitignored
Makefile  README.md  ARCHITECTURE.md  AGENTS.md  CLAUDE.md
.gitignore .dockerignore .env.example
```

## Backend

- One pipeline per API endpoint, each with one entry-point function in
  `pipeline.py`. The API calls it; tests may call any function.
- `api.py` holds routes only. It also serves our page from `src/web/` and the
  frontend libraries under `/vendor/`.
- `dataset_store.py` stages CSV uploads under the container's `/tmp`, validates
  every CSV and fit setting before activating it, and serializes reads against
  replacement. Geometry and fit initialization are activated atomically with
  the files and retained for later API calls and page reloads. Uploads are
  limited to 100 MB and 1000 files.
- Upload validation uses `validate_dataset`: frequency metadata must be positive
  and finite, with at least eight finite numeric field/signal rows per CSV.
  Resonance extraction and aggregate fit success do not gate activation.
- `pipeline.py` owns CSV parsing, resonance extraction, and both scientific
  fits. The frontend receives complete data and fit curves from the API.
- Analysis accepts request-scoped `excluded_measurement_ids`, validated for
  length, uniqueness and membership in the active dataset. Both aggregate
  fits use the same included subset; damping uses its refitted g factor.
  Responses retain every resonance point with an `excluded` flag and report
  `included_measurement_count`. Failed per-sweep extractions retain their IDs
  and `extraction_error`, with null extracted values. They must be explicitly
  excluded before fitting the remaining measurements.
- A valid analysis returns all measurements even when scientific fitting is
  unavailable: both aggregate fits are null and `fit_error` explains why.
  This includes fewer than four included sweeps, negative fitted resonances
  unsupported by the perpendicular model, and nonphysical linewidth fits.
  Invalid settings, CSVs, and exclusion IDs remain HTTP 422 errors.
- `analyze_trace` returns raw samples independently of resonance fit success;
  a failed fit has null parameters, an empty curve, and `extraction_error`.
  Signed field coordinates are preserved throughout; no absolute-field
  conversion or implicit branch selection is performed.
- Analysis selects the aligned-axis in-plane Kittel model or the saturated
  perpendicular model `f = (g μB/h)(Bres − Beff,⊥)`, using the convention
  `Beff,⊥ = μ0 Ms − μ0 H2⊥`. Perpendicular defaults are −0.4 T and 10 Oe
  peak-to-peak linewidth; these initialize fits, not fixed results.
  The perpendicular model returns no four-fold term (`null` in the API).

## Acquisition page

`src/web/` is one page that fills the window as four quadrants, modelled
on the LabVIEW front panel (`Labview_fmr/`). A single `<form>` spans all
four, so every named input is part of `RunSettings`.

| Quadrant | Contents |
|---|---|
| Top left: Data | Signal X and phase θ against H, with a sweep selector |
| Top right: instrument setup | Tabs named as in the VI: **H field setup** (ramp, waits, H conversion, H read scale/offset, invert Vaux, Kittel g and Meff), **A83640B** (RF power), **SR830** (reference, time constant, sensitivity, modulation field and coil constant), **Stepper Motor** (placeholder until Q4 and task 6) |
| Bottom left: measurement list | Frequencies (comma, space or newline separated), orientation, angle (file name only), field range and step, save folder and file prefix |
| Bottom right: run | Measure / Skip / Stop All, run status and errors, the backend preview as a table (Hres, sweep, points and file path per frequency) |

Below 900 px the quadrants stack and the page scrolls. The save folder is a
relative name (`RunSettings.save_folder`, up to four `/`-separated parts).
The API rejects `..`, absolute paths, drive letters, backslashes and Windows
device names. `SweepStore` also refuses any path that resolves outside
the data directory, so measurement data stays inside the repository.
`GET /api/settings/defaults` reports that data directory for the page to show.
`src/app/sr830_tables.py` holds the SR830 time-constant (OFLT) and
sensitivity (SENS) tables. The defaults endpoint sends them with labels, and
the page shows them as dropdowns. `check_limits` refuses a wait per step
shorter than 3 time constants, and the preview reports that minimum.
The page and `/vendor/` files are served with `Cache-Control: no-cache`, so a
browser never runs an old `app.js` or `styles.css` against a new `index.html`.
`tests/2026-11-11/test_page_layout.py` checks the quadrants, the tab names, and
that every run setting and every element the script uses exists. The page has
not been checked in a real browser yet (task 5, `make browser`).

## Browser

The rest of this section describes the earlier analysis app and is rewritten
in task 7.

- Geometry controls select upload/analysis API settings. Switching to a
  different geometry requires a matching folder; old plots are hidden until
  measurements for that geometry are loaded.
- All scientific points, parameters and curves come from the API.
  JavaScript formats labels, displays equations and handles interaction.
- Clicking markers on either scientific chart or using an accessible dataset
  list selects sweep IDs. Exclude/restore controls request a new analysis;
  selected markers are cyan and excluded markers are gray crosses in both
  plots. A failed request leaves the previous results available. Exclusions
  survive refits within the page and reset on reload or a successful upload.
- Valid responses with unavailable fits clear previous property values and
  curves, display an explanatory status, and retain point selection and raw
  inspection. Failed extractions are labeled in the dataset and trace lists;
  their missing coordinates are not plotted. Raw traces still render with an
  unavailable-fit annotation. PNG exports also indicate unavailable fits.
- Plotly charts render after their results section becomes visible, resize
  with `ResizeObserver`, and become one column below 1100 px. Equations,
  legends and axes have reserved margins. PNGs include fitted values and
  an opaque background.

## The container

- The Dockerfile separates build dependencies, app runtime and browser checks:
  one stage with uv only (where `make lock` runs,
  so the first lock needs no lock), one with Node for the frontend libraries,
  and the final app image with both sets of locked dependencies. Compose
  explicitly selects the `app` target. Separate `browser-deps` and
  `browser-runtime`/`browser-checks` stages install the optional Playwright group and
  Chromium with system dependencies at build time. Browser tooling is
  excluded from the normal app image. The profiled `browser` service has no
  published ports, runs as the host user with read-only root and `/tmp`
  tmpfs, and writes artifacts only to the repository's `artifacts/` mount.
- The image contains `src/`, `tests/`, and `docker/pyproject.toml` under
  `/work`, with `PYTHONPATH=/work/src`. Supplied CSVs are copied into the image
  at `/data` as read-only data. Application code and data are read from the
  image because Python received `EDEADLK` reading the macOS bind mount in
  this environment. `.dockerignore` allows only the required build inputs.
  After local code changes, `make up` rebuilds the image and starts the app
  with the updated code.
- Frontend libraries are installed at build time from `package-lock.json` and
  copied into the image. Never installed on the host, never committed, never
  loaded from a CDN.
- The app service publishes on `127.0.0.1` and runs without host bind mounts;
  the Makefile loads `.env` when it exists. The container filesystem is
  read-only except for `/tmp`.
- The bundled dataset is the startup default. Uploaded datasets are held only
  in container `/tmp` (a tmpfs), replace the active dataset after successful
  validation, and are discarded when the container stops. Plot images are
  exported by Plotly in the browser and are not stored by the backend.

## Makefile

`make help` (the default) lists every target in three groups.

Everyday, the only ones a user needs:

- `build`: build everything the project needs, into the image.
- `up` and `down`: start and stop the app.
- `verify`: check that it all works (lint, test, smoke, browser). Must pass from a
  fresh clone with only Docker, Make and git installed.
- `clean`: return to the state of a fresh clone on a fresh computer. This
  project's containers, images and generated files are removed; `data/raw/`
  and `.env` are kept.

While developing:

- `test`: run the tests copied into the image; `TEST_PATHS` can select test
  files. `lint`: check the code copied into the image, changing nothing.
  Both rebuild first. `fmt`: rewrite the host source and tests into the
  standard format using explicit writable mounts for this command only.
- `smoke`: start the app, check a real API result (not just a status code),
  stop it again.
- `logs` and `shell`: follow the app's output; open a shell inside the
  container.
- `browser`: build the separate browser image and run real Chromium
  upload/refit/reload/export checks against an isolated API inside that
  container. Check page overflow, clipped labels and equation/legend
  overlap at desktop and mobile sizes. Save screenshots and PNGs to
  gitignored `artifacts/`.
- `review`: check Git diff whitespace and display status/statistics.
- `fresh-verify`: clone the committed feature branch into a new directory
  under repository `.cache/` and run `make verify` there. No `.env` or
  uncommitted files are copied. The checkout is kept for inspection.
- `fmt` accepts `FORMAT_PATHS` to limit formatting to selected files.

Only when dependencies change:

- `lock`: after adding, removing or upgrading a package in
  `docker/pyproject.toml` or `docker/package.json`, record the exact versions
  in `docker/uv.lock` and `docker/package-lock.json`, and commit each manifest
  with its lock. `build` uses only what the locks record, and says so, with
  this instruction, when a manifest and its lock disagree.

Container targets run through compose (`docker compose -f docker/compose.yaml`);
`lock` uses build-tool containers directly. Read-only Git review and creating
the artifact directory need no container. The Makefile sets `BUILDX_CONFIG`
to repository-local `.cache/buildx/`, keeping builder activity metadata out
of the host's Docker config folder.
