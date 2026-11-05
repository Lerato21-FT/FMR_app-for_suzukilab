"""Calibration conversions and the Kittel resonance estimate."""

import itertools
import math

import pytest

from app.calibration import (
    aux_voltage_to_field_oe,
    corrected_field_oe,
    estimate_resonance_field_oe,
    field_to_aux_voltage,
    modulation_rms_oe,
    ramp_voltages,
    raw_reading_for_field,
    sweep_voltages,
)
from app.models import CalibrationSettings, Orientation

CAL = CalibrationSettings()


def test_inverted_aux_output_gives_positive_field_for_negative_volts():
    assert aux_voltage_to_field_oe(-1.0, CAL) == pytest.approx(996.3)
    assert field_to_aux_voltage(996.3, CAL) == pytest.approx(-1.0)


def test_non_inverted_aux_output():
    cal = CalibrationSettings(aux_output_inverted=False, field_per_volt_oe=1984.4)
    assert aux_voltage_to_field_oe(2.0, cal) == pytest.approx(3968.8)


def test_gaussmeter_correction_uses_scale_and_offset():
    # Values recorded on the LabVIEW panel: scale 1.544, offset -11.956 Oe.
    assert corrected_field_oe(1000.0, CAL) == pytest.approx(1532.044)
    assert corrected_field_oe(raw_reading_for_field(2500.0, CAL), CAL) == pytest.approx(
        2500.0
    )


def test_modulation_rms_field():
    # 5.219 Oe/V at 700 Hz, from the VI panel.
    assert modulation_rms_oe(0.4, CAL) == pytest.approx(2.0876)


def test_sweep_voltages_include_both_ends():
    volts = sweep_voltages(-2.5, -3.1, 0.002)
    assert len(volts) == 301
    assert volts[0] == -2.5
    assert volts[-1] == pytest.approx(-3.1)
    assert all(b < a for a, b in itertools.pairwise(volts))


def test_sweep_voltages_short_last_step():
    assert sweep_voltages(0.0, 1.0, 0.3) == pytest.approx([0.0, 0.3, 0.6, 0.9, 1.0])


def test_sweep_voltages_reject_bad_input():
    with pytest.raises(ValueError):
        sweep_voltages(0.0, 1.0, 0.0)
    with pytest.raises(ValueError):
        sweep_voltages(1.0, 1.0, 0.1)


def test_ramp_excludes_start_and_limits_step():
    assert ramp_voltages(0.0, 0.25, 0.1) == pytest.approx([0.1, 0.2, 0.25])
    assert ramp_voltages(-0.3, 0.0, 0.1) == pytest.approx([-0.2, -0.1, 0.0])
    assert ramp_voltages(0.5, 0.5, 0.1) == []


def test_in_plane_resonance_satisfies_kittel():
    field = estimate_resonance_field_oe(10.0, 2.8, 140.0, Orientation.IN_PLANE)
    four_pi_m = 4 * math.pi * 140.0
    assert field is not None
    assert 2.8e-3 * math.sqrt(field * (field + four_pi_m)) == pytest.approx(10.0)
    assert field == pytest.approx(2798.5, abs=0.5)


def test_out_of_plane_resonance():
    field = estimate_resonance_field_oe(10.0, 2.8, 140.0, Orientation.OUT_OF_PLANE)
    assert field == pytest.approx(10_000 / 2.8 + 4 * math.pi * 140.0)


def test_out_of_plane_without_positive_solution():
    assert (
        estimate_resonance_field_oe(1.0, 2.8, -500.0, Orientation.OUT_OF_PLANE) is None
    )
