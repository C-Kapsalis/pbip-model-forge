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
    <name>.Report/            (blank PBIR report: report.json, version.json, one empty page)
    handoff/                  (manifest.json + SPEC.md, see handoff.py)

Everything is parametric and deterministic: every lineageTag, relationship
name and logicalId is a UUID5 of the object's path in the model, so building
the same spec twice yields a byte-identical tree. The output is designed to
pass ``tmdl-preflight check`` with zero errors; ``pbip-forge check`` (see
check.py) judges the spec itself against the modeling rules.

Spec shape (all keys except ``name``/``tables`` optional)::

    {
      "name": "Model",
      "tables": [
        {
          "name": "Products",
          "description": "Product catalog.",   # optional -> /// doc comment
          "role": "dimension",                   # optional; inferred otherwise
          "hidden": False,                       # optional
          "columns": [
            {"name": "product_id", "type": "int64", "key": True,
             "summarizeBy": "none", "format": None, "hidden": False,
             "description": "..."},
            ...
          ],
          "rows": [[1, "Road Bike", 1200.0], ...],
        },
        ...
      ],
      # start_year / end_year are inferred from the fact date columns if omitted
      "calendar": {"name": "__Calendar", "start_year": 2024, "end_year": 2025},
      "measures_table": {
        "name": "Key Measures",
        "description": "...",
        "measures": [
          {"name": "Total Revenue", "expression": "SUM(Sales[net_amount])",
           "format": "$ #,0.00", "description": "...",
           "displayFolder": "Base",              # optional; default by kind
           "helper": False},                     # True -> hidden, _Helpers
        ],
      },
      "relationships": [
        {"from": "Sales.product_id", "to": "Products.product_id",
         "active": True},                        # "crossFilter": "both" allowed
      ],
    }

Generator defaults: ``key`` columns and relationship ``from`` columns are
hidden; numeric fact columns that are not keys or relationship endpoints are
hidden with ``isAvailableInMdx: false``; every measure gets a display folder
(``Counts`` / ``Ratios`` / ``Base`` unless the spec names one).
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .enter_data import DUMMY_PARTITION_SOURCE, entered_data_source, resolve_type
from .blank_report import write_blank_report
from . import model_info as mi

_SIMPLE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Fixed namespace for every generated identifier. Never change it: doing so
# changes every lineageTag in every model built from then on.
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/C-Kapsalis/pbip-model-forge")


def _q(name: str) -> str:
    """Quote a TMDL object name if it is not a simple identifier."""
    if _SIMPLE_IDENT.match(name):
        return name
    return "'" + name.replace("'", "''") + "'"


def stable_id(model: str, table: str, kind: str, name: str) -> str:
    """Deterministic UUID for one model object (lineageTag, logicalId, ...)."""
    return str(uuid.uuid5(NAMESPACE, f"{model}/{table}/{kind}/{name}"))


def _doc(text: str | None, indent: str = "") -> str:
    """Render an optional description as TMDL /// doc-comment lines.

    The lines are emitted directly above the declaration they document; a
    blank line between the two would orphan the comment."""
    if not text:
        return ""
    return "".join(f"{indent}/// {line}\n" for line in text.splitlines())


# ---------------------------------------------------------------------------
# Table renderers
# ---------------------------------------------------------------------------
def render_data_table(table: dict[str, Any], model: str = "Model",
                      spec: dict[str, Any] | None = None) -> str:
    """Render an import (M / entered-data) table file."""
    spec = spec if spec is not None else {"tables": [table]}
    name = table["name"]
    cols = table["columns"]
    out: list[str] = []
    out.append(_doc(table.get("description")))
    out.append(f"table {_q(name)}\n")
    if table.get("hidden"):
        out.append("\tisHidden\n")
    out.append(f"\tlineageTag: {stable_id(model, name, 'table', name)}\n")
    out.append("\n")

    for col in cols:
        cname = col["name"]
        info = resolve_type(col["type"])
        eff = mi.column_defaults(spec, table, col)
        out.append(_doc(col.get("description"), "\t"))
        out.append(f"\tcolumn {_q(cname)}\n")
        out.append(f"\t\tdataType: {info['dataType']}\n")
        if col.get("key"):
            out.append("\t\tisKey\n")
        if eff["hidden"]:
            out.append("\t\tisHidden\n")
        if not eff["mdx"]:
            out.append("\t\tisAvailableInMdx: false\n")
        if col.get("format"):
            out.append(f"\t\tformatString: {col['format']}\n")
        out.append(f"\t\tlineageTag: {stable_id(model, name, 'column', cname)}\n")
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


