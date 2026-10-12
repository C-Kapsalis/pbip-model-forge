"""``pbip-forge check``: modeling best-practice rules, judged on the spec dict.

tmdl-preflight answers "will Power BI Desktop open this?". This module answers
the next question: "is this a model a data engineer can trust?". It reads the
spec dict (so sample rows are available) and reports :class:`Violation`
records with a rule id (``FM001``...), a severity and a concrete fix.

Severities:
    P0  the model is broken or computes wrong numbers
    P1  must be fixed before the model is handed off
    P2  advisory

Profiles:
    mockup   lenient: documentation and naming rules are advisory (P2)
    handoff  strict: documentation and naming rules are P1

The gate is **0 P0 and 0 P1** under the chosen profile. Every rule, with its
rationale and fix, is listed in ``RULES`` (``pbip-forge rules`` prints it).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

from . import model_info as mi
from .enter_data import resolve_type

PROFILES = ("mockup", "handoff")
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


@dataclass(frozen=True)
class Violation:
    rule: str
    severity: str
    object: str
    message: str
    fix: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def format(self) -> str:
        return (f"{self.severity} {self.rule} {self.object}: {self.message}\n"
                f"    fix: {self.fix}")


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    mockup: str
    handoff: str
    rationale: str
    fix: str

    def severity(self, profile: str) -> str:
        return self.handoff if profile == "handoff" else self.mockup


class SpecCheckError(ValueError):
    """Raised by ``build_pbip(..., check=True)`` when the gate fails."""

    def __init__(self, violations: list[Violation], profile: str = "mockup"):
        self.violations = violations
        self.profile = profile
        super().__init__(format_report(violations, profile))


# ---------------------------------------------------------------------------
# Rule catalog
# ---------------------------------------------------------------------------
_RULES = [
    Rule("FM001", "relationship-endpoints", "P0", "P0",
         "A relationship whose table or column does not exist cannot be built.",
         "Correct the table or column name in the relationship, or add the column."),
    Rule("FM002", "row-width", "P0", "P0",
         "Every sample row must have one value per declared column, or the "
         "entered-data partition loads shifted or missing values.",
         "Add or remove values so each row matches the column list."),
    Rule("FM003", "dimension-single-key", "P1", "P1",
         "A dimension needs exactly one key column for relationships to land on "
         "and for engineers to know its grain.",
         "Mark exactly one column with \"key\": True."),
    Rule("FM004", "key-unique-non-null", "P0", "P0",
         "The one side of a relationship must be unique and non-blank, or the "
         "relationship fails to refresh.",
         "Make every key value distinct and non-null."),
    Rule("FM005", "fk-orphans", "P1", "P1",
         "Fact rows whose foreign key matches no dimension key (or is null) "
         "land on the blank member and silently drop out of sliced totals.",
         "Add an 'Unknown' row (for example key -1) to the dimension and point "
         "unmatched or null foreign keys at it."),
    Rule("FM006", "key-type-match", "P0", "P0",
         "Relationship endpoints of different data types never match.",
         "Give the foreign key the same type as the key it points to."),
    Rule("FM007", "key-name-match", "P2", "P2",
         "A foreign key named exactly like its primary key makes the join "
         "obvious to everyone who reads the model.",
         "Rename one side so the FK and PK share a name."),
    Rule("FM008", "fact-calendar", "P1", "P1",
         "A fact without an active relationship to the calendar cannot be "
         "sliced by date.",
         "Add an active relationship from the fact's primary date column to "
         "__Calendar.Date (add a calendar to the spec if there is none)."),
    Rule("FM009", "dimension-connected", "P1", "P1",
         "A dimension that reaches no fact filters nothing; it is either dead "
         "weight or a missing relationship.",
         "Relate it to a fact (directly or through another dimension), or "
         "remove it."),
    Rule("FM010", "no-bidirectional", "P1", "P1",
         "Bidirectional filters create ambiguous paths and surprising totals.",
         "Use single-direction filtering; express the cross-filter in a measure "
         "(CROSSFILTER or TREATAS) where it is really needed."),
    Rule("FM011", "single-active-path", "P0", "P0",
         "Two active paths between the same tables make filter propagation "
         "ambiguous; Power BI deactivates one of them on its own.",
         "Mark all but one path \"active\": False and use USERELATIONSHIP in "
         "the measures that need the other."),
    Rule("FM012", "no-relationship-cycle", "P0", "P0",
         "A relationship cycle (A filters B filters ... filters A) cannot be "
         "resolved by the engine.",
         "Remove or reverse one relationship in the cycle."),
    Rule("FM013", "dax-references", "P0", "P0",
         "A DAX reference to a table, column or measure that does not exist "
         "makes the measure fail.",
         "Fix the name, or add the missing column or measure."),
    Rule("FM014", "fact-read-by-measure", "P1", "P1",
         "A fact no measure reads is dead weight, or the measures that should "
         "summarize it are missing. Filter sensors (ISFILTERED, ISEMPTY, "
         "ISINSCOPE, HASONEVALUE, ...) do not count as reads.",
         "Add at least one measure that aggregates the fact."),
    Rule("FM015", "ratio-grain", "P1", "P1",
         "A ratio whose denominator counts a dimension table ignores filters "
         "from the other dimensions (they filter the fact, not that "
         "dimension), so per-slice values are wrong.",
         "Count the entity from the fact's foreign key instead, for example "
         "DISTINCTCOUNT(Fact[fk])."),
    Rule("FM016", "measure-format", "P2", "P1",
         "A visible measure without a format string shows raw engine "
         "formatting (long decimals, no currency).",
         "Set \"format\" on the measure."),
    Rule("FM017", "measure-description", "P2", "P1",
         "Consumers read the description as the measure's definition; an "
         "empty or placeholder one leaves it ambiguous.",
         "Write a one-line description of at least 10 characters (no TBD/TODO)."),
    Rule("FM018", "measure-display-folder", "P2", "P1",
         "Display folders keep the field list navigable; the builder defaults "
         "to Counts / Ratios / Base, so this fires only on an explicit empty "
         "folder.",
         "Remove the empty \"displayFolder\" or name a folder."),
    Rule("FM019", "name-format-agreement", "P2", "P1",
         "The naming convention promises the format: 'X %' is a percentage, "
         "'X #' is a whole-number count.",
         "Use a percent format for '%' names and a whole-number format such "
         "as #,0 for '#' names (or rename the measure)."),
    Rule("FM020", "fact-dates-in-calendar", "P1", "P1",
         "Fact dates outside the calendar range join to nothing and vanish "
         "from date-sliced visuals.",
         "Widen the calendar's start_year/end_year, or omit them so they are "
         "inferred from the data."),
    Rule("FM021", "table-description", "P2", "P1",
         "A one-line table description tells engineers the grain and purpose.",
         "Set \"description\" on the table, e.g. 'One row per order line.'"),
    Rule("FM022", "column-description", "P2", "P2",
         "Visible columns are what report authors see; a description saves a "
         "trip to the source system.",
         "Set \"description\" on each visible column."),
]
RULES: dict[str, Rule] = {r.id: r for r in _RULES}

_PLACEHOLDERS = re.compile(r"^\s*(tbd|todo|fixme|xxx|placeholder|n/?a|-+|\.+)\s*\.?\s*$",
                           re.IGNORECASE)
_PLACEHOLDER_WORD = re.compile(r"\b(tbd|todo|fixme|xxx)\b", re.IGNORECASE)
_SENSOR_FUNCS = ("ISFILTERED", "ISCROSSFILTERED", "ISINSCOPE", "ISEMPTY",
                 "HASONEVALUE", "HASONEFILTER")
_SENSOR_CALL = re.compile(r"\b(?:" + "|".join(_SENSOR_FUNCS) + r")\s*\(", re.IGNORECASE)
_COUNT_CALL = re.compile(
    r"\b(DISTINCTCOUNT|DISTINCTCOUNTNOBLANK|COUNT|COUNTA|COUNTBLANK|COUNTROWS)\s*\(",
    re.IGNORECASE)
_WHOLE_FORMAT = re.compile(r"^[#,0]+$")


# ---------------------------------------------------------------------------
# DAX text helpers
# ---------------------------------------------------------------------------
def strip_dax(expr: str) -> str:
    """Blank out comments and string literals (keeping offsets stable)."""
    out: list[str] = []
    i, n = 0, len(expr)
    while i < n:
        two = expr[i:i + 2]
        if two in ("--", "//"):
            j = expr.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif two == "/*":
            j = expr.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(re.sub(r"[^\n]", " ", expr[i:j]))
            i = j
        elif expr[i] == '"':
            j = i + 1
            while j < n:
                if expr[j] == '"':
                    if j + 1 < n and expr[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            out.append('""' + " " * max(0, j - i - 1))
            i = j + 1
        else:
            out.append(expr[i])
            i += 1
    return "".join(out)


def _string_literals(expr: str) -> set[str]:
    return {m.group(1).replace('""', '"') for m in re.finditer(r'"((?:[^"]|"")*)"', expr)}


_QUOTED_REF = re.compile(r"'((?:[^']|'')+)'\s*\[([^\]]+)\]")
_UNQUOTED_REF = re.compile(r"(?<![\w'\]])([A-Za-z_][A-Za-z0-9_]*)\[([^\]]+)\]")
_QUOTED_TABLE = re.compile(r"'((?:[^']|'')+)'(?!\s*\[)")
_BARE_REF = re.compile(r"\[([^\]]+)\]")


def dax_references(expr: str) -> dict[str, list]:
    """Extract ``{"qualified": [(table, member)], "tables": [name],
    "bare": [member]}`` from a DAX expression (comments/strings removed)."""
    text = strip_dax(expr)
    qualified: list[tuple[str, str]] = []

    def _take(m: re.Match, table: str) -> str:
        qualified.append((table, m.group(2)))
        return " " * (m.end() - m.start())

    text = _QUOTED_REF.sub(lambda m: _take(m, m.group(1).replace("''", "'")), text)
    text = _UNQUOTED_REF.sub(lambda m: _take(m, m.group(1)), text)
    tables = [m.group(1).replace("''", "'") for m in _QUOTED_TABLE.finditer(text)]
    bare = [m.group(1) for m in _BARE_REF.finditer(text)]
    return {"qualified": qualified, "tables": tables, "bare": bare}


def _call_spans(text: str, call_re: re.Pattern) -> list[tuple[int, int, str]]:
    """(start, end, inner-text) of each ``FN( ... )`` call matched by call_re."""
    spans = []
    for m in call_re.finditer(text):
        i = m.end() - 1
        depth, j = 0, i
        while j < len(text):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        spans.append((m.start(), j + 1, text[i + 1:j]))
    return spans


def _split_args(inner: str) -> list[str]:
    args, depth, cur = [], 0, []
    for ch in inner:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    args.append("".join(cur))
    return [a.strip() for a in args]


def mentions_table(text: str, table: str) -> bool:
    """True if ``text`` (already comment/string-stripped) names ``table``.
    Bracket contents are ignored, so ``[Visits #]`` does not mention Visits."""
    text = re.sub(r"\[[^\]]*\]", "[]", text)
    if re.search(r"'" + re.escape(table.replace("'", "''")) + r"'", text):
        return True
    if _is_simple_ident(table):
        return re.search(r"(?<![\w'])" + re.escape(table) + r"(?![\w'])", text) is not None
    return False


def _is_simple_ident(name: str) -> bool:
    return re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) is not None


