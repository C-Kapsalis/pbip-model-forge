"""`pbip-forge report blank --full`: a complete PBIR blank report for a model.

Spec H-blank-report-scaffold, cases 1-7. Fixture:
tests/fixtures/blank_report/coffee_client (Coffee.SemanticModel) and a
fictional theme file tests/fixtures/blank_report/themes/Roastery Light.json.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ported_helpers import FIXTURES, copy_fixture, forge, load, tree

THEME_SRC = FIXTURES / "blank_report" / "themes" / "Roastery Light.json"
HEX20 = re.compile(r"^[0-9a-f]{20}$")


@pytest.fixture
def client(tmp_path: Path) -> Path:
    return copy_fixture("blank_report/coffee_client", tmp_path)


def _blank(client: Path, *extra: object):
    return forge("report", "blank", "--client", client, "--model", "Coffee", "--full", *extra)


def test_case1_full_report_files(client):
    run = _blank(client)
    assert run.code == 0, run.text
    rep = client / "Coffee.Report"
    for d in ("definition/pages", "definition/bookmarks",
              "StaticResources/SharedResources/BaseThemes",
              "StaticResources/RegisteredResources", ".pbi"):
        assert (rep / d).is_dir(), d

    platform = load(rep / ".platform")
    assert platform["$schema"].endswith("platformProperties/2.0.0/schema.json")
    assert platform["metadata"] == {"type": "Report", "displayName": "Coffee"}
    assert platform["config"]["version"] == "2.0"
    assert re.fullmatch(r"[0-9a-f-]{36}", platform["config"]["logicalId"])

    pbir = load(rep / "definition.pbir")
    assert pbir["$schema"].endswith("definitionProperties/2.0.0/schema.json")
    assert pbir["version"] == "4.0"
    assert pbir["datasetReference"]["byPath"]["path"] == "../Coffee.SemanticModel"

    report = load(rep / "definition" / "report.json")
    assert report["$schema"].endswith("report/3.1.0/schema.json")
    base = report["themeCollection"]["baseTheme"]
    assert base["reportVersionAtImport"] == {"visual": "2.5.0", "report": "3.1.0", "page": "2.3.0"}
    assert base["type"] == "SharedResources"
    assert report["objects"]["section"][0]["properties"]["verticalAlignment"] == \
        {"expr": {"Literal": {"Value": "'Top'"}}}
    pkg = report["resourcePackages"][0]
    assert pkg["name"] == "SharedResources" and pkg["type"] == "SharedResources"
    assert pkg["items"][0]["path"] == f"BaseThemes/{base['name']}.json"
    assert pkg["items"][0]["type"] == "BaseTheme"
    expected_settings = dict.fromkeys(
        ["allowChangeFilterTypes", "defaultDrillFilterOtherVisuals",
         "useDefaultAggregateDisplayName", "useEnhancedTooltips",
         "useStylableVisualContainerHeader"], True)
    expected_settings["exportDataMode"] = "AllowSummarized"
    assert report["settings"] == expected_settings

    version = load(rep / "definition" / "version.json")
    assert version["$schema"].endswith("versionMetadata/1.0.0/schema.json")
    assert version["version"] == "2.0.0"
    local = load(rep / ".pbi" / "localSettings.json")
    assert list(local) == ["$schema"] and local["$schema"].endswith("localSettings/1.0.0/schema.json")

    pages = load(rep / "definition" / "pages" / "pages.json")
    assert pages["$schema"].endswith("pagesMetadata/1.0.0/schema.json")
    assert len(pages["pageOrder"]) == 1
    page_id = pages["pageOrder"][0]
    assert HEX20.match(page_id)
    assert pages["activePageName"] == page_id
    folders = [p.name for p in (rep / "definition" / "pages").iterdir() if p.is_dir()]
    assert folders == [page_id]
    page = load(rep / "definition" / "pages" / page_id / "page.json")
    assert page["$schema"].endswith("page/2.0.0/schema.json")
    assert (page["name"], page["displayName"], page["displayOption"], page["height"], page["width"]) == \
        (page_id, "Page 1", "FitToPage", 720, 1280)
    # 2-space JSON
    assert (rep / ".platform").read_text(encoding="utf-8").startswith('{\n  "')


def test_case2_existing_report_is_skipped_untouched(client):
    rep = client / "Coffee.Report"
    rep.mkdir()
    (rep / "keep.txt").write_text("hand made", encoding="utf-8")
    before = tree(client)
    run = _blank(client)
    assert run.code == 0, run.text
    assert "already exists" in run.text
    assert tree(client) == before


def test_case3_missing_model_is_a_warning_not_a_failure(client):
    run = forge("report", "blank", "--client", client, "--model", "Tea", "--full")
    assert run.code == 0, run.text
    assert "Tea" in run.text
    assert not (client / "Tea.Report").exists()


def test_case4_dry_run_creates_nothing(client):
    before = tree(client)
    run = _blank(client, "--dry-run")
    assert run.code == 0, run.text
    assert "Coffee.Report" in run.text
    assert tree(client) == before


def test_case5_theme_copied_byte_identical(client):
    run = _blank(client, "--theme", "Roastery Light", "--theme-file", THEME_SRC)
    assert run.code == 0, run.text
    copied = client / "Coffee.Report/StaticResources/SharedResources/BaseThemes/Roastery Light.json"
    assert copied.read_bytes() == THEME_SRC.read_bytes()
    report = load(client / "Coffee.Report/definition/report.json")
    assert report["themeCollection"]["baseTheme"]["name"] == "Roastery Light"


def test_case5_absent_theme_source_still_creates_report(client, tmp_path):
    run = _blank(client, "--theme", "Roastery Light", "--theme-file", tmp_path / "missing.json")
    assert run.code == 0, run.text
    themes = client / "Coffee.Report/StaticResources/SharedResources/BaseThemes"
    assert themes.is_dir() and not any(themes.iterdir())
    assert (client / "Coffee.Report/definition/report.json").is_file()


def _normalised(client: Path) -> dict[str, bytes]:
    rep = client / "Coffee.Report"
    logical = load(rep / ".platform")["config"]["logicalId"]
    page = load(rep / "definition/pages/pages.json")["pageOrder"][0]
    out = {}
    for rel, data in tree(rep).items():
        out[rel.replace(page, "PAGE")] = data.replace(logical.encode(), b"LID").replace(page.encode(), b"PAGE")
    return out, logical, page


def test_case6_two_runs_differ_only_in_random_ids(tmp_path):
    a = copy_fixture("blank_report/coffee_client", tmp_path / "a")
    b = copy_fixture("blank_report/coffee_client", tmp_path / "b")
    assert _blank(a).code == 0 and _blank(b).code == 0
    ta, la, pa = _normalised(a)
    tb, lb, pb = _normalised(b)
    assert la != lb and pa != pb
    assert ta == tb


def test_custom_report_name_and_missing_client(client, tmp_path):
    run = forge("report", "blank", "--client", client, "--model", "Coffee", "--name", "Coffee Ops", "--full")
    assert run.code == 0, run.text
    rep = client / "Coffee Ops.Report"
    assert load(rep / ".platform")["metadata"]["displayName"] == "Coffee Ops"
    assert load(rep / "definition.pbir")["datasetReference"]["byPath"]["path"] == "../Coffee.SemanticModel"
    assert forge("report", "blank", "--client", tmp_path / "nope", "--model", "Coffee", "--full").code == 1


def test_case7_preflight_reports_no_b004(client):
    pytest.importorskip("tmdl_preflight")
    assert _blank(client).code == 0
    proc = subprocess.run(
        [sys.executable, "-m", "tmdl_preflight.cli", "check", str(client), "--select", "B004", "--json"],
        capture_output=True, text=True,
    )
    payload = json.loads(proc.stdout)
    b004 = [v for v in payload["violations"]
            if (v.get("rule_id") or v.get("rule") or v.get("id")) == "B004"]
    assert b004 == [], b004


# -- review fixes ----------------------------------------------------------------
def test_default_theme_name(client):
    assert _blank(client).code == 0
    report = load(client / "Coffee.Report" / "definition" / "report.json")
    assert report["themeCollection"]["baseTheme"]["name"] == "CY25SU12"
    assert report["resourcePackages"][0]["items"][0]["path"] == "BaseThemes/CY25SU12.json"


def test_an_unexpected_error_fails_that_model_and_the_next_one_still_runs(client, monkeypatch):
    from pbip_model_forge import report_scaffold
    shutil.copytree(client / "Coffee.SemanticModel", client / "Tea.SemanticModel")
    real = report_scaffold.write_full_blank_report

    def flaky(parent, report_name, *a, **k):
        if report_name == "Coffee":
            raise RuntimeError("disk said no")
        return real(parent, report_name, *a, **k)

    monkeypatch.setattr(report_scaffold, "write_full_blank_report", flaky)
    run = forge("report", "blank", "--client", client, "--model", "Coffee", "Tea", "--full")
    assert run.code == 1, run.text
    assert "RuntimeError: disk said no" in run.out
    assert (client / "Tea.Report" / "definition" / "report.json").is_file()
