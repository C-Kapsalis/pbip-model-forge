"""``pbip-forge i-filters``: regenerate the ``i-Applied Filters`` caption.

``i-Applied Filters`` (in the ``Helper Measures`` table) is a text measure
that lists every dimension filter currently applied, one line per filtered
column, for a caption or tooltip. It goes stale as soon as a new dimension is
offered in a y- selector table. This module rebuilds it from the selector
tables, so every offered dimension is covered, validates the result, and
replaces the measure's expression in place (properties are kept). The
file's line endings and a UTF-8 BOM are kept; the backup is a byte copy.

Each dimension block reads, in DAX::

    IF(ISFILTERED(col), <label> & (" = " & selected | " is not " & excluded) & CR LF)

The "is not" form is used when the column has more than ``invert_min_total``
values and only ``invert_min``..``invert_max`` of them are excluded, which
reads better than a long list of selected values. At most ``top_n`` selected
values are listed. A blank value shows as ``(Blank)``.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import tmdl_text as tt

CAPTION_MEASURE = "i-Applied Filters"
HOST_TABLE = "Helper Measures"
DATE_SPINE_PREFIX = "__Calendar"
LABELS = {"Campaign Actual": "Campaign Name"}


@dataclass
class Options:
    top_n: int = 10
    invert_min_total: int = 5      # invert only when the column has MORE values than this
    invert_min: int = 1
    invert_max: int = 3
    date_spine_prefix: str = DATE_SPINE_PREFIX
    labels: dict[str, str] = field(default_factory=lambda: dict(LABELS))
    output: str = "text"           # text | html | count
    date_column: str | None = None  # e.g. "'__Calendar'[Date]" adds a date block
    order: dict[str, int] | None = None  # "table[column]" -> sort key


@dataclass(frozen=True)
class Dimension:
    table: str
    column: str
    cluster: bool = False

    @property
    def key(self) -> str:
        return f"{self.table}[{self.column}]"

    @property
    def ref(self) -> str:
        return f"'{self.table.replace(chr(39), chr(39) * 2)}'[{self.column}]"


# ---------------------------------------------------------------------------
# Dimension discovery
# ---------------------------------------------------------------------------
def _selector_files(model_dir: Path) -> list[Path]:
    return [p for p in tt.table_files(model_dir)
            if (tt.table_name(p.read_text(encoding="utf-8")) or p.stem).startswith("y-")]


def _hidden_columns(model_dir: Path) -> set[str]:
    hidden = set()
    for path in tt.table_files(model_dir):
        text = path.read_text(encoding="utf-8")
        table = tt.table_name(text) or path.stem
        for col, props in tt.column_props(text).items():
            if "isHidden" in props:
                hidden.add(f"{table}[{col}]")
    return hidden


def _skip(table: str, column: str, opts: Options) -> bool:
    low = column.lower()
    return (table.startswith(opts.date_spine_prefix) or table.startswith("__Comparison")
            or "blank" in low or "z_space" in low)


def dimensions(model_dir: str | Path, opts: Options | None = None) -> list[Dimension]:
    """Visible columns offered by the y- selector tables, in selector order.

    Rows are ordered by their numeric order field within each table (tables
    in file order); the date spine, comparison tables and spacer columns are
    left out, duplicates keep their first position. A column whose name
    contains ``Cluster`` is a cluster dimension."""
    opts = opts or Options()
    model_dir = Path(model_dir)
    hidden = _hidden_columns(model_dir)
    found: list[Dimension] = []
    seen: set[str] = set()
    for path in _selector_files(model_dir):
        entries = []
        for pos, fields in enumerate(tt.selector_rows(path.read_text(encoding="utf-8"))):
            target = next((tt.nameof_target(f) for f in fields if tt.nameof_target(f)), None)
            if target is None:
                continue
            order = next((float(f) for f in fields[2:3] if re.fullmatch(r"-?\d+(\.\d+)?", f)), pos)
            entries.append((order, pos, target))
        for _, _, (table, column) in sorted(entries):
            dim = Dimension(table, column, cluster="cluster" in column.lower())
            if dim.key in seen or dim.key in hidden or _skip(table, column, opts):
                continue
            seen.add(dim.key)
            found.append(dim)
    if opts.order:
        rank = {d.key: opts.order.get(d.key, 10**9) for d in found}
        found = sorted(found, key=lambda d: rank[d.key])  # stable: ties keep input order
    return found


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def _label(dim: Dimension, opts: Options) -> str:
    if dim.cluster:
        return f"[-{dim.column} Name]"
    text = opts.labels.get(dim.column, dim.column)
    return '"' + text.replace('"', '""') + '"'


def _block(dim: Dimension, opts: Options) -> str:
    col = dim.ref
    item = f"[-{dim.column} Name]" if dim.cluster else col
    shown = f'IF(ISBLANK({item}), "(Blank)", {item})'
    if opts.output == "html":
        head = f'"<span style=""font-weight:bold"">" & {_label(dim, opts)} & "</span>"'
        brk = '"<br/>"'
    else:
        head, brk = _label(dim, opts), "UNICHAR(13) & UNICHAR(10)"
    return "\n".join([
        "IF(",
        f"    ISFILTERED({col}),",
        f"    VAR __sel = VALUES({col})",
        f"    VAR __excl = EXCEPT(ALL({col}), __sel)",
        "    VAR __exclCount = COUNTROWS(__excl)",
        f"    VAR __invert = COUNTROWS(ALL({col})) > {opts.invert_min_total}"
        f" && __exclCount >= {opts.invert_min} && __exclCount <= {opts.invert_max}",
        f"    VAR __top = TOPN({opts.top_n}, __sel, {col}, ASC)",
        f'    VAR __selList = CONCATENATEX(__top, {shown}, ", ", {col}, ASC)',
        f'    VAR __exclList = CONCATENATEX(__excl, {shown}, ", ", {col}, ASC)',
        f'    RETURN {head} & IF(__invert, " is not ", " = ")'
        f" & IF(__invert, __exclList, __selList) & {brk}",
        ")",
    ])


#: FORMAT pattern of the dates in the period line, e.g. "3 Feb 2025"
DATE_FORMAT = "d mmm yyyy"


def _date_block(opts: Options) -> str:
    """One "Period: <first> - <last>" line (a single date when the range is
    one day) while the calendar column is filtered."""
    col = opts.date_column
    first, last = (f'FORMAT({v}, "{DATE_FORMAT}")' for v in ("__first", "__last"))
    brk = '"<br/>"' if opts.output == "html" else "UNICHAR(13) & UNICHAR(10)"
    return "\n".join([
        "IF(",
        f"    ISFILTERED({col}),",
        f"    VAR __first = MIN({col})",
        f"    VAR __last = MAX({col})",
        f'    RETURN "Period: " & IF(__first = __last, {first}, {first} & " - " & {last})'
        f" & {brk}",
        ")",
    ])


def generate_expression(dims: list[Dimension], opts: Options | None = None) -> str:
    """The DAX expression of the caption measure for ``dims``."""
    opts = opts or Options()
    if opts.output == "count":
        flags = " + ".join(f"INT(ISFILTERED({d.ref}))" for d in dims) or "0"
        return "\n".join([
            f"VAR __active = {flags}",
            'RETURN IF(__active = 0, "No filters applied", __active & " filters active")',
        ])
    blocks = [_block(d, opts) for d in dims]
    if opts.date_column:
        blocks.append(_date_block(opts))
    if not blocks:
        return '""'
    body = " &\n".join(blocks)
    if opts.output == "html":
        body = '"<div style=""color:#404040"">" &\n' + body + ' &\n"</div>"'
    return body


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@dataclass
class Validation:
    coverage_percent: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.coverage_percent >= 100.0 and not self.errors


def validate_caption(expression: str, dims: list[Dimension]) -> Validation:
    """Check a generated caption before it is written."""
    targets = {(t, c) for t, c in re.findall(
        r"ISFILTERED\(\s*'((?:[^']|'')+)'\[([^\]]+)\]\s*\)", expression)}
    targets = {(t.replace("''", "'"), c) for t, c in targets}
    covered = sum((d.table, d.column) in targets for d in dims)
    coverage = 100.0 if not dims else round(100.0 * covered / len(dims), 2)
    res = Validation(coverage)
    if dims:
        for needle in ("ISFILTERED", "CONCATENATEX"):
            if needle not in expression:
                res.errors.append(f"{needle} missing")
        for needle in ("__sel", "__excl", "__invert"):
            if needle not in expression:
                res.warnings.append(f"working variable {needle} missing")
        if "TOPN" not in expression:
            res.warnings.append("TOPN missing")
        if "UNICHAR(13)" not in expression and "<br/>" not in expression:
            res.warnings.append("no CR line break")
    for dim in dims:
        if dim.cluster and f"[-{dim.column} Name]" not in expression:
            res.errors.append(f"cluster name measure [-{dim.column} Name] not referenced")
    if coverage < 100.0:
        missing = [d.key for d in dims if (d.table, d.column) not in targets]
        res.errors.append(f"coverage {coverage}%: no ISFILTERED for {', '.join(missing)}")
    return res


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def replace_expression(text: str, measure: str, expression: str) -> str | None:
    """``text`` with ``measure``'s expression replaced by a fenced block.

    Properties and everything outside the measure are kept byte for byte.
    Returns None when the measure is not declared."""
    lines = tt.split_lines(text)
    block = next((b for b in tt.measure_blocks(lines) if b.name == measure), None)
    if block is None:
        return None
    head = tt.MEASURE_RE.match(lines[block.start])
    decl = f"\tmeasure {head.group(1)} = ```"
    body = [f"\t\t\t{ln}" if ln.strip() else "" for ln in expression.split("\n")]
    if block.expr_lines:
        last = block.expr_lines[-1] + (2 if block.fenced else 1)
    else:
        last = block.start + 1
    new = [decl] + body + ["\t\t\t```"]
    return "\n".join(lines[:block.start] + new + lines[last:])


@dataclass
class Result:
    model: Path
    dimensions: list[Dimension] = field(default_factory=list)
    generated: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    backup: Path | None = None

    @property
    def ok(self) -> bool:
        return not self.failed


def update_caption(model_dir: str | Path, dry_run: bool = False, backups: bool = True,
                   validate: bool = True, opts: Options | None = None) -> Result:
    """Regenerate ``i-Applied Filters`` for one model."""
    opts = opts or Options()
    model_dir = Path(model_dir)
    res = Result(model_dir)
    host = model_dir / "definition" / "tables" / f"{HOST_TABLE}.tmdl"
    if not host.is_file():
        res.failed.append((CAPTION_MEASURE, f"{host.name} not found"))
        return res
    res.dimensions = dimensions(model_dir, opts)
    expr = generate_expression(res.dimensions, opts)
    res.generated.append(CAPTION_MEASURE)
    if validate:
        # looked up on the module at call time so a caller can swap the validator
        verdict: Any = globals()["validate_caption"](expr, res.dimensions)
        res.warnings.extend(getattr(verdict, "warnings", []) or [])
        if verdict.coverage_percent < 100 or verdict.errors:
            reasons = list(verdict.errors) or [f"coverage {verdict.coverage_percent}%"]
            res.failed.append((CAPTION_MEASURE, "validation failed: " + "; ".join(reasons)))
            return res
    source = tt.read_source(host)
    original = source.text
    updated = replace_expression(original, CAPTION_MEASURE, expr)
    if updated is None:
        res.failed.append((CAPTION_MEASURE, f"measure not found in {host.name}"))
        return res
    if updated != original:
        res.updated.append(CAPTION_MEASURE)
        if not dry_run:
            if backups:
                stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
                res.backup = host.with_name(f"{host.name}.{stamp}.bak")
            tt.write_edit(source, updated, backup=res.backup)
    return res


def run_cli(models: list[Path], dry_run: bool = False, backups: bool = True,
            validate: bool = True, verbose: bool = False) -> int:
    if not models:
        print("error: no semantic model to process")
        return 1
    failed = 0
    for _, model in models:
        res = update_caption(model, dry_run=dry_run, backups=backups, validate=validate)
        print(f"== {model}")
        print(f"  dimensions: {len(res.dimensions)}"
              + (f" ({', '.join(d.key for d in res.dimensions)})" if res.dimensions else ""))
        print(f"  generated: {len(res.generated)}  updated: {len(res.updated)}"
              f"  failed: {len(res.failed)}")
        for name, why in res.failed:
            print(f"  FAILED {name}: {why}")
        for warning in res.warnings:
            print(f"  warning: {warning}")
        if res.updated and dry_run:
            print("  dry run: nothing written")
            if verbose:
                print(generate_expression(res.dimensions))
        elif res.updated:
            print(f"  wrote {HOST_TABLE}.tmdl" + (f" (backup {res.backup.name})" if res.backup else ""))
        elif res.ok:
            print("  no change")
        failed += not res.ok
    return 1 if failed else 0
