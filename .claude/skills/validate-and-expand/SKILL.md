---
name: validate-and-expand
description: >-
  Validate an existing pbip-model-forge PBIP with pbip-forge check and
  tmdl-preflight, and expand it (add tables, columns, measures, relationships)
  while keeping it openable and correct. Use when the user wants to grow or
  modify a sample model already created with create-sample-model, or asks to
  "check this model", "keep it valid", "add a measure/dimension and re-verify".
  Wraps the two-gate loop.
---

# validate-and-expand

The "expand and keep-valid" loop for a model built by `create-sample-model`.
The invariant: **the spec is the source of truth; the TMDL is regenerated,
never hand-edited; every change passes `pbip-forge check` (0 P0/P1) and then
`tmdl-preflight check` (0 errors).**

## The loop

1. **Locate the spec.** Prefer the spec file from the conversation (a Python
   file with a module-level `SPEC`). If it is gone, reconstruct it from
   `out/<Domain>/handoff/manifest.json` (tables, roles, columns, types, keys,
   relationships, measures) and the sample rows in the conversation. Keep the
   spec file between turns so you never have to reverse-engineer it.

2. **Apply the requested change to the spec**, not to the TMDL:
   - *Add a dimension*: append a table (exactly one `key: True` column, a few
     attributes, `rows`, a one-line `description`) and a relationship
     `Fact.<fk> -> NewDim.<key>`. Name the FK exactly like the key and give it
     the same type. Add the FK column to the fact and a value to **every** fact
     row; use an "Unknown" member (for example key `-1`) for rows with no real
     match, never a null.
   - *Add a measure*: append to `measures_table["measures"]` with a `format`
     and a one-line `description`, named by the convention below. Count
     entities from the fact's FK (`DISTINCTCOUNT(Fact[fk])`), never from the
     dimension table.
   - *Add a column*: append to that table's `columns` and add a matching value
     to **every** row in `rows` (row width must equal column count).
   - *Change grain / date range*: adjust fact `rows`; the calendar range is
     inferred from the fact dates unless the spec pins `start_year`/`end_year`.

   | Pattern | Use for | Format |
   |---|---|---|
   | `X #` | counts | `#,0` |
   | `X %` | shares and rates | `0.0%` |
   | `Avg X` | averages | `#,0.0` or currency |
   | `Total X` | additive sums | currency or `#,0` |
   | `X per Y` | ratios of two measures | as the numerator |

3. **Gate the spec:** `pbip-forge check <spec file> --profile handoff` →
   require **0 P0 and 0 P1**. Each violation names the rule, the object and
   the fix; fix the spec and re-check.

4. **Rebuild:** `pbip-forge build <spec file> <out_dir>` (or
   `build_pbip(spec, out_dir)`; overwrites in place, including `handoff/`).

5. **Gate the files:** `tmdl-preflight check <out_dir>` → require **0 errors**.
   `tmdl-preflight fix <path>` can auto-repair M003/M004/M006, but the right
   move is to fix the spec and regenerate.

6. **Report** the diff (what tables, measures and relationships changed), the
   refreshed diagram from `handoff/SPEC.md`, and both gate results.

## Rule quick reference

`pbip-forge rules` prints the full catalog. The ones expansions trip most:

| Rule | Meaning | Spec-level fix |
|---|---|---|
| FM003 | dimension without exactly one key | mark one column `key: True` |
| FM004 | key values duplicated or null | make keys unique and non-null |
| FM005 | FK value missing from the dimension, or null | add an "Unknown" member row |
| FM006 / FM007 | FK/PK type differs / name differs | same type; same name |
| FM008 | fact has no active calendar relationship | relate its primary date to `__Calendar.Date` |
| FM009 | dimension reaches no fact | add the relationship or drop the table |
| FM011 | second active path between two tables | set one relationship `"active": False` |
| FM013 | DAX names something that does not exist | fix the name |
| FM015 | ratio denominator counts a dimension | `DISTINCTCOUNT(Fact[fk])` |
| FM016-FM019 | format, description, folder, name/format | fill them in |
| M005 | column dataType not engine-valid | use int64/string/double/decimal/datetime/boolean |
| M006 / M007 | table not referenced / no partition | rebuild through build_pbip |
| M008 | inline `#table(...)` entity source | never hand-author data |

Never claim a model opens in Power BI Desktop beyond what tmdl-preflight
proves; an actual Desktop open is a human verification step.
