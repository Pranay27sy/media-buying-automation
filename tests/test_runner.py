import json

from apiwatch import report, runner
from apiwatch.fetchers import MetaSDKFetcher, TTDSampleFetcher
from conftest import FakeHttp

SDK_CONFIG = "ads_api_config = {\n  'API_VERSION': 'v26.0',\n  'SDK_VERSION': 'v26.0.1',\n}\n"


def routes(fixture_json, discovery=None, adaccount=None):
    disc = discovery or fixture_json("discovery.json")
    return FakeHttp({
        "discovery/v1/apis": {"items": [
            {"version": "v3", "discoveryRestUrl": "https://dv/v3"},
            {"version": "v4", "preferred": True, "discoveryRestUrl": "https://dv/v4"},
        ]},
        "https://dv/": disc,
        "apiconfig.py": SDK_CONFIG,
        "AdAccount.json": adaccount or fixture_json("meta_adaccount.json"),
    })


def test_meta_fetcher(fixture_json):
    f = MetaSDKFetcher("meta", {"entities": {"Campaign": "AdAccount:campaigns"}},
                       routes(fixture_json))
    assert f.latest_version() == "v26.0"
    fields = f.fetch("v26.0").entities["Campaign"]
    assert fields["special_ad_categories"].required
    assert fields["daily_budget"].type == "unsigned int"


def test_ttd_sample_fetcher():
    http = FakeHttp({
        "/authentication": {"Token": "t"},
        "/campaign/1": {"CampaignName": "x", "Budget": {"Amount": 1, "CurrencyCode": "USD"}},
    })
    f = TTDSampleFetcher("ttd", {"base_url": "https://ttd/v3", "login": "l", "password": "p",
                                 "entities": {"Campaign": {"path": "campaign", "id": "1"}}}, http)
    fields = f.fetch("v3").entities["Campaign"]
    assert {"CampaignName", "Budget", "Budget.Amount", "Budget.CurrencyCode"} == set(fields)


def test_first_run_saves_baselines_and_proposes_upgrade(project, fixture_json):
    results = {r.platform: r for r in runner.run(project, propose_upgrades=True, http=routes(fixture_json))}
    dv, meta, ttd = results["dv360"], results["meta"], results["ttd"]

    assert dv.first_run and (project / "snapshots/dv360/v4.json").exists()
    assert (project / "snapshots/dv360/v3.json").exists()  # the version you use is saved too
    assert dv.upgrade_proposed == "v4"                       # v4 breaks none of the watched fields
    assert "version_in_use: v4" in (project / "watchlists/dv360.yaml").read_text()

    # Meta: new mandatory field special_ad_categories isn't on the watchlist -> warning, still upgradable
    assert any(f.path == "special_ad_categories" for f in meta.findings)
    assert meta.upgrade_proposed == "v26.0"
    assert ttd.status == "manual"

    text = report.render(list(results.values()))
    assert "ready for your approval" in text and "Check by hand" in text


def test_breaking_change_blocks_upgrade_and_is_reported(project, fixture_json):
    runner.run(project, http=routes(fixture_json))  # week 1: baseline, no upgrade proposed

    week2 = fixture_json("discovery.json")
    props = week2["schemas"]["Campaign"]["properties"]
    props["title"] = props.pop("displayName")                        # renamed field
    props["entityStatus"]["enum"] = ["ENTITY_STATUS_UNSPECIFIED", "ENTITY_STATUS_ACTIVE"]
    props["entityStatus"]["enumDeprecated"] = [False, False]
    results = {r.platform: r for r in runner.run(project, propose_upgrades=True,
                                                   http=routes(fixture_json, discovery=week2))}
    dv = results["dv360"]
    assert dv.action_needed and not dv.upgrade_proposed
    msgs = {(f.path, f.message) for f in dv.findings}
    assert ("entityStatus", "value `ENTITY_STATUS_PAUSED` is no longer allowed") in msgs
    kinds = {(c.path, c.kind) for c in dv.changes}
    assert ("displayName", "removed") in kinds and ("title", "added_required") in kinds
    assert "version_in_use: v3" in (project / "watchlists/dv360.yaml").read_text()
    assert "Action needed" in report.render(list(results.values()))
    assert json.loads((project / "snapshots/dv360/v4.json").read_text())["entities"]["Campaign"]["title"]


def test_no_changes_writes_nothing(project, fixture_json):
    runner.run(project, http=routes(fixture_json))
    again = runner.run(project, http=routes(fixture_json))
    assert all(not r.files_changed and not r.changes for r in again)


def test_fetch_errors_are_reported_not_raised(project, fixture_json):
    http = routes(fixture_json)
    http.routes["apiconfig.py"] = "nothing useful here"
    results = runner.run(project, http=http)
    meta = {r.platform: r for r in results}["meta"]
    assert meta.status == "error" and "API version" in meta.message
    assert meta.action_needed  # marks the weekly run red
    assert "automatic check failed" in report.render(results)
    assert report.title(results).endswith("action needed")


def test_empty_discovery_directory_is_an_error(project, fixture_json):
    http = routes(fixture_json)
    http.routes["discovery/v1/apis"] = {"items": []}
    dv = {r.platform: r for r in runner.run(project, http=http)}["dv360"]
    assert dv.status == "error" and dv.action_needed


def test_report_never_says_all_good_when_a_platform_was_skipped():
    skipped = runner.PlatformResult("ttd", "The Trade Desk", "skipped", message="Set TTD_AUTH_TOKEN")
    assert "not checked this week" in report.render([skipped])
    assert "all good" not in report.render([skipped])
    assert report.title([skipped]).endswith("some platforms not checked")


def test_first_run_title_says_baseline(project, fixture_json):
    results = runner.run(project, http=routes(fixture_json))
    assert report.title(results).endswith("first check, baseline saved")
