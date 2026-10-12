"""Tests for ``pbip-forge check``: one good spec, then one mutation per rule.

Run: python -m pytest tests/
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pbip_model_forge.check import (  # noqa: E402
    RULES, blocking, check_spec, dax_references, reads_table, strip_dax,
)
from pbip_model_forge.cli import forge_main, load_spec  # noqa: E402
from specs import good_spec  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _table(spec, name):
    return next(t for t in spec["tables"] if t["name"] == name)


def _measure(spec, name):
    return next(m for m in spec["measures_table"]["measures"] if m["name"] == name)


def _rules(spec, profile="handoff"):
    return {v.rule for v in check_spec(spec, profile)}


def _severity(spec, rule, profile="handoff"):
    return {v.severity for v in check_spec(spec, profile) if v.rule == rule}


# ---------------------------------------------------------------------------
def test_good_spec_is_clean_in_both_profiles():
    for profile in ("mockup", "handoff"):
        assert check_spec(good_spec(), profile) == []


def test_rule_catalog_ids_are_sequential():
    assert list(RULES) == [f"FM{i:03d}" for i in range(1, len(RULES) + 1)]
    for r in RULES.values():
        assert r.mockup in ("P0", "P1", "P2") and r.handoff in ("P0", "P1", "P2")
        assert r.rationale and r.fix


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        check_spec(good_spec(), "strict")


# -- structure ---------------------------------------------------------------
def test_fm001_missing_relationship_column():
    s = good_spec()
    s["relationships"][0]["to"] = "Stores.store_key"
    assert "FM001" in _rules(s)


def test_fm002_row_width():
    s = good_spec()
    _table(s, "Stores")["rows"].append([3])
    assert "FM002" in _rules(s)


def test_fm003_dimension_without_key():
    s = good_spec()
    _table(s, "Products")["columns"][0]["key"] = False
    assert "FM003" in _rules(s)


def test_fm004_duplicate_and_null_keys():
    s = good_spec()
    _table(s, "Stores")["rows"].append([1, "North again"])
    _table(s, "Products")["rows"].append([None, "Lock"])
    found = [v for v in check_spec(s, "handoff") if v.rule == "FM004"]
    assert {v.object for v in found} == {"'Stores'[store_id]", "'Products'[product_id]"}
    assert all(v.severity == "P0" for v in found)


def test_fm005_orphan_and_null_fk_suggest_unknown_member():
    s = good_spec()
    _table(s, "Sales")["rows"].append([4, dt.date(2023, 5, 5), 99, 10, 5.0])
    _table(s, "Sales")["rows"].append([5, dt.date(2023, 5, 6), None, 10, 5.0])
    found = [v for v in check_spec(s, "handoff") if v.rule == "FM005"]
    assert len(found) == 2
    assert all("Unknown" in v.fix for v in found)


def test_fm006_type_mismatch_and_fm007_name_mismatch():
    s = good_spec()
    _table(s, "Sales")["columns"][2] = {"name": "shop_id", "type": "string"}
    s["relationships"][0]["from"] = "Sales.shop_id"
    _measure(s, "Stores #")["expression"] = "DISTINCTCOUNT(Sales[shop_id])"
    for row in _table(s, "Sales")["rows"]:
        row[2] = str(row[2])
    assert _severity(s, "FM006") == {"P0"}
    assert _severity(s, "FM007") == {"P2"}


# -- graph -------------------------------------------------------------------
def test_fm008_fact_without_active_calendar_link():
    s = good_spec()
    s["relationships"][2]["active"] = False
    assert "FM008" in _rules(s)
    s = good_spec()
    del s["calendar"]
    s["relationships"].pop()
    assert "FM008" in _rules(s)


def test_fm009_disconnected_dimension():
    s = good_spec()
    s["tables"].append({
        "name": "Regions", "description": "One row per region.",
        "columns": [{"name": "region_id", "type": "int64", "key": True}],
        "rows": [[1]],
    })
    assert "FM009" in _rules(s)


def test_snowflaked_dimension_counts_as_connected():
    s = good_spec()
    s["tables"].append({
        "name": "Regions", "description": "One row per region.",
        "columns": [{"name": "region_id", "type": "int64", "key": True}],
        "rows": [[1]],
    })
    stores = _table(s, "Stores")
    stores["columns"].append({"name": "region_id", "type": "int64"})
    for row in stores["rows"]:
        row.append(1)
    s["relationships"].append({"from": "Stores.region_id", "to": "Regions.region_id"})
    assert check_spec(s, "handoff") == []


def test_fm010_bidirectional():
    s = good_spec()
    s["relationships"][0]["crossFilter"] = "both"
    assert "FM010" in _rules(s)


def test_fm011_two_active_paths():
    s = good_spec()
    sales = _table(s, "Sales")
    sales["columns"].append({"name": "ship_date", "type": "datetime"})
    for row in sales["rows"]:
        row.append(row[1])
    s["relationships"].append({"from": "Sales.ship_date", "to": "__Calendar.Date"})
    assert _severity(s, "FM011") == {"P0"}
    s["relationships"][-1]["active"] = False
    assert "FM011" not in _rules(s)


def test_fm012_cycle():
    s = good_spec()
    stores = _table(s, "Stores")
    stores["columns"].append({"name": "order_id", "type": "int64"})
    for row in stores["rows"]:
        row.append(1)
    s["relationships"].append({"from": "Stores.order_id", "to": "Sales.order_id",
                               "active": False})
    assert "FM012" in _rules(s)


# -- DAX ---------------------------------------------------------------------
def test_fm013_unresolved_references():
    s = good_spec()
    _measure(s, "Total Sales")["expression"] = "SUM(Sales[amount_typo]) + [Nope] + SUM('Ghost'[x])"
    msgs = [v.message for v in check_spec(s) if v.rule == "FM013"]
    assert any("amount_typo" in m for m in msgs)
    assert any("[Nope]" in m for m in msgs)
    assert any("Ghost" in m for m in msgs)


def test_fm013_ignores_comments_and_strings():
    s = good_spec()
    _measure(s, "Total Sales")["expression"] = (
        "SUM(Sales[amount]) // not [Real]\n/* 'Ghost'[x] */ & \"[Also Not]\""
    )
    assert "FM013" not in _rules(s)


def test_fm014_fact_only_sensed_is_not_read():
    s = good_spec()
    for m in s["measures_table"]["measures"]:
        m["expression"] = "IF(ISFILTERED(Sales), 1, 0)"
    assert "FM014" in _rules(s)


def test_fm015_ratio_grain_counts_dimension():
    s = good_spec()
    _measure(s, "Stores #")["expression"] = "DISTINCTCOUNT(Stores[store_id])"
    found = [v for v in check_spec(s, "handoff") if v.rule == "FM015"]
    assert len(found) == 1
    assert found[0].object == "'Key Measures'[Avg Sales per Store]"
    assert "DISTINCTCOUNT(Sales[store_id])" in found[0].fix


def test_fm015_countrows_of_dimension_inline():
    s = good_spec()
    _measure(s, "Avg Sales per Store")["expression"] = "DIVIDE([Total Sales], COUNTROWS(Stores))"
    assert "FM015" in _rules(s)


# -- documentation and naming -----------------------------------------------
def test_fm016_fm017_fm018_profiles_differ():
    s = good_spec()
    m = _measure(s, "Total Sales")
    del m["format"]
    m["description"] = "TBD"
    m["displayFolder"] = ""
    for rule in ("FM016", "FM017", "FM018"):
        assert _severity(s, rule, "handoff") == {"P1"}
        assert _severity(s, rule, "mockup") == {"P2"}
    assert blocking(check_spec(s, "mockup")) == []


def test_helper_measures_are_exempt_from_docs_rules():
    s = good_spec()
    assert "description" not in _measure(s, "Sales Base")
    assert check_spec(s, "handoff") == []


def test_fm019_name_format_agreement():
    s = good_spec()
    _measure(s, "Bike Share %")["format"] = "#,0.00"
    _measure(s, "Orders #")["format"] = "#,0.0"
    found = [v for v in check_spec(s) if v.rule == "FM019"]
    assert {v.object for v in found} == {"'Key Measures'[Bike Share %]",
                                         "'Key Measures'[Orders #]"}


def test_fm020_dates_outside_calendar():
    s = good_spec()
    s["calendar"].update(start_year=2024, end_year=2024)
    assert "FM020" in _rules(s)


def test_fm021_fm022_descriptions():
    s = good_spec()
    del _table(s, "Stores")["description"]
    del _table(s, "Products")["columns"][1]["description"]
    assert _severity(s, "FM021") == {"P1"}
    assert _severity(s, "FM022") == {"P2"}


# -- helpers -----------------------------------------------------------------
def test_strip_dax_keeps_offsets():
    expr = 'SUM(T[a]) -- c\n+ "x[y]"'
    assert len(strip_dax(expr)) == len(expr)
    assert "[y]" not in strip_dax(expr)


def test_dax_references_shapes():
    refs = dax_references("SUM('My T'[a]) + T2[b] + [M] + COUNTROWS('Other')")
    assert refs["qualified"] == [("My T", "a"), ("T2", "b")]
    assert refs["bare"] == ["M"]
    assert refs["tables"] == ["Other"]


def test_reads_table_ignores_sensors():
    assert not reads_table("IF(ISINSCOPE(Sales[x]), 1)", "Sales")
    assert reads_table("IF(ISINSCOPE(Sales[x]), SUM(Sales[y]))", "Sales")


# -- CLI ---------------------------------------------------------------------
def test_cli_check_json_spec_exit_codes(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(good_spec(), default=str), encoding="utf-8")
    assert forge_main(["check", str(good), "--profile", "handoff"]) == 0
    assert "0 P0, 0 P1, 0 P2" in capsys.readouterr().out

    bad = good_spec()
    _measure(bad, "Stores #")["expression"] = "DISTINCTCOUNT(Stores[store_id])"
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad, default=str), encoding="utf-8")
    assert forge_main(["check", str(bad_path), "--format", "json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["violations"][0]["rule"] == "FM015"


def test_cli_build_with_check_refuses(tmp_path, capsys):
    bad = good_spec()
    _table(bad, "Stores")["rows"].append([1, "dup"])
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad, default=str), encoding="utf-8")
    assert forge_main(["build", str(path), str(tmp_path / "out"), "--check"]) == 1
    assert not (tmp_path / "out").exists()
    assert "FM004" in capsys.readouterr().err


def test_load_spec_from_python_file():
    spec = load_spec(REPO / "scripts" / "build_template.py")
    assert spec["name"] == "Model"


@pytest.mark.parametrize("script", ["build_template", "build_hospital",
                                    "build_vet_clinic", "build_physio"])
def test_examples_pass_handoff_profile(script):
    spec = load_spec(REPO / "scripts" / f"{script}.py")
    assert blocking(check_spec(spec, "handoff")) == []
