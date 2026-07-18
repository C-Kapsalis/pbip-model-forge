# Build a model from a domain prompt

**Goal:** turn a one-line domain description into an openable PBIP with sample
data loaded, proven by tmdl-preflight.

## 1. Ask

In a Claude Code session in this repo:

> create a sample data model for &lt;domain&gt;

Examples: *"…for a hospital"*, *"…for subscription analytics"*, *"…for a
logistics company"*. This triggers the
[`create-sample-model`](../../.claude/skills/create-sample-model/SKILL.md) skill.

## 2. Design a star schema (what the skill invents)

- **1 fact table** (hidden) at a clear grain — one row per order / visit /
  shipment. Foreign-key columns (`int64`), 1–2 date columns (`datetime`), and
  1–2 additive measure columns (`double`/`int64`, `summarizeBy: sum`).
- **2–4 dimension tables** — each with an `int64` key column (`key: True`) and a
  few `string`/`double` attributes.
- **Realistic sample rows** — roughly 4–8 dimension rows, 8–20 fact rows, with
  dates spread across the calendar range.
- A **`calendar`** (`__Calendar`, `start_year`/`end_year` covering the data).
- A **`measures_table`** with 3–6 DAX measures, each with a `format`.
- **`relationships`** — one per foreign key into each dimension, plus the primary
  fact date to `__Calendar.Date` (active) and any secondary date as
  `"active": False`.

Endpoint columns must exist and share the same declared type (fact FK `int64` ↔
dim key `int64`; date `datetime` ↔ `__Calendar.Date`). See the
[spec schema](../reference/spec-schema.md).

## 3. Build (never hand-write TMDL)

Always go through the builder:

```python
import sys; sys.path.insert(0, "src")
from pbip_model_forge.build_model import build_pbip

spec = { ... }                       # the dict designed above
build_pbip(spec, "out/<Domain>")     # writes <name>.pbip + .SemanticModel + blank .Report
```

Copy [`scripts/build_template.py`](../../scripts/build_template.py) for a
complete, working spec to start from. The builder bakes in every will-it-open
invariant; your only job is a good spec.

## 4. Gate

```powershell
tmdl-preflight check out/<Domain>
# tmdl-preflight: 0 error(s), 0 warning(s), 0 info(s)
```

Must be **0 errors**. If not, each violation names the file, line, and rule id.
Common fixes:

- **M005** (bad dataType): use one of
  `int64` / `string` / `double` / `decimal` / `datetime` / `boolean`.
- **Relationship errors**: an endpoint column name is misspelled, or the two
  endpoints have different declared types.
- **M006 / M007** (table not referenced / no partition): only happens if you
  bypass the builder — rebuild through `build_pbip`.

Fix the **spec**, rebuild, re-check.

## 5. Present the spec

Hand over three things:

- a **diagram-style summary** (a Mermaid `erDiagram` of tables, types, measures,
  and `Fact.fk -> Dim.key` relationships),
- the **path to the PBIP** plus "open `<name>.pbip` in Power BI Desktop",
- the **tmdl-preflight result** (0 errors) as proof.

Do not claim "it opens in Power BI" beyond what tmdl-preflight verifies — a live
Desktop open is a human step. See
[Hand the spec to a data engineer](hand-the-spec-to-a-data-engineer.md).
