"""Tests for build_pbip: determinism, generator defaults, calendar, hand-off pack.

Run: python -m pytest tests/
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pbip_model_forge.build_model import build_pbip, stable_id  # noqa: E402
from pbip_model_forge.check import SpecCheckError  # noqa: E402
from pbip_model_forge.cli import load_spec  # noqa: E402
from pbip_model_forge.model_info import calendar_years, infer_roles  # noqa: E402
from specs import good_spec  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _tmdl(out: Path, spec: dict, table: str) -> str:
    return (out / f"{spec['name']}.SemanticModel" / "definition" / "tables"
            / f"{table}.tmdl").read_text(encoding="utf-8")


def _column_block(text: str, column: str) -> str:
    m = re.search(rf"^\tcolumn {re.escape(column)}\n((?:\t\t.*\n)+)", text, re.M)
    assert m, f"column {column} not found"
    return m.group(1)


def _measure_block(text: str, measure: str) -> str:
    m = re.search(rf"^\tmeasure '?{re.escape(measure)}'? =.*\n((?:\t\t.*\n)+)", text, re.M)
    assert m, f"measure {measure} not found"
    return m.group(1)


# ---------------------------------------------------------------------------
def test_build_twice_is_byte_identical(tmp_path):
    spec = load_spec(REPO / "scripts" / "build_template.py")
    a, b = tmp_path / "a", tmp_path / "b"
    build_pbip(spec, a)
    build_pbip(spec, b)
    build_pbip(spec, b)  # rebuild in place too
    assert _tree(a) == _tree(b)
    assert "handoff/manifest.json" in _tree(a)


def test_committed_template_matches_a_fresh_build(tmp_path):
    spec = load_spec(REPO / "scripts" / "build_template.py")
    build_pbip(spec, tmp_path)
    fresh = _tree(tmp_path)
    committed = _tree(REPO / "template")
    assert fresh.keys() == committed.keys()
    for path, data in fresh.items():
        # git may check text files out with CRLF on Windows
        assert committed[path].replace(b"\r\n", b"\n") == data, path


def test_ids_are_unique_and_stable(tmp_path):
    spec = good_spec()
    build_pbip(spec, tmp_path)
    tags = []
    for p in tmp_path.rglob("*.tmdl"):
        tags += re.findall(r"lineageTag: (\S+)", p.read_text(encoding="utf-8"))
    assert len(tags) == len(set(tags))
    assert stable_id("Tiny", "Stores", "table", "Stores") in tags


def test_no_dangling_description_comments(tmp_path):
    """A /// run must be followed directly by its declaration, never a blank line."""
    for spec in (good_spec(), load_spec(REPO / "scripts" / "build_hospital.py")):
        out = tmp_path / spec["name"]
        build_pbip(spec, out)
        for p in out.rglob("*.tmdl"):
            lines = p.read_text(encoding="utf-8").split("\n")
            for i, line in enumerate(lines):
                if line.lstrip().startswith("///"):
                    nxt = lines[i + 1] if i + 1 < len(lines) else ""
                    assert nxt.strip(), f"dangling /// in {p.name} line {i + 1}"


def test_descriptions_sit_on_declarations(tmp_path):
    spec = good_spec()
    build_pbip(spec, tmp_path)
    text = _tmdl(tmp_path, spec, "Stores")
    assert "/// One row per store.\ntable Stores\n" in text
    assert "\t/// Store trading name.\n\tcolumn store_name\n" in text


def test_keys_and_relationship_columns_hidden(tmp_path):
    spec = good_spec()
    build_pbip(spec, tmp_path)
    stores = _tmdl(tmp_path, spec, "Stores")
    assert "isHidden" in _column_block(stores, "store_id")
    assert "isHidden" not in _column_block(stores, "store_name")
    sales = _tmdl(tmp_path, spec, "Sales")
    fk = _column_block(sales, "store_id")
    assert "isHidden" in fk and "isAvailableInMdx" not in fk
    amount = _column_block(sales, "amount")
    assert "isHidden" in amount and "isAvailableInMdx: false" in amount
    assert "isAvailableInMdx" not in _column_block(sales, "order_date")


def test_explicit_hidden_false_wins(tmp_path):
    spec = good_spec()
    spec["tables"][0]["columns"][0]["hidden"] = False
    build_pbip(spec, tmp_path)
    assert "isHidden" not in _column_block(_tmdl(tmp_path, spec, "Stores"), "store_id")


def test_display_folders_and_helpers(tmp_path):
    spec = good_spec()
    spec["measures_table"]["measures"][0]["displayFolder"] = "Sales\\Totals"
    build_pbip(spec, tmp_path)
    text = _tmdl(tmp_path, spec, "Key Measures")
    assert "displayFolder: Sales\\Totals" in _measure_block(text, "Total Sales")
    assert "displayFolder: Counts" in _measure_block(text, "Orders #")
    assert "displayFolder: Ratios" in _measure_block(text, "Avg Sales per Store")
    helper = _measure_block(text, "Sales Base")
    assert "isHidden" in helper and "displayFolder: _Helpers" in helper


