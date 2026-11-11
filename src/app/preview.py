"""Derived values shown before a run: per-frequency sweeps, time, limits."""

from app.calibration import (
    aux_voltage_to_field_oe,
    modulation_rms_oe,
    ramp_voltages,
    sine_amplitude_for_modulation,
)
from app.measurement import check_limits
from app.models import Limits, Preview, RunSettings
from app.sr830_tables import min_step_wait_ms
from app.sweep_plan import aux_step_v, plan_sweeps


def preview_run(settings: RunSettings, limits: Limits) -> Preview:
    """Compute what a run with these settings would do, without running it."""
    s = settings
    cal = s.calibration
    plans, _ = plan_sweeps(s)  # check_limits reports the plan errors too
    sine_v = sine_amplitude_for_modulation(s.modulation_field_oe_rms, cal)
    total_ms = 0
    for plan in plans:
        ramp_steps = len(ramp_voltages(0.0, plan.begin_v, s.ramp_step_v)) + len(
            ramp_voltages(plan.end_v, 0.0, s.ramp_step_v)
        )
        total_ms += (
            plan.points * s.step_wait_ms
            + ramp_steps * s.ramp_wait_ms
            + s.saturate_wait_ms
            + s.zero_wait_ms
        )
    return Preview(
        sweeps=plans,
        field_step_oe=abs(aux_voltage_to_field_oe(aux_step_v(s), cal)),
        sine_amplitude_v=sine_v,
        modulation_rms_oe=modulation_rms_oe(sine_v, cal),
        estimated_run_seconds=total_ms / 1000,
        min_step_wait_ms=min_step_wait_ms(s.lockin.time_constant_index),
        limit_errors=check_limits(s, limits),
    )
