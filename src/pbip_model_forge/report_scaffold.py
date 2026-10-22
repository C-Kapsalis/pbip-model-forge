"""Report folders for existing models: full blank scaffold, clone, integrity.

Three pieces live here:

* :func:`write_full_blank_report` writes a complete PBIR report definition
  (``report.json``, ``version.json``, one page listed in ``pages.json``)
  bound to a semantic model. ``report blank`` and ``build`` (through
  :func:`blank_report.write_blank_report`) both write this form.
* :func:`clone_report` copies a finished report folder, gives the copy a new
  ``logicalId`` and display name, and optionally points it at another model.
* :func:`check_report` is a small structural check of a report folder (the
  dataset reference resolves, every listed page has a valid ``page.json``),
  run after both commands so a broken scaffold is reported at once.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import importlib.util
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
PLATFORM_SCHEMA = f"{_SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json"
PBIR_SCHEMA = f"{_SCHEMA}/item/report/definitionProperties/2.0.0/schema.json"
REPORT_SCHEMA = f"{_SCHEMA}/item/report/definition/report/3.1.0/schema.json"
VERSION_SCHEMA = f"{_SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json"
#: tmdl-preflight B005 accepts the 1.1.0 pages metadata (the original wrote 1.0.0).
PAGES_SCHEMA = f"{_SCHEMA}/item/report/definition/pagesMetadata/1.1.0/schema.json"
PAGE_SCHEMA = f"{_SCHEMA}/item/report/definition/page/2.0.0/schema.json"

#: Built-in Power BI base theme referenced by new reports (December 2025 release).
DEFAULT_THEME = "CY25SU12"

_SUBDIRS = (
    "definition/pages",
    "definition/bookmarks",
    "StaticResources/SharedResources/BaseThemes",
    "StaticResources/RegisteredResources",
)
# No `.pbi` folder: `.pbi/localSettings.json` is user/machine state that Power
# BI Desktop writes itself and that belongs in .gitignore (tmdl-preflight
# B007 warns when a report carries it). The original wrote it; BUGFIX.


def _dump(obj: Any, indent: int | str = 2) -> str:
    """A JSON document, as the original writes it.

    Two-space indentation, `": "` after the keys, and NO newline at the
    end of the file.
    """
    return json.dumps(obj, indent=indent, ensure_ascii=True)


#: report-level switches written into every new report.json
_REPORT_SETTINGS = dict(
    allowChangeFilterTypes=True,
    defaultDrillFilterOtherVisuals=True,
    exportDataMode="AllowSummarized",
    useDefaultAggregateDisplayName=True,
    useEnhancedTooltips=True,
    useStylableVisualContainerHeader=True,
)
#: schema versions the base theme was imported at
_IMPORT_VERSIONS = dict(page="2.3.0", report="3.1.0", visual="2.5.0")


def _report_json(theme: str) -> dict[str, Any]:
    top_align = dict(expr=dict(Literal=dict(Value="'Top'")))
    theme_item = dict(name=theme, path="BaseThemes/" + theme + ".json", type="BaseTheme")
    doc: dict[str, Any] = {"$schema": REPORT_SCHEMA}
    doc["themeCollection"] = dict(baseTheme=dict(
        name=theme, reportVersionAtImport=dict(_IMPORT_VERSIONS), type="SharedResources"))
    doc["objects"] = dict(section=[dict(properties=dict(verticalAlignment=top_align))])
    doc["resourcePackages"] = [dict(name="SharedResources", type="SharedResources",
                                    items=[theme_item])]
    doc["settings"] = dict(_REPORT_SETTINGS)
    return doc


def new_page_id() -> str:
    """A 20-hex-character page name, the shape Power BI Desktop uses."""
    return hashlib.md5(uuid.uuid4().bytes).hexdigest()[:20]


def full_report_files(report_name: str, model_name: str, theme: str,
                      logical_id: str, page_id: str) -> dict[str, str]:
    """Relative path -> text for every JSON file of a full blank report."""
    platform = {"$schema": PLATFORM_SCHEMA}
    platform["metadata"] = dict(type="Report", displayName=report_name)
    platform["config"] = dict(version="2.0", logicalId=logical_id)

    pbir = {"$schema": PBIR_SCHEMA, "version": "4.0"}
    pbir["datasetReference"] = dict(byPath=dict(path="../" + model_name + ".SemanticModel"))

    pages = {"$schema": PAGES_SCHEMA}
    pages.update(pageOrder=[page_id], activePageName=page_id)

    page = {"$schema": PAGE_SCHEMA}
    page.update(name=page_id, displayName="Page 1", displayOption="FitToPage")
    page.update(height=720, width=1280)

    return {
        ".platform": _dump(platform),
        "definition.pbir": _dump(pbir),
        "definition/report.json": _dump(_report_json(theme)),
        "definition/version.json": _dump({"$schema": VERSION_SCHEMA, "version": "2.0.0"}),
        "definition/pages/pages.json": _dump(pages),
        "definition/pages/" + page_id + "/page.json": _dump(page),
    }


def write_full_blank_report(parent: str | Path, report_name: str, model_name: str,
                            theme: str = DEFAULT_THEME, theme_file: str | Path | None = None,
                            logical_id: str | None = None, page_id: str | None = None) -> Path:
    """Write ``<parent>/<report_name>.Report`` with a complete PBIR definition.

    The theme JSON is copied byte for byte when ``theme_file`` exists; when it
    does not, report.json still names the theme and Desktop falls back to its
    defaults."""
    report_dir = Path(parent) / f"{report_name}.Report"
    for sub in _SUBDIRS:
        (report_dir / sub).mkdir(parents=True, exist_ok=True)
    files = full_report_files(report_name, model_name, theme,
                              logical_id or str(uuid.uuid4()), page_id or new_page_id())
    for rel, text in files.items():
        target = report_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if theme_file is not None and Path(theme_file).is_file():
        shutil.copyfile(theme_file, report_dir / "StaticResources/SharedResources/BaseThemes"
                        / f"{theme}.json")
    return report_dir


def _sibling_theme(client: Path, theme: str) -> Path | None:
    """A theme file of that name already shipped by another report of the client."""
    for rep in sorted(client.glob("*.Report")):
        cand = rep / "StaticResources/SharedResources/BaseThemes" / f"{theme}.json"
        if cand.is_file():
            return cand
    return None


#: The console tags the original writes, with their colours.
_TAG = {
    "info": "\033[0;34m[INFO]\033[0m",
    "success": "\033[0;32m[SUCCESS]\033[0m",
    "warning": "\033[1;33m[WARNING]\033[0m",
}


def _rule() -> str:
    return "=" * 80


def blank_reports_cli(args: argparse.Namespace) -> int:
    """``pbip-forge report blank``: the original's output, byte for byte.

    The full PBIR definition is the default; there is no minimal mode in
    this command. Exit 1 when a report failed or a model was not found
    (nothing is created for it), else 0; an existing report is a skip.
    """
    client = Path(args.client)
    if not client.is_dir():
        print(f"❌ Client directory not found: {client}")
        return 1
    if args.name and len(args.model) > 1:
        print("error: --name works with exactly one --model", file=sys.stderr)
        return 2
    theme = args.theme or DEFAULT_THEME
    print(_rule())
    print("CREATE BLANK REPORTS")
    print(_rule())
    print()
    failed = False
    missing = False
    created = 0
    for model in args.model:
        report_name = args.name or model
        model_dir = client / f"{model}.SemanticModel"
        report_dir = client / f"{report_name}.Report"
        if not model_dir.exists():
            print(f"⚠️  Semantic model not found: {model_dir}")
            print(f"   Skipping report creation for {model}")
            print()
            missing = True
            continue
        if report_dir.exists():
            print(f"ℹ️  Report already exists: {report_name}")
            print(f"   Skipping: {report_dir}")
            print()
            continue
        print(f"Creating blank report: {report_name}")
        print(f"  Location: {report_dir}")
        print(f"  References: {model}.SemanticModel")
        print()
        if args.dry_run:
            print("  [DRY RUN] Would create:")
            for rel in (".platform", "definition.pbir",
                        "definition/report.json", "definition/version.json",
                        "definition/pages/", "definition/bookmarks/",
                        "StaticResources/"):
                print(f"    - {report_dir}/{rel}")
            print()
            created += 1
            continue
        theme_src = (Path(args.theme_file) if args.theme_file
                     else _sibling_theme(client, theme))
        try:
            write_full_blank_report(client, report_name, model, theme,
                                    theme_src)
        except Exception as exc:      # one bad model must not stop the rest
            print(f"❌ Error creating report: {exc}")
            import traceback
            traceback.print_exc()
            failed = True
            continue
        print(f"✅ Created blank report: {report_name}")
        print(f"   Location: {report_dir}")
        print()
        created += 1
    # BUGFIX: a model that does not exist is not a success. The original
    # printed the success footer and exited 0 even when nothing was created.
    if not failed and not missing:
        footer = "✅ ALL REPORTS CREATED SUCCESSFULLY"
    elif not failed and not created:
        footer = "⚠️  NO REPORTS CREATED"
    else:
        footer = "⚠️  SOME REPORTS FAILED"
    print(_rule())
    print(footer)
    print(_rule())
    return 1 if (failed or missing) else 0


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------
def _indent_of(text: str) -> int | str:
    """The indentation unit of a pretty-printed JSON document."""
    for line in text.splitlines()[1:]:
        lead = line[: len(line) - len(line.lstrip())]
        if lead:
            return lead if "\t" in lead else len(lead)
    return 2


def _rewrite_json(path: Path, edit) -> None:
    """Load ``path``, apply ``edit(obj)`` in place, write it back in the
    source's indentation and line-ending style (key order is kept)."""
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    obj = json.loads(text)
    edit(obj)
    out = json.dumps(obj, indent=_indent_of(text), ensure_ascii=False)
    if text.endswith("\n"):
        out += "\n"
    if b"\r\n" in raw:
        out = out.replace("\n", "\r\n")
    prefix = "﻿" if raw.startswith(b"\xef\xbb\xbf") else ""
    path.write_bytes((prefix + out).encode("utf-8"))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class CloneError(Exception):
    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


