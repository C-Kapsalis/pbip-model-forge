"""Build the seed/template PBIP under template/Model.*.

Run:  python scripts/build_template.py
Then: tmdl-preflight check template

This is also the canonical worked example of a spec dict fed to build_pbip.
The model is a small but real retail-sales star schema:
    Customers  (dim)   Products (dim)   Sales (fact)   __Calendar (calc dim)
    Measures   (measures-only table with dummy partition)
with four relationships (product, customer, order-date active, ship-date
inactive) into the fact.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

# Make src/ importable when run directly from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbip_model_forge.build_model import build_pbip  # noqa: E402


SPEC = {
    "name": "Model",
    "tables": [
        {
            "name": "Customers",
            "description": "One row per customer.",
            "columns": [
                {"name": "customer_id", "type": "int64", "key": True},
                {"name": "customer_name", "type": "string"},
                {"name": "segment", "type": "string"},
                {"name": "country", "type": "string"},
            ],
            "rows": [
                [1, "Aurora Labs", "Enterprise", "United States"],
                [2, "Bright Retail", "SMB", "United Kingdom"],
                [3, "Cobalt Foods", "SMB", "Germany"],
                [4, "Delta Health", "Enterprise", "United States"],
                [5, "Evergreen Co", "Mid-Market", "Canada"],
            ],
        },
        {
            "name": "Products",
            "description": "Product catalog.",
            "columns": [
                {"name": "product_id", "type": "int64", "key": True},
                {"name": "product_name", "type": "string"},
                {"name": "category", "type": "string"},
                {"name": "unit_price", "type": "double", "format": "$ #,0.00"},
            ],
            "rows": [
                [1, "Standard Plan", "Subscriptions", 49.00],
                [2, "Pro Plan", "Subscriptions", 149.00],
                [3, "Onboarding Pack", "Services", 500.00],
                [4, "Support Add-on", "Services", 90.00],
            ],
        },
        {
            "name": "Sales",
            "description": "One row per order line. Core fact table.",
            "hidden": True,
            "columns": [
                {"name": "order_id", "type": "int64", "hidden": True},
                {"name": "order_date", "type": "datetime", "hidden": True,
                 "format": "General Date"},
                {"name": "ship_date", "type": "datetime", "hidden": True,
                 "format": "General Date"},
                {"name": "customer_id", "type": "int64", "hidden": True},
                {"name": "product_id", "type": "int64", "hidden": True},
                {"name": "quantity", "type": "int64", "hidden": True,
                 "summarizeBy": "sum"},
                {"name": "net_amount", "type": "double", "hidden": True,
                 "summarizeBy": "sum"},
            ],
            "rows": [
                [1001, dt.date(2024, 1, 15), dt.date(2024, 1, 17), 1, 2, 3, 447.00],
                [1002, dt.date(2024, 2, 3), dt.date(2024, 2, 6), 2, 1, 10, 490.00],
                [1003, dt.date(2024, 3, 21), dt.date(2024, 3, 22), 3, 3, 1, 500.00],
                [1004, dt.date(2024, 6, 9), dt.date(2024, 6, 12), 4, 2, 5, 745.00],
                [1005, dt.date(2024, 9, 30), dt.date(2024, 10, 2), 1, 4, 8, 720.00],
                [1006, dt.date(2025, 1, 11), dt.date(2025, 1, 13), 5, 1, 4, 196.00],
                [1007, dt.date(2025, 4, 5), dt.date(2025, 4, 7), 2, 2, 2, 298.00],
                [1008, dt.date(2025, 7, 18), dt.date(2025, 7, 21), 4, 3, 1, 500.00],
            ],
        },
    ],
    "calendar": {"name": "__Calendar", "start_year": 2024, "end_year": 2025},
    "measures_table": {
        "name": "Key Measures",
        "description": "Measure home table: all user-facing measures live here.",
        "measures": [
            {"name": "Revenue", "expression": "SUM(Sales[net_amount])",
             "format": "$ #,0.00", "description": "Total net revenue."},
            {"name": "Orders #", "expression": "DISTINCTCOUNT(Sales[order_id])",
             "format": "#,0"},
            {"name": "Units Sold", "expression": "SUM(Sales[quantity])",
             "format": "#,0"},
            {"name": "Average Order Value",
             "expression": "DIVIDE([Revenue], [Orders #])", "format": "$ #,0.00"},
        ],
    },
    "relationships": [
        {"from": "Sales.product_id", "to": "Products.product_id"},
        {"from": "Sales.customer_id", "to": "Customers.customer_id"},
        {"from": "Sales.order_date", "to": "__Calendar.Date"},
        {"from": "Sales.ship_date", "to": "__Calendar.Date", "active": False},
    ],
}


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "template"
    pbip = build_pbip(SPEC, out)
    print(f"Built template PBIP: {pbip}")


if __name__ == "__main__":
    main()
