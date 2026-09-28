"""Fallback for APIs without machine-readable docs (The Trade Desk v3 by default):
GET one real object per entity and infer its field list from the response.

Removed / added / renamed fields are caught; enum and required-ness are not.
Point the ``ttd`` platform at an OpenAPI spec instead if you have one.
"""
from __future__ import annotations

from ..schema import Snapshot, infer_fields
from .base import Fetcher, SkipPlatform


class TTDSampleFetcher(Fetcher):
    historical_versions = False

    def latest_version(self) -> str:
        return self.cfg.get("version", "v3")

    def _token(self) -> str:
        if self.cfg.get("auth_token"):
            return self.cfg["auth_token"]
        login, password = self.cfg.get("login"), self.cfg.get("password")
        if not (login and password):
            raise SkipPlatform("Set TTD_AUTH_TOKEN, or TTD_LOGIN and TTD_PASSWORD")
        resp = self.http.post_json(
            f"{self.cfg['base_url'].rstrip('/')}/authentication",
            {"Login": login, "Password": password, "TokenExpirationInMinutes": 60},
        )
        return resp["Token"]

    def fetch(self, version: str) -> Snapshot:
        base = self.require("base_url").rstrip("/")
        headers = {"TTD-Auth": self._token()}
        entities = {}
        for entity, spec in (self.cfg.get("entities") or {}).items():
            if not spec or not spec.get("id"):
                raise SkipPlatform(f"No sample object id configured for TTD entity `{entity}`")
            data = self.http.get_json(f"{base}/{spec['path'].strip('/')}/{spec['id']}", headers=headers)
            entities[entity] = infer_fields(data)
        return Snapshot(platform=self.platform, version=version, entities=entities, source=base)
