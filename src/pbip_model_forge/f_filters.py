"""``pbip-forge f-filters``: fill gaps in the f-Filters gate table.

Background. A report built on the selector pattern has one hidden measure
``f-<Category>`` per analysis category in the ``f-Filters`` table. It returns
a positive number when the category's fact tables hold rows. The combined
measure ``f-All`` holds two chains of gate lines (``VAR temp_basic`` with
``&&`` and ``VAR temp_alt`` with ``||``), one pair per category, so the canvas
only offers categories that have data.

Two things drift as a model grows:

* a fact table is read by a user-facing measure but by no f- measure, so its
  category's gate ignores it;
* a category registered in the z-Map table has no gate line in ``f-All``.

This module finds both and repairs them by appending only: an f- measure is
created or has ``+ int(not ISEMPTY('<fact>'))`` terms added, and ``f-All``
gets new gate lines at the end of each chain. Existing lines are never
rewritten.

The analysis helpers (:func:`is_fact_table`, :func:`is_user_facing`,
:func:`uncovered_facts`, :func:`registered_categories`,
:func:`live_gate_names`, :func:`category_gated`, :func:`find_gate_measure`,
:func:`chain_text`) are public so a linter can use the same definitions as
the fixer.

Edits keep the file's bytes: line endings (LF or CRLF) and a UTF-8 BOM
survive, and the backup is a byte copy of the file before the edit.
"""

from __future__ import annotations

import datetime as _dt
import re
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from . import enter_data
from . import tmdl_text as tt

GATE_TABLE = "f-Filters"
COMBINED_MEASURE = "f-All"
MAP_TABLE = "z-Map Dimension-Measure Groupings"
MAP_TABLE_GLOB = "z-Map*.tmdl"
DISPLAY_FOLDER = "Visual-Level filters"
#: a created f- measure whose expression is this long or longer is fenced
INLINE_LIMIT = 100
#: the only files x-Selector entries are read from
SELECTOR_FILES = tuple(f"x-Selector {n}.tmdl" for n in range(1, 10))
#: z-Map group ids that never stand for an analysis category
IGNORED_GROUPS = frozenset({"Blank Measure_x", "Blank Dimension_y", "Date_y",
                            "Date_day_y", "Date_week_y"})
#: functions whose arguments only sense filter state, not data
SENSOR_FUNCTIONS = ("ISFILTERED", "ISINSCOPE", "ISEMPTY", "ISCROSSFILTERED",
                    "HASONEVALUE", "HASONEFILTER")

SKIP_REASON = ("consumed by user-facing measures but no z-Map mapping for any x-Selector "
               "category_x_id that reaches it (missing z-Map row, or candidate for removal)")
EXTEND_NOTE = ("If the existing measure is AGGREGATOR, SWITCH-ROUTER, or DISPLAY-STRING "
               "(per tmdl-preflight A005 f-measure-pattern), this append likely BROKE its "
               "semantics or DAX syntax. MANUAL VERIFY NOW before committing.")
NO_BASIC_WARNING = ("f-All temp_basic block not found — created f-<Cat> measures but didn't "
                    "extend the orchestrator. Either f-All is named/structured differently "
                    "here or this model doesn't use one.")
