"""Report folders for existing models: full blank scaffold, clone, integrity.

Three pieces live here:

* :func:`write_full_blank_report` writes a complete PBIR report definition
  (``report.json``, ``version.json``, one page, ``.pbi/localSettings.json``)
  bound to a semantic model that already exists. The minimal two-file form
  used by ``build`` stays in :mod:`blank_report`.
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

from .blank_report import write_blank_report

_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
PLATFORM_SCHEMA = f"{_SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json"
PBIR_SCHEMA = f"{_SCHEMA}/item/report/definitionProperties/2.0.0/schema.json"
REPORT_SCHEMA = f"{_SCHEMA}/item/report/definition/report/3.1.0/schema.json"
VERSION_SCHEMA = f"{_SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json"
PAGES_SCHEMA = f"{_SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json"
PAGE_SCHEMA = f"{_SCHEMA}/item/report/definition/page/2.0.0/schema.json"
LOCAL_SCHEMA = f"{_SCHEMA}/item/report/localSettings/1.0.0/schema.json"

#: Built-in Power BI base theme referenced by new reports (December 2025 release).
DEFAULT_THEME = "CY25SU12"

_SUBDIRS = (
    "definition/pages",
    "definition/bookmarks",
    "StaticResources/SharedResources/BaseThemes",
    "StaticResources/RegisteredResources",
    ".pbi",
)


def _dump(obj: Any, indent: int | str = 2) -> str:
    return json.dumps(obj, indent=indent, ensure_ascii=False) + "\n"


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
        ".pbi/localSettings.json": _dump({"$schema": LOCAL_SCHEMA}),
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


def blank_reports_cli(args: argparse.Namespace) -> int:
    client = Path(args.client)
    if not client.is_dir():
        print(f"error: client folder not found: {client}")
        return 1
    if args.name and len(args.model) > 1:
        print("error: --name works with exactly one --model")
        return 2
    theme = args.theme or DEFAULT_THEME
    failed = 0
    for model in args.model:
        report_name = args.name or model
        model_dir = client / f"{model}.SemanticModel"
        report_dir = client / f"{report_name}.Report"
        if not model_dir.is_dir():
            print(f"warning: {model_dir} not found; skipped {model}")
            continue
        if report_dir.exists():
            print(f"skip: {report_dir} already exists (never overwritten)")
            continue
        theme_src = Path(args.theme_file) if args.theme_file else _sibling_theme(client, theme)
        if args.dry_run:
            if args.full:
                rels = sorted(set(_SUBDIRS) | set(full_report_files(
                    report_name, model, theme, "<logicalId>", "<page id>")))
            else:
                rels = [".platform", "definition.pbir"]
            print(f"would create {report_dir}")
            for rel in rels:
                print(f"  {rel}")
            if args.full and theme_src is not None and theme_src.is_file():
                print(f"  StaticResources/SharedResources/BaseThemes/{theme}.json (from {theme_src})")
            continue
        try:
            if args.full:
                write_full_blank_report(client, report_name, model, theme, theme_src)
            else:
                write_blank_report(client, report_name, model_name=model)
        except Exception as exc:  # one bad model must not stop the others
            print(f"error: {report_dir}: {type(exc).__name__}: {exc}")
            failed += 1
            continue
        print(f"created {report_dir}")
        if args.full and (theme_src is None or not theme_src.is_file()):
            print(f"  note: no theme file copied; report.json names '{theme}' and "
                  "Power BI falls back to its default theme")
        for problem in check_report(report_dir):
            print(f"  integrity: {problem}")
    return 1 if failed else 0


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


def clone_report(template: str | Path, name: str, out_dir: str | Path | None = None,
                 model: str | Path | None = None, force: bool = False,
                 logical_id: str | None = None) -> dict[str, Any]:
    """Copy ``template`` to ``<out_dir>/<name>.Report`` with a new identity.

    A relative ``model`` is read from the new report folder, the way
    ``definition.pbir`` stores it (``../Roastery.SemanticModel`` names a
    sibling of the copy); it must name an existing ``*.SemanticModel``
    folder.

    Returns ``{"target", "logical_id", "dataset_path"}``. Raises
    :class:`CloneError` before anything is written: exit code 2 for a bad
    template, ``--out-dir``, ``--model`` or ``--logical-id``, and 1 for a
    target that exists (without ``force``, or as a file)."""
    template = Path(template)
    if not template.is_dir():
        raise CloneError(f"template not found: {template}", 2)
    if not (template / ".platform").is_file():
        raise CloneError(f"template has no .platform: {template}", 2)
    if logical_id is not None:
        try:
            uuid.UUID(logical_id)
        except ValueError:
            raise CloneError(f"--logical-id is not a UUID: {logical_id!r}", 2) from None
    parent = Path(out_dir) if out_dir is not None else template.parent
    target = parent / f"{name}.Report"
    tpl_real = template.resolve()
    if target.resolve() == tpl_real:
        raise CloneError("target is the template itself", 2)
    if _is_within(parent.resolve(), tpl_real):
        raise CloneError(f"--out-dir {parent} is inside the template {template}; "
                         "choose a folder outside it", 2)

    model_rel = None
    if model is not None:
        model_path = Path(model)
        if not model_path.is_absolute():
            model_path = target / model_path
        model_real = Path(os.path.abspath(model_path))
        if not (model_real.name.endswith(".SemanticModel") and model_real.is_dir()):
            hint = "" if Path(model).is_absolute() else \
                " (a relative --model is read from the new report folder)"
            raise CloneError(f"--model {model} does not point to an existing *.SemanticModel "
                             f"folder: {model_real}{hint}", 2)
        model_rel = Path(os.path.relpath(model_real.resolve(), target.resolve())).as_posix()

    if target.exists() or target.is_symlink():
        if not target.is_dir() or target.is_symlink():
            raise CloneError(f"target exists and is not a folder: {target}", 1)
        if not force:
            raise CloneError(f"target already exists: {target} (use --force to replace it)", 1)
        try:
            shutil.rmtree(target)
        except OSError as exc:
            raise CloneError(f"could not remove {target}: {exc}", 1) from None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(template, target)
    except OSError as exc:
        raise CloneError(f"could not copy {template} to {target}: {exc}", 1) from None

    new_id = (logical_id or str(uuid.uuid4())).lower()

    def set_identity(obj: dict[str, Any]) -> None:
        obj.setdefault("metadata", {})["displayName"] = name
        obj.setdefault("config", {})["logicalId"] = new_id

    _rewrite_json(target / ".platform", set_identity)

    pbir = target / "definition.pbir"
    if model_rel is not None:
        def set_dataset(obj: dict[str, Any]) -> None:
            obj.setdefault("datasetReference", {}).setdefault("byPath", {})["path"] = model_rel

        _rewrite_json(pbir, set_dataset)
    dataset = None
    if pbir.is_file():
        try:
            dataset = json.loads(pbir.read_text(encoding="utf-8-sig"))[
                "datasetReference"]["byPath"]["path"]
        except (ValueError, KeyError, TypeError):
            dataset = None
    return {"target": target, "logical_id": new_id, "dataset_path": dataset}


def clone_report_cli(args: argparse.Namespace) -> int:
    try:
        done = clone_report(args.template, args.name, args.out_dir, args.model,
                            args.force, args.logical_id)
    except CloneError as exc:
        print(f"error: {exc}")
        return exc.code
    print(f"cloned {args.template} -> {done['target']}")
    print(f"  logicalId: {done['logical_id']}")
    print(f"  dataset:   {done['dataset_path'] or '(no byPath reference)'}")
    problems = check_report(done["target"])
    problems += preflight_report_findings(done["target"])
    if problems:
        for problem in problems:
            print(f"  integrity: {problem}")
    else:
        print("  integrity: ok")
    return 1 if (problems and args.strict) else 0


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
