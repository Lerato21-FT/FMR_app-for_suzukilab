"""Open the real instruments through PyVISA and NI-VISA."""

from app.config import AppConfig
from app.instruments.agilent83640b import Agilent83640B
from app.instruments.base import Lab
from app.instruments.lakeshore425 import (
    SERIAL_BAUD_RATE,
    SERIAL_DATA_BITS,
    LakeShore425,
)
from app.instruments.sr830 import SR830

_TIMEOUT_MS = 2000


def open_hardware_lab(config: AppConfig) -> Lab:
    """Open VISA sessions to the SR830, 83640B and Lake Shore 425.

    PyVISA is imported here so simulated mode never loads NI-VISA.

    Raises:
        pyvisa.Error: if an instrument cannot be opened.
    """
    import pyvisa
    from pyvisa import constants

    manager = pyvisa.ResourceManager()
    opened: list[object] = []
    try:
        lockin = manager.open_resource(config.sr830_address)
        opened.append(lockin)
        rf = manager.open_resource(config.rf_source_address)
        opened.append(rf)
        meter = manager.open_resource(config.lakeshore_address)
        opened.append(meter)
        for resource in (lockin, rf, meter):
            resource.timeout = _TIMEOUT_MS
        lockin.read_termination = "\n"
        lockin.write_termination = "\n"
        rf.read_termination = "\n"
        rf.write_termination = "\n"
        meter.baud_rate = SERIAL_BAUD_RATE
        meter.data_bits = SERIAL_DATA_BITS
        meter.parity = constants.Parity.odd
        meter.stop_bits = constants.StopBits.one
        meter.read_termination = "\r\n"
        meter.write_termination = "\n"
    except Exception:
        for resource in opened:
            resource.close()  # type: ignore[attr-defined]
        manager.close()
        raise

    def close() -> None:
        for resource in (lockin, rf, meter):
            resource.close()
        manager.close()

    return Lab(
        lockin=SR830(lockin),
        field_meter=LakeShore425(meter),
        rf_source=Agilent83640B(rf),
        magnet_aux_channel=config.magnet_aux_channel,
        close=close,
    )
