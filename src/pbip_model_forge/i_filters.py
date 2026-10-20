"""``pbip-forge i-filters``: regenerate the ``i-Applied Filters`` caption.

``i-Applied Filters`` (in the ``Helper Measures`` table) is a text measure
that lists every dimension filter currently applied, one line per filtered
column, for a caption or tooltip. It goes stale as soon as a new dimension is
offered in a y- selector table. This module rebuilds it from the
``y-Selector`` and ``y-Plot Specific`` tables, validates the result (every
offered column needs its ``ISFILTERED`` test) and replaces the measure's
expression in place. The file's line endings and a UTF-8 BOM are kept; the
backup is a byte copy.

Each dimension block reads, in DAX::

    IF(ISFILTERED(col), "<label>" & (" = " & selected | " is not " & excluded) & CR LF)

The "is not" form is used when the column has more than ``invert_min_total``
values and only ``invert_min``..``invert_max`` of them are excluded. At most
``top_n`` selected values are listed. A blank value shows as ``(Blank)``.

The library also writes the older caption shapes (a plain caption with a
date block, an HTML caption in red or green, and a filter count); see
:func:`legacy_caption`.
"""

from __future__ import annotations

import datetime as _dt
import re
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from . import tmdl_text as tt

CAPTION_MEASURE = "i-Applied Filters"
HOST_TABLE = "Helper Measures"
SELECTOR_PREFIXES = ("y-Selector", "y-Plot Specific")
DATE_SPINE_PREFIX = "__Calendar"
LABELS = {"Campaign Actual": "Campaign Name", "Campaign Ad Group": "Ad Group",
          "Landing Page": "Landing Page"}
GROWTH_PREFIXES = ("Ticket", "_Play", "Dynamics")
#: order of a selector row without a number after its NAMEOF
NO_ORDER = 1_000_000_000
RULE = "=" * 80
THIN = "-" * 80


@dataclass
class Options:
    top_n: int = 10
    invert_min_total: int = 5      # invert only when the column has MORE values than this
    invert_min: int = 1
    invert_max: int = 3


@dataclass(frozen=True)
class Dimension:
    table: str
    column: str

    @property
    def key(self) -> str:
        return f"{self.table}[{self.column}]"

    @property
    def ref(self) -> str:
        return f"'{self.table.replace(chr(39), chr(39) * 2)}'[{self.column}]"


# ---------------------------------------------------------------------------
# Dimension discovery
# ---------------------------------------------------------------------------
_NAMEOF_RE = re.compile(r"NAMEOF\s*\(\s*('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)\s*\[([^\]]+)\]\s*\)",
                        re.I)


def selector_refs(text: str) -> dict[tuple[str, str], int]:
    """``(table, column)`` -> order for every NAMEOF in a selector file.

    The order is the integer that follows the NAMEOF (after a comma, within
    24 characters), else :data:`NO_ORDER`; a repeated ref keeps its smallest
    order. Commented-out lines are ignored."""
    plain = "\n".join("" if re.match(r"^\s*(//|--)", ln) else ln
                      for ln in text.replace("\r\n", "\n").split("\n"))
    out: dict[tuple[str, str], int] = {}
    for hit in _NAMEOF_RE.finditer(plain):
        after = re.match(r"\s*,\s*(-?\d+)", plain[hit.end():hit.end() + 24])
        order = int(after.group(1)) if after else NO_ORDER
        ref = (tt.unquote(hit.group(1)), hit.group(2))
        out[ref] = min(order, out.get(ref, order))
    return out


def discover(model_dir: str | Path) -> tuple[list[Dimension], list[Dimension]]:
    """``(dimensions, missing)`` offered by the y- selector tables.

    All refs are sorted by (order, table, column). The column ``z``, columns
    containing "blank" and ``__Calendar`` tables are dropped; a column the
    model does not declare is MISSING; a hidden column is dropped."""
    refs: dict[tuple[str, str], int] = {}
    columns: dict[tuple[str, str], list[str]] = {}
    for path in tt.table_files(model_dir):
        text = path.read_text(encoding="utf-8-sig")
        table = tt.table_name(text) or path.stem
        for col, props in tt.column_props(text.replace("\r\n", "\n")).items():
            columns[(table, col)] = props
        if table.startswith(SELECTOR_PREFIXES):
            for ref, order in selector_refs(text).items():
                refs[ref] = min(order, refs.get(ref, order))
    dims: list[Dimension] = []
    missing: list[Dimension] = []
    for (table, column), _ in sorted(refs.items(), key=lambda kv: (kv[1], kv[0][0], kv[0][1])):
        if column == "z" or "blank" in column.lower() or table.startswith(DATE_SPINE_PREFIX):
            continue
        props = columns.get((table, column))
        if props is None:
            missing.append(Dimension(table, column))
        elif "isHidden" not in props and not any(p.startswith("isHidden:") and "true" in p
                                                 for p in props):
            dims.append(Dimension(table, column))
    return dims, missing


