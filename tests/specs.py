"""Tiny spec dicts shared by the build and check tests.

``good_spec()`` passes ``pbip-forge check --profile handoff`` with no
violations at all; tests mutate a fresh copy to trip one rule at a time.
"""

from __future__ import annotations

import datetime as dt
from typing import Any


def good_spec() -> dict[str, Any]:
    return {
        "name": "Tiny",
        "tables": [
            {
                "name": "Stores",
                "description": "One row per store.",
                "columns": [
                    {"name": "store_id", "type": "int64", "key": True},
                    {"name": "store_name", "type": "string",
                     "description": "Store trading name."},
                ],
                "rows": [[1, "North"], [2, "South"], [-1, "Unknown"]],
            },
            {
                "name": "Products",
                "description": "One row per product.",
                "columns": [
                    {"name": "product_id", "type": "int64", "key": True},
                    {"name": "product_name", "type": "string",
                     "description": "Product display name."},
                ],
                "rows": [[10, "Bike"], [11, "Helmet"]],
            },
            {
                "name": "Sales",
                "description": "One row per order line.",
                "hidden": True,
                "columns": [
                    {"name": "order_id", "type": "int64"},
                    {"name": "order_date", "type": "datetime"},
                    {"name": "store_id", "type": "int64"},
                    {"name": "product_id", "type": "int64"},
                    {"name": "amount", "type": "double", "summarizeBy": "sum"},
                ],
                "rows": [
                    [1, dt.date(2023, 3, 1), 1, 10, 100.0],
                    [2, dt.date(2023, 7, 9), 2, 11, 40.0],
                    [3, dt.date(2024, 1, 2), -1, 10, 120.0],
                ],
            },
        ],
        "calendar": {"name": "__Calendar"},
        "measures_table": {
            "name": "Key Measures",
            "description": "Home table for every measure.",
            "measures": [
                {"name": "Total Sales", "expression": "SUM(Sales[amount])",
                 "format": "$ #,0.00", "description": "Total sales amount."},
                {"name": "Orders #", "expression": "DISTINCTCOUNT(Sales[order_id])",
                 "format": "#,0", "description": "Number of distinct orders."},
                {"name": "Stores #", "expression": "DISTINCTCOUNT(Sales[store_id])",
                 "format": "#,0", "description": "Stores with at least one sale."},
                {"name": "Avg Sales per Store",
                 "expression": "DIVIDE([Total Sales], [Stores #])",
                 "format": "$ #,0.00", "description": "Average sales per selling store."},
                {"name": "Bike Share %",
                 "expression": (
                     "DIVIDE(CALCULATE([Total Sales], Products[product_name] = \"Bike\"), "
                     "[Total Sales])  -- share of sales from bikes"
                 ),
                 "format": "0.0%", "description": "Share of sales that are bikes."},
                {"name": "Sales Base", "expression": "SUM(Sales[amount])",
                 "format": "#,0", "helper": True},
            ],
        },
        "relationships": [
            {"from": "Sales.store_id", "to": "Stores.store_id"},
            {"from": "Sales.product_id", "to": "Products.product_id"},
            {"from": "Sales.order_date", "to": "__Calendar.Date"},
        ],
    }
