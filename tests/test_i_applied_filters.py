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

from ported_helpers import copy_fixture, forge, tree


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
