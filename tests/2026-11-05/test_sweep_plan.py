"""Sweeps centred on each frequency's Kittel resonance, and the Kittel model."""

import math

import pytest

from app.calibration import (
    aux_voltage_to_field_oe,
    centred_field_range,
    estimate_resonance_field_oe,
    gyromagnetic_ratio_mhz_per_oe,
)
from app.measurement import check_limits
from app.models import Limits, Orientation, ResonanceModel, RunSettings
from app.sweep_plan import plan_sweeps


def settings(**overrides) -> RunSettings:
    return RunSettings(**overrides)


def test_range_runs_from_high_to_low_around_the_guess():
    # The example from the request: range 1000 Oe, guess 1500 Oe.
    assert centred_field_range(1500.0, 1000.0) == (2000.0, 1000.0)


def test_g_two_gives_the_free_electron_gyromagnetic_ratio():
    assert gyromagnetic_ratio_mhz_per_oe(2.0) == pytest.approx(2.79925, abs=1e-5)


def test_in_plane_kittel_matches_apl_127_032406():
    # Eq. (2) with H4 = 0: g = 2.02 and mu0*Meff = 20 mT give mu0*Hfmr = 451 mT
    # at 13 GHz. 4*pi*Meff = 200 G, so Meff = 200 / (4*pi) emu/cc.
    meff = 200.0 / (4.0 * math.pi)
    field = estimate_resonance_field_oe(13.0, 2.02, meff, Orientation.IN_PLANE)
    assert field == pytest.approx(4510.0, abs=15.0)


def test_out_of_plane_kittel_is_unchanged():
    gamma = gyromagnetic_ratio_mhz_per_oe(2.0)
    field = estimate_resonance_field_oe(10.0, 2.0, 140.0, Orientation.OUT_OF_PLANE)
    assert field == pytest.approx(10_000.0 / gamma + 4.0 * math.pi * 140.0)


def test_each_frequency_gets_its_own_centred_sweep():
    s = settings(frequencies_ghz=[8.0, 12.0], field_range_oe=600.0)
    plans, errors = plan_sweeps(s)
    assert errors == []
    for plan, frequency in zip(plans, s.frequencies_ghz, strict=True):
        guess = estimate_resonance_field_oe(frequency, 2.0, 140.0, Orientation.IN_PLANE)
        assert plan.resonance_field_oe == pytest.approx(guess)
        # Aux Out has 1 mV steps, so endpoints land within one step of the target.
        tolerance = 0.001 * s.calibration.field_per_volt_oe
        assert plan.begin_field_oe == pytest.approx(guess + 300.0, abs=tolerance)
        assert plan.end_field_oe == pytest.approx(guess - 300.0, abs=tolerance)
        assert aux_voltage_to_field_oe(plan.begin_v, s.calibration) == pytest.approx(
            plan.begin_field_oe
        )
    assert plans[1].resonance_field_oe > plans[0].resonance_field_oe


def test_sweep_may_cross_zero_with_a_bipolar_supply():
    # A low frequency puts guess - range/2 below zero; that is allowed.
    s = settings(frequencies_ghz=[1.0], field_range_oe=1000.0)
    plans, errors = plan_sweeps(s)
    assert errors == []
    assert plans[0].end_field_oe < 0 < plans[0].begin_field_oe
    assert check_limits(s, Limits()) == []


def test_sweeps_beyond_the_limits_are_rejected():
    s = settings(frequencies_ghz=[30.0], field_range_oe=2000.0)
    errors = check_limits(s, Limits(max_field_oe=5000, max_aux_voltage_v=5.0))
    assert any("Oe limit" in e for e in errors)
    assert any("V limit" in e for e in errors)


def test_frequency_without_a_resonance_is_reported():
    s = settings(
        frequencies_ghz=[1.0],
        orientation=Orientation.OUT_OF_PLANE,
        resonance=ResonanceModel(meff_emu_cc=-500.0),
    )
    plans, errors = plan_sweeps(s)
    assert plans == []
    assert any("1.0 GHz" in e for e in errors)


def test_field_step_finer_than_aux_resolution_is_invalid():
    with pytest.raises(ValueError, match="resolution"):
        settings(field_step_oe=0.1)
