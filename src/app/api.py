"""HTTP routes. Every result comes from the backend modules; this file only routes."""

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from app.config import PROJECT_ROOT, AppConfig
from app.instruments.base import Lab
from app.instruments.simulated import create_simulated_lab
from app.measurement import MeasurementRunner, RunConflictError, RunSettingsError
from app.models import (
    Defaults,
    InstrumentInfo,
    InstrumentsStatus,
    Preview,
    RunSettings,
    RunStatus,
)
from app.preview import preview_run
from app.sr830_tables import SENSITIVITIES, TIME_CONSTANTS
from app.storage import SweepStore

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


class RevalidatedStaticFiles(StaticFiles):
    """Static files the browser must revalidate on every load.

    Without ``Cache-Control: no-cache`` browsers cache files heuristically
    from ``Last-Modified`` and, after an update, keep running an old app.js
    or styles.css against a new index.html. Unchanged files still come back
    as cheap ``304 Not Modified`` responses via the ETag.
    """

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        """Serve the file with ``Cache-Control: no-cache``."""
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-cache"
        return response


def default_lab_factory(config: AppConfig) -> Callable[[], Lab]:
    """Return a factory for the lab selected by ``config.instrument_mode``."""
    if config.instrument_mode == "hardware":
        # Deferred import: simulated mode never loads the VISA layer.
        from app.instruments.hardware import open_hardware_lab

        return lambda: open_hardware_lab(config)
    return lambda: (
        create_simulated_lab(magnet_aux_channel=config.magnet_aux_channel).lab
    )


def create_app(
    config: AppConfig | None = None,
    lab_factory: Callable[[], Lab] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> FastAPI:
    """Build the FastAPI app (tests inject a config, lab and fast sleep)."""
    config = config or AppConfig.from_env()
    runner = MeasurementRunner(
        lab_factory=lab_factory or default_lab_factory(config),
        store=SweepStore(config.data_dir),
        limits=config.limits,
        sleep=sleep,
    )
    app = FastAPI(
        title="FMR acquisition",
        description="Runs lock-in detected, field-swept FMR measurements.",
        version="0.1.0",
    )
    app.state.runner = runner
    app.state.config = config

    @app.get("/api/settings/defaults")
    def get_defaults() -> Defaults:
        """Default run settings and the active safety limits."""
        data_dir = config.data_dir.resolve()
        if data_dir.is_relative_to(PROJECT_ROOT):
            data_dir = data_dir.relative_to(PROJECT_ROOT)
        return Defaults(
            settings=RunSettings(),
            limits=runner.limits,
            instrument_mode=config.instrument_mode,
            data_dir=data_dir.as_posix(),
            analysis_url=config.analysis_url,
            time_constants=list(TIME_CONSTANTS),
            sensitivities=list(SENSITIVITIES),
        )

    @app.post("/api/preview")
    def post_preview(settings: RunSettings) -> Preview:
        """Each frequency's centred sweep, the duration and any limit problems."""
        return preview_run(settings, runner.limits)

    @app.get("/api/instruments")
    def get_instruments() -> InstrumentsStatus:
        """Instrument mode, addresses and identification strings."""
        addresses = {
            "lockin": config.sr830_address,
            "field_meter": config.lakeshore_address,
            "rf_source": config.rf_source_address,
        }
        try:
            identities = runner.identify()
            error = None
        except RunConflictError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except Exception as exc:
            logger.exception("instrument identification failed")
            identities = {}
            error = f"{type(exc).__name__}: {exc}"
        return InstrumentsStatus(
            mode=config.instrument_mode,
            instruments=[
                InstrumentInfo(
                    role=role,
                    address=address,
                    identity=identities.get(role),
                    error=error,
                )
                for role, address in addresses.items()
            ],
        )

    @app.post("/api/runs", status_code=status.HTTP_201_CREATED)
    def post_run(settings: RunSettings) -> RunStatus:
        """Start a run (422 if unsafe or a file exists, 409 if one is active)."""
        try:
            return runner.start(settings)
        except RunSettingsError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors
            ) from exc
        except RunConflictError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    @app.get("/api/runs/latest")
    def get_latest_run() -> RunStatus:
        """The most recent run (404 if none has started)."""
        run_id = runner.latest_run_id()
        if run_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no run has started")
        return runner.status(run_id)

    @app.get("/api/runs/{run_id}")
    def get_run(
        run_id: str,
        since: Annotated[int, Query(ge=0, le=10_000_000)] = 0,
    ) -> RunStatus:
        """Run state plus the points measured after index ``since``."""
        try:
            return runner.status(run_id, since)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run") from exc

    @app.post("/api/runs/{run_id}/skip", status_code=status.HTTP_202_ACCEPTED)
    def post_skip(run_id: str) -> RunStatus:
        """End the current sweep and continue with the next frequency."""
        try:
            runner.skip(run_id)
            return runner.status(run_id)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run") from exc

    @app.post("/api/runs/{run_id}/stop", status_code=status.HTTP_202_ACCEPTED)
    def post_stop(run_id: str) -> RunStatus:
        """Stop the run after RF and modulation are off and the field is ramped down."""
        try:
            runner.stop(run_id)
            return runner.status(run_id)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run") from exc

    app.mount(
        "/vendor",
        RevalidatedStaticFiles(directory=WEB_DIR / "vendor", check_dir=False),
        name="vendor",
    )
    app.mount("/", RevalidatedStaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()
