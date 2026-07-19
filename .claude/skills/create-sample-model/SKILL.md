---
name: create-sample-model
description: >-
  Create a sample Power BI data model (PBIP semantic model + blank report) for a
  business domain. Use when the user says things like "create a sample data model
  for <domain>", "prototype a semantic model for <X>", "mock up a star schema for
  <X>", or "generate a PBIP with sample data". Invents realistic tables/columns/
  rows, emits an openable PBIP with the data physically loaded, validates it with
  tmdl-preflight, and can iteratively expand it (relationships, measures,
  dimensions) while staying valid. The end product is a data-model spec a user
  can hand to data engineers.
---

# create-sample-model

Turn a one-line request ("create a sample data model for a hospital", "…for
subscription analytics", "…for a logistics company") into a **real, openable
PBIP** — a Power BI semantic model with plausible sample data physically loaded,
plus a blank report — then validate and iterate on it. The deliverable is a
**spec**: a diagram-style summary of the model plus the PBIP files that a data
engineer can open in Power BI Desktop and use as a blueprint.

## Requirements (check once, up front)

This skill drives two things that must be present:

1. **This repo's builder** — `pbip_model_forge` under `src/`. No pip deps.
2. **`tmdl-preflight`** — the user's validation tool, installed separately (its
   console command `tmdl-preflight` must be on PATH). This is the **gate**: a
   model is only "done" when `tmdl-preflight check` reports 0 errors. If the
   command is missing, tell the user to install it (see the repo README) — do
   not claim a model opens without it passing.

Verify with: `tmdl-preflight --version`.

## The golden rule

**Never hand-write TMDL partition M or entered-data base64.** Always go through
`pbip_model_forge.build_model.build_pbip(spec, out_dir)`. The builder bakes in
every item of the will-it-open playbook (full artifact set, `ref table` for
every table, a partition on every table including the dummy measures partition,
compressed entered-data instead of inline `#table`, the required annotations, a
self-contained calculated calendar, typed relationships). Your job is to invent
a good *spec*; the builder guarantees it is structurally openable.

## Workflow

### 1. Interpret the domain and design a star schema
From the user's domain, invent:
- **1 fact table** (hidden) — the grain (one row per order / visit / shipment /
  event). Include foreign-key columns (`int64`), 1-2 date columns
  (`datetime`), and 1-2 additive measures columns (`double`/`int64`,
  `summarizeBy: sum`).
- **2-4 dimension tables** — each with an `int64` key column (`key: True`) and a
  few descriptive `string`/`double` attributes.
- Generate **realistic sample rows** (roughly 4-8 dimension rows, 8-20 fact
  rows). Use real-sounding names, sensible categories, dates spread across the
  calendar range, and amounts that reconcile with quantity × price where it
  makes sense.

### 2. Add a calendar, a measures table, and relationships
- `calendar`: `{"name": "__Calendar", "start_year": <min year in data>,
  "end_year": <max year>}`. The builder makes it a self-contained calculated
  table with a date hierarchy and `dataCategory: Time`.
- `measures_table`: a measures-home table with 3-6 DAX measures (Revenue,
  Count, averages, ratios) each with a `format`. Measures reference the fact
  table. **Never name it `Measures`** — that name is reserved in Power BI and
  Desktop refuses to open the model (*"Unsupported Table name"*). Use
  `Key Measures` or a domain name like `Sales Measures` / `Clinic Measures`.
  (The builder also guards this and will raise if a reserved name slips in.)
- `relationships`: one per foreign key from the fact into each dimension, plus
  `Fact.<primary date> -> __Calendar.Date` (active) and any secondary date
  (e.g. ship date) as `"active": False`. **Both endpoint columns must exist and
  share the same declared type** — fact FK `int64` to dim key `int64`, date
  `datetime` to `__Calendar.Date` (`dateTime`).

### 3. Build
```python
import sys; sys.path.insert(0, "src")
from pbip_model_forge.build_model import build_pbip
spec = { ... }                       # the dict you designed
build_pbip(spec, "out/<Domain>")     # writes <name>.pbip + .SemanticModel + blank .Report
```
See `scripts/build_template.py` for a complete, working spec to copy from, and
`docs/entered-data-encoding.md` for how the data is encoded.

### 4. Validate (the gate)
```
tmdl-preflight check out/<Domain>
```
Must be **0 errors**. If not, read each violation (they name the file, line, and
rule id M0xx), fix the spec, rebuild, re-check. Common fixes:
- **M006** (table not in model.tmdl): only happens if you bypass the builder —
  don't; rebuild through `build_pbip`.
- **M005** (bad dataType): a column `type` you used isn't supported — use one of
  int64/string/double/decimal/datetime/boolean.
- Relationship errors: an endpoint column name is misspelled or the two
  endpoints have different declared types.

### 5. Present the spec (the deliverable)
Give the user:
- A **diagram-style summary** of the model: each table with its columns and
  types, the measures, and the relationships drawn as `Fact.fk -> Dim.key`
  (a Mermaid `erDiagram` reads well). This is what they hand to data engineers.
- The **path to the PBIP** and a one-line "open `<name>.pbip` in Power BI
  Desktop" note.
- The **tmdl-preflight result** (0 errors) as proof it is structurally openable.

Do NOT fabricate an "it opens in Power BI" claim beyond what tmdl-preflight
verifies — a real Desktop open-test is a human step.

## Iterating / expanding (staying valid)
When the user asks to expand ("add a promotions dimension", "add a margin
measure", "make it monthly"), edit the spec dict, add the new
tables/columns/measures/relationships, **rebuild through `build_pbip`, and
re-run `tmdl-preflight check`**. Never edit the generated TMDL by hand — always
regenerate from the spec so the invariants hold. Keep the spec as the source of
truth across turns. The companion skill `validate-and-expand` documents this
keep-it-valid loop in more detail.

## What good output looks like
- A star schema with 1 fact + 2-4 dims + calendar + measures table.
- Sample data that looks like it came from the real domain.
- `tmdl-preflight check` → 0 errors.
- A clear diagram summary + the PBIP path.
