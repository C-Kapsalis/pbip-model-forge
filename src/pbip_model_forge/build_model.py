"""Assemble a complete, openable PBIP from a plain-dict spec.

Given a spec describing data tables (columns + rows), an optional calculated
calendar, a measures table and relationships, ``build_pbip`` writes the full
artifact set the will-it-open playbook requires:

    <name>.pbip
    <name>.SemanticModel/
        .platform
        definition.pbism
        definition/database.tmdl
        definition/model.tmdl
        definition/relationships.tmdl
        definition/tables/*.tmdl
    <name>.Report/            (blank: .platform + definition.pbir only)

Everything is parametric. The output is designed to pass
``tmdl-preflight check`` with zero errors.

Spec shape (all keys except ``name``/``tables`` optional)::

    {
      "name": "Model",
      "tables": [
        {
          "name": "Products",
          "description": "Product catalog",   # optional -> /// doc comment
          "hidden": False,                       # optional
          "columns": [
            {"name": "product_id", "type": "int64", "key": True,
             "summarizeBy": "none", "format": None, "hidden": False},
            ...
          ],
          "rows": [[1, "Road Bike", 1200.0], ...],
        },
        ...
      ],
      "calendar": {"name": "__Calendar", "start_year": 2024, "end_year": 2025},
      "measures_table": {
        "name": "Key Measures",
        "description": "...",
        "measures": [
          {"name": "Revenue", "expression": "SUM(Sales[net_amount])",
           "format": "$ #,0.00", "description": "..."},
        ],
      },
      "relationships": [
        {"from": "Sales.product_id", "to": "Products.product_id",
         "active": True},
      ],
    }
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .enter_data import DUMMY_PARTITION_SOURCE, entered_data_source, resolve_type
from .blank_report import write_blank_report

_SIMPLE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _q(name: str) -> str:
    """Quote a TMDL object name if it is not a simple identifier."""
    if _SIMPLE_IDENT.match(name):
        return name
    return "'" + name.replace("'", "''") + "'"


def _uuid() -> str:
    return str(uuid.uuid4())


def _doc(text: str | None, indent: str = "") -> str:
    """Render an optional description as TMDL /// doc-comment lines."""
    if not text:
        return ""
    return "".join(f"{indent}/// {line}\n" for line in text.splitlines())


# ---------------------------------------------------------------------------
# Table renderers
# ---------------------------------------------------------------------------
def render_data_table(table: dict[str, Any]) -> str:
    """Render an import (M / entered-data) table file."""
    name = table["name"]
    cols = table["columns"]
    out: list[str] = []
    out.append(_doc(table.get("description")))
    out.append(f"table {_q(name)}\n")
    if table.get("hidden"):
        out.append("\tisHidden\n")
    out.append(f"\tlineageTag: {_uuid()}\n")
    out.append("\n")

    for col in cols:
        cname = col["name"]
        info = resolve_type(col["type"])
        out.append(_doc(col.get("description"), "\t"))
        out.append(f"\tcolumn {_q(cname)}\n")
        out.append(f"\t\tdataType: {info['dataType']}\n")
        if col.get("key"):
            out.append("\t\tisKey\n")
        if col.get("hidden"):
            out.append("\t\tisHidden\n")
        if col.get("format"):
            out.append(f"\t\tformatString: {col['format']}\n")
        out.append(f"\t\tlineageTag: {_uuid()}\n")
        out.append(f"\t\tsummarizeBy: {col.get('summarizeBy', 'none')}\n")
        out.append(f"\t\tsourceColumn: {cname}\n")
        out.append("\n")

    colnames = [c["name"] for c in cols]
    types = [c["type"] for c in cols]
    rows = table.get("rows", [])
    out.append(f"\tpartition {_q(name)} = m\n")
    out.append("\t\tmode: import\n")
    out.append("\t\tsource =\n")
    out.append(entered_data_source(colnames, types, rows) + "\n")
    out.append("\n")
    out.append("\tannotation PBI_NavigationStepName = Navigation\n")
    out.append("\n")
    out.append("\tannotation PBI_ResultType = Table\n")
    return "".join(out)


