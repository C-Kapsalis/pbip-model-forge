"""`pbip-forge table dump`: the original's listing, byte for byte.

The original (`decrypt_binary_table.py`) prints a fixed block:

    Columns: <repr of row 0>

    Total rows: <n>

    Data (first <M> rows):
    <80 dashes>
      1. <repr of row 1>
    ... and <k> more rows

This test pins that block, the file mode, and the decode error.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_helpers import forge, raw_deflate_b64

RULE = "-" * 80


def _payload(rows: list) -> str:
    return raw_deflate_b64(json.dumps(rows).encode())


def _tmdl(payload: str) -> str:
    return (
        "table 'Entered'\n"
        "\tlineageTag: 00000000-0000-0000-0000-000000000001\n\n"
        "\tpartition 'Entered' = m\n"
        "\t\tmode: import\n"
        "\t\tsource =\n"
        f'\t\t\t\tBinary.FromText("{payload}", BinaryEncoding.Base64)\n')


def _rows(n: int) -> list:
    return [["A", "B"]] + [[f"r{i}", None] for i in range(n)]


def _write(tmp_path: Path, rows: list) -> Path:
    path = tmp_path / "Entered.tmdl"
    path.write_text(_tmdl(_payload(rows)), encoding="utf-8")
    return path


# ── item 41: the listing ──────────────────────────────────────────────────

def test_the_listing_is_the_original_shape(tmp_path):
    """Item 41: the block, exactly."""
    path = _write(tmp_path, _rows(3))
    run = forge("table", "dump", str(path))
    assert run.code == 0, run.text
    assert run.out == (
        "Columns: ['A', 'B']\n"
        "\n"
        "Total rows: 3\n"
        "\n"
        "Data (first 20 rows):\n"
        f"{RULE}\n"
        "  1. ['r0', None]\n"
        "  2. ['r1', None]\n"
        "  3. ['r2', None]\n"
    ), run.out


def test_the_row_number_is_right_aligned_in_three(tmp_path):
    """Item 41: `<i> .` right-aligned in 3."""
    path = _write(tmp_path, _rows(12))
    run = forge("table", "dump", str(path))
    assert run.code == 0, run.text
    assert "  1. [" in run.out, run.out
    assert " 12. [" in run.out, run.out


def test_the_hidden_rows_are_counted(tmp_path):
    """Item 41: the last line appears only when k > 0."""
    path = _write(tmp_path, _rows(25))
    run = forge("table", "dump", str(path))
    assert run.code == 0, run.text
    assert "Data (first 20 rows):" in run.out, run.out
    assert "... and 5 more rows" in run.out, run.out


def test_max_rows_changes_the_listing(tmp_path):
    """Item 41: `<M>` is `--max-rows`."""
    path = _write(tmp_path, _rows(25))
    run = forge("table", "dump", str(path), "--max-rows", "3")
    assert run.code == 0, run.text
    assert "Data (first 3 rows):" in run.out, run.out
    assert "... and 22 more rows" in run.out, run.out


def test_an_empty_array_prints_no_data(tmp_path):
    """Item 41: the kept BUGFIX."""
    path = _write(tmp_path, [])
    run = forge("table", "dump", str(path))
    assert run.code == 0, run.text
    assert run.out == "No data\n", run.out


# ── item 39: the file mode ────────────────────────────────────────────────

def test_a_file_with_no_payload_fails(tmp_path):
    """Item 39: the message and exit 1."""
    path = tmp_path / "Empty.tmdl"
    path.write_text("table 'Entered'\n", encoding="utf-8")
    run = forge("table", "dump", str(path))
    assert run.code == 1, run.text
    assert f"No binary data found in {path}" in run.err, run.err


def test_only_the_first_payload_is_read(tmp_path):
    """Item 39: the first payload wins."""
    path = tmp_path / "Two.tmdl"
    path.write_text(
        _tmdl(_payload([["A"], ["1"]])) + "\n" + _tmdl(_payload([["B"], ["2"]])),
        encoding="utf-8")
    run = forge("table", "dump", str(path))
    assert run.code == 0, run.text
    assert "Columns: ['A']" in run.out, run.out


# ── item 40: the decode errors ────────────────────────────────────────────

def test_a_corrupt_payload_prints_the_error_on_stdout(tmp_path):
    """Item 40: the message and exit 1."""
    path = tmp_path / "Broken.tmdl"
    path.write_text(
        'table \'Entered\'\n\tpartition \'Entered\' = m\n\t\tsource =\n'
        '\t\t\t\tBinary.FromText("!!!not base64!!!", BinaryEncoding.Base64)\n',
        encoding="utf-8")
    run = forge("table", "dump", str(path))
    assert run.code == 1, run.text
    assert "Error decrypting: " in run.out, run.out


def test_a_payload_that_is_not_an_array_is_rejected(tmp_path):
    """Item 40: the kept BUGFIX — the original crashed on it."""
    path = tmp_path / "Object.tmdl"
    path.write_text(_tmdl(_payload({"a": 1})), encoding="utf-8")
    run = forge("table", "dump", str(path))
    assert run.code == 1, run.text
    assert "Error decrypting: " in run.out, run.out