#: The log tags the original writes, with their colours.
_CLONE_COLORS = {"info": "\033[0;34m", "success": "\033[0;32m",
                  "warning": "\033[1;33m", "error": "\033[0;31m"}


def _log(tag: str, message: str) -> None:
    """One log line: a coloured tag, then the message."""
    print(f"{_CLONE_COLORS[tag]}[{tag.upper()}]\033[0m {message}")


_BANNER = (
    "",
    "╔══════════════════════════════════════════════════════════════╗",
    "║              Universal M Template Deployment                 ║",
    "║                  Production Ready v2.0                      ║",
    "║              27-Visual Architecture • <2s Load              ║",
    "╚══════════════════════════════════════════════════════════════╝",
    "",
)

_INSTRUCTIONS = """
╔══════════════════════════════════════════════════════════════╗
║                     Deployment Complete!                     ║
╚══════════════════════════════════════════════════════════════╝

📍 Location: {target}
📊 Semantic Model: {model}
🎯 Visuals: {visuals} components (x/y/t Protocol)
⚡ Performance: <2s load time target

🚀 Next Steps:

1. Deploy Semantic Model to Power BI:
   • Ensure '{model}' exists in your workspace
   • Verify x-Selector and y-Selector field parameters
   • Check f-Filters table for gating functionality

2. Import Report to Power BI:
   • Open Power BI Desktop
   • File → Import → Browse to: {target}
   • Select: definition.pbir
   • Click Open

3. Validate Functionality:
   • Report loads in <2s
   • Field parameter slicers work
   • Matrix updates with selections
   • Bookmarks switch contexts

4. Enterprise Features:
   • x/y/t Protocol visual organization
   • ThemeDataColor integration
   • Foundation Rules compliance
   • Production-ready performance

📚 Documentation: See docs/ directory for detailed guides

✅ Ready for enterprise deployment!
"""


