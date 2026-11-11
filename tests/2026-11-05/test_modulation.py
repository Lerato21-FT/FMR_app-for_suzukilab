"""The user sets the modulation field; the backend computes the sine drive."""

import pytest
from pydantic import ValidationError

from app.calibration import modulation_rms_oe, sine_amplitude_for_modulation
from app.instruments.simulated import create_simulated_lab
from app.measurement import MeasurementRunner
from app.models import SR830_MIN_SINE_V, CalibrationSettings, Limits, RunSettings
from app.preview import preview_run
from app.storage import SweepStore, sweep_file_name

CAL = CalibrationSettings()  # 5.219 Oe/V rms at 700 Hz


def test_two_oe_rms_needs_0_384_v():
    # 2.0 / 5.219 = 0.3832 V, rounded to the 2 mV sine resolution.
    assert sine_amplitude_for_modulation(2.0, CAL) == pytest.approx(0.384)


def test_drive_is_rounded_to_the_2_mv_sine_resolution():
    volts = sine_amplitude_for_modulation(1.0, CAL)  # 0.19161 V exactly
    assert volts == pytest.approx(0.192)
    assert modulation_rms_oe(volts, CAL) == pytest.approx(1.00205, abs=1e-4)


def test_coil_constant_is_used():
    cal = CalibrationSettings(modulation_oe_per_volt=10.0)
    assert sine_amplitude_for_modulation(2.0, cal) == pytest.approx(0.2)


@pytest.mark.parametrize("field", [0.01, 30.0])
def test_field_outside_the_sr830_sine_range_is_invalid(field):
    with pytest.raises(ValidationError, match="Oe rms"):
        RunSettings(modulation_field_oe_rms=field)


def test_preview_and_file_name_report_the_drive(tmp_path):
    settings = RunSettings(modulation_field_oe_rms=2.0)
    preview = preview_run(settings, Limits())
    assert preview.sine_amplitude_v == pytest.approx(0.384)
    assert preview.modulation_rms_oe == pytest.approx(0.384 * 5.219)
    assert "+0dBm2.0OeRMS-" in sweep_file_name(settings, 10.0)


def test_run_drives_the_lockin_with_the_computed_voltage(tmp_path):
    sim = create_simulated_lab()
    seen: list[float] = []
    original = sim.lab.lockin.set_sine_amplitude

    def record(volts: float) -> None:
        seen.append(volts)
        original(volts)

    sim.lab.lockin.set_sine_amplitude = record
    runner = MeasurementRunner(
        lambda: sim.lab, SweepStore(tmp_path), Limits(), lambda _s: None
    )
    settings = RunSettings(
        frequencies_ghz=[10.0],
        field_range_oe=20.0,
        modulation_field_oe_rms=3.0,
        step_wait_ms=1,
        lockin={"time_constant_index": 0},
        ramp_wait_ms=0,
        saturate_wait_ms=0,
        zero_wait_ms=0,
    )
    runner.wait(runner.start(settings).run_id, timeout_s=30)
    assert pytest.approx(0.574) in seen  # 3.0 / 5.219 = 0.5748 V -> 0.574 V
    assert seen[-1] == SR830_MIN_SINE_V  # modulation off at the end
