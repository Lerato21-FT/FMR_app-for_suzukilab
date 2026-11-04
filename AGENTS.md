# Standards for this repository

These rules apply to every task. How the project is built is described in
ARCHITECTURE.md: read it before creating or moving files, adding a dependency,
or changing the Makefile or the instrument drivers, and keep it true when you
change the design.

## Boundaries (these override everything else)

- The app runs natively on the Windows lab computer, not in Docker. It drives
  the instruments with PyVISA over GPIB (and serial) through the NI-VISA
  library installed on that computer, which a container cannot reach.
- Host prerequisites are installed and maintained by the lab, never by an
  agent: Python 3.14 (64-bit, `py` launcher), NI-VISA with NI-488.2, Git and
  GNU Make. Do not install, upgrade or reconfigure any of them.
- Python packages are installed only into the repository's `.venv/`, from the
  committed lock, by `make install`. NOTHING else is installed on the host: no
  global or user-level pip installs, packages, tools, drivers, runtimes or
  global configuration, by any means. If you believe another host install is
  truly unavoidable, stop, explain why, and wait for my explicit approval of
  that specific install. Expect the answer to be no.
- Every change on the host happens inside this repository. Nothing is written
  outside this directory tree, including measurement data and tool caches. An
  agent's own memory or global instruction file is the only possible
  exception, and only when I have agreed.
- Powerful commands (pip, curl, wget, and their like) run only inside Makefile
  targets. Never run them as one-off commands, and never tuck them inside a
  longer command or script. Anything run more than once (testing, validation,
  a data step) belongs in the Makefile; if a task needs a new command, add a
  target and say so.
- Real instruments are commanded only through the app's drivers, and only when
  I have asked for a hardware test. Tests and `make verify` use the simulated
  instruments and never open a VISA session.
- Secrets live in `.env`, which is gitignored; commit a `.env.example`.

## Git

- Work on your feature branch. Commit to it often, in small steps, each with a
  clear message. You may push it.
- `main` changes only through what I review and merge. Never
  commit to, merge into, or push to `main` without my approval.
- Merging into any branch other than your feature branch needs my explicit
  approval, every time. Approval for one merge is not approval for the next.
- Never force-push, rewrite published history, or change git configuration.

## Before you start

For any task that creates or changes more than one file, reply first with your
plan, the files you will touch, your assumptions and your questions, in under
40 lines. Wait for approval.

## Invariants (true after every change)

- Results are computed by the backend and delivered through the API. The
  frontend draws and handles interaction; it computes nothing a scientist
  would call a result (a fit, a unit conversion, a filter, a statistic).
- Everything the app needs is installed by `make install` from the lock,
  never while it runs.
- The app is served on `127.0.0.1` only.
- Instrument safety: the backend rejects any setting outside the configured
  limits (field, Aux Out voltage, ramp rate, RF power) before a command
  reaches an instrument. Every run, however it ends (finished, skipped,
  stopped or failed), turns RF and modulation off and ramps the field down.
  Only one run is active at a time.

## Running anything

Through the Makefile, and nothing else. `make help` lists the targets;
`make verify` is the gate.

## Quality

Follow current best practice for code quality, structure and security, and say
in the plan where you depart from it and why. Code a stranger can read, with
type hints and docstrings on anything public. Every input validated at the API
boundary, errors handled and never swallowed. No secrets in code, logs or
error messages, no `eval`, no shell built from user input. Add a dependency
only when it earns its place, and say why.

## Done means

- `make verify` is green from a fresh clone, with simulated instruments and
  no hardware attached.
- Each pipeline has a test that fails when the result is wrong; show it
  failing once before you make it pass.
- The README is enough for a stranger, and ARCHITECTURE.md still describes the
  project.
- Say what you did not verify, including whether real hardware was used.

# Tasks
@TASKS.md for today's tasks.

# Testing
Store all tests in the tests folder. Create subfolders inside of that folder for every test related to the task of that day..
