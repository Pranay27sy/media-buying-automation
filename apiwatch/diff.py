"""Compare two snapshots of the same platform and classify every change."""
from __future__ import annotations

from dataclasses import dataclass

from .schema import FieldSpec, Snapshot

BREAKING, WARNING, INFO = "breaking", "warning", "info"


@dataclass
class Change:
    entity: str
    path: str
    kind: str
    severity: str
    detail: str = ""


def _is_unknown(t: str) -> bool:
    return t in ("unknown", "") or "unknown" in t


def diff_fields(entity: str, old: dict[str, FieldSpec], new: dict[str, FieldSpec]) -> list[Change]:
    changes: list[Change] = []
    for path in sorted(old.keys() - new.keys()):
        changes.append(Change(entity, path, "removed", BREAKING, "field no longer exists"))
    for path in sorted(new.keys() - old.keys()):
        spec = new[path]
        if spec.required and not spec.read_only:
            changes.append(Change(entity, path, "added_required", BREAKING, "new MANDATORY field"))
        else:
            changes.append(Change(entity, path, "added", INFO, "new optional field"))
    for path in sorted(old.keys() & new.keys()):
        a, b = old[path], new[path]
        if a.type != b.type and not (_is_unknown(a.type) or _is_unknown(b.type)):
            changes.append(Change(entity, path, "type_changed", BREAKING, f"type {a.type} → {b.type}"))
        if b.required and not a.required and not b.read_only:
            changes.append(Change(entity, path, "became_required", BREAKING, "is now MANDATORY"))
        if a.required and not b.required:
            changes.append(Change(entity, path, "became_optional", INFO, "is now optional"))
        if b.deprecated and not a.deprecated:
            changes.append(Change(entity, path, "deprecated", WARNING, "marked deprecated (will be removed)"))
        if b.read_only and not a.read_only:
            changes.append(Change(entity, path, "became_read_only", BREAKING, "can no longer be set (read-only)"))
        old_enum, new_enum = set(a.enum or []), set(b.enum or [])
        if a.enum and b.enum:
            if gone := sorted(old_enum - new_enum):
                changes.append(Change(entity, path, "values_removed", BREAKING, "values removed: " + ", ".join(gone)))
            if added := sorted(new_enum - old_enum):
                changes.append(Change(entity, path, "values_added", INFO, "values added: " + ", ".join(added)))
        if newly := sorted(set(b.enum_deprecated or []) - set(a.enum_deprecated or [])):
            changes.append(Change(entity, path, "values_deprecated", WARNING, "values deprecated: " + ", ".join(newly)))
    return changes


def diff_snapshots(old: Snapshot, new: Snapshot) -> list[Change]:
    changes: list[Change] = []
    for entity in sorted(old.entities.keys() | new.entities.keys()):
        if entity not in new.entities or (old.entities.get(entity) and not new.entities[entity]):
            changes.append(Change(entity, "", "entity_removed", BREAKING, f"{entity} is no longer in the API"))
            continue
        changes += diff_fields(entity, old.entities.get(entity, {}), new.entities[entity])
    return changes
