"""The sweep run engine: one background run at a time, always shut down safely."""

import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.calibration import (
    corrected_field_oe,
    sine_amplitude_for_modulation,
    sweep_voltages,
)
from app.instruments.base import Lab
from app.instruments.magnet import AuxOutMagnet
from app.models import (
    SR830_MIN_SINE_V,
    DataPoint,
    Limits,
    RunSettings,
    RunState,
    RunStatus,
    SweepPlan,
    SweepState,
    SweepSummary,
)
from app.storage import SweepStore, sweep_file_name
from app.sweep_plan import aux_step_v, plan_sweeps

logger = logging.getLogger(__name__)

_MAX_KEPT_RUNS = 20


class RunConflictError(RuntimeError):
    """Raised when a run is requested while another is active."""


class RunSettingsError(ValueError):
    """Raised when settings break a safety limit or would overwrite a file."""

    def __init__(self, errors: list[str]) -> None:
        """Keep every problem so the API can report them together."""
        super().__init__("; ".join(errors))
        self.errors = errors


def check_limits(settings: RunSettings, limits: Limits) -> list[str]:
    """Return every way ``settings`` breaks ``limits`` (empty when safe).

    Every frequency's planned sweep is checked. Negative fields are allowed
    (the supply is bipolar); limits apply to the magnitude.
    """
    plans, errors = plan_sweeps(settings)
    for plan in plans:
        label = f"{plan.frequency_ghz} GHz"
        for end, volts, field in (
            ("start", plan.begin_v, plan.begin_field_oe),
            ("end", plan.end_v, plan.end_field_oe),
        ):
            if abs(volts) > limits.max_aux_voltage_v:
                errors.append(
                    f"{label}: {end} Aux Out {volts} V exceeds the "
                    f"{limits.max_aux_voltage_v} V limit"
                )
            if abs(field) > limits.max_field_oe:
                errors.append(
                    f"{label}: {end} field {field:.0f} Oe exceeds the "
                    f"{limits.max_field_oe:.0f} Oe limit"
                )
        if plan.points > limits.max_points_per_sweep:
            errors.append(
                f"{label}: {plan.points} points per sweep exceeds the "
                f"{limits.max_points_per_sweep} limit"
            )
    if settings.rf_power_dbm > limits.max_rf_power_dbm:
        errors.append(
            f"RF power {settings.rf_power_dbm} dBm exceeds the "
            f"{limits.max_rf_power_dbm} dBm limit"
        )
    if settings.ramp_step_v > limits.max_ramp_step_v:
        errors.append(
            f"ramp_step_v exceeds the {limits.max_ramp_step_v} V per step limit"
        )
    if aux_step_v(settings) > limits.max_ramp_step_v:
        errors.append(
            f"field_step_oe is more than {limits.max_ramp_step_v} V of Aux Out per step"
        )
    return errors


class _Run:
    """Mutable state of one run, guarded by ``lock``."""

    def __init__(self, settings: RunSettings, file_names: list[str]) -> None:
        self.run_id = uuid.uuid4().hex
        self.settings = settings
        self.lock = threading.Lock()
        self.state = RunState.RUNNING
        self.started_at = datetime.now(UTC)
        self.finished_at: datetime | None = None
        self.current_sweep: int | None = None
        self.sweeps = [
            SweepSummary(
                sweep_index=i,
                frequency_ghz=f,
                state=SweepState.PENDING,
                point_count=0,
                file_name=file_names[i],
                saved=False,
            )
            for i, f in enumerate(settings.frequencies_ghz)
        ]
        self.points: list[DataPoint] = []
        self.unsaved: list[DataPoint] = []
        self.error: str | None = None
        self.shutdown_errors: list[str] = []
        self.stop_event = threading.Event()
        self.skip_event = threading.Event()
        self.thread: threading.Thread | None = None

    def snapshot(self, since: int) -> RunStatus:
        with self.lock:
            return RunStatus(
                run_id=self.run_id,
                state=self.state,
                started_at=self.started_at,
                finished_at=self.finished_at,
                current_sweep_index=self.current_sweep,
                sweeps=[s.model_copy() for s in self.sweeps],
                points=self.points[max(since, 0) :],
                next_index=len(self.points),
                error=self.error,
                shutdown_errors=list(self.shutdown_errors),
                settings=self.settings,
            )

    def set_sweep(self, index: int, **changes: object) -> None:
        with self.lock:
            self.sweeps[index] = self.sweeps[index].model_copy(update=changes)


