"""Pydantic models shared by the API, the run engine and the page."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Smallest SR830 sine output amplitude (V rms); used as "modulation off".
SR830_MIN_SINE_V = 0.004
#: Largest SR830 sine output amplitude (V rms).
SR830_MAX_SINE_V = 5.0
#: SR830 sine output resolution (V).
SR830_SINE_RESOLUTION_V = 0.002
#: SR830 Aux Out range (V).
SR830_AUX_RANGE_V = 10.5
#: SR830 Aux Out resolution (V).
SR830_AUX_RESOLUTION_V = 0.001

FrequencyGHz = Annotated[float, Field(gt=0, le=40, allow_inf_nan=False)]

#: One folder name: starts with a letter or digit, never ends with a dot.
_FOLDER_SEGMENT = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,62}[A-Za-z0-9_-])?"
#: Up to four "/"-separated folder names, or empty for the data directory.
SAVE_FOLDER_PATTERN = rf"^(?:{_FOLDER_SEGMENT}(?:/{_FOLDER_SEGMENT}){{0,3}})?$"
#: Device names Windows reserves in every folder, with or without an extension.
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


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

    reference_frequency_hz: float = Field(
        700.0, ge=0.001, le=102000, description="Modulation and detection (Hz)."
    )
    time_constant_index: int = Field(
        8, ge=0, le=19, description="SR830 OFLT index (8 = 100 ms)."
    )
    sensitivity_index: int = Field(
        17, ge=0, le=26, description="SR830 SENS index (17 = 1 mV)."
    )


class ResonanceModel(StrictModel):
    """Kittel parameters that place each sweep around its expected resonance."""

    g_factor: float = Field(2.0, gt=0, le=10, description="Spectroscopic g-factor.")
    meff_emu_cc: float = Field(
        140.0, ge=-5000, le=5000, description="Effective magnetization (emu/cc)."
    )


class RunSettings(StrictModel):
    """Everything needed to run a set of field sweeps at fixed frequencies."""

    frequencies_ghz: list[FrequencyGHz] = Field(
        default_factory=lambda: [10.0], min_length=1, max_length=200
    )
    rf_power_dbm: float = Field(0.0, ge=-20, le=25)
    orientation: Orientation = Orientation.IN_PLANE
    angle_deg: float = Field(0.0, ge=-360, le=360)
    field_range_oe: float = Field(
        600.0,
        gt=0,
        le=50_000,
        description="Width of each sweep (Oe). Each sweep runs from "
        "Hres + range/2 down to Hres - range/2, where Hres is the Kittel "
        "estimate at that frequency.",
    )
    field_step_oe: float = Field(
        2.0,
        gt=0,
        le=10_000,
        description="Field step (Oe); rounded to whole 1 mV Aux Out steps.",
    )
    resonance: ResonanceModel = Field(default_factory=ResonanceModel)
    step_wait_ms: int = Field(200, ge=0, le=60_000)
    ramp_step_v: float = Field(0.05, ge=0.001, le=1.0)
    ramp_wait_ms: int = Field(50, ge=0, le=60_000)
    saturate_wait_ms: int = Field(2000, ge=0, le=600_000)
    zero_wait_ms: int = Field(1000, ge=0, le=600_000)
    modulation_field_oe_rms: float = Field(
        2.0,
        gt=0,
        le=1000,
        description="Modulation field (Oe rms). The backend sets the SR830 sine "
        "amplitude to this divided by the coil constant.",
    )
    lockin: LockInSettings = Field(default_factory=LockInSettings)
    calibration: CalibrationSettings = Field(default_factory=CalibrationSettings)
    file_prefix: str = Field("fmr", pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
    save_folder: str = Field(
        "",
        pattern=SAVE_FOLDER_PATTERN,
        description="Folder inside the data directory for this run's files, "
        "e.g. '2026-11-11_CoFeB' or 'CoFeB/run_2'; empty saves in the data "
        "directory itself. Absolute paths, drive letters, '..' and '\\' are "
        "rejected, so files can never be written outside the repository.",
    )

    @field_validator("save_folder")
    @classmethod
    def _check_save_folder(cls, value: str) -> str:
        """Reject Windows reserved device names (CON, NUL, COM1, ...)."""
        for segment in filter(None, value.split("/")):
            if segment.split(".")[0].lower() in _WINDOWS_RESERVED:
                raise ValueError(f"'{segment}' is a reserved name on Windows")
        return value

    @model_validator(mode="after")
    def _check_sweep(self) -> Self:
        """Check the modulation, the field step and the frequencies.

        The modulation must be reachable by the SR830 sine output, the step
        at least one Aux Out mV and within the range, and frequencies distinct.
        """
        m = self.calibration.modulation_oe_per_volt
        low, high = SR830_MIN_SINE_V * m, SR830_MAX_SINE_V * m
        if not low <= self.modulation_field_oe_rms <= high:
            raise ValueError(
                f"modulation_field_oe_rms {self.modulation_field_oe_rms} Oe rms is "
                f"outside {low:.3g}-{high:.3g} Oe rms, the SR830 sine range "
                f"({SR830_MIN_SINE_V}-{SR830_MAX_SINE_V} V) at {m} Oe/V"
            )
        resolution_oe = SR830_AUX_RESOLUTION_V * self.calibration.field_per_volt_oe
        if self.field_step_oe < resolution_oe / 2:
            raise ValueError(
                f"field_step_oe {self.field_step_oe} Oe is finer than the Aux Out "
                f"resolution of 1 mV = {resolution_oe:.3g} Oe"
            )
        if self.field_step_oe > self.field_range_oe:
            raise ValueError("field_step_oe must not exceed field_range_oe")
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


class SweepPlan(StrictModel):
    """Where one frequency's sweep runs, derived from the Kittel estimate."""

    frequency_ghz: float
    resonance_field_oe: float
    begin_field_oe: float = Field(description="Nominal field at begin_v (Oe).")
    end_field_oe: float = Field(description="Nominal field at end_v (Oe).")
    begin_v: float
    end_v: float
    step_v: float
    points: int
    file_name: str


class Preview(StrictModel):
    """Derived values the page shows before a run starts."""

    sweeps: list[SweepPlan]
    field_step_oe: float = Field(description="Actual step after 1 mV rounding.")
    sine_amplitude_v: float = Field(
        description="SR830 sine drive the run will use (V rms, 2 mV steps)."
    )
    modulation_rms_oe: float = Field(
        description="Modulation field that drive gives (Oe rms)."
    )
    estimated_run_seconds: float
    limit_errors: list[str]


class Defaults(StrictModel):
    """Default settings and the active limits, for populating the page."""

    settings: RunSettings
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
