"""The Run quadrant links to the analysis app, at a local address set in .env."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import (
    DEFAULT_ANALYSIS_URL,
    AppConfig,
    ConfigError,
    resolve_analysis_url,
)
from app.models import Limits

WEB_HTML = (
    Path(__file__).resolve().parents[2] / "src" / "web" / "index.html"
).read_text(encoding="utf-8")


def test_default_is_the_analysis_app_port():
    assert DEFAULT_ANALYSIS_URL == "http://127.0.0.1:8765"
    assert AppConfig.from_env({}).analysis_url == DEFAULT_ANALYSIS_URL


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8765", "http://localhost:9000/", "https://127.0.0.1:8443/app"],
)
def test_local_addresses_are_accepted(url):
    assert resolve_analysis_url(url) == url
    assert AppConfig.from_env({"FMR_ANALYSIS_URL": url}).analysis_url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:8765",
        "http://192.168.1.5:8765",
        "http://127.0.0.1.evil.com:8765",
        "http://user:pw@127.0.0.1:8765",
        "http://127.0.0.1:99999",
        "http://127.0.0.1:8765/?next=http://example.com",
        "ftp://127.0.0.1:8765",
        "javascript:alert(1)",
        "127.0.0.1:8765",
    ],
)
def test_other_addresses_are_rejected(url):
    with pytest.raises(ConfigError, match="FMR_ANALYSIS_URL"):
        AppConfig.from_env({"FMR_ANALYSIS_URL": url})


def test_defaults_endpoint_sends_the_link(tmp_path):
    config = AppConfig(
        instrument_mode="simulated",
        sr830_address="GPIB0::8::INSTR",
        rf_source_address="GPIB0::19::INSTR",
        lakeshore_address="ASRL3::INSTR",
        magnet_aux_channel=1,
        data_dir=tmp_path,
        limits=Limits(),
        analysis_url="http://localhost:9000",
    )
    with TestClient(create_app(config)) as client:
        body = client.get("/api/settings/defaults").json()
    assert body["analysis_url"] == "http://localhost:9000"


def test_run_quadrant_ends_with_a_new_tab_button():
    run_quadrant = WEB_HTML.split('id="q-run"', 1)[1].split("</section>", 1)[0]
    link = re.search(r'<a id="analysis-link"[^>]*>', run_quadrant)
    assert link, "analysis link missing from the Run quadrant"
    assert 'target="_blank"' in link.group(0)
    assert 'rel="noopener"' in link.group(0)
    # It sits at the bottom: after the preview table, last in the quadrant.
    assert run_quadrant.index("analysis-link") > run_quadrant.index("preview-table")
    assert run_quadrant.rstrip().endswith("</div>")
    assert "</a>" in run_quadrant.rstrip().rsplit("<div", 1)[1]