def reads_table(expr: str, table: str) -> bool:
    """True if ``expr`` reads data from ``table`` outside filter sensors."""
    text = strip_dax(expr)
    chars = list(text)
    for s, e, _ in _call_spans(text, _SENSOR_CALL):
        for k in range(s, e):
            chars[k] = " "
    return mentions_table("".join(chars), table)


# ---------------------------------------------------------------------------
# The checker
# ---------------------------------------------------------------------------
class _Ctx:
    def __init__(self, spec: dict[str, Any], profile: str):
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}; use one of {PROFILES}")
        self.spec = spec
        self.profile = profile
        self.out: list[Violation] = []
        self.roles = mi.infer_roles(spec)
        self.tables = {t["name"]: t for t in spec.get("tables", [])}
        self.cal = mi.calendar_name(spec)
        mt = spec.get("measures_table") or {}
        self.mt_name = mt.get("name")
        self.measures = list(mt.get("measures", []))
        self.measure_by_name = {m["name"]: m for m in self.measures}
        self.columns: dict[str, dict[str, dict[str, Any]]] = {
            n: {c["name"]: c for c in t["columns"]} for n, t in self.tables.items()
        }
        if self.cal:
            self.columns[self.cal] = {
                c["name"]: {"name": c["name"], "type": c["dataType"]}
                for c in mi.CALENDAR_COLUMNS
            }
        self.rels = list(spec.get("relationships", []))

    def add(self, rule: str, obj: str, message: str, fix: str | None = None) -> None:
        r = RULES[rule]
        self.out.append(Violation(rule, r.severity(self.profile), obj, message,
                                  fix or r.fix))

    def data_type(self, table: str, column: str) -> str | None:
        col = self.columns.get(table, {}).get(column)
        if col is None:
            return None
        t = col["type"]
        try:
            return resolve_type(t)["dataType"]
        except ValueError:
            return t

    def values(self, table: str, column: str) -> list[Any]:
        t = self.tables.get(table)
        if not t:
            return []
        names = [c["name"] for c in t["columns"]]
        if column not in names:
            return []
        i = names.index(column)
        return [row[i] if i < len(row) else None for row in t.get("rows", [])]

    def valid_rels(self) -> list[dict[str, Any]]:
        out = []
        for r in self.rels:
            ft, fc = mi.split_ref(r["from"])
            tt, tc = mi.split_ref(r["to"])
            if fc in self.columns.get(ft, {}) and tc in self.columns.get(tt, {}):
                out.append(r)
        return out