def test_cross_filter_both_is_emitted(tmp_path):
    spec = good_spec()
    spec["relationships"][0]["crossFilter"] = "both"
    build_pbip(spec, tmp_path)
    rel = (tmp_path / "Tiny.SemanticModel" / "definition" / "relationships.tmdl").read_text()
    assert rel.count("crossFilteringBehavior: bothDirections") == 1


# -- calendar ----------------------------------------------------------------
def test_calendar_years_inferred_from_fact_dates(tmp_path):
    spec = good_spec()
    assert calendar_years(spec) == (2023, 2024)
    build_pbip(spec, tmp_path)
    cal = _tmdl(tmp_path, spec, "__Calendar")
    assert "CALENDAR ( DATE ( 2023, 1, 1 ), DATE ( 2024, 12, 31 ) )" in cal
    spec["calendar"].update(start_year=2020, end_year=2030)
    assert calendar_years(spec) == (2020, 2030)


def test_calendar_columns(tmp_path):
    spec = good_spec()
    build_pbip(spec, tmp_path)
    cal = _tmdl(tmp_path, spec, "__Calendar")
    assert "sortByColumn: 'Calendar Quarter'" in _column_block(cal, "Quarter")
    assert "sortByColumn: 'Month Start'" in _column_block(cal, "'Year-Month'")
    assert "sortByColumn: 'Day of Week Number'" in _column_block(cal, "'Day of Week'")
    assert "isHidden" in _column_block(cal, "'Day of Week Number'")
    assert "dataType: dateTime" in _column_block(cal, "'Week Start'")
    assert '"Week Start", [Date] - WEEKDAY ( [Date], 2 ) + 1' in cal
    assert "dataCategory: Time" in cal


# -- check integration -------------------------------------------------------
def test_build_with_check_raises_before_writing(tmp_path):
    spec = good_spec()
    spec["tables"][0]["rows"].append([1, "dup"])
    with pytest.raises(SpecCheckError) as exc:
        build_pbip(spec, tmp_path / "out", check=True)
    assert "FM004" in str(exc.value)
    assert not (tmp_path / "out").exists()
    build_pbip(good_spec(), tmp_path / "ok", check=True, profile="handoff")


def test_reserved_table_name_still_rejected(tmp_path):
    spec = good_spec()
    spec["measures_table"]["name"] = "Measures"
    with pytest.raises(ValueError):
        build_pbip(spec, tmp_path)


# -- hand-off pack -----------------------------------------------------------
def test_handoff_manifest(tmp_path):
    spec = good_spec()
    build_pbip(spec, tmp_path)
    manifest = json.loads((tmp_path / "handoff" / "manifest.json").read_text())
    roles = {t["name"]: t["role"] for t in manifest["tables"]}
    assert roles == {"Stores": "dimension", "Products": "dimension", "Sales": "fact",
                     "__Calendar": "calendar", "Key Measures": "measures"}
    assert roles == infer_roles(spec)
    avg = next(m for m in manifest["measures"] if m["name"] == "Avg Sales per Store")
    assert avg["dependsOn"]["measures"] == ["Stores #", "Total Sales"]
    share = next(m for m in manifest["measures"] if m["name"] == "Bike Share %")
    assert "Products[product_name]" in share["dependsOn"]["columns"]
    names = [t["name"] for t in manifest["tables"]]
    assert names == sorted(names, key=str.lower)


def test_handoff_spec_md(tmp_path):
    spec = good_spec()
    build_pbip(spec, tmp_path)
    md = (tmp_path / "handoff" / "SPEC.md").read_text()
    assert "```mermaid\nerDiagram\n" in md
    assert 'Stores ||--o{ Sales : "store_id"' in md
    assert "int64 store_id PK" in md and "int64 store_id FK" in md
    assert "| Avg Sales per Store | Ratios |" in md


def test_handoff_can_be_disabled(tmp_path):
    build_pbip(good_spec(), tmp_path, handoff=False)
    assert not (tmp_path / "handoff").exists()


# -- tmdl-preflight gate (skipped when the validator is not installed) -------
@pytest.mark.skipif(shutil.which("tmdl-preflight") is None,
                    reason="tmdl-preflight not on PATH")
@pytest.mark.parametrize("script", ["build_template", "build_hospital",
                                    "build_vet_clinic", "build_physio"])
def test_examples_pass_tmdl_preflight(tmp_path, script):
    spec = load_spec(REPO / "scripts" / f"{script}.py")
    build_pbip(spec, tmp_path)
    run = subprocess.run(["tmdl-preflight", "check", str(tmp_path)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "0 error(s)" in run.stdout
