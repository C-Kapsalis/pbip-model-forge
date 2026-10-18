"""Compressed "entered data" encoder for hand-authored PBIP models.

This is the single most important module in the repo. Power BI stores manually
entered / prototype data inside an M partition as a base64 string that is a
**raw-DEFLATE-compressed JSON array-of-arrays** where *every* cell is a string.
Reproducing that byte layout exactly is what lets a hand-written model load real
data without tripping the "composite model / entity based query source" error
(tmdl-preflight rule M008) that inline ``#table(...)`` sources cause.

The encoder here is byte-for-byte identical to what Power BI Desktop itself
emits (verified against the proven-openable ``bike-shop-clean`` example).

Encoding recipe (see ``encode_rows``):
    1. rows -> JSON array-of-arrays, every value a string
       (dates as ISO ``YYYY-MM-DD``), ``json.dumps(rows, separators=(",",":"))``
    2. compress with **raw** DEFLATE: ``zlib.compressobj(9, zlib.DEFLATED, -15)``
    3. ``base64.b64encode``
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import re
import sys
import zlib
from pathlib import Path
from typing import Any, Iterable, Sequence

# ---------------------------------------------------------------------------
# Type system: maps a friendly spec type keyword to
#   - the TMDL column ``dataType:`` (must be in tmdl-preflight VALID_DATA_TYPES)
#   - the M ``Table.TransformColumnTypes`` target
# The transform targets are exactly the ones blessed by the will-it-open
# playbook: Int64.Type, type text, type number, type datetime, type logical.
# ---------------------------------------------------------------------------
TYPE_MAP: dict[str, dict[str, str]] = {
    "int64":    {"dataType": "int64",    "transform": "Int64.Type"},
    "int":      {"dataType": "int64",    "transform": "Int64.Type"},
    "string":   {"dataType": "string",   "transform": "type text"},
    "text":     {"dataType": "string",   "transform": "type text"},
    "double":   {"dataType": "double",   "transform": "type number"},
    "number":   {"dataType": "double",   "transform": "type number"},
    "decimal":  {"dataType": "decimal",  "transform": "type number"},
    "datetime": {"dataType": "dateTime", "transform": "type datetime"},
    "date":     {"dataType": "dateTime", "transform": "type datetime"},
    "boolean":  {"dataType": "boolean",  "transform": "type logical"},
    "bool":     {"dataType": "boolean",  "transform": "type logical"},
}


def resolve_type(keyword: str) -> dict[str, str]:
    """Return the {dataType, transform} pair for a spec type keyword."""
    key = keyword.strip().lower()
    if key not in TYPE_MAP:
        raise ValueError(
            f"unknown column type {keyword!r}; supported: {sorted(set(TYPE_MAP))}"
        )
    return TYPE_MAP[key]


def stringify(value: Any) -> str | None:
    """Coerce a single cell value into the string form Power BI expects.

    ``None`` is preserved as JSON ``null`` (the partition column type is
    ``nullable text``, so nulls are legal). Booleans become ``TRUE``/``FALSE``
    so ``type logical`` parses them. ``date``/``datetime`` become ISO text.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, _dt.datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, _dt.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _deflate_b64(text: str) -> str:
    """Raw DEFLATE (level 9, window 15, no zlib header) then padded base64."""
    packer = zlib.compressobj(9, zlib.DEFLATED, -15)  # -15 == raw DEFLATE
    blob = packer.compress(text.encode("utf-8")) + packer.flush()
    return base64.b64encode(blob).decode("ascii")


def encode_rows(rows: Iterable[Sequence[Any]], parity_json: bool = False) -> str:
    """Encode rows (array-of-arrays) into the base64 entered-data string.

    Default (compact) mode stringifies every cell and writes JSON with no
    spaces; the output is byte-identical to Power BI Desktop's own "entered
    data" encoding.

    ``parity_json=True`` keeps every cell exactly as given (numbers stay
    numbers) and writes JSON with the standard library's default spacing
    (``", "`` and ``": "``) and ASCII escaping. Use it to reproduce payloads
    written by tooling that serialised rows that way, byte for byte.
    """
    if parity_json:
        return _deflate_b64(json.dumps([list(r) for r in rows]))
    string_rows = [[stringify(cell) for cell in row] for row in rows]
    return _deflate_b64(json.dumps(string_rows, separators=(",", ":")))


def decode_base64(b64: str) -> list[list[Any]]:
    """Inverse of :func:`encode_rows` (raw-DEFLATE inflate + JSON).

    Raises on a payload that does not decode; see :func:`decode_b64_or_none`
    for the forgiving variant."""
    raw = zlib.decompress(base64.b64decode(b64), -15)
    return json.loads(raw.decode("utf-8"))


