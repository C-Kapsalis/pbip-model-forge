"""Facts about a spec dict shared by the builder, the checker and the hand-off pack.

Everything here is derived from the spec alone (no TMDL parsing):

    - table roles (fact / dimension / calendar / measures)
    - the generated ``__Calendar`` column catalog and its year range
    - the effective visibility of a column (spec value, else generator default)
    - the effective display folder of a measure (spec value, else by kind)

Keeping these in one place means the checker judges exactly what the builder
will emit.
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any, Iterable

DEFAULT_CALENDAR_NAME = "__Calendar"
DEFAULT_START_YEAR = 2024
DEFAULT_END_YEAR = 2025

NUMERIC_TYPES = {"int64", "int", "double", "number", "decimal"}
DATE_TYPES = {"datetime", "date"}

HELPER_FOLDER = "_Helpers"

# The generated calendar: (name, dataType, DAX for ADDCOLUMNS or None for the
# CALENDAR() Date column, formatString, sortByColumn, hidden, description).
CALENDAR_COLUMNS: list[dict[str, Any]] = [
    {"name": "Date", "dataType": "dateTime", "dax": None,
     "format": "Long Date", "sortBy": None, "hidden": False,
     "description": "One row per calendar day; the key every fact date joins to."},
    {"name": "Calendar Year", "dataType": "int64", "dax": "YEAR ( [Date] )",
     "format": "0", "sortBy": None, "hidden": False,
     "description": "Four-digit calendar year, e.g. 2024."},
    {"name": "Calendar Quarter", "dataType": "int64", "dax": "QUARTER ( [Date] )",
     "format": "0", "sortBy": None, "hidden": True,
     "description": "Quarter number 1-4; sort key for Quarter."},
    {"name": "Quarter", "dataType": "string", "dax": "\"Q\" & QUARTER ( [Date] )",
     "format": None, "sortBy": "Calendar Quarter", "hidden": False,
     "description": "Quarter label, Q1 to Q4."},
    {"name": "Calendar Month", "dataType": "int64", "dax": "MONTH ( [Date] )",
     "format": "0", "sortBy": None, "hidden": True,
     "description": "Month number 1-12; sort key for Calendar Month Name."},
    {"name": "Calendar Month Name", "dataType": "string",
     "dax": "FORMAT ( [Date], \"MMMM\" )",
     "format": None, "sortBy": "Calendar Month", "hidden": False,
     "description": "Full month name, e.g. January."},
    {"name": "Month Start", "dataType": "dateTime",
     "dax": "DATE ( YEAR ( [Date] ), MONTH ( [Date] ), 1 )",
     "format": "mmm yyyy", "sortBy": None, "hidden": False,
     "description": "First day of the month; use it for monthly trend axes."},
    {"name": "Year-Month", "dataType": "string",
     "dax": "FORMAT ( [Date], \"yyyy-mm\" )",
     "format": None, "sortBy": "Month Start", "hidden": False,
     "description": "Year and month as text, e.g. 2024-01; sorted by Month Start."},
    {"name": "Week Start", "dataType": "dateTime",
     "dax": "[Date] - WEEKDAY ( [Date], 2 ) + 1",
     "format": "yyyy-mm-dd", "sortBy": None, "hidden": False,
     "description": "Monday of the week the date falls in."},
    {"name": "Day of Week Number", "dataType": "int64",
     "dax": "WEEKDAY ( [Date], 2 )",
     "format": "0", "sortBy": None, "hidden": True,
     "description": "Day of week 1-7, Monday = 1; sort key for Day of Week."},
    {"name": "Day of Week", "dataType": "string",
     "dax": "FORMAT ( [Date], \"dddd\" )",
     "format": None, "sortBy": "Day of Week Number", "hidden": False,
     "description": "Day name, e.g. Monday; sorted Monday to Sunday."},
]

CALENDAR_HIERARCHY = ["Calendar Year", "Quarter", "Calendar Month Name", "Date"]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def type_key(keyword: str) -> str:
    return keyword.strip().lower()


def split_ref(ref: str) -> tuple[str, str]:
    """Split a relationship endpoint ``"Table.column"`` into its two parts."""
    table, _, column = ref.partition(".")
    return table, column


def as_date(value: Any) -> _dt.date | None:
    """Coerce a cell (date, datetime or ISO text) to a date, else None."""
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        try:
            return _dt.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def calendar_name(spec: dict[str, Any]) -> str | None:
    cal = spec.get("calendar")
    if not cal:
        return None
    return cal.get("name", DEFAULT_CALENDAR_NAME)


def measures_table_name(spec: dict[str, Any]) -> str | None:
    mt = spec.get("measures_table")
    return mt["name"] if mt else None


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
def infer_roles(spec: dict[str, Any]) -> dict[str, str]:
    """Map every table name to ``fact``, ``dimension``, ``calendar`` or
    ``measures``.

    A data table's explicit ``"role"`` wins. Otherwise a table on the ``to``
    side of any relationship is a dimension, a table only on the ``from`` side
    is a fact, and an unrelated table is treated as a dimension (the checker
    then reports it as disconnected).
    """
    rels = spec.get("relationships", [])
    to_tables = {split_ref(r["to"])[0] for r in rels}
    from_tables = {split_ref(r["from"])[0] for r in rels}
    roles: dict[str, str] = {}
    for t in spec.get("tables", []):
        name = t["name"]
        if t.get("role"):
            roles[name] = t["role"]
        elif name in to_tables:
            roles[name] = "dimension"
        elif name in from_tables:
            roles[name] = "fact"
        else:
            roles[name] = "dimension"
    cal = calendar_name(spec)
    if cal:
        roles[cal] = "calendar"
    mt = measures_table_name(spec)
    if mt:
        roles[mt] = "measures"
    return roles


def fact_date_values(spec: dict[str, Any]) -> Iterable[_dt.date]:
    """Every date value in the fact tables' date columns."""
    roles = infer_roles(spec)
    for t in spec.get("tables", []):
        if roles.get(t["name"]) != "fact":
            continue
        idx = [i for i, c in enumerate(t["columns"])
               if type_key(c["type"]) in DATE_TYPES]
        for row in t.get("rows", []):
            for i in idx:
                if i < len(row):
                    d = as_date(row[i])
                    if d is not None:
                        yield d


