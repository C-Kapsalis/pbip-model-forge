# The compressed "entered data" encoding

This is how pbip-model-forge loads real sample data into a semantic model
**without any external data source** — the piece that makes the generated model
a populated model rather than an empty diagram. Getting it byte-exact is what
keeps Power BI Desktop happy.

## Why not just write the data inline?

The obvious approach — an inline `#table(type table [...], {...})` — is an
**entity-typed query source**. The moment the model also contains any calculated
table (and ours always has the calculated `__Calendar`), Power BI classifies the
model as *composite* and refuses to open it:

> A composite model cannot be used with entity based query sources.

(That is tmdl-preflight rule **M008**.) So manual data must be stored the way
Power BI Desktop itself stores manually-entered data: as a compressed,
base64-encoded blob inside `Table.FromRows(Json.Document(Binary.Decompress(...)))`.

## The format

Power BI writes entered data as:

1. The rows as a **JSON array-of-arrays** where **every cell is a string**
   (dates as ISO `YYYY-MM-DD`, booleans as `TRUE`/`FALSE`, nulls as JSON
   `null`), serialized compactly: `json.dumps(rows, separators=(",",":"))`.
2. Compressed with **raw DEFLATE** — zlib with a negative window bits so there
   is no zlib header/trailer: `zlib.compressobj(9, zlib.DEFLATED, -15)`.
3. Base64-encoded.

That base64 string goes into the M partition. A `Table.TransformColumnTypes`
step then converts the all-text columns to their real types.

### The M it produces

```m
let
    Source = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText(
        "<BASE64>", BinaryEncoding.Base64), Compression.Deflate)),
        let _t = ((type nullable text) meta [Serialized.Text = true]) in
        type table [#"col_a" = _t, #"col_b" = _t]),
    #"Changed Type" = Table.TransformColumnTypes(Source,
        {{"col_a", Int64.Type}, {"col_b", type text}})
in
    #"Changed Type"
```

The partition declares every column as `nullable text`, then
`TransformColumnTypes` casts. Valid cast targets (mapped from the friendly spec
`type` keyword by `enter_data.TYPE_MAP`):

| spec type | TMDL `dataType` | TransformColumnTypes target |
|---|---|---|
| `int64` / `int` | `int64` | `Int64.Type` |
| `string` / `text` | `string` | `type text` |
| `double` / `number` | `double` | `type number` |
| `decimal` | `decimal` | `type number` |
| `datetime` / `date` | `dateTime` | `type datetime` |
| `boolean` / `bool` | `boolean` | `type logical` |

## Worked example (reproduce it yourself)

```python
import sys; sys.path.insert(0, "src")
from pbip_model_forge.enter_data import encode_rows, decode_base64

rows = [
    ["1", "Downtown", "North"],
    ["2", "Harbor",   "South"],
    ["3", "Uptown",   "North"],
]
b64 = encode_rows(rows)
print(b64)
# i45WMlTSUXLJL88rAWIg0y+/qCRDKVYnWskIyPNILErKLwIygvNLocLGQF5oAarqWAA=
print(decode_base64(b64) == rows)   # True
```

That exact base64 string is what Power BI Desktop wrote for the same three rows
in the proven-openable `bike-shop-clean` example — the encoder is **byte-for-
byte identical** to Power BI's own output. `tests/test_enter_data.py` locks this
down with three golden strings straight out of a model that opens.

### The empty / dummy partition

A measures-only table has no data but still needs a partition (rule **M007**).
The canonical dummy is `[[" "]]` — one row, one column holding a single space —
whose encoding is the constant `i45WUlCKjQUA`. The M declares a throwaway column
`z` and immediately removes it:

```m
let
    Source = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText(
        "i45WUlCKjQUA", BinaryEncoding.Base64), Compression.Deflate)),
        let _t = ((type nullable text) meta [Serialized.Text = true]) in
        type table [z = _t]),
    #"Removed Columns" = Table.RemoveColumns(Source,{"z"})
in
    #"Removed Columns"
```

This is `enter_data.DUMMY_PARTITION_SOURCE`.

## Value coercion rules (`enter_data.stringify`)

| Python value | Encoded as |
|---|---|
| `None` | JSON `null` (column is `nullable text`) |
| `True` / `False` | `"TRUE"` / `"FALSE"` (parses as `type logical`) |
| `datetime.date` | `"YYYY-MM-DD"` |
| `datetime.datetime` | `"YYYY-MM-DDTHH:MM:SS"` |
| `float` | `repr(value)` (round-trippable) |
| anything else | `str(value)` |

## Gotchas

- **Raw DEFLATE, not zlib.** `zlib.compress(data)` (window bits +15) prepends a
  2-byte header and appends a checksum — Power BI's `Compression.Deflate`
  expects the raw stream. Always use window bits `-15`.
- **Every cell must be a string before JSON.** Numbers, dates, and booleans are
  stringified first; the real types are applied only by `TransformColumnTypes`.
- **Row width must equal the column count.** When you add a column to a table,
  add a value to *every* row.
- Don't hand-edit the base64 — regenerate from the spec via `build_pbip`.
