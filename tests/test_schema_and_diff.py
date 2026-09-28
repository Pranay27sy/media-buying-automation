from apiwatch.diff import BREAKING, INFO, WARNING, diff_snapshots
from apiwatch.fetchers import GoogleDiscoveryFetcher
from apiwatch.schema import FieldSpec, Snapshot, SnapshotStore, infer_fields, version_key
from conftest import FakeHttp


def dv360(fixture_json):
    http = FakeHttp({
        "discovery/v1/apis": {"items": [
            {"version": "v3", "preferred": False, "discoveryRestUrl": "https://x/v3"},
            {"version": "v4", "preferred": True, "discoveryRestUrl": "https://x/v4"},
        ]},
        "https://x/": lambda: fixture_json("discovery.json"),
    })
    return GoogleDiscoveryFetcher("dv360", {"api": "displayvideo", "entities": ["Campaign"]}, http)


def test_discovery_flattening(fixture_json):
    f = dv360(fixture_json)
    assert f.latest_version() == "v4"
    fields = f.fetch("v4").entities["Campaign"]
    assert fields["displayName"] == FieldSpec(type="string", required=True)
    assert fields["name"].read_only
    assert fields["campaignGoal"].type == "object"
    assert fields["campaignGoal.campaignGoalType"].enum == ["A", "B"]
    assert fields["campaignBudgets"].type == "array<object>"
    assert fields["campaignBudgets[].budgetAmountMicros"].type == "string(int64)"
    assert "parent.displayName" not in fields  # self-reference isn't expanded forever


def snap(**fields):
    return Snapshot("p", "v1", {"Campaign": fields})


def test_diff_classifies_changes():
    old = snap(
        a=FieldSpec(type="string"),
        b=FieldSpec(type="string"),
        c=FieldSpec(type="string", enum=["X", "Y"]),
        d=FieldSpec(type="string"),
    )
    new = snap(
        b=FieldSpec(type="integer"),
        c=FieldSpec(type="string", enum=["X", "Z"], enum_deprecated=["X"]),
        d=FieldSpec(type="string", deprecated=True, required=True),
        e=FieldSpec(type="string"),
        f=FieldSpec(type="string", required=True),
    )
    got = {(c.path, c.kind): c.severity for c in diff_snapshots(old, new)}
    assert got == {
        ("a", "removed"): BREAKING,
        ("b", "type_changed"): BREAKING,
        ("c", "values_removed"): BREAKING,
        ("c", "values_added"): INFO,
        ("c", "values_deprecated"): WARNING,
        ("d", "became_required"): BREAKING,
        ("d", "deprecated"): WARNING,
        ("e", "added"): INFO,
        ("f", "added_required"): BREAKING,
    }


def test_unknown_types_are_not_type_changes():
    old = snap(a=FieldSpec(type="unknown"))
    new = snap(a=FieldSpec(type="string"))
    assert diff_snapshots(old, new) == []


def test_store_roundtrip(tmp_path):
    store = SnapshotStore(tmp_path)
    s = Snapshot("dv360", "v4", {"Campaign": {"x": FieldSpec(type="string", enum=["A"])}}, revision="1")
    store.save(s)
    loaded = store.load("dv360", "v4")
    assert loaded.same_schema(s) and loaded.revision == "1"
    assert store.versions("dv360") == ["v4"]


def test_version_ordering():
    assert sorted(["v10", "v9", "v4"], key=version_key) == ["v4", "v9", "v10"]
    assert version_key("v26.0") > version_key("v25.0")


def test_infer_fields_from_sample():
    fields = infer_fields({"Name": "x", "Budget": {"Amount": 5}, "Flights": [{"Id": 1}], "Notes": None})
    assert fields["Budget.Amount"].type == "number"
    assert fields["Flights[].Id"].type == "number"
    assert fields["Notes"].type == "unknown"
