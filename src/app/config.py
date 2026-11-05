"""App configuration read from environment variables (loaded from ``.env``)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.models import Limits

#: Repository root: ``src/app/config.py`` -> two levels up from ``src``.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

InstrumentMode = Literal["simulated", "hardware"]


class ConfigError(ValueError):
    """Raised when an environment setting is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    """Validated settings for one app process."""

    instrument_mode: InstrumentMode
    sr830_address: str
    rf_source_address: str
    lakeshore_address: str
    magnet_aux_channel: int
    data_dir: Path
    limits: Limits

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, root: Path = PROJECT_ROOT
    ) -> AppConfig:
        """Build the configuration from ``env`` (default: ``os.environ``).

        Raises:
            ConfigError: if a value is invalid or the data directory would be
                outside the repository.
        """
        env = os.environ if env is None else env
        mode = env.get("FMR_INSTRUMENTS", "simulated").strip().lower()
        if mode not in ("simulated", "hardware"):
            raise ConfigError("FMR_INSTRUMENTS must be 'simulated' or 'hardware'")
        channel = _int(env, "FMR_MAGNET_AUX_CHANNEL", 1)
        if channel not in (1, 2, 3, 4):
            raise ConfigError("FMR_MAGNET_AUX_CHANNEL must be 1, 2, 3 or 4")
        try:
            limits = Limits(
                max_aux_voltage_v=_float(env, "FMR_MAX_AUX_VOLTAGE_V", 5.0),
                max_field_oe=_float(env, "FMR_MAX_FIELD_OE", 10_000),
                max_rf_power_dbm=_float(env, "FMR_MAX_RF_POWER_DBM", 20),
                max_ramp_step_v=_float(env, "FMR_MAX_RAMP_STEP_V", 0.1),
                max_points_per_sweep=_int(env, "FMR_MAX_POINTS_PER_SWEEP", 20_000),
            )
        except ValueError as exc:
            raise ConfigError(f"invalid safety limit: {exc}") from exc
        return cls(
            instrument_mode=mode,  # type: ignore[arg-type]
            sr830_address=env.get("FMR_SR830_ADDRESS", "GPIB0::8::INSTR"),
            rf_source_address=env.get("FMR_RF_SOURCE_ADDRESS", "GPIB0::19::INSTR"),
            lakeshore_address=env.get("FMR_LAKESHORE_ADDRESS", "ASRL3::INSTR"),
            magnet_aux_channel=channel,
            data_dir=resolve_data_dir(
                env.get("FMR_DATA_DIR", "data/measurements"), root
            ),
            limits=limits,
        )


def resolve_data_dir(value: str, root: Path = PROJECT_ROOT) -> Path:
    """Resolve ``value`` against ``root`` and require it to stay inside ``root``.

    Raises:
        ConfigError: if the resolved path is outside the repository.
    """
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ConfigError("FMR_DATA_DIR must be inside the repository")
    return path


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
