"""pbip-model-forge: build openable PBIP semantic models from plain-dict specs.

Public API:
    - enter_data.encode_rows / entered_data_source  (compressed entered-data M)
    - build_model.build_pbip                         (assemble a full PBIP)
    - blank_report.write_blank_report                (the blank "spec" report)
    - check.check_spec / Violation                   (pbip-forge check rules)
    - handoff.write_handoff / build_manifest         (manifest.json + SPEC.md)
"""

# Defined before the submodule imports: cli/handoff read it at import time.
__version__ = "1.1.0"

from .enter_data import (
    DUMMY_PARTITION_SOURCE,
    TYPE_MAP,
    decode_base64,
    encode_rows,
    entered_data_source,
    resolve_type,
)

from .build_model import build_pbip
from .blank_report import write_blank_report
from .check import RULES, SpecCheckError, Violation, check_spec
from .handoff import build_manifest, write_handoff

__all__ = [
    "encode_rows",
    "entered_data_source",
    "decode_base64",
    "resolve_type",
    "TYPE_MAP",
    "DUMMY_PARTITION_SOURCE",
    "build_pbip",
    "write_blank_report",
    "check_spec",
    "Violation",
    "SpecCheckError",
    "RULES",
    "build_manifest",
    "write_handoff",
]
