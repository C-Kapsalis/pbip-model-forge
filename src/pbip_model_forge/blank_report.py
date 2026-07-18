"""Emit the BLANK report artifact.

The "spec, no visuals" deliverable is a report folder containing exactly two
files and nothing else:

    <name>.Report/.platform          (metadata.type == "Report")
    <name>.Report/definition.pbir    (datasetReference.byPath -> ../<name>.SemanticModel)

No report.json, no pages, no StaticResources. Power BI Desktop opens it as an
empty canvas bound to the semantic model -- exactly what a data-model spec needs.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path


def write_blank_report(out_dir: str | Path, name: str) -> Path:
    """Write the blank report folder for model ``name`` under ``out_dir``."""
    out_dir = Path(out_dir)
    report_dir = out_dir / f"{name}.Report"
    report_dir.mkdir(parents=True, exist_ok=True)

    (report_dir / ".platform").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                "metadata": {"type": "Report", "displayName": name},
                "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (report_dir / "definition.pbir").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
                "version": "4.0",
                "datasetReference": {
                    "byPath": {"path": f"../{name}.SemanticModel"}
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return report_dir
