"""The run engine against simulated instruments: data, files and safe shutdown."""

import pytest

from app.calibration import estimate_resonance_field_oe
from app.instruments.simulated import create_simulated_lab
from app.measurement import MeasurementRunner, RunConflictError, RunSettingsError
from app.models import (
    SR830_MIN_SINE_V,
    Limits,
    Orientation,
    RunSettings,
    RunState,
    SweepState,
)
from app.storage import SweepStore, sweep_file_name
from app.sweep_plan import plan_sweeps


def fast_settings(**changes):
    base = {
        "frequencies_ghz": [10.0, 12.0],
        "field_range_oe": 400.0,
        "field_step_oe": 2.0,
        "step_wait_ms": 1,
        "lockin": {"time_constant_index": 0},
        "ramp_wait_ms": 0,
        "saturate_wait_ms": 0,
        "zero_wait_ms": 0,
    }
    base.update(changes)
    return RunSettings(**base)


def make_runner(tmp_path, sim=None, sleep=lambda _s: None):
    sim = sim or create_simulated_lab()
    runner = MeasurementRunner(lambda: sim.lab, SweepStore(tmp_path), Limits(), sleep)
    return runner, sim


def assert_safe(sim):
    assert sim.state.rf_on is False
    assert sim.state.sine_v == SR830_MIN_SINE_V
    assert sim.state.aux_v[0] == 0.0


def read_file(path):
    rows = [line.split("\t") for line in path.read_text().splitlines()]
    return [tuple(float(v) for v in row) for row in rows]


def test_run_saves_sweeps_and_finds_the_simulated_resonance(tmp_path):
    runner, sim = make_runner(tmp_path)
    settings = fast_settings()
    status = runner.wait(runner.start(settings).run_id, timeout_s=30)

    assert status.state is RunState.FINISHED
    assert status.error is None and status.shutdown_errors == []
    assert [s.state for s in status.sweeps] == [SweepState.COMPLETE] * 2
    plans, _ = plan_sweeps(settings)
    assert [s.point_count for s in status.sweeps] == [p.points for p in plans]
    assert all(s.saved for s in status.sweeps)
    assert_safe(sim)

    rows = read_file(tmp_path / sweep_file_name(settings, 10.0))
    assert len(rows) == plans[0].points
    fields = [r[0] for r in rows]
    # Field column is the gaussmeter reading after calibration: the true field.
    # The sweep is centred on the Kittel estimate and runs high to low.
    expected = estimate_resonance_field_oe(10.0, 2.0, 140.0, Orientation.IN_PLANE)
    assert fields[0] == pytest.approx(expected + 200.0, abs=1.5)
    assert fields[-1] == pytest.approx(expected - 200.0, abs=1.5)

    # The derivative line crosses zero midway between its two extrema.
    signal = [r[1] for r in rows]
    h_max = fields[signal.index(max(signal))]
    h_min = fields[signal.index(min(signal))]
    assert (h_max + h_min) / 2 == pytest.approx(expected, abs=3.0)
    assert h_max < expected < h_min


def test_failure_mid_sweep_still_shuts_down_and_keeps_data(tmp_path):
    sim = create_simulated_lab()
    meter = sim.lab.field_meter
    calls = {"n": 0}
    original = meter.read_field

    def failing_read():
        calls["n"] += 1
        if calls["n"] > 50:
            raise OSError("gaussmeter timeout")
        return original()

    meter.read_field = failing_read
    runner, _ = make_runner(tmp_path, sim)
    settings = fast_settings()
    status = runner.wait(runner.start(settings).run_id, timeout_s=30)

    assert status.state is RunState.FAILED
    assert "gaussmeter timeout" in status.error
    assert status.sweeps[0].state is SweepState.FAILED
    assert status.sweeps[0].saved
    assert status.sweeps[1].state is SweepState.PENDING
    assert len(read_file(tmp_path / sweep_file_name(settings, 10.0))) == 50
    assert_safe(sim)


def test_stop_ramps_down_and_saves_partial_sweep(tmp_path):
    sim = create_simulated_lab()
    meter = sim.lab.field_meter
    original = meter.read_field
    reads = {"n": 0}
    runner, _ = make_runner(tmp_path, sim)

    def read_then_stop():
        reads["n"] += 1
        if reads["n"] == 20:
            runner.stop(runner.latest_run_id())
        return original()

    meter.read_field = read_then_stop
    status = runner.wait(runner.start(fast_settings()).run_id, timeout_s=30)

    assert status.state is RunState.STOPPED
    assert status.sweeps[0].state is SweepState.STOPPED
    assert status.sweeps[0].point_count == 20
    assert status.sweeps[1].state is SweepState.PENDING
    assert_safe(sim)


def test_skip_moves_to_next_frequency(tmp_path):
    sim = create_simulated_lab()
    meter = sim.lab.field_meter
    original = meter.read_field
    reads = {"n": 0}
    runner, _ = make_runner(tmp_path, sim)

    def read_then_skip():
        reads["n"] += 1
        if reads["n"] == 10:
            runner.skip(runner.latest_run_id())
        return original()

    meter.read_field = read_then_skip
    status = runner.wait(runner.start(fast_settings()).run_id, timeout_s=30)

    assert status.state is RunState.FINISHED
    assert status.sweeps[0].state is SweepState.SKIPPED
    assert status.sweeps[0].point_count == 10
    assert status.sweeps[1].state is SweepState.COMPLETE
    assert_safe(sim)


def test_limits_are_checked_before_anything_is_sent(tmp_path):
    runner, sim = make_runner(tmp_path)
    with pytest.raises(RunSettingsError) as info:
        runner.start(fast_settings(field_range_oe=8000.0, rf_power_dbm=24))
    messages = " ".join(info.value.errors)
    assert "V limit" in messages and "RF power" in messages
    assert runner.latest_run_id() is None
    assert sim.state.rf_hz == 0.0


def test_existing_file_is_never_overwritten(tmp_path):
    settings = fast_settings()
    (tmp_path / sweep_file_name(settings, 12.0)).write_text("keep me")
    runner, _ = make_runner(tmp_path)
    with pytest.raises(RunSettingsError, match="already exists"):
        runner.start(settings)
    assert (tmp_path / sweep_file_name(settings, 12.0)).read_text() == "keep me"


def test_only_one_run_at_a_time(tmp_path):
    import threading

    release = threading.Event()
    runner, sim = make_runner(tmp_path, sleep=lambda _s: release.wait(5))
    first = runner.start(fast_settings(file_prefix="first"))
    try:
        with pytest.raises(RunConflictError):
            runner.start(fast_settings(file_prefix="second"))
    finally:
        runner.stop(first.run_id)
        release.set()
    assert runner.wait(first.run_id, timeout_s=30).state is RunState.STOPPED
    assert_safe(sim)
