"""Small, line-based readers and editors for TMDL table files.

The model-editing commands (``f-filters``, ``i-filters``) change one measure
at a time and must leave every other byte of the file alone, so they work on
the text itself rather than on a parsed object model. This module holds the
pieces they share: measure blocks, expressions, properties and table
references.

Conventions assumed (the layout Power BI Desktop writes): objects of a table
are indented with one tab, their properties with two, and a multi-line
expression either sits in a ``````` fence or on lines indented by three or
more tabs below the declaration.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

_NAME = r"(?:'(?:[^']|'')+'|\"[^\"]+\"|[^\s=']+)"
MEASURE_RE = re.compile(rf"^\tmeasure\s+({_NAME})\s*=(.*)$")
_TOP_OBJECT_RE = re.compile(r"^\t(?!\t)\S")


def unquote(name: str) -> str:
    # single quotes double up inside: 'it''s' -> it's ; "x" -> x
    raw = name.strip()
    mark = raw[:1]
    if mark not in ("'", '"') or len(raw) < 2 or not raw.endswith(mark):
        return raw
    inner = raw[1:-1]
    return inner.replace("''", "'") if mark == "'" else inner


def quote(name: str) -> str:
    """TMDL object name, single-quoted when it is not a plain identifier."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return "'" + name.replace("'", "''") + "'"


@dataclass
class MeasureBlock:
    """One measure declaration and its span in a list of lines."""

    name: str
    start: int                    # index of the `measure ... =` line
    end: int                      # index one past the block's last line
    fenced: bool
    expr_lines: list[int] = field(default_factory=list)   # indices of expression lines
    props: list[str] = field(default_factory=list)        # stripped property lines

    @property
    def hidden(self) -> bool:
        return any(p == "isHidden" or p.startswith("isHidden:") and "true" in p for p in self.props)


def split_lines(text: str) -> list[str]:
    return text.split("\n")


# ---------------------------------------------------------------------------
# Byte-faithful reading and writing
# ---------------------------------------------------------------------------
@dataclass
class SourceFile:
    """A table file as read from disk: its exact bytes and an LF-only text
    view that the line-based editors work on."""

    path: Path
    raw: bytes

    @property
    def text(self) -> str:
        return self.raw.decode("utf-8").replace("\r\n", "\n")


def read_source(path: str | Path) -> SourceFile:
    path = Path(path)
    return SourceFile(path, path.read_bytes())


def _line_endings(raw_text: str) -> list[str]:
    """The terminator of every line of ``raw_text`` ("\r\n", "\n" or "" for
    an unterminated last line), aligned with ``text.split("\n")``."""
    ends = []
    for piece in raw_text.split("\n")[:-1]:
        ends.append("\r\n" if piece.endswith("\r") else "\n")
    ends.append("")
    return ends


def restore_line_endings(raw: bytes, edited: str) -> bytes:
    """Encode ``edited`` (LF-only text derived from ``raw``) with ``raw``'s
    line endings.

    Lines that the edit kept are written with the terminator they had;
    inserted or changed lines take the file's prevailing terminator (CRLF
    when most lines of the original end that way). A file that was all LF
    or all CRLF therefore stays exactly that, and every byte outside the
    edit is unchanged."""
    raw_text = raw.decode("utf-8")
    old_lines = raw_text.replace("\r\n", "\n").split("\n")
    old_ends = _line_endings(raw_text)
    crlf = sum(e == "\r\n" for e in old_ends)
    lf = sum(e == "\n" for e in old_ends)
    usual = "\r\n" if crlf > lf else "\n"
    new_lines = edited.split("\n")
    new_ends = [usual] * (len(new_lines) - 1) + [""]
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, _ in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                if j1 + k < len(new_lines) - 1:
                    new_ends[j1 + k] = old_ends[i1 + k] or usual
    return "".join(ln + end for ln, end in zip(new_lines, new_ends)).encode("utf-8")


def write_edit(source: SourceFile, edited: str, backup: Path | None = None) -> None:
    """Write ``edited`` over ``source.path`` keeping its line endings; when
    ``backup`` is given, first copy the original bytes there unchanged."""
    if backup is not None:
        backup.write_bytes(source.raw)
    source.path.write_bytes(restore_line_endings(source.raw, edited))


def measure_blocks(lines: list[str]) -> list[MeasureBlock]:
    """Every measure of a table file with its expression and property lines.

    A block runs from its declaration to the next object at one-tab indent
    (or the end of the file); trailing blank lines are left outside it."""
    blocks: list[MeasureBlock] = []
    i = 0
    while i < len(lines):
        hit = MEASURE_RE.match(lines[i])
        if not hit:
            i += 1
            continue
        name, rest = unquote(hit.group(1)), hit.group(2).strip()
        block = MeasureBlock(name=name, start=i, end=i + 1, fenced=rest.startswith("```"))
        j = i + 1
        if block.fenced:
            while j < len(lines) and lines[j].strip() != "```":
                block.expr_lines.append(j)
                j += 1
            j += 1  # closing fence
        elif not rest:
            while j < len(lines) and (lines[j].startswith("\t\t\t") or
                                      (not lines[j].strip() and _continues(lines, j))):
                block.expr_lines.append(j)
                j += 1
        while j < len(lines) and not _TOP_OBJECT_RE.match(lines[j]) and \
                not (lines[j] and not lines[j].startswith("\t")):
            if lines[j].strip():
                if lines[j].startswith("\t\t") and not lines[j].startswith("\t\t\t"):
                    block.props.append(lines[j].strip())
                block.end = j + 1
            j += 1
        blocks.append(block)
        i = max(block.end, i + 1)
    return blocks


