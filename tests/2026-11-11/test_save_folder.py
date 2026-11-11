"""The user names a save folder; sweeps land in it, inside the data directory."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import create_app
from app.config import PROJECT_ROOT, AppConfig
from app.instruments.simulated import create_simulated_lab
from app.measurement import MeasurementRunner
from app.models import DataPoint, Limits, RunSettings
from app.storage import SweepStore, sweep_file_name, sweep_relative_path

FAST = {
    "frequencies_ghz": [10.0],
    "field_range_oe": 20.0,
    "step_wait_ms": 1,
    "lockin": {"time_constant_index": 0},
    "ramp_wait_ms": 0,
    "saturate_wait_ms": 0,
    "zero_wait_ms": 0,
}


@pytest.mark.parametrize("folder", ["", "2026-11-11_CoFeB", "CoFeB/run_2", "a.b-c"])
def test_safe_folder_names_are_accepted(folder):
    assert RunSettings(save_folder=folder).save_folder == folder


@pytest.mark.parametrize(
    "folder",
    [
        "..",
        "../outside",
        "a/../../b",
        "/absolute",
        "C:/Users",
        "C:",
        r"a\b",
        "a//b",
        "a/",
        "./a",
        "trailing.",
        "CON",
        "nul/x",
        "com1",
        "with space",
    ],
)
def test_unsafe_folder_names_are_rejected(folder):
    with pytest.raises(ValidationError):
        RunSettings(save_folder=folder)


def test_relative_path_puts_the_file_in_the_folder():
    settings = RunSettings(save_folder="CoFeB/run_2")
    name = sweep_file_name(settings, 10.0)
    assert sweep_relative_path(settings, 10.0) == f"CoFeB/run_2/{name}"
    assert sweep_relative_path(RunSettings(), 10.0) == name


def test_store_refuses_paths_that_leave_its_directory(tmp_path):
    store = SweepStore(tmp_path / "data")
    point = DataPoint(
        index=0,
        sweep_index=0,
        aux_voltage_v=0.0,
        field_oe=1.0,
        signal_x_v=0.0,
        phase_deg=0.0,
    )
    with pytest.raises(ValueError, match="outside"):
        store.write("../escape.csv", [point])
    assert not (tmp_path / "escape.csv").exists()


def test_run_saves_into_the_chosen_folder(tmp_path):
    sim = create_simulated_lab()
    runner = MeasurementRunner(
        lambda: sim.lab, SweepStore(tmp_path), Limits(), lambda _s: None
    )
    settings = RunSettings(save_folder="sample_A", **FAST)
    status = runner.wait(runner.start(settings).run_id, timeout_s=30)
    saved = tmp_path / "sample_A" / sweep_file_name(settings, 10.0)
    assert status.sweeps[0].saved
    assert saved.is_file()
    assert len(saved.read_text().splitlines()) == status.sweeps[0].point_count


def _config(data_dir):
    return AppConfig(
        instrument_mode="simulated",
        sr830_address="GPIB0::8::INSTR",
        rf_source_address="GPIB0::19::INSTR",
        lakeshore_address="ASRL3::INSTR",
        magnet_aux_channel=1,
        data_dir=data_dir,
        limits=Limits(),
    )


def test_defaults_report_where_folders_are_created(tmp_path):
    inside = _config(PROJECT_ROOT / "data" / "measurements")
    with TestClient(create_app(inside)) as client:
        body = client.get("/api/settings/defaults").json()
    assert body["data_dir"] == "data/measurements"
    assert body["settings"]["save_folder"] == ""
    with TestClient(create_app(_config(tmp_path))) as client:
        body = client.get("/api/settings/defaults").json()
    assert body["data_dir"] == tmp_path.resolve().as_posix()


def test_api_rejects_an_escaping_folder(tmp_path):
    sim = create_simulated_lab()
    app = create_app(_config(tmp_path), lambda: sim.lab, sleep=lambda _s: None)
    with TestClient(app) as client:
        response = client.post("/api/runs", json={**FAST, "save_folder": "../x"})
    assert response.status_code == 422
    assert not any(tmp_path.parent.glob("x"))
