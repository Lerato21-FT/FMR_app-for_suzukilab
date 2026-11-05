"""Agilent 83640B synthesized sweeper driver (CW use only)."""

from app.instruments.base import VisaResource


class Agilent83640B:
    """Agilent 83640B over GPIB, using the SCPI strings from the LabVIEW VI."""

    def __init__(self, resource: VisaResource) -> None:
        """Wrap an open VISA resource."""
        self._resource = resource

    def identify(self) -> str:
        """Return the ``*IDN?`` string."""
        return self._resource.query("*IDN?").strip()

    def set_cw_frequency(self, hertz: float) -> None:
        """Select CW mode and set the output frequency.

        Raises:
            ValueError: if the frequency is not positive.
        """
        if hertz <= 0:
            raise ValueError("frequency must be positive")
        self._resource.write(":FREQ:MODE CW")
        self._resource.write(f":FREQ:CW {hertz:.0f} HZ")

    def set_power(self, dbm: float) -> None:
        """Set the output level in dBm."""
        self._resource.write(f":POW:LEV {dbm:.2f} DBM")

    def set_output(self, enabled: bool) -> None:
        """Turn the RF output on or off."""
        self._resource.write(":POW:STAT ON" if enabled else ":POW:STAT OFF")