def render_measures_table(mt: dict[str, Any], model: str = "Model") -> str:
    """Render a measures-only table with the mandated dummy partition."""
    name = mt["name"]
    out: list[str] = []
    out.append(_doc(mt.get("description")))
    out.append(f"table {_q(name)}\n")
    out.append(f"\tlineageTag: {stable_id(model, name, 'table', name)}\n")
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
        if mi.measure_hidden(m):
            out.append("\t\tisHidden\n")
        folder = mi.measure_folder(m)
        if folder:
            out.append(f"\t\tdisplayFolder: {folder}\n")
        out.append(f"\t\tlineageTag: {stable_id(model, name, 'measure', m['name'])}\n")
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


def render_calendar_table(cal: dict[str, Any], model: str = "Model",
                          years: tuple[int, int] | None = None) -> str:
    """Render a self-contained calculated Calendar table (no PBI_ResultType).

    ``years`` is the (start, end) range; by default the calendar dict's
    ``start_year`` / ``end_year`` (see model_info.calendar_years for the
    inference build_pbip applies)."""
    name = cal.get("name", mi.DEFAULT_CALENDAR_NAME)
    if years is None:
        years = (cal.get("start_year", mi.DEFAULT_START_YEAR),
                 cal.get("end_year", mi.DEFAULT_END_YEAR))
    start, end = years
    out: list[str] = [
        "/// Central date dimension. Self-contained calculated table so it always\n",
        "/// populates without an external source.\n",
        f"table {_q(name)}\n",
        f"\tlineageTag: {stable_id(model, name, 'table', name)}\n",
        "\tdataCategory: Time\n",
        "\n",
    ]
    for col in mi.CALENDAR_COLUMNS:
        cname = col["name"]
        out.append(_doc(col["description"], "\t"))
        out.append(f"\tcolumn {_q(cname)}\n")
        out.append(f"\t\tdataType: {col['dataType']}\n")
        if cname == "Date":
            out.append("\t\tisKey\n")
        if col["hidden"]:
            out.append("\t\tisHidden\n")
        if col["format"]:
            out.append(f"\t\tformatString: {col['format']}\n")
        out.append(f"\t\tlineageTag: {stable_id(model, name, 'column', cname)}\n")
        out.append("\t\tsummarizeBy: none\n")
        out.append(f"\t\tsourceColumn: [{cname}]\n")
        if col["sortBy"]:
            out.append(f"\t\tsortByColumn: {_q(col['sortBy'])}\n")
        out.append("\n")

    hier = "Date Hierarchy"
    out.append(f"\thierarchy {_q(hier)}\n")
    out.append(f"\t\tlineageTag: {stable_id(model, name, 'hierarchy', hier)}\n")
    for level in mi.CALENDAR_HIERARCHY:
        out.append("\n")
        out.append(f"\t\tlevel {_q(level)}\n")
        out.append(f"\t\t\tlineageTag: {stable_id(model, name, 'level', hier + '/' + level)}\n")
        out.append(f"\t\t\tcolumn: {_q(level)}\n")
    out.append("\n")

    adds = [f'\t\t\t\t    "{c["name"]}", {c["dax"]}'
            for c in mi.CALENDAR_COLUMNS if c["dax"]]
    out.append(f"\tpartition {_q(name)} = calculated\n")
    out.append("\t\tmode: import\n")
    out.append("\t\tsource =\n")
    out.append("\t\t\t\tADDCOLUMNS (\n")
    out.append(f"\t\t\t\t    CALENDAR ( DATE ( {start}, 1, 1 ), DATE ( {end}, 12, 31 ) ),\n")
    out.append(",\n".join(adds) + "\n")
    out.append("\t\t\t\t)\n")
    return "".join(out)


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


