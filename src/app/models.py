"""Pydantic models shared by the API, the run engine and the page."""

import math
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Smallest SR830 sine output amplitude (V rms); used as "modulation off".
SR830_MIN_SINE_V = 0.004
#: SR830 Aux Out range (V).
SR830_AUX_RANGE_V = 10.5

FrequencyGHz = Annotated[float, Field(gt=0, le=40, allow_inf_nan=False)]


class StrictModel(BaseModel):
    """Base model that rejects unknown fields and non-finite numbers."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Orientation(StrEnum):
    """Direction of the static field relative to the film."""

    IN_PLANE = "in_plane"
    OUT_OF_PLANE = "out_of_plane"

    @property
    def file_label(self) -> str:
        """Label used in saved file names, matching the LabVIEW VI."""
        return "In-plane" if self is Orientation.IN_PLANE else "Out-of-plane"


class CalibrationSettings(StrictModel):
    """Conversion constants between instrument values and fields.

    Defaults are the values recorded on the LabVIEW front panel; they are
    editable starting points, not constants of nature.
    """

    field_per_volt_oe: float = Field(
        996.3,
        gt=0,
        le=1e5,
        description="Magnet field per SR830 Aux Out volt (Oe/V). One Kepco "
        "supply ~996.3, two supplies ~1984.4.",
    )
    aux_output_inverted: bool = Field(
        True,
        description="True when a negative Aux Out voltage gives a positive field.",
    )
    gaussmeter_scale: float = Field(
        1.544, gt=0, le=100, description="Gaussmeter reading scale factor."
    )
    gaussmeter_offset_oe: float = Field(
        -11.956, ge=-1e4, le=1e4, description="Gaussmeter reading offset (Oe)."
    )
    modulation_oe_per_volt: float = Field(
        5.219,
        gt=0,
        le=1e4,
        description="Modulation coil field per SR830 sine volt rms (Oe/V).",
    )


class LockInSettings(StrictModel):
    """SR830 settings applied at the start of a run."""

    reference_frequency_hz: float = Field(700.0, ge=0.001, le=102000)
    sine_amplitude_v: float = Field(
        0.4,
        ge=SR830_MIN_SINE_V,
        le=5.0,
        description="Modulation drive, SR830 sine output (V rms).",
    )
    time_constant_index: int = Field(
        8, ge=0, le=19, description="SR830 OFLT index (8 = 100 ms)."
    )
    sensitivity_index: int = Field(
        17, ge=0, le=26, description="SR830 SENS index (17 = 1 mV)."
    )


class RunSettings(StrictModel):
    """Everything needed to run a set of field sweeps at fixed frequencies."""

    frequencies_ghz: list[FrequencyGHz] = Field(
        default_factory=lambda: [10.0], min_length=1, max_length=200
    )
    rf_power_dbm: float = Field(0.0, ge=-20, le=25)
    orientation: Orientation = Orientation.IN_PLANE
    angle_deg: float = Field(0.0, ge=-360, le=360)
    aux_begin_v: float = Field(-2.5, ge=-SR830_AUX_RANGE_V, le=SR830_AUX_RANGE_V)
    aux_end_v: float = Field(-3.1, ge=-SR830_AUX_RANGE_V, le=SR830_AUX_RANGE_V)
    aux_step_v: float = Field(
        0.002, ge=0.001, le=1.0, description="SR830 Aux Out resolution is 1 mV."
    )
    step_wait_ms: int = Field(200, ge=0, le=60_000)
    ramp_step_v: float = Field(0.05, ge=0.001, le=1.0)
    ramp_wait_ms: int = Field(50, ge=0, le=60_000)
    saturate_wait_ms: int = Field(2000, ge=0, le=600_000)
    zero_wait_ms: int = Field(1000, ge=0, le=600_000)
    lockin: LockInSettings = Field(default_factory=LockInSettings)
    calibration: CalibrationSettings = Field(default_factory=CalibrationSettings)
    file_prefix: str = Field("fmr", pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

    @model_validator(mode="after")
    def _check_sweep(self) -> Self:
        """Require a non-empty sweep and distinct frequencies."""
        if math.isclose(self.aux_begin_v, self.aux_end_v, abs_tol=1e-9):
            raise ValueError("aux_begin_v and aux_end_v must differ")
        if len(set(self.frequencies_ghz)) != len(self.frequencies_ghz):
            raise ValueError("frequencies_ghz must not repeat")
        return self


class Limits(StrictModel):
    """Safety limits that every run is checked against before it starts."""

    max_aux_voltage_v: float = Field(5.0, gt=0, le=SR830_AUX_RANGE_V)
    max_field_oe: float = Field(10_000, gt=0)
    max_rf_power_dbm: float = Field(20, le=25)
    max_ramp_step_v: float = Field(0.1, gt=0, le=1.0)
    max_points_per_sweep: int = Field(20_000, gt=0)


class ResonanceEstimateSettings(StrictModel):
    """Guesses used to estimate where each resonance should appear."""

    gamma_mhz_per_oe: float = Field(2.8, gt=0, le=10)
    meff_emu_cc: float = Field(140.0, ge=-5000, le=5000)


class PreviewRequest(StrictModel):
    """Run settings to preview, plus resonance-estimate guesses."""

    settings: RunSettings
    estimate: ResonanceEstimateSettings = Field(
        default_factory=ResonanceEstimateSettings
    )


class ResonanceEstimate(StrictModel):
    """Estimated resonance field for one frequency."""

    frequency_ghz: float
    resonance_field_oe: float | None
    inside_sweep: bool
    file_name: str


class Preview(StrictModel):
    """Derived values the page shows before a run starts."""

    begin_field_oe: float
    end_field_oe: float
    field_step_oe: float
    points_per_sweep: int
    modulation_rms_oe: float
    estimated_run_seconds: float
    resonances: list[ResonanceEstimate]
    limit_errors: list[str]


class Defaults(StrictModel):
    """Default settings and the active limits, for populating the page."""

    settings: RunSettings
    estimate: ResonanceEstimateSettings
    limits: Limits
    instrument_mode: Literal["simulated", "hardware"]


class RunState(StrEnum):
    """Lifecycle of a run."""

    RUNNING = "running"
    FINISHED = "finished"
    STOPPED = "stopped"
    FAILED = "failed"


class SweepState(StrEnum):
    """Outcome of one frequency sweep."""

    PENDING = "pending"
    MEASURING = "measuring"
    COMPLETE = "complete"
    SKIPPED = "skipped"
    STOPPED = "stopped"
    FAILED = "failed"


class DataPoint(StrictModel):
    """One measured point of a sweep."""

    index: int
    sweep_index: int
    aux_voltage_v: float
    field_oe: float
    signal_x_v: float
    phase_deg: float


class SweepSummary(StrictModel):
    """State of one frequency sweep within a run."""

    sweep_index: int
    frequency_ghz: float
    state: SweepState
    point_count: int
    file_name: str
    saved: bool


class RunStatus(StrictModel):
    """Run state plus the points measured after a given index."""

    run_id: str
    state: RunState
    started_at: datetime
    finished_at: datetime | None
    current_sweep_index: int | None
    sweeps: list[SweepSummary]
    points: list[DataPoint]
    next_index: int
    error: str | None
    shutdown_errors: list[str]
    settings: RunSettings


class InstrumentInfo(StrictModel):
    """Identification of one instrument."""

    role: str
    address: str
    identity: str | None
    error: str | None


class InstrumentsStatus(StrictModel):
    """Instrument mode and identification strings."""

    mode: Literal["simulated", "hardware"]
    instruments: list[InstrumentInfo]