EXTENDED_BANNER = """
⚠️  ONE OR MORE EXISTING f-MEASURES WERE EXTENDED ABOVE.
    If any extended measure was AGGREGATOR / SWITCH-ROUTER /
    DISPLAY-STRING (not STANDARD), the append BROKE its
    semantics or DAX syntax. MANUAL VERIFY NOW.
"""
REVIEW_BLOCK = """
─── REVIEW REQUIRED ─────────────────────────────────────────────────────
This script only emits the STANDARD f-measure shape:
    int(not ISEMPTY('<FactTable>'))

Per tmdl-preflight A005 (f-measure-pattern), three other shapes exist:
  AGGREGATOR     [f-A] + [f-B]                       (combines refs)
  SWITCH-ROUTER  SWITCH(TRUE(), ...)                 (category dispatch)
  DISPLAY-STRING CONCATENATEX-based, in w-* tables   (visual labels)

The emitted STANDARD measures are CORRECT for any measure that should
existence-check a fact table. If any newly-created f-measure should
actually be one of the three non-STANDARD shapes, that emission is
WRONG and needs manual conversion.

Run the classifier:
  tmdl-preflight check <model> --select A005

Any measure flagged as unclassified is one this script emitted that needs
to be rewritten by hand.
─────────────────────────────────────────────────────────────────────────
"""
_NEW_MEASURE_PROPS = ("\t\tisHidden\n\t\tdisplayFolder: " + DISPLAY_FOLDER +
                      "\n\t\tlineageTag: {tag}\n\n"
                      '\t\tannotation PBI_FormatHint = {{"isGeneralNumber":true}}\n\n')
_GATE_INDENT = "\t\t\t        "


# ---------------------------------------------------------------------------
# Names and text helpers
# ---------------------------------------------------------------------------
_LETTER_DASH = re.compile(r"[A-Za-z]-")


def is_fact_table(name: str, text: str) -> bool:
    """A table that holds facts, judged by its name and its file text.

    Not a fact: names starting with ``_``, ``<letter>-`` or a character that
    is not a letter or digit, names containing the word Measure(s); tables
    without columns, calculation groups, field parameters, tables whose
    first partition is not an M partition and entered-data tables."""
    if not name or name.startswith("_") or _LETTER_DASH.match(name) or not name[0].isalnum():
        return False
    if re.search(r"\bmeasures?\b", name, re.I):
        return False
    if not tt.has_columns(text) or re.search(r"^\tcalculationGroup", text, re.M):
        return False
    if "groupByColumn" in text and re.search(r"sourceColumn:\s*\[Value\d+\]", text):
        return False
    first = re.search(r"^\tpartition\s.*?=\s*(\S+)", text, re.M)
    if first is None or first.group(1) != "m":
        return False
    return "Table.FromRows" not in text and "#table(" not in text


def is_user_facing(measure: str) -> bool:
    """Decided by name only: not ``-``/``_`` prefixed, not ``<letter>-``
    (except ``z-``), and no word starting with ``test``."""
    if measure.startswith(("-", "_")):
        return False
    if _LETTER_DASH.match(measure) and measure[0] != "z":
        return False
    return re.search(r"\btest", measure, re.I) is None


def strip_comments(dax: str, keep_strings: bool = True) -> str:
    """DAX without ``--``/``//`` line comments and ``/* */`` blocks. Text in
    ``'...'`` and ``"..."`` is never read as a comment; with
    ``keep_strings=False`` the contents of ``"..."`` literals are dropped."""
    out: list[str] = []
    pos, size = 0, len(dax)
    while pos < size:
        ch = dax[pos]
        if ch in "\"'":
            end = pos + 1
            while end < size:
                if dax[end] == ch:
                    if dax[end + 1:end + 2] == ch:
                        end += 2
                        continue
                    break
                end += 1
            piece = dax[pos:end + 1]
            out.append('""' if ch == '"' and not keep_strings else piece)
            pos = end + 1
        elif dax.startswith(("//", "--"), pos):
            nl = dax.find("\n", pos)
            pos = size if nl < 0 else nl
        elif dax.startswith("/*", pos):
            close = dax.find("*/", pos + 2)
            out.append(" ")
            pos = size if close < 0 else close + 2
        else:
            out.append(ch)
            pos += 1
    return "".join(out)


def _quoted(table: str) -> str:
    return "'" + table.replace("'", "''") + "'"


def _mentions_table(plain: str, table: str) -> bool:
    """``'T'``, ``[T]`` or (for a name without spaces) ``T[`` in ``plain``."""
    if _quoted(table) in plain or f"[{table}]" in plain:
        return True
    return " " not in table and re.search(rf"(?<![\w']){re.escape(table)}\[", plain) is not None


_SENSOR_RE = re.compile(r"\b(?:" + "|".join(SENSOR_FUNCTIONS) + r")\s*\(", re.I)