def clone_report(template: str | Path, name: str, target: str | Path,
                 model: str | None = None, force: bool = False,
                 logical_id: str | None = None,
                 expect_visuals: int | None = None,
                 expect_bookmarks: list[str] | None = None,
                 stdin=None) -> dict[str, Any]:
    """Copy ``template`` into ``target`` and give the copy a new identity.

    The target directory is the report folder itself, used exactly as given.
    The semantic model is a free string; no existence check. The value
    edits are JSON-aware: only the value's bytes change, the formatting
    and the key order stay as they are.

    Raises :class:`CloneError` before anything is written: exit code 2 for
    a target inside the template or a ``--logical-id`` that is not a UUID,
    and 1 for a missing template or a missing required file.
    """
    template = Path(template)
    target = Path(target)
    if not template.is_dir():
        raise CloneError(f"Universal template not found at: {template}", 1)
    tpl_real = template.resolve()
    try:
        inside = target.resolve().is_relative_to(tpl_real)
    except (OSError, ValueError):
        inside = False
    if inside:
        raise CloneError(f"target directory {target} is inside the template "
                         f"{template}; choose a folder outside it", 2)
    if logical_id is not None:
        try:
            uuid.UUID(logical_id)
        except ValueError:
            raise CloneError(f"--logical-id is not a UUID: {logical_id!r}",
                             2) from None
    return {"target": target, "name": name, "model": model,
            "logical_id": logical_id}


