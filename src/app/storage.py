"""Save sweeps as tab-delimited files compatible with the LabVIEW VI output."""

from collections.abc import Sequence
from pathlib import Path

from app.calibration import modulation_rms_oe, sine_amplitude_for_modulation
from app.models import DataPoint, RunSettings


class FileExistsConflictError(FileExistsError):
    """Raised when a sweep file name is already taken."""


def _format_mhz(frequency_ghz: float) -> str:
    mhz = round(frequency_ghz * 1000.0, 3)
    if mhz == int(mhz):
        return str(int(mhz))
    return f"{mhz:.3f}".rstrip("0").rstrip(".")


def sweep_file_name(settings: RunSettings, frequency_ghz: float) -> str:
    """Return the LabVIEW-style file name for one sweep.

    Example: ``fmr-10000MHz-In-plane-000.0deg-+0dBm2.0OeRMS-.csv``. The
    modulation is the field the computed sine amplitude actually gives.
    """
    cal = settings.calibration
    hmod = modulation_rms_oe(
        sine_amplitude_for_modulation(settings.modulation_field_oe_rms, cal), cal
    )
    return (
        f"{settings.file_prefix}-{_format_mhz(frequency_ghz)}MHz-"
        f"{settings.orientation.file_label}-{settings.angle_deg:05.1f}deg-"
        f"{settings.rf_power_dbm:+.0f}dBm{hmod:.1f}OeRMS-.csv"
    )


def sweep_relative_path(settings: RunSettings, frequency_ghz: float) -> str:
    """Return the sweep file's path relative to the data directory.

    The file goes in ``settings.save_folder`` (validated by ``RunSettings``),
    e.g. ``CoFeB/run_2/fmr-10000MHz-...csv``; an empty folder gives the bare
    file name.
    """
    name = sweep_file_name(settings, frequency_ghz)
    return f"{settings.save_folder}/{name}" if settings.save_folder else name


class SweepStore:
    """Writes sweep files under one directory, never overwriting.

    File names may include sub-folders (``folder/name.csv``); any path that
    would resolve outside the directory is refused.
    """

    def __init__(self, directory: Path) -> None:
        """Use ``directory`` (created on first write)."""
        self.directory = directory

    def _path(self, name: str) -> Path:
        """Return where ``name`` lives, refusing anything outside the directory."""
        base = self.directory.resolve()
        path = (base / name).resolve()
        if not path.is_relative_to(base) or path == base:
            raise ValueError(f"{name!r} is outside the data directory")
        return path

    def existing(self, names: Sequence[str]) -> list[str]:
        """Return which of ``names`` already exist."""
        return [name for name in names if self._path(name).exists()]

    def write(self, name: str, points: Sequence[DataPoint]) -> Path:
        """Write ``points`` as rows of field (Oe), X (V) and phase (deg).

        Raises:
            ValueError: if ``name`` resolves outside the directory.
            FileExistsConflictError: if the file already exists.
        """
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="ascii", newline="\n") as handle:
                for point in points:
                    handle.write(
                        f"{point.field_oe:.6e}\t{point.signal_x_v:.6e}\t"
                        f"{point.phase_deg:.6e}\n"
                    )
        except FileExistsError as exc:
            raise FileExistsConflictError(f"{name} already exists") from exc
        return path