def _sensor_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for hit in _SENSOR_RE.finditer(text):
        start = hit.end() - 1
        depth, end = 0, len(text)
        for k in range(start, len(text)):
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    end = k
                    break
        spans.append((start, end))
    return spans


def data_reads(expression: str, table: str) -> bool:
    """True when ``expression`` reads ``table`` for its data, not only inside
    a filter-state sensor such as ``ISFILTERED(...)`` or ``ISEMPTY(...)``."""
    text = strip_comments(expression)
    patterns = [re.escape(_quoted(table))]
    if " " not in table and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        patterns.append(rf"(?<!\w){re.escape(table)}(?!\w)")
    spans = _sensor_spans(text)
    for pattern in patterns:
        for hit in re.finditer(pattern, text):
            if not any(a < hit.start() < b for a, b in spans):
                return True
    return False


# ---------------------------------------------------------------------------
# Model reading
# ---------------------------------------------------------------------------
@dataclass
class _Measure:
    table: str
    expression: str
    plain: str


def _tables(model_dir: Path) -> dict[str, str]:
    out = {}
    for path in tt.table_files(model_dir):
        text = path.read_text(encoding="utf-8-sig")
        out[tt.table_name(text) or path.stem] = text
    return out


def _measures(tables: dict[str, str]) -> dict[str, _Measure]:
    index: dict[str, _Measure] = {}
    for table, text in tables.items():
        lines = tt.split_lines(text.replace("\r\n", "\n"))
        for block in tt.measure_blocks(lines):
            expr = tt.expression(lines, block)
            index[block.name] = _Measure(table, expr, strip_comments(expr, keep_strings=False))
    return index


class _Reach:
    """Fact tables a measure reaches through its own text and the measures
    it references, transitively."""

    def __init__(self, index: dict[str, _Measure], facts: set[str]) -> None:
        self.index = index
        self.direct = {m: {f for f in facts if _mentions_table(v.plain, f)}
                       for m, v in index.items()}
        self.refs = {m: {r.strip() for r in re.findall(r"\[([^\]]+)\]", v.plain)
                         if r.strip() in index and r.strip() != m}
                     for m, v in index.items()}
        self._memo: dict[str, set[str]] = {}

    def __call__(self, measure: str) -> set[str]:
        if measure in self._memo:
            return self._memo[measure]
        found: set[str] = set()
        seen, stack = {measure}, [measure]
        while stack:
            current = stack.pop()
            found |= self.direct.get(current, set())
            for ref in self.refs.get(current, ()):
                if ref not in seen:
                    seen.add(ref)
                    stack.append(ref)
        self._memo[measure] = found
        return found


def _fenced_calculated_source(text: str) -> str | None:
    """The fenced source of the first ``calculated`` partition that has one."""
    lines = tt.split_lines(text.replace("\r\n", "\n"))
    i = 0
    while i < len(lines):
        head = re.match(r"^\tpartition\s.*?=\s*(\S+)", lines[i])
        if not head:
            i += 1
            continue
        j = i + 1
        body: list[str] = []
        while j < len(lines) and not re.match(r"^\t(?!\t)\S", lines[j]):
            body.append(lines[j])
            j += 1
        if head.group(1) == "calculated":
            for k, line in enumerate(body):
                if re.match(r"^\s*source\s*=\s*```\s*$", line):
                    inner = []
                    for rest in body[k + 1:]:
                        if rest.strip() == "```":
                            return "\n".join(inner)
                        inner.append(rest)
        i = j
    return None


_ENTRY_RE = re.compile(
    r'\(\s*"(?:[^"]|"")*"\s*,\s*NAMEOF\s*\(\s*(?:\'(?:[^\']|\'\')+\'\s*)?\[([^\]]+)\]\s*\)'
    r'\s*,\s*-?\d+\s*,\s*"((?:[^"]|"")*)"')