def _clone_deploy(template: Path, name: str, target: Path, model: str,
                  force: bool, logical_id: str | None,
                  expect_visuals: int | None,
                  expect_bookmarks: list[str], stdin) -> int:
    """The original's deployment sequence, with its log lines."""
    if expect_visuals is not None or expect_bookmarks:
        for line in _BANNER:
            print(line)

    _log("info", "Configuration:")
    _log("info", f"  Deployment Name: {name}")
    _log("info", f"  Target Directory: {target}")
    _log("info", f"  Semantic Model: {model}")
    _log("info", f"  Template Source: {template}")
    print()

    # ── prerequisites ──
    _log("info", "Validating prerequisites...")
    if not template.is_dir():
        _log("error", f"Universal template not found at: {template}")
        return 1
    if target.exists():
        _log("warning", f"Target directory already exists: {target}")
        if not force:
            sys.stdout.write("Continue and overwrite? (y/N): ")
            sys.stdout.flush()
            answer = ""
            if stdin is not None:
                answer = stdin.readline()
            if answer.strip() not in ("y", "Y"):
                _log("info", "Deployment cancelled.")
                return 0
        shutil.rmtree(target, ignore_errors=True)
    _log("success", "Prerequisites validated")

    # ── deploy ──
    _log("info", "Deploying universal M Template...")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, target, dirs_exist_ok=True)

    pbir = target / "definition.pbir"
    if pbir.is_file():
        _log("info", f"Updating semantic model reference to: {model}")
        shutil.copyfile(pbir, pbir.with_name("definition.pbir.backup"))
        _set_json_values(pbir, "path", f"../{model}")
        _log("success", "Updated semantic model reference")

    platform = target / ".platform"
    new_id = (logical_id or str(uuid.uuid4())).lower()
    if platform.is_file():
        _log("info", "Generating unique logical ID...")
        shutil.copyfile(platform, platform.with_name(".platform.backup"))
        _set_json_values(platform, "logicalId", new_id)
        _set_json_values(platform, "displayName", name)
        _log("success", f"Generated unique logical ID: {new_id}")
    _log("success", "Universal M Template deployed successfully!")

    # ── validate ──
    _log("info", "Validating deployment...")
    if expect_visuals is not None:
        _check_visuals(target, expect_visuals)
    for name_ in ("definition.pbir", ".platform", "definition/report.json",
                  "definition/version.json"):
        if (target / name_).is_file():
            _log("success", f"Required file exists: {name_}")
        else:
            _log("error", f"Missing required file: {name_}")
            return 1
    if expect_bookmarks:
        failed = False
        for bookmark in expect_bookmarks:
            rel = f"definition/bookmarks/{bookmark}.bookmark.json"
            if (target / rel).is_file():
                print(f"✅ {rel}: EXISTS")
            else:
                print(f"❌ {rel}: MISSING")
                failed = True
        if failed:
            print("❌ VALIDATION FAILED - Fix critical issues before pushing "
                  "to Power BI Online")
            return 1
    _log("success", "Deployment validation completed!")

    if expect_visuals is not None or expect_bookmarks:
        print(_INSTRUCTIONS.format(
            target=target, model=model,
            visuals=expect_visuals if expect_visuals is not None else 27))
    _log("success", "Universal M Template deployment completed successfully!")
    return 0


def _check_visuals(target: Path, expected: int) -> None:
    """The visual count and the x/y/t protocol check."""
    folder = target / "definition" / "pages" / "main_page" / "visuals"
    count = len(list(folder.rglob("visual.json"))) if folder.is_dir() else 0
    if count == expected:
        _log("success", f"Visual count validated: {expected} components "
                        f"(streamlined architecture)")
    else:
        _log("warning", f"Visual count: {count} (expected: {expected})")
    if not folder.is_dir():
        _log("warning", "x/y/t Protocol validation incomplete")
        return
    counts = {}
    for prefix in ("x", "y", "t", "e"):
        counts[prefix] = sum(1 for p in folder.iterdir()
                             if p.is_dir() and p.name.startswith(prefix))
    if counts["x"] > 0 and counts["y"] > 0:
        _log("success", "x/y/t Protocol validated: "
                        f"x={counts['x']}, y={counts['y']}, t={counts['t']}, "
                        f"e={counts['e']}")
    else:
        _log("warning", "x/y/t Protocol validation incomplete")


