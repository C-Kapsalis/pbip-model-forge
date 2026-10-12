"""The hand-off pack: ``<out>/handoff/manifest.json`` and ``SPEC.md``.

What a data engineer needs to build the model for real, generated from the
same spec the PBIP came from:

    manifest.json   machine-readable: tables (with inferred role), columns,
                    types, keys, relationships, and measures with the tables,
                    columns and measures each one depends on
    SPEC.md         human-readable: a data dictionary per table, the
                    relationships, the measures, and a Mermaid erDiagram

Both files are deterministic (sorted, no timestamps), so they diff cleanly
between rebuilds.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import model_info as mi
from .check import dax_references, mentions_table, strip_dax
from .enter_data import resolve_type


def _measure_dependencies(m: dict[str, Any], spec: dict[str, Any]) -> dict[str, list[str]]:
    mt = spec.get("measures_table") or {}
    measure_names = {x["name"] for x in mt.get("measures", [])}
    data_tables = {t["name"] for t in spec.get("tables", [])}
    cal = mi.calendar_name(spec)
    if cal:
        data_tables.add(cal)
    refs = dax_references(m.get("expression", ""))
    measures, columns, tables = set(), set(), set()
    for t, member in refs["qualified"]:
        if t == mt.get("name") and member in measure_names:
            measures.add(member)
        else:
            columns.add(f"{t}[{member}]")
            tables.add(t)
    for member in refs["bare"]:
        if member in measure_names:
            measures.add(member)
    text = strip_dax(m.get("expression", ""))
    for t in data_tables:
        if mentions_table(text, t):
            tables.add(t)
    return {"measures": sorted(measures), "columns": sorted(columns),
            "tables": sorted(tables)}


def build_manifest(spec: dict[str, Any]) -> dict[str, Any]:
    """The manifest dict (see module docstring)."""
    from . import __version__

    roles = mi.infer_roles(spec)
    tables: list[dict[str, Any]] = []
    for t in spec.get("tables", []):
        tables.append({
            "name": t["name"],
            "role": roles[t["name"]],
            "description": t.get("description", ""),
            "hidden": bool(t.get("hidden", False)),
            "sample_rows": len(t.get("rows", [])),
            "columns": [
                {
                    "name": c["name"],
                    "dataType": resolve_type(c["type"])["dataType"],
                    "key": bool(c.get("key", False)),
                    "hidden": mi.column_defaults(spec, t, c)["hidden"],
                    "format": c.get("format") or "",
                    "description": c.get("description", ""),
                }
                for c in t["columns"]
            ],
        })
    cal = spec.get("calendar")
    if cal:
        start, end = mi.calendar_years(spec)
        tables.append({
            "name": mi.calendar_name(spec),
            "role": "calendar",
            "description": "Calculated date dimension.",
            "hidden": False,
            "range": {"start": f"{start}-01-01", "end": f"{end}-12-31"},
            "columns": [
                {"name": c["name"], "dataType": c["dataType"],
                 "key": c["name"] == "Date", "hidden": c["hidden"],
                 "format": c["format"] or "", "description": c["description"]}
                for c in mi.CALENDAR_COLUMNS
            ],
        })
    mt = spec.get("measures_table")
    if mt:
        tables.append({"name": mt["name"], "role": "measures",
                       "description": mt.get("description", ""),
                       "hidden": False, "columns": []})
    tables.sort(key=lambda x: x["name"].lower())

    relationships = sorted(
        (
            {
                "from": r["from"],
                "to": r["to"],
                "active": r.get("active", True) is not False,
                "crossFilter": "both" if str(r.get("crossFilter", "")).lower()
                in ("both", "bothdirections") else "single",
            }
            for r in spec.get("relationships", [])
        ),
        key=lambda x: (x["from"], x["to"]),
    )

    measures = sorted(
        (
            {
                "name": m["name"],
                "table": mt["name"],
                "expression": m["expression"],
                "format": m.get("format") or "",
                "displayFolder": mi.measure_folder(m),
                "hidden": mi.measure_hidden(m),
                "description": m.get("description", ""),
                "dependsOn": _measure_dependencies(m, spec),
            }
            for m in (mt or {}).get("measures", [])
        ),
        key=lambda x: x["name"].lower(),
    )
    return {
        "model": spec["name"],
        "generator": f"pbip-model-forge {__version__}",
        "tables": tables,
        "relationships": relationships,
        "measures": measures,
    }


# ---------------------------------------------------------------------------
# SPEC.md
# ---------------------------------------------------------------------------
def _mermaid_id(name: str) -> str:
    return re.sub(r"\W", "_", name)


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_spec_md(manifest: dict[str, Any]) -> str:
    """Render SPEC.md from a manifest dict."""
    out: list[str] = [f"# {manifest['model']}: model spec", ""]
    out.append(f"Generated by {manifest['generator']} from the model's spec dict. "
               "Regenerate it rather than editing it by hand.")
    out.append("")

    data = [t for t in manifest["tables"] if t["role"] != "measures"]
    rels = manifest["relationships"]
    fk_cols = {r["from"] for r in rels}

    out += ["## Diagram", "", "```mermaid", "erDiagram"]
    for r in rels:
        ft, fc = mi.split_ref(r["from"])
        tt, _ = mi.split_ref(r["to"])
        line = "||--o{" if r["active"] else "||..o{"
        out.append(f'    {_mermaid_id(tt)} {line} {_mermaid_id(ft)} : "{fc}"')
    for t in data:
        out.append(f"    {_mermaid_id(t['name'])} {{")
        for c in t["columns"]:
            tag = " PK" if c["key"] else (" FK" if f"{t['name']}.{c['name']}" in fk_cols else "")
            out.append(f"        {c['dataType']} {_mermaid_id(c['name'])}{tag}")
        out.append("    }")
    out += ["```", ""]

    out += ["## Tables", "", "| Table | Role | Description |", "|---|---|---|"]
    for t in manifest["tables"]:
        out.append(f"| {_cell(t['name'])} | {t['role']} | {_cell(t['description'])} |")
    out.append("")

    for t in data:
        out.append(f"### {t['name']}")
        out.append("")
        if t.get("description"):
            out += [t["description"], ""]
        if t.get("range"):
            out += [f"Range: {t['range']['start']} to {t['range']['end']}.", ""]
        out += ["| Column | Type | Key | Hidden | Format | Description |",
                "|---|---|---|---|---|---|"]
        for c in t["columns"]:
            key = "PK" if c["key"] else ("FK" if f"{t['name']}.{c['name']}" in fk_cols else "")
            out.append(f"| {_cell(c['name'])} | {c['dataType']} | {key} | "
                       f"{'yes' if c['hidden'] else ''} | {_cell(c['format'])} | "
                       f"{_cell(c['description'])} |")
        out.append("")

    out += ["## Relationships", "", "| From (many) | To (one) | Active | Filter |",
            "|---|---|---|---|"]
    for r in rels:
        out.append(f"| {_cell(r['from'])} | {_cell(r['to'])} | "
                   f"{'yes' if r['active'] else 'no'} | {r['crossFilter']} |")
    out.append("")

    out += ["## Measures", "", "| Measure | Folder | Format | Description | DAX |",
            "|---|---|---|---|---|"]
    for m in manifest["measures"]:
        expr = " ".join(m["expression"].split())
        out.append(f"| {_cell(m['name'])} | {_cell(m['displayFolder'])} | "
                   f"{_cell(m['format'])} | {_cell(m['description'])} | "
                   f"`{_cell(expr)}` |")
    out.append("")
    return "\n".join(out)


def write_handoff(spec: dict[str, Any], out_dir: str | Path) -> Path:
    """Write ``<out_dir>/handoff/manifest.json`` and ``SPEC.md``; returns the
    handoff folder."""
    folder = Path(out_dir) / "handoff"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(spec)
    (folder / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (folder / "SPEC.md").write_text(render_spec_md(manifest), encoding="utf-8")
    return folder