class MeasurementRunner:
    """Starts runs, tracks their status, and serializes access to the lab."""

    def __init__(
        self,
        lab_factory: Callable[[], Lab],
        store: SweepStore,
        limits: Limits,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Create a runner; the lab is opened lazily on first use."""
        self._lab_factory = lab_factory
        self._lab: Lab | None = None
        self._store = store
        self._limits = limits
        self._sleep = sleep
        self._lock = threading.Lock()
        self._runs: dict[str, _Run] = {}
        self._order: list[str] = []
        self._identities: dict[str, str] | None = None

    @property
    def limits(self) -> Limits:
        """The active safety limits."""
        return self._limits

    def _get_lab(self) -> Lab:
        if self._lab is None:
            self._lab = self._lab_factory()
        return self._lab

    def _active(self) -> _Run | None:
        if not self._order:
            return None
        run = self._runs[self._order[-1]]
        return run if run.state is RunState.RUNNING else None

    def identify(self) -> dict[str, str]:
        """Return identification strings, querying only when no run is active.

        Raises:
            Exception: whatever the instrument layer raises when it cannot
                identify an instrument.
        """
        with self._lock:
            if self._active() is not None and self._identities is not None:
                return dict(self._identities)
            if self._active() is not None:
                raise RunConflictError("instruments are busy with a run")
            lab = self._get_lab()
            self._identities = {
                "lockin": lab.lockin.identify(),
                "field_meter": lab.field_meter.identify(),
                "rf_source": lab.rf_source.identify(),
            }
            return dict(self._identities)

    def start(self, settings: RunSettings) -> RunStatus:
        """Validate ``settings`` and start a run in a background thread.

        Raises:
            RunSettingsError: if a limit is broken or a file name is taken.
            RunConflictError: if another run is active.
        """
        errors = check_limits(settings, self._limits)
        names = [sweep_file_name(settings, f) for f in settings.frequencies_ghz]
        if len(set(names)) != len(names):
            errors.append("two frequencies give the same file name")
        taken = self._store.existing(names)
        errors.extend(f"{name} already exists" for name in taken)
        if errors:
            raise RunSettingsError(errors)
        with self._lock:
            if self._active() is not None:
                raise RunConflictError("a run is already active")
            lab = self._get_lab()
            run = _Run(settings, names)
            self._runs[run.run_id] = run
            self._order.append(run.run_id)
            while len(self._order) > _MAX_KEPT_RUNS:
                del self._runs[self._order.pop(0)]
            run.thread = threading.Thread(
                target=self._execute, args=(run, lab), name=f"run-{run.run_id[:8]}"
            )
            run.thread.start()
        return run.snapshot(0)

    def status(self, run_id: str, since: int = 0) -> RunStatus:
        """Return a run's status and the points after index ``since``.

        Raises:
            KeyError: if the run is unknown.
        """
        return self._runs[run_id].snapshot(since)

    def latest_run_id(self) -> str | None:
        """Return the most recent run's ID, if any."""
        with self._lock:
            return self._order[-1] if self._order else None

    def skip(self, run_id: str) -> None:
        """Ask the run to end its current sweep and move to the next.

        Raises:
            KeyError: if the run is unknown.
        """
        self._runs[run_id].skip_event.set()

    def stop(self, run_id: str) -> None:
        """Ask the run to stop after the safe shutdown.

        Raises:
            KeyError: if the run is unknown.
        """
        self._runs[run_id].stop_event.set()

    def wait(self, run_id: str, timeout_s: float | None = None) -> RunStatus:
        """Block until the run's thread ends (for tests and the smoke check)."""
        run = self._runs[run_id]
        if run.thread is not None:
            run.thread.join(timeout_s)
        return run.snapshot(0)

    # The run thread -----------------------------------------------------

    def _execute(self, run: _Run, lab: Lab) -> None:
        settings = run.settings
        magnet: AuxOutMagnet | None = None
        final_state = RunState.FINISHED
        try:
            plans, plan_errors = plan_sweeps(settings)
            if plan_errors:
                raise RunSettingsError(plan_errors)
            magnet = AuxOutMagnet(lab.lockin, lab.magnet_aux_channel)
            lab.lockin.configure(settings.lockin)
            for index, plan in enumerate(plans):
                if run.stop_event.is_set():
                    break
                outcome = self._measure_sweep(run, lab, magnet, index, plan)
                self._end_sweep(lab, magnet, settings)
                self._save_sweep(run, index, outcome)
            if run.stop_event.is_set():
                final_state = RunState.STOPPED
        except Exception as exc:
            logger.exception("run %s failed", run.run_id)
            final_state = RunState.FAILED
            with run.lock:
                run.error = f"{type(exc).__name__}: {exc}"
            if run.current_sweep is not None:
                run.set_sweep(run.current_sweep, state=SweepState.FAILED)
        finally:
            shutdown_errors = self._safe_shutdown(lab, magnet, settings)
            if run.unsaved and run.current_sweep is not None:
                try:
                    self._save_sweep(run, run.current_sweep, None)
                except Exception as exc:
                    logger.exception("saving partial sweep failed")
                    shutdown_errors.append(f"saving partial sweep: {exc}")
            with run.lock:
                run.shutdown_errors = shutdown_errors
                if shutdown_errors:
                    final_state = RunState.FAILED
                run.state = final_state
                run.finished_at = datetime.now(UTC)
                run.current_sweep = None

    def _measure_sweep(
        self,
        run: _Run,
        lab: Lab,
        magnet: AuxOutMagnet,
        index: int,
        plan: SweepPlan,
    ) -> SweepState:
        settings = run.settings
        run.skip_event.clear()
        with run.lock:
            run.current_sweep = index
            run.unsaved = []
        run.set_sweep(index, state=SweepState.MEASURING)

        lab.rf_source.set_cw_frequency(plan.frequency_ghz * 1e9)
        lab.rf_source.set_power(settings.rf_power_dbm)
        lab.rf_source.set_output(True)
        lab.lockin.set_sine_amplitude(
            sine_amplitude_for_modulation(
                settings.modulation_field_oe_rms, settings.calibration
            )
        )

        reached = magnet.ramp_to(
            plan.begin_v,
            settings.ramp_step_v,
            settings.ramp_wait_ms / 1000,
            self._sleep,
            should_abort=run.stop_event.is_set,
        )
        if not reached:
            return SweepState.STOPPED
        self._sleep(settings.saturate_wait_ms / 1000)

        voltages = sweep_voltages(plan.begin_v, plan.end_v, plan.step_v)
        for volts in voltages:
            if run.stop_event.is_set():
                return SweepState.STOPPED
            if run.skip_event.is_set():
                return SweepState.SKIPPED
            magnet.set_voltage(volts)
            self._sleep(settings.step_wait_ms / 1000)
            raw = lab.field_meter.read_field()
            x_v, phase_deg = lab.lockin.read_signal()
            with run.lock:
                point = DataPoint(
                    index=len(run.points),
                    sweep_index=index,
                    aux_voltage_v=volts,
                    field_oe=corrected_field_oe(raw, settings.calibration),
                    signal_x_v=x_v,
                    phase_deg=phase_deg,
                )
                run.points.append(point)
                run.unsaved.append(point)
                count = len(run.unsaved)
            run.set_sweep(index, point_count=count)
        return SweepState.COMPLETE

    def _end_sweep(self, lab: Lab, magnet: AuxOutMagnet, settings: RunSettings) -> None:
        """Turn modulation and RF off and ramp the field to zero (as the VI does)."""
        lab.lockin.set_sine_amplitude(SR830_MIN_SINE_V)
        lab.rf_source.set_output(False)
        magnet.ramp_to(
            0.0, settings.ramp_step_v, settings.ramp_wait_ms / 1000, self._sleep
        )
        self._sleep(settings.zero_wait_ms / 1000)

    def _save_sweep(self, run: _Run, index: int, outcome: SweepState | None) -> None:
        with run.lock:
            points = list(run.unsaved)
            run.unsaved = []
            name = run.sweeps[index].file_name
        changes: dict[str, object] = {}
        if outcome is not None:
            changes["state"] = outcome
        if points:
            self._store.write(name, points)
            changes["saved"] = True
        run.set_sweep(index, **changes)

    def _safe_shutdown(
        self, lab: Lab, magnet: AuxOutMagnet | None, settings: RunSettings
    ) -> list[str]:
        """Turn RF and modulation off and ramp to zero; report every failure."""
        errors: list[str] = []
        steps: list[tuple[str, Callable[[], object]]] = [
            ("RF off", lambda: lab.rf_source.set_output(False)),
            ("modulation off", lambda: lab.lockin.set_sine_amplitude(SR830_MIN_SINE_V)),
        ]
        if magnet is not None:
            steps.append(
                (
                    "field ramp-down",
                    lambda: magnet.ramp_to(
                        0.0,
                        settings.ramp_step_v,
                        settings.ramp_wait_ms / 1000,
                        self._sleep,
                    ),
                )
            )
        else:
            errors.append("field ramp-down: magnet state unknown, Aux Out not changed")
        for label, action in steps:
            try:
                action()
            except Exception as exc:
                logger.exception("shutdown step %s failed", label)
                errors.append(f"{label}: {type(exc).__name__}: {exc}")
        return errors
