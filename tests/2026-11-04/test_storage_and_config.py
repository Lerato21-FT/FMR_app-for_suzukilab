"""File naming/format and configuration validation."""

import pytest

from app.config import AppConfig, ConfigError, resolve_data_dir
from app.models import DataPoint, RunSettings
from app.storage import FileExistsConflictError, SweepStore, sweep_file_name


def test_file_name_matches_labview_pattern():
    settings = RunSettings(file_prefix="sample1", rf_power_dbm=0)
    assert (
        sweep_file_name(settings, 10.0)
        == "sample1-10000MHz-In-plane-000.0deg-+0dBm2.0OeRMS-.csv"
    )
    assert "-10500.5MHz-" in sweep_file_name(settings, 10.5005)


def test_store_writes_tab_delimited_rows_once(tmp_path):
    store = SweepStore(tmp_path / "new")
    point = DataPoint(
        index=0,
        sweep_index=0,
        aux_voltage_v=-1.0,
        field_oe=996.3,
        signal_x_v=1.5e-6,
        phase_deg=12.0,
    )
    path = store.write("a.csv", [point])
    assert path.read_text() == "9.963000e+02\t1.500000e-06\t1.200000e+01\n"
    with pytest.raises(FileExistsConflictError):
        store.write("a.csv", [point])


def test_data_dir_must_stay_inside_repository(tmp_path):
    assert resolve_data_dir("data/x", tmp_path) == (tmp_path / "data/x").resolve()
    with pytest.raises(ConfigError):
        resolve_data_dir("../outside", tmp_path)


def test_config_from_env_defaults_and_errors(tmp_path):
    config = AppConfig.from_env({}, tmp_path)
    assert config.instrument_mode == "simulated"
    assert config.sr830_address == "GPIB0::8::INSTR"
    with pytest.raises(ConfigError):
        AppConfig.from_env({"FMR_INSTRUMENTS": "docker"}, tmp_path)
    with pytest.raises(ConfigError):
        AppConfig.from_env({"FMR_MAX_FIELD_OE": "lots"}, tmp_path)
