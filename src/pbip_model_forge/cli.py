"""Tiny CLI: rebuild the seed template, or build a PBIP from a JSON spec file.

Usage:
    pbip-forge-template                 # rebuild template/ (same as scripts/build_template.py)
    pbip-forge-template spec.json out/  # build a PBIP from a JSON spec into out/

The JSON spec matches the dict shape documented in build_model.build_pbip.
(For rows with dates, pass ISO strings like "2024-01-15".)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .build_model import build_pbip


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        # Rebuild the repo's template using the canonical spec.
        repo = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(repo / "scripts"))
        from build_template import SPEC  # type: ignore

        pbip = build_pbip(SPEC, repo / "template")
        print(f"Built template PBIP: {pbip}")
        return 0

    if len(argv) != 2:
        print(__doc__)
        return 2

    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    pbip = build_pbip(spec, argv[1])
    print(f"Built PBIP: {pbip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