def _continues(lines: list[str], j: int) -> bool:
    """True when a blank line sits inside an unfenced multi-line expression."""
    k = j
    while k < len(lines) and not lines[k].strip():
        k += 1
    return k < len(lines) and lines[k].startswith("\t\t\t")


def expression(lines: list[str], block: MeasureBlock) -> str:
    """The DAX text of a measure (fence and indentation removed)."""
    if block.expr_lines:
        return "\n".join(lines[k].strip() for k in block.expr_lines).strip()
    hit = MEASURE_RE.match(lines[block.start])
    return hit.group(2).strip() if hit else ""


def declared_measure_names(text: str) -> list[str]:
    return [b.name for b in measure_blocks(split_lines(text))]


_TABLE_REF_RE = re.compile(r"'((?:[^']|'')+)'|(?<![\w\]])([A-Za-z_][A-Za-z0-9_]*)\[")


def strip_comments_and_strings(dax: str) -> str:
    """DAX with string literals, `//`/`--` line comments and block comments blanked."""
    dax = re.sub(r'"(?:[^"]|"")*"', '""', dax)
    dax = re.sub(r"/\*.*?\*/", " ", dax, flags=re.S)
    return re.sub(r"(//|--).*", "", dax)


def table_refs(dax: str) -> set[str]:
    """Table names a DAX expression mentions (`'T'`, `'T'[c]` or `T[c]`)."""
    found: set[str] = set()
    for quoted, bare in _TABLE_REF_RE.findall(strip_comments_and_strings(dax)):
        name = quoted.replace("''", "'") if quoted else bare.strip()
        if name:
            found.add(name)
    return found


def table_name(text: str) -> str | None:
    hit = re.match(rf"\s*table\s+({_NAME})", text)
    return unquote(hit.group(1)) if hit else None


def table_files(model_dir: str | Path) -> list[Path]:
    tables = Path(model_dir) / "definition" / "tables"
    return sorted(tables.glob("*.tmdl")) if tables.is_dir() else []


def has_columns(text: str) -> bool:
    return re.search(r"^\tcolumn\s", text, re.M) is not None


def column_props(text: str) -> dict[str, list[str]]:
    """Column name -> its stripped property lines."""
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in split_lines(text):
        hit = re.match(rf"^\tcolumn\s+({_NAME})", line)
        if hit:
            current = unquote(hit.group(1))
            out[current] = []
        elif _TOP_OBJECT_RE.match(line):
            current = None
        elif current is not None and line.startswith("\t\t") and line.strip():
            out[current].append(line.strip())
    return out


def partition_source(text: str) -> str:
    """The text of every partition's source (fenced or indented), joined."""
    lines = split_lines(text)
    chunks: list[str] = []
    i = 0
    while i < len(lines):
        if re.match(r"^\tpartition\s", lines[i]):
            j = i + 1
            while j < len(lines) and not _TOP_OBJECT_RE.match(lines[j]):
                chunks.append(lines[j])
                j += 1
            i = j
        else:
            i += 1
    return "\n".join(chunks)


_OPENERS, _CLOSERS = "([{", ")]}"


def _split_top(text: str, sep: str) -> list[str]:
    """Split on ``sep`` outside strings, quoted names and brackets."""
    pieces: list[str] = []
    start = level = 0
    pos, size = 0, len(text)
    while pos < size:
        ch = text[pos]
        if ch == '"' or ch == "'":
            # skip a quoted run; a doubled quote is an escaped quote
            pos += 1
            while pos < size and not (text[pos] == ch and text[pos + 1:pos + 2] != ch):
                pos += 2 if text[pos] == ch else 1
        elif ch in _OPENERS:
            level += 1
        elif ch in _CLOSERS:
            level -= 1
        elif ch == sep and not level:
            pieces.append(text[start:pos])
            start = pos + 1
        pos += 1
    pieces.append(text[start:])
    return pieces


def selector_rows(text: str) -> list[list[str]]:
    """The tuples of a field-parameter table's ``{ (...), (...) }`` source.

    Each row comes back as its raw, stripped fields. Commented-out lines are
    ignored and nested parentheses (``NAMEOF(...)``) stay inside their field.
    """
    src = "\n".join(re.sub(r"^\s*(//|--).*$", "", ln)
                    for ln in partition_source(text).split("\n"))
    open_at = src.find("{")
    close_at = src.rfind("}")
    if open_at < 0 or close_at <= open_at:
        return []
    rows = []
    for chunk in _split_top(src[open_at + 1:close_at], ","):
        chunk = chunk.strip()
        if chunk.startswith("(") and chunk.endswith(")"):
            rows.append([f.strip() for f in _split_top(chunk[1:-1], ",")])
    return rows


_NAMEOF_RE = re.compile(r"NAMEOF\s*\(\s*('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)\s*\[([^\]]+)\]\s*\)",
                        re.I)


def nameof_target(field_text: str) -> tuple[str, str] | None:
    """``(table, object)`` of a ``NAMEOF('T'[x])`` field, else None."""
    hit = _NAMEOF_RE.search(field_text)
    return (unquote(hit.group(1)), hit.group(2)) if hit else None


def string_literal(field_text: str) -> str | None:
    t = field_text.strip()
    if len(t) >= 2 and t[0] == t[-1] == '"':
        return t[1:-1].replace('""', '"')
    return None
