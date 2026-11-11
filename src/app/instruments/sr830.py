"""Stanford Research SR830 lock-in amplifier driver."""

from app.instruments.base import VisaResource
from app.models import (
    SR830_AUX_RANGE_V,
    SR830_MAX_SINE_V,
    SR830_MIN_SINE_V,
    LockInSettings,
)


class SR830:
    """SR830 over GPIB.

    ``*RST`` is deliberately never sent: it zeroes the Aux outputs, which
    would step the magnet field abruptly instead of ramping it.
    """

    def __init__(self, resource: VisaResource) -> None:
        """Wrap an open VISA resource."""
        self._resource = resource

    def identify(self) -> str:
        """Return the ``*IDN?`` string."""
        return self._resource.query("*IDN?").strip()

    def configure(self, settings: LockInSettings) -> None:
        """Set internal reference, filters and sensitivity, modulation off."""
        self._resource.write("OUTX 1")  # replies over GPIB
        self._resource.write("FMOD 1")  # internal reference
        self._resource.write(f"FREQ {settings.reference_frequency_hz:.4f}")
        self._resource.write("HARM 1")
        self._resource.write(f"SLVL {SR830_MIN_SINE_V:.3f}")
        self._resource.write(f"OFLT {settings.time_constant_index:d}")
        self._resource.write("OFSL 1")  # 12 dB/oct, as in the VI
        self._resource.write(f"SENS {settings.sensitivity_index:d}")

    def set_sine_amplitude(self, volts_rms: float) -> None:
        """Set the sine output amplitude (0.004-5 V rms).

        Raises:
            ValueError: if the amplitude is out of range.
        """
        if not SR830_MIN_SINE_V <= volts_rms <= SR830_MAX_SINE_V:
            raise ValueError("sine amplitude must be between 0.004 and 5 V")
        self._resource.write(f"SLVL {volts_rms:.3f}")

    def set_aux_output(self, channel: int, volts: float) -> None:
        """Set Aux Out ``channel`` (1-4) to ``volts`` (+/-10.5 V, 1 mV steps).

        Raises:
            ValueError: if the channel or voltage is out of range.
        """
        _check_channel(channel)
        if abs(volts) > SR830_AUX_RANGE_V:
            raise ValueError("aux output must be within +/-10.5 V")
        self._resource.write(f"AUXV {channel:d},{volts:.3f}")

    def read_aux_output(self, channel: int) -> float:
        """Return the voltage currently set on Aux Out ``channel``."""
        _check_channel(channel)
        return float(self._resource.query(f"AUXV? {channel:d}"))

    def read_signal(self) -> tuple[float, float]:
        """Return X (V) and theta (deg), sampled together with ``SNAP?``.

        Raises:
            ValueError: if the reply cannot be parsed.
        """
        reply = self._resource.query("SNAP? 1,4").strip()
        parts = reply.split(",")
        if len(parts) != 2:
            raise ValueError(f"unexpected SNAP? reply: {reply!r}")
        return float(parts[0]), float(parts[1])


def _check_channel(channel: int) -> None:
    if channel not in (1, 2, 3, 4):
        raise ValueError("aux channel must be 1, 2, 3 or 4")