def selector_entries(model_dir: str | Path, measures: set[str] | None = None) -> list[tuple[str, str]]:
    """``(measure, group id)`` of every x-Selector 1..9 row whose measure exists.

    Only the fenced source of each file's first calculated partition is
    read; commented-out lines are ignored."""
    tables_dir = Path(model_dir) / "definition" / "tables"
    out = []
    for name in SELECTOR_FILES:
        path = tables_dir / name
        if not path.is_file():
            continue
        src = _fenced_calculated_source(path.read_text(encoding="utf-8-sig"))
        if src is None:
            continue
        src = "\n".join("" if re.match(r"^\s*(//|--)", ln) else ln for ln in src.split("\n"))
        for hit in _ENTRY_RE.finditer(src):
            measure = hit.group(1)
            if measures is None or measure in measures:
                out.append((measure, hit.group(2)))
    return out


def _cell(value: object) -> str:
    return "" if value is None else str(value).strip()


def group_categories(model_dir: str | Path) -> dict[str, set[str]]:
    """z-Map group id -> analysis categories (``{}`` on any failure)."""
    path = Path(model_dir) / "definition" / "tables" / f"{MAP_TABLE}.tmdl"
    try:
        b64 = enter_data.first_payload(path.read_text(encoding="utf-8-sig"))
        rows = enter_data.decode_base64(b64.strip())
        out: dict[str, set[str]] = {}
        for row in rows:
            if not isinstance(row, list) or len(row) < 3:
                continue
            category, group = _cell(row[0]), _cell(row[2])
            if category and group and group not in IGNORED_GROUPS:
                out.setdefault(group, set()).add(category)
        return out
    except Exception:  # any failure: no mapping at all
        return {}


def registered_categories(model_dir: str | Path) -> list[str]:
    """Distinct first-cell values of the first ``z-Map*`` table, sorted.

    The file must hold exactly one ``Binary.FromText("...")`` payload;
    otherwise (or on any decode failure) the list is empty and coverage
    enforcement is skipped."""
    files = sorted((Path(model_dir) / "definition" / "tables").glob(MAP_TABLE_GLOB))
    if not files:
        return []
    payloads = re.findall(r'Binary\.FromText\("([^"]*)"', files[0].read_text(encoding="utf-8-sig"))
    if len(payloads) != 1:
        return []
    try:
        rows = enter_data.decode_base64(payloads[0].strip())
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    return sorted({row[0] for row in rows
                   if isinstance(row, list) and row and isinstance(row[0], str) and row[0]})


#: older name of :func:`registered_categories`
map_table_categories = registered_categories


def uncovered_facts(model_dir: str | Path) -> dict[str, list[str]]:
    """Fact tables consumed by a user-facing measure, reached by no f-
    measure and not gated through the category mechanism, in name order,
    each with its sorted analysis categories (possibly none)."""
    model_dir = Path(model_dir)
    tables = _tables(model_dir)
    facts = {name for name, text in tables.items() if is_fact_table(name, text)}
    index = _measures(tables)
    reach = _Reach(index, facts)

    consumed: set[str] = set()
    covered: set[str] = set()
    for name in index:
        if is_user_facing(name):
            consumed |= reach(name)
        if name.startswith("f-"):
            covered |= reach(name)

    groups = group_categories(model_dir)
    categories: dict[str, set[str]] = {}
    gated: set[str] = set()
    for measure, group in selector_entries(model_dir, set(index)):
        cats = groups.get(group)
        if not cats:
            continue
        for fact in reach(measure):
            categories.setdefault(fact, set()).update(cats)
        if is_user_facing(measure):
            gated |= {f for f in facts if data_reads(index[measure].expression, f)}

    return {fact: sorted(categories.get(fact, ())) for fact in sorted(consumed - covered - gated)}


# ---------------------------------------------------------------------------
# f-All gate helpers
# ---------------------------------------------------------------------------
_GATE_LITERAL_RE = re.compile(r'CONTAINSSTRING\s*\(\s*all_cats\s*,\s*"((?:[^"]|"")*)"\s*\)', re.I)


