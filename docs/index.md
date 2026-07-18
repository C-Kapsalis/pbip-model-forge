# pbip-model-forge documentation

**Prototype a Power BI data model in chat, then hand the diagram to your data
engineers as a spec.** You say *"create a sample data model for a hospital"*;
Claude invents plausible tables, columns and sample data, and this repo turns
that into a **real, openable PBIP** — a Power BI semantic model with the sample
data *physically loaded*, plus a blank report — proven structurally openable by
`tmdl-preflight`. You then keep expanding it while it stays valid. The end
product is a **data-model spec**: a star-schema diagram plus the PBIP files an
engineer can open and build from.

The three moving parts:

- **Claude** (the [`create-sample-model`](../.claude/skills/create-sample-model/SKILL.md)
  skill) invents the *content* — tables, columns, believable rows, measures.
- **`build_pbip`** (the Python builder) guarantees the *structure* is openable —
  it bakes in every item of the will-it-open playbook.
- **`tmdl-preflight`** is the *gate* that proves it: **0 errors = structurally
  openable.**

The documentation follows the [Diátaxis](https://diataxis.fr/) framework:
tutorials teach, how-to guides solve, reference informs, explanation deepens.

## Before anything: install tmdl-preflight (required)

`tmdl-preflight` is the validation tool the whole workflow gates on. It is
**not on PyPI** and is **not bundled here** — it is your own local package.
Install it from its folder:

```powershell
pip install -e C:\Users\<you>\Desktop\tmdl-preflight
```

Confirm it is on PATH:

```powershell
tmdl-preflight --version
# tmdl-preflight 0.1.0
```

A model is only considered "openable" once `tmdl-preflight check <project>`
reports **0 errors**. Without it, do not trust that a generated model will open.
Full walkthrough: [Install & verify tmdl-preflight](how-to/install-and-verify-tmdl-preflight.md).

## Tutorials

- [Getting started](tutorials/getting-started.md) — install the validator, build
  the seed template, check it to 0 errors, then run your first
  "create a sample data model for &lt;domain&gt;" pass ending in a diagram-style spec.

## How-to guides

- [Build a model from a domain prompt](how-to/build-a-model-from-a-prompt.md)
- [Expand a model and keep it valid](how-to/expand-a-model-and-keep-it-valid.md)
- [Add a measure, a dimension, or a relationship](how-to/add-a-measure-dimension-relationship.md)
- [Hand the spec to a data engineer](how-to/hand-the-spec-to-a-data-engineer.md)
- [Install & verify tmdl-preflight](how-to/install-and-verify-tmdl-preflight.md)

## Reference

- [The `build_pbip` spec schema](reference/spec-schema.md) — every key, its type,
  and what the builder does with it.
- [CLI reference](reference/cli.md) — `pbip-forge-template`, `build_pbip()`, and
  the `tmdl-preflight check` gate.
- [Artifact checklist](reference/artifact-checklist.md) — every required file and
  every will-it-open check, mapped to tmdl-preflight rules.

## Explanation

- [The compressed "entered data" encoding](explanation/entered-data-encoding.md) —
  why compressed `Table.FromRows(Json.Document(Binary.Decompress(...)))` and not
  inline `#table`.
- [The "will it open" playbook](explanation/will-it-open.md) — the ~9 structural
  details Power BI Desktop demands, and why each rule exists.
- [The spec is the source of truth](explanation/spec-as-source-of-truth.md) —
  regenerate, never hand-edit the generated TMDL.
- [A spec for data engineers](explanation/spec-for-data-engineers.md) — why the
  report is blank and the model is the deliverable.

## Requirements recap

- **Python 3.9+** — the builder uses only the standard library (`json`, `zlib`,
  `base64`, `uuid`); no pip installs are needed to build a model.
- **`tmdl-preflight` installed separately** (see above) — a hard requirement; it
  is the only thing that proves a generated model is structurally openable.