def decode_b64_or_none(b64: str) -> list[list[Any]] | None:
    """Decode a payload, or print one error line to stderr and return None.

    Every row comes back as data: row 0 is never dropped or treated as a
    header here."""
    try:
        rows = decode_base64(b64.strip())
    except (ValueError, zlib.error, UnicodeDecodeError) as exc:
        reason = " ".join(str(exc).split()) or type(exc).__name__
        print(f"error: encoded payload does not decode: {reason}", file=sys.stderr)
        return None
    if not isinstance(rows, list):
        print("error: encoded payload is not a JSON array of rows", file=sys.stderr)
        return None
    return rows


_PAYLOAD_RE = re.compile(r'Binary\.FromText\("([^"]+)"')


def first_payload(text: str) -> str | None:
    """The first ``Binary.FromText("...")`` payload in TMDL text, if any."""
    hit = _PAYLOAD_RE.search(text)
    return hit.group(1) if hit else None


def decode_file(path: str | Path) -> list[list[Any]] | None:
    """Rows of the FIRST encoded payload in a TMDL file (read-only).

    Raises ``ValueError("no encoded payload in <file>")`` when the file holds
    none; returns None (after one error line) when the payload is corrupt."""
    path = Path(path)
    b64 = first_payload(path.read_text(encoding="utf-8"))
    if b64 is None:
        raise ValueError(f"no encoded payload in {path}")
    return decode_b64_or_none(b64)


def format_dump(rows: Sequence[Sequence[Any]], max_rows: int = 20) -> str:
    """A review listing of decoded rows. Row 0 is shown as column names."""
    if not rows:
        return "No data: the payload is an empty array.\n"

    def cell(v: Any) -> str:
        return "(null)" if v is None else str(v)

    names, body = rows[0], rows[1:]
    out = [f"Columns ({len(names)}): " + " | ".join(cell(v) for v in names),
           f"Data rows: {len(body)}"]
    shown = body[:max(max_rows, 0)]
    width = len(str(len(shown))) if shown else 1
    for n, row in enumerate(shown, start=1):
        out.append(f"{n:>{width}}  " + " | ".join(cell(v) for v in row))
    hidden = len(body) - len(shown)
    if hidden > 0:
        out.append(f"... {hidden} more rows not shown (use --max-rows)")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# M source builders
# ---------------------------------------------------------------------------
# The `let ... in` body is indented with tab characters to match the exact
# layout Power BI Desktop writes (and that bike-shop-clean uses). Callers
# supply the leading indent for the whole block.

_SRC_INDENT = "\t\t\t\t"          # continuation lines under `source =`
_SRC_STMT = "\t\t\t\t    "        # statements inside let (4 tabs + 4 spaces)


def entered_data_source(columns: Sequence[str], types: Sequence[str],
                        rows: Iterable[Sequence[Any]]) -> str:
    """Build the full M ``let ... in`` source that loads ``rows`` as data.

    Uses the compressed entered-data pattern followed by
    ``Table.TransformColumnTypes`` to set real column types. Returns the source
    body starting at ``let`` (already indented for a table partition).
    """
    if len(columns) != len(types):
        raise ValueError("columns and types must be the same length")
    b64 = encode_rows(rows)
    typedef = ", ".join(f'#"{c}" = _t' for c in columns)
    transforms = ", ".join(
        f'{{"{c}", {resolve_type(t)["transform"]}}}' for c, t in zip(columns, types)
    )
    source_line = (
        'Source = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("'
        f'{b64}", BinaryEncoding.Base64), Compression.Deflate)), '
        'let _t = ((type nullable text) meta [Serialized.Text = true]) in '
        f'type table [{typedef}])'
    )
    changed_line = f'#"Changed Type" = Table.TransformColumnTypes(Source, {{{transforms}}})'
    return (
        f"{_SRC_INDENT}let\n"
        f"{_SRC_STMT}{source_line},\n"
        f"{_SRC_STMT}{changed_line}\n"
        f"{_SRC_INDENT}in\n"
        f'{_SRC_STMT}#"Changed Type"'
    )


# The canonical dummy partition for a measures-only table. base64 "i45WUlCKjQUA"
# decodes to [[" "]] (one row, one space cell); the column `z` is then dropped.
# This is the exact string the playbook (rule M007) mandates.
DUMMY_PARTITION_SOURCE = (
    f"{_SRC_INDENT}let\n"
    f'{_SRC_STMT}Source = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText('
    '"i45WUlCKjQUA", BinaryEncoding.Base64), Compression.Deflate)), '
    'let _t = ((type nullable text) meta [Serialized.Text = true]) in '
    "type table [z = _t]),\n"
    f'{_SRC_STMT}#"Removed Columns" = Table.RemoveColumns(Source,{{"z"}})\n'
    f"{_SRC_INDENT}in\n"
    f'{_SRC_STMT}#"Removed Columns"'
)
