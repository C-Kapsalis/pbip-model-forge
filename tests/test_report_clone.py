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
