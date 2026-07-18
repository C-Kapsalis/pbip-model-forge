# Release notes

## 0.1.0 — first release

**pbip-model-forge** turns a one-line domain prompt into a real, openable
Power BI project (PBIP) — a semantic model with sample data *physically
loaded* plus a blank report — so a domain expert can prototype a data model in
conversation and hand the diagram to their data engineers as a spec.

### Highlights

- **Two Claude Code skills.** `create-sample-model` builds a star schema from a
  domain prompt (*"create a sample data model for a physiotherapy clinic"*);
  `validate-and-expand` adds tables, relationships and measures and keeps the
  model valid across turns.
- **Data physically loaded, no external source.** A compressed "entered-data"
  encoder (raw-DEFLATE + base64, `Table.FromRows(Json.Document(Binary.Decompress(...)))`)
  writes rows byte-identically to how Power BI Desktop stores manually-entered
  data — so relationships resolve and measures compute offline.
- **Openable by construction.** `build_pbip(spec, out_dir)` bakes in the whole
  *will-it-open* playbook: the full artifact set, a `ref table` line per table,
  a partition on every table (including the dummy measures partition), the
  required `PBI_NavigationStepName` / `PBI_ResultType` annotations, a
  self-contained calculated `__Calendar`, type-consistent relationships, a
  reserved-table-name guard (e.g. `Measures`), and a clean-rebuild so the
  expand loop never leaves an orphaned table.
- **Validated, not asserted.** Every model is gated by `tmdl-preflight check` —
  **0 errors is the definition of "done"**. The builder never claims a model
  opens without the validator passing.
- **The deliverable is a spec.** A star-schema diagram plus a loadable PBIP with
  a blank report — the hand-off artifact for data engineers (or a
  data-engineering Claude Code skill).
- **Docs.** Full Diátaxis set (tutorial with guided matrix creation, how-to,
  reference, explanation), an artifact checklist mapped to `tmdl-preflight`
  rules, and the entered-data encoding guide.

### Requirements

- **Python 3.9+** — the builder uses only the standard library.
- **`tmdl-preflight`** installed separately (it is not on PyPI) and on PATH —
  the validation gate the whole workflow depends on. See the README for the
  install command.

### Known limitations

- `tmdl-preflight` proves *structural* openability; a live Power BI Desktop
  open + refresh is still a human confirmation step.
- Sample data is illustrative, not production data — swap in real warehouse
  sources when engineers build the model out.
- The reserved-name guard covers the confirmed `Measures`; other reserved
  names, if any, are not yet enumerated (tmdl-preflight rule M009 is the gate).
