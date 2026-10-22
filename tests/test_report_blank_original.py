"""`pbip-forge report blank`: the original's output, byte for byte.

The original's `create_blank_report.py` writes a complete PBIR report and
prints a fixed block of console lines. This test pins both.

What the original does that the tool did not:
- the FULL definition is the default (there is no minimal mode here);
- every file is written with 2-space indentation, `": "` after keys and NO
  trailing newline;
- the console output is the original's, with its coloured tags and its
  banner.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from forge_helpers import FIXTURES, copy_fixture, forge, load, tree

HEX20 = re.compile(r"^[0-9a-f]{20}$")
UUID = re.compile(r"^[0-9a-f-]{36}$")
RULE = "=" * 80


@pytest.fixture
def client(tmp_path: Path) -> Path:
    return copy_fixture("blank_report/coffee_client", tmp_path)


def _blank(client: Path, *extra: object):
    return forge("report", "blank", "--client", client, "--model", "Coffee", *extra)


# ── item 30: the full definition is the default ───────────────────────────

def test_the_full_definition_is_the_default(client):
    """Item 30: no `--full` needed."""
    run = _blank(client)
    assert run.code == 0, run.text
    rep = client / "Coffee.Report"
    assert (rep / "definition" / "report.json").is_file()
    assert (rep / "definition" / "version.json").is_file()
    assert (rep / "definition" / "pages" / "pages.json").is_file()
    # BUGFIX (after 1.2.0): no .pbi/localSettings.json (user/machine state)
    assert not (rep / ".pbi" / "localSettings.json").exists()


def test_full_is_still_accepted(client):
    """Item 30: `--full` has no further effect."""
    run = _blank(client, "--full")
    assert run.code == 0, run.text
    assert (client / "Coffee.Report" / "definition" / "report.json").is_file()


# ── item 31: the exact files ──────────────────────────────────────────────

def test_every_file_is_written_with_two_space_indent_and_no_newline(client):
    """Item 31: the exact bytes of every file."""
    run = _blank(client)
    assert run.code == 0, run.text
    rep = client / "Coffee.Report"
    for rel in (".platform", "definition.pbir", "definition/report.json",
                "definition/version.json", "definition/pages/pages.json"):
        text = (rep / rel).read_text(encoding="utf-8")
        assert text.startswith('{\n  "'), (rel, text[:40])
        assert not text.endswith("\n"), (rel, "the file ends with a newline")
        assert '": ' in text, (rel, "no space after the colon")


def test_the_folders_exist(client):
    """Item 31: the folders."""
    run = _blank(client)
    assert run.code == 0, run.text
    rep = client / "Coffee.Report"
    for d in ("definition/pages", "definition/bookmarks",
              "StaticResources/SharedResources/BaseThemes",
              "StaticResources/RegisteredResources"):
        assert (rep / d).is_dir(), d
    # BUGFIX (after 1.2.0): no .pbi folder
    assert not (rep / ".pbi").exists()


def test_non_ascii_is_escaped(tmp_path):
    """Item 31: `Café` is written as its escape."""
    client = copy_fixture("blank_report/coffee_client", tmp_path)
    (client / "Coffee.SemanticModel").rename(client / "Café.SemanticModel")
    run = forge("report", "blank", "--client", client, "--model", "Café")
    assert run.code == 0, run.text
    text = (client / "Café.Report" / ".platform").read_text(encoding="utf-8")
    assert "Caf\\u00e9" in text, text


def test_the_ids_are_the_right_shape(client):
    """Item 31: the logical id is a UUID, the page id is 20 hex chars."""
    run = _blank(client)
    assert run.code == 0, run.text
    rep = client / "Coffee.Report"
    assert UUID.match(load(rep / ".platform")["config"]["logicalId"])
    pages = load(rep / "definition" / "pages" / "pages.json")
    assert HEX20.match(pages["pageOrder"][0])


# ── item 32: the theme copy ───────────────────────────────────────────────

def test_the_theme_is_copied_from_a_sibling_report(client):
    """Item 32: the client's own report ships the theme."""
    src = (client / "Coffee.Report" / "StaticResources" / "SharedResources"
           / "BaseThemes" / "CY25SU12.json")
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text('{"theme": true}', encoding="utf-8")
    shutil.rmtree(client / "Coffee.Report")
    other = client / "Other.Report" / "StaticResources" / "SharedResources" \
        / "BaseThemes"
    other.mkdir(parents=True)
    (other / "CY25SU12.json").write_text('{"theme": true}', encoding="utf-8")

    run = _blank(client)
    assert run.code == 0, run.text
    copied = (client / "Coffee.Report" / "StaticResources" / "SharedResources"
              / "BaseThemes" / "CY25SU12.json")
    assert copied.read_bytes() == b'{"theme": true}'


def test_no_theme_means_no_note(client):
    """Item 32: nothing is copied and nothing is said."""
    run = _blank(client)
    assert run.code == 0, run.text
    assert "no theme file copied" not in run.text, run.text


# ── item 33: the checks ───────────────────────────────────────────────────

def test_a_missing_client_folder_fails(client, tmp_path):
    """Item 33: exit 1 and the original's message."""
    run = forge("report", "blank", "--client", tmp_path / "nowhere",
                "--model", "Coffee")
    assert run.code == 1, run.text
    assert "Client directory not found" in run.text, run.text


def test_a_missing_model_is_a_skip(client):
    """Item 33: nothing is created for a missing model. BUGFIX (after
    1.2.0): it is no longer a success; the run exits 1."""
    run = forge("report", "blank", "--client", client, "--model", "Tea")
    assert run.code == 1, run.text
    assert "Semantic model not found" in run.text, run.text
    assert not (client / "Tea.Report").exists()


