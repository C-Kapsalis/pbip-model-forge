# Marketing / launch material — pbip-model-forge

Truthful, specific to what the repo does. No invented metrics. Fill the
`<repo-url>` placeholder before posting.

## Positioning tagline

**Prototype a Power BI data model in chat — with real data loaded — then hand
the diagram to your data engineers as a spec.**

Alt taglines:
- *From "create a sample model for X" to an openable PBIP, validated.*
- *Design the model in conversation. Ship the diagram as the spec.*

## The mission (the "why now" angle)

In the AI age, the asset that keeps its value is **domain expertise** — the
people who understand the business and what moves its numbers. Yet those teams
(marketing, finance, ops, sales) are handed the fewest data resources and the
least engineering support, so their sharpest questions never reach a model.
pbip-model-forge puts model-building in their hands: a domain expert can spec
and stand up a real, openable data model themselves, in plain conversation —
turning expertise into actionable insight they can take to stakeholders, and
into a spec their data engineers (or a data-engineering Claude Code skill)
build the warehouse from. Lead with this framing for founder/vision posts; use
the "collapse the design loop" framing below for practitioner/how-it-works
posts.

## Problem → solution hook

**Problem.** Data-model design starts with a slow back-and-forth: a stakeholder
describes what they want, an analyst mocks something up, an engineer builds the
real thing — and the misunderstandings only surface at the end. Hand-authoring a
Power BI PBIP to prototype faster is brutal: get one of ~9 structural details
wrong and Power BI Desktop just refuses to open the project, often with a
cryptic error.

**Solution.** pbip-model-forge is a Claude Code skill that turns a one-line
prompt — "create a sample data model for a hospital" — into a **real, openable
PBIP**: a semantic model with plausible sample data *physically loaded*, plus a
blank report. It validates the model with `tmdl-preflight` so you know it opens,
and you keep expanding it in chat (dimensions, measures, relationships) while it
stays valid. The output is a **spec**: a star-schema diagram engineers can build
against, with sample data that makes intent unambiguous.

## X / Twitter launch thread (6–8 posts)

**1/**
Designing a Power BI data model usually means a slow loop between stakeholders,
analysts, and engineers — and nobody sees the misunderstandings until the end.

We built a Claude Code skill to collapse the front of that loop into a chat.

Meet pbip-model-forge. 🧵

**2/**
The pitch: say "create a sample data model for a hospital" (or subscriptions, or
logistics)…

…and get back a REAL, openable Power BI project — a semantic model with
plausible sample data physically loaded, plus a blank report. Not a drawing. A
model that opens.

**3/**
Why "physically loaded" matters: relationships resolve, measures compute, and
the diagram view is populated. So the model doubles as a **spec** you hand to
data engineers — the tables, keys, types, and metrics to build against the real
warehouse, with sample rows that pin down intent.

**4/**
Hand-authoring a PBIP is unforgiving. Miss one of ~9 structural details and
Power BI Desktop refuses to open it — "Sequence contains no elements", "A
composite model cannot be used with entity based query sources", and friends.

We hit every one of those. Then encoded the fixes into the builder.

**5/**
The trickiest part: loading data with no external source. Power BI stores
manually-entered data as a raw-DEFLATE + base64 blob that has to be
byte-identical to what Desktop writes.

Our encoder is verified byte-for-byte against a model that's proven to open.

**6/**
Every generated model is gated by `tmdl-preflight` — a validator that catches
the won't-open issues before you ever launch Desktop. 0 errors = structurally
openable. We don't claim a model opens unless the validator passes.

**7/**
And it's iterative: "add a promotions dimension", "add a margin measure", "make
it monthly" — the model regenerates from a single spec and re-validates, so it
stays openable as it grows.

**8/**
Open source, Python standard library only, ships as a Claude Code skill.
Requires the tmdl-preflight validator (installed separately).

Prototype the model in chat. Ship the diagram as the spec.

→ <repo-url>

## LinkedIn post (~250 words)

Designing a data model is one of the slowest handshakes in analytics. A
stakeholder describes what they need, an analyst sketches something, an engineer
builds the real thing — and the misunderstandings only surface at the end,
after the expensive work is done.

We wanted to collapse the front of that loop into a conversation, so we built
**pbip-model-forge**, an open-source Claude Code skill.

You describe a domain — "create a sample data model for a hospital's admissions,"
or for subscriptions, or a delivery fleet — and it generates a real, openable
Power BI project: a semantic model with plausible sample data *physically
loaded*, plus a blank report. Because the data is actually loaded, relationships
resolve and measures compute, so the model doubles as a **spec** you hand to
data engineers: the exact tables, keys, types, and metrics to build against the
real warehouse, with sample rows that make the intent unambiguous.

Hand-authoring a Power BI PBIP is famously unforgiving — miss one of about nine
structural details and Desktop simply refuses to open the project, usually with
a cryptic error. We hit every one of those failures and encoded the fixes into
the builder, including a compressed "entered data" encoder that is byte-for-byte
identical to what Power BI Desktop itself writes. Every generated model is gated
by the `tmdl-preflight` validator: zero errors means it's structurally openable.

Prototype the model in chat. Validate that it opens. Hand the diagram view to
your engineers as the spec.

It's open source — link in the comments.

#PowerBI #DataModeling #Analytics #ClaudeCode #DataEngineering

## Five one-liner hooks

1. "Create a sample data model for X" → an openable Power BI PBIP with real data
   loaded, validated. In chat.
2. Stop drawing data models in slides. Prototype one that actually opens in
   Power BI — and hand it over as the spec.
3. Hand-authoring a PBIP fails ~9 different ways. We hit all of them so your
   generated model just opens.
4. The diagram view IS the spec: tables, keys, types, measures — with sample
   rows that pin down intent for your data engineers.
5. A compressed entered-data encoder byte-identical to Power BI's own — so
   prototype models load real data with no external source.
6. In the AI age, domain expertise is the moat — this lets the expert (not
   just the data team) spec the model that proves their value to stakeholders.

## Hashtags

`#PowerBI` `#DataModeling` `#DataEngineering` `#Analytics` `#BusinessIntelligence`
`#ClaudeCode` `#TMDL` `#PBIP` `#SemanticModel` `#OpenSource`