def live_gate_names(text: str) -> list[str]:
    """The category text of every ``CONTAINSSTRING(all_cats, "...")`` test on
    a line that is not commented out (``//`` or ``--`` first), unescaped
    (``""`` read as ``"``), in order of first appearance, without repeats."""
    seen: list[str] = []
    for line in text.split("\n"):
        if line.lstrip().startswith(("//", "--")):
            continue
        for found in _GATE_LITERAL_RE.findall(line):
            lit = found.replace('""', '"')
            if lit not in seen:
                seen.append(lit)
    return seen


def category_gated(category: str, literals: list[str]) -> bool:
    """CONTAINSSTRING semantics: gated when any literal occurs in the name."""
    return any(lit in category for lit in literals)


def find_gate_measure(category: str, declared: set[str] | list[str]) -> str | None:
    """The f- measure that stands for ``category``, trying in turn
    ``f-<cat>``, ``f-<cat with spaces as _>`` and ``f-<cat without spaces>``."""
    known = set(declared)
    for spelling in (category, category.replace(" ", "_"), category.replace(" ", "")):
        if "f-" + spelling in known:
            return "f-" + spelling
    return None


def declared_measures(text: str) -> set[str]:
    """Measure names declared in a table file (quoted or bare)."""
    return set(tt.declared_measure_names(text))


_CHAIN_RE = {
    "temp_basic": re.compile(r"VAR\s+temp_basic\s*=.*?(?=\n\s*(?:VAR\s+temp_alt\b|RETURN\b))", re.S),
    "temp_alt": re.compile(r"VAR\s+temp_alt\s*=.*?(?=\n\s*(?:VAR\b|RETURN\b))", re.S),
}
_CHAIN_DECL_RE = {var: re.compile(rf"\bVAR\s+{var}\s*=") for var in _CHAIN_RE}


def chain_text(f_all_text: str, var: str) -> str | None:
    """One chain of ``f-All``: from ``VAR <var> =`` up to the line break
    before the next ``VAR temp_alt`` (for temp_basic) or ``VAR`` (for
    temp_alt) or ``RETURN``."""
    hit = _CHAIN_RE[var].search(f_all_text)
    return hit.group(0) if hit else None


def _f_all_bounds(text: str) -> tuple[int, int] | None:
    lines = tt.split_lines(text)
    block = next((b for b in tt.measure_blocks(lines) if b.name == COMBINED_MEASURE), None)
    if block is None:
        return None
    start = sum(len(ln) + 1 for ln in lines[:block.start])
    end = min(sum(len(ln) + 1 for ln in lines[:block.end]), len(text))
    return start, end


def dax_string(text: str) -> str:
    """A DAX string literal: ``"`` doubles inside the quotes."""
    return '"' + text.replace('"', '""') + '"'


def dax_measure_ref(name: str) -> str:
    """A DAX measure reference: ``]`` doubles inside the brackets."""
    return "[" + name.replace("]", "]]") + "]"


def gate_line(category: str, measure: str, chain: str) -> str:
    """The gate appended to ``temp_basic`` (``basic``) or ``temp_alt``,
    without its indentation."""
    op, default = ("&&", "TRUE()") if chain == "basic" else ("||", "FALSE()")
    return (f"{op} IF(CONTAINSSTRING(all_cats, {dax_string(category)}), "
            f"IF({dax_measure_ref(measure)} > 0, TRUE(), FALSE()), {default})")


