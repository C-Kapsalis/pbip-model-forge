"""Regression tests locking the encoder to Power BI Desktop's own byte layout.

The three golden base64 strings below were emitted by Power BI Desktop (they
live in the proven-openable bike-shop-clean example). If encode_rows ever drifts
from Power BI's format, these fail -- which means generated models may stop
opening.

Run: python -m pytest tests/  (or: python tests/test_enter_data.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbip_model_forge.enter_data import decode_base64, encode_rows  # noqa: E402

# base64 -> the exact string Power BI wrote for these rows.
GOLDEN = {
    # empty measures dummy partition: [[" "]]
    "i45WUlCKjQUA": [[" "]],
    # Stores dim
    "i45WMlTSUXLJL88rAWIg0y+/qCRDKVYnWskIyPNILErKLwIygvNLocLGQF5oAarqWAA=": [
        ["1", "Downtown", "North"],
        ["2", "Harbor", "South"],
        ["3", "Uptown", "North"],
    ],
    # Products dim
    "i45WMlTSUQrKT0xRcMrMTgWyQVQxkDY0MjBQitWJVjICcjxSc3JTS4AMx+Tk1OLi/KJMsBoLiApjIDNU1yc/ORtDhbEpWIUJkOmbX5pXkpiZh2GRKciiWAA=": [
        ["1", "Road Bike", "Bikes", "1200"],
        ["2", "Helmet", "Accessories", "80"],
        ["3", "U-Lock", "Accessories", "35"],
        ["4", "Mountain Bike", "Bikes", "1500"],
    ],
}


def test_encoder_matches_powerbi_golden():
    for b64, rows in GOLDEN.items():
        assert encode_rows(rows) == b64, f"drift for rows={rows}"


def test_roundtrip():
    for b64, rows in GOLDEN.items():
        assert decode_base64(b64) == rows


def test_value_coercion():
    import datetime as dt

    # int, float, date, bool, None -> strings / null
    b64 = encode_rows([[1, 2.5, dt.date(2024, 1, 2), True, None]])
    assert decode_base64(b64) == [["1", "2.5", "2024-01-02", "TRUE", None]]


if __name__ == "__main__":
    test_encoder_matches_powerbi_golden()
    test_roundtrip()
    test_value_coercion()
    print("all tests passed")
