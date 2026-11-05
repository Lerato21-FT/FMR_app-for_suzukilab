"""Typed interfaces that real and simulated instruments implement."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.models import LockInSettings


class VisaResource(Protocol):
    """The subset of a PyVISA message-based resource the drivers use."""

    def write(self, message: str) -> object:
        """Send one command."""
        ...

    def query(self, message: str) -> str:
        """Send one command and return the instrument's reply."""
        ...

    def close(self) -> None:
        """Release the VISA session."""
        ...


class LockIn(Protocol):
    """Lock-in amplifier with a sine output and auxiliary outputs."""

    def identify(self) -> str:
        """Return the identification string."""
        ...

    def configure(self, settings: LockInSettings) -> None:
        """Apply reference, filter and sensitivity settings (modulation off)."""
        ...

    def set_sine_amplitude(self, volts_rms: float) -> None:
        """Set the sine output (modulation drive) amplitude."""
        ...

    def set_aux_output(self, channel: int, volts: float) -> None:
        """Set an auxiliary output voltage."""
        ...

    def read_aux_output(self, channel: int) -> float:
        """Return the current auxiliary output voltage."""
        ...

    def read_signal(self) -> tuple[float, float]:
        """Return ``(X in V, theta in degrees)``."""
        ...


class FieldMeter(Protocol):
    """Gaussmeter returning uncorrected field readings."""

    def identify(self) -> str:
        """Return the identification string."""
        ...

    def read_field(self) -> float:
        """Return one raw field reading."""
        ...


class RFSource(Protocol):
    """Microwave source used in CW mode."""

    def identify(self) -> str:
        """Return the identification string."""
        ...

    def set_cw_frequency(self, hertz: float) -> None:
        """Set the CW output frequency."""
        ...

    def set_power(self, dbm: float) -> None:
        """Set the output power level."""
        ...

    def set_output(self, enabled: bool) -> None:
        """Turn the RF output on or off."""
        ...


@dataclass
class Lab:
    """The set of instruments one run uses."""

    lockin: LockIn
    field_meter: FieldMeter
    rf_source: RFSource
    magnet_aux_channel: int
    close: Callable[[], None]