@dataclass
class _Pass:
    status: str = "ok"           # ok | no_f_all | no_basic | no_alt | duplicate
    added: list[tuple[str, str]] = field(default_factory=list)
    gated: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def _gate_pass(text: str, categories: list[str], declared: set[str]) -> tuple[str, _Pass]:
    """Append one batch of gate lines (both chains) for ``categories``."""
    res = _Pass()
    bounds = _f_all_bounds(text)
    if bounds is None:
        res.status = "no_basic"
        return text, res
    lo, hi = bounds
    region = text[lo:hi]
    if any(len(_CHAIN_DECL_RE[v].findall(region)) > 1 for v in _CHAIN_RE):
        res.status = "duplicate"
        return text, res
    basic = _CHAIN_RE["temp_basic"].search(region)
    if basic is None:
        res.status = "no_basic"
        return text, res
    alt = _CHAIN_RE["temp_alt"].search(region)
    if alt is None:
        res.status = "no_alt"
        return text, res
    literals = live_gate_names(basic.group(0))
    for cat in categories:
        if category_gated(cat, literals):
            res.gated.append(cat)
            continue
        measure = find_gate_measure(cat, declared)
        if measure is None:
            res.unresolved.append(cat)
        else:
            res.added.append((cat, measure))
    if not res.added:
        return text, res
    edits = []
    for hit, chain in ((basic, "basic"), (alt, "alt")):
        new_lines = [_GATE_INDENT + gate_line(c, m, chain) for c, m in res.added]
        edits.append((hit.start(), hit.end(),
                      hit.group(0).rstrip() + "\n" + "\n".join(new_lines) + "\n\t\t\t"))
    for start, end, new in sorted(edits, reverse=True):
        region = region[:start] + new + region[end:]
    return text[:lo] + region + text[hi:], res


# ---------------------------------------------------------------------------
# Measure edits
# ---------------------------------------------------------------------------
def _term(table: str) -> str:
    return f"int(not ISEMPTY({_quoted(table)}))"


def _code_end(line: str) -> int:
    """Where a trailing ``//`` or ``--`` comment starts on a DAX line (the
    line's length when there is none). Text inside ``"..."`` strings and
    ``'...'`` or ``[...]`` names is not a comment."""
    pos, size = 0, len(line)
    while pos < size:
        ch = line[pos]
        if ch in "\"'[":
            close = "]" if ch == "[" else ch
            pos += 1
            while pos < size:
                if line[pos] == close:
                    if line[pos + 1:pos + 2] == close:   # doubled: escaped
                        pos += 2
                        continue
                    break
                pos += 1
        elif line.startswith(("//", "--"), pos):
            return pos
        pos += 1
    return size


def _append_terms(line: str, terms: str) -> str:
    """``line`` with ``terms`` after its code, before a trailing comment."""
    cut = _code_end(line)
    code, comment = line[:cut].rstrip(), line[cut:]
    return code + terms + (" " + comment if comment else "")


def _has_code(line: str) -> bool:
    return bool(strip_comments(line).strip())


def extend_measure(text: str, name: str, facts: list[str]) -> str:
    """``text`` with `` + int(not ISEMPTY('<fact>'))`` appended to measure
    ``name`` for each fact."""
    lines = tt.split_lines(text)
    block = next(b for b in tt.measure_blocks(lines) if b.name == name)
    terms = "".join(f" + {_term(f)}" for f in facts)
    if not block.expr_lines and not block.fenced:          # inline
        lines[block.start] = _append_terms(lines[block.start], terms)
        return "\n".join(lines)
    body = "\n".join(lines[k] for k in block.expr_lines).rstrip().split("\n")
    code = [k for k, ln in enumerate(body) if _has_code(ln)]
    target = code[-1] if code else len(body) - 1
    body[target] = _append_terms(body[target], terms)
    first = block.start + 1
    if block.fenced:
        fence = block.expr_lines[-1] + 1 if block.expr_lines else block.start + 1
        lines[first:fence + 1] = body + ["\t\t```"]
    else:
        lines[first:block.expr_lines[-1] + 1] = body
    return "\n".join(lines)


def new_measure_block(name: str, facts: list[str]) -> str:
    """The exact text of a created ``f-<Category>`` measure."""
    expr = " + ".join(_term(f) for f in facts)
    head = f"\tmeasure {_quoted(name)} = "
    if "\n" not in expr and len(expr) < INLINE_LIMIT:
        head += expr + "\n"
    else:
        head += "```\n\t\t\t" + expr + "\n\t\t```\n"
    tag = name.lower().replace(" ", "-") + "-auto-generated"
    return head + _NEW_MEASURE_PROPS.format(tag=tag)


