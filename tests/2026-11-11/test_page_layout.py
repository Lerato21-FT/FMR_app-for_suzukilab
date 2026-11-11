"""Static checks of the four-quadrant page (no browser; Playwright is task 5)."""

import re
from html.parser import HTMLParser
from pathlib import Path

from pydantic import BaseModel

from app.models import RunSettings

WEB = Path(__file__).resolve().parents[2] / "src" / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
JS = (WEB / "app.js").read_text(encoding="utf-8")


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.names: set[str] = set()
        self.tabs: list[str] = []
        self._in_tab = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag in ("input", "select", "textarea") and a.get("name"):
            self.names.add(a["name"])
        self._in_tab = a.get("role") == "tab"

    def handle_data(self, data):
        if self._in_tab and data.strip():
            self.tabs.append(data.strip())
            self._in_tab = False


PAGE = _Collector()
PAGE.feed(HTML)


def _leaf_fields(model, prefix=""):
    for name in type(model).model_fields:
        value = getattr(model, name)
        if isinstance(value, BaseModel):
            yield from _leaf_fields(value, f"{prefix}{name}.")
        else:
            yield f"{prefix}{name}"


def test_four_quadrants_exist():
    for quadrant in ("q-plots", "q-instruments", "q-list", "q-run"):
        assert quadrant in PAGE.ids


def test_instrument_tabs_follow_the_labview_panel():
    assert PAGE.tabs == ["H field setup", "A83640B", "SR830", "Stepper Motor"]


def test_every_element_the_script_uses_exists():
    used = set(re.findall(r'getElementById\("([^"]+)"\)', JS))
    used |= set(re.findall(r'querySelector\("#([\w-]+)', JS))
    used |= set(re.findall(r'Plotly\.react\("([^"]+)"', JS))
    assert used, "no element lookups found"
    assert used <= PAGE.ids, f"missing in index.html: {sorted(used - PAGE.ids)}"


def test_every_run_setting_has_an_input():
    assert set(_leaf_fields(RunSettings())) == PAGE.names
