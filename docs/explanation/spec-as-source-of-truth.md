# The spec is the source of truth

**The rule: the spec dict is the only thing you edit; the TMDL is regenerated
from it, never hand-edited.** Every model is fully described by its spec, and
`build_pbip(spec, out_dir)` is a pure function from that spec to an openable
PBIP. This is the single discipline that keeps a model valid as it grows.

## Why not just edit the generated TMDL?

Because "openable" is a property of the *whole artifact set*, not of any one
file, and the invariants that make it openable are only guaranteed when the
builder writes everything together:

- every table has a `ref table` line in `model.tmdl` (M006),
- every table has at least one partition, including the measures table's dummy
  one (M007),
- import tables carry the two required annotations, and the calculated calendar
  deliberately does not,
- data is the compressed entered-data blob, never an inline `#table` (M008),
- relationship endpoints exist and are type-matched.

A hand edit sees one file. Add a column in `Sales.tmdl` and forget to widen every
row in the entered-data blob, or add a table file and forget its `ref table`
line, and the model silently stops opening. The builder holds all the invariants
at once precisely because it regenerates the whole set from one description. See
[the will-it-open playbook](will-it-open.md).

The base64 entered-data blob makes this vivid: it is not human-editable at all.
There is no "just tweak one value" — you change a row in the spec and re-encode.
See [the encoding guide](entered-data-encoding.md).

## The loop

1. Keep the spec dict in the conversation (or reconstruct it from the generated
   files if it was lost).
2. Apply the change **to the spec** — add a table, a measure, a relationship,
   widen the rows.
3. `build_pbip(spec, out_dir)` — overwrites in place.
4. `tmdl-preflight check <out_dir>` — require 0 errors; on any violation, fix the
   *spec* and rebuild.

This is the [`validate-and-expand`](../../.claude/skills/validate-and-expand/SKILL.md)
loop. Because step 3 always rewrites from scratch, there is no drift between "what
the spec says" and "what the files contain" — they are recomputed to agree on
every pass.

## Why `tmdl-preflight fix` is not the answer here

The validator can auto-repair some issues (M003/M004/M006) directly in the files.
That is useful for models you *don't* have a generator for. But a fix applied to
the generated TMDL is erased by the next `build_pbip`. For a pbip-model-forge
model, a violation is a signal that the **spec** is wrong (a bad type, a
misspelled endpoint, a mismatched row width). Fix the cause, not the symptom, and
the fix persists.

## Consequences worth internalizing

- **The spec is portable; the TMDL is disposable.** You can throw away `out/` and
  rebuild byte-for-byte from the spec.
- **Idempotence is free.** Rebuilding an unchanged spec yields the same model
  (modulo freshly-minted lineage-tag UUIDs, which are per-build by design).
- **Review happens on the spec.** A diff of the spec dict is legible; a diff of
  regenerated TMDL (with new UUIDs) is not the thing to review.