def dimensions(model_dir: str | Path) -> list[Dimension]:
    return discover(model_dir)[0]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def _label(dim: Dimension) -> str:
    return LABELS.get(dim.column, dim.column).replace('"', '""')


def _block(dim: Dimension, opts: Options) -> str:
    col = dim.ref
    shown = f'IF(ISBLANK({col}), "(Blank)", {col} & "")'
    return "\n".join([
        "IF(",
        f"    ISFILTERED({col}),",
        f"    VAR ___f = FILTERS({col})",
        f"    VAR ___x = EXCEPT(ALL({col}), ___f)",
        "    VAR ___nX = COUNTROWS(___x)",
        f"    VAR ___inv = COUNTROWS(ALL({col})) > {opts.invert_min_total}"
        f" && ___nX >= {opts.invert_min} && ___nX <= {opts.invert_max}",
        f"    VAR ___t = TOPN({opts.top_n}, ___f, {col})",
        f'    VAR ___d = CONCATENATEX(___t, {shown}, ", ")',
        f'    VAR ___dx = CONCATENATEX(___x, {shown}, ", ", {col}, ASC)',
        f'    RETURN "{_label(dim)}" & IF(___inv, " is not ", " = ")'
        " & IF(___inv, ___dx, ___d) & UNICHAR(13) & UNICHAR(10)",
        ")",
    ])


def _measure_head(name: str) -> str:
    return f"measure '{name.replace(chr(39), chr(39) * 2)}' =\n"


def generate_caption(dims: list[Dimension], opts: Options | None = None,
                     name: str = CAPTION_MEASURE) -> str:
    """The full generated text: ``measure '<name>' =``, one block per
    dimension joined by `` &``, and a final newline."""
    opts = opts or Options()
    return _measure_head(name) + " &\n".join(_block(d, opts) for d in dims) + "\n"


def _date_block(cal: str, html: bool) -> str:
    ref = f"'{cal.replace(chr(39), chr(39) * 2)}'[Date]"
    pad = "    "
    ret = ('RETURN "<span style=\'font-weight: bold\'>Date</span> = " & ___dateRange & "<br/>"'
           if html else 'RETURN "Date = " & ___dateRange & UNICHAR(13) & UNICHAR(10)')
    return "\n".join([
        "IF(",
        f"{pad}ISFILTERED({ref}),",
        f"{pad}VAR ___dateMin = MIN({ref})",
        f"{pad}VAR ___dateMax = MAX({ref})",
        f'{pad}VAR ___dateRange = IF(___dateMin = ___dateMax, FORMAT(___dateMin, "yyyy-mm-dd"), '
        'FORMAT(___dateMin, "yyyy-mm-dd") & " to " & FORMAT(___dateMax, "yyyy-mm-dd"))',
        f"{pad}{ret}",
        ") &" if html else ")",
    ])


def _html_block(dim: Dimension, opts: Options) -> str:
    col = dim.ref
    return "\n".join([
        "IF(",
        f"    ISFILTERED({col}),",
        f"    VAR ___f = FILTERS({col})",
        f"    VAR ___t = TOPN({opts.top_n}, ___f, {col})",
        f'    VAR ___d = CONCATENATEX(___t, {col}, ", ")',
        f"    RETURN \"<span style='font-weight: bold'>{_label(dim)}</span>\""
        ' & " = " & ___d & "<br/>"',
        ") &",
    ])


