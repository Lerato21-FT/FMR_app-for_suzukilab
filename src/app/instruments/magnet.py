"""Electromagnet driven by a Kepco supply programmed from an SR830 Aux Out."""

from collections.abc import Callable

from app.calibration import ramp_voltages
from app.instruments.base import LockIn


class AuxOutMagnet:
    """Tracks and changes the Aux Out voltage that programs the Kepco supply."""

    def __init__(self, lockin: LockIn, channel: int) -> None:
        """Read the present Aux Out voltage so ramps start from it."""
        self._lockin = lockin
        self._channel = channel
        self._voltage = lockin.read_aux_output(channel)

    @property
    def voltage(self) -> float:
        """The Aux Out voltage last set (or read at start)."""
        return self._voltage

    def set_voltage(self, volts: float) -> None:
        """Set the Aux Out voltage in one step."""
        self._lockin.set_aux_output(self._channel, volts)
        self._voltage = volts

    def ramp_to(
        self,
        target_v: float,
        max_step_v: float,
        wait_s: float,
        sleep: Callable[[float], None],
        should_abort: Callable[[], bool] = lambda: False,
    ) -> bool:
        """Ramp to ``target_v`` in steps of at most ``max_step_v``.

        Returns:
            True if the target was reached, False if ``should_abort`` stopped
            the ramp early.
        """
        for volts in ramp_voltages(self._voltage, target_v, max_step_v):
            if should_abort():
                return False
            self.set_voltage(volts)
            sleep(wait_s)
        return True
