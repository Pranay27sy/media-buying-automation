import json
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class FakeHttp:
    """Serves canned responses by URL substring; records requests."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls = []

    def _find(self, url):
        self.calls.append(url)
        for key, value in self.routes.items():
            if key in url:
                return value() if callable(value) else value
        raise AssertionError(f"unexpected request: {url}")

    def get_json(self, url, **kw):
        return self._find(url)

    def get_text(self, url, **kw):
        return self._find(url)

    def post_json(self, url, payload, **kw):
        return self._find(url)


@pytest.fixture
def fixture_json():
    return lambda name: json.loads((FIXTURES / name).read_text())


@pytest.fixture
def project(tmp_path):
    """A throwaway copy of the project layout with a small config."""
    (tmp_path / "config").mkdir()
    (tmp_path / "watchlists").mkdir()
    shutil.copy(FIXTURES / "platforms.yaml", tmp_path / "config" / "platforms.yaml")
    for name in ("dv360.yaml", "meta.yaml"):
        shutil.copy(FIXTURES / f"watchlist_{name}", tmp_path / "watchlists" / name)
    return tmp_path
