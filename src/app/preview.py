"""Derived values shown before a run: fields, point count, resonances, limits."""

from app.calibration import (
    aux_voltage_to_field_oe,
    estimate_resonance_field_oe,
    modulation_rms_oe,
    ramp_voltages,
    sweep_voltages,
)
from app.measurement import check_limits
from app.models import Limits, Preview, PreviewRequest, ResonanceEstimate
from app.storage import sweep_file_name


def preview_run(request: PreviewRequest, limits: Limits) -> Preview:
    """Compute what a run with these settings would do, without running it."""
    s = request.settings
    cal = s.calibration
    voltages = sweep_voltages(s.aux_begin_v, s.aux_end_v, s.aux_step_v)
    begin = aux_voltage_to_field_oe(s.aux_begin_v, cal)
    end = aux_voltage_to_field_oe(s.aux_end_v, cal)
    low, high = sorted((begin, end))

    ramp_steps = len(ramp_voltages(0.0, s.aux_begin_v, s.ramp_step_v)) + len(
        ramp_voltages(s.aux_end_v, 0.0, s.ramp_step_v)
    )
    per_sweep_s = (
        len(voltages) * s.step_wait_ms
        + ramp_steps * s.ramp_wait_ms
        + s.saturate_wait_ms
        + s.zero_wait_ms
    ) / 1000

    resonances = []
    for frequency in s.frequencies_ghz:
        field = estimate_resonance_field_oe(
            frequency,
            request.estimate.gamma_mhz_per_oe,
            request.estimate.meff_emu_cc,
            s.orientation,
        )
        resonances.append(
            ResonanceEstimate(
                frequency_ghz=frequency,
                resonance_field_oe=field,
                inside_sweep=field is not None
                and (low <= field <= high or low <= -field <= high),
                file_name=sweep_file_name(s, frequency),
            )
        )

    return Preview(
        begin_field_oe=begin,
        end_field_oe=end,
        field_step_oe=abs(aux_voltage_to_field_oe(s.aux_step_v, cal)),
        points_per_sweep=len(voltages),
        modulation_rms_oe=modulation_rms_oe(s.lockin.sine_amplitude_v, cal),
        estimated_run_seconds=per_sweep_s * len(s.frequencies_ghz),
        resonances=resonances,
        limit_errors=check_limits(s, limits),
    )