def calendar_years(spec: dict[str, Any]) -> tuple[int, int]:
    """The calendar's (start_year, end_year): the spec values when given, else
    inferred from the fact tables' date columns, else the defaults."""
    cal = spec.get("calendar") or {}
    start, end = cal.get("start_year"), cal.get("end_year")
    if start is None or end is None:
        dates = list(fact_date_values(spec))
        if start is None:
            start = min((d.year for d in dates), default=DEFAULT_START_YEAR)
        if end is None:
            end = max((d.year for d in dates), default=max(start, DEFAULT_END_YEAR))
    return int(start), int(end)


# ---------------------------------------------------------------------------
# Generator defaults
# ---------------------------------------------------------------------------
def relationship_from_columns(spec: dict[str, Any]) -> set[tuple[str, str]]:
    return {split_ref(r["from"]) for r in spec.get("relationships", [])}


def relationship_columns(spec: dict[str, Any]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in spec.get("relationships", []):
        out.add(split_ref(r["from"]))
        out.add(split_ref(r["to"]))
    return out


def column_defaults(spec: dict[str, Any], table: dict[str, Any],
                    col: dict[str, Any]) -> dict[str, bool]:
    """Effective ``hidden`` and ``mdx`` (isAvailableInMdx) for a data column.

    - ``key: True`` columns and relationship ``from`` columns are hidden.
    - Numeric fact columns that are neither keys nor relationship endpoints
      (the raw values measures aggregate) are hidden and get
      ``isAvailableInMdx: false``.
    An explicit spec ``hidden`` always wins.
    """
    tname, cname = table["name"], col["name"]
    role = infer_roles(spec).get(tname)
    rel_cols = relationship_columns(spec)
    is_rel_from = (tname, cname) in relationship_from_columns(spec)
    raw_value = (
        role == "fact"
        and type_key(col["type"]) in NUMERIC_TYPES
        and not col.get("key")
        and (tname, cname) not in rel_cols
    )
    hidden = bool(col.get("key")) or is_rel_from or raw_value
    if "hidden" in col:
        hidden = bool(col["hidden"])
    mdx = col.get("isAvailableInMdx", not raw_value)
    return {"hidden": hidden, "mdx": bool(mdx)}


_COUNT_EXPR = re.compile(r"^\s*(DISTINCTCOUNT|DISTINCTCOUNTNOBLANK|COUNTROWS|COUNTA?|COUNTX)\s*\(",
                         re.IGNORECASE)


def measure_kind(m: dict[str, Any]) -> str:
    """``Counts``, ``Ratios`` or ``Base``, from the measure name and DAX."""
    name = m["name"]
    expr = m.get("expression", "")
    fmt = m.get("format") or ""
    if name.rstrip().endswith("#") or _COUNT_EXPR.match(expr):
        return "Counts"
    if ("%" in name or "%" in fmt or re.search(r"\bDIVIDE\s*\(", expr, re.I)
            or re.match(r"^(Avg|Average)\b", name) or " per " in name):
        return "Ratios"
    return "Base"


def measure_folder(m: dict[str, Any]) -> str:
    if "displayFolder" in m:
        return m["displayFolder"] or ""
    if m.get("helper"):
        return HELPER_FOLDER
    return measure_kind(m)


def measure_hidden(m: dict[str, Any]) -> bool:
    if "hidden" in m:
        return bool(m["hidden"])
    return bool(m.get("helper"))
