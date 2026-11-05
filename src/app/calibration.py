"""Conversions between instrument values and magnetic fields.

Everything here is a scientific result (a unit conversion or an estimate),
so it lives in the backend and reaches the page only through the API.
"""

import math

from app.models import CalibrationSettings, Orientation

_EPS = 1e-9


def aux_voltage_to_field_oe(voltage_v: float, cal: CalibrationSettings) -> float:
    """Return the nominal magnet field (Oe) produced by an Aux Out voltage."""
    sign = -1.0 if cal.aux_output_inverted else 1.0
    return sign * voltage_v * cal.field_per_volt_oe


def field_to_aux_voltage(field_oe: float, cal: CalibrationSettings) -> float:
    """Return the Aux Out voltage that nominally produces ``field_oe``."""
    sign = -1.0 if cal.aux_output_inverted else 1.0
    return sign * field_oe / cal.field_per_volt_oe


def corrected_field_oe(raw_reading: float, cal: CalibrationSettings) -> float:
    """Apply the gaussmeter calibration: ``H = scale * raw + offset``."""
    return cal.gaussmeter_scale * raw_reading + cal.gaussmeter_offset_oe


def raw_reading_for_field(field_oe: float, cal: CalibrationSettings) -> float:
    """Invert :func:`corrected_field_oe` (used by the simulated gaussmeter)."""
    return (field_oe - cal.gaussmeter_offset_oe) / cal.gaussmeter_scale


def modulation_rms_oe(sine_amplitude_v: float, cal: CalibrationSettings) -> float:
    """Return the modulation field (Oe rms) for an SR830 sine amplitude (V rms)."""
    return sine_amplitude_v * cal.modulation_oe_per_volt


def sweep_voltages(begin_v: float, end_v: float, step_v: float) -> list[float]:
    """Return Aux Out voltages from ``begin_v`` to ``end_v`` inclusive.

    Steps are ``step_v`` apart in the direction of ``end_v``; when the span is
    not a whole number of steps, the last step is shorter and lands on
    ``end_v``. Values are rounded to the SR830's 1 mV resolution.

    Raises:
        ValueError: if ``step_v`` is not positive or the endpoints are equal.
    """
    if step_v <= 0:
        raise ValueError("step_v must be positive")
    span = end_v - begin_v
    if abs(span) < _EPS:
        raise ValueError("begin_v and end_v must differ")
    direction = 1.0 if span > 0 else -1.0
    whole_steps = math.floor(abs(span) / step_v + _EPS)
    voltages = [
        round(begin_v + direction * i * step_v, 6) for i in range(whole_steps + 1)
    ]
    if abs(voltages[-1] - end_v) > _EPS:
        voltages.append(round(end_v, 6))
    return voltages


def ramp_voltages(start_v: float, target_v: float, max_step_v: float) -> list[float]:
    """Return the voltages to step through from ``start_v`` to ``target_v``.

    The start itself is excluded, the target is included, and no step is
    larger than ``max_step_v``. An empty list means no change is needed.

    Raises:
        ValueError: if ``max_step_v`` is not positive.
    """
    if max_step_v <= 0:
        raise ValueError("max_step_v must be positive")
    if abs(target_v - start_v) < _EPS:
        return []
    return sweep_voltages(start_v, target_v, max_step_v)[1:]


def estimate_resonance_field_oe(
    frequency_ghz: float,
    gamma_mhz_per_oe: float,
    meff_emu_cc: float,
    orientation: Orientation,
) -> float | None:
    """Estimate the resonance field from the Kittel relation (CGS units).

    In plane: ``f = γ √(H (H + 4πMeff))``.
    Out of plane (saturated): ``f = γ (H − 4πMeff)``.

    Returns:
        The resonance field in Oe, or ``None`` when the model has no positive
        solution for these inputs.
    """
    f_over_gamma = frequency_ghz * 1000.0 / gamma_mhz_per_oe
    four_pi_m = 4.0 * math.pi * meff_emu_cc
    if orientation is Orientation.OUT_OF_PLANE:
        field = f_over_gamma + four_pi_m
    else:
        # Positive root of H^2 + 4πM·H − (f/γ)^2 = 0.
        half = four_pi_m / 2.0
        field = -half + math.sqrt(half * half + f_over_gamma * f_over_gamma)
    return field if field > 0 else None
