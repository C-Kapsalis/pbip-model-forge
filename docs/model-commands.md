# Commands for existing PBIP projects

`check`, `build` and `rules` work on a spec. The commands below work on a
PBIP project that already exists: they read an encoded table, scaffold or
clone a report, or repair two helper measures of the selector pattern. All
of them run on the standard library only.

Commands that edit files (`f-filters`, `i-filters`) take `--dry-run` and
keep a timestamped backup copy of the file they change unless
`--no-backups` is given. The backup is a byte copy of the file before the
edit. The edit keeps the file's line endings (a CRLF file stays CRLF, an LF
file stays LF, on every OS) and a UTF-8 BOM; only the inserted or replaced
lines change. Work in a git repository or on a copy so every change can be
undone.

## `pbip-forge table dump`

```
pbip-forge table dump FILE.tmdl [--max-rows N]
pbip-forge table dump --b64 STRING [--max-rows N]
```

Power BI stores an "Enter data" table as `Binary.FromText("<base64>")`: a
raw DEFLATE stream of a JSON array of rows. `table dump` decodes the FIRST
such payload in the file (the file is never written) and prints the column
names (row 0), the number of data rows, the first `N` data rows (default
20) numbered from 1, and how many rows were left out. An empty array prints
one "no data" line. A payload that does not decode prints one error line and
exits 1.

Library: `enter_data.decode_file(path)`, `enter_data.decode_b64_or_none(b64)`
and `enter_data.encode_rows(rows, parity_json=False)`. The default encoding
is Power BI Desktop's own (every cell a string, compact JSON).
`parity_json=True` keeps cells as they are and uses the standard JSON
spacing (`", "`), so payloads written by tools that serialised rows that way
can be reproduced byte for byte. Decoded rows are always headerless data;
only the dump display treats row 0 as column names.

## `pbip-forge report blank`

```
pbip-forge report blank --client DIR --model NAME [NAME ...] [--name REPORT]
                        [--full] [--theme NAME] [--theme-file PATH] [--dry-run]
```

Creates `<DIR>/<REPORT>.Report` bound to `<DIR>/<NAME>.SemanticModel`.
Without `--full` it writes the minimal two-file report that `build` writes
(`.platform` and `definition.pbir`). With `--full` it writes a complete PBIR
definition, which Fabric Git integration and deployment pipelines need:
`definition/report.json`, `definition/version.json`, one page
(`Page 1`, 1280 x 720) listed in `definition/pages/pages.json`,
`.pbi/localSettings.json`, and the `bookmarks` and `StaticResources` folders.

- A model folder that does not exist is a warning and is skipped.
- An existing report folder is never overwritten ("already exists").
- `--theme` names the base theme (default `CY25SU12`). The theme JSON is
  copied from `--theme-file`, or else from another report of the same client
  that ships it; when neither exists, report.json still names the theme and
  Power BI falls back to its default.
- The `logicalId` and page id are random, so two runs differ only there.
- Exit 0 unless writing a report failed; a missing `--client` folder exits 1.
  An error while writing one report (of any kind) is printed, marks that
  report failed and the remaining models are still processed.

## `pbip-forge clone-report`

```
pbip-forge clone-report TEMPLATE.Report NAME [--out-dir DIR] [--model PATH]
                        [--force] [--logical-id UUID] [--strict]
```

Copies a finished report folder (hidden files included) to
`<DIR>/<NAME>.Report` (DIR defaults to the template's parent folder), then:

- sets `metadata.displayName` to NAME and `config.logicalId` to a new random
  UUID (or `--logical-id`) in `.platform`, keeping every other key, the key
  order and the indentation;
- with `--model`, points `definition.pbir` at that model, written as a path
  relative to the new report. A relative `--model` is read from the new
  report folder, the way `definition.pbir` stores it: `--model
  ../Roastery.SemanticModel` names a sibling of the copy, whatever the
  current directory. The path must name an existing `*.SemanticModel`
  folder, or nothing is written (exit 2).

Two copies with the same `logicalId` collide on Fabric Git sync; the clone
always gets its own. No backup files are written into the copy.

Exit codes: 0 copied; 1 the target exists (without `--force`, or as a
file rather than a folder); 2 the template is missing or has no
`.platform`, `--out-dir` lies inside the template, `--model` is not an
existing `*.SemanticModel` folder, or `--logical-id` is not a UUID. In
every error case nothing is written. After copying, the command checks the
copy (the dataset reference resolves, every page in `pages.json` has a
valid `page.json`) and, when tmdl-preflight is installed, reports its B004
findings for files inside the copy's own folder (a sibling report is never
counted). Problems are printed; `--strict` turns them into exit 1.

## `pbip-forge f-filters`

```
pbip-forge f-filters --model M.SemanticModel [--model ...] | --fleet DIR
                     [--dry-run] [--no-backups] [-v]
```

For models built on the selector pattern: one hidden `f-<Category>` measure
per analysis category in `f-Filters`, and an `f-All` measure with two
chains of gate lines (`VAR temp_basic` joined with `&&`, `VAR temp_alt`
joined with `||`).

