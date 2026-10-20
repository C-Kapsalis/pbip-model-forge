"""`pbip-forge clone-report`: the original deployment script's behaviour.

The original is a shell script (`deploy-universal-template.sh`) with a fixed
sequence of coloured log lines, a prompt when the target exists, and a
validation block. This test pins the console output, the exit codes and the
files the copy keeps.

What the original does that the tool did not:
- the target directory is the report folder itself, used exactly as given;
- the semantic model is a free string, with no existence check;
- the log lines carry a coloured tag;
- the required-file check names the file and stops at once;
- the copies keep a `.backup` of every file it edits.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from forge_helpers import forge, load, tree

BLUE = "\033[0;34m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@pytest.fixture
def template(tmp_path: Path) -> Path:
    """A minimal report folder with the four required files."""
    rep = tmp_path / "Shop.Report"
    (rep / "definition" / "pages").mkdir(parents=True)
    (rep / "definition" / "bookmarks").mkdir(parents=True)
    (rep / "StaticResources" / "RegisteredResources").mkdir(parents=True)
    (rep / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                   "gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": "Shop"},
        "config": {"version": "2.0", "logicalId": str(_uuid())},
    }, indent=2), encoding="utf-8")
    (rep / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                   "item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": "../Shop.SemanticModel"}},
    }, indent=2), encoding="utf-8")
    (rep / "definition" / "report.json").write_text(
        json.dumps({"$schema": "x"}, indent=2), encoding="utf-8")
    (rep / "definition" / "version.json").write_text(
        json.dumps({"$schema": "x", "version": "2.0.0"}, indent=2),
        encoding="utf-8")
    (rep / ".hidden").write_text("kept", encoding="utf-8")
    return rep


def _uuid() -> str:
    import uuid
    return str(uuid.uuid4())


def _clone(template: Path, *extra: object, name="Acme-Analytics",
           target=None, input=None):
    args = ["clone-report", str(template)]
    if name is not None:
        args.append(name)
    if target is not None:
        args.append(str(target))
    return forge(*args, *extra, input=input)


# ── item 35: the command shape ────────────────────────────────────────────

def test_the_target_directory_is_used_exactly_as_given(template, tmp_path):
    """Item 35: no `.Report` is added."""
    target = tmp_path / "out" / "Acme"
    run = _clone(template, target=target)
    assert run.code == 0, run.text
    assert target.is_dir(), run.text
    assert not (target.parent / "Acme.Report").exists()


def test_the_semantic_model_defaults_to_the_name(template, tmp_path):
    """Item 35: `<NAME>.SemanticModel`."""
    target = tmp_path / "out"
    run = _clone(template, target=target)
    assert run.code == 0, run.text
    pbir = load(target / "definition.pbir")
    assert pbir["datasetReference"]["byPath"]["path"] == \
        "../Acme-Analytics.SemanticModel"


def test_the_semantic_model_is_a_free_string(template, tmp_path):
    """Item 35: no existence check."""
    target = tmp_path / "out"
    run = forge("clone-report", str(template), "Acme", str(target),
                "Whatever.SemanticModel")
    assert run.code == 0, run.text
    pbir = load(target / "definition.pbir")
    assert pbir["datasetReference"]["byPath"]["path"] == \
        "../Whatever.SemanticModel"


def test_model_is_accepted_as_the_same(template, tmp_path):
    """Item 35: `--model` is the same as the positional argument."""
    target = tmp_path / "out"
    run = forge("clone-report", str(template), "Acme", str(target),
                "--model", "Other.SemanticModel")
    assert run.code == 0, run.text
    pbir = load(target / "definition.pbir")
    assert pbir["datasetReference"]["byPath"]["path"] == \
        "../Other.SemanticModel"


def test_a_target_inside_the_template_is_refused(template):
    """Item 35: the kept BUGFIX."""
    inside = template / "inside"
    run = _clone(template, target=inside)
    assert run.code == 2, run.text
    assert not inside.exists()


# ── item 36: the steps and their lines ───────────────────────────────────

def test_the_configuration_block(template, tmp_path):
    """Item 36: the configuration lines."""
    target = tmp_path / "out"
    run = _clone(template, target=target)
    assert run.code == 0, run.text
    assert f"{BLUE}[INFO]{NC} Configuration:" in run.text, run.text
    assert f"{BLUE}[INFO]{NC}   Deployment Name: Acme-Analytics" in run.text, \
        run.text
    assert f"{BLUE}[INFO]{NC}   Target Directory: {target}" in run.text, \
        run.text
    assert f"{BLUE}[INFO]{NC}   Semantic Model: Acme-Analytics.SemanticModel" \
        in run.text, run.text
    assert f"{BLUE}[INFO]{NC}   Template Source: {template}" in run.text, \
        run.text


def test_the_prerequisites_and_the_deployment(template, tmp_path):
    """Item 36: the step lines, in order."""
    target = tmp_path / "out"
    run = _clone(template, target=target)
    assert run.code == 0, run.text
    for needle in (f"{BLUE}[INFO]{NC} Validating prerequisites...",
                   f"{GREEN}[SUCCESS]{NC} Prerequisites validated",
                   f"{BLUE}[INFO]{NC} Deploying universal M Template...",
                   f"{BLUE}[INFO]{NC} Updating semantic model reference to: "
                   "Acme-Analytics.SemanticModel",
                   f"{GREEN}[SUCCESS]{NC} Updated semantic model reference",
                   f"{BLUE}[INFO]{NC} Generating unique logical ID...",
                   f"{GREEN}[SUCCESS]{NC} Universal M Template deployed "
                   "successfully!",
                   f"{BLUE}[INFO]{NC} Validating deployment...",
                   f"{GREEN}[SUCCESS]{NC} Deployment validation completed!",
                   f"{GREEN}[SUCCESS]{NC} Universal M Template deployment "
                   "completed successfully!"):
        assert needle in run.text, (needle, run.text)


def test_the_logical_id_is_a_new_lowercase_uuid(template, tmp_path):
    """Item 36: a new uuid, and the display name becomes NAME."""
    target = tmp_path / "out"
    run = _clone(template, target=target)
    assert run.code == 0, run.text
    platform = load(target / ".platform")
    new_id = platform["config"]["logicalId"]
    assert UUID.match(new_id), new_id
    assert platform["metadata"]["displayName"] == "Acme-Analytics"
    assert f"Generated unique logical ID: {new_id}" in run.text, run.text


def test_logical_id_can_be_given(template, tmp_path):
    """Item 36: `--logical-id` is used as given."""
    target = tmp_path / "out"
    given = "12345678-1234-1234-1234-123456789abc"
    run = _clone(template, "--logical-id", given, target=target)
    assert run.code == 0, run.text
    assert load(target / ".platform")["config"]["logicalId"] == given


def test_a_bad_logical_id_is_refused(template, tmp_path):
    """Item 37: exit 2 for the kept BUGFIX."""
    target = tmp_path / "out"
    run = _clone(template, "--logical-id", "not-a-uuid", target=target)
    assert run.code == 2, run.text
    assert not target.exists()


def test_the_backups_stay_in_the_copy(template, tmp_path):
    """Item 36: every edited file keeps a `.backup`."""
    target = tmp_path / "out"
    run = _clone(template, target=target)
    assert run.code == 0, run.text
    assert (target / "definition.pbir.backup").is_file()
    assert (target / ".platform.backup").is_file()


def test_the_hidden_files_are_copied(template, tmp_path):
    """Item 36: the whole tree, hidden files included."""
    target = tmp_path / "out"
    run = _clone(template, target=target)
    assert run.code == 0, run.text
    assert (target / ".hidden").read_text(encoding="utf-8") == "kept"


def test_the_required_files_are_checked_in_order(template, tmp_path):
    """Item 36: the four required files, in order."""
    target = tmp_path / "out"
    run = _clone(template, target=target)
    assert run.code == 0, run.text
    for name in ("definition.pbir", ".platform", "definition/report.json",
                 "definition/version.json"):
        assert f"Required file exists: {name}" in run.text, (name, run.text)


def test_a_missing_required_file_fails_at_once(template, tmp_path):
    """Item 36: exit 1, and the copy stays."""
    (template / "definition" / "version.json").unlink()
    target = tmp_path / "out"
    run = _clone(template, target=target)
    assert run.code == 1, run.text
    assert f"{RED}[ERROR]{NC} Missing required file: definition/version.json" \
        in run.text, run.text
    assert target.is_dir(), "the copy must stay"


def test_a_missing_template_fails(template, tmp_path):
    """Item 36: exit 1."""
    run = forge("clone-report", str(tmp_path / "nowhere"), "Acme")
    assert run.code == 1, run.text
    assert "Universal template not found at:" in run.text, run.text


def test_the_old_lines_are_gone(template, tmp_path):
    """Item 36: the tool's own lines are removed."""
    target = tmp_path / "out"
    run = _clone(template, target=target)
    for gone in ("cloned ", "logicalId:", "dataset:", "integrity:"):
        assert gone not in run.text, (gone, run.text)