def legacy_caption(dims: list[Dimension], kind: str = "plain", name: str = CAPTION_MEASURE,
                   calendar: str = DATE_SPINE_PREFIX, date_block: bool = True,
                   opts: Options | None = None) -> str:
    """An older caption shape: ``plain`` (date block first, then the live
    blocks), ``html_red``/``html_green`` (HTML text) or ``count``."""
    opts = opts or Options()
    if kind == "plain":
        blocks = ([_date_block(calendar, html=False)] if date_block else [])
        blocks += [_block(d, opts) for d in dims]
        return _measure_head(name) + " &\n".join(blocks) + "\n"
    if kind in ("html_red", "html_green"):
        colour = kind.split("_")[1]
        indent = " " * 13
        parts = ["\"<div style='font-family: 'Segoe UI Light', 'Segoe UI', Arial;\n"
                 f"{indent}font-size: 8px;\n{indent}font-weight: 300;\n"
                 f"{indent}line-height: 1.2;\n{indent}color: {colour};'>\" &"]
        if date_block:
            parts.append(_date_block(calendar, html=True))
        parts += [_html_block(d, opts) for d in dims]
        parts.append('"</div>"')
        return _measure_head(name) + "\n".join(parts) + "\n"
    if kind == "count":
        cal_ref = f"'{calendar.replace(chr(39), chr(39) * 2)}'[Date]"
        refs = ([cal_ref] if date_block else []) + [d.ref for d in dims]
        terms = " +\n".join(f"    IF(ISFILTERED({r}), 1, 0)" for r in refs)
        return (_measure_head(name) + "VAR ___totalActiveFilters =\n" + terms + "\n\n"
                "RETURN\nIF(\n    ___totalActiveFilters > 0,\n"
                '    "🔍 " & ___totalActiveFilters & " filters active",\n'
                '    "ℹ️ No filters applied"\n)\n')
    raise ValueError(f"unknown caption kind: {kind}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@dataclass
class Validation:
    coverage_percent: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    found: int = 0

    @property
    def ok(self) -> bool:
        return self.coverage_percent == 100.0 and not self.errors


_ISFILTERED_RE = re.compile(r"ISFILTERED\(\s*('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)\[([^\]]+)\]\s*\)",
                            re.I)


def validate_caption(text: str, expected: list[Dimension], kind: str = "plain_text") -> Validation:
    """Check generated caption text before it is written.

    Coverage is the share of ``expected`` columns that appear as an
    ``ISFILTERED`` target (0.0 when nothing is expected); it must be 100.
    ``ISFILTERED(`` and (except for ``count``) ``CONCATENATEX(`` must be
    present. The working variables, ``TOPN(`` and a line break are warnings."""
    targets = {(tt.unquote(t).lower(), c.lower()) for t, c in _ISFILTERED_RE.findall(text)}
    keys = {(d.table.lower(), d.column.lower()) for d in expected}
    covered = sum(k in targets for k in keys)
    coverage = 100.0 * covered / len(keys) if keys else 0.0
    res = Validation(coverage, found=len(_ISFILTERED_RE.findall(text)))
    if coverage != 100.0:
        res.errors.append(f"coverage {coverage:.1f}%")
    if "ISFILTERED(" not in text:
        res.errors.append("no ISFILTERED( in the generated DAX")
    if kind == "count":
        return res
    if "CONCATENATEX(" not in text:
        res.errors.append("no CONCATENATEX( in the generated DAX")
    if kind.startswith("html"):
        if "<br/>" not in text and "<br>" not in text:
            res.warnings.append("no <br/> line break")
        if "style=" not in text:
            res.errors.append("no style= attribute")
        colour = kind.split("_")[-1]
        if colour in ("red", "green") and f"color: {colour}" not in text \
                and f"color:{colour}" not in text:
            res.warnings.append(f"no color: {colour}")
        return res
    if not all(v in text for v in ("VAR ___f =", "VAR ___t =", "VAR ___d =")):
        res.warnings.append("working variables ___f/___t/___d missing")
    if "TOPN(" not in text:
        res.warnings.append("no TOPN(")
    if "UNICHAR(13)" not in text:
        res.warnings.append("no UNICHAR(13) line break")
    return res


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
_DECL_RE = re.compile(r"^(\s*)measure\s+('(?:[^']|'')+'|\"[^\"]+\"|[^\s=]+)\s*=(.*)$")


def _find_decl(lines: list[str], measure: str) -> tuple[int, re.Match] | None:
    for i, line in enumerate(lines):
        hit = _DECL_RE.match(line)
        if hit and tt.unquote(hit.group(2)) == measure:
            return i, hit
    return None


def _fence_line(line: str) -> str:
    if not line.strip():
        return ""
    rest = line
    while True:
        if rest.startswith("    "):
            rest = rest[4:]
        elif rest.startswith("\t"):
            rest = rest[1:]
        else:
            break
    return ("\t\t\t" if rest.startswith(") &") or rest == ")" else "\t\t\t\t\t") + rest


def replace_caption(text: str, measure: str, generated: str) -> tuple[str, int, int] | None:
    """``(new text, old line count, new line count)`` with the measure's
    expression replaced by the generated text (whose first line, the
    ``measure`` line, is never written). None when the measure is missing."""
    lines = text.split("\n")
    found = _find_decl(lines, measure)
    if found is None:
        return None
    i, hit = found
    indent, token, rest = hit.group(1), hit.group(2), hit.group(3)
    gen = generated.split("\n")
    if rest.strip() == "```":
        close = next((k for k in range(i + 1, len(lines)) if lines[k].strip() == "```"), None)
        if close is None:
            return None
        inner = lines[i + 1:close]
        a = 0
        while a < len(inner) and not inner[a].strip():
            a += 1
        b = len(inner)
        while b > a and not inner[b - 1].strip():
            b -= 1
        body = [_fence_line(ln) for ln in gen[1:]]
        new = lines[:i + 1] + inner[:a] + body + inner[b:] + lines[close:]
        return "\n".join(new), b - a, len(body)
    while gen and not gen[0].strip():
        gen.pop(0)
    while gen and not gen[-1].strip():
        gen.pop()
    gen = gen[1:]
    if not gen:
        return text, 0, 0
    end = next((k for k in range(i + 1, len(lines)) if re.match(r"^\t{0,2}\S", lines[k])),
               len(lines))
    while end - 1 > i and not lines[end - 1].strip():
        end -= 1
    if rest.strip() and len(gen) == 1:
        replacement = [f"{indent}measure {token} = {gen[0].strip()}"]
    else:
        replacement = [f"{indent}measure {token} ="]
        replacement += [f"\t\t\t{ln}" if ln.strip() else "" for ln in gen]
    new = lines[:i] + replacement + lines[end:]
    return "\n".join(new), end - i, len(replacement)


def _old_span(text: str, measure: str) -> str | None:
    lines = text.split("\n")
    found = _find_decl(lines, measure)
    if found is None:
        return None
    i, hit = found
    start = sum(len(ln) + 1 for ln in lines[:i]) + hit.start(0) + len(hit.group(1))
    stop = re.compile(r"\n(?=(?:measure|column|table)\s)").search(text, start)
    return text[start:stop.start() if stop else len(text)]


def _listing(title: str, text: str) -> list[str]:
    lines = text.split("\n")
    out = [f"{title} (first 5 lines):"] + [f"  | {ln}" for ln in lines[:5]]
    if len(lines) > 10:
        out.append(f"  | ... ({len(lines) - 10} more lines)")
    out += [f"{title} (last 5 lines):"] + [f"  | {ln}" for ln in lines[-5:]]
    return out


def preview(old: str | None, new: str, measure: str = CAPTION_MEASURE,
            host: str = f"{HOST_TABLE}.tmdl") -> list[str]:
    """The dry-run preview lines."""
    out = ["", RULE, "PREVIEW: Measure Updates", RULE, "", f"Measure: {measure}", THIN]
    if old is None:
        out += [f"❌ NOT FOUND in {host}", ""]
    else:
        ol, oc, nl, nc = old.count("\n"), len(old), new.count("\n"), len(new)
        out += [f"Original: {ol} lines, {oc} characters",
                f"New:      {nl} lines, {nc} characters",
                f"Change:   {nl - ol:+d} lines, {nc - oc:+d} characters", ""]
        out += _listing("Original", old) + [""] + _listing("New", new) + [""]
    return out + [RULE, ""]


@dataclass
class Result:
    model: Path
    dimensions: list[Dimension] = field(default_factory=list)
    missing: list[Dimension] = field(default_factory=list)
    generated: str = ""
    updated: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    error: str | None = None
    validation: Validation | None = None
    backup: Path | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _say(*lines: str) -> None:
    for line in lines:
        print(line)


def _banner(title: str) -> None:
    _say("", RULE, title, RULE, "")


def update_caption(model_dir: str | Path, dry_run: bool = False, backups: bool = True,
                   validate: bool = True, verbose: bool = False,
                   opts: Options | None = None) -> Result:
    """Regenerate ``i-Applied Filters`` for one model."""
    model_dir = Path(model_dir)
    res = Result(model_dir)
    res.dimensions, res.missing = discover(model_dir)
    if verbose:
        _banner("STEP 1: Dimension Discovery")
        growth = sum(d.table.startswith(GROWTH_PREFIXES) for d in res.dimensions)
        _say("", f"✅ Discovered {len(res.dimensions)} dimensions",
             f"   Performance dimensions: {len(res.dimensions) - growth}",
             f"   Growth dimensions: {growth}", "   Cluster dimensions: 0")

    res.generated = generate_caption(res.dimensions, opts)
    if verbose:
        _banner("STEP 2: DAX Generation")
        _say("📝 Generating the required measure", "", "✅ Generated 1 measures",
             f"   {CAPTION_MEASURE}: {res.generated.count(chr(10))} lines, "
             f"{len(res.generated):,} characters")

    if validate:
        expected = res.dimensions + res.missing
        if verbose:
            _banner("STEP 3: Validation")
            _say("", f"📋 Validating: {CAPTION_MEASURE}",
                 f"🔍 Validating coverage for {len(expected)} dimensions")
        # looked up on the module at call time so a caller can swap the validator
        verdict = globals()["validate_caption"](res.generated, expected)
        res.validation = verdict
        passed = verdict.coverage_percent == 100.0 and not verdict.errors
        if verbose:
            _say(f"   Found {getattr(verdict, 'found', 0)} ISFILTERED checks in DAX",
                 "🔍 Validating DAX patterns for plain_text",
                 f"{'✅ PASS' if passed else '❌ FAIL'}: {CAPTION_MEASURE} "
                 f"({verdict.coverage_percent:.1f}% coverage)")
        if not passed:
            res.error = "Validation failed - see details above"
            if not verbose:
                _say("", "❌ Validation failed. Run with --verbose for details.")
            return res
        if verbose:
            _say("", "✅ All validations passed")
    elif verbose:
        _say("", "⏭️  Skipping validation (--skip-validation)")

    host = model_dir / "definition" / "tables" / f"{HOST_TABLE}.tmdl"
    if verbose:
        _banner("STEP 4: Preview Changes (Dry-Run)" if dry_run else "STEP 4: Update Measures")
    if dry_run:
        if host.is_file():
            text = tt.read_source(host).text
            _say(*preview(_old_span(text, CAPTION_MEASURE), res.generated))
        else:
            res.error = f"Helper Measures file not found: {host}"
        if verbose and res.ok:
            _say("", "✅ Dry-run completed - no changes applied")
        return res

    if not host.is_file():
        res.error = f"Helper Measures file not found: {host}"
    elif res.dimensions:
        if verbose:
            _say(f"📖 Reading: {host}")
        source = tt.read_source(host)
        original = source.text
        replaced = replace_caption(original, CAPTION_MEASURE, res.generated)
        if backups and (replaced is None or replaced[0] != original):
            stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            res.backup = host.with_name(f"{host.name}.backup_{stamp}")
            shutil.copy2(host, res.backup)
            if verbose:
                _say(f"💾 Backup created: {res.backup}")
        if verbose:
            _say("", f"🔄 Updating: {CAPTION_MEASURE}")
        if replaced is None:
            res.failed.append(CAPTION_MEASURE)
            res.error = f"Failed to update: {CAPTION_MEASURE}"
            if verbose:
                _say(f"   ❌ Failed: {res.error}")
        else:
            new_text, old_n, new_n = replaced
            if verbose:
                _say(f"   ✅ Updated: {old_n} lines → {new_n} lines")
            if new_text != original:
                res.updated.append(CAPTION_MEASURE)
                tt.write_edit(source, new_text)
                if verbose:
                    _say("", f"✅ Wrote updated file: {host}")
    if verbose:
        if res.ok:
            _say("", f"✅ Successfully updated {len(res.updated)} measures")
        else:
            _say("", f"❌ Update completed with errors: {res.error}")
    return res


def run_cli(targets: list[tuple[str, Path]], dry_run: bool = False, backups: bool = True,
            validate: bool = True, verbose: bool = False) -> int:
    """Regenerate the caption for ``(label, model folder)`` targets."""
    _say(f"i-filter update — {len(targets)} target(s); mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    failed = 0
    for label, path in targets:
        tables = Path(path) / "definition" / "tables"
        if not tables.is_dir():
            print("", file=sys.stderr)
            print(f"[SKIP] {label}: {tables} not found", file=sys.stderr)
            failed += 1
            continue
        _say("", f"── {label}  ({Path(path).resolve()})")
        try:
            res = update_caption(path, dry_run=dry_run, backups=backups and not dry_run,
                                 validate=validate, verbose=verbose)
        except Exception as exc:
            _say("", f"❌ Error: {exc}")
            traceback.print_exc()
            res = Result(Path(path), error=str(exc))
        status = "OK" if res.ok else f"FAIL: {res.error}"
        _say(f"   dims={len(res.dimensions)} gen=1 updated={len(res.updated)} "
             f"failed={len(res.failed)}  -> {status}")
        failed += not res.ok
    _say("")
    return 1 if failed else 0
