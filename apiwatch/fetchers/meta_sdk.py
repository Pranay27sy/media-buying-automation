"""Meta Marketing API - no credentials needed.

Meta generates its official SDKs from a public, machine-readable description of
the Marketing API (github.com/facebook/facebook-business-sdk-codegen). We read:

* the newest API version from the official Python SDK's ``apiconfig.py``;
* the "create" forms - e.g. ``POST /act_<id>/campaigns`` - from ``AdAccount.json``,
  which lists every parameter with its type and whether it is mandatory.

Only the newest version is published there, so older versions come from the
snapshots we saved in previous weeks.
"""
from __future__ import annotations

import re

from ..schema import FieldSpec, Snapshot
from .base import Fetcher

SDK_CONFIG = "https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/apiconfig.py"
SPECS = "https://raw.githubusercontent.com/facebook/facebook-business-sdk-codegen/main/api_specs/specs"


class MetaSDKFetcher(Fetcher):
    historical_versions = False

    def latest_version(self) -> str:
        text = self.http.get_text(self.cfg.get("sdk_config_url", SDK_CONFIG))
        m = re.search(r"['\"]API_VERSION['\"]\s*:\s*['\"](v\d+\.\d+)['\"]", text)
        if not m:
            # The file changed shape on Meta's side: fail loudly rather than skip quietly.
            raise RuntimeError("Could not read the API version from Meta's SDK config")
        return m.group(1)

    def fetch(self, version: str) -> Snapshot:
        base = self.cfg.get("specs_url", SPECS).rstrip("/")
        cache: dict[str, dict] = {}
        entities = {}
        for entity, where in (self.cfg.get("entities") or {}).items():
            # "AdAccount:campaigns" = the params of POST /act_<id>/campaigns
            parent, _, endpoint = where.partition(":")
            if parent not in cache:
                cache[parent] = self.http.get_json(f"{base}/{parent}.json")
            api = next(
                (a for a in cache[parent].get("apis", [])
                 if a.get("method") == "POST" and a.get("endpoint") == endpoint),
                None,
            )
            entities[entity] = {
                p["name"]: FieldSpec(type=p.get("type") or "unknown", required=bool(p.get("required")))
                for p in (api or {}).get("params", [])
            }
        return Snapshot(platform=self.platform, version=version, entities=entities, source=base)