def render_measures_table(mt: dict[str, Any]) -> str:
    """Render a measures-only table with the mandated dummy partition."""
    name = mt["name"]
    out: list[str] = []
    out.append(_doc(mt.get("description")))
    out.append(f"table {_q(name)}\n")
    out.append(f"\tlineageTag: {_uuid()}\n")
    out.append("\n")

    for m in mt.get("measures", []):
        expr = m["expression"]
        out.append(_doc(m.get("description"), "\t"))
        if "\n" in expr:
            # multi-line measure: expression on following indented lines
            out.append(f"\tmeasure {_q(m['name'])} =\n")
            for line in expr.splitlines():
                out.append(f"\t\t\t{line}\n")
        else:
            out.append(f"\tmeasure {_q(m['name'])} = {expr}\n")
        if m.get("format"):
            out.append(f"\t\tformatString: {m['format']}\n")
        out.append(f"\t\tlineageTag: {_uuid()}\n")
        out.append("\n")

    out.append(f"\tpartition {_q(name)} = m\n")
    out.append("\t\tmode: import\n")
    out.append("\t\tsource =\n")
    out.append(DUMMY_PARTITION_SOURCE + "\n")
    out.append("\n")
    out.append("\tannotation PBI_NavigationStepName = Navigation\n")
    out.append("\n")
    out.append("\tannotation PBI_ResultType = Table\n")
    return "".join(out)


def render_calendar_table(cal: dict[str, Any]) -> str:
    """Render a self-contained calculated Calendar table (no PBI_ResultType)."""
    name = cal.get("name", "__Calendar")
    start = cal.get("start_year", 2024)
    end = cal.get("end_year", 2025)
    tags = [_uuid() for _ in range(9)]
    return f"""/// Central date dimension. Self-contained calculated table so it always
/// populates without an external source.
table {_q(name)}
\tlineageTag: {tags[0]}
\tdataCategory: Time

\tcolumn Date
\t\tdataType: dateTime
\t\tisKey
\t\tformatString: Long Date
\t\tlineageTag: {tags[1]}
\t\tsummarizeBy: none
\t\tsourceColumn: [Date]

\tcolumn 'Calendar Year'
\t\tdataType: int64
\t\tformatString: 0
\t\tlineageTag: {tags[2]}
\t\tsummarizeBy: none
\t\tsourceColumn: [Calendar Year]

\tcolumn 'Calendar Month'
\t\tdataType: int64
\t\tisHidden
\t\tformatString: 0
\t\tlineageTag: {tags[3]}
\t\tsummarizeBy: none
\t\tsourceColumn: [Calendar Month]

\tcolumn 'Calendar Month Name'
\t\tdataType: string
\t\tlineageTag: {tags[4]}
\t\tsummarizeBy: none
\t\tsourceColumn: [Calendar Month Name]
\t\tsortByColumn: 'Calendar Month'

\tcolumn 'Calendar Quarter'
\t\tdataType: int64
\t\tformatString: 0
\t\tlineageTag: {tags[5]}
\t\tsummarizeBy: none
\t\tsourceColumn: [Calendar Quarter]

\thierarchy 'Date Hierarchy'
\t\tlineageTag: {tags[6]}

\t\tlevel 'Calendar Year'
\t\t\tlineageTag: {_uuid()}
\t\t\tcolumn: 'Calendar Year'

\t\tlevel 'Calendar Quarter'
\t\t\tlineageTag: {_uuid()}
\t\t\tcolumn: 'Calendar Quarter'

\t\tlevel 'Calendar Month'
\t\t\tlineageTag: {_uuid()}
\t\t\tcolumn: 'Calendar Month'

\t\tlevel Date
\t\t\tlineageTag: {_uuid()}
\t\t\tcolumn: Date

\tpartition {_q(name)} = calculated
\t\tmode: import
\t\tsource =
\t\t\t\tADDCOLUMNS (
\t\t\t\t    CALENDAR ( DATE ( {start}, 1, 1 ), DATE ( {end}, 12, 31 ) ),
\t\t\t\t    "Calendar Year", YEAR ( [Date] ),
\t\t\t\t    "Calendar Month", MONTH ( [Date] ),
\t\t\t\t    "Calendar Month Name", FORMAT ( [Date], "MMMM" ),
\t\t\t\t    "Calendar Quarter", QUARTER ( [Date] )
\t\t\t\t)
"""


# ---------------------------------------------------------------------------
# Model-level files
# ---------------------------------------------------------------------------
def render_model_tmdl(all_table_names: list[str], import_table_names: list[str]) -> str:
    query_order = json.dumps(import_table_names, separators=(",", ""))
    refs = "\n".join(f"ref table {_q(n)}" for n in all_table_names)
    return f"""model Model
\tculture: en-US
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tdiscourageImplicitMeasures
\tsourceQueryCulture: en-US
\tdataAccessOptions
\t\tlegacyRedirects
\t\treturnErrorValuesAsNull

annotation PBI_QueryOrder = {query_order}

annotation __PBI_TimeIntelligenceEnabled = 0

annotation PBI_ProTooling = ["DevMode"]

{refs}
"""


