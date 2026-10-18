"""`pbip-forge clone-report`: copy a finished report for another model.

Spec H-report-clone-from-template, cases 1-6. Fixture: tests/fixtures/clone
(fictional `Cafe.Report` with logicalId aaaaaaaa-0000-0000-0000-000000000001,
plus `Cafe.SemanticModel` and `Roastery.SemanticModel` siblings).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ported_helpers import copy_fixture, forge, load, tree

TEMPLATE_ID = "aaaaaaaa-0000-0000-0000-000000000001"
NEW_ID = "bbbbbbbb-1111-2222-3333-444444444444"


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    return copy_fixture("clone", tmp_path)


def test_case1_clone_rebinds_and_gets_new_identity(ws):
    tpl = ws / "Cafe.Report"
    run = forge("clone-report", tpl, "Roastery", "--model", ws / "Roastery.SemanticModel",
                "--logical-id", NEW_ID)
    assert run.code == 0, run.text
    new = ws / "Roastery.Report"
    platform = load(new / ".platform")
    src = load(tpl / ".platform")
    assert platform["metadata"]["displayName"] == "Roastery"
    assert platform["config"]["logicalId"] == NEW_ID
    # every other key (and key order) unchanged
    src["metadata"]["displayName"] = "Roastery"
    src["config"]["logicalId"] = NEW_ID
    assert json.dumps(platform) == json.dumps(src)
    assert (new / ".platform").read_text(encoding="utf-8").startswith('{\n  "')

    pbir = load(new / "definition.pbir")
    assert pbir["datasetReference"]["byPath"]["path"] == "../Roastery.SemanticModel"
    assert pbir["version"] == "4.0" and "$schema" in pbir

    a, b = tree(tpl), tree(new)
    assert set(a) == set(b)
    for rel in a:
        if rel not in (".platform", "definition.pbir"):
            assert a[rel] == b[rel], rel
    assert NEW_ID in run.out and "../Roastery.SemanticModel" in run.out


def test_case1_random_logical_id_differs_from_template(ws):
    run = forge("clone-report", ws / "Cafe.Report", "Roastery", "--model", ws / "Roastery.SemanticModel")
    assert run.code == 0, run.text
    lid = load(ws / "Roastery.Report" / ".platform")["config"]["logicalId"]
    assert lid != TEMPLATE_ID
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", lid)


def test_without_model_the_dataset_reference_is_kept(ws, tmp_path):
    out = tmp_path / "elsewhere"
    out.mkdir()
    run = forge("clone-report", ws / "Cafe.Report", "Cafe Copy", "--out-dir", out, "--logical-id", NEW_ID)
    assert run.code == 0, run.text
    new = out / "Cafe Copy.Report"
    assert (new / "definition.pbir").read_bytes() == (ws / "Cafe.Report" / "definition.pbir").read_bytes()


def test_case2_existing_target_without_force_is_untouched(ws):
    target = ws / "Roastery.Report"
    target.mkdir()
    (target / "mine.txt").write_text("keep", encoding="utf-8")
    before = tree(ws)
    run = forge("clone-report", ws / "Cafe.Report", "Roastery", "--logical-id", NEW_ID)
    assert run.code == 1, run.text
    assert tree(ws) == before


def test_case3_force_replaces_with_fresh_copy(ws):
    target = ws / "Roastery.Report"
    target.mkdir()
    (target / "stale.txt").write_text("old", encoding="utf-8")
    run = forge("clone-report", ws / "Cafe.Report", "Roastery", "--force", "--logical-id", NEW_ID)
    assert run.code == 0, run.text
    assert not (target / "stale.txt").exists()
    assert load(target / ".platform")["config"]["logicalId"] == NEW_ID


def test_case4_template_without_platform(ws):
    (ws / "Cafe.Report" / ".platform").unlink()
    before = tree(ws)
    run = forge("clone-report", ws / "Cafe.Report", "Roastery")
    assert run.code == 2, run.text
    assert "template has no .platform" in run.text
    assert tree(ws) == before


def test_case4_missing_template(ws):
    run = forge("clone-report", ws / "Nope.Report", "Roastery")
    assert run.code == 2, run.text
    assert "Nope.Report" in run.text
    assert not (ws / "Roastery.Report").exists()


def test_case5_no_backup_files(ws):
    assert forge("clone-report", ws / "Cafe.Report", "Roastery", "--logical-id", NEW_ID).code == 0
    leftovers = [p for p in ws.rglob("*") if p.suffix in (".bak", ".backup")]
    assert leftovers == []


def test_case6_hidden_files_are_copied(ws):
    assert forge("clone-report", ws / "Cafe.Report", "Roastery", "--logical-id", NEW_ID).code == 0
    copied = ws / "Roastery.Report" / ".pbi" / "localSettings.json"
    assert copied.read_bytes() == (ws / "Cafe.Report" / ".pbi" / "localSettings.json").read_bytes()


# -- review fixes ----------------------------------------------------------------
def test_relative_model_is_read_from_the_new_report_folder(ws, tmp_path, monkeypatch):
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    run = forge("clone-report", ws / "Cafe.Report", "Roastery", "--model", "../Roastery.SemanticModel",
                "--logical-id", NEW_ID)
    assert run.code == 0, run.text
    pbir = load(ws / "Roastery.Report" / "definition.pbir")
    assert pbir["datasetReference"]["byPath"]["path"] == "../Roastery.SemanticModel"
    assert "integrity: ok" in run.out


@pytest.mark.parametrize("model", ["Roastery.SemanticModel", "../Nope.SemanticModel", "../Cafe.Report"])
def test_model_that_is_not_an_existing_semantic_model_is_refused(ws, model):
    before = tree(ws)
    run = forge("clone-report", ws / "Cafe.Report", "Roastery", "--model", model, "--logical-id", NEW_ID)
    assert run.code == 2, run.text
    assert "does not point to an existing *.SemanticModel folder" in run.out
    assert tree(ws) == before


def test_absolute_missing_model_is_refused(ws):
    run = forge("clone-report", ws / "Cafe.Report", "X", "--model", ws / "Nope.SemanticModel", "--strict")
    assert run.code == 2, run.text
    assert not (ws / "X.Report").exists()


def test_strict_turns_integrity_problems_into_exit_1(ws):
    pages = ws / "Cafe.Report" / "definition" / "pages" / "pages.json"
    meta = load(pages)
    meta["pageOrder"].append("deadbeefdeadbeefdead")
    pages.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    run = forge("clone-report", ws / "Cafe.Report", "Loose", "--logical-id", NEW_ID)
    assert run.code == 0, run.text
    assert "integrity: page deadbeefdeadbeefdead in pages.json has no page.json" in run.out
    run = forge("clone-report", ws / "Cafe.Report", "Tight", "--logical-id", NEW_ID, "--strict")
    assert run.code == 1, run.text
    assert (ws / "Tight.Report" / ".platform").is_file()


def test_out_dir_inside_the_template_is_refused(ws):
    before = tree(ws)
    for out in (ws / "Cafe.Report", ws / "Cafe.Report" / "sub"):
        run = forge("clone-report", ws / "Cafe.Report", "Inner", "--out-dir", out)
        assert run.code == 2, run.text
        assert "inside the template" in run.out
    assert tree(ws) == before
    assert not (ws / "Cafe.Report" / "sub").exists()


def test_force_onto_a_plain_file_is_a_clean_error(ws):
    (ws / "Z.Report").write_text("x", encoding="utf-8")
    run = forge("clone-report", ws / "Cafe.Report", "Z", "--force")
    assert run.code == 1, run.text
    assert "is not a folder" in run.out
    assert (ws / "Z.Report").read_text(encoding="utf-8") == "x"


def test_logical_id_must_be_a_uuid(ws):
    before = tree(ws)
    run = forge("clone-report", ws / "Cafe.Report", "Bad", "--logical-id", "not-a-uuid")
    assert run.code == 2, run.text
    assert "not a UUID" in run.out
    assert tree(ws) == before


def test_preflight_absent_adds_no_findings(ws, monkeypatch):
    from pbip_model_forge import report_scaffold
    monkeypatch.setattr(report_scaffold.importlib.util, "find_spec", lambda name: None)
    assert report_scaffold.preflight_report_findings(ws / "Cafe.Report") == []


def test_preflight_findings_are_attributed_by_exact_folder(ws, monkeypatch):
    from pbip_model_forge import report_scaffold
    found = [
        {"rule": "B004", "message": "sibling broken", "file": str(ws / "MyShop.Report" / "x.json"),
         "path": "MyShop.Report/x.json"},
        {"rule": "B004", "message": "clone broken", "file": str(ws / "Shop.Report" / "x.json"),
         "path": "Shop.Report/x.json"},
        {"rule": "B004", "message": "by path only", "path": "Shop.Report/y.json"},
        {"rule": "B004", "message": "path only, sibling", "path": "MyShop.Report/y.json"},
    ]

    class Proc:
        returncode, stdout = 1, json.dumps({"violations": found})

    monkeypatch.setattr(report_scaffold.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(report_scaffold.subprocess, "run", lambda *a, **k: Proc())
    assert report_scaffold.preflight_report_findings(ws / "Shop.Report") == [
        "tmdl-preflight B004: clone broken", "tmdl-preflight B004: by path only"]


def test_broken_sibling_does_not_fail_a_clean_clone_with_preflight(ws):
    pytest.importorskip("tmdl_preflight")
    import shutil
    sib = ws / "MyShop.Report"
    shutil.copytree(ws / "Cafe.Report", sib)
    shutil.rmtree(sib / "definition" / "pages" / "c0ffee00c0ffee00c0ff")
    run = forge("clone-report", ws / "Cafe.Report", "Shop", "--model", "../Cafe.SemanticModel",
                "--logical-id", NEW_ID, "--strict")
    assert run.code == 0, run.text
    assert "integrity: ok" in run.out


def test_preflight_reports_a_broken_clone(ws):
    pytest.importorskip("tmdl_preflight")
    import shutil
    shutil.rmtree(ws / "Cafe.Report" / "definition" / "pages" / "c0ffee00c0ffee00c0ff")
    run = forge("clone-report", ws / "Cafe.Report", "Shop", "--logical-id", NEW_ID, "--strict")
    assert run.code == 1, run.text
    assert "tmdl-preflight B004:" in run.out
