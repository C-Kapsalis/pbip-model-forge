# Expand a model and keep it valid

**Goal:** grow an existing model — add tables, columns, measures, relationships —
without breaking the open. This is the
[`validate-and-expand`](../../.claude/skills/validate-and-expand/SKILL.md) loop.

The one invariant: **the spec dict is the source of truth; the TMDL is
regenerated, never hand-edited; every change is gated by `tmdl-preflight check`.**

## 1. Locate the spec

Keep the spec dict in the conversation between turns so you never have to
reverse-engineer it. If it isn't around, reconstruct it from the generated files
(table columns/types from `tables/*.tmdl`, relationships from
`relationships.tmdl`) back into a `build_pbip` spec dict.

## 2. Apply the change to the spec — not the TMDL

See [Add a measure, a dimension, or a relationship](add-a-measure-dimension-relationship.md)
for the field-level recipes. In short:

- **Add a dimension** → append a table dict (key column + attrs + `rows`) and a
  relationship `Fact.<fk> -> NewDim.<key>` (matching `int64`); add the FK column
  to the fact if missing.
- **Add a measure** → append to `measures_table["measures"]` with a `format`.
- **Add a column** → append to that table's `columns` **and** add a value to
  *every* row (row width must equal column count).
- **Change grain / date range** → adjust fact `rows` and the `calendar`
  `start_year`/`end_year` so relationships still resolve.

## 3. Rebuild (overwrites in place)

```python
import sys; sys.path.insert(0, "src")
from pbip_model_forge.build_model import build_pbip
build_pbip(spec, "out/<Domain>")
```

## 4. Gate

```powershell
tmdl-preflight check out/<Domain>
# tmdl-preflight: 0 error(s), 0 warning(s), 0 info(s)
```

Require **0 errors**. Read any violation (file, line, rule id), fix the spec,
rebuild, re-check. `tmdl-preflight fix <path>` can auto-repair M003/M004/M006
lineage/ref issues — but the right move is always to fix the spec and regenerate,
so the fix survives the next rebuild.

## 5. Report the diff

State what tables/measures/relationships changed and show the fresh 0-error
result. Keep the updated spec in the conversation for the next turn.

## Why not just edit the TMDL?

Because the invariants (a `ref table` for every table, a partition on every
table, the required annotations, compressed entered-data instead of inline
`#table`, type-consistent relationships) only hold if the builder writes the
files. A hand edit silently drops one and the model stops opening. See
[The spec is the source of truth](../explanation/spec-as-source-of-truth.md).
