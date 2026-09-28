from apiwatch.diff import BREAKING, WARNING
from apiwatch.schema import FieldSpec, Snapshot
from apiwatch.watchlist import Watchlist, check


def wl(levels):
    return Watchlist("p", "v1", levels)


def findings(levels, fields):
    return {(f.path, f.severity, f.message) for f in check(wl(levels), Snapshot("p", "v1", {"Campaign": fields}))}


def test_removed_field_suggests_rename():
    got = findings({"Campaign": {"budgetAmount": None}}, {"budgetAmountMicros": FieldSpec(type="string")})
    assert ("budgetAmount", BREAKING, "field no longer exists - maybe renamed to `budgetAmountMicros`?") in got


def test_values_checked():
    spec = FieldSpec(type="string", enum=["A", "B"], enum_deprecated=["B"])
    got = findings({"Campaign": {"s": ["B", "C"]}}, {"s": spec})
    assert ("s", WARNING, "value `B` is deprecated") in got
    assert ("s", BREAKING, "value `C` is no longer allowed") in got


def test_mandatory_fields_not_watched():
    fields = {
        "name": FieldSpec(type="string"),
        "goal": FieldSpec(type="object", required=True),
        "goal.type": FieldSpec(type="string", required=True),
        "goal.amount": FieldSpec(type="string"),
        "status": FieldSpec(type="string", required=True),
        "id": FieldSpec(type="string", required=True, read_only=True),
        "optionalThing.inner": FieldSpec(type="string", required=True),
    }
    got = {p for p, sev, _ in findings({"Campaign": {"name": None, "goal.amount": None}}, fields)}
    # goal is covered by goal.amount; goal.type is mandatory inside something we send;
    # status is top-level mandatory; read-only and fields inside unsent objects are ignored.
    assert got == {"goal.type", "status"}


def test_set_version_keeps_comments(project):
    path = project / "watchlists" / "dv360.yaml"
    w = Watchlist.load(path)
    w.set_version("v4")
    text = path.read_text()
    assert "version_in_use: v4" in text and "# a comment that must survive" in text
    assert Watchlist.load(path).version_in_use == "v4"
