"""Normalized, platform-independent representation of an API's entity schemas.

Every platform's docs format (Google Discovery, OpenAPI, Meta ?metadata=1, a
sample JSON response) is flattened into the same shape:

    entities -> { "Campaign": { "campaignGoal.campaignGoalType": FieldSpec, ... } }

Nested objects use dotted paths; array items use ``[]`` (``campaignBudgets[].budgetId``).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

_INDEX = re.compile(r"\[\d+\]")


def normalize_path(path: str) -> str:
    """``campaignBudgets[0].budgetId`` -> ``campaignBudgets[].budgetId``."""
    return _INDEX.sub("[]", path)


def version_key(version: str) -> tuple:
    """Sortable key for ``v4``, ``v23.0``, ``v1beta`` style versions."""
    nums = [int(n) for n in re.findall(r"\d+", version)]
    return (tuple(nums), "beta" not in version and "alpha" not in version)


@dataclass
class FieldSpec:
    type: str = "unknown"
    required: bool = False
    read_only: bool = False
    deprecated: bool = False
    enum: list[str] | None = None
    enum_deprecated: list[str] | None = None

    def to_json(self) -> dict:
        # Only non-default values, to keep snapshot files small and diffs readable.
        default = FieldSpec()
        return {k: v for k, v in asdict(self).items() if v != getattr(default, k)}

    @classmethod
    def from_json(cls, data: dict) -> "FieldSpec":
        return cls(**data)


@dataclass
class Snapshot:
    platform: str
    version: str
    entities: dict[str, dict[str, FieldSpec]] = field(default_factory=dict)
    source: str = ""
    revision: str = ""

    def to_json(self) -> dict:
        return {
            "platform": self.platform,
            "version": self.version,
            "revision": self.revision,
            "source": self.source,
            "entities": {
                name: {path: spec.to_json() for path, spec in sorted(fields.items())}
                for name, fields in sorted(self.entities.items())
            },
        }

    @classmethod
    def from_json(cls, data: dict) -> "Snapshot":
        return cls(
            platform=data["platform"],
            version=data["version"],
            revision=data.get("revision", ""),
            source=data.get("source", ""),
            entities={
                name: {p: FieldSpec.from_json(s) for p, s in fields.items()}
                for name, fields in data.get("entities", {}).items()
            },
        )

    def same_schema(self, other: "Snapshot | None") -> bool:
        return other is not None and self.to_json()["entities"] == other.to_json()["entities"]


class SnapshotStore:
    """Snapshots live in ``snapshots/<platform>/<version>.json`` and are committed,
    so git history doubles as the change log of every API."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, platform: str, version: str) -> Path:
        return self.root / platform / f"{version}.json"

    def load(self, platform: str, version: str) -> Snapshot | None:
        p = self.path(platform, version)
        if not p.exists():
            return None
        return Snapshot.from_json(json.loads(p.read_text()))

    def save(self, snap: Snapshot) -> Path:
        p = self.path(snap.platform, snap.version)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snap.to_json(), indent=2, sort_keys=False) + "\n")
        return p

    def versions(self, platform: str) -> list[str]:
        d = self.root / platform
        if not d.is_dir():
            return []
        return sorted((p.stem for p in d.glob("*.json")), key=version_key)


# --------------------------------------------------------------------------- #
# JSON-schema flattening, shared by the Google Discovery and OpenAPI fetchers. #
# --------------------------------------------------------------------------- #

def flatten_json_schema(
    root: dict,
    schemas: dict[str, dict],
    *,
    is_required: Callable[[dict, str, dict], bool],
    is_read_only: Callable[[dict], bool],
    max_depth: int = 6,
) -> dict[str, FieldSpec]:
    """Flatten a JSON-schema object (with ``$ref``/``allOf``) into dotted paths.

    ``schemas`` resolves ``$ref`` by its last path segment, which works for both
    Discovery (``"$ref": "Campaign"``) and OpenAPI (``"#/components/schemas/Campaign"``).
    """
    out: dict[str, FieldSpec] = {}

    def deref(s: dict) -> tuple[dict, str | None]:
        if not isinstance(s, dict):
            return {}, None
        name = None
        if "$ref" in s:
            name = s["$ref"].rsplit("/", 1)[-1]
            target = schemas.get(name, {})
            s = {**target, **{k: v for k, v in s.items() if k != "$ref"}}
        if "allOf" in s:
            merged: dict = {"properties": {}, "required": []}
            for part in s["allOf"]:
                p, _ = deref(part)
                merged["properties"].update(p.get("properties", {}))
                merged["required"] += p.get("required", [])
                for k in ("type", "enum", "readOnly", "deprecated"):
                    if k in p:
                        merged[k] = p[k]
            s = {**merged, **{k: v for k, v in s.items() if k != "allOf"}}
        return s, name

    def type_of(s: dict, ref: str | None) -> str:
        if s.get("type") == "array" or "items" in s:
            item, iref = deref(s.get("items", {}))
            return f"array<{type_of(item, iref)}>"
        if s.get("properties"):
            return "object"
        t = s.get("type") or (ref and "object") or "unknown"
        return f"{t}({s['format']})" if s.get("format") else t

    def spec_for(parent: dict, name: str, raw: dict) -> FieldSpec:
        s, ref = deref(raw)
        enum = s.get("enum")
        enum_dep = None
        if s.get("type") == "array":
            item, _ = deref(s.get("items", {}))
            enum = item.get("enum")
            s_enum_dep = item.get("enumDeprecated")
        else:
            s_enum_dep = s.get("enumDeprecated")
        if enum and s_enum_dep:
            enum_dep = [v for v, dep in zip(enum, s_enum_dep) if dep] or None
        return FieldSpec(
            type=type_of(s, ref),
            required=is_required(parent, name, s),
            read_only=is_read_only(s),
            deprecated=bool(s.get("deprecated")),
            enum=list(enum) if enum else None,
            enum_deprecated=enum_dep,
        )

    def walk(schema: dict, prefix: str, depth: int, stack: frozenset) -> None:
        s, _ = deref(schema)
        for name, raw in (s.get("properties") or {}).items():
            path = f"{prefix}.{name}" if prefix else name
            out[path] = spec_for(s, name, raw)
            if depth >= max_depth:
                continue
            child, ref = deref(raw)
            if ref and ref in stack:
                continue
            if child.get("type") == "array" or "items" in child:
                item, iref = deref(child.get("items", {}))
                if item.get("properties") and not (iref and iref in stack):
                    walk(item, path + "[]", depth + 1, stack | {iref})
            elif child.get("properties"):
                walk(child, path, depth + 1, stack | {ref})

    _, root_ref = deref(root)
    walk(root, "", 0, frozenset({root_ref}))
    return out


def infer_fields(sample, prefix: str = "") -> dict[str, FieldSpec]:
    """Infer a field list from a real API response (used where no machine-readable
    docs exist). Nulls are typed ``unknown`` so they never register as type changes."""
    out: dict[str, FieldSpec] = {}
    if not isinstance(sample, dict):
        return out
    for name, value in sample.items():
        path = f"{prefix}.{name}" if prefix else name
        out[path] = FieldSpec(type=_json_type(value))
        if isinstance(value, dict):
            out.update(infer_fields(value, path))
        elif isinstance(value, list):
            items = [v for v in value if isinstance(v, dict)]
            if items:
                merged: dict = {}
                for item in items:
                    merged.update(item)
                out.update(infer_fields(merged, path + "[]"))
    return out


def _json_type(value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        inner = {_json_type(v) for v in value if v is not None}
        return f"array<{inner.pop() if len(inner) == 1 else 'unknown'}>"
    return "object"
