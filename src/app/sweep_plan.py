"""Place each frequency's sweep around its Kittel resonance estimate."""

from app.calibration import (
    aux_voltage_to_field_oe,
    centred_field_range,
    estimate_resonance_field_oe,
    field_to_aux_voltage,
    sweep_voltages,
)
from app.models import SR830_AUX_RESOLUTION_V, RunSettings, SweepPlan
from app.storage import sweep_file_name

_MV_DECIMALS = 3


def aux_step_v(settings: RunSettings) -> float:
    """Return the Aux Out step for ``settings.field_step_oe``, in whole mV."""
    step = abs(field_to_aux_voltage(settings.field_step_oe, settings.calibration))
    return max(round(step, _MV_DECIMALS), SR830_AUX_RESOLUTION_V)


def plan_sweeps(settings: RunSettings) -> tuple[list[SweepPlan], list[str]]:
    """Return a sweep plan per frequency, and a message for each that has none.

    Each sweep runs from ``Hres + range/2`` down to ``Hres − range/2``, where
    ``Hres`` is the Kittel estimate at that frequency. The endpoints are
    rounded to the SR830's 1 mV Aux Out resolution, and the reported fields
    are the nominal fields at those rounded voltages. Safety limits are not
    checked here; see :func:`app.measurement.check_limits`.
    """
    cal = settings.calibration
    step_v = aux_step_v(settings)
    plans: list[SweepPlan] = []
    errors: list[str] = []
    for frequency in settings.frequencies_ghz:
        centre = estimate_resonance_field_oe(
            frequency,
            settings.resonance.g_factor,
            settings.resonance.meff_emu_cc,
            settings.orientation,
        )
        if centre is None:
            errors.append(
                f"{frequency} GHz: the Kittel model has no positive resonance "
                "field for these g and Meff values"
            )
            continue
        begin_oe, end_oe = centred_field_range(centre, settings.field_range_oe)
        begin_v = round(field_to_aux_voltage(begin_oe, cal), _MV_DECIMALS)
        end_v = round(field_to_aux_voltage(end_oe, cal), _MV_DECIMALS)
        if begin_v == end_v:
            errors.append(f"{frequency} GHz: the field range is under 1 mV of Aux Out")
            continue
        plans.append(
            SweepPlan(
                frequency_ghz=frequency,
                resonance_field_oe=centre,
                begin_field_oe=aux_voltage_to_field_oe(begin_v, cal),
                end_field_oe=aux_voltage_to_field_oe(end_v, cal),
                begin_v=begin_v,
                end_v=end_v,
                step_v=step_v,
                points=len(sweep_voltages(begin_v, end_v, step_v)),
                file_name=sweep_file_name(settings, frequency),
            )
        )
    return plans, errors
