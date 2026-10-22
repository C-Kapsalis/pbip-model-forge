"""Emit the BLANK report artifact that ``build`` writes next to the model.

The "spec, no visuals" deliverable is a complete PBIR report with one empty
page, bound to the semantic model:

    <name>.Report/.platform                       (metadata.type == "Report")
    <name>.Report/definition.pbir                 (byPath -> ../<model>.SemanticModel)
    <name>.Report/definition/report.json
    <name>.Report/definition/version.json
    <name>.Report/definition/pages/pages.json     (pagesMetadata 1.1.0)
    <name>.Report/definition/pages/<id>/page.json ("Page 1", 1280 x 720)

It is the same structure ``pbip-forge report blank`` writes (see
:mod:`report_scaffold`). Up to 1.2.0 this module wrote only ``.platform`` and
``definition.pbir``, which tmdl-preflight rejects (B005: no pages.json; B007:
no report.json).
"""

from __future__ import annotations

import uuid
from pathlib import Path


def write_blank_report(out_dir: str | Path, name: str,
                       logical_id: str | None = None,
                       model_name: str | None = None,
                       page_id: str | None = None) -> Path:
    """Write the blank report folder ``name`` under ``out_dir``.

    The report points at ``../<model_name>.SemanticModel`` (``model_name``
    defaults to ``name``). ``logical_id`` defaults to a random UUID and
    ``page_id`` to a random 20-hex-character page name; build_pbip passes
    deterministic ones so rebuilds are byte-identical."""
    from .report_scaffold import new_page_id, write_full_blank_report

    return write_full_blank_report(out_dir, name, model_name or name,
                                   logical_id=logical_id or str(uuid.uuid4()),
                                   page_id=page_id or new_page_id())
