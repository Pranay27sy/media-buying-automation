"""Command line: ``python -m apiwatch run``."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import report, runner


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="apiwatch", description="Weekly ad-platform API change check")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="check all platforms and write a report")
    r.add_argument("--root", default=".", help="project folder (default: current)")
    r.add_argument("--platform", action="append", help="only check this platform (repeatable)")
    r.add_argument("--report", default="api-report.md", help="where to write the markdown report")
    r.add_argument("--propose-upgrades", action="store_true",
                   help="bump version_in_use when a newer version breaks none of your fields")
    r.add_argument("--dry-run", action="store_true", help="don't save snapshots or edit watchlists")
    args = ap.parse_args(argv)

    results = runner.run(Path(args.root), platforms=args.platform,
                         propose_upgrades=args.propose_upgrades, dry_run=args.dry_run)
    text = report.render(results)
    Path(args.report).write_text(text)
    title = report.title(results)
    print(title)
    for res in results:
        print(f"  {res.title}: {report.status_line(res)}" + (f" ({res.message})" if res.message else ""))

    if gh_out := os.environ.get("GITHUB_OUTPUT"):
        with open(gh_out, "a") as f:
            f.write(f"title={title}\n")
            f.write(f"action_needed={'true' if any(x.action_needed for x in results) else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
