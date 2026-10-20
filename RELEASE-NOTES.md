# Release notes

## Unreleased

Commands for projects that already exist, next to the spec-based `check`
and `build`. See [docs/model-commands.md](docs/model-commands.md).

### Added

- **`pbip-forge table dump FILE | --b64 STRING [--max-rows N]`** prints the
  rows of an encoded "Enter data" table: the column names (row 0), the
  data-row count, and the first 20 rows numbered from 1, with the number of
  rows left out. Only the file's first payload is read and the file is
  never written. A file with no payload prints `No binary data found in
  <file>` on standard error and exits 1; a payload that does not decode
  prints `Error decrypting: <the error>` and exits 1.
- **Codec additions** in `enter_data`: `decode_file(path)` (first payload;
  `ValueError("no encoded payload in <file>")` when there is none),
  `decode_b64_or_none(b64)` (None plus one error line instead of an
  exception) and `encode_rows(rows, parity_json=True)` (cells kept as they
  are, standard JSON spacing, ASCII escaping). The default encoding is
  unchanged.
- **`pbip-forge report blank --client DIR --model NAME...`** creates
  a report bound to an existing model. The command writes the complete
  PBIR definition (report.json, version.json, one page, localSettings) that
  Fabric Git sync and deployment pipelines need; `--full` is still accepted
  and has no further effect. Every file is written with two-space
  indentation, a space after the keys and no trailing newline, and
  non-ASCII characters are escaped. Existing reports are never overwritten;
  a missing model is skipped and a missing client folder fails. The console
  output is the original's: a banner, one block per model, and a footer
  that says whether every report was created. `--theme`/`--theme-file` set
  and copy the base theme (default name `CY25SU12`, the December 2025
  built-in theme). An error of any kind while writing one report is
  printed, fails that report and the other models are still processed.
- **`pbip-forge clone-report TEMPLATE [NAME] [TARGET_DIR] [SEMANTIC_MODEL]`**
  copies a report under a new name and identity. The target directory is
  the report folder itself, used exactly as given (no `.Report` is added);
  it defaults to `<cwd>/<NAME>`. The semantic model is a free string, with
  no existence check; it defaults to `<NAME>.SemanticModel`, and `--model`
  is the same argument. The copy keeps a `.backup` of every file it edits
  (`definition.pbir` and `.platform`), the value edits are JSON-aware (the
  value is escaped and any spacing is accepted), and the log lines carry a
  coloured tag. The four required files are checked in order and a missing
  one ends the run with exit 1, the copy staying. Exit 0 on success or when
  the operator declines the overwrite prompt; 1 for a missing template, a
  missing required file or a failed template check; 2 for the target being
  inside the template or a `--logical-id` that is not a UUID. `--force`
  replaces an existing target without asking; `--expect-visuals` and
  `--expect-bookmark` turn on the template's own checks.
- **Report integrity check** in the `pbip_model_forge.report_scaffold` API
  (`check_report`): the dataset reference resolves, every page in
  `pages.json` has a parseable `page.json`, `activePageName` is listed.
  With tmdl-preflight installed, `preflight_report_findings` returns its
  B004 findings for files inside the copy's own folder (a sibling such as
  `MyShop.Report` never counts against `Shop.Report`).
- **`pbip-forge f-filters --model M`** (repeatable, or `--fleet DIR`)
  creates missing `f-<Category>` gate measures, appends uncovered fact
  tables to existing ones (with a warning on stdout and stderr), and
  appends paired `temp_basic`/`temp_alt` gate lines to `f-All`: first for
  the created categories, then for every z-Map category that no live
  `temp_basic` literal gates. A fact is uncovered when a user-facing
  measure (decided by name) reaches it, no `f-` measure does, and no
  user-facing x-Selector entry measure with a mapped group reads it for
  data. Categories come from `x-Selector 1..9` entries joined to the
  `z-Map Dimension-Measure Groupings` rows. Created measures go before the
  table's result-type annotation, inline below 100 characters. The console
  shows a header, one summary line per model and its items, and a review
  note on stderr; `-v` adds every step. Append-only, idempotent,
  `--dry-run`, backup `f-Filters.tmdl.backup_gapfill_<YYYYmmdd_HHMMSS>`
  (byte copy, original modification time) unless `--no-backups`; a model
  without `f-Filters.tmdl` fails. The analysis helpers are public in
  `pbip_model_forge.f_filters`.
- **`pbip-forge i-filters --model M`** regenerates `i-Applied Filters` in
  `Helper Measures` from the `y-Selector`/`y-Plot Specific` tables: refs
  sorted by their order number, then table and column, across all tables;
  `z`, `blank` columns, `__Calendar` and hidden columns dropped. Validation
  (100% `ISFILTERED` coverage of the dimensions and of any missing column)
  gates the write, so zero dimensions or a missing column exit 1 with
  nothing written; `--skip-validation` overrides. Only the measure's
  expression is replaced (fenced, bare or inline). A dry run prints a
  preview; the per-model line is `dims=<n> gen=1 updated=<u> failed=<f>`.
  Backup `Helper Measures.tmdl.backup_<YYYYmmdd_HHMMSS>` unless
  `--no-backups`. The library keeps the older plain (with a
  `Date = <min> to <max>` block), HTML and count captions.
- Both editing commands keep each file's bytes outside the edit: line
  endings (LF or CRLF, on every OS) and a UTF-8 BOM. The backup is a byte
  copy of the file before the edit.
- Tests for all of the above (fictional fixtures). With tmdl-preflight
  installed (`uv run --group test pytest`) its integration tests run too;
  without it they skip.

### Kept fixes (BUGFIX)

Where these commands deliberately differ from the scripts they replace:

- BUGFIX: f-filters looks for the gate chains only inside `f-All`.
- BUGFIX: f-filters refuses a chain variable declared twice (no gate line
  is written, a warning says why).
- BUGFIX: f-filters writes gate lines only when both chains exist.
- BUGFIX: f-filters adds terms before a trailing `//` or `--` line comment.
- BUGFIX: f-filters escapes `"`, `]` and `'` in generated names.
- BUGFIX: f-filters and i-filters keep line endings and BOM, and the backup
  is a byte copy.
- BUGFIX: i-filters does not rewrite or back up an unchanged file.
- BUGFIX: i-filters escapes `'` (table names) and `"` (labels) in the
  caption.
- BUGFIX: an unexpected error in one model fails only that model in
  f-filters; the other models still run.
- BUGFIX: commented selector rows are ignored, and comments are stripped
  before references are detected.
- BUGFIX: the verbose f-filters line reads `Loading model index`, and the
  warnings point at tmdl-preflight A005 for the f-measure shapes.
- BUGFIX: `table dump` rejects a payload that is not a JSON array (the
  original crashed on it).
- BUGFIX: `clone-report` edits `.platform` and `definition.pbir` as JSON
  values (the original's text replacement missed compact JSON and broke on
  quotes in names).
- BUGFIX: an empty decoded payload prints `No data` instead of an empty
  listing.
- BUGFIX: a target directory inside the template is refused (exit 2,
  nothing written).
- BUGFIX: `--logical-id` is validated as a UUID.

### Notes

- Only the bare `i-Applied Filters` measure is written by the command; the
  other caption shapes are library functions.

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
