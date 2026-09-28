# Media buying API watch

Every Monday this project automatically checks the **DV360**, **Meta** and **The Trade Desk**
campaign APIs for changes, and tells you in plain English whether anything your campaign
tool uses has changed.

## How it works (non-technical)

1. **Every Monday at 06:00 UTC** a robot (GitHub Actions) looks up the current API
   "forms" for each platform: every field, what values it accepts, and which ones are mandatory.
2. It compares them with last week's and checks the **watchlist**, the fields your campaign
   tool sends (see [`watchlists/`](watchlists/)).
3. It posts a report as a comment on the **"Weekly API watch"** issue in this repository.
   GitHub emails everyone watching the repository.
4. If something changed, it also opens a **pull request** with the report and the updated files.
   **Merging that pull request is your approval.** Nothing changes until you do.

The report tells you, per platform:

| Status | Meaning |
|---|---|
| ✅ No action needed | Nothing that affects you changed. |
| 🟡 Heads-up | Something you use is being phased out, or a new mandatory field appeared. |
| ⬆️ Upgrade ready for your approval | A new API version is out and none of your fields are affected. Merge the pull request, then update the version number in your campaign tool. |
| 🔴 Action needed | Something you use was removed, renamed, or no longer accepts a value you send. Your campaign tool must be updated. |
| ✋ Check by hand | This platform can't be checked automatically yet (TTD, see below). |

### What each platform needs

| Platform | Checked automatically? | Credentials needed |
|---|---|---|
| Google DV360 | ✅ Yes, via Google's public API description | None |
| Meta | ✅ Yes, via Meta's public SDK specification | None |
| The Trade Desk | ✋ Manual checklist for now | TTD's docs need a partner login |

**To automate TTD later:** ask your TTD account manager for API access, then in GitHub go to
*Settings → Secrets and variables → Actions* and add `TTD_AUTH_TOKEN` (or `TTD_LOGIN` and
`TTD_PASSWORD`), plus `TTD_CAMPAIGN_ID` and `TTD_ADGROUP_ID` (the ids of any existing campaign
and ad group). Then change `mode: manual` to `mode: auto` for `ttd` in
[`config/platforms.yaml`](config/platforms.yaml).

### One-time setup

1. Make this branch the repository's default branch, or merge it into the default branch.
   GitHub only runs scheduled jobs from the default branch.
2. In *Settings → Actions → General*, tick **"Allow GitHub Actions to create and approve pull
   requests"** so the robot can open the weekly pull request.
3. Optional: to run the check right away, open *Actions → Weekly API check → Run workflow*.

### Keeping the watchlist accurate

The watchlists start with a **standard set** of fields most campaign tools send. The more closely
they match what your tool really sends, the fewer false alarms and missed changes you'll see.
See [`watchlists/README.md`](watchlists/README.md).

## Technical details

```
apiwatch/
  fetchers/google_discovery.py  DV360: Google Discovery documents (all versions, public)
  fetchers/meta_sdk.py          Meta: newest version from the official Python SDK; "create" params
                                (POST /act_<id>/campaigns, /adsets, /ads) from the public
                                facebook-business-sdk-codegen API specs
  fetchers/sample.py            TTD: infers fields from a real GET response (needs credentials)
  schema.py                     normalized snapshot format (dotted field paths) + storage
  diff.py                       classifies changes: removed, type change, newly mandatory, values ...
  watchlist.py                  checks your watched fields/values against a snapshot
  runner.py / report.py         weekly orchestration and the markdown report
config/platforms.yaml           which platforms/levels are checked and where from
watchlists/<platform>.yaml      fields your tool sends + the API version it uses
snapshots/<platform>/<v>.json   saved API schemas; git history is the change log
```

Run locally:

```bash
pip install -r requirements-dev.txt
python -m apiwatch run --report api-report.md                 # check everything
python -m apiwatch run --platform dv360 --dry-run             # check one platform, save nothing
python -m apiwatch run --propose-upgrades                     # also bump version_in_use when safe
python -m pytest -q
```

Limits worth knowing:

- **Meta**: the public spec lists field names, types and which fields are mandatory, but not
  the allowed values. Only the newest version is published, so older versions come from
  snapshots saved in earlier weeks.
- **Version retirement dates** aren't read automatically. The report links to each
  platform's deprecation page.
- **TTD** (once automated) sees the fields that appear in a real response. It catches added
  and removed fields, but not allowed values or mandatory fields.
