"""Lake Shore 425 gaussmeter driver."""

from app.instruments.base import VisaResource

#: Serial settings of the Lake Shore 425 USB/serial interface.
SERIAL_BAUD_RATE = 57600
SERIAL_DATA_BITS = 7


class LakeShore425:
    """Lake Shore 425 over its serial (virtual COM) interface."""

    def __init__(self, resource: VisaResource) -> None:
        """Wrap an open VISA resource."""
        self._resource = resource

    def identify(self) -> str:
        """Return the ``*IDN?`` string."""
        return self._resource.query("*IDN?").strip()

    def read_field(self) -> float:
        """Return one uncorrected field reading in the meter's units."""
        return float(self._resource.query("RDGFIELD?"))
