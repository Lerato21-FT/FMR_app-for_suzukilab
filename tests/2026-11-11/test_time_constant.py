"""SR830 index tables, and the rule time constant x 3 <= wait per step."""

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import AppConfig
from app.instruments.simulated import create_simulated_lab
from app.measurement import MeasurementRunner, RunSettingsError, check_limits
from app.models import Limits, LockInSettings, RunSettings
from app.preview import preview_run
from app.sr830_tables import (
    SENSITIVITIES,
    TIME_CONSTANTS,
    min_step_wait_ms,
    time_constant_s,
)
from app.storage import SweepStore


def _settings(tc_index: int, wait_ms: int) -> RunSettings:
    return RunSettings(
        step_wait_ms=wait_ms, lockin=LockInSettings(time_constant_index=tc_index)
    )


def _tc_errors(settings: RunSettings) -> list[str]:
    return [e for e in check_limits(settings, Limits()) if "time constant" in e]


@pytest.mark.parametrize(
    ("index", "seconds", "label"),
    [
        (0, 10e-6, "10 µs"),
        (4, 1e-3, "1 ms"),
        (8, 0.1, "100 ms"),
        (9, 0.3, "300 ms"),
        (10, 1.0, "1 s"),
        (19, 30e3, "30 ks"),
    ],
)
def test_time_constant_table_matches_the_sr830_manual(index, seconds, label):
    assert len(TIME_CONSTANTS) == 20
    option = TIME_CONSTANTS[index]
    assert option.index == index
    assert option.value == pytest.approx(seconds)
    assert option.label == label
    assert time_constant_s(index) == pytest.approx(seconds)


@pytest.mark.parametrize(
    ("index", "volts", "label"),
    [
        (0, 2e-9, "2 nV"),
        (8, 1e-6, "1 µV"),
        (17, 1e-3, "1 mV"),
        (25, 0.5, "500 mV"),
        (26, 1.0, "1 V"),
    ],
)
def test_sensitivity_table_matches_the_sr830_manual(index, volts, label):
    assert len(SENSITIVITIES) == 27
    option = SENSITIVITIES[index]
    assert option.index == index
    assert option.value == pytest.approx(volts)
    assert option.label == label


@pytest.mark.parametrize(("index", "minimum"), [(0, 1), (8, 300), (9, 900), (10, 3000)])
def test_shortest_wait_is_three_time_constants(index, minimum):
    assert min_step_wait_ms(index) == minimum


@pytest.mark.parametrize(
    ("index", "wait_ms", "allowed"),
    [
        (8, 200, False),
        (8, 299, False),
        (8, 300, True),
        (9, 899, False),
        (9, 900, True),
        (7, 90, True),
        (7, 89, False),
    ],
)
def test_wait_shorter_than_three_time_constants_is_a_limit_error(
    index, wait_ms, allowed
):
    errors = _tc_errors(_settings(index, wait_ms))
    assert (errors == []) is allowed
    if not allowed:
        assert f"at least {min_step_wait_ms(index)} ms" in errors[0]


def test_defaults_obey_the_rule():
    assert check_limits(RunSettings(), Limits()) == []
    assert RunSettings().step_wait_ms == 300


def test_preview_reports_the_shortest_allowed_wait():
    preview = preview_run(_settings(9, 200), Limits())
    assert preview.min_step_wait_ms == 900
    assert any("time constant 300 ms" in e for e in preview.limit_errors)


def test_run_is_refused_when_the_wait_is_too_short(tmp_path):
    sim = create_simulated_lab()
    runner = MeasurementRunner(
        lambda: sim.lab, SweepStore(tmp_path), Limits(), lambda _s: None
    )
    with pytest.raises(RunSettingsError) as caught:
        runner.start(_settings(8, 200))
    assert any("time constant" in e for e in caught.value.errors)
    assert not any(tmp_path.iterdir())


def test_defaults_endpoint_lists_the_labelled_options(tmp_path):
    config = AppConfig(
        instrument_mode="simulated",
        sr830_address="GPIB0::8::INSTR",
        rf_source_address="GPIB0::19::INSTR",
        lakeshore_address="ASRL3::INSTR",
        magnet_aux_channel=1,
        data_dir=tmp_path,
        limits=Limits(),
    )
    with TestClient(create_app(config)) as client:
        body = client.get("/api/settings/defaults").json()
    assert body["time_constants"][8] == {"index": 8, "value": 0.1, "label": "100 ms"}
    assert body["sensitivities"][17]["label"] == "1 mV"
