# The `build_pbip` spec schema

A spec is a plain Python `dict` (or the JSON equivalent for the CLI). It is the
single input to `build_pbip(spec, out_dir)` and the source of truth for a model.
This page documents every key. The canonical worked example is
[`scripts/build_template.py`](../../scripts/build_template.py).

Only `name` and `tables` are required; everything else is optional.

## Top level

| Key | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | Model name. Drives the file names: `<name>.pbip`, `<name>.SemanticModel/`, `<name>.Report/`. |
| `tables` | list of [table](#table) | yes | The import (entered-data) tables — fact and dimensions. |
| `calendar` | [calendar](#calendar) | no | A self-contained calculated date table. |
| `measures_table` | [measures table](#measures-table) | no | A measures-only table with a dummy partition. |
| `relationships` | list of [relationship](#relationship) | no | Relationships between columns. Omitted ⇒ empty `relationships.tmdl`. |

```python
spec = {
    "name": "Model",
    "tables": [ ... ],
    "calendar": {"name": "__Calendar", "start_year": 2024, "end_year": 2025},
    "measures_table": { ... },
    "relationships": [ ... ],
}
```

## table

An import table, rendered by `render_data_table` with a compressed entered-data
partition and the two mandatory annotations.

| Key | Type | Required | Default | Effect on the TMDL |
|---|---|---|---|---|
| `name` | string | yes | — | `table <name>` (quoted if it contains spaces/specials). File `tables/<name>.tmdl`. |
| `columns` | list of [column](#column) | yes | — | One `column` block each. |
| `rows` | list of lists | no | `[]` | The data, one inner list per row. **Row width must equal the column count.** |
| `description` | string | no | — | Rendered as `///` doc-comment lines above the table. |
| `hidden` | bool | no | `false` | Adds `isHidden` (use for fact tables). |

## column

| Key | Type | Required | Default | Effect on the TMDL |
|---|---|---|---|---|
| `name` | string | yes | — | `column <name>`; also becomes `sourceColumn: <name>`. |
| `type` | string | yes | — | The spec type keyword → `dataType`. See [type keywords](#type-keywords). |
| `key` | bool | no | `false` | Adds `isKey` (use on dimension key columns). |
| `hidden` | bool | no | `false` | Adds `isHidden`. |
| `format` | string | no | — | `formatString: <format>` (e.g. `"$ #,0.00"`, `"General Date"`). |
| `summarizeBy` | string | no | `"none"` | `summarizeBy: <value>` (e.g. `"sum"` for additive fact measures). |
| `description` | string | no | — | `///` doc-comment lines above the column. |

Every column also gets a fresh `lineageTag` (UUID) minted by the builder — you
never supply one.

### type keywords

The spec `type` keyword maps to a TMDL `dataType` and a Power Query cast target
(`enter_data.TYPE_MAP`). Any other keyword raises `ValueError` at build time
(and a bad `dataType` would fail the gate as **M005**).

| Keyword(s) | `dataType` | Cast target |
|---|---|---|
| `int64`, `int` | `int64` | `Int64.Type` |
| `string`, `text` | `string` | `type text` |
| `double`, `number` | `double` | `type number` |
| `decimal` | `decimal` | `type number` |
| `datetime`, `date` | `dateTime` | `type datetime` |
| `boolean`, `bool` | `boolean` | `type logical` |

Cell values are stringified before encoding (dates → ISO, bools → `TRUE`/`FALSE`,
`None` → JSON `null`); the real type is applied by `Table.TransformColumnTypes`.
See [the encoding guide](../explanation/entered-data-encoding.md).

## calendar

Rendered by `render_calendar_table` as a **calculated** table with
`dataCategory: Time`, a `Date`/`Calendar Year`/`Calendar Month`/`Calendar Month
Name`/`Calendar Quarter` column set, and a `Date Hierarchy`. It is listed in
`model.tmdl`'s `ref table` lines but not in the import query order, and (being
calculated) does **not** get the import annotations.

| Key | Type | Required | Default |
|---|---|---|---|
| `name` | string | no | `"__Calendar"` |
| `start_year` | int | no | `2024` |
| `end_year` | int | no | `2025` |

The `Date` column is the relationship target for fact date columns
(`datetime` ↔ `dateTime`). Set `start_year`/`end_year` to span your fact dates.

## measures table

Rendered by `render_measures_table`: a table holding only measures, plus the
mandated **dummy partition** (`DUMMY_PARTITION_SOURCE`) so it still has one
partition (rule M007), and the two import annotations.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | The table name (e.g. `"Measures"`). |
| `measures` | list of [measure](#measure) | yes | The measures. |
| `description` | string | no | `///` doc comment. |

### measure

| Key | Type | Required | Meaning |
|---|---|---|---|
| `name` | string | yes | `measure <name>`. |
| `expression` | string | yes | The DAX. Single-line ⇒ `measure X = <expr>`; multi-line (contains `\n`) ⇒ the body is emitted on indented continuation lines. |
| `format` | string | no | `formatString: <format>`. |
| `description` | string | no | `///` doc comment. |

## relationship

Rendered by `render_relationships` as a `relationship <uuid>` block.

| Key | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `from` | `"Table.Column"` | yes | — | The many side (fact). Split on the first `.`. |
| `to` | `"Table.Column"` | yes | — | The one side (dimension). |
| `active` | bool | no | `true` | `false` emits `isActive: false` (use for secondary dates). |

**Both endpoint columns must exist and share the same declared `dataType`.**
A misspelled name or a type mismatch fails the gate.

## What the builder writes (not spec-controlled)

For reference, `build_pbip` also emits, with fixed values: `database.tmdl`
(`compatibilityLevel: 1601`); `definition.pbism` (`version "4.2"`); the
`.SemanticModel/.platform`; the blank report (`.platform` + `definition.pbir`);
and the `<name>.pbip` pointer. `model.tmdl` gets a `ref table` line for every
table and a `PBI_QueryOrder` annotation over the import tables. See the
[artifact checklist](artifact-checklist.md).