def render_relationships(relationships: list[dict[str, Any]],
                         model: str = "Model") -> str:
    blocks: list[str] = []
    seen: dict[str, int] = {}
    for rel in relationships:
        from_tbl, from_col = rel["from"].split(".", 1)
        to_tbl, to_col = rel["to"].split(".", 1)
        key = f"{rel['from']}->{rel['to']}"
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            key = f"{key}#{seen[key]}"
        lines = [f"relationship {stable_id(model, '', 'relationship', key)}"]
        if rel.get("active", True) is False:
            lines.append("\tisActive: false")
        if str(rel.get("crossFilter", "")).lower() in ("both", "bothdirections"):
            lines.append("\tcrossFilteringBehavior: bothDirections")
        lines.append(f"\tfromColumn: {_q(from_tbl)}.{_q(from_col)}")
        lines.append(f"\ttoColumn: {_q(to_tbl)}.{_q(to_col)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------
# Table names Power BI Desktop rejects on open ("Unsupported Table name
# '<name>' has been found in data model schema"), most notably the implicit
# measures container "Measures". Compared case-insensitively.
RESERVED_TABLE_NAMES = {"measures"}


def build_pbip(spec: dict[str, Any], out_dir: str | Path, *,
               check: bool = False, profile: str = "mockup",
               handoff: bool = True) -> Path:
    """Write the complete PBIP for ``spec`` under ``out_dir``. Returns the
    path to the ``.pbip`` file.

    ``check=True`` runs ``pbip-forge check`` on the spec first (with the given
    ``profile``) and raises :class:`pbip_model_forge.check.SpecCheckError`,
    before writing anything, if any P0/P1 violation is found.
    ``handoff=True`` (the default) also writes ``<out_dir>/handoff/`` with
    ``manifest.json`` and ``SPEC.md``.
    """
    if check:
        from .check import SpecCheckError, blocking, check_spec

        found = check_spec(spec, profile=profile)
        if blocking(found):
            raise SpecCheckError(found, profile)

    out_dir = Path(out_dir)
    name = spec["name"]
    sm_dir = out_dir / f"{name}.SemanticModel"
    defn = sm_dir / "definition"
    tables_dir = defn / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    data_tables = spec.get("tables", [])
    calendar = spec.get("calendar")
    measures_table = spec.get("measures_table")

    # Guard reserved table names up front: Power BI will not open a model
    # that contains one (e.g. a table literally named "Measures").
    _names = [t["name"] for t in data_tables]
    if calendar:
        _names.append(calendar.get("name", mi.DEFAULT_CALENDAR_NAME))
    if measures_table:
        _names.append(measures_table["name"])
    for _n in _names:
        if _n.strip().lower() in RESERVED_TABLE_NAMES:
            raise ValueError(
                f"table name {_n!r} is reserved in Power BI; Desktop refuses "
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
            render_data_table(t, name, spec), encoding="utf-8"
        )
        all_table_names.append(t["name"])
        import_table_names.append(t["name"])

    # Calendar (calculated) -- listed in refs but not in import query order
    if calendar:
        cname = calendar.get("name", mi.DEFAULT_CALENDAR_NAME)
        (tables_dir / f"{cname}.tmdl").write_text(
            render_calendar_table(calendar, name, mi.calendar_years(spec)),
            encoding="utf-8",
        )
        all_table_names.append(cname)

    # Measures table
    if measures_table:
        (tables_dir / f"{measures_table['name']}.tmdl").write_text(
            render_measures_table(measures_table, name), encoding="utf-8"
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
        render_relationships(spec.get("relationships", []), name), encoding="utf-8"
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
                "config": {"version": "2.0",
                           "logicalId": stable_id(name, "", "platform", "SemanticModel")},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Blank report: a complete PBIR report with one empty page
    write_blank_report(out_dir, name,
                       logical_id=stable_id(name, "", "platform", "Report"),
                       page_id=stable_id(name, "", "page", "Page 1")
                       .replace("-", "")[:20])

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

    # Hand-off pack
    if handoff:
        from .handoff import write_handoff

        write_handoff(spec, out_dir)
    return pbip_path
