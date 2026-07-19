---
name: validate-and-expand
description: >-
  Validate an existing pbip-model-forge PBIP with tmdl-preflight and expand it
  (add tables, columns, measures, relationships) while keeping it openable. Use
  when the user wants to grow or modify a sample model already created with
  create-sample-model, or asks to "check this model", "keep it valid", "add a
  measure/dimension and re-verify". Wraps the tmdl-preflight gate loop.
---

# validate-and-expand

The "expand and keep-valid" loop for a model built by `create-sample-model`.
The invariant: **the spec dict is the source of truth; the TMDL is regenerated,
never hand-edited; every change is gated by `tmdl-preflight check`.**

## The loop

1. **Locate the spec.** If it isn't in the conversation, reconstruct it from the
   generated files (table columns/types from `tables/*.tmdl`, relationships from
   `relationships.tmdl`) into a `build_pbip` spec dict. Prefer keeping the spec
   in the conversation between turns so you never have to reverse-engineer it.

2. **Apply the requested change to the spec dict**, not to the TMDL:
   - *Add a dimension*: append a table dict (key column `key: True` + attrs +
     `rows`), and a relationship `Fact.<fk> -> NewDim.<key>` (matching `int64`
     types). Add the FK column to the fact table if it isn't there.
   - *Add a measure*: append to `measures_table["measures"]` with a `format`.
   - *Add a column*: append to that table's `columns` and add a matching value
     to **every** row in `rows` (row width must equal column count).
   - *Change grain / date range*: adjust fact `rows` and the `calendar`
     `start_year`/`end_year` so relationships still resolve.

3. **Rebuild:** `build_pbip(spec, out_dir)` (overwrites in place).

4. **Gate:** `tmdl-preflight check <out_dir>` → require **0 errors**. Read any
   violation (file, line, rule id) and fix the spec, then rebuild + re-check.
   `tmdl-preflight fix <path>` can auto-repair M003/M004/M006 lineage/ref issues,
   but the right move is to fix the spec and regenerate.

5. **Report** the diff (what tables/measures/relationships changed) and the
   fresh 0-error result.

## Rule quick reference (what the gate catches)
| Rule | Meaning | Spec-level fix |
|---|---|---|
| M001 | model.tmdl / tables folder missing | rebuild through build_pbip |
| M005 | column dataType not engine-valid | use int64/string/double/decimal/datetime/boolean |
| M006 | table not referenced in model.tmdl | rebuild (builder writes every `ref table`) |
| M007 | a table has no partition | rebuild (builder always adds one) |
| M008 | inline `#table(...)` entity source | never hand-author data; builder uses entered-data |

Structural rules live in `tmdl-preflight/src/tmdl_preflight/rules/structural.py`.
Never claim a model opens in Power BI Desktop beyond what tmdl-preflight proves;
an actual Desktop open is a human verification step.
