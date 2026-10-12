---
name: create-sample-model
description: >-
  Create a sample Power BI data model (PBIP semantic model + blank report) for a
  business domain. Use when the user says things like "create a sample data model
  for <domain>", "prototype a semantic model for <X>", "mock up a star schema for
  <X>", or "generate a PBIP with sample data". Invents realistic tables/columns/
  rows, emits an openable PBIP with the data physically loaded, gates it with
  pbip-forge check and tmdl-preflight, and can iteratively expand it
  (relationships, measures, dimensions) while staying valid. The end product is
  a data-model spec a user can hand to data engineers.
---

# create-sample-model

Turn a one-line request ("create a sample data model for a hospital", "…for
subscription analytics", "…for a logistics company") into a **real, openable
PBIP**: a Power BI semantic model with plausible sample data physically
loaded, plus a blank report. Then validate and iterate on it. The deliverable
is a **spec**: the generated `handoff/SPEC.md` (data dictionary and diagram)
plus the PBIP files a data engineer can open in Power BI Desktop and use as a
blueprint.

## Requirements (check once, up front)

1. **This repo's builder**, `pbip_model_forge` under `src/`. No pip deps.
   `pip install -e .` adds the `pbip-forge` command; without installing, use
   `PYTHONPATH=src python -m pbip_model_forge` in its place.
2. **`tmdl-preflight`**, the validation tool, installed separately
   (`pip install git+https://github.com/C-Kapsalis/tmdl-preflight.git`). Its
   console command must be on PATH. If it is missing, tell the user to install
   it; do not claim a model opens without it passing.

Verify with: `pbip-forge --version` and `tmdl-preflight --version`.

## The golden rule

**Never hand-write TMDL partition M or entered-data base64.** Always go through
`pbip_model_forge.build_model.build_pbip(spec, out_dir)`. The builder bakes in
every item of the will-it-open playbook (full artifact set, `ref table` for
every table, a partition on every table including the dummy measures partition,
compressed entered-data instead of inline `#table`, the required annotations, a
self-contained calculated calendar, typed relationships, deterministic IDs).
Your job is to invent a good *spec*; the two gates prove it.

## The two gates

A model is done only when both pass, in this order:

1. `pbip-forge check <spec file> --profile handoff` reports **0 P0 and 0 P1**.
   This judges the spec itself: keys, foreign keys, relationships, DAX
   references, measure grain, formats and descriptions (rules FM001-FM022;
   `pbip-forge rules` lists them with their fixes).
2. `tmdl-preflight check out/<Domain>` reports **0 errors**. This proves the
   generated files are structurally openable.

## Workflow

### 1. Design a star schema
From the user's domain, invent:
- **1 fact table** (hidden) that sets the grain (one row per order / visit /
  shipment / event). Include foreign-key columns (`int64`), 1-2 date columns
  (`datetime`), and 1-2 additive value columns (`double`/`int64`,
  `summarizeBy: sum`).
- **2-4 dimension tables**, each with exactly one `int64` key column
  (`key: True`) and a few descriptive `string`/`double` attributes.
- **Name every foreign key exactly like the key it points to**
  (`Visits.patient_id -> Patients.patient_id`, never `-> Patients.id`).
- **No null or dangling foreign keys.** If a fact row has no real match, add an
  "Unknown" member to the dimension (for example key `-1`, name `Unknown`) and
  point the row at it.
- **Realistic sample rows** (roughly 4-8 dimension rows, 8-20 fact rows): real-
  sounding names, sensible categories, dates spread across one or two years,
  amounts that reconcile with quantity × price where it makes sense.
- **A one-line `description`** on every table and every user-facing column
  (state the grain on the fact: "One row per clinic visit.").

The builder hides key columns, relationship `from` columns and raw numeric
fact columns for you; do not hand-set `hidden` unless you mean to override.

### 2. Add a calendar, a measures table, and relationships
- `calendar`: `{"name": "__Calendar"}`. The builder infers the year range from
  the fact dates (or pass `start_year`/`end_year`) and generates Year, Quarter,
  Month, Month Start, Year-Month, Week Start and Day of Week columns plus a date
  hierarchy.
- `measures_table`: a measures-home table with 3-8 DAX measures, each with a
  `format` and a one-line `description`. **Never name it `Measures`**; that
  name is reserved in Power BI and Desktop refuses to open the model. Use
  `Key Measures` or a domain name like `Clinic Measures`.
- `relationships`: one per foreign key from the fact into each dimension, plus
  `Fact.<primary date> -> __Calendar.Date` (active) and any secondary date as
  `"active": False`. Endpoints must share the same declared type.

**Measure naming convention** (the check enforces the format half):

| Pattern | Use for | Example | Format |
|---|---|---|---|
| `X #` | counts | `Visits #`, `Patients #` | `#,0` |
| `X %` | shares and rates | `No-Show %` | `0.0%` |
| `Avg X` | averages | `Avg Length of Stay` | `#,0.0` or currency |
| `Total X` | additive sums | `Total Revenue` | `$ #,0.00` or `#,0` |
| `X per Y` | ratios of two measures | `Avg Billed per Patient` | as the numerator |

**Count entities from the fact's foreign key, never from the dimension.**
`Patients # = DISTINCTCOUNT(Visits[patient_id])`, not
`DISTINCTCOUNT(Patients[patient_id])`. The other dimensions filter the fact,
not the Patients table, so a dimension-side count ignores them and every
"per patient" ratio comes out wrong when sliced (rule FM015 catches this).
Build ratios with `DIVIDE([Numerator], [Denominator])`. Mark internal building
blocks `"helper": True` (hidden, `_Helpers` folder).

### 3. Write the spec, gate it, build it
Save the spec dict as a module-level `SPEC` in a Python file (copy the shape of
`scripts/build_hospital.py`, which is a complete worked example), then:

```
pbip-forge check out/<domain>_spec.py --profile handoff   # 0 P0, 0 P1
pbip-forge build out/<domain>_spec.py out/<Domain> --check --profile handoff
tmdl-preflight check out/<Domain>                         # 0 errors
```

Fix every P0/P1 in the spec and re-run; each violation names the object and the
fix. Common ones:
- **FM005** orphan or null FK: add the "Unknown" member described above.
- **FM007** FK/PK names differ: rename one side.
- **FM013** unresolved DAX reference: a typo in a table, column or measure name.
- **FM015** ratio grain: count from the fact's FK.
- **FM017** description missing, under 10 characters, or a placeholder.
- tmdl-preflight **M005** bad dataType: use int64/string/double/decimal/
  datetime/boolean. **M006/M007** only happen if you bypass the builder; don't.

### 4. Present the spec (the deliverable)
Give the user:
- The generated **`out/<Domain>/handoff/SPEC.md`**: show its Mermaid
  `erDiagram` and summarize its data dictionary. Do not hand-write a separate
  diagram; the generated one always matches the model.
- The **path to the PBIP** and a one-line "open `<name>.pbip` in Power BI
  Desktop" note. `handoff/manifest.json` is the machine-readable version for a
  data-engineering tool.
- **Both gate results**: `pbip-forge check` (0 P0, 0 P1, any P2 advisories
  listed) and `tmdl-preflight` (0 errors).

Do NOT fabricate an "it opens in Power BI" claim beyond what tmdl-preflight
verifies; a real Desktop open-test is a human step.

## Iterating / expanding (staying valid)
When the user asks to expand ("add a promotions dimension", "add a margin
measure"), edit the spec, rebuild through `build_pbip`, and re-run both gates.
Never edit the generated TMDL by hand; always regenerate from the spec so the
invariants hold. Keep the spec file as the source of truth across turns. The
companion skill `validate-and-expand` documents this loop in more detail.

## What good output looks like
- A star schema with 1 fact + 2-4 dims + calendar + measures table.
- Sample data that looks like it came from the real domain, with no orphan keys.
- Measures named by the convention, counted from the fact, all described.
- `pbip-forge check --profile handoff` → 0 P0/P1; `tmdl-preflight check` → 0 errors.
- The generated SPEC.md + the PBIP path.