def insert_measure(text: str, block: str) -> str:
    """Insert ``block`` before the table's navigation/result-type annotation,
    else before the final line break, else at the end."""
    found = [p for p in (text.find("\n\tannotation PBI_NavigationStepName"),
                         text.find("\n\tannotation PBI_ResultType")) if p >= 0]
    if found:
        pos = min(found)
    elif text.endswith("\n"):
        pos = len(text) - 1
    else:
        pos = len(text)
    return text[:pos] + "\n" + block + text[pos:]


# ---------------------------------------------------------------------------
# One model
# ---------------------------------------------------------------------------
@dataclass
class Result:
    model: Path
    ok: bool = True
    error: str | None = None
    created: dict[str, list[str]] = field(default_factory=dict)
    extended: dict[str, list[str]] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    #: pass 1: created categories that got gate lines / were already gated
    combined_gates_added: list[str] = field(default_factory=list)
    already_gated: list[str] = field(default_factory=list)
    #: pass 2: registered categories gated now (category, measure) / unresolved
    coverage_gates: list[tuple[str, str]] = field(default_factory=list)
    coverage_already: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    changed: bool = False
    backup: Path | None = None


def _say(*lines: str, err: bool = False) -> None:
    for line in lines:
        print(line, file=sys.stderr if err else sys.stdout)


