"""``pbip-forge f-filters``: fill gaps in the f-Filters gate table.

Background. A report built on the selector pattern has one hidden measure
``f-<Category>`` per analysis category in the ``f-Filters`` table. It returns
a positive number when the category's fact tables hold rows. The combined
measure ``f-All`` holds two chains of gate lines (``VAR temp_basic`` with
``&&`` and ``VAR temp_alt`` with ``||``), one pair per category, so the canvas
only offers categories that have data.

Two things drift as a model grows:

* a fact table is read by a visible measure but by no f- measure, so its
  category's gate ignores it;
* a category registered in the z-Map table has no gate line in ``f-All``.

This module finds both and repairs them by appending only: an f- measure is
created or has ``+ int(not ISEMPTY('<fact>'))`` terms added, and ``f-All``
gets new gate lines at the end of each chain. Existing lines are never
rewritten.

The detection helpers (:func:`gate_literals`, :func:`category_gated`,
:func:`resolve_f_measure`, :func:`declared_measures`,
:func:`zmap_categories`, :func:`chain_span`, :func:`uncovered_facts`) are
public so a linter can use the same definitions as the fixer.
"""

from __future__ import annotations

import datetime as _dt
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import enter_data
from . import tmdl_text as tt

GATE_TABLE = "f-Filters"
COMBINED_MEASURE = "f-All"
MAP_TABLE_GLOB = "z-Map*.tmdl"
DISPLAY_FOLDER = "Visual-Level filters"
#: an f- measure expression longer than this is written in a ``` fence
INLINE_LIMIT = 100

_HELPER_PREFIXES = ("x-", "y-", "z-", "f-", "i-", "__")
_GATE_LITERAL_RE = re.compile(r'CONTAINSSTRING\s*\(\s*all_cats\s*,\s*"([^"]*)"\s*\)', re.I)
_SHAPE_WARNING = ("non-standard f- measure shapes (an aggregator, a SWITCH router or a "
                  "display-string measure) may now be broken; review every extended measure")


# ---------------------------------------------------------------------------
# Shared detection helpers
# ---------------------------------------------------------------------------
def _is_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("//") or s.startswith("--")


def gate_literals(text: str) -> list[str]:
    """Every ``CONTAINSSTRING(all_cats, "<literal>")`` literal on a live line.

    Lines whose first non-blank characters are ``//`` or ``--`` are skipped.
    Order of first appearance; duplicates dropped."""
    seen: list[str] = []
    for line in text.split("\n"):
        if _is_comment(line):
            continue
        for lit in _GATE_LITERAL_RE.findall(line):
            if lit not in seen:
                seen.append(lit)
    return seen


def category_gated(category: str, literals: list[str]) -> bool:
    """CONTAINSSTRING semantics: gated when any literal occurs in the name."""
    return any(lit and lit in category for lit in literals)


def resolve_f_measure(category: str, declared: set[str] | list[str]) -> str | None:
    """The f- measure that stands for ``category``, trying in turn
    ``f-<cat>``, ``f-<cat with spaces as _>`` and ``f-<cat without spaces>``."""
    words = category.split(" ")
    spellings = (category, "_".join(words), "".join(words))
    known = set(declared)
    return next(("f-" + s for s in spellings if "f-" + s in known), None)


def declared_measures(text: str) -> set[str]:
    """Measure names declared in a table file (quoted or bare)."""
    return set(tt.declared_measure_names(text))


def chain_span(lines: list[str], var: str) -> tuple[int, int] | None:
    """``(first, last)`` line indices of one ``VAR <var> =`` chain.

    The chain ends at the last non-blank line before the next ``VAR`` or
    ``RETURN`` (or the closing fence)."""
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^\s*VAR\s+{re.escape(var)}\s*=", line):
            start = i
            break
    if start is None:
        return None
    last = start
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if re.match(r"^(VAR|RETURN)\b", s) or s == "```" or (lines[j] and not lines[j].startswith("\t\t")):
            break
        if s:
            last = j
    return start, last


def _map_columns(text: str) -> tuple[int, int]:
    """Indices of the category and group columns of the map table."""
    names = list(tt.column_props(text))
    cat = next((i for i, n in enumerate(names) if n.lower() == "analysis category"), 0)
    group = next((i for i, n in enumerate(names) if "group" in n.lower() and i != cat),
                 max(len(names) - 1, 0))
    return cat, group