def _set_json_values(path: Path, key: str, value: str) -> None:
    """Set EVERY value of ``key`` in a JSON document to ``value``.

    The value's bytes change; the formatting and the key order stay as
    they are. The document is read as JSON, so any spacing is accepted and
    a name with a quote in it is escaped correctly.
    """
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    doc = json.loads(text)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key and isinstance(v, str):
                    node[k] = value
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(doc)
    out = json.dumps(doc, indent=_indent_of(text), ensure_ascii=False)
    if text.endswith("\n"):
        out += "\n"
    if b"\r\n" in raw:
        out = out.replace("\n", "\r\n")
    prefix = "﻿" if raw.startswith(b"\xef\xbb\xbf") else ""
    path.write_bytes((prefix + out).encode("utf-8"))


def clone_report_cli(args: argparse.Namespace) -> int:
    """``pbip-forge clone-report``: the original deployment script."""
    template = Path(args.template)
    name = args.name or "MyCompany-Analytics"
    target = Path(args.target_dir) if args.target_dir else \
        (Path.cwd() / name).resolve()
    model = args.semantic_model or args.model or f"{name}.SemanticModel"
    try:
        clone_report(template, name, target, model, args.force,
                     args.logical_id)
    except CloneError as exc:
        _log("error", str(exc))
        return exc.code
    return _clone_deploy(template, name, target, model, args.force,
                         args.logical_id, args.expect_visuals,
                         list(args.expect_bookmark or []), sys.stdin)


def preflight_report_findings(report_dir: Path) -> list[str]:
    """B004 findings of tmdl-preflight for this report, when it is installed.

    tmdl-preflight is an optional companion here: when it cannot be imported
    the built-in :func:`check_report` stands alone and nothing is reported."""
    if importlib.util.find_spec("tmdl_preflight") is None:
        return []
    proc = subprocess.run(
        [sys.executable, "-m", "tmdl_preflight.cli", "check", str(report_dir.parent),
         "--select", "B004", "--json"],
        capture_output=True, text=True, check=False)
    try:
        found = json.loads(proc.stdout).get("violations", [])
    except (ValueError, AttributeError):
        return [f"tmdl-preflight did not return JSON (exit {proc.returncode})"]
    return [f"tmdl-preflight B004: {v.get('message', v)}" for v in found
            if isinstance(v, dict) and _finding_in(v, report_dir)]


def _finding_in(violation: dict[str, Any], report_dir: Path) -> bool:
    """True when a tmdl-preflight finding is about a file of ``report_dir``
    itself (not of a sibling whose name merely contains it)."""
    root = report_dir.resolve()
    file = violation.get("file")
    if file:
        return _is_within(Path(file).resolve(), root)
    rel = violation.get("path")
    if rel:
        return _is_within((report_dir.parent / rel).resolve(), root)
    return False


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------
def _load_json(path: Path) -> tuple[Any, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except (OSError, ValueError) as exc:
        return None, f"{path.name} is not valid JSON ({exc})"


def check_report(report_dir: str | Path) -> list[str]:
    """Structural problems of a report folder; an empty list means clean.

    Checks: ``.platform`` and ``definition.pbir`` parse; a ``byPath`` dataset
    reference points at an existing folder; when ``definition/pages`` exists,
    every page in ``pages.json`` has a folder with a parseable ``page.json``
    and ``activePageName`` is one of them."""
    report_dir = Path(report_dir)
    problems: list[str] = []
    platform = report_dir / ".platform"
    if not platform.is_file():
        problems.append(".platform is missing")
    else:
        obj, err = _load_json(platform)
        if err:
            problems.append(err)
        elif not (isinstance(obj, dict) and obj.get("config", {}).get("logicalId")):
            problems.append(".platform has no config.logicalId")

    pbir = report_dir / "definition.pbir"
    if not pbir.is_file():
        problems.append("definition.pbir is missing")
    else:
        obj, err = _load_json(pbir)
        if err:
            problems.append(err)
        else:
            path = (obj.get("datasetReference", {}).get("byPath") or {}).get("path") \
                if isinstance(obj, dict) else None
            if path and not (report_dir / path).is_dir():
                problems.append(f"dataset reference {path} does not exist")

    pages_dir = report_dir / "definition" / "pages"
    pages_json = pages_dir / "pages.json"
    if pages_json.is_file():
        meta, err = _load_json(pages_json)
        if err:
            problems.append(err)
        elif isinstance(meta, dict):
            order = meta.get("pageOrder") or []
            for page in order:
                page_file = pages_dir / str(page) / "page.json"
                if not page_file.is_file():
                    problems.append(f"page {page} in pages.json has no page.json")
                else:
                    _, perr = _load_json(page_file)
                    if perr:
                        problems.append(f"page {page}: {perr}")
            active = meta.get("activePageName")
            if active and active not in order:
                problems.append(f"activePageName {active} is not in pageOrder")
    return problems
