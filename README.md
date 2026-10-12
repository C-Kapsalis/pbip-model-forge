# pbip-model-forge

**Prototype a Power BI data model in chat, then hand the diagram to your data
engineers as a spec.**

You say *"create a sample data model for a hospital"* (or subscription
analytics, or logistics, or something else entirely). Claude invents
plausible tables, columns, and sample data, and this repo turns that into a
**real, openable PBIP**, a Power BI semantic model with the sample data
**physically loaded**, plus a **blank report**, validated so Power BI Desktop
will actually open it. You can then keep expanding it (relationships,
measures, dimensions) in the same conversation while it stays valid. The end
product is a **data-model spec**: a star-schema diagram plus the PBIP files a
data engineer can open and build from.

This is a **Claude Code skill-based product**. The skill
[`create-sample-model`](.claude/skills/create-sample-model/SKILL.md) drives the
workflow; [`validate-and-expand`](.claude/skills/validate-and-expand/SKILL.md)
handles the keep-it-valid iteration loop.

## Mission

In the AI age, the one asset that keeps its value is **domain expertise**:
the person who deeply understands the business, its customers, and what
actually moves the numbers. Yet the teams that hold that expertise, across
marketing, finance, operations, and sales, are routinely handed the *fewest*
data resources and the least data-engineering support. Their questions sit in
a backlog, and their insight never reaches a model.

pbip-model-forge is built to close that gap. It lets a domain expert **spec
and stand up a real data model themselves**, in plain conversation, capturing
the tables, relationships, and measures their questions actually need. From
that they can extract actionable insights, justify their priorities, and
express their value to stakeholders in concrete terms, no longer blocked on
scarce data resources to prove the point.

And because the output is a **real, openable spec**, a star-schema diagram
plus a loadable PBIP, it becomes the hand-off artifact: give it to your data
engineers to build the warehouse to exactly that shape, or hand it to a
data-engineering Claude Code skill and have the pipeline generated the same
way. The domain expert defines *what the business needs to measure*; the
plumbing follows.

## Why PBIP, and why this repo exists

Power BI Desktop's modeling view, the interface most people mean when they
say Power BI is hard to learn, has a genuinely steep learning curve: the
relationships pane, the DAX editor, the field list, all built for someone who
already thinks in tabular models. PBIP, the plain-text project format Power
BI Desktop can save to (in public preview since the Power BI June 2023
feature summary), sidesteps that interface entirely: a semantic model is
just a folder of text files, so a model can be produced without ever opening
that view. That is what this repo automates: Claude drafts the tables and
sample data, and this repo assembles a folder Power BI Desktop can open
directly.

Getting that folder structurally right without hand-authoring it is real
engineering work (a wrong partition, a missing model reference, and Power BI
Desktop refuses to open the project with an opaque error), but that is
plumbing this repo and its validator, `tmdl-preflight`, handle for you. It is
not something you, as the person describing a model in chat, ever need to
think about.

## Requirements

- **Python 3.9+** (the builder uses only the standard library; no pip installs
  are needed to build a model).
- **`tmdl-preflight` (REQUIRED, installed separately).** This is the validation
  tool the whole workflow gates on. It is **not** bundled here. Install it from
  GitHub:

  ```powershell
  pip install git+https://github.com/C-Kapsalis/tmdl-preflight.git
  ```

  Confirm it is on PATH: `tmdl-preflight --version`. A model is only considered
  "openable" once `tmdl-preflight check <project>` reports **0 errors**. Without
  it, do not trust that a generated model will open.

## Quick start

Build the seed template model, a retail-sales star schema with data already
loaded:

```powershell
python scripts/build_template.py
```

Validate it. This must report zero errors:

```powershell
tmdl-preflight check template
```

Then open `template/Model.pbip` in Power BI Desktop yourself: the one step
this cannot automate.

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
    "measures_table": {"name": "Key Measures", "measures": [
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
└─ .claude/skills/
   ├─ create-sample-model/       ← main skill: domain → validated PBIP spec
   └─ validate-and-expand/       ← expand-and-keep-valid loop
```

The full documentation set (tutorial, how-to guides) is published separately;
see [Documentation](#documentation) below.

## The deliverable is a spec, not a report

The generated `.Report` is intentionally **blank** (just `.platform` +
`definition.pbir`, no pages, no visuals). The value is the **model**: tables,
types, relationships, and measures: the thing a data engineer needs. Present it
as a star-schema diagram alongside the PBIP.

## Tests

```powershell
python tests/test_enter_data.py
```

Or, equivalently:

```powershell
python -m pytest
```

## Documentation

The tutorial and how-to guides (getting started, building a line and
clustered column chart, building a drill-down matrix) are published at
`pbip-model-forge-documentation` on Read the Docs.

## Part of a small family of Power BI tools

pbip-model-forge is the accessible entry point into a small set of related,
independently installable tools; a team adopts whichever ones it needs, not
all of them.

- [`tmdl-preflight`](https://github.com/C-Kapsalis/tmdl-preflight): the
  validator this repo requires, and, on its own, a linter and auto-fixer for
  any TMDL-format Power BI model.
- [`tmdl-drift-doctor`](https://github.com/C-Kapsalis/tmdl-drift-doctor):
  keeps many derived models in sync with one shared template.
- [`pbi-plot-styler`](https://github.com/C-Kapsalis/pbi-plot-styler): keeps
  report visuals on-brand as measures are added.
- [`BI-report-template-site`](https://github.com/C-Kapsalis/BI-report-template-site):
  not a tool but a documentation paradigm demonstrating what Diátaxis-style
  documentation looks like applied to a Power BI report.

## Contributing

Contributions are welcome: new domain-skill patterns, new spec column types,
documentation, and bug reports. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the development setup and how the
pieces fit together.

## License

MIT.