def map_rows(model_dir: str | Path) -> tuple[list[list], int, int]:
    """Decoded rows of the first z-Map table, with category/group indices.

    Any failure (no table, no payload, corrupt payload) gives no rows. A row
    that repeats the column names is not a mapping and is dropped."""
    files = sorted((Path(model_dir) / "definition" / "tables").glob(MAP_TABLE_GLOB))
    if not files:
        return [], 0, 0
    text = files[0].read_text(encoding="utf-8")
    b64 = enter_data.first_payload(text)
    rows = enter_data.decode_b64_or_none(b64) if b64 else None
    if not rows:
        return [], 0, 0
    names = list(tt.column_props(text))
    cat, group = _map_columns(text)
    clean = [r for r in rows if isinstance(r, list) and r != names]
    return clean, cat, group


def zmap_categories(model_dir: str | Path) -> list[str]:
    """Distinct analysis categories in the first z-Map table ([] on failure)."""
    rows, cat, _ = map_rows(model_dir)
    out: list[str] = []
    for row in rows:
        value = row[cat] if cat < len(row) else None
        if isinstance(value, str) and value.strip() and value not in out:
            out.append(value)
    return out


@dataclass
class _Table:
    name: str
    path: Path
    text: str


def _load_tables(model_dir: Path) -> list[_Table]:
    out = []
    for path in tt.table_files(model_dir):
        text = path.read_text(encoding="utf-8")
        out.append(_Table(tt.table_name(text) or path.stem, path, text))
    return out


def _one_side_tables(model_dir: Path) -> tuple[set[str], set[str]]:
    """Tables on the `to` (one) side and on the `from` side of relationships."""
    rel = model_dir / "definition" / "relationships.tmdl"
    to_side, from_side = set(), set()
    if rel.is_file():
        for kind, ref in re.findall(r"^\s*(fromColumn|toColumn):\s*(.+?)\s*$",
                                    rel.read_text(encoding="utf-8"), re.M):
            table = tt.unquote(ref.rsplit(".", 1)[0]) if "." in ref else ref
            (to_side if kind == "toColumn" else from_side).add(table)
    return to_side, from_side


def _is_fact_candidate(table: _Table, to_side: set[str], from_side: set[str]) -> bool:
    """A data table that can hold facts: it has columns, it is loaded rather
    than calculated, it is not a helper (selector, map, gate, caption or
    date-spine) table, and it is not purely the one side of relationships."""
    if table.name.startswith(_HELPER_PREFIXES) or not tt.has_columns(table.text):
        return False
    if re.search(r"^\tpartition\s.*=\s*calculated\s*$", table.text, re.M):
        return False
    return not (table.name in to_side and table.name not in from_side)


def _measure_index(tables: list[_Table]) -> dict[str, dict]:
    """Measure name -> {table, hidden, expr, tables (direct), measures (refs)}."""
    index: dict[str, dict] = {}
    for table in tables:
        lines = tt.split_lines(table.text)
        for block in tt.measure_blocks(lines):
            expr = tt.expression(lines, block)
            plain = tt.strip_comments_and_strings(expr)
            index[block.name] = {
                "table": table.name,
                "hidden": block.hidden,
                "tables": tt.table_refs(expr),
                "measures": set(re.findall(r"(?<![\w'\]])\[([^\]]+)\]", plain)),
            }
    return index


def _reach(name: str, index: dict[str, dict], seen: set[str] | None = None) -> set[str]:
    """Tables a measure reads, following measure references."""
    seen = set() if seen is None else seen
    if name in seen or name not in index:
        return set()
    seen.add(name)
    found = set(index[name]["tables"])
    for ref in index[name]["measures"]:
        found |= _reach(ref, index, seen)
    return found


def uncovered_facts(model_dir: str | Path, gate_table: str = GATE_TABLE) -> dict[str, list[str]]:
    """Fact tables read by a visible measure but by no f- measure.

    Maps each such table to its analysis categories (possibly none): the
    categories of the z-Map rows whose group id matches an x- selector entry
    whose measure reads the table."""
    model_dir = Path(model_dir)
    tables = _load_tables(model_dir)
    index = _measure_index(tables)
    to_side, from_side = _one_side_tables(model_dir)
    facts = {t.name for t in tables if _is_fact_candidate(t, to_side, from_side)}

    read_by_visible, read_by_gate = set(), set()
    for measure in index:
        meta = index[measure]
        hits = facts.intersection(_reach(measure, index))
        is_gate = measure.startswith("f-") and meta["table"] == gate_table
        if is_gate:
            read_by_gate.update(hits)
        elif not meta["hidden"]:
            read_by_visible.update(hits)

    # group id -> categories
    rows, cat_i, group_i = map_rows(model_dir)
    by_group: dict[str, list[str]] = {}
    for row in rows:
        if max(cat_i, group_i) < len(row):
            cat, group = row[cat_i], row[group_i]
            if isinstance(cat, str) and cat and isinstance(group, str) and group:
                by_group.setdefault(group, [])
                if cat not in by_group[group]:
                    by_group[group].append(cat)

    # fact -> categories via x- selector entries
    fact_cats: dict[str, list[str]] = {}
    for table in tables:
        if not table.name.startswith("x-"):
            continue
        for fields in tt.selector_rows(table.text):
            target = next((tt.nameof_target(f) for f in fields if tt.nameof_target(f)), None)
            group = tt.string_literal(fields[3]) if len(fields) > 3 else None
            if target is None or not group:
                continue
            for fact in _reach(target[1], index) & facts:
                for cat in by_group.get(group, []):
                    fact_cats.setdefault(fact, [])
                    if cat not in fact_cats[fact]:
                        fact_cats[fact].append(cat)

    return {fact: fact_cats.get(fact, []) for fact in sorted(read_by_visible - read_by_gate)}


