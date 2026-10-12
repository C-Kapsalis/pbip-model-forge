"""``python -m pbip_model_forge check|build|rules`` (same as ``pbip-forge``)."""

from .cli import forge_main

raise SystemExit(forge_main())
