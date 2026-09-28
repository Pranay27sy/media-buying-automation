"""Watchlists: the fields (and values) YOUR campaign tool sends to each platform.

Checking the API against this list is what turns "Google changed 300 things"
into "2 of those affect you".
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .diff import BREAKING, INFO, WARNING
from .schema import FieldSpec, Snapshot, normalize_path


@dataclass
class Watchlist:
    platform: str
    version_in_use: str
    levels: dict[str, dict[str, list | None]]
    path: Path | None = None
    notes: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Watchlist":
        data = yaml.safe_load(Path(path).read_text()) or {}
        levels = {}
        for level, fields in (data.get("levels") or {}).items():
            levels[level] = {normalize_path(k): (v if isinstance(v, list) or v is None else [v])
                             for k, v in (fields or {}).items()}
        return cls(
            platform=data["platform"],
            version_in_use=str(data.get("version_in_use", "")),
            levels=levels,
            path=Path(path),
            notes={k: data[k] for k in ("release_notes", "manual_check") if k in data},
        )

    def set_version(self, version: str) -> None:
        """Rewrite only the ``version_in_use`` line so comments survive."""
        assert self.path is not None
        text = self.path.read_text()
        text, n = re.subn(r"(?m)^(version_in_use:\s*)\S+", rf"\g<1>{version}", text, count=1)
        if not n:
            raise ValueError(f"No version_in_use line in {self.path}")
        self.path.write_text(text)
        self.version_in_use = version


@dataclass
class Finding:
    level: str
    path: str
    severity: str
    message: str


def check(watchlist: Watchlist, snap: Snapshot) -> list[Finding]:
    """Check every watched field/value against a snapshot, and flag mandatory
    fields the watchlist doesn't cover (a new required field breaks creation)."""
    findings: list[Finding] = []
    for level, fields in watchlist.levels.items():
        if level not in snap.entities:
            findings.append(Finding(level, "", WARNING, f"{level} is not tracked for {snap.platform} (check config/platforms.yaml)"))
            continue
        schema = snap.entities[level]
        if not schema:
            findings.append(Finding(level, "", BREAKING, f"{level} no longer exists in {snap.version}"))
            continue
        for path, values in fields.items():
            spec = schema.get(path)
            if spec is None:
                hint = _suggest(path, schema)
                findings.append(Finding(level, path, BREAKING,
                                        "field no longer exists" + (f" - maybe renamed to `{hint}`?" if hint else "")))
                continue
            if spec.deprecated:
                findings.append(Finding(level, path, WARNING, "field is deprecated and will be removed"))
            if spec.read_only:
                findings.append(Finding(level, path, BREAKING, "field is read-only - it can't be set when creating"))
            findings += _check_values(level, path, values, spec)
        watched = set(fields)
        for path, spec in sorted(schema.items()):
            if not spec.required or spec.read_only or path in watched:
                continue
            if any(w.startswith(path + ".") or w.startswith(path + "[]") for w in watched):
                continue  # we fill in something inside it, so it is sent
            parent = path.rsplit(".", 1)[0] if "." in path else ""
            # Nested mandatory fields only matter if we fill in their parent object.
            if parent and not any(w == parent or w.startswith(parent + ".") for w in watched):
                continue
            findings.append(Finding(level, path, WARNING, "MANDATORY field that isn't on your watchlist - does your tool send it?"))
    return findings


def _check_values(level: str, path: str, values, spec: FieldSpec) -> list[Finding]:
    if not values or not spec.enum:
        return []
    out = []
    for v in values:
        if v not in spec.enum:
            out.append(Finding(level, path, BREAKING, f"value `{v}` is no longer allowed"))
        elif v in (spec.enum_deprecated or []):
            out.append(Finding(level, path, WARNING, f"value `{v}` is deprecated"))
    return out


def _suggest(path: str, schema: dict[str, FieldSpec]) -> str | None:
    leaf = path.rsplit(".", 1)[-1].lower()
    by_leaf = {p.rsplit(".", 1)[-1].lower(): p for p in schema}
    match = difflib.get_close_matches(leaf, by_leaf, n=1, cutoff=0.75)
    if match:
        return by_leaf[match[0]]
    match = difflib.get_close_matches(path, list(schema), n=1, cutoff=0.75)
    return match[0] if match else None


def worst(findings) -> str:
    sev = {f.severity for f in findings}
    return BREAKING if BREAKING in sev else WARNING if WARNING in sev else INFO
