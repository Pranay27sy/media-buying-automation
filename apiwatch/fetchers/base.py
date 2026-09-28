from __future__ import annotations

import requests

from ..schema import Snapshot


class SkipPlatform(Exception):
    """Raised when a platform can't be checked (e.g. credentials not configured)."""


class Http:
    """Thin wrapper so tests can inject canned responses."""

    def __init__(self, session: requests.Session | None = None, timeout: int = 60):
        self.session = session or requests.Session()
        self.timeout = timeout

    def get_json(self, url: str, **kw):
        r = self.session.get(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r.json()

    def get_text(self, url: str, **kw) -> str:
        r = self.session.get(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r.text

    def post_json(self, url: str, payload: dict, **kw):
        r = self.session.post(url, json=payload, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r.json()


class Fetcher:
    """One per platform. ``latest_version`` finds the newest released API version;
    ``fetch`` returns the normalized schema of the configured entities at a version."""

    #: False when only the newest version can be fetched (older ones come from saved snapshots).
    historical_versions = True

    def __init__(self, platform: str, cfg: dict, http: Http):
        self.platform = platform
        self.cfg = cfg
        self.http = http

    def require(self, key: str) -> str:
        value = self.cfg.get(key)
        if not value:
            raise SkipPlatform(f"`{key}` is not configured (see config/platforms.yaml)")
        return value

    def latest_version(self) -> str:
        raise NotImplementedError

    def fetch(self, version: str) -> Snapshot:
        raise NotImplementedError