def render_relationships(relationships: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for rel in relationships:
        from_tbl, from_col = rel["from"].split(".", 1)
        to_tbl, to_col = rel["to"].split(".", 1)
        lines = [f"relationship {_uuid()}"]
        if rel.get("active", True) is False:
            lines.append("\tisActive: false")
        lines.append(f"\tfromColumn: {_q(from_tbl)}.{_q(from_col)}")
        lines.append(f"\ttoColumn: {_q(to_tbl)}.{_q(to_col)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------
# Table names Power BI Desktop rejects on open ("Unsupported Table name
# '<name>' has been found in data model schema") — most notably the implicit
# measures container "Measures". Compared case-insensitively.
RESERVED_TABLE_NAMES = {"measures"}


def build_pbip(spec: dict[str, Any], out_dir: str | Path) -> Path:
    """Write the complete PBIP for ``spec`` under ``out_dir``. Returns the
    path to the ``.pbip`` file."""
    out_dir = Path(out_dir)
    name = spec["name"]
    sm_dir = out_dir / f"{name}.SemanticModel"
    defn = sm_dir / "definition"
    tables_dir = defn / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    data_tables = spec.get("tables", [])
    calendar = spec.get("calendar")
    measures_table = spec.get("measures_table")

    # Guard reserved table names up front — Power BI will not open a model
    # that contains one (e.g. a table literally named "Measures").
    _names = [t["name"] for t in data_tables]
    if calendar:
        _names.append(calendar.get("name", "__Calendar"))
    if measures_table:
        _names.append(measures_table["name"])
    for _n in _names:
        if _n.strip().lower() in RESERVED_TABLE_NAMES:
            raise ValueError(
                f"table name {_n!r} is reserved in Power BI — Desktop refuses "
                f"to open the model ('Unsupported Table name'). Rename it, e.g. "
                f"'Key Measures' or '<Domain> Measures'."
            )

    # Clean stale table files so a rebuild after a rename/removal (e.g. the
    # expand loop) never leaves an orphan the model no longer references.
    for _old in tables_dir.glob("*.tmdl"):
        _old.unlink()

    all_table_names: list[str] = []
    import_table_names: list[str] = []

    # Data tables
    for t in data_tables:
        (tables_dir / f"{t['name']}.tmdl").write_text(
            render_data_table(t), encoding="utf-8"
        )
        all_table_names.append(t["name"])
        import_table_names.append(t["name"])

    # Calendar (calculated) -- listed in refs but not in import query order
    if calendar:
        cname = calendar.get("name", "__Calendar")
        (tables_dir / f"{cname}.tmdl").write_text(
            render_calendar_table(calendar), encoding="utf-8"
        )
        all_table_names.append(cname)

    # Measures table
    if measures_table:
        (tables_dir / f"{measures_table['name']}.tmdl").write_text(
            render_measures_table(measures_table), encoding="utf-8"
        )
        all_table_names.append(measures_table["name"])
        import_table_names.append(measures_table["name"])

    # model.tmdl / database.tmdl / relationships.tmdl / definition.pbism
    (defn / "model.tmdl").write_text(
        render_model_tmdl(all_table_names, import_table_names), encoding="utf-8"
    )
    (defn / "database.tmdl").write_text(
        "database\n\tcompatibilityLevel: 1601\n\n", encoding="utf-8"
    )
    (defn / "relationships.tmdl").write_text(
        render_relationships(spec.get("relationships", [])), encoding="utf-8"
    )
    (sm_dir / "definition.pbism").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
                "version": "4.2",
                "settings": {"qnaLsdlSharingPermissions": 1},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (sm_dir / ".platform").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                "metadata": {"type": "SemanticModel", "displayName": name},
                "config": {"version": "2.0", "logicalId": _uuid()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Blank report
    write_blank_report(out_dir, name)

    # .pbip
    pbip_path = out_dir / f"{name}.pbip"
    pbip_path.write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
                "version": "1.0",
                "artifacts": [{"report": {"path": f"{name}.Report"}}],
                "settings": {"enableAutoRecovery": True},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return pbip_path