def test_an_existing_report_is_a_skip(client):
    """Item 33: an existing report is never overwritten."""
    rep = client / "Coffee.Report"
    rep.mkdir()
    (rep / "keep.txt").write_text("hand made", encoding="utf-8")
    before = tree(client)
    run = _blank(client)
    assert run.code == 0, run.text
    assert "Report already exists" in run.text, run.text
    assert tree(client) == before


# ── item 34: the console output ───────────────────────────────────────────

def test_the_banner_and_the_footer(client):
    """Item 34: the original's banner and footer."""
    run = _blank(client)
    assert run.code == 0, run.text
    lines = run.text.splitlines()
    assert lines[0] == RULE, lines[:3]
    assert lines[1] == "CREATE BLANK REPORTS", lines[:3]
    assert lines[2] == RULE, lines[:3]
    assert lines[-3] == RULE, lines[-3:]
    assert lines[-2] == "✅ ALL REPORTS CREATED SUCCESSFULLY", lines[-3:]
    assert lines[-1] == RULE, lines[-3:]


def test_the_creation_block(client):
    """Item 34: the per-model lines."""
    run = _blank(client)
    assert run.code == 0, run.text
    assert "Creating blank report: Coffee" in run.text, run.text
    assert "  Location: " in run.text, run.text
    assert "  References: Coffee.SemanticModel" in run.text, run.text


def test_the_success_block(client):
    """Item 34: the success lines."""
    run = _blank(client)
    assert run.code == 0, run.text
    assert "✅ Created blank report: Coffee" in run.text, run.text
    assert "   Location: " in run.text, run.text


def test_the_dry_run_block(client):
    """Item 34: the dry-run listing."""
    run = _blank(client, "--dry-run")
    assert run.code == 0, run.text
    assert "  [DRY RUN] Would create:" in run.text, run.text
    folder = client / "Coffee.Report"
    for rel in (".platform", "definition.pbir", "definition/report.json",
                "definition/version.json", "definition/pages/",
                "definition/bookmarks/", "StaticResources/"):
        assert f"    - {folder}/{rel}" in run.text, (rel, run.text)


def test_the_skip_blocks(client):
    """Item 34: the missing-model and existing-report blocks."""
    (client / "Coffee.Report").mkdir()
    run = forge("report", "blank", "--client", client,
                "--model", "Coffee", "Tea")
    # BUGFIX (after 1.2.0): the missing model Tea makes the run exit 1
    assert run.code == 1, run.text
    assert "⚠️  Semantic model not found: " in run.text, run.text
    assert "   Skipping report creation for Tea" in run.text, run.text
    assert "ℹ️  Report already exists: Coffee" in run.text, run.text
    assert "   Skipping: " in run.text, run.text


def test_the_old_lines_are_gone(client):
    """Item 34: the tool's own lines are removed."""
    run = _blank(client)
    for gone in ("created ", "skip: ", "warning: ", "would create",
                 "integrity:", "note: no theme file copied"):
        assert gone not in run.text, (gone, run.text)


# ── kept fixes after 1.2.0 (BUGFIX) ──────────────────────────────────────

PAGES_SCHEMA_1_1 = ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
                    "definition/pagesMetadata/1.1.0/schema.json")


def test_pages_json_declares_the_1_1_0_schema(client):
    """BUGFIX: tmdl-preflight B005 accepts pagesMetadata 1.1.0, not 1.0.0."""
    run = _blank(client)
    assert run.code == 0, run.text
    pages = load(client / "Coffee.Report" / "definition" / "pages" / "pages.json")
    assert pages["$schema"] == PAGES_SCHEMA_1_1


def test_no_local_settings_are_written(client):
    """BUGFIX: .pbi/localSettings.json is user/machine state (B007 warning)."""
    run = _blank(client)
    assert run.code == 0, run.text
    assert not (client / "Coffee.Report" / ".pbi").exists()


def test_only_missing_models_create_nothing_and_fail(tmp_path):
    """BUGFIX: a client with no model must not claim success."""
    client = tmp_path / "empty"
    client.mkdir()
    run = forge("report", "blank", "--client", client, "--model", "Nope")
    assert run.code == 1, run.text
    lines = run.out.splitlines()
    assert lines[-2] == "⚠️  NO REPORTS CREATED", lines[-3:]
    assert "ALL REPORTS CREATED SUCCESSFULLY" not in run.text
    assert list(client.iterdir()) == []


def test_a_missing_model_next_to_a_created_one_fails(client):
    """BUGFIX: one created report does not make a missing model a success."""
    run = forge("report", "blank", "--client", client, "--model", "Coffee", "Tea")
    assert run.code == 1, run.text
    assert (client / "Coffee.Report" / "definition" / "report.json").is_file()
    assert run.out.splitlines()[-2] == "⚠️  SOME REPORTS FAILED", run.out


def test_report_blank_has_no_preflight_errors_or_warnings(client):
    """A fresh blank report passes tmdl-preflight with 0 errors, 0 warnings."""
    pytest.importorskip("tmdl_preflight")
    import subprocess
    import sys
    assert _blank(client).code == 0
    proc = subprocess.run(
        [sys.executable, "-m", "tmdl_preflight.cli", "check", str(client), "--json"],
        capture_output=True, text=True)
    payload = json.loads(proc.stdout)
    report_findings = [v for v in payload["violations"]
                       if v.get("severity") in ("error", "warning")
                       and v.get("rule", "").startswith("B")]
    assert report_findings == [], report_findings