# ── item 36: the overwrite prompt ─────────────────────────────────────────

def test_an_existing_target_asks_before_overwriting(template, tmp_path):
    """Item 36: the prompt, and 'n' changes nothing."""
    target = tmp_path / "out"
    target.mkdir()
    (target / "keep.txt").write_text("hand made", encoding="utf-8")
    before = tree(target)

    run = _clone(template, target=target, input="n\n")
    assert run.code == 0, run.text
    assert "Target directory already exists:" in run.text, run.text
    assert "Continue and overwrite? (y/N): " in run.text, run.text
    assert "Deployment cancelled." in run.text, run.text
    assert tree(target) == before, "the target was changed"


def test_force_overwrites_without_asking(template, tmp_path):
    """Item 36: `--force` answers the prompt with yes."""
    target = tmp_path / "out"
    target.mkdir()
    (target / "stale.txt").write_text("old", encoding="utf-8")

    run = _clone(template, "--force", target=target)
    assert run.code == 0, run.text
    assert not (target / "stale.txt").exists()
    assert (target / ".platform").is_file()


# ── item 38: the template-specific checks ─────────────────────────────────

def test_the_visual_count_is_checked_when_asked(template, tmp_path):
    """Item 38: `--expect-visuals` counts the visual files."""
    visuals = target = tmp_path / "out"
    for name in ("v1", "v2"):
        d = template / "definition" / "pages" / "main_page" / "visuals" / name
        d.mkdir(parents=True)
        (d / "visual.json").write_text("{}", encoding="utf-8")

    run = _clone(template, "--expect-visuals", "2", target=target)
    assert run.code == 0, run.text
    assert "Visual count validated: 2 components (streamlined architecture)" \
        in run.text, run.text


def test_a_wrong_visual_count_is_a_warning(template, tmp_path):
    """Item 38: a warning only."""
    target = tmp_path / "out"
    run = _clone(template, "--expect-visuals", "27", target=target)
    assert run.code == 0, run.text
    assert "Visual count: 0 (expected: 27)" in run.text, run.text


def test_a_missing_bookmark_fails(template, tmp_path):
    """Item 38: a missing bookmark ends the run with exit 1."""
    target = tmp_path / "out"
    run = _clone(template, "--expect-bookmark", "b1", target=target)
    assert run.code == 1, run.text
    assert "definition/bookmarks/b1.bookmark.json: MISSING" in run.text, \
        run.text
    assert "VALIDATION FAILED" in run.text, run.text


def test_an_existing_bookmark_passes(template, tmp_path):
    """Item 38: the other side of the rule."""
    (template / "definition" / "bookmarks" / "b1.bookmark.json").write_text(
        "{}", encoding="utf-8")
    target = tmp_path / "out"
    run = _clone(template, "--expect-bookmark", "b1", target=target)
    assert run.code == 0, run.text
    assert "definition/bookmarks/b1.bookmark.json: EXISTS" in run.text, \
        run.text
