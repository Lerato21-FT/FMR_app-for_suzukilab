"""SR830 time-constant and sensitivity tables (SR830 manual, OFLT and SENS).

The lock-in takes an index for each; these tables give what the index means
so the page can label it and the backend can check the measurement timing.
"""

import math

from app.models import LockInOption

#: Each measurement point waits at least this many time constants, so the
#: lock-in output has settled after the field step.
TIME_CONSTANTS_PER_STEP = 3


def _label(value: float, unit: str) -> str:
    """Format ``value`` with an SI prefix, e.g. 0.1 s -> '100 ms'."""
    for factor, prefix in (
        (1e3, "k"),
        (1.0, ""),
        (1e-3, "m"),
        (1e-6, "µ"),
        (1e-9, "n"),
    ):
        if value >= factor * (1 - 1e-9):
            return f"{round(value / factor):g} {prefix}{unit}"
    raise ValueError(f"{value} {unit} is below the table range")


def _decades(
    mantissas: tuple[float, ...], start_exponent: int, count: int
) -> list[float]:
    """Return ``count`` values cycling through ``mantissas`` per decade."""
    return [
        mantissas[i % len(mantissas)] * 10.0 ** (start_exponent + i // len(mantissas))
        for i in range(count)
    ]


#: OFLT 0-19: 10 µs, 30 µs, 100 µs, ..., 10 ks, 30 ks.
TIME_CONSTANTS: tuple[LockInOption, ...] = tuple(
    LockInOption(index=i, value=v, label=_label(v, "s"))
    for i, v in enumerate(_decades((1.0, 3.0), -5, 20))
)

#: SENS 0-26: 2 nV, 5 nV, 10 nV, ..., 500 mV, 1 V (full scale).
SENSITIVITIES: tuple[LockInOption, ...] = tuple(
    LockInOption(index=i, value=v, label=_label(v, "V"))
    for i, v in enumerate(_decades((2.0, 5.0, 10.0), -9, 27))
)


def time_constant_s(index: int) -> float:
    """Return the SR830 time constant (s) for OFLT ``index``."""
    return TIME_CONSTANTS[index].value


def min_step_wait_ms(time_constant_index: int) -> int:
    """Shortest allowed wait per field step (ms) for this time constant.

    It is ``TIME_CONSTANTS_PER_STEP`` time constants, rounded up to whole ms.
    """
    ms = TIME_CONSTANTS_PER_STEP * time_constant_s(time_constant_index) * 1000
    return math.ceil(round(ms, 6))
