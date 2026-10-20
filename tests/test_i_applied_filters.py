"""`pbip-forge i-filters`: regenerate the `i-Applied Filters` caption measure.

Fixture: tests/fixtures/i_filters/Shops.SemanticModel (fictional shop chain):
`y-Selector 1` offers Stores[Store Name] (order 2), Stores[Region] (order 1)
and __Calendar[Date] (order 3); `Helper Measures` holds a placeholder
`i-Applied Filters = ""`.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from forge_helpers import copy_fixture, forge, tree
from pbip_model_forge import i_filters


@pytest.fixture
def model(tmp_path: Path) -> Path:
    return copy_fixture("i_filters/Shops.SemanticModel", tmp_path)


def _tables(model: Path) -> Path:
    return model / "definition" / "tables"


def _helper(model: Path) -> Path:
    return _tables(model) / "Helper Measures.tmdl"


def _selector(name: str, rows: list[str]) -> str:
    body = ",\n".join(f"\t\t\t\t    {r}" for r in rows)
    return (f"table '{name}'\n\tlineageTag: {name}\n\n"
            f"\tpartition '{name}' = calculated\n\t\tmode: import\n\t\tsource =\n"
            f"\t\t\t\t{{\n{body}\n\t\t\t\t}}\n")


def _table(name: str, columns: list[str], hidden: tuple[str, ...] = ()) -> str:
    text = f"table '{name}'\n\tlineageTag: {name}\n\n"
    for col in columns:
        text += (f"\tcolumn '{col}'\n\t\tdataType: string\n"
                 + ("\t\tisHidden\n" if col in hidden else "")
                 + f"\t\tlineageTag: {col}\n\t\tsourceColumn: {col}\n\n")
    return text


def STORE(col: str) -> str:
    return f"'Stores'[{col}]"


BLOCK = """IF(
    ISFILTERED({c}),
    VAR ___f = FILTERS({c})
    VAR ___x = EXCEPT(ALL({c}), ___f)
    VAR ___nX = COUNTROWS(___x)
    VAR ___inv = COUNTROWS(ALL({c})) > 5 && ___nX >= 1 && ___nX <= 3
    VAR ___t = TOPN(10, ___f, {c})
    VAR ___d = CONCATENATEX(___t, IF(ISBLANK({c}), "(Blank)", {c} & ""), ", ")
    VAR ___dx = CONCATENATEX(___x, IF(ISBLANK({c}), "(Blank)", {c} & ""), ", ", {c}, ASC)
    RETURN "{label}" & IF(___inv, " is not ", " = ") & IF(___inv, ___dx, ___d) & UNICHAR(13) & UNICHAR(10)
)"""


def expected_caption(*dims: tuple[str, str]) -> str:
    return ("measure 'i-Applied Filters' =\n"
            + " &\n".join(BLOCK.format(c=c, label=label) for c, label in dims) + "\n")


TWO = expected_caption((STORE("Region"), "Region"), (STORE("Store Name"), "Store Name"))


# -- 22. dimension set and order --------------------------------------------------
def test_global_order_across_y_tables_and_drops(model):
    tables = _tables(model)
    (tables / "y-Selector 1.tmdl").write_text(_selector("y-Selector 1", [
        "(\"A\", NAMEOF('Stores'[A]), 5)", "(\"B\", NAMEOF(Stores[B]), 1)",
        "(\"Hidden\", NAMEOF('Stores'[H]), 2)", "(\"z\", NAMEOF('Stores'[z]), 3)",
        "(\"Blank\", NAMEOF('Stores'[My Blank Col]), 3)",
        "(\"Date\", NAMEOF('__Calendar'[Date]), -1)",
        "// (\"Old\", NAMEOF('Stores'[Old]), -5)",
        "(\"Again\", NAMEOF('Stores'[A]), 7)",
    ]), encoding="utf-8")
    (tables / "y-Plot Specific 1.tmdl").write_text(_selector("y-Plot Specific 1", [
        "(\"C\", NAMEOF('Stores'[C]), 0)", "(\"Space\", NAMEOF('__Comparison'[z_space]), 9)",
        "(\"NoOrder\", NAMEOF('Stores'[D]))",
    ]), encoding="utf-8")
    (tables / "w-Other.tmdl").write_text(_selector("w-Other", ["(\"W\", NAMEOF('Stores'[W]), -9)"]),
                                         encoding="utf-8")
    (tables / "Stores.tmdl").write_text(_table("Stores", ["A", "B", "C", "D", "H", "W", "Old"],
                                               hidden=("H",)), encoding="utf-8")
    (tables / "__Comparison.tmdl").write_text(_table("__Comparison", ["z_space"]), encoding="utf-8")
    dims, missing = i_filters.discover(model)
    assert [d.key for d in dims] == ["Stores[C]", "Stores[B]", "Stores[A]",
                                     "__Comparison[z_space]", "Stores[D]"]
    assert missing == []


def test_sort_ties_break_on_table_then_column(model):
    (_tables(model) / "y-Selector 1.tmdl").write_text(_selector("y-Selector 1", [
        "(\"S\", NAMEOF('Stores'[Store Name]), 1)", "(\"R\", NAMEOF('Stores'[Region]), 1)",
    ]), encoding="utf-8")
    assert [d.column for d in i_filters.dimensions(model)] == ["Region", "Store Name"]


# -- 23. validation gate ------------------------------------------------------------
def test_model_without_y_tables_fails_and_writes_nothing(model):
    (_tables(model) / "y-Selector 1.tmdl").unlink()
    before = tree(model)
    run = forge("i-filters", "--model", model)
    assert run.code == 1, run.text
    assert "\n❌ Validation failed. Run with --verbose for details.\n" in run.out
    assert "-> FAIL: Validation failed - see details above\n" in run.out
    assert tree(model) == before


def test_missing_column_fails_and_writes_nothing(model):
    sel = _tables(model) / "y-Selector 1.tmdl"
    sel.write_text(sel.read_text(encoding="utf-8").replace(
        "\t\t\t\t    (\"Date\"", "\t\t\t\t    (\"Gone\", NAMEOF('Stores'[Gone]), 4),\n\t\t\t\t    (\"Date\""),
        encoding="utf-8")
    before = tree(model)
    run = forge("i-filters", "--model", model)
    assert run.code == 1, run.text
    assert tree(model) == before


def test_skip_validation_leaves_a_missing_column_out(model):
    sel = _tables(model) / "y-Selector 1.tmdl"
    sel.write_text(sel.read_text(encoding="utf-8").replace(
        "\t\t\t\t    (\"Date\"", "\t\t\t\t    (\"Gone\", NAMEOF('Stores'[Gone]), 4),\n\t\t\t\t    (\"Date\""),
        encoding="utf-8")
    run = forge("i-filters", "--model", model, "--no-backups", "--skip-validation")
    assert run.code == 0, run.text
    text = _helper(model).read_text(encoding="utf-8")
    assert "Gone" not in text and "ISFILTERED('Stores'[Store Name])" in text


def test_skip_validation_with_zero_dimensions_changes_nothing(model):
    (_tables(model) / "y-Selector 1.tmdl").unlink()
    before = tree(model)
    run = forge("i-filters", "--model", model, "--skip-validation")
    assert run.code == 0, run.text
    assert tree(model) == before


def test_validator_seam_blocks_the_write(model, monkeypatch):
    monkeypatch.setattr(i_filters, "validate_caption",
                        lambda text, expected: SimpleNamespace(coverage_percent=99.0, errors=[],
                                                               warnings=[], found=1))
    before = tree(model)
    assert forge("i-filters", "--model", model).code == 1
    assert tree(model) == before


@pytest.mark.parametrize("text, expected, coverage, ok", [
    (TWO, [i_filters.Dimension("Stores", "Region"), i_filters.Dimension("Stores", "Store Name")],
     100.0, True),
    (TWO.lower().replace("isfiltered", "ISFILTERED").replace("concatenatex", "CONCATENATEX"),
     [i_filters.Dimension("Stores", "Region")], 100.0, True),
    (TWO, [i_filters.Dimension("Stores", "Region"), i_filters.Dimension("Stores", "Gone")],
     50.0, False),
    (TWO, [], 0.0, False),
    (TWO.replace("CONCATENATEX", "CONCAT"), [i_filters.Dimension("Stores", "Region")], 100.0, False),
])
def test_validation_rules(text, expected, coverage, ok):
    verdict = i_filters.validate_caption(text, expected)
    assert verdict.coverage_percent == coverage
    assert verdict.ok is ok


def test_missing_topn_is_only_a_warning():
    dims = [i_filters.Dimension("Stores", "Region")]
    verdict = i_filters.validate_caption(TWO.replace("TOPN(", "TOP("), dims)
    assert verdict.ok and verdict.warnings == ["no TOPN("]


# -- 24. generated text -------------------------------------------------------------
def test_generated_text_for_two_dimensions():
    dims = [i_filters.Dimension("Stores", "Region"), i_filters.Dimension("Stores", "Store Name")]
    assert i_filters.generate_caption(dims) == TWO


def test_labels_and_escaping():
    dims = [i_filters.Dimension("Ads", "Campaign Actual"), i_filters.Dimension("Ads", "Campaign Ad Group"),
            i_filters.Dimension("Bob's", 'Say "Hi"')]
    text = i_filters.generate_caption(dims)
    assert 'RETURN "Campaign Name" & IF(' in text and 'RETURN "Ad Group" & IF(' in text
    assert "ISFILTERED('Bob''s'[Say \"Hi\"])" in text
    assert 'RETURN "Say ""Hi""" & IF(' in text


def test_thresholds_are_configurable():
    text = i_filters.generate_caption([i_filters.Dimension("Stores", "Region")],
                                      i_filters.Options(top_n=4, invert_min_total=8,
                                                        invert_min=2, invert_max=6))
    assert "COUNTROWS(ALL('Stores'[Region])) > 8 && ___nX >= 2 && ___nX <= 6" in text
    assert "TOPN(4, ___f, 'Stores'[Region])" in text


# -- 25. writing into Helper Measures ------------------------------------------------
def _body_lines(generated: str, fenced: bool) -> list[str]:
    out = []
    for line in generated.split("\n")[1:]:
        if fenced:
            s = line.lstrip(" ")
            out.append("" if not s else ("\t\t\t" if s.startswith(") &") or s == ")" else "\t\t\t\t\t") + s)
        else:
            out.append("\t\t\t" + line if line.strip() else "")
    return out


def test_inline_form_bytes(model):
    before = _helper(model).read_text(encoding="utf-8")
    assert forge("i-filters", "--model", model, "--no-backups").code == 0
    body = "\n".join(_body_lines(TWO, fenced=False)[:-1])
    assert _helper(model).read_text(encoding="utf-8") == before.replace(
        "\tmeasure 'i-Applied Filters' = \"\"\n",
        "\tmeasure 'i-Applied Filters' =\n" + body + "\n")


def test_fenced_form_bytes(model):
    helper = _helper(model)
    fenced = helper.read_text(encoding="utf-8").replace(
        "\tmeasure 'i-Applied Filters' = \"\"\n",
        "\tmeasure 'i-Applied Filters' = ```\n\n\t\t\told line\n\t\t\t\n\t\t\t```\n")
    helper.write_text(fenced, encoding="utf-8")
    assert forge("i-filters", "--model", model, "--no-backups").code == 0
    body = "\n".join(_body_lines(TWO, fenced=True))
    assert helper.read_text(encoding="utf-8") == fenced.replace(
        "\n\t\t\told line\n\t\t\t\n", "\n" + body + "\n\t\t\t\n")
    assert "\t\t\t\t\tIF(\n\t\t\t\t\tISFILTERED('Stores'[Region]),\n" in helper.read_text(encoding="utf-8")
    assert "\t\t\t) &\n\t\t\t\t\tIF(\n" in helper.read_text(encoding="utf-8")


def test_bare_form_bytes(model):
    helper = _helper(model)
    bare = helper.read_text(encoding="utf-8").replace(
        "\tmeasure 'i-Applied Filters' = \"\"\n",
        "\tmeasure 'i-Applied Filters' =\n\t\t\tVAR x = 1\n\n\t\t\tRETURN x\n\n")
    helper.write_text(bare, encoding="utf-8")
    assert forge("i-filters", "--model", model, "--no-backups").code == 0
    body = "\n".join(_body_lines(TWO, fenced=False)[:-1])
    assert helper.read_text(encoding="utf-8") == bare.replace(
        "\tmeasure 'i-Applied Filters' =\n\t\t\tVAR x = 1\n\n\t\t\tRETURN x\n",
        "\tmeasure 'i-Applied Filters' =\n" + body + "\n")


def test_inline_single_line_result_stays_inline():
    text = "table t\n\tmeasure 'i-Applied Filters' = 1\n\t\tlineageTag: x\n"
    new, _, _ = i_filters.replace_caption(text, "i-Applied Filters", "measure 'i' =\n  BLANK()  \n")
    assert new == "table t\n\tmeasure 'i-Applied Filters' = BLANK()\n\t\tlineageTag: x\n"


def test_crlf_and_bom_are_kept(tmp_path):
    lf = copy_fixture("i_filters/Shops.SemanticModel", tmp_path / "lf")
    crlf = copy_fixture("i_filters/Shops.SemanticModel", tmp_path / "crlf")
    host = _helper(crlf)
    host.write_bytes(b"\xef\xbb\xbf" + host.read_bytes().replace(b"\n", b"\r\n"))
    assert forge("i-filters", "--model", lf, "--no-backups").code == 0
    assert forge("i-filters", "--model", crlf, "--no-backups").code == 0
    assert host.read_bytes() == b"\xef\xbb\xbf" + _helper(lf).read_bytes().replace(b"\n", b"\r\n")


# -- 26. backup and failures ---------------------------------------------------------------
def test_backup_keeps_bytes_and_time_and_unchanged_file_is_left_alone(model):
    host = _helper(model)
    original = host.read_bytes()
    os.utime(host, (1_600_000_000, 1_600_000_000))
    assert forge("i-filters", "--model", model).code == 0
    backups = list(host.parent.glob("Helper Measures.tmdl.backup_*"))
    assert len(backups) == 1
    assert re.fullmatch(r"Helper Measures\.tmdl\.backup_\d{8}_\d{6}", backups[0].name)
    assert backups[0].read_bytes() == original
    assert backups[0].stat().st_mtime == 1_600_000_000
    once = tree(model)
    run = forge("i-filters", "--model", model)
    assert run.code == 0 and "updated=0" in run.out
    assert tree(model) == once


def test_missing_host_file(model):
    _helper(model).unlink()
    run = forge("i-filters", "--model", model)
    assert run.code == 1
    assert f"-> FAIL: Helper Measures file not found: {_helper(model)}\n" in run.out


def test_missing_measure_fails_without_writing(model):
    helper = _helper(model)
    helper.write_text(helper.read_text(encoding="utf-8").replace(
        "\tmeasure 'i-Applied Filters' = \"\"\n\t\tlineageTag: i-applied-filters\n\n", ""),
        encoding="utf-8")
    before = helper.read_bytes()
    run = forge("i-filters", "--model", model, "--no-backups")
    assert run.code == 1, run.text
    assert "   dims=2 gen=1 updated=0 failed=1  -> FAIL: Failed to update: i-Applied Filters\n" in run.out
    assert helper.read_bytes() == before


# -- 27/28. console ----------------------------------------------------------------------
def test_apply_run_snapshot(model):
    run = forge("i-filters", "--model", model, "--no-backups")
    assert run.code == 0
    assert run.out == ("i-filter update — 1 target(s); mode: APPLY\n\n"
                       f"── {model}  ({model.resolve()})\n"
                       "   dims=2 gen=1 updated=1 failed=0  -> OK\n\n")
    assert run.err == ""


def test_dry_run_snapshot(model):
    before = tree(model)
    run = forge("i-filters", "--model", model, "--dry-run")
    assert run.code == 0
    assert tree(model) == before
    old = _helper(model).read_text(encoding="utf-8")
    old = old[old.index("measure 'i-Applied Filters'"):]
    new_lines, old_lines = TWO.split("\n"), old.split("\n")
    assert run.out == "\n".join([
        "i-filter update — 1 target(s); mode: DRY-RUN", "",
        f"── {model}  ({model.resolve()})", "",
        "=" * 80, "PREVIEW: Measure Updates", "=" * 80, "",
        "Measure: i-Applied Filters", "-" * 80,
        f"Original: {old.count(chr(10))} lines, {len(old)} characters",
        f"New:      {TWO.count(chr(10))} lines, {len(TWO)} characters",
        f"Change:   {TWO.count(chr(10)) - old.count(chr(10)):+d} lines, {len(TWO) - len(old):+d} characters",
        "",
        "Original (first 5 lines):", *(f"  | {ln}" for ln in old_lines[:5]),
        f"  | ... ({len(old_lines) - 10} more lines)",
        "Original (last 5 lines):", *(f"  | {ln}" for ln in old_lines[-5:]),
        "",
        "New (first 5 lines):", *(f"  | {ln}" for ln in new_lines[:5]),
        f"  | ... ({len(new_lines) - 10} more lines)",
        "New (last 5 lines):", *(f"  | {ln}" for ln in new_lines[-5:]),
        "", "=" * 80, "",
        "   dims=2 gen=1 updated=0 failed=0  -> OK", "", ""])
    assert "Original: 16 lines, 560 characters\nNew:      23 lines, 1344 characters\n" \
           "Change:   +7 lines, +784 characters\n" in run.out


def test_dry_run_with_missing_measure_is_ok(model):
    helper = _helper(model)
    helper.write_text(helper.read_text(encoding="utf-8").replace("'i-Applied Filters'", "'Other'"),
                      encoding="utf-8")
    run = forge("i-filters", "--model", model, "--dry-run")
    assert run.code == 0
    assert ("Measure: i-Applied Filters\n" + "-" * 80 + "\n❌ NOT FOUND in Helper Measures.tmdl\n\n"
            + "=" * 80 + "\n\n") in run.out


def test_missing_tables_folder_is_skipped_on_stderr(tmp_path):
    (tmp_path / "Empty.SemanticModel").mkdir()
    run = forge("i-filters", "--fleet", tmp_path)
    assert run.code == 1
    tables = tmp_path / "Empty.SemanticModel" / "definition" / "tables"
    assert run.err == f"\n[SKIP] {tmp_path}/Empty.SemanticModel: {tables} not found\n"


def _banner(title: str) -> str:
    return "\n" + "=" * 80 + "\n" + title + "\n" + "=" * 80 + "\n\n"


def test_verbose_apply_snapshot(model):
    run = forge("i-filters", "--model", model, "-v")
    assert run.code == 0
    host = _helper(model)
    backup = next(host.parent.glob("Helper Measures.tmdl.backup_*"))
    assert run.out == (
        "i-filter update — 1 target(s); mode: APPLY\n\n"
        f"── {model}  ({model.resolve()})\n"
        + _banner("STEP 1: Dimension Discovery") +
        "\n✅ Discovered 2 dimensions\n   Performance dimensions: 2\n   Growth dimensions: 0\n"
        "   Cluster dimensions: 0\n"
        + _banner("STEP 2: DAX Generation") +
        "📝 Generating the required measure\n\n✅ Generated 1 measures\n"
        "   i-Applied Filters: 23 lines, 1,344 characters\n"
        + _banner("STEP 3: Validation") +
        "\n📋 Validating: i-Applied Filters\n🔍 Validating coverage for 2 dimensions\n"
        "   Found 2 ISFILTERED checks in DAX\n🔍 Validating DAX patterns for plain_text\n"
        "✅ PASS: i-Applied Filters (100.0% coverage)\n\n✅ All validations passed\n"
        + _banner("STEP 4: Update Measures") +
        f"📖 Reading: {host}\n💾 Backup created: {backup}\n\n🔄 Updating: i-Applied Filters\n"
        "   ✅ Updated: 1 lines → 23 lines\n\n"
        f"✅ Wrote updated file: {host}\n\n✅ Successfully updated 1 measures\n"
        "   dims=2 gen=1 updated=1 failed=0  -> OK\n\n")


def test_verbose_skip_validation_and_dry_run(model):
    run = forge("i-filters", "--model", model, "-v", "--dry-run", "--skip-validation")
    assert run.code == 0
    assert "\n⏭️  Skipping validation (--skip-validation)\n" in run.out
    assert _banner("STEP 4: Preview Changes (Dry-Run)") in run.out
    assert "STEP 3" not in run.out
    assert run.out.endswith("\n✅ Dry-run completed - no changes applied\n"
                            "   dims=2 gen=1 updated=0 failed=0  -> OK\n\n")


def test_verbose_validation_failure(model):
    (_tables(model) / "y-Selector 1.tmdl").unlink()
    run = forge("i-filters", "--model", model, "-v")
    assert run.code == 1
    assert "❌ FAIL: i-Applied Filters (0.0% coverage)\n" in run.out
    assert "Run with --verbose" not in run.out


def test_growth_dimensions_are_counted(model):
    tables = _tables(model)
    (tables / "Tickets.tmdl").write_text(_table("Tickets", ["Queue"]), encoding="utf-8")
    sel = tables / "y-Selector 1.tmdl"
    sel.write_text(sel.read_text(encoding="utf-8").replace(
        "\t\t\t\t    (\"Date\"", "\t\t\t\t    (\"Queue\", NAMEOF('Tickets'[Queue]), 4),\n\t\t\t\t    (\"Date\""),
        encoding="utf-8")
    run = forge("i-filters", "--model", model, "-v", "--dry-run")
    assert "   Performance dimensions: 2\n   Growth dimensions: 1\n" in run.out


# -- 29. legacy captions ------------------------------------------------------------------
REGION = [i_filters.Dimension("Stores", "Region")]
DATE_PLAIN = """IF(
    ISFILTERED('__Calendar'[Date]),
    VAR ___dateMin = MIN('__Calendar'[Date])
    VAR ___dateMax = MAX('__Calendar'[Date])
    VAR ___dateRange = IF(___dateMin = ___dateMax, FORMAT(___dateMin, "yyyy-mm-dd"), FORMAT(___dateMin, "yyyy-mm-dd") & " to " & FORMAT(___dateMax, "yyyy-mm-dd"))
    RETURN "Date = " & ___dateRange & UNICHAR(13) & UNICHAR(10)
)"""


def test_legacy_plain_caption():
    assert i_filters.legacy_caption(REGION, "plain", name="Caption") == (
        "measure 'Caption' =\n" + DATE_PLAIN + " &\n"
        + BLOCK.format(c=STORE("Region"), label="Region") + "\n")


@pytest.mark.parametrize("colour", ["red", "green"])
def test_legacy_html_caption(colour):
    text = i_filters.legacy_caption(REGION, f"html_{colour}", name="Caption")
    assert text == (
        "measure 'Caption' =\n"
        "\"<div style='font-family: 'Segoe UI Light', 'Segoe UI', Arial;\n"
        "             font-size: 8px;\n"
        "             font-weight: 300;\n"
        "             line-height: 1.2;\n"
        f"             color: {colour};'>\" &\n"
        "IF(\n"
        "    ISFILTERED('__Calendar'[Date]),\n"
        "    VAR ___dateMin = MIN('__Calendar'[Date])\n"
        "    VAR ___dateMax = MAX('__Calendar'[Date])\n"
        '    VAR ___dateRange = IF(___dateMin = ___dateMax, FORMAT(___dateMin, "yyyy-mm-dd"), '
        'FORMAT(___dateMin, "yyyy-mm-dd") & " to " & FORMAT(___dateMax, "yyyy-mm-dd"))\n'
        "    RETURN \"<span style='font-weight: bold'>Date</span> = \" & ___dateRange & \"<br/>\"\n"
        ") &\n"
        "IF(\n"
        "    ISFILTERED('Stores'[Region]),\n"
        "    VAR ___f = FILTERS('Stores'[Region])\n"
        "    VAR ___t = TOPN(10, ___f, 'Stores'[Region])\n"
        "    VAR ___d = CONCATENATEX(___t, 'Stores'[Region], \", \")\n"
        "    RETURN \"<span style='font-weight: bold'>Region</span>\" & \" = \" & ___d & \"<br/>\"\n"
        ") &\n"
        "\"</div>\"\n")
    verdict = i_filters.validate_caption(text, REGION, kind=f"html_{colour}")
    assert verdict.ok and verdict.warnings == []


def test_legacy_count_caption():
    text = i_filters.legacy_caption(REGION, "count", name="Caption")
    assert text == (
        "measure 'Caption' =\n"
        "VAR ___totalActiveFilters =\n"
        "    IF(ISFILTERED('__Calendar'[Date]), 1, 0) +\n"
        "    IF(ISFILTERED('Stores'[Region]), 1, 0)\n"
        "\n"
        "RETURN\n"
        "IF(\n"
        "    ___totalActiveFilters > 0,\n"
        "    \"🔍 \" & ___totalActiveFilters & \" filters active\",\n"
        "    \"ℹ️ No filters applied\"\n"
        ")\n")
    assert i_filters.validate_caption(text, REGION, kind="count").ok


def test_live_caption_has_no_date_block():
    assert "__Calendar" not in i_filters.generate_caption(REGION)
    assert "__Calendar" not in i_filters.legacy_caption(REGION, "plain", date_block=False)


def test_html_validation_needs_a_style_attribute():
    text = i_filters.legacy_caption(REGION, "html_red").replace("style=", "data=")
    assert not i_filters.validate_caption(text, REGION, kind="html_red").ok