1. **Fact tables.** A table is not a fact when its name starts with `_`,
   with one letter and `-` (`w-`, `x-`, ...) or with a character that is not
   a letter or digit, or contains the word `Measure`/`Measures`. Of the
   rest, a fact has columns, is not a calculation group or field parameter,
   has an M partition first, and holds no entered data (`Table.FromRows`,
   `#table(`). A dimension on the one side of a relationship can be a fact.
2. **Uncovered.** A fact is consumed when a user-facing measure reaches it
   (directly or through the measures it references; comments and strings
   are ignored). User-facing is decided by name: not `-`/`_`, not
   `<letter>-` other than `z-`, no word starting with `test`; the hidden
   flag does not matter. A fact reached by any `f-` measure is covered. A
   fact read for data (not only inside `ISFILTERED`, `ISEMPTY`, ...) by a
   user-facing x-Selector entry measure whose group maps to a category is
   already gated. Uncovered = consumed, not covered, not gated.
3. **Categories.** Entries come from the fenced source of the first
   calculated partition of `x-Selector 1.tmdl` .. `x-Selector 9.tmdl`
   (`("Label", NAMEOF('T'[Measure]), n, "group")`; commented lines are
   ignored). The group id is looked up in the table
   `z-Map Dimension-Measure Groupings` (category = cell 1, group = cell 3;
   date and blank groups are ignored). A fact gets every category of every
   entry that reaches it; a fact with none is skipped.
4. **Measures.** For each category in sorted order, an existing
   `f-<Category>` is extended (`+ int(not ISEMPTY('<Fact>'))` per fact, on
   the last code line, before a trailing comment; a fenced expression gets
   its closing fence at two tabs) and a warning is printed on stdout and
   stderr. Otherwise `f-<Category>` is created (inline below 100
   characters, else fenced; hidden, display folder `Visual-Level filters`,
   lineage tag `<name>-auto-generated`) before the table's
   `PBI_NavigationStepName`/`PBI_ResultType` annotation.
5. **f-All gates.** Pass 1 gates the created categories, pass 2 every
   category of the first `z-Map*` table (only when that file holds exactly
   one payload). A category is already gated when a literal of an
   uncommented `CONTAINSSTRING(all_cats, "...")` line of `temp_basic` is a
   substring of it. Otherwise its measure (`f-<cat>`, then `_` for spaces,
   then no spaces) gets one line at the end of each chain, followed by a
   line of three tabs; categories without a measure are unresolved. Only
   `f-All` is searched; a chain declared twice, or a missing `temp_alt`,
   writes no gate line. In the written DAX `"`, `]` and `'` are doubled.

Output: a header line, then per model `── <label>  (<path>)`, the model's
warnings, and a summary line
`created=<c> extended=<e> skipped=<s> f-All=<fa>  -> OK` followed by one
line per created, extended or skipped item. `-v` adds the steps (uncovered
count, created DAX, gate passes, the written file). stderr always ends with
a review note pointing at `tmdl-preflight check <model> --select A005`.

A model without `f-Filters.tmdl` or without a `definition/tables` folder
fails (exit 1); an unexpected error fails only that model (`-v` prints the
traceback). The backup is `f-Filters.tmdl.backup_gapfill_<YYYYmmdd_HHMMSS>`,
a byte copy with the original modification time. A second run on a
repaired model changes nothing. Library: `pbip_model_forge.f_filters`
(`is_fact_table`, `is_user_facing`, `uncovered_facts`, `selector_entries`,
`group_categories`, `registered_categories`, `live_gate_names`,
`category_gated`, `find_gate_measure`, `chain_text`, `fill_gaps`).

## `pbip-forge i-filters`

```
pbip-forge i-filters --model M.SemanticModel [--model ...] | --fleet DIR
                     [--dry-run] [--no-backups] [--skip-validation] [-v]
```

Regenerates the `i-Applied Filters` caption measure in `Helper Measures`
from the y- selector tables: one block per offered column, in selector order,
skipping hidden columns, the `__Calendar` date spine, `__Comparison` tables
and spacer columns. Each block shows `Column = a, b, c` for the selected
values (at most 10, blank shown as `(Blank)`), or `Column is not x` when the
column has more than 5 values and only 1 to 3 are excluded.

Before writing, the measure is validated: every dimension must have its
`ISFILTERED` test (100% coverage) and `ISFILTERED` and `CONCATENATEX` must
be present; missing working variables, `TOPN` or line breaks are warnings.
A failed validation writes nothing and exits 1; `--skip-validation` writes
anyway. A host table without the measure is a failure (exit 1). Only the
measure's expression is replaced; its properties and the rest of the file
are kept.

The library (`pbip_model_forge.i_filters`) also offers an HTML output, a
count-only output, an optional date block and an explicit dimension order
(`Options`). The date block reads `Period: 3 Feb 2025 - 28 Feb 2025` (one
date when the range is a single day).
