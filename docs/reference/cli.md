# CLI reference

pbip-model-forge exposes a small builder CLI plus a Python entry point. The
validation gate is a **separate** tool, `tmdl-preflight`, documented at the end.

## `pbip-forge-template`

The console script installed by the package (`pip install -e .`). Two forms:

```
pbip-forge-template                      # rebuild the repo's seed template/
pbip-forge-template <spec.json> <out>    # build a PBIP from a JSON spec into <out>
```

| Invocation | Behavior |
|---|---|
| no args | Rebuilds `template/` from the canonical `scripts/build_template.py` `SPEC`. Prints `Built template PBIP: <path>`. |
| `<spec.json> <out_dir>` | Loads the JSON spec, runs `build_pbip`, writes the PBIP under `<out_dir>`. Prints `Built PBIP: <path>`. |
| wrong number of args | Prints usage and exits `2`. |

The JSON spec matches the [spec schema](spec-schema.md). For date cells, pass ISO
strings like `"2024-01-15"` (JSON has no date type).

```powershell
pbip-forge-template my-spec.json out/MyModel
tmdl-preflight check out/MyModel
```

## `python scripts/build_template.py`

Rebuilds `template/` **without needing an install** — the script puts `src/` on
`sys.path` itself. Equivalent to `pbip-forge-template` with no arguments, and the
canonical worked example of a spec dict.

```powershell
python scripts/build_template.py
# Built template PBIP: ...\template\Model.pbip
```

## Python API: `build_pbip(spec, out_dir)`

The programmatic entry point, and what the skills call.

```python
import sys; sys.path.insert(0, "src")   # or `pip install -e .` and import directly
from pbip_model_forge.build_model import build_pbip

pbip_path = build_pbip(spec, "out/MyModel")   # -> pathlib.Path to the .pbip
```

- `spec`: a dict following the [spec schema](spec-schema.md).
- `out_dir`: `str` or `Path`. Created if missing; existing files are overwritten
  in place (so re-running after a spec edit is the normal expand loop).
- **Returns** the `Path` to the written `<name>.pbip`.

Related helpers you can import from `pbip_model_forge`:

| Symbol | Module | Use |
|---|---|---|
| `build_pbip` | `build_model` | assemble the whole PBIP |
| `write_blank_report` | `blank_report` | just the 2-file blank report |
| `encode_rows` / `decode_base64` | `enter_data` | the entered-data base64 codec |
| `entered_data_source` | `enter_data` | build one table's M partition source |
| `resolve_type` | `enter_data` | map a spec type keyword → `{dataType, transform}` |

## Tests

```powershell
python tests/test_enter_data.py      # or: python -m pytest
```

`tests/test_enter_data.py` locks the encoder to Power BI's golden byte layout.

## The gate: `tmdl-preflight check` (separate tool)

Not part of this package — install it separately (see
[Install & verify tmdl-preflight](../how-to/install-and-verify-tmdl-preflight.md)).

```powershell
tmdl-preflight check <project-or-model-path>   # read-only; 0 errors = openable
tmdl-preflight fix   <project-or-model-path>   # auto-repair M003/M004/M006, then re-check
tmdl-preflight --version
```

`check` reports each violation as `<file>:<line>  <RULE> <severity>: <message>`;
exit code `0` = clean, `1` = violations remain. With pbip-model-forge, always fix
the **spec** and rebuild rather than relying on `fix`, so the repair survives the
next `build_pbip`. See the [artifact checklist](artifact-checklist.md) for the
rules the gate enforces.