def _ref(table: str, member: str | None = None) -> str:
    q = f"'{table}'"
    return q if member is None else f"{q}[{member}]"


def _norm(v: Any) -> Any:
    """Compare key values across int/str sample data sensibly."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        return s
    return v


# -- structure ---------------------------------------------------------------
def _rule_endpoints(c: _Ctx) -> None:
    for r in c.rels:
        for side in ("from", "to"):
            t, col = mi.split_ref(r[side])
            if t not in c.columns:
                c.add("FM001", f"relationship {r['from']} -> {r['to']}",
                      f"{side} table {t!r} does not exist")
            elif col not in c.columns[t]:
                c.add("FM001", f"relationship {r['from']} -> {r['to']}",
                      f"{side} column {t}.{col} does not exist")


def _rule_row_width(c: _Ctx) -> None:
    for name, t in c.tables.items():
        width = len(t["columns"])
        for i, row in enumerate(t.get("rows", []), 1):
            if len(row) != width:
                c.add("FM002", _ref(name),
                      f"row {i} has {len(row)} values for {width} columns")


def _rule_keys(c: _Ctx) -> None:
    for name, t in c.tables.items():
        if c.roles.get(name) != "dimension":
            continue
        keys = [col["name"] for col in t["columns"] if col.get("key")]
        if len(keys) != 1:
            c.add("FM003", _ref(name),
                  f"dimension has {len(keys)} key columns"
                  + (f" ({', '.join(keys)})" if keys else ""))
    # uniqueness on every key column and every relationship 'to' column
    targets = {(n, col["name"]) for n, t in c.tables.items()
               for col in t["columns"] if col.get("key")}
    for r in c.valid_rels():
        tt, tc = mi.split_ref(r["to"])
        if tt in c.tables:
            targets.add((tt, tc))
    for tt, tc in sorted(targets):
        vals = [_norm(v) for v in c.values(tt, tc)]
        nulls = sum(1 for v in vals if v is None or v == "")
        seen, dups = set(), set()
        for v in vals:
            if v in seen:
                dups.add(v)
            seen.add(v)
        if nulls:
            c.add("FM004", _ref(tt, tc), f"{nulls} null key value(s)")
        if dups:
            c.add("FM004", _ref(tt, tc),
                  f"duplicate key value(s): {', '.join(map(str, sorted(dups, key=str)))}")


def _rule_fk_orphans(c: _Ctx) -> None:
    for r in c.valid_rels():
        ft, fc = mi.split_ref(r["from"])
        tt, tc = mi.split_ref(r["to"])
        if tt == c.cal or ft not in c.tables or tt not in c.tables:
            continue
        keys = {_norm(v) for v in c.values(tt, tc)}
        fks = [_norm(v) for v in c.values(ft, fc)]
        nulls = sum(1 for v in fks if v is None or v == "")
        orphans = sorted({v for v in fks if v not in (None, "") and v not in keys}, key=str)
        if nulls:
            c.add("FM005", _ref(ft, fc), f"{nulls} row(s) with a null foreign key to {tt}")
        if orphans:
            c.add("FM005", _ref(ft, fc),
                  f"value(s) {', '.join(map(str, orphans))} not found in {tt}[{tc}]")


def _rule_key_match(c: _Ctx) -> None:
    for r in c.valid_rels():
        ft, fc = mi.split_ref(r["from"])
        tt, tc = mi.split_ref(r["to"])
        a, b = c.data_type(ft, fc), c.data_type(tt, tc)
        obj = f"relationship {r['from']} -> {r['to']}"
        if a != b:
            c.add("FM006", obj, f"{ft}.{fc} is {a} but {tt}.{tc} is {b}")
        if tt != c.cal and fc != tc:
            c.add("FM007", obj, f"foreign key {fc!r} is named differently from key {tc!r}",
                  f"Rename {ft}.{fc} or {tt}.{tc} so both are {tc!r}.")


# -- graph -------------------------------------------------------------------
def _rule_calendar(c: _Ctx) -> None:
    facts = sorted(n for n, r in c.roles.items() if r == "fact")
    for f in facts:
        if not c.cal:
            c.add("FM008", _ref(f), "the spec has no calendar")
            continue
        ok = any(mi.split_ref(r["from"])[0] == f and mi.split_ref(r["to"])[0] == c.cal
                 and r.get("active", True) is not False for r in c.valid_rels())
        if not ok:
            c.add("FM008", _ref(f), f"no active relationship to {c.cal}")


def _rule_dimension_connected(c: _Ctx) -> None:
    facts = {n for n, r in c.roles.items() if r == "fact"}
    # a dimension reaches a fact if a fact filters-up to it through any chain
    up: dict[str, set[str]] = {}
    for r in c.valid_rels():
        up.setdefault(mi.split_ref(r["from"])[0], set()).add(mi.split_ref(r["to"])[0])
    reached: set[str] = set()
    stack = list(facts)
    while stack:
        t = stack.pop()
        for nxt in up.get(t, ()):
            if nxt not in reached:
                reached.add(nxt)
                stack.append(nxt)
    for n, role in sorted(c.roles.items()):
        if role == "dimension" and n not in reached:
            c.add("FM009", _ref(n), "dimension is not related to any fact")


def _rule_bidirectional(c: _Ctx) -> None:
    for r in c.rels:
        if str(r.get("crossFilter", "")).lower() in ("both", "bothdirections"):
            c.add("FM010", f"relationship {r['from']} -> {r['to']}",
                  "relationship filters in both directions")


def _rule_paths(c: _Ctx) -> None:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in c.valid_rels():
        if r.get("active", True) is False:
            continue
        a, b = find(mi.split_ref(r["from"])[0]), find(mi.split_ref(r["to"])[0])
        if a == b:
            c.add("FM011", f"relationship {r['from']} -> {r['to']}",
                  "creates a second active path between tables already connected")
        else:
            parent[a] = b
    # directed cycle over all relationships
    edges: dict[str, set[str]] = {}
    for r in c.valid_rels():
        edges.setdefault(mi.split_ref(r["from"])[0], set()).add(mi.split_ref(r["to"])[0])
    state: dict[str, int] = {}
    cycles: list[str] = []

    def visit(n: str, path: list[str]) -> None:
        state[n] = 1
        for m in sorted(edges.get(n, ())):
            if state.get(m) == 1:
                cycles.append(" -> ".join(path[path.index(m):] + [m]))
            elif m not in state:
                visit(m, path + [m])
        state[n] = 2

    for n in sorted(edges):
        if n not in state:
            visit(n, [n])
    for cyc in cycles:
        c.add("FM012", "relationships", f"cycle {cyc}")


# -- DAX ---------------------------------------------------------------------
def _rule_dax_refs(c: _Ctx) -> None:
    all_columns = {col for cols in c.columns.values() for col in cols}
    tables = set(c.columns) | ({c.mt_name} if c.mt_name else set())
    for m in c.measures:
        expr = m.get("expression", "")
        refs = dax_references(expr)
        aliases = _string_literals(expr)
        obj = _ref(c.mt_name or "?", m["name"])
        for t, member in refs["qualified"]:
            if t not in tables:
                c.add("FM013", obj, f"unknown table {t!r} in {t}[{member}]")
            elif member not in c.columns.get(t, {}) and not (
                    t == c.mt_name and member in c.measure_by_name):
                c.add("FM013", obj, f"unknown column or measure {t}[{member}]")
        for t in refs["tables"]:
            if t not in tables:
                c.add("FM013", obj, f"unknown table '{t}'")
        for member in refs["bare"]:
            if (member not in c.measure_by_name and member not in all_columns
                    and member not in aliases):
                c.add("FM013", obj, f"unknown measure [{member}]")


def _rule_fact_read(c: _Ctx) -> None:
    exprs = [m.get("expression", "") for m in c.measures]
    for n, role in sorted(c.roles.items()):
        if role == "fact" and not any(reads_table(e, n) for e in exprs):
            c.add("FM014", _ref(n), "no measure reads this fact")


_LEADING_TABLE = re.compile(r"^(?:[A-Za-z]+\s*\(\s*)*('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)")


def _counted_tables(expr: str, c: _Ctx, depth: int = 0) -> set[str]:
    """Tables a (denominator) expression counts rows or values of: the table
    named by the first argument of each COUNT-family call, following measure
    references a few levels deep."""
    text = strip_dax(expr)
    found: set[str] = set()
    for _, _, inner in _call_spans(text, _COUNT_CALL):
        first = _split_args(inner)[0]
        refs = dax_references(first)
        for t, _member in refs["qualified"]:
            found.add(t)
        lead = _LEADING_TABLE.match(first)
        if lead:
            name = lead.group(1)
            if name.startswith("'"):
                name = name[1:-1].replace("''", "'")
            if name in c.tables:
                found.add(name)
    if depth < 4:
        for member in dax_references(text)["bare"]:
            m = c.measure_by_name.get(member)
            if m:
                found |= _counted_tables(m.get("expression", ""), c, depth + 1)
    return found


def _rule_ratio_grain(c: _Ctx) -> None:
    for m in c.measures:
        text = strip_dax(m.get("expression", ""))
        for _, _, inner in _call_spans(text, re.compile(r"\bDIVIDE\s*\(", re.I)):
            args = _split_args(inner)
            if len(args) < 2:
                continue
            for t in sorted(_counted_tables(args[1], c)):
                if c.roles.get(t) != "dimension":
                    continue
                fk = next((mi.split_ref(r["from"]) for r in c.valid_rels()
                           if mi.split_ref(r["to"])[0] == t
                           and c.roles.get(mi.split_ref(r["from"])[0]) == "fact"), None)
                hint = (f"Count from the fact instead: DISTINCTCOUNT({fk[0]}[{fk[1]}])."
                        if fk else None)
                c.add("FM015", _ref(c.mt_name or "?", m["name"]),
                      f"DIVIDE denominator counts dimension table {t!r}, so filters "
                      f"from other dimensions do not reach it", hint)


# -- documentation and naming -----------------------------------------------
def _bad_description(text: str | None) -> str | None:
    if not text or not text.strip():
        return "missing description"
    if len(text.strip()) < 10:
        return f"description {text!r} is shorter than 10 characters"
    if _PLACEHOLDERS.match(text) or _PLACEHOLDER_WORD.search(text):
        return f"description {text!r} is a placeholder"
    return None


def _rule_measure_docs(c: _Ctx) -> None:
    for m in c.measures:
        if mi.measure_hidden(m):
            continue
        obj = _ref(c.mt_name or "?", m["name"])
        fmt = (m.get("format") or "").strip()
        if not fmt:
            c.add("FM016", obj, "visible measure has no format string")
        problem = _bad_description(m.get("description"))
        if problem:
            c.add("FM017", obj, problem)
        if not mi.measure_folder(m):
            c.add("FM018", obj, "visible measure has an empty display folder")
        name = m["name"]
        if "%" in name and fmt and "%" not in fmt:
            c.add("FM019", obj, f"name contains '%' but format {fmt!r} is not a percentage")
        if re.search(r"(^#\s|\s#$)", name) and fmt and not _WHOLE_FORMAT.match(fmt):
            c.add("FM019", obj, f"'#' count but format {fmt!r} is not a whole number")
        if "%" in fmt and "%" not in name:
            c.out.append(Violation("FM019", "P2", obj,
                                   f"percent format {fmt!r} but the name has no '%'",
                                   "Name percentages 'X %' so the unit is visible."))


def _rule_fact_dates(c: _Ctx) -> None:
    if not c.cal:
        return
    start, end = mi.calendar_years(c.spec)
    for n, t in sorted(c.tables.items()):
        if c.roles.get(n) != "fact":
            continue
        for i, col in enumerate(t["columns"]):
            if mi.type_key(col["type"]) not in mi.DATE_TYPES:
                continue
            outside = sorted({d for d in (mi.as_date(r[i]) for r in t.get("rows", [])
                                          if i < len(r))
                              if d is not None and not (start <= d.year <= end)})
            if outside:
                c.add("FM020", _ref(n, col["name"]),
                      f"{len(outside)} date(s) outside {start}-{end}, e.g. {outside[0]}")


def _rule_table_docs(c: _Ctx) -> None:
    named = list(c.tables.values())
    mt = c.spec.get("measures_table")
    if mt:
        named.append(mt)
    for t in named:
        problem = _bad_description(t.get("description"))
        if problem:
            c.add("FM021", _ref(t["name"]), problem)
    for n, t in sorted(c.tables.items()):
        for col in t["columns"]:
            if mi.column_defaults(c.spec, t, col)["hidden"] or t.get("hidden"):
                continue
            if _bad_description(col.get("description")):
                c.add("FM022", _ref(n, col["name"]), "visible column has no description")


_CHECKS: list[Callable[[_Ctx], None]] = [
    _rule_endpoints, _rule_row_width, _rule_keys, _rule_fk_orphans,
    _rule_key_match, _rule_calendar, _rule_dimension_connected,
    _rule_bidirectional, _rule_paths, _rule_dax_refs, _rule_fact_read,
    _rule_ratio_grain, _rule_measure_docs, _rule_fact_dates, _rule_table_docs,
]


def check_spec(spec: dict[str, Any], profile: str = "mockup") -> list[Violation]:
    """Run every rule on ``spec``; returns violations sorted by severity,
    rule and object."""
    ctx = _Ctx(spec, profile)
    for fn in _CHECKS:
        fn(ctx)
    return sorted(ctx.out, key=lambda v: (SEVERITY_ORDER[v.severity], v.rule, v.object,
                                          v.message))


def blocking(violations: Iterable[Violation]) -> list[Violation]:
    """The P0/P1 violations: the ones that fail the gate."""
    return [v for v in violations if v.severity in ("P0", "P1")]


def format_report(violations: list[Violation], profile: str) -> str:
    counts = {s: sum(1 for v in violations if v.severity == s) for s in SEVERITY_ORDER}
    lines = [v.format() for v in violations]
    lines.append(f"pbip-forge check ({profile}): {counts['P0']} P0, "
                 f"{counts['P1']} P1, {counts['P2']} P2")
    return "\n".join(lines)


def format_rules() -> str:
    lines = []
    for r in _RULES:
        lines.append(f"{r.id}  {r.name:<26} mockup {r.mockup}  handoff {r.handoff}")
        lines.append(f"      {r.rationale}")
        lines.append(f"      fix: {r.fix}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
