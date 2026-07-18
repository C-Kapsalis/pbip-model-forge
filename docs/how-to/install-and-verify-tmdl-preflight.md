# Install & verify tmdl-preflight

**Goal:** get the validator on PATH so the gate works. This is a hard
requirement — without it, nothing can prove a generated model opens.

`tmdl-preflight` is **not on PyPI** and is **not bundled** with this repo. It is
your own local package, installed separately.

## 1. Install it (editable) from its folder

```powershell
pip install -e C:\Users\<you>\Desktop\tmdl-preflight
```

Point the path at wherever your `tmdl-preflight` checkout lives. Editable (`-e`)
means updates to that checkout take effect without reinstalling.

## 2. Confirm it is on PATH

```powershell
tmdl-preflight --version
# tmdl-preflight 0.1.0
```

If the command isn't found, your Python scripts directory may not be on PATH, or
the install landed in a different environment than your shell uses. Reinstall
into the interpreter you actually run (`python -m pip install -e <path>`).

## 3. Prove the gate on a known-good model

Build the seed template and check it:

```powershell
python scripts/build_template.py
tmdl-preflight check template
# tmdl-preflight: 0 error(s), 0 warning(s), 0 info(s)
```

Exit code 0 confirms the validator works end to end.

## Using the gate

`check` is read-only and reports violations by file, line, and rule id
(M001–M008 for the structural rules this project cares about):

```powershell
tmdl-preflight check out/<Domain>
```

**0 errors = structurally openable.** Never claim a model opens without this
passing. `tmdl-preflight fix <path>` can auto-repair lineage/ref issues
(M003/M004/M006), but with pbip-model-forge the correct response is always to fix
the spec and rebuild through `build_pbip` — see
[The spec is the source of truth](../explanation/spec-as-source-of-truth.md).

For the checks it runs, see the
[artifact checklist](../reference/artifact-checklist.md).
