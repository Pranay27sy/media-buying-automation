"""Google APIs (DV360 = ``displayvideo``) publish public, machine-readable
Discovery documents for every version - no credentials needed."""
from __future__ import annotations

from ..schema import Snapshot, flatten_json_schema, version_key
from .base import Fetcher

DIRECTORY = "https://www.googleapis.com/discovery/v1/apis?name={api}"


class GoogleDiscoveryFetcher(Fetcher):
    def _directory(self) -> list[dict]:
        api = self.require("api")
        items = self.http.get_json(DIRECTORY.format(api=api)).get("items", [])
        if not items:
            # Google renamed or withdrew the API: fail loudly rather than skip quietly.
            raise RuntimeError(f"No Discovery entries for API `{api}`")
        return items

    def latest_version(self) -> str:
        items = self._directory()
        preferred = [i["version"] for i in items if i.get("preferred")]
        if preferred:
            return preferred[0]
        return max((i["version"] for i in items), key=version_key)

    def fetch(self, version: str) -> Snapshot:
        api = self.require("api")
        url = self.cfg.get("discovery_url") or next(
            (i["discoveryRestUrl"] for i in self._directory() if i["version"] == version),
            f"https://{api}.googleapis.com/$discovery/rest?version={version}",
        )
        doc = self.http.get_json(url)
        schemas = doc.get("schemas", {})
        entities = {}
        for entity in self.cfg.get("entities", []):
            if entity not in schemas:
                entities[entity] = {}
                continue
            entities[entity] = flatten_json_schema(
                {"$ref": entity},
                schemas,
                is_required=lambda _p, _n, s: (s.get("description") or "").startswith("Required."),
                is_read_only=lambda s: bool(s.get("readOnly"))
                or (s.get("description") or "").startswith("Output only."),
                max_depth=self.cfg.get("max_depth", 6),
            )
        return Snapshot(
            platform=self.platform,
            version=version,
            entities=entities,
            source=url,
            revision=doc.get("revision", ""),
        )
