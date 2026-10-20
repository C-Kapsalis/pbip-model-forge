"""`pbip-forge clone-report`: copy a report under a new name and identity.

The command follows the original deployment script: the target directory is
the report folder itself, the semantic model is a free string, the log
lines carry a coloured tag, and the copy keeps a `.backup` of every file it
edits.

Fixture: tests/fixtures/clone (a fictional `Cafe.Report` with logicalId
aaaaaaaa-0000-0000-0000-000000000001).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from forge_helpers import copy_fixture, forge, load, tree

TEMPLATE_ID = "aaaaaaaa-0000-0000-0000-000000000001"
NEW_ID = "bbbbbbbb-1111-2222-3333-444444444444"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    return copy_fixture("clone", tmp_path)


def _clone(ws: Path, name: str, *extra: object, target=None, model=None,
           input=None):
    args = ["clone-report", str(ws / "Cafe.Report"), name]
    if target is not None:
        args.append(str(target))
    if model is not None:
        args.append(model)
    return forge(*args, *extra, input=input)


def test_case1_clone_rebinds_and_gets_new_identity(ws):
    """The copy carries the new name and the new identity."""
    run = _clone(ws, "Roastery", "--logical-id", NEW_ID,
                 target=ws / "Roastery.Report",
                 model="Roastery.SemanticModel")
    assert run.code == 0, run.text
    new = ws / "Roastery.Report"
    platform = load(new / ".platform")
    src = load(ws / "Cafe.Report" / ".platform")
    assert platform["metadata"]["displayName"] == "Roastery"
    assert platform["config"]["logicalId"] == NEW_ID
    # every other key (and key order) unchanged
    src["metadata"]["displayName"] = "Roastery"
    src["config"]["logicalId"] = NEW_ID
    assert json.dumps(platform) == json.dumps(src)
    assert (new / ".platform").read_text(encoding="utf-8").startswith('{\n  "')

    pbir = load(new / "definition.pbir")
    assert pbir["datasetReference"]["byPath"]["path"] == \
        "../Roastery.SemanticModel"
    assert pbir["version"] == "4.0" and "$schema" in pbir

    a, b = tree(ws / "Cafe.Report"), tree(new)
    assert set(a) - {".platform", "definition.pbir"} == \
        set(b) - {".platform", "definition.pbir",
                  "definition.pbir.backup", ".platform.backup"}
    for rel in a:
        if rel not in (".platform", "definition.pbir"):
            assert a[rel] == b[rel], rel


def test_case1_random_logical_id_differs_from_template(ws):
    """The new identity is a random uuid."""
    run = _clone(ws, "Roastery", target=ws / "Roastery.Report")
    assert run.code == 0, run.text
    lid = load(ws / "Roastery.Report" / ".platform")["config"]["logicalId"]
    assert lid != TEMPLATE_ID
    assert UUID_RE.fullmatch(lid)


def test_the_semantic_model_is_a_free_string(ws):
    """No existence check: the copy points at what it is told."""
    run = _clone(ws, "Roastery", target=ws / "Roastery.Report",
                 model="Whatever.SemanticModel")
    assert run.code == 0, run.text
    pbir = load(ws / "Roastery.Report" / "definition.pbir")
    assert pbir["datasetReference"]["byPath"]["path"] == \
        "../Whatever.SemanticModel"


def test_case2_existing_target_asks_before_overwriting(ws):
    """The prompt, and 'n' changes nothing."""
    target = ws / "Roastery.Report"
    target.mkdir()
    (target / "mine.txt").write_text("keep", encoding="utf-8")
    before = tree(ws)
    run = _clone(ws, "Roastery", target=target, input="n\n")
    assert run.code == 0, run.text
    assert "Target directory already exists" in run.text
    assert tree(ws) == before


def test_case3_force_replaces_with_fresh_copy(ws):
    """`--force` answers the prompt with yes."""
    target = ws / "Roastery.Report"
    target.mkdir()
    (target / "stale.txt").write_text("old", encoding="utf-8")
    run = _clone(ws, "Roastery", "--force", "--logical-id", NEW_ID,
                 target=target)
    assert run.code == 0, run.text
    assert not (target / "stale.txt").exists()
    assert load(target / ".platform")["config"]["logicalId"] == NEW_ID


def test_case4_missing_template(ws):
    """A missing template is exit 1."""
    run = forge("clone-report", ws / "Nope.Report", "Roastery")
    assert run.code == 1, run.text
    assert "Universal template not found at" in run.text
    assert not (ws / "Roastery.Report").exists()


def test_case4_template_without_platform_is_copied_and_then_fails(ws):
    """A template without `.platform` is copied; the required-file check
    then fails with exit 1 (no traceback)."""
    (ws / "Cafe.Report" / ".platform").unlink()
    target = ws / "Roastery.Report"
    run = _clone(ws, "Roastery", target=target)
    assert run.code == 1, run.text
    assert "Missing required file: .platform" in run.text
    assert target.is_dir(), "the copy stays"


def test_case5_the_backups_stay_in_the_copy(ws):
    """Every edited file keeps a `.backup`."""
    target = ws / "Roastery.Report"
    run = _clone(ws, "Roastery", "--logical-id", NEW_ID, target=target)
    assert run.code == 0, run.text
    assert (target / "definition.pbir.backup").is_file()
    assert (target / ".platform.backup").is_file()


def test_case6_hidden_files_are_copied(ws):
    """The whole tree, hidden files included."""
    target = ws / "Roastery.Report"
    run = _clone(ws, "Roastery", "--logical-id", NEW_ID, target=target)
    assert run.code == 0, run.text
    copied = target / ".pbi" / "localSettings.json"
    assert copied.read_bytes() == \
        (ws / "Cafe.Report" / ".pbi" / "localSettings.json").read_bytes()


def test_the_target_directory_is_the_report_folder_itself(ws):
    """No `.Report` is added."""
    target = ws / "out" / "Acme"
    run = _clone(ws, "Acme", target=target)
    assert run.code == 0, run.text
    assert (target / ".platform").is_file()
    assert not (ws / "out" / "Acme.Report").exists()


def test_the_target_inside_the_template_is_refused(ws):
    """The kept BUGFIX."""
    before = tree(ws)
    for inside in (ws / "Cafe.Report", ws / "Cafe.Report" / "sub"):
        run = _clone(ws, "Inner", target=inside)
        assert run.code == 2, run.text
        assert "inside the template" in run.text
    assert tree(ws) == before
    assert not (ws / "Cafe.Report" / "sub").exists()


def test_logical_id_must_be_a_uuid(ws):
    """Exit 2 for the kept BUGFIX."""
    before = tree(ws)
    run = _clone(ws, "Bad", "--logical-id", "not-a-uuid",
                 target=ws / "Bad.Report")
    assert run.code == 2, run.text
    assert "not a UUID" in run.text
    assert tree(ws) == before


def test_the_model_option_is_the_same_as_the_argument(ws):
    """`--model` is the same as the semantic model argument."""
    target = ws / "Roastery.Report"
    run = forge("clone-report", str(ws / "Cafe.Report"), "Roastery",
                str(target), "--model", "Other.SemanticModel")
    assert run.code == 0, run.text
    pbir = load(target / "definition.pbir")
    assert pbir["datasetReference"]["byPath"]["path"] == \
        "../Other.SemanticModel"


def test_the_console_carries_the_original_s_tags(ws):
    """Every log line has a coloured tag."""
    target = ws / "Roastery.Report"
    run = _clone(ws, "Roastery", target=target)
    assert run.code == 0, run.text
    assert "\033[0;34m[INFO]\033[0m" in run.text
    assert "\033[0;32m[SUCCESS]\033[0m" in run.text
    for gone in ("cloned ", "logicalId:", "dataset:", "integrity:"):
        assert gone not in run.text, (gone, run.text)


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