def fill_gaps(model_dir: str | Path, dry_run: bool = False, backups: bool = True,
              verbose: bool = False) -> Result:
    """Plan and (unless ``dry_run``) apply the f-Filters gap fill for one model.

    Progress lines are printed as the work happens (more with ``verbose``)."""
    model_dir = Path(model_dir)
    res = Result(model_dir)
    gate_file = model_dir / "definition" / "tables" / f"{GATE_TABLE}.tmdl"
    if not gate_file.is_file():
        res.ok, res.error = False, f"{GATE_TABLE}.tmdl not found: {gate_file}"
        return res

    if verbose:
        _say("", f"── Loading model index from {model_dir}")
    uncovered = uncovered_facts(model_dir)
    if verbose:
        _say(f"   Uncovered fact tables: {len(uncovered)}")
    plan: dict[str, list[str]] = {}
    for fact, cats in uncovered.items():
        if not cats:
            res.skipped.append(fact)
        for cat in cats:
            plan.setdefault(cat, []).append(fact)
    if res.skipped and verbose:
        _say("", f"   Uncategorized (skipped): {len(res.skipped)}",
             *(f"     - {fact}" for fact in res.skipped))

    source = tt.read_source(gate_file)
    original = source.text
    text = original
    declared = declared_measures(text)

    for cat in sorted(plan):
        facts = sorted(plan[cat])
        name = f"f-{cat}"
        if name in declared:
            text = extend_measure(text, name, facts)
            res.extended[name] = facts
            items = " ".join(f"`+ {_term(f)}`" for f in facts)
            for err in (False, True):
                _say("", f"   ⚠️  EXTENDED {name} by appending {items}",
                     f"     {EXTEND_NOTE}", err=err)
        else:
            text = insert_measure(text, new_measure_block(name, facts))
            res.created[name] = facts
            declared.add(name)
            if verbose:
                _say("", f"   CREATE {name}", f"     dax: {' + '.join(_term(f) for f in facts)}")

    warned_duplicate = False

    def duplicate_warning(state: _Pass) -> None:
        nonlocal warned_duplicate
        if state.status == "duplicate" and not warned_duplicate:
            warned_duplicate = True
            _say(f"   WARNING: {COMBINED_MEASURE} declares a temp_basic or temp_alt chain more "
                 "than once; which chain to extend is ambiguous, no gate lines written")

    created_cats = sorted(name[2:] for name in res.created)
    if created_cats:
        text, first = _gate_pass(text, created_cats, declared)
        duplicate_warning(first)
        res.combined_gates_added = [c for c, _ in first.added]
        res.already_gated = list(first.gated)
        if first.status == "no_basic":
            _say("", f"   ⚠️  {NO_BASIC_WARNING}", err=True)
        if verbose and first.added:
            _say("", f"   f-All extended with {len(first.added)} new categor(ies): "
                 + ", ".join(res.combined_gates_added))
        if verbose and first.gated:
            _say(f"   f-All skipped {len(first.gated)} already-gated categor(ies): "
                 + ", ".join(first.gated),
                 "     (these categories already have an un-commented CONTAINSSTRING(all_cats, "
                 "...) gate, possibly under a non-canonical f-measure name)")

    registered = registered_categories(model_dir)
    if registered:
        text, second = _gate_pass(text, registered, declared)
        duplicate_warning(second)
        if second.status != "ok":
            second = _Pass(second.status, unresolved=list(registered))
        res.coverage_gates = list(second.added)
        res.coverage_already = list(second.gated)
        res.unresolved = list(second.unresolved)
        if verbose:
            _say("", f"   f-All coverage: {len(registered)} z-Map categor(ies), "
                 f"{len(second.added)} gate(s) added, {len(second.gated)} already gated, "
                 f"{len(second.unresolved)} unresolved",
                 *(f"      + gate {c} -> [{m}]" for c, m in second.added),
                 *(f"      ! {c}: registered in z-Map but no f- measure exists to gate it "
                   "— create one first" for c in second.unresolved))

    res.changed = text != original
    if not res.changed:
        if verbose:
            _say("", "   No changes needed.")
    elif dry_run:
        if verbose:
            _say("", f"── DRY-RUN: would write {gate_file}")
    else:
        if backups:
            stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            res.backup = gate_file.with_name(f"{gate_file.name}.backup_gapfill_{stamp}")
            shutil.copy2(gate_file, res.backup)
            if verbose:
                _say("", f"   backup: {res.backup.name}")
        tt.write_edit(source, text)
        if verbose:
            _say("", f"   Wrote {gate_file}")
    return res


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def _summary(res: Result) -> list[str]:
    if res.combined_gates_added or res.already_gated:
        fa = f"+{len(res.combined_gates_added)}"
        if res.already_gated:
            fa += f"/skip {len(res.already_gated)}"
    else:
        fa = "-"
    status = "OK" if res.ok else f"FAIL: {res.error or '(no msg)'}"
    out = [f"   created={len(res.created)} extended={len(res.extended)} "
           f"skipped={len(res.skipped)} f-All={fa}  -> {status}"]
    out += [f"     CREATE  {name}" for name in res.created]
    out += [f"     EXTEND  {name}  (+ {', '.join(facts)})" for name, facts in res.extended.items()]
    for fact in res.skipped:
        out += [f"     SKIP    {fact}", f"             {SKIP_REASON}"]
    out += [f"     f-All   {cat} already gated, no new line added" for cat in res.already_gated]
    return out


def run_cli(targets: list[tuple[str, Path]], dry_run: bool = False, backups: bool = True,
            verbose: bool = False) -> int:
    """Run the gap fill on ``(label, model folder)`` targets; 1 when any failed."""
    _say(f"f-filter update — {len(targets)} target(s); mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    failed = 0
    extended_any = False
    for label, path in targets:
        tables = Path(path) / "definition" / "tables"
        if not tables.is_dir():
            _say("", f"[SKIP] {label}: {tables} not found", err=True)
            failed += 1
            continue
        _say("", f"── {label}  ({Path(path).resolve()})")
        try:
            res = fill_gaps(path, dry_run=dry_run, backups=backups, verbose=verbose)
        except Exception as exc:  # one broken model must not stop the others
            if verbose:
                traceback.print_exc()
            res = Result(Path(path), ok=False, error=str(exc))
        _say(*_summary(res))
        failed += not res.ok
        extended_any = extended_any or bool(res.extended)
    if extended_any:
        sys.stderr.write(EXTENDED_BANNER + "\n")
    sys.stderr.write(REVIEW_BLOCK + "\n")
    return 1 if failed else 0