# ---------------------------------------------------------------------------
# Edits
# ---------------------------------------------------------------------------
def repr_table(table: str) -> str:
    return "'" + table.replace("'", "''") + "'"


def _term(table: str) -> str:
    return f"int(not ISEMPTY({repr_table(table)}))"


def gate_line(category: str, measure: str, chain: str) -> str:
    """The gate line appended to ``temp_basic`` (``basic``) or ``temp_alt``."""
    op, default = ("&&", "TRUE()") if chain == "basic" else ("||", "FALSE()")
    return (f'{op} IF(CONTAINSSTRING(all_cats, "{category}"), '
            f"IF([{measure}] > 0, TRUE(), FALSE()), {default})")


def _chain_indent(lines: list[str], span: tuple[int, int]) -> str:
    for k in range(span[0] + 1, span[1] + 1):
        s = lines[k].lstrip()
        if s.startswith(("&&", "||")):
            return lines[k][: len(lines[k]) - len(s)]
    head = lines[span[0]]
    return head[: len(head) - len(head.lstrip())] + "    "


def _lineage(table: str, measure: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"pbip-forge/{table}/measure/{measure}"))


def _new_measure_lines(table: str, measure: str, facts: list[str]) -> list[str]:
    terms = [_term(f) for f in facts]
    inline = " + ".join(terms)
    if len(inline) <= INLINE_LIMIT:
        head = [f"\tmeasure {repr_table(measure)} = {inline}"]
    else:
        head = [f"\tmeasure {repr_table(measure)} = ```"]
        head += [f"\t\t\t{'+ ' if k else ''}{t}" for k, t in enumerate(terms)]
        head.append("\t\t\t```")
    return head + [
        "\t\tisHidden",
        f"\t\tdisplayFolder: {DISPLAY_FOLDER}",
        f"\t\tlineageTag: {_lineage(table, measure)}",
        "",
        '\t\tannotation PBI_FormatHint = {"isGeneralNumber":true}',
        "",
    ]


def _insert_at(lines: list[str]) -> int:
    """Where a new measure goes: after the last measure, else before the
    table's trailing top-level annotations, else at the end."""
    blocks = tt.measure_blocks(lines)
    if blocks:
        pos = blocks[-1].end
        while pos < len(lines) and not lines[pos].strip():
            pos += 1
        return pos
    pos = len(lines)
    while pos > 0 and (not lines[pos - 1].strip() or lines[pos - 1].startswith("\tannotation ")):
        pos -= 1
    while pos < len(lines) and not lines[pos].strip():
        pos += 1
    return pos


@dataclass
class Result:
    model: Path
    ok: bool = True
    error: str | None = None
    created: dict[str, list[str]] = field(default_factory=dict)
    extended: dict[str, list[str]] = field(default_factory=dict)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    f_all_extended: list[str] = field(default_factory=list)
    already_gated: list[str] = field(default_factory=list)
    coverage_gates: list[tuple[str, str]] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    changed: bool = False
    backup: Path | None = None


