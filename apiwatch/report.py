"""Plain-English markdown report - written for people, not programmers."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from .diff import BREAKING, INFO, WARNING
from .runner import PlatformResult
from .watchlist import worst

ICON = {BREAKING: "🔴", WARNING: "🟡", INFO: "🟢"}
MAX_DETAIL_ROWS = 300


def status_line(r: PlatformResult) -> str:
    if r.status == "error":
        return "⚠️ Check failed"
    if r.status == "skipped":
        return "⚪ Not checked"
    if r.status == "manual":
        return "✋ Check by hand"
    if r.action_needed:
        return "🔴 Action needed"
    if r.upgrade_proposed:
        return f"⬆️ Upgrade to {r.upgrade_proposed} ready for your approval"
    if r.first_run:
        return "📸 First check - baseline saved"
    if worst(r.findings) == WARNING or any(c.severity != INFO for c in r.changes):
        return "🟡 Heads-up"
    return "✅ No action needed"


def title(results: list[PlatformResult], today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    if any(r.action_needed for r in results):
        what = "action needed"
    elif any(r.upgrade_proposed for r in results):
        what = "upgrade ready for approval"
    elif any(r.status in ("error", "skipped") for r in results):
        what = "some platforms not checked"
    elif any(r.changes for r in results):
        what = "changes found"
    elif any(r.first_run for r in results):
        what = "first check, baseline saved"
    else:
        what = "no changes"
    return f"API check {today.isoformat()}: {what}"


def render(results: list[PlatformResult], today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    out = [f"# Weekly ad-platform API check - {today:%d %b %Y}", ""]
    out += ["| Platform | Version you use | Newest version | Status |", "|---|---|---|---|"]
    for r in results:
        out.append(f"| **{r.title}** | {r.version_in_use or '-'} | {r.latest_version or '-'} | {status_line(r)} |")
    out.append("")
    out += _todo(results)
    for r in results:
        out += _platform(r)
    out += [
        "---",
        "<sub>Legend: 🔴 breaks campaign creation · 🟡 will break later / please check · "
        "🟢 harmless. Generated automatically by `apiwatch` every Monday.</sub>",
    ]
    return "\n".join(out) + "\n"


def _todo(results) -> list[str]:
    items = []
    for r in results:
        if r.status == "error":
            items.append(f"**{r.title}**: the automatic check failed (`{r.message}`). Ask a developer to look at the workflow run.")
        elif r.status == "skipped":
            items.append(f"**{r.title}**: not checked this week ({r.message}).")
        elif r.action_needed:
            items.append(f"**{r.title}**: something you use changed - see the 🔴 items below. Your campaign tool needs updating.")
        elif r.upgrade_proposed:
            items.append(f"**{r.title}**: version **{r.upgrade_proposed}** is out and none of your fields are affected. "
                         f"Approving this pull request switches the watchlist from {r.version_in_use} to {r.upgrade_proposed}; "
                         "then update the version number in your campaign tool.")
        elif r.new_version:
            items.append(f"**{r.title}**: version **{r.latest_version}** is out (you use {r.version_in_use}).")
        elif r.status == "manual":
            items.append(f"**{r.title}**: {r.message}. Please go through the manual checklist below.")
    out = ["## What you need to do", ""]
    out += [f"{i}. {t}" for i, t in enumerate(items, 1)] if items else ["Nothing - all good this week. ✅"]
    return out + [""]


def _platform(r: PlatformResult) -> list[str]:
    out = [f"## {r.title}", ""]
    for label, url in r.links.items():
        out.append(f"- {label}: {url}")
    if r.links:
        out.append("")
    if r.status in ("error", "skipped"):
        return out + [f"Not checked: {r.message}", ""]
    if r.status == "manual":
        return out + _manual(r)
    if r.message:
        out += [f"> {r.message}", ""]
    if r.first_run:
        out += ["This is the first check, so there's nothing to compare with yet. "
                "The current API has been saved; from next week you'll see what changed.", ""]

    watched = _watched(r)
    if r.findings_in_use:
        out += [f"### Your fields on the version you use today ({r.version_in_use})", ""]
        out += _findings(r.findings_in_use)
    label = f"on the newest version ({r.latest_version})" if r.new_version else f"({r.latest_version})"
    out += [f"### Your fields {label}", ""]
    out += _findings(r.findings)

    if r.changes:
        mine = [c for c in r.changes if (c.entity, c.path) in watched or c.kind in ("added_required", "became_required", "entity_removed")]
        since = f"since last check ({r.baseline_version})" if r.baseline_version != r.latest_version else "since last check"
        out += [f"### Everything that changed in the API {since}", ""]
        counts = defaultdict(int)
        for c in r.changes:
            counts[c.severity] += 1
        out.append(" · ".join(f"{ICON[s]} {counts[s]} {n}" for s, n in
                              ((BREAKING, "breaking"), (WARNING, "warnings"), (INFO, "harmless")) if counts[s]))
        out.append("")
        if mine:
            out += ["**Changes that touch fields you use (or new mandatory fields):**", ""]
            out += [f"- {ICON[c.severity]} {c.entity} → `{c.path}`: {c.detail}" for c in mine]
            out.append("")
        out += ["<details><summary>Full list</summary>", "", "| | Level | Field | Change |", "|---|---|---|---|"]
        for c in r.changes[:MAX_DETAIL_ROWS]:
            out.append(f"| {ICON[c.severity]} | {c.entity} | `{c.path}` | {c.detail} |")
        if len(r.changes) > MAX_DETAIL_ROWS:
            out.append(f"| | | | …and {len(r.changes) - MAX_DETAIL_ROWS} more (see the snapshot files in this pull request) |")
        out += ["", "</details>", ""]
    elif not r.first_run:
        out += ["No changes in the API since last check.", ""]
    return out


def _findings(findings) -> list[str]:
    if not findings:
        return ["✅ All fields you use are still valid.", ""]
    by_level = defaultdict(list)
    for f in findings:
        by_level[f.level].append(f)
    out = []
    for level, items in by_level.items():
        out.append(f"**{level}**")
        out += [f"- {ICON[f.severity]} " + (f"`{f.path}`: " if f.path else "") + f.message for f in items]
        out.append("")
    return out


def _manual(r: PlatformResult) -> list[str]:
    out = [f"This platform can't be checked automatically yet: {r.message}.", ""]
    if r.watchlist and r.watchlist.notes.get("manual_check"):
        out += [str(r.watchlist.notes["manual_check"]).strip(), ""]
    if r.watchlist:
        out += [f"Look in the release notes for anything about these fields (version you use: {r.version_in_use or '-'}):", ""]
        for level, fields in r.watchlist.levels.items():
            out.append(f"- [ ] **{level}**: " + ", ".join(f"`{p}`" for p in fields))
        out.append("")
    return out


def _watched(r: PlatformResult) -> set[tuple[str, str]]:
    if not r.watchlist:
        return set()
    return {(level, p) for level, fields in r.watchlist.levels.items() for p in fields}
