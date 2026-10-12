# Release notes

## 1.1.0 (2026-10-12): Born compliant

Generated models now follow modeling best practice by construction, and a
new gate, `pbip-forge check`, proves it on the spec before the files are
written. `tmdl-preflight` still proves the files open; `pbip-forge check`
proves the model is one a data engineer can trust.

Version note: the previous release was tagged `v1.0.0-stable` on GitHub
while the package metadata still said `0.1.0`. 1.1.0 brings the two back in
line.

### Added

- **`pbip-forge check`**, a rule engine that judges the spec dict (sample
  rows included) against 22 rules, `FM001`-`FM022`, each reported as a
  `Violation(rule, severity, object, message, fix)`. It covers keys (one per
  dimension, unique and non-null), foreign keys (every value present in the
  dimension, same type, same name), relationships (every fact on the
  calendar, every dimension reaching a fact, no bidirectional filters, one
  active path, no cycles), DAX (references resolve with comments and strings
  ignored; every fact read by a measure; ratio denominators counted from the
  fact, not a dimension), and documentation (formats, descriptions, display
  folders, name/format agreement, fact dates inside the calendar).
  Two profiles: `mockup` (documentation rules advisory) and `handoff`
  (strict). The gate is 0 P0 and 0 P1.
- **`pbip-forge` command** with `check`, `build` and `rules`, also runnable as
  `python -m pbip_model_forge`. Specs load from JSON or from a Python file
  that defines `SPEC`.
- **`build_pbip(..., check=True, profile=...)`** refuses to write a model
  that fails the gate and raises `SpecCheckError` with the report.
- **Hand-off pack.** `build_pbip(..., handoff=True)` (the default) writes
  `handoff/manifest.json` (tables with their role, columns, types, keys,
  relationships, and measures with their dependencies) and
  `handoff/SPEC.md` (data dictionary plus a Mermaid `erDiagram`). Both are
  deterministic.
- **Fuller `__Calendar`**: Quarter label (`Q1`), Month Start, Year-Month
  (sorted by Month Start), Week Start (Monday), and Day of Week (sorted by a
  hidden day number), every column described and formatted. The year range is
  inferred from the fact date columns when the spec omits it.
- Spec keys: table `role`, measure `displayFolder`, `helper` and `hidden`,
  column `isAvailableInMdx`, relationship `crossFilter`.
- Tests: `tests/test_build.py` and `tests/test_check.py` (59 tests in all).

### Changed

- **Deterministic IDs.** Every lineageTag, relationship name and
  `.platform` logicalId is a UUID5 of the object's path in the model, so the
  same spec always produces a byte-identical tree. Models rebuilt with 1.1.0
  get new IDs once, then never churn again.
- **Generator defaults.** Key columns and relationship `from` columns are
  hidden; raw numeric fact columns are hidden with `isAvailableInMdx: false`;
  every measure gets a display folder (`Counts`, `Ratios` or `Base`, or
  `_Helpers` for helper measures, which are also hidden). Descriptions are
  written as `///` comments directly above their declarations.
- The calendar's date hierarchy is now Year > Quarter > Month Name > Date.
- **Skills** gate on `pbip-forge check` (0 P0/P1) before `tmdl-preflight`
  (0 errors), teach the measure naming convention (`X #`, `X %`, `Avg X`,
  `Total X`, `X per Y`), count entities from the fact's foreign key, use
  "Unknown" member rows instead of null keys, name each FK exactly like its
  PK, describe every measure, table and user-facing column, and present the
  generated `SPEC.md` instead of a hand-written diagram.
- Example measures renamed to the convention (for example `Visit Count` is
  now `Visits #`, `Insurance Reimbursement Rate` is now
  `Insurance Reimbursement %`, `Revenue` in the template is now
  `Total Revenue`).
- `tmdl-preflight` installs from GitHub:
  `pip install git+https://github.com/C-Kapsalis/tmdl-preflight.git`.
- The documentation lives in the separate `pbip-model-forge-documentation`
  repository.

### Fixed

- **Hospital example grain bug.** `Avg Billed per Patient` divided by
  `DISTINCTCOUNT(Patients[patient_id])`. Departments, physicians and
  diagnoses filter the Encounters fact, not the Patients table, so every
  department divided by all six patients: Cardiology showed $18,300 instead
  of $109,800 / 3 = $36,600. The measure now counts
  `DISTINCTCOUNT(Encounters[patient_id])`, and rule FM015 catches the pattern
  in any model.
- Hospital `InsuranceCompanies.company_id` renamed to `insurance_company_id`
  to match the foreign key on Patients.
- The README quick-start spec used the reserved table name `Measures`, which
  the builder rejects; it now uses `Key Measures`.

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