def fill_gaps(model_dir: str | Path, dry_run: bool = False, backups: bool = True) -> Result:
    """Plan and (unless ``dry_run``) apply the f-Filters gap fill for one model."""
    model_dir = Path(model_dir)
    res = Result(model_dir)
    tables_dir = model_dir / "definition" / "tables"
    if not tables_dir.is_dir():
        res.ok, res.error = False, f"no tables folder in {model_dir}"
        return res
    gate_file = tables_dir / f"{GATE_TABLE}.tmdl"
    if not gate_file.is_file():
        res.ok, res.error = False, f"{gate_file.name} not found in {tables_dir}"
        return res

    original = gate_file.read_text(encoding="utf-8")
    lines = tt.split_lines(original)
    declared = declared_measures(original)

    plan: dict[str, list[str]] = {}
    for fact, cats in uncovered_facts(model_dir).items():
        if not cats:
            res.skipped.append((fact, "no analysis category reaches it"))
        for cat in cats:
            plan.setdefault(cat, []).append(fact)

    # 1. extend existing measures (line contents change, line count does not)
    to_create: list[tuple[str, str, list[str]]] = []
    for cat, facts in plan.items():
        name = resolve_f_measure(cat, declared)
        if name is None:
            to_create.append((cat, f"f-{cat}", facts))
            continue
        block = next(b for b in tt.measure_blocks(lines) if b.name == name)
        have = tt.table_refs(tt.expression(lines, block))
        new = [f for f in facts if f not in have]
        if not new:
            continue
        expr_idx = [k for k in block.expr_lines if lines[k].strip()]
        target = expr_idx[-1] if expr_idx else block.start
        lines[target] = lines[target].rstrip() + "".join(f" + {_term(f)}" for f in new)
        res.extended[name] = new
    for cat, name, facts in to_create:
        res.created[name] = facts
        declared.add(name)

    # 2. f-All gate lines (append only, both chains)
    basic = chain_span(lines, "temp_basic")
    alt = chain_span(lines, "temp_alt")
    if basic is None or alt is None:
        if to_create or zmap_categories(model_dir):
            res.warnings.append(f"{COMBINED_MEASURE} has no temp_basic/temp_alt chain pair; "
                                "no gate lines written")
    else:
        literals = gate_literals("\n".join(lines))
        created_cats = [c for c, _, _ in to_create]
        wanted = created_cats + [c for c in zmap_categories(model_dir) if c not in created_cats]
        for cat in wanted:
            if category_gated(cat, literals):
                res.already_gated.append(cat)
                continue
            measure = resolve_f_measure(cat, declared)
            if measure is None:
                res.unresolved.append(cat)
                continue
            for var, chain in (("temp_basic", "basic"), ("temp_alt", "alt")):
                span = chain_span(lines, var)
                lines.insert(span[1] + 1, _chain_indent(lines, span) + gate_line(cat, measure, chain))
            literals.append(cat)
            if cat in created_cats:
                res.f_all_extended.append(cat)
            else:
                res.coverage_gates.append((cat, measure))

    # 3. create missing measures
    for cat, name, facts in to_create:
        pos = _insert_at(lines)
        lines[pos:pos] = _new_measure_lines(GATE_TABLE, name, facts)

    updated = "\n".join(lines)
    res.changed = updated != original
    if res.extended:
        res.warnings.append(f"extended {', '.join(res.extended)}: {_SHAPE_WARNING}")
    if res.changed and not dry_run:
        if backups:
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            res.backup = gate_file.with_name(f"{gate_file.name}.{stamp}.bak")
            res.backup.write_text(original, encoding="utf-8")
        gate_file.write_text(updated, encoding="utf-8")
    return res


def _report(res: Result, dry_run: bool) -> None:
    print(f"== {res.model}")
    if not res.ok:
        print(f"  error: {res.error}")
        return
    for name, facts in res.created.items():
        print(f"  created  {name} <- {', '.join(facts)}")
    for name, facts in res.extended.items():
        print(f"  extended {name} <- {', '.join(facts)}")
    for fact, why in res.skipped:
        print(f"  skipped  {fact}: {why}")
    for cat in res.f_all_extended:
        print(f"  {COMBINED_MEASURE} extended for created category {cat}")
    for cat, measure in res.coverage_gates:
        print(f"  coverage gate added: {cat} -> [{measure}]")
    if res.already_gated:
        print(f"  already gated: {', '.join(res.already_gated)}")
    if res.unresolved:
        print(f"  unresolved (no f- measure; no gate written): {', '.join(res.unresolved)}")
    for warning in res.warnings:
        print(f"  WARNING: {warning}")
        if "extended" in warning:
            print(f"WARNING [{res.model.name}]: {warning}", file=sys.stderr)
    if not res.changed:
        print("  no change")
    elif dry_run:
        print("  dry run: nothing written")
    else:
        print(f"  wrote {GATE_TABLE}.tmdl" + (f" (backup {res.backup.name})" if res.backup else ""))


def run_cli(models: list[Path], dry_run: bool = False, backups: bool = True,
            verbose: bool = False) -> int:
    if not models:
        print("error: no semantic model to process")
        return 1
    failed = 0
    for model in models:
        res = fill_gaps(model, dry_run=dry_run, backups=backups)
        _report(res, dry_run)
        failed += not res.ok
    print(f"Reminder: {_SHAPE_WARNING}.", file=sys.stderr)
    return 1 if failed else 0
