"""HTTP contract: validation, run lifecycle and the preview."""

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import AppConfig
from app.instruments.simulated import create_simulated_lab
from app.models import Limits

FAST = {
    "frequencies_ghz": [10.0],
    "aux_begin_v": -2.7,
    "aux_end_v": -2.9,
    "aux_step_v": 0.005,
    "step_wait_ms": 0,
    "ramp_wait_ms": 0,
    "saturate_wait_ms": 0,
    "zero_wait_ms": 0,
}


@pytest.fixture
def client(tmp_path):
    config = AppConfig(
        instrument_mode="simulated",
        sr830_address="GPIB0::8::INSTR",
        rf_source_address="GPIB0::19::INSTR",
        lakeshore_address="ASRL3::INSTR",
        magnet_aux_channel=1,
        data_dir=tmp_path,
        limits=Limits(),
    )
    sim = create_simulated_lab()
    app = create_app(config, lambda: sim.lab, sleep=lambda _s: None)
    with TestClient(app) as test_client:
        yield test_client


def test_defaults_and_page(client):
    body = client.get("/api/settings/defaults").json()
    assert body["instrument_mode"] == "simulated"
    assert body["settings"]["calibration"]["field_per_volt_oe"] == 996.3
    assert "FMR acquisition" in client.get("/").text


def test_preview_reports_fields_and_resonance(client):
    response = client.post("/api/preview", json={"settings": FAST})
    assert response.status_code == 200
    body = response.json()
    assert body["begin_field_oe"] == pytest.approx(2690.01)
    assert body["points_per_sweep"] == 41
    assert body["resonances"][0]["inside_sweep"] is True
    assert body["limit_errors"] == []


def test_invalid_and_unsafe_settings_are_rejected(client):
    bad = client.post("/api/runs", json={**FAST, "aux_step_v": -1})
    assert bad.status_code == 422
    unknown = client.post("/api/runs", json={**FAST, "surprise": 1})
    assert unknown.status_code == 422
    unsafe = client.post("/api/runs", json={**FAST, "aux_end_v": -9})
    assert unsafe.status_code == 422
    assert any("aux_end_v" in e for e in unsafe.json()["detail"])


def test_run_lifecycle(client):
    assert client.get("/api/runs/latest").status_code == 404
    created = client.post("/api/runs", json=FAST)
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    client.app.state.runner.wait(run_id, timeout_s=30)

    status = client.get(f"/api/runs/{run_id}").json()
    assert status["state"] == "finished"
    assert status["next_index"] == 41
    assert len(status["points"]) == 41
    tail = client.get(f"/api/runs/{run_id}?since=40").json()
    assert [p["index"] for p in tail["points"]] == [40]
    assert client.get("/api/runs/latest").json()["run_id"] == run_id
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get(f"/api/runs/{run_id}?since=-1").status_code == 422

    again = client.post("/api/runs", json=FAST)
    assert again.status_code == 422
    assert "already exists" in again.json()["detail"][0]


def test_instruments_identify(client):
    body = client.get("/api/instruments").json()
    assert body["mode"] == "simulated"
    assert all(i["identity"].startswith("Simulated") for i in body["instruments"])
