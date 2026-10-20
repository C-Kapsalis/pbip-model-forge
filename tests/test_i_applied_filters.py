"""`pbip-forge i-filters`: regenerate the `i-Applied Filters` caption measure.

Spec F-i-applied-filters-generator, fictional cases 1-5. Fixture:
tests/fixtures/i_filters/Shops.SemanticModel (fictional shop chain):
`y-Selector 1` offers Stores[Store Name] (order 2), Stores[Region] (order 1)
and __Calendar[Date] (order 3); `Helper Measures` holds a placeholder
`i-Applied Filters`.

Validator seam (proposed): the command validates through
``pbip_model_forge.i_filters.validate_caption(expression, dimensions)``,
looked up on the module at call time. It returns an object with
``coverage_percent`` (float), ``errors`` and ``warnings`` (lists); the
command treats ``coverage_percent < 100`` or any error as a failure.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from forge_helpers import copy_fixture, forge, tree


@pytest.fixture
def model(tmp_path: Path) -> Path:
    return copy_fixture("i_filters/Shops.SemanticModel", tmp_path)


def _helper(model: Path) -> Path:
    return model / "definition" / "tables" / "Helper Measures.tmdl"


def _caption(model: Path) -> str:
    text = _helper(model).read_text(encoding="utf-8")
    m = re.search(r"^\tmeasure 'i-Applied Filters' =.*?(?=^\tmeasure |^\tpartition |\Z)",
                  text, re.S | re.M)
    assert m, text
    return m.group(0)


def test_case1_two_dimensions_in_selector_order(model):
    run = forge("i-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    body = _caption(model)
    targets = re.findall(r"ISFILTERED\(\s*'?([^'\[\)]+)'?\[([^\]]+)\]\s*\)", body)
    assert targets == [("Stores", "Region"), ("Stores", "Store Name")]
    assert "CONCATENATEX" in body
    assert "TOPN" in body
    assert "(Blank)" in body
    assert '" is not "' in body and '" = "' in body
    assert body.count("measure 'i-Applied Filters'") == 1
    # the rest of the host table is untouched
    assert "measure 'Blank Measure' = BLANK()" in _helper(model).read_text(encoding="utf-8")


def test_case5_date_spine_is_excluded(model):
    run = forge("i-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert "__Calendar" not in _caption(model)


def test_case2_missing_caption_measure_fails_without_writing(model):
    helper = _helper(model)
    text = helper.read_text(encoding="utf-8")
    helper.write_text(re.sub(r"\tmeasure 'i-Applied Filters' = \"\"\n\t\tlineageTag: i-applied-filters\n\n",
                             "", text), encoding="utf-8")
    before = tree(model)
    run = forge("i-filters", "--model", model, "--no-backups")
    assert run.code == 1, run.text
    assert tree(model) == before


def test_case3_dry_run_writes_nothing(model):
    before = tree(model)
    run = forge("i-filters", "--model", model, "--dry-run")
    assert run.code == 0, run.text
    assert tree(model) == before


def test_case4_validation_failure_blocks_the_write(model, monkeypatch):
    from pbip_model_forge import i_filters

    monkeypatch.setattr(
        i_filters, "validate_caption",
        lambda expression, dimensions: SimpleNamespace(coverage_percent=99.0, errors=[], warnings=[]),
    )
    before = tree(model)
    run = forge("i-filters", "--model", model, "--no-backups")
    assert run.code == 1, run.text
    assert "validation failed" in run.text.lower()
    assert tree(model) == before

    run = forge("i-filters", "--model", model, "--no-backups", "--skip-validation")
    assert run.code == 0, run.text
    assert "ISFILTERED" in _caption(model)


def test_case4_error_severity_result_blocks_the_write(model, monkeypatch):
    from pbip_model_forge import i_filters

    monkeypatch.setattr(
        i_filters, "validate_caption",
        lambda expression, dimensions: SimpleNamespace(
            coverage_percent=100.0, errors=["ISFILTERED missing"], warnings=[]),
    )
    before = tree(model)
    run = forge("i-filters", "--model", model, "--no-backups")
    assert run.code == 1, run.text
    assert tree(model) == before


# -- review fixes ----------------------------------------------------------------
def test_crlf_host_table_stays_crlf_and_backup_is_a_byte_copy(tmp_path):
    lf = copy_fixture("i_filters/Shops.SemanticModel", tmp_path / "lf")
    crlf = copy_fixture("i_filters/Shops.SemanticModel", tmp_path / "crlf")
    host = _helper(crlf)
    original = host.read_bytes().replace(b"\n", b"\r\n")
    host.write_bytes(original)
    assert forge("i-filters", "--model", lf, "--no-backups").code == 0
    assert forge("i-filters", "--model", crlf).code == 0
    after = host.read_bytes()
    assert after.count(b"\n") == after.count(b"\r\n")
    assert after == _helper(lf).read_bytes().replace(b"\n", b"\r\n")
    backups = list(host.parent.glob("Helper Measures.tmdl.*.bak"))
    assert len(backups) == 1 and backups[0].read_bytes() == original


def test_lf_edit_changes_only_the_caption_measure(model):
    before = _helper(model).read_bytes()
    assert forge("i-filters", "--model", model, "--no-backups").code == 0
    after = _helper(model).read_bytes()
    head = b"\tmeasure 'i-Applied Filters' = "
    tail = b"\t\tlineageTag: i-applied-filters\n"
    assert after[:after.index(head)] == before[:before.index(head)]
    assert after[after.index(tail):] == before[before.index(tail):]


def test_second_run_is_a_no_op(model):
    assert forge("i-filters", "--model", model, "--no-backups").code == 0
    once = tree(model)
    run = forge("i-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert "updated: 0" in run.out and "no change" in run.out
    assert tree(model) == once


def test_invert_thresholds_are_written_and_configurable():
    from pbip_model_forge import i_filters
    dim = i_filters.Dimension("Stores", "Region")
    default = i_filters.generate_expression([dim])
    assert "COUNTROWS(ALL('Stores'[Region])) > 5 && __exclCount >= 1 && __exclCount <= 3" in default
    assert "TOPN(10, __sel," in default
    custom = i_filters.generate_expression(
        [dim], i_filters.Options(top_n=4, invert_min_total=8, invert_min=2, invert_max=6))
    assert "COUNTROWS(ALL('Stores'[Region])) > 8 && __exclCount >= 2 && __exclCount <= 6" in custom
    assert "TOPN(4, __sel," in custom


def test_label_map_and_cluster_dimension_pass_the_real_validator():
    from pbip_model_forge import i_filters
    campaign = i_filters.Dimension("Campaigns", "Campaign Actual")
    cluster = i_filters.Dimension("Stores", "Store Cluster", cluster=True)
    expr = i_filters.generate_expression([campaign, cluster])
    assert '"Campaign Name" & IF(__invert' in expr
    assert "[-Store Cluster Name] & IF(__invert" in expr
    assert 'IF(ISBLANK([-Store Cluster Name]), "(Blank)", [-Store Cluster Name])' in expr
    verdict = i_filters.validate_caption(expr, [campaign, cluster])
    assert verdict.ok and verdict.coverage_percent == 100.0 and verdict.errors == []
    labelled = i_filters.generate_expression(
        [campaign], i_filters.Options(labels={"Campaign Actual": 'The "Campaign"'}))
    assert '"The ""Campaign""" & IF(__invert' in labelled


def test_real_validator_reports_missing_coverage_and_cluster_measure():
    from pbip_model_forge import i_filters
    campaign = i_filters.Dimension("Campaigns", "Campaign Actual")
    cluster = i_filters.Dimension("Stores", "Store Cluster", cluster=True)
    verdict = i_filters.validate_caption(i_filters.generate_expression([campaign]),
                                         [campaign, cluster])
    assert not verdict.ok and verdict.coverage_percent == 50.0
    assert verdict.errors == [
        "cluster name measure [-Store Cluster Name] not referenced",
        "coverage 50.0%: no ISFILTERED for Stores[Store Cluster]",
    ]


def test_cli_with_a_cluster_column_uses_the_real_validator(model):
    stores = model / "definition" / "tables" / "Stores.tmdl"
    stores.write_text(stores.read_text(encoding="utf-8").replace(
        "\tcolumn 'Store Id'",
        "\tcolumn 'Store Cluster'\n\t\tdataType: string\n\t\tlineageTag: stores-cluster\n"
        "\t\tsummarizeBy: none\n\t\tsourceColumn: Store Cluster\n\n\tcolumn 'Store Id'"), encoding="utf-8")
    sel = model / "definition" / "tables" / "y-Selector 1.tmdl"
    sel.write_text(sel.read_text(encoding="utf-8").replace(
        '("Region", NAMEOF(\'Stores\'[Region]), 1),',
        '("Region", NAMEOF(\'Stores\'[Region]), 1),\n\t\t\t\t    ("Cluster", NAMEOF(\'Stores\'[Store Cluster]), 4),'),
        encoding="utf-8")
    run = forge("i-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert "dimensions: 3" in run.out
    assert "[-Store Cluster Name]" in _caption(model)


def test_date_block_wording():
    from pbip_model_forge import i_filters
    expr = i_filters.generate_expression([], i_filters.Options(date_column="'__Calendar'[Date]"))
    assert '"Period: " & IF(__first = __last, FORMAT(__first, "d mmm yyyy"), ' \
           'FORMAT(__first, "d mmm yyyy") & " - " & FORMAT(__last, "d mmm yyyy"))' in expr
