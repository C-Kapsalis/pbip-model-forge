"""Encoded entered-data codec and `pbip-forge table dump`.

Spec H-encoded-table-codec, cases 1-7. Proposed API in
``pbip_model_forge.enter_data``:

* ``encode_rows(rows, parity_json=False)`` - existing compact encoder; with
  ``parity_json=True`` it uses default JSON spacing, ASCII escaping and keeps
  cell values as they are (no stringify);
* ``decode_file(path)`` - rows of the FIRST ``Binary.FromText("...")`` payload
  of a TMDL file; ``ValueError("no encoded payload in <file>")`` when none;
* ``decode_b64_or_none(b64)`` - rows, or ``None`` plus one error line on the
  console when the payload does not decode.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ported_helpers import entered_data_tmdl, forge, inflate_b64, raw_deflate_b64

from pbip_model_forge import enter_data

ROWS = [["Group", "Sub", "Key"], ["Retail", "", "store_id"]]


# -- case 1 ----------------------------------------------------------------------
def test_case1_parity_round_trip_keeps_row_zero():
    b64 = enter_data.encode_rows(ROWS, parity_json=True)
    assert enter_data.decode_b64_or_none(b64) == ROWS
    assert enter_data.decode_base64(b64) == ROWS


# -- case 2 ----------------------------------------------------------------------
def test_case2_parity_spacing_and_bytes():
    rows = [["Group", "Sub", "Key"], ["Retail", 7, "café"]]
    parity = enter_data.encode_rows(rows, parity_json=True)
    text = inflate_b64(parity).decode("utf-8")
    assert text.startswith('[["Group", "Sub", "Key"], ')
    assert '"caf\\u00e9"' in text                      # ASCII escaping
    assert json.loads(text)[1][1] == 7                  # number stays a number
    # byte-exact: default separators, level-9 raw deflate, padded base64
    assert parity == raw_deflate_b64(json.dumps(rows).encode("utf-8"))

    compact = enter_data.encode_rows(rows)
    assert compact != parity
    assert json.loads(inflate_b64(compact))[1][1] == "7"   # compact stringifies
    assert inflate_b64(compact).decode().startswith('[["Group","Sub","Key"],')


def test_compact_mode_is_unchanged_today():
    """The existing default encoder keeps its Power BI byte layout."""
    assert enter_data.encode_rows([[" "]]) == "i45WUlCKjQUA"


# -- case 3 ----------------------------------------------------------------------
def test_case3_two_payloads_only_first_is_read(tmp_path):
    first = enter_data.encode_rows([["Name", "City"], ["Beanery", "Porto"]])
    second = enter_data.encode_rows([["Other", "Thing"], ["x", "y"]])
    f = tmp_path / "Shops.tmdl"
    f.write_text(entered_data_tmdl("Shops", [first, second]), encoding="utf-8")
    before = f.read_bytes()

    assert enter_data.decode_file(f) == [["Name", "City"], ["Beanery", "Porto"]]
    run = forge("table", "dump", f)
    assert run.code == 0, run.text
    assert "Name" in run.out and "Beanery" in run.out
    assert "Other" not in run.out
    assert f.read_bytes() == before


# -- case 4 ----------------------------------------------------------------------
def test_case4_file_without_payload(tmp_path):
    f = tmp_path / "Plain.tmdl"
    f.write_text("table Plain\n\tcolumn A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no encoded payload"):
        enter_data.decode_file(f)


# -- case 5 ----------------------------------------------------------------------
def test_case5_corrupt_base64_returns_nothing_and_one_error_line(capsys):
    assert enter_data.decode_b64_or_none("@@@not base64@@@") is None
    captured = capsys.readouterr()
    lines = [ln for ln in (captured.out + captured.err).splitlines() if ln.strip()]
    assert len(lines) == 1, lines

    run = forge("table", "dump", "--b64", "@@@not base64@@@")
    assert run.code == 1, run.text
    assert run.out == ""
    assert len(run.err.strip().splitlines()) == 1, run.err


# -- case 6 ----------------------------------------------------------------------
def _dump_rows(n: int, tmp_path: Path) -> Path:
    rows = [["Shop", "Region"]] + [[f"shop{i:02d}", "North"] for i in range(1, n + 1)]
    f = tmp_path / "Shops.tmdl"
    f.write_text(entered_data_tmdl("Shops", [enter_data.encode_rows(rows)]), encoding="utf-8")
    return f


def test_case6_dump_shows_first_twenty_of_twenty_five(tmp_path):
    run = forge("table", "dump", _dump_rows(25, tmp_path))
    assert run.code == 0, run.text
    assert "Shop" in run.out and "Region" in run.out
    assert "Data rows: 25\n" in run.out
    assert "shop20" in run.out and "shop21" not in run.out
    assert run.out.splitlines()[-1] == "... 5 more rows not shown (use --max-rows)"
    assert re.search(r"^\s*1\b.*shop01", run.out, re.M)   # 1-based numbering


def test_case6_max_rows_option(tmp_path):
    run = forge("table", "dump", _dump_rows(25, tmp_path), "--max-rows", "3")
    assert run.code == 0, run.text
    assert "shop03" in run.out and "shop04" not in run.out
    assert run.out.splitlines()[-1] == "... 22 more rows not shown (use --max-rows)"


# -- case 7 ----------------------------------------------------------------------
def test_case7_dump_of_empty_array(tmp_path):
    f = tmp_path / "Empty.tmdl"
    f.write_text(entered_data_tmdl("Empty", [enter_data.encode_rows([])]), encoding="utf-8")
    run = forge("table", "dump", f)
    assert run.code == 0, run.text
    lines = [ln for ln in run.out.splitlines() if ln.strip()]
    assert len(lines) == 1 and "no data" in lines[0].lower(), run.out
