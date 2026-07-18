# The "will it open" playbook

Power BI's PBIP format is unforgiving to hand-author. Miss one of about nine
structural details and Power BI Desktop simply **refuses to open the project** —
often with an opaque error like *"Sequence contains no elements"* or *"A
composite model cannot be used with entity based query sources"*. Every one of
those was hit for real while building this tool, and each is now baked into
`build_pbip` so you never hit it again.

This page explains **why** each rule exists. For the terse checklist and the file
manifest, see the [artifact checklist](../reference/artifact-checklist.md); the
automated version is `tmdl-preflight check`.

## Two forces the builder is fighting

Almost every failure traces back to one of two facts about the Power BI engine:

1. **A model is a graph, not a folder of files.** A `.tmdl` file on disk is
   inert until `model.tmdl` *references* it and it declares at least one
   *partition* the engine can load. A table that is present but unreferenced, or
   referenced but partition-less, isn't "half a model" — it makes the whole
   project unopenable.
2. **Data provenance is typed.** The engine decides whether a model is "import"
   or "composite" from how each table's data arrives. Mixing an *entity-typed
   query source* (an inline `#table`) with a *calculated* table trips the
   composite classifier, and composite + entity sources is an illegal
   combination that blocks the open.

The rules below are the concrete consequences.

## Why each rule exists

### The full artifact set must exist (M001)
The `.pbip`, the `.SemanticModel` (`.platform`, `definition.pbism`,
`database.tmdl`, `model.tmdl`, `relationships.tmdl`, `tables/*.tmdl`) and the
`.Report` (`.platform`, `definition.pbir`) are a linked set with exact schema
URLs and versions. A missing file or a wrong `datasetReference` path leaves the
report pointing at nothing. `build_pbip` writes all of them.

### Every table needs a `ref table` line (M006)
A table file with no `ref table '<name>'` in `model.tmdl` is **not attached to
the model** — from the engine's point of view it doesn't exist, and the mismatch
between the folder and the graph aborts the open. The builder emits a `ref table`
for every table it writes, quoted when the name has spaces.

### Every table needs ≥1 partition — even measures-only tables (M007)
A partition is *how* a table gets its rows. A table with none crashes on open
("Sequence contains no elements" inside `GetLinkedQuery`). A measures-only table
has no data of its own, so it gets a **dummy** partition — the constant
`i45WUlCKjQUA` (which decodes to `[[" "]]`), loaded and then column-dropped. The
calendar gets a `calculated` partition; data tables get an entered-data
partition.

### Never inline `#table(...)` for data (M008)
An inline `#table(type table [...], {...})` is an *entity-typed query source*.
Because the model always contains the calculated `__Calendar`, an inline source
flips the engine into composite mode, and *"A composite model cannot be used with
entity based query sources"* blocks the open. The fix is to store data exactly
the way Desktop stores manually-entered data — the compressed
`Table.FromRows(Json.Document(Binary.Decompress(...)))` blob. The builder
*cannot* emit an inline `#table`. See
[the encoding guide](entered-data-encoding.md).

### Import tables need two annotations
```
annotation PBI_NavigationStepName = Navigation
annotation PBI_ResultType = Table
```
Without them the engine takes the same "Sequence contains no elements"
`GetLinkedQuery` path. They go on every import table *and* the measures table —
but **not** on the calculated calendar, which would break it instead.

### The calendar is a self-contained calculated table
Rather than depend on an external source, `__Calendar` is a `calculated`
partition (`ADDCOLUMNS(CALENDAR(...), ...)`) with `dataCategory: Time` and a date
hierarchy. Self-contained means it always populates. Being calculated is also
exactly why it must skip the import annotations above.

### Relationships must be type-consistent
Both endpoint columns must exist and share the same declared `dataType`. A
fact FK `int64` relates to a dimension key `int64`; a fact date `datetime`
relates to `__Calendar.Date` (`dateTime`). A misspelled column or a type
mismatch is rejected. You supply the endpoints in the spec; the builder can't
invent a column you didn't declare.

## The gate, and its honest limits

`tmdl-preflight check <project>` runs all of this automatically. **0 errors means
structurally openable** — and that is the strongest claim you should make.
tmdl-preflight validates *structure*; it does not launch Power BI Desktop.
Opening the `.pbip` for a live render, publishing to a workspace, and swapping
sample data for real sources remain human steps.

The auto-fixer (`tmdl-preflight fix`) can repair lineage/reference issues
(M003/M004/M006), but for a pbip-model-forge model the correct response to any
violation is to fix the **spec** and regenerate — see
[The spec is the source of truth](spec-as-source-of-truth.md).
