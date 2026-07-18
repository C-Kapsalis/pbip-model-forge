# Add a measure, a dimension, or a relationship

**Goal:** the field-level edits for the three most common expansions. Each edits
the **spec dict**, then rebuilds and re-gates. Never edit the generated TMDL.

After every change:

```python
import sys; sys.path.insert(0, "src")
from pbip_model_forge.build_model import build_pbip
build_pbip(spec, "out/<Domain>")
```
```powershell
tmdl-preflight check out/<Domain>   # must be 0 errors
```

## Add a measure

Append to `measures_table["measures"]`. `name` and `expression` are required;
give it a `format` so it renders cleanly. DAX may be single- or multi-line.

```python
spec["measures_table"]["measures"].append(
    {"name": "Gross Margin %",
     "expression": "DIVIDE([Revenue] - [Cost], [Revenue])",
     "format": "0.0%",
     "description": "Margin as a share of revenue."}   # description optional
)
```

Measures reference the fact table (or other measures). No new relationship is
needed.

## Add a dimension

1. Append a table dict — an `int64` key column with `key: True`, a few
   attributes, and `rows`:

   ```python
   spec["tables"].append({
       "name": "Promotions",
       "columns": [
           {"name": "promo_id", "type": "int64", "key": True},
           {"name": "promo_name", "type": "string"},
           {"name": "discount_pct", "type": "double", "format": "0.0%"},
       ],
       "rows": [[1, "Spring Sale", 0.10], [2, "Clearance", 0.25]],
   })
   ```

2. Add the foreign key to the **fact** table's `columns` if it isn't there — and
   add a matching value to **every** existing fact row (row width must equal
   column count).

3. Add the relationship (see below).

## Add a relationship

Append to `spec["relationships"]`. `from` and `to` are `"Table.Column"` strings;
`active` defaults to `True`.

```python
spec["relationships"].append(
    {"from": "Sales.promo_id", "to": "Promotions.promo_id"}
)
# secondary date relationships must be inactive:
spec["relationships"].append(
    {"from": "Sales.ship_date", "to": "__Calendar.Date", "active": False}
)
```

**Both endpoint columns must exist and share the same declared type** — fact FK
`int64` ↔ dim key `int64`, date `datetime` ↔ `__Calendar.Date`. A misspelled
column name or a type mismatch is the usual cause of a relationship error at the
gate.

## If the gate complains

| Symptom | Cause | Fix |
|---|---|---|
| M005 | a column `type` isn't engine-valid | use int64/string/double/decimal/datetime/boolean |
| relationship error | endpoint missing or type-mismatched | correct the column name / align types in the spec |
| row-width error on rebuild | a row has the wrong number of cells | give every row exactly one value per column |

Fix the spec, rebuild, re-check. Full field reference:
[The `build_pbip` spec schema](../reference/spec-schema.md).
