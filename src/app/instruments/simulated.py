"""Simulated instruments that produce a synthetic field-modulated FMR line.

They share one state object, so the lock-in signal responds to the Aux Out
voltage (through the magnet calibration), the RF source and the modulation
amplitude just as the real setup does. Used by tests, ``make verify`` and
``FMR_INSTRUMENTS=simulated``; they never open a VISA session.
"""

import math
import random
from dataclasses import dataclass, field

from app.calibration import (
    aux_voltage_to_field_oe,
    estimate_resonance_field_oe,
    modulation_rms_oe,
    raw_reading_for_field,
)
from app.instruments.base import Lab
from app.models import (
    SR830_MIN_SINE_V,
    CalibrationSettings,
    LockInSettings,
    Orientation,
)


@dataclass
class SimulatedSample:
    """Magnetic sample parameters for the synthetic resonance."""

    gamma_mhz_per_oe: float = 2.8
    meff_emu_cc: float = 140.0
    orientation: Orientation = Orientation.IN_PLANE
    linewidth_hwhm_oe: float = 15.0
    signal_v_per_oe_rms: float = 2e-5
    noise_v: float = 2e-8
    phase_deg: float = 12.0


@dataclass
class _State:
    calibration: CalibrationSettings
    sample: SimulatedSample
    rng: random.Random
    aux_v: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    sine_v: float = SR830_MIN_SINE_V
    rf_hz: float = 0.0
    rf_dbm: float = 0.0
    rf_on: bool = False
    magnet_channel: int = 1

    def field_oe(self) -> float:
        return aux_voltage_to_field_oe(
            self.aux_v[self.magnet_channel - 1], self.calibration
        )


class SimulatedLockIn:
    """Simulated SR830."""

    def __init__(self, state: _State) -> None:
        """Attach to the shared simulated state."""
        self._state = state

    def identify(self) -> str:
        """Return a simulated identification string."""
        return "Simulated,SR830,0,1.0"

    def configure(self, settings: LockInSettings) -> None:
        """Accept settings and turn the modulation off."""
        del settings
        self._state.sine_v = SR830_MIN_SINE_V

    def set_sine_amplitude(self, volts_rms: float) -> None:
        """Set the simulated modulation drive."""
        self._state.sine_v = volts_rms

    def set_aux_output(self, channel: int, volts: float) -> None:
        """Set a simulated Aux Out."""
        self._state.aux_v[channel - 1] = volts

    def read_aux_output(self, channel: int) -> float:
        """Return a simulated Aux Out."""
        return self._state.aux_v[channel - 1]

    def read_signal(self) -> tuple[float, float]:
        """Return a derivative-Lorentzian X signal plus noise, and the phase."""
        state = self._state
        sample = state.sample
        rng = state.rng
        noise = rng.gauss(0.0, sample.noise_v)
        phase = sample.phase_deg + rng.gauss(0.0, 0.1)
        if not state.rf_on or state.sine_v <= SR830_MIN_SINE_V:
            return noise, phase
        resonance = estimate_resonance_field_oe(
            state.rf_hz / 1e9,
            sample.gamma_mhz_per_oe,
            sample.meff_emu_cc,
            sample.orientation,
        )
        if resonance is None:
            return noise, phase
        field_oe = state.field_oe()
        u = (abs(field_oe) - resonance) / sample.linewidth_hwhm_oe
        amplitude = sample.signal_v_per_oe_rms * modulation_rms_oe(
            state.sine_v, state.calibration
        )
        derivative = -2.0 * u / (1.0 + u * u) ** 2
        return math.copysign(1.0, field_oe) * amplitude * derivative + noise, phase


class SimulatedFieldMeter:
    """Simulated Lake Shore 425 returning uncorrected readings."""

    def __init__(self, state: _State) -> None:
        """Attach to the shared simulated state."""
        self._state = state

    def identify(self) -> str:
        """Return a simulated identification string."""
        return "Simulated,MODEL425,0,1.0"

    def read_field(self) -> float:
        """Return the raw reading that the calibration maps to the true field."""
        state = self._state
        true_field = state.field_oe() + state.rng.gauss(0.0, 0.05)
        return raw_reading_for_field(true_field, state.calibration)


class SimulatedRFSource:
    """Simulated Agilent 83640B."""

    def __init__(self, state: _State) -> None:
        """Attach to the shared simulated state."""
        self._state = state

    def identify(self) -> str:
        """Return a simulated identification string."""
        return "Simulated,83640B,0,1.0"

    def set_cw_frequency(self, hertz: float) -> None:
        """Set the simulated frequency."""
        self._state.rf_hz = hertz

    def set_power(self, dbm: float) -> None:
        """Set the simulated power."""
        self._state.rf_dbm = dbm

    def set_output(self, enabled: bool) -> None:
        """Turn the simulated RF on or off."""
        self._state.rf_on = enabled


@dataclass
class SimulatedLab:
    """A simulated lab plus direct access to its state for tests."""

    lab: Lab
    state: _State


def create_simulated_lab(
    calibration: CalibrationSettings | None = None,
    sample: SimulatedSample | None = None,
    magnet_aux_channel: int = 1,
    seed: int = 1,
) -> SimulatedLab:
    """Build simulated instruments sharing one state."""
    state = _State(
        calibration=calibration or CalibrationSettings(),
        sample=sample or SimulatedSample(),
        rng=random.Random(seed),  # noqa: S311 - simulation noise, not security
        magnet_channel=magnet_aux_channel,
    )
    lab = Lab(
        lockin=SimulatedLockIn(state),
        field_meter=SimulatedFieldMeter(state),
        rf_source=SimulatedRFSource(state),
        magnet_aux_channel=magnet_aux_channel,
        close=lambda: None,
    )
    return SimulatedLab(lab=lab, state=state)
