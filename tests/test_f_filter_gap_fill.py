"""`pbip-forge f-filters`: gap-fill f-<Category> measures and f-All gates.

Spec F-f-filter-gap-fill, fictional cases 1-7 plus the create path of the
Fix section. Fixture: tests/fixtures/f_filters/Roastery.SemanticModel
(fictional coffee roastery):

* facts `Store Sales` (read by `Store Revenue`, group store_m) and
  `Web Sales` (read by `Web Revenue`, group web_m);
* z-Map rows: Spend <- store_m, Spend <- web_m,
  Email Marketing Campaigns <- email_m;
* f-Filters: `f-All` with paired temp_basic / temp_alt chains gating only
  the literal "Email Marketing", a fenced `f-Spend` reading Store Sales, and
  `f-Email_Marketing`.

So `Web Sales` is uncovered (category Spend -> extend f-Spend) and the z-Map
category Spend is not yet gated in f-All.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ported_helpers import copy_fixture, forge, lazy_module, tree

#: shared gap-fill library (proposed module), imported lazily so a missing
#: module fails each test that uses it instead of the whole file.
f_filters = lazy_module("pbip_model_forge.f_filters")

BASIC_SPEND = '&& IF(CONTAINSSTRING(all_cats, "Spend"), IF([f-Spend] > 0, TRUE(), FALSE()), TRUE())'
ALT_SPEND = '|| IF(CONTAINSSTRING(all_cats, "Spend"), IF([f-Spend] > 0, TRUE(), FALSE()), FALSE())'


@pytest.fixture
def model(tmp_path: Path) -> Path:
    return copy_fixture("f_filters/Roastery.SemanticModel", tmp_path)


def _ff(model: Path) -> Path:
    return model / "definition" / "tables" / "f-Filters.tmdl"


def _chain(text: str, var: str) -> str:
    """Lines of one VAR chain of f-All (from `VAR <var>` to the next VAR/RETURN)."""
    m = re.search(rf"VAR {var} =.*?(?=\n\s*(?:VAR |RETURN))", text, re.S)
    assert m, f"no {var} chain"
    return m.group(0)


def _measure(text: str, name: str) -> str:
    m = re.search(rf"^\tmeasure '{re.escape(name)}' =.*?(?=^\t(?:measure|partition|annotation|column) |\Z)",
                  text, re.S | re.M)
    assert m, f"measure {name} not found"
    return m.group(0)


# -- case 1 ----------------------------------------------------------------------
def test_case1_substring_literal_gates_category_and_spend_gets_paired_lines(model):
    before = _ff(model).read_text(encoding="utf-8")
    literals = f_filters.gate_literals(before)
    assert set(literals) == {"Email Marketing"}
    assert f_filters.category_gated("Email Marketing Campaigns", literals)
    assert not f_filters.category_gated("Spend", literals)

    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    after = _ff(model).read_text(encoding="utf-8")
    basic, alt = _chain(after, "temp_basic"), _chain(after, "temp_alt")
    assert basic.count(BASIC_SPEND) == 1
    assert alt.count(ALT_SPEND) == 1
    assert ALT_SPEND not in basic and BASIC_SPEND not in alt
    # the already-gated category gets no new line, existing lines untouched
    assert after.count('CONTAINSSTRING(all_cats, "Email Marketing")') == 2
    for line in before.splitlines():
        if "CONTAINSSTRING" in line:
            assert line in after.splitlines()


def test_case1_zmap_categories_are_decoded(model):
    assert sorted(f_filters.zmap_categories(model)) == ["Email Marketing Campaigns", "Spend"]


def test_zmap_decode_failure_skips_enforcement(model):
    zmap = model / "definition" / "tables" / "z-Map Dimension-Measure Groupings.tmdl"
    text = zmap.read_text(encoding="utf-8")
    zmap.write_text(re.sub(r'FromText\("[^"]+"', 'FromText("@@not-base64@@"', text), encoding="utf-8")
    assert f_filters.zmap_categories(model) == []


# -- case 2 ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "declared, expected",
    [
        ({"f-Loyalty Cohort", "f-Loyalty_Cohort", "f-LoyaltyCohort"}, "f-Loyalty Cohort"),
        ({"f-Loyalty_Cohort"}, "f-Loyalty_Cohort"),
        ({"f-LoyaltyCohort"}, "f-LoyaltyCohort"),
        ({"f-Loyalty_Cohort", "f-LoyaltyCohort"}, "f-Loyalty_Cohort"),
    ],
)
def test_case2_f_measure_resolution_order(declared, expected):
    assert f_filters.resolve_f_measure("Loyalty Cohort", declared) == expected


def test_declared_measures_reads_all_quoting_styles():
    text = ("table 'f-Filters'\n\tmeasure 'f-Spend' = 1\n\tmeasure \"f-Email\" = 1\n"
            "\tmeasure f-Web = 1\n")
    assert f_filters.declared_measures(text) == {"f-Spend", "f-Email", "f-Web"}


# -- case 3 ----------------------------------------------------------------------
def test_case3_category_without_measure_is_unresolved_and_never_gated(model):
    assert f_filters.resolve_f_measure("Gift Cards", {"f-Spend"}) is None
    zmap = model / "definition" / "tables" / "z-Map Dimension-Measure Groupings.tmdl"
    from ported_helpers import raw_deflate_b64
    import json
    rows = [["Spend", "", "store_m"], ["Spend", "", "web_m"],
            ["Email Marketing Campaigns", "", "email_m"], ["Gift Cards", "", "gift_m"]]
    b64 = raw_deflate_b64(json.dumps(rows, separators=(",", ":")).encode())
    text = zmap.read_text(encoding="utf-8")
    zmap.write_text(re.sub(r'FromText\("[^"]+"', f'FromText("{b64}"', text), encoding="utf-8")

    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert "Gift Cards" in run.text            # listed as unresolved
    assert "unresolved" in run.text.lower()
    assert "Gift Cards" not in _ff(model).read_text(encoding="utf-8")


# -- case 4 ----------------------------------------------------------------------
@pytest.mark.parametrize("marker", ["//", "--"])
def test_case4_commented_gate_line_contributes_no_literal(model, marker):
    ff = _ff(model)
    text = ff.read_text(encoding="utf-8")
    commented = f'\t\t\t    {marker} && IF(CONTAINSSTRING(all_cats, "Spend"), IF([f-Spend] > 0, TRUE(), FALSE()), TRUE())\n'
    text = text.replace("\t\t\tVAR temp_alt", commented + "\t\t\tVAR temp_alt", 1)
    ff.write_text(text, encoding="utf-8")
    assert "Spend" not in set(f_filters.gate_literals(text))

    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    basic = _chain(ff.read_text(encoding="utf-8"), "temp_basic")
    active = [ln for ln in basic.splitlines() if ln.strip().startswith("&&")]
    assert sum(BASIC_SPEND in ln for ln in active) == 1
    assert commented.rstrip("\n") in ff.read_text(encoding="utf-8")  # never edited


# -- case 5 ----------------------------------------------------------------------
def test_case5_extend_fenced_measure_inside_fence_with_loud_warning(model):
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    spend = _measure(_ff(model).read_text(encoding="utf-8"), "f-Spend")
    fence = re.search(r"```(.*?)```", spend, re.S)
    assert fence, spend
    body = fence.group(1)
    assert "int(not ISEMPTY('Store Sales')) + int(not ISEMPTY('Web Sales'))" in body
    assert spend.count("ISEMPTY('Web Sales')") == 1
    for stream in (run.out, run.err):
        assert "non-standard" in stream.lower(), stream


# -- create path (Fix section; acceptance stand-in of the preflight test) ----------
def test_create_missing_category_measure(model):
    ff = _ff(model)
    text = ff.read_text(encoding="utf-8")
    text = re.sub(r"\tmeasure 'f-Spend' = ```.*?lineageTag: f-spend\n\n", "", text, flags=re.S)
    ff.write_text(text, encoding="utf-8")

    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    after = ff.read_text(encoding="utf-8")
    spend = _measure(after, "f-Spend")
    assert "int(not ISEMPTY('Store Sales'))" in spend
    assert "int(not ISEMPTY('Web Sales'))" in spend
    assert re.search(r"^\t\tisHidden$", spend, re.M)
    assert "displayFolder: Visual-Level filters" in spend
    assert "lineageTag:" in spend
    # inserted before the table's trailing annotations
    assert after.index("measure 'f-Spend'") < after.index("annotation PBI_ResultType")
    # created and resolvable -> gated in both chains
    assert _chain(after, "temp_basic").count(BASIC_SPEND) == 1
    assert _chain(after, "temp_alt").count(ALT_SPEND) == 1


# -- case 6 ----------------------------------------------------------------------
def test_case6_model_without_f_filters_is_an_error(model):
    _ff(model).unlink()
    before = tree(model)
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 1, run.text
    assert tree(model) == before


# -- case 7 ----------------------------------------------------------------------
def test_case7_dry_run_writes_nothing_and_second_run_is_a_no_op(model):
    before = tree(model)
    dry = forge("f-filters", "--model", model, "--dry-run")
    assert dry.code == 0, dry.text
    assert "f-Spend" in dry.text
    assert tree(model) == before

    first = forge("f-filters", "--model", model, "--no-backups")
    assert first.code == 0, first.text
    once = tree(model)
    assert once != before
    second = forge("f-filters", "--model", model, "--no-backups")
    assert second.code == 0, second.text
    assert tree(model) == once


def test_no_backups_adds_no_files(model):
    names = set(tree(model))
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert set(tree(model)) == names


def test_default_run_keeps_a_backup_of_f_filters(model):
    names = set(tree(model))
    assert forge("f-filters", "--model", model).code == 0
    added = set(tree(model)) - names
    assert len(added) == 1 and "f-Filters" in next(iter(added))
