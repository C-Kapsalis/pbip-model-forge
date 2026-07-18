# Artifact checklist — the will-it-open playbook

A hand-authored PBIP must satisfy **all** of the following or Power BI Desktop
refuses to open the project. `build_pbip` enforces every item; this page is the
manual audit for when you're debugging a model that won't open, and the
authoritative record of what each rule protects. Run
`tmdl-preflight check <project>` for the automated version — it maps to the
"gate" rules noted below. For the *why* behind each rule, see
[The "will it open" playbook](../explanation/will-it-open.md).

## Part A — every file that must exist

For a model named `<name>`, the complete artifact set is:

- [ ] `<name>.pbip`
      — schema `.../pbip/pbipProperties/1.0.0`, `version "1.0"`, an
      `artifacts` entry pointing at `<name>.Report`.
- [ ] `<name>.SemanticModel/.platform`
      — gitIntegration `platformProperties/2.0.0`, `metadata.type ==
      "SemanticModel"`, `config.version "2.0"` + a `logicalId`.
- [ ] `<name>.SemanticModel/definition.pbism`
      — semanticModel `definitionProperties/1.0.0`, `version "4.2"`.
- [ ] `<name>.SemanticModel/definition/database.tmdl`
      — `compatibilityLevel: 1601`.
- [ ] `<name>.SemanticModel/definition/model.tmdl`
      — the `model` block **plus a `ref table` line for every table** (see B2).
- [ ] `<name>.SemanticModel/definition/relationships.tmdl`
      — one `relationship` block per relationship (may be empty if none).
- [ ] `<name>.SemanticModel/definition/tables/<Table>.tmdl`
      — one file per table; **at least one** must exist.
- [ ] `<name>.Report/.platform`
      — `metadata.type == "Report"`.
- [ ] `<name>.Report/definition.pbir`
      — report `definitionProperties/2.0.0`,
      `datasetReference.byPath.path == "../<name>.SemanticModel"`.

The BLANK report is **exactly** `.platform` + `definition.pbir` and **nothing
else** — no `report.json`, no `pages/`, no `StaticResources/`. That "spec, no
visuals" report is the deliverable.

## Part B — the nine will-it-open checks

### 1. Full artifact set
Every file in Part A is present, with the exact schemas/versions listed.
*Builder:* `build_pbip` writes all of them; `write_blank_report` writes the
2-file blank report. *Gate:* **tmdl-preflight M001** (model.tmdl / tables folder
present).

### 2. `model.tmdl` lists every table with `ref table '<name>'`
A table file under `tables/` with no matching `ref table` line in `model.tmdl`
is **not attached to the model** → Power BI won't open the project.
(`ref cultureInfo` is added **only** if a `cultures/` file exists — we don't
emit one, so we don't reference one.)
*Gate:* **tmdl-preflight M006.** *Builder:* every created table name is written
as a `ref table` line, quoted when it contains spaces.

### 3. Every table has ≥1 partition — including measures-only tables
A table with no partition crashes on open ("Sequence contains no elements" in
GetLinkedQuery). A measures-only table needs a **dummy** partition. The exact
dummy source (mandated verbatim) is:
```
Source = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText(
  "i45WUlCKjQUA", BinaryEncoding.Base64), Compression.Deflate)),
  let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [z = _t]),
#"Removed Columns" = Table.RemoveColumns(Source,{"z"})
```
(`i45WUlCKjQUA` decodes to `[[" "]]`.)
*Gate:* **tmdl-preflight M007.** *Builder:* data tables get an entered-data
partition; the measures table gets `DUMMY_PARTITION_SOURCE`; the calendar gets a
`calculated` partition.

### 4. Never use inline `#table(type table [...], {...})` for data
An inline `#table(...)` source is an *entity-typed query source*; combined with
any calculated table (the Calendar!), Power BI treats the model as composite and
refuses to open it ("A composite model cannot be used with entity based query
sources").
*Gate:* **tmdl-preflight M008.** *Builder:* data is only ever emitted via the
compressed entered-data pattern — the builder cannot produce an inline `#table`.

### 5. Load real data via the compressed "entered data" pattern
```
Source = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText(
  "<BASE64>", BinaryEncoding.Base64), Compression.Deflate)),
  let _t = ((type nullable text) meta [Serialized.Text = true]) in
  type table [#"Col1" = _t, ...])),
#"Changed Type" = Table.TransformColumnTypes(Source, {{"Col1", <type>}, ...})
```
`<BASE64>` = rows as a JSON array-of-arrays where **every value is a string**
(dates ISO `YYYY-MM-DD`), `json.dumps(rows, separators=(",",":"))`, compressed
with **raw DEFLATE** `zlib.compressobj(9, zlib.DEFLATED, -15)`, then
`base64.b64encode`. TransformColumnTypes targets: `Int64.Type`, `type text`,
`type number`, `type datetime`, `type logical`.
*Builder:* `enter_data.encode_rows` / `entered_data_source`. See
[the encoding guide](../explanation/entered-data-encoding.md).

### 6. Every M/import table has the two table-level annotations
```
annotation PBI_NavigationStepName = Navigation
annotation PBI_ResultType = Table
```
Missing them → the same GetLinkedQuery "Sequence contains no elements" crash.
*Builder:* appended to every data table **and** the measures table. (Calculated
tables — the Calendar — must **not** have them; see check 7.)

### 7. Calendar = self-contained calculated table
`partition = calculated`, source
`ADDCOLUMNS(CALENDAR(DATE(y,1,1),DATE(y,12,31)), "Year", YEAR([Date]), …)`, with
columns declared using `sourceColumn: [Date]` etc. Calculated tables do **not**
get the PBI_ResultType / PBI_NavigationStepName annotations.
*Builder:* `render_calendar_table` (also sets `dataCategory: Time` and a date
hierarchy).

### 8. Relationships are type-consistent
Both endpoint columns must exist and share the same declared `dataType`. Give
the calendar `dataCategory: Time` and relate a `dateTime` date key to it.
*Builder:* `render_relationships`; you supply `"Fact.col" -> "Dim.col"` and must
keep the types matched in the spec (fact FK `int64` ↔ dim key `int64`; date
`datetime` ↔ `__Calendar.Date`).

### 9. Validate everything with tmdl-preflight
```
tmdl-preflight check <model-or-project-path>
```
**0 errors = structurally openable.** This is the gate in the skill loop. Never
claim a model opens without it passing. (`tmdl-preflight fix <path>` can
auto-repair M003/M004/M006, but the right move is to fix the spec and rebuild.)

## Rule id quick reference

| Rule | Meaning | Fix (always at the spec level) |
|---|---|---|
| M001 | model.tmdl / tables folder missing | rebuild through `build_pbip` |
| M003 | duplicate lineageTag | rebuild (the builder mints fresh UUIDs) |
| M004 | lineageTag is not a canonical UUID | rebuild |
| M005 | column dataType not engine-valid | use int64/string/double/decimal/datetime/boolean |
| M006 | table not referenced in model.tmdl | rebuild (builder writes every `ref table`) |
| M007 | a table has no partition | rebuild (builder always adds one) |
| M008 | inline `#table(...)` entity source | never hand-author data; builder uses entered-data |

Structural rules live in `tmdl-preflight`'s
`src/tmdl_preflight/rules/structural.py`.

## What still needs a human
- Opening `<name>.pbip` in **Power BI Desktop** to confirm the live open
  (tmdl-preflight proves *structure*, not a Desktop render).
- Publishing to the Power BI service / a workspace.
- Replacing sample data with real warehouse sources when engineers build the
  production model.
