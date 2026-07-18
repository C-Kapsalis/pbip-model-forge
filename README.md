# pbip-model-forge

**Prototype a Power BI data model in chat, then hand the diagram to your data
engineers as a spec.**

You say *"create a sample data model for a hospital"* (or subscription
analytics, or logistics, or …). Claude invents plausible tables, columns and
sample data, and this repo turns that into a **real, openable PBIP** — a Power
BI semantic model with the sample data **physically loaded**, plus a **blank
report** — validated so Power BI Desktop will actually open it. You can then
keep expanding it (relationships, measures, dimensions) in the same
conversation while it stays valid. The end product is a **data-model spec**: a
star-schema diagram plus the PBIP files a data engineer can open and build from.

This is a **Claude Code skill-based product**. The skill
[`create-sample-model`](.claude/skills/create-sample-model/SKILL.md) drives the
workflow; [`validate-and-expand`](.claude/skills/validate-and-expand/SKILL.md)
handles the keep-it-valid iteration loop.

## Mission

In the AI age, the one asset that keeps its value is **domain expertise** —
the person who deeply understands the business, its customers, and what
actually moves the numbers. Yet the teams that hold that expertise — across
marketing, finance, operations, sales — are routinely handed the *fewest*
data resources and the least data-engineering support. Their questions sit in
a backlog; their insight never reaches a model.

pbip-model-forge is built to close that gap. It lets a domain expert **spec
and stand up a real data model themselves**, in plain conversation, capturing
the tables, relationships and measures their questions actually need. From
that they can extract actionable insights, justify their priorities, and
express their value to stakeholders in concrete terms — no longer blocked on
scarce data resources to prove the point.

And because the output is a **real, openable spec** — a star-schema diagram
plus a loadable PBIP — it becomes the hand-off artifact: give it to your data
engineers to build the warehouse to exactly that shape, or hand it to a
data-engineering Claude Code skill and have the pipeline generated the same
way. The domain expert defines *what the business needs to measure*; the
plumbing follows.

## Why this is hard (and why the repo exists)

A hand-authored PBIP is fussy: get one of ~9 structural details wrong and Power
BI Desktop simply **refuses to open the project** — often with an opaque error
like *"Sequence contains no elements"* or *"A composite model cannot be used
with entity based query sources"*. Each of those was hit for real and is now
encoded into the builder so you never hit it again. The full list is the
[will-it-open playbook / artifact checklist](docs/artifact-checklist.md).

The single trickiest part — loading real data without an external source — is
the **compressed "entered data" encoding**: a raw-DEFLATE + base64 blob that
must be byte-identical to what Power BI Desktop writes. This repo's encoder is
verified byte-for-byte against a proven-openable model. See
[the encoding guide](docs/entered-data-encoding.md).

## Requirements

- **Python 3.9+** (the builder uses only the standard library — no pip installs
  needed to build a model).
- **`tmdl-preflight` (REQUIRED, installed separately).** This is the validation
  tool the whole workflow gates on. It is **not** on PyPI and is **not** bundled
  here — it is the user's own local package. Install it from its folder, e.g.:

  ```powershell
  pip install -e C:\Users\<you>\Desktop\tmdl-preflight
  ```

  Confirm it is on PATH: `tmdl-preflight --version`. A model is only considered
  "openable" once `tmdl-preflight check <project>` reports **0 errors**. Without
  it, do not trust that a generated model will open.

## Quick start

```powershell
# 1. Build the seed/template model (retail-sales star schema with data loaded)
python scripts/build_template.py

# 2. Validate it — must report 0 errors
tmdl-preflight check template

# 3. Open template/Model.pbip in Power BI Desktop (human step)
```

Build your own model from a spec dict:

```python
import sys; sys.path.insert(0, "src")
from pbip_model_forge.build_model import build_pbip

spec = {
    "name": "Model",
    "tables": [
        {"name": "Products",
         "columns": [
             {"name": "product_id", "type": "int64", "key": True},
             {"name": "product_name", "type": "string"},
             {"name": "unit_price", "type": "double", "format": "$ #,0.00"},
         ],
         "rows": [[1, "Widget", 9.99], [2, "Gadget", 19.99]]},
    ],
    "calendar": {"name": "__Calendar", "start_year": 2024, "end_year": 2025},
    "measures_table": {"name": "Measures", "measures": [
        {"name": "Product Count", "expression": "COUNTROWS(Products)", "format": "#,0"},
    ]},
    "relationships": [],
}
build_pbip(spec, "out/MyModel")   # -> out/MyModel/Model.pbip (+ .SemanticModel + blank .Report)
```

Then `tmdl-preflight check out/MyModel`.

## What's in the box

```
pbip-model-forge/
├─ README.md                     ← you are here
├─ pyproject.toml                ← package metadata (tmdl-preflight noted as required companion)
├─ .gitignore
├─ template/                     ← the seed PBIP (built by scripts/build_template.py, passes tmdl-preflight)
│  ├─ Model.pbip
│  ├─ Model.SemanticModel/…      ← 3 data tables + calculated __Calendar + Measures table + 4 relationships
│  └─ Model.Report/              ← BLANK report: .platform + definition.pbir only
├─ src/pbip_model_forge/
│  ├─ enter_data.py              ← compressed entered-data encoder (byte-exact) + M source builders
│  ├─ build_model.py             ← build_pbip(spec, out_dir): assembles the full PBIP
│  ├─ blank_report.py            ← the blank "spec, no visuals" report
│  └─ cli.py                     ← pbip-forge-template convenience CLI
├─ scripts/build_template.py     ← canonical worked example spec → template/
├─ tests/test_enter_data.py      ← locks the encoder to Power BI's golden byte layout
├─ .claude/skills/
│  ├─ create-sample-model/       ← main skill: domain → validated PBIP spec
│  └─ validate-and-expand/       ← expand-and-keep-valid loop
└─ docs/
   ├─ README.md                  ← vision & how it fits together
   ├─ artifact-checklist.md      ← EVERY file + EVERY playbook check (items 1-9)
   └─ entered-data-encoding.md   ← the compressed encoding, worked example
```

## The deliverable is a spec, not a report

The generated `.Report` is intentionally **blank** (just `.platform` +
`definition.pbir`, no pages, no visuals). The value is the **model**: tables,
types, relationships, and measures — the thing a data engineer needs. Present it
as a star-schema diagram alongside the PBIP.

## Tests

```powershell
python tests/test_enter_data.py      # or: python -m pytest
```

## License

MIT.
