"""Drivers send the expected command strings (no VISA session is opened)."""

import pytest

from app.instruments.agilent83640b import Agilent83640B
from app.instruments.lakeshore425 import LakeShore425
from app.instruments.magnet import AuxOutMagnet
from app.instruments.sr830 import SR830
from app.models import LockInSettings


class FakeResource:
    def __init__(self, replies=None):
        self.writes = []
        self.replies = replies or {}

    def write(self, message):
        self.writes.append(message)

    def query(self, message):
        self.writes.append(message)
        return self.replies[message]

    def close(self):
        pass


def test_sr830_configure_never_resets():
    resource = FakeResource()
    SR830(resource).configure(LockInSettings(reference_frequency_hz=700))
    assert "*RST" not in resource.writes
    assert "FMOD 1" in resource.writes
    assert "FREQ 700.0000" in resource.writes
    assert "SLVL 0.004" in resource.writes
    assert "OFLT 8" in resource.writes
    assert "SENS 17" in resource.writes


def test_sr830_aux_and_signal():
    resource = FakeResource({"SNAP? 1,4": "1.5e-6,12.5\n", "AUXV? 1": "-0.250\n"})
    lockin = SR830(resource)
    lockin.set_aux_output(1, -2.5)
    assert resource.writes[-1] == "AUXV 1,-2.500"
    assert lockin.read_aux_output(1) == -0.25
    assert lockin.read_signal() == (1.5e-6, 12.5)


def test_sr830_rejects_out_of_range():
    lockin = SR830(FakeResource())
    with pytest.raises(ValueError):
        lockin.set_aux_output(5, 0.0)
    with pytest.raises(ValueError):
        lockin.set_aux_output(1, 11.0)
    with pytest.raises(ValueError):
        lockin.set_sine_amplitude(6.0)


def test_rf_source_commands():
    resource = FakeResource()
    rf = Agilent83640B(resource)
    rf.set_cw_frequency(10e9)
    rf.set_power(-3)
    rf.set_output(True)
    rf.set_output(False)
    assert resource.writes == [
        ":FREQ:MODE CW",
        ":FREQ:CW 10000000000 HZ",
        ":POW:LEV -3.00 DBM",
        ":POW:STAT ON",
        ":POW:STAT OFF",
    ]


def test_lakeshore_reading():
    meter = LakeShore425(FakeResource({"RDGFIELD?": "+1234.5\r\n"}))
    assert meter.read_field() == 1234.5


def test_magnet_ramp_steps_are_bounded():
    resource = FakeResource({"AUXV? 1": "0.0"})
    magnet = AuxOutMagnet(SR830(resource), 1)
    waits = []
    assert magnet.ramp_to(-0.25, 0.1, 0.05, waits.append)
    assert resource.writes[1:] == ["AUXV 1,-0.100", "AUXV 1,-0.200", "AUXV 1,-0.250"]
    assert waits == [0.05, 0.05, 0.05]
    assert magnet.voltage == -0.25
