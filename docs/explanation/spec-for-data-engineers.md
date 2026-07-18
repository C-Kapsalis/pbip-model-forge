# A spec for data engineers

pbip-model-forge produces a **data-model spec**, not a report. Understanding that
framing explains the two design choices that surprise people most: the report is
blank on purpose, and the sample data is loaded on purpose.

## The problem it addresses

Data-model design usually happens in slow loops. A business stakeholder describes
what they want, an analyst mocks something up, a data engineer builds the real
thing against the warehouse, and everyone discovers the misunderstandings only at
the end — the wrong grain, a missing dimension, a metric defined three
incompatible ways.

pbip-model-forge collapses the front of that loop into a chat. You describe a
domain; Claude invents a plausible star schema with realistic sample data; the
builder emits a real, openable PBIP. Because the data is *physically loaded*, the
model isn't a drawing — relationships resolve, measures compute, the diagram view
is populated. The result is a concrete artifact the stakeholder can react to and
the engineer can build against, produced in minutes instead of a sprint.

## Why the report is blank

The generated `.Report` is exactly two files — `.platform` and `definition.pbir`
— and nothing else: no pages, no visuals, no `StaticResources`. Power BI Desktop
opens it as an empty canvas bound to the semantic model.

That is deliberate. The **value is the model**: the tables, keys, types,
relationships and measures — the thing an engineer needs to build the production
model against the real warehouse. A mocked-up dashboard would only invite
bikeshedding about chart colors and distract from the contract that actually
matters. Present the model as a **star-schema diagram** (a Mermaid `erDiagram`
reads well) alongside the PBIP.

## Why the sample data is loaded (and why it's illustrative)

Loading real rows is what makes intent unambiguous. A column typed `int64` with
values `1, 2, 3` and a foreign key that resolves to a `Products` row says more
than any prose. It also lets the engineer open the PBIP and *see* the model work
before writing a line of SQL.

But the data is a **prototype**, not a source. When engineers build the
production model they replace the entered-data partitions with real warehouse
sources. What they preserve is the structure: the grain of the fact, the
dimensions and their keys, the declared types, the relationships, and the DAX
measures. That structure is the spec; the sample rows are the worked example that
makes it legible.

## The division of labor

- **Claude** invents the *content* — believable tables, columns, rows, measures.
- **`build_pbip`** guarantees the *structure* is openable — it bakes in every
  will-it-open invariant so a hand-authoring mistake can't sneak in.
- **`tmdl-preflight`** is the *gate* that proves it — 0 errors = structurally
  openable.

What still needs a human: opening the `.pbip` in Power BI Desktop for a live
render, publishing to a workspace, and swapping the sample data for production
sources. Say so plainly when you hand it over — see
[Hand the spec to a data engineer](../how-to/hand-the-spec-to-a-data-engineer.md).
