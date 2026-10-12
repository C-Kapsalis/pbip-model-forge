# Contributing to pbip-model-forge

**pbip-model-forge** generates openable Power BI PBIP semantic models, with
sample data physically loaded, from plain-dict specs, so you can prototype a
data model in chat and hand the diagram to data engineers as a spec. It ships as
a Claude Code skill plus a small standard-library Python builder.

Contributions welcome. This guide is accurate to the repo as it stands.

## Dev setup

```powershell
# 1. Clone
git clone <your-fork-url> pbip-model-forge
cd pbip-model-forge

# 2. Create a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell (Windows)
# source .venv/bin/activate         # bash/zsh

# 3. Install the package (editable) + dev extras
pip install -e ".[dev]"

# 4. Install the REQUIRED external validator (see below) and confirm it's on PATH
tmdl-preflight --version

# 5. Build the template and run both gates
python scripts/build_template.py
pbip-forge check scripts/build_template.py --profile handoff   # 0 P0, 0 P1
tmdl-preflight check template        # must report 0 errors

# 6. Run the tests
python -m pytest
```

The builder and checker have **no pip dependencies**: they use only the
standard library. The `dev` extra installs `pytest`.

## Required external dependency: tmdl-preflight

Validation is not optional and is not vendored. **`tmdl-preflight`** is a
separate tool that determines whether a generated model is structurally
openable. Install it from GitHub:

```powershell
pip install git+https://github.com/C-Kapsalis/tmdl-preflight.git
```

Every change that touches model generation must be verified with
`tmdl-preflight check <project>` reporting **0 errors**. Never claim a model
opens without that gate passing.

## Project layout

```
src/pbip_model_forge/
  enter_data.py     compressed "entered data" encoder (byte-exact to Power BI)
                    + M source builders + TYPE_MAP
  build_model.py    build_pbip(spec, out_dir): renders the full PBIP artifact set
                    with deterministic (uuid5) IDs
  model_info.py     table roles, calendar columns, generator defaults; shared
                    by the builder, the checker and the hand-off pack
  check.py          pbip-forge check: the FM rule catalog and the checker
  handoff.py        handoff/manifest.json + handoff/SPEC.md
  blank_report.py   the blank "spec, no visuals" report (.platform + definition.pbir)
  cli.py            pbip-forge (check, build, rules) and pbip-forge-template
scripts/                    worked-example specs: template, hospital, vet clinic, physio
template/                   the seed PBIP (generated; passes both gates)
tests/test_enter_data.py    golden-value regression tests for the encoder
tests/test_build.py         determinism, generator defaults, calendar, hand-off pack
tests/test_check.py         one good spec, then one mutation per FM rule
tests/specs.py              the tiny spec dicts the tests share
.claude/skills/
  create-sample-model/      main skill: domain prompt -> validated PBIP spec
  validate-and-expand/      the expand-and-keep-valid loop
```

The full documentation (vision, the artifact checklist / will-it-open
playbook, the entered-data encoding guide) lives in the separate
`pbip-model-forge-documentation` repository, published on Read the Docs.

## How the pieces fit

1. A user prompt ("create a sample data model for X") triggers the
   **`create-sample-model`** skill, which invents a **spec dict** (tables,
   columns, sample rows, measures, relationships).
2. **`pbip-forge check`** judges the spec against the modeling rules: 0 P0
   and 0 P1 means the model is correct enough to hand off.
3. **`build_model.build_pbip(spec, out_dir)`** renders every TMDL/JSON file the
   artifact checklist (in `pbip-model-forge-documentation`) requires. It calls
   **`enter_data`** to encode row data as the compressed entered-data blob (so
   data loads with no external source and without tripping the composite-model
   error), **`blank_report`** to emit the blank report, and **`handoff`** to
   write the manifest and SPEC.md.
4. **`tmdl-preflight check`** is the final gate: 0 errors ⇒ structurally
   openable.
5. The **`validate-and-expand`** skill grows an existing model by editing the
   spec and re-running the gate, never by hand-editing generated TMDL.

The spec dict is always the source of truth; TMDL is regenerated, never
hand-edited.

## Extending

### Add a column type
Edit `TYPE_MAP` in `src/pbip_model_forge/enter_data.py`: map the keyword to a
`dataType` (must be in tmdl-preflight's `VALID_DATA_TYPES`) and a
`TransformColumnTypes` target. Add a coercion branch to `stringify` if the
Python value needs special formatting. Add a golden/round-trip case to
`tests/test_enter_data.py`.

### Add a new generator (table kind, model feature)
Add a `render_*` function in `build_model.py` and wire it into `build_pbip`.
Keep two invariants: every table gets a `ref table` line (M006) and at least one
partition (M007); import tables get the `PBI_NavigationStepName` /
`PBI_ResultType` annotations, calculated tables do not. Rebuild the template and
run `tmdl-preflight check template`.

### Add a check rule
Add a `Rule(...)` to `_RULES` in `src/pbip_model_forge/check.py` with the next
free `FM` id, a severity per profile (`mockup`, `handoff`), a rationale and a
fix, then a `_rule_*` function that calls `ctx.add(...)` and an entry in
`_CHECKS`. Add a test to `tests/test_check.py` that mutates `good_spec()` to
trip it, confirm the four example specs still pass
`pbip-forge check --profile handoff`, and document the rule on the rule
catalog page in `pbip-model-forge-documentation`.

### Add or change a skill
Skills live in `.claude/skills/<name>/SKILL.md` with YAML frontmatter (`name`,
`description`). Keep the golden rule visible: never hand-author TMDL/base64;
always go through `build_pbip`, and always gate on `pbip-forge check`, then
`tmdl-preflight`.

## Encoder integrity

The encoder must stay **byte-for-byte identical** to Power BI Desktop's output.
`tests/test_enter_data.py` locks it to three golden base64 strings taken from a
proven-openable model. If you change encoding, those tests must still pass (or
you have broken openability). Do not "clean up" the raw-DEFLATE window-bits
(`-15`) or the compact `json.dumps` separators.

## Commit & PR conventions

- Branch off `main`; keep PRs focused.
- Use clear, imperative commit subjects (e.g. `Add currency column type`).
- Every PR that touches generation must show `pbip-forge check` at 0 P0/P1 and
  `tmdl-preflight check` at 0 errors for the template and the example specs,
  and passing `pytest`.
- Keep builds deterministic: never introduce random IDs or timestamps into
  generated files (`test_build_twice_is_byte_identical` guards this).
- Update the relevant guide in `pbip-model-forge-documentation` when behavior
  changes; if you touch the playbook invariants, update its artifact
  checklist page.

## Issues

When filing a bug, include: the spec dict (or steps) that produced it, the
full `pbip-forge check` and `tmdl-preflight check` output, your Python,
pbip-model-forge and tmdl-preflight versions, and, if a model won't open in
Power BI Desktop, the exact Desktop error text. Feature requests: describe
the domain/model shape you want to generate.

## License

MIT (see [pyproject.toml](pyproject.toml)). By contributing you agree your
contributions are licensed under the same terms.
