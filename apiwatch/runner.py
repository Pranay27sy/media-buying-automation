"""The weekly check: fetch each platform, compare with last week, check the watchlist."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .diff import BREAKING, Change, diff_snapshots
from .fetchers import Http, SkipPlatform, make_fetcher
from .schema import SnapshotStore, version_key
from .watchlist import Finding, Watchlist, check, worst

_ENV = re.compile(r"\$\{(\w+)\}")


def load_config(path: Path) -> dict:
    """YAML config where ``${NAME}`` is replaced by the environment variable NAME
    (empty if unset), so secrets never live in the repo."""
    def expand(v):
        if isinstance(v, str):
            return _ENV.sub(lambda m: os.environ.get(m.group(1), ""), v)
        if isinstance(v, dict):
            return {k: expand(x) for k, x in v.items()}
        if isinstance(v, list):
            return [expand(x) for x in v]
        return v
    return expand(yaml.safe_load(Path(path).read_text()) or {})


@dataclass
class PlatformResult:
    platform: str
    title: str
    status: str  # checked | manual | skipped | error
    message: str = ""
    version_in_use: str = ""
    latest_version: str = ""
    baseline_version: str = ""
    first_run: bool = False
    changes: list[Change] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)          # on the newest version
    findings_in_use: list[Finding] = field(default_factory=list)   # on the version you use today
    upgrade_proposed: str = ""
    watchlist: Watchlist | None = None
    links: dict = field(default_factory=dict)
    files_changed: list[Path] = field(default_factory=list)

    @property
    def new_version(self) -> bool:
        return bool(self.version_in_use and self.latest_version
                    and version_key(self.latest_version) > version_key(self.version_in_use))

    @property
    def action_needed(self) -> bool:
        return self.status == "error" or worst(self.findings_in_use or self.findings) == BREAKING or (
            self.new_version and worst(self.findings) == BREAKING)


def run(root: Path, *, platforms: list[str] | None = None, propose_upgrades: bool = False,
        dry_run: bool = False, http: Http | None = None) -> list[PlatformResult]:
    root = Path(root)
    cfg = load_config(root / "config" / "platforms.yaml")
    store = SnapshotStore(root / "snapshots")
    http = http or Http()
    results = []
    for name, pcfg in (cfg.get("platforms") or {}).items():
        if platforms and name not in platforms:
            continue
        results.append(_run_platform(root, name, pcfg, store, http, propose_upgrades, dry_run))
    return results


def _run_platform(root, name, pcfg, store, http, propose_upgrades, dry_run) -> PlatformResult:
    wl_path = root / "watchlists" / f"{name}.yaml"
    wl = Watchlist.load(wl_path) if wl_path.exists() else None
    res = PlatformResult(
        platform=name,
        title=pcfg.get("title", name),
        status="checked",
        version_in_use=wl.version_in_use if wl else "",
        watchlist=wl,
        links=pcfg.get("links") or {},
    )
    if pcfg.get("mode") == "manual":
        res.status, res.message = "manual", pcfg.get("manual_reason", "Checked by hand")
        return res

    fetcher = make_fetcher(name, pcfg, http)
    try:
        res.latest_version = fetcher.latest_version()
        new = fetcher.fetch(res.latest_version)
    except SkipPlatform as e:
        res.status, res.message = "skipped", str(e)
        return res
    except Exception as e:  # network errors, format changes on the platform's side...
        res.status, res.message = "error", f"{type(e).__name__}: {e}"
        return res

    saved_same = store.load(name, res.latest_version)
    stored = store.versions(name)
    baseline = saved_same or (store.load(name, stored[-1]) if stored else None)
    if baseline:
        res.baseline_version = baseline.version
        res.changes = diff_snapshots(baseline, new)
    else:
        res.first_run = True
    if not new.same_schema(saved_same) and not dry_run:
        res.files_changed.append(store.save(new))

    if not wl:
        return res
    res.findings = check(wl, new)

    in_use = wl.version_in_use
    if in_use and in_use != res.latest_version:
        snap_in_use = None
        if fetcher.historical_versions:
            try:
                snap_in_use = fetcher.fetch(in_use)
            except Exception as e:
                res.message = f"Could not fetch version {in_use}: {e}"
            if snap_in_use and not snap_in_use.same_schema(store.load(name, in_use)) and not dry_run:
                res.files_changed.append(store.save(snap_in_use))
        else:
            snap_in_use = store.load(name, in_use)
        if snap_in_use:
            res.findings_in_use = check(wl, snap_in_use)

    if propose_upgrades and res.new_version and worst(res.findings) != BREAKING:
        res.upgrade_proposed = res.latest_version
        if not dry_run:
            wl.set_version(res.latest_version)
            res.files_changed.append(wl.path)
    return res
