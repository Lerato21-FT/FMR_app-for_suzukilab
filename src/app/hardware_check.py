"""Identify the real instruments without changing any output.

Run only through ``make hardware-check``. It opens the VISA sessions, sends
identification queries, prints the replies and closes the sessions. It sends
no command that changes a field, RF or modulation output.
"""

import sys

from app.config import AppConfig
from app.instruments.hardware import open_hardware_lab


def main() -> int:
    """Print each instrument's identity; return a non-zero exit code on failure."""
    config = AppConfig.from_env()
    lab = open_hardware_lab(config)
    failures = 0
    try:
        for role, instrument, address in (
            ("SR830 lock-in", lab.lockin, config.sr830_address),
            ("Lake Shore 425", lab.field_meter, config.lakeshore_address),
            ("83640B RF source", lab.rf_source, config.rf_source_address),
        ):
            try:
                print(f"{role:18} {address:20} {instrument.identify()}")
            except Exception as exc:
                failures += 1
                print(f"{role:18} {address:20} FAILED: {type(exc).__name__}: {exc}")
    finally:
        lab.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
