"""Command-line entry points.

``pbip-forge`` (the main CLI)::

    pbip-forge check SPEC [--profile mockup|handoff] [--format text|json]
    pbip-forge build SPEC OUT_DIR [--check] [--profile ...] [--no-handoff]
    pbip-forge rules
    pbip-forge table dump FILE.tmdl | --b64 STRING [--max-rows N]
    pbip-forge report blank --client DIR --model NAME... [--full] [--dry-run]
    pbip-forge clone-report TEMPLATE.Report NAME [--model PATH] [--force]
    pbip-forge f-filters --model M.SemanticModel [--dry-run] [--no-backups]
    pbip-forge i-filters --model M.SemanticModel [--dry-run] [--no-backups]

SPEC is either a JSON file holding the spec dict, or a Python file that
defines a module-level ``SPEC`` dict (like ``scripts/build_hospital.py``).
For rows with dates in JSON, pass ISO strings like "2024-01-15".
``check`` exits 1 when any P0/P1 violation is found, else 0.

``pbip-forge-template`` (kept from 1.0)::

    pbip-forge-template                 # rebuild template/ (same as scripts/build_template.py)
    pbip-forge-template spec.json out/  # build a PBIP from a JSON spec into out/
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .build_model import build_pbip
from .check import PROFILES, SpecCheckError, blocking, check_spec, format_report, format_rules


def load_spec(path: str | Path) -> dict[str, Any]:
    """Load a spec dict from a ``.json`` file or a ``.py`` file defining ``SPEC``."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix.lower() == ".py":
        mod_spec = importlib.util.spec_from_file_location(f"_pbip_spec_{path.stem}", path)
        if mod_spec is None or mod_spec.loader is None:
            raise SystemExit(f"cannot load {path}")
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)
        spec = getattr(module, "SPEC", None)
        if not isinstance(spec, dict):
            raise SystemExit(f"{path} does not define a module-level SPEC dict")
        return spec
    raise SystemExit(f"{path}: expected a .json or .py spec file")


def forge_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pbip-forge",
        description="Check and build Power BI PBIP models from spec dicts.")
    parser.add_argument("--version", action="version", version=f"pbip-forge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="judge a spec against the FM rules")
    p_check.add_argument("spec", help="spec .json, or .py defining SPEC")
    p_check.add_argument("--profile", choices=PROFILES, default="mockup")
    p_check.add_argument("--format", choices=("text", "json"), default="text")

    p_build = sub.add_parser("build", help="build a PBIP from a spec")
    p_build.add_argument("spec")
    p_build.add_argument("out_dir")
    p_build.add_argument("--check", action="store_true",
                         help="refuse to build if the check finds P0/P1 violations")
    p_build.add_argument("--profile", choices=PROFILES, default="mockup")
    p_build.add_argument("--no-handoff", action="store_true",
                         help="skip handoff/manifest.json and SPEC.md")

    sub.add_parser("rules", help="list the rule catalog")

    _add_model_commands(sub)

    args = parser.parse_args(argv)
    if args.command == "rules":
        sys.stdout.write(format_rules())
        return 0
    if args.command in _MODEL_COMMANDS:
        return _MODEL_COMMANDS[args.command](args)

    spec = load_spec(args.spec)
    if args.command == "check":
        found = check_spec(spec, profile=args.profile)
        if args.format == "json":
            print(json.dumps({"profile": args.profile,
                              "violations": [v.to_dict() for v in found]}, indent=2))
        else:
            print(format_report(found, args.profile))
        return 1 if blocking(found) else 0

    try:
        pbip = build_pbip(spec, args.out_dir, check=args.check, profile=args.profile,
                          handoff=not args.no_handoff)
    except SpecCheckError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Built PBIP: {pbip}")
    return 0


def _add_model_commands(sub: Any) -> None:
    """Subcommands that read or edit an existing PBIP (not a spec)."""
    p_table = sub.add_parser("table", help="entered-data table tools")
    table_sub = p_table.add_subparsers(dest="table_command", required=True)
    p_dump = table_sub.add_parser("dump", help="print the rows of an encoded entered-data table")
    src = p_dump.add_mutually_exclusive_group(required=True)
    src.add_argument("file", nargs="?", help="TMDL file; its first Binary.FromText payload is read")
    src.add_argument("--b64", help="a bare base64 payload instead of a file")
    p_dump.add_argument("--max-rows", type=int, default=20,
                        help="data rows to print (default 20)")

    p_report = sub.add_parser("report", help="report scaffolding")
    report_sub = p_report.add_subparsers(dest="report_command", required=True)
    p_blank = report_sub.add_parser("blank", help="create a blank report bound to an existing model")
    p_blank.add_argument("--client", required=True, help="folder holding <name>.SemanticModel")
    p_blank.add_argument("--model", nargs="+", required=True, help="model name(s)")
    p_blank.add_argument("--name", help="report name (one model only; default: the model name)")
    p_blank.add_argument("--theme", default=None, help="base theme name")
    p_blank.add_argument("--theme-file", help="theme JSON to copy into the report")
    p_blank.add_argument("--full", action="store_true",
                         help="write a complete PBIR definition (pages, report.json, ...)")
    p_blank.add_argument("--dry-run", action="store_true", help="list what would be created")

    p_clone = sub.add_parser("clone-report", help="copy a report under a new name and identity")
    p_clone.add_argument("template", help="existing <X>.Report folder")
    p_clone.add_argument("name", help="name of the new report")
    p_clone.add_argument("--out-dir", help="parent folder of the copy (default: the template's)")
    p_clone.add_argument("--model", help="semantic model folder the copy should point at")
    p_clone.add_argument("--force", action="store_true", help="replace an existing target folder")
    p_clone.add_argument("--logical-id", help="logicalId to use instead of a random UUID")
    p_clone.add_argument("--strict", action="store_true",
                         help="exit 1 when the copy fails the report integrity checks")

    for cmd, what in (("f-filters", "fill f-<Category> measures and f-All gates"),
                      ("i-filters", "regenerate the i-Applied Filters caption measure")):
        p = sub.add_parser(cmd, help=what)
        where = p.add_mutually_exclusive_group(required=True)
        where.add_argument("--model", action="append", help="<X>.SemanticModel folder (repeatable)")
        where.add_argument("--fleet", help="folder whose *.SemanticModel children are all processed")
        p.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
        p.add_argument("--no-backups", action="store_true", help="do not keep a timestamped backup")
        p.add_argument("-v", "--verbose", action="store_true")
        if cmd == "i-filters":
            p.add_argument("--skip-validation", action="store_true",
                           help="write even when the generated measure fails validation")


def _cmd_table(args: argparse.Namespace) -> int:
    from . import enter_data

    if args.b64 is not None:
        rows = enter_data.decode_b64_or_none(args.b64)
    else:
        try:
            rows = enter_data.decode_file(args.file)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    if rows is None:
        return 1
    sys.stdout.write(enter_data.format_dump(rows, args.max_rows))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from .report_scaffold import blank_reports_cli
    return blank_reports_cli(args)


def _cmd_clone(args: argparse.Namespace) -> int:
    from .report_scaffold import clone_report_cli
    return clone_report_cli(args)


def _model_targets(args: argparse.Namespace) -> list[tuple[str, Path]]:
    """``(label, folder)`` per target: a ``--model`` path as given, or
    ``<fleet>/<child>`` for each ``*.SemanticModel`` folder of ``--fleet``."""
    if args.model:
        return [(m, Path(m)) for m in args.model]
    fleet = args.fleet.rstrip("/\\") or args.fleet
    return [(f"{fleet}/{p.name}", p)
            for p in sorted(Path(args.fleet).glob("*.SemanticModel")) if p.is_dir()]


def _cmd_f_filters(args: argparse.Namespace) -> int:
    from .f_filters import run_cli
    return run_cli(_model_targets(args), dry_run=args.dry_run,
                   backups=not args.no_backups, verbose=args.verbose)


def _cmd_i_filters(args: argparse.Namespace) -> int:
    from .i_filters import run_cli
    return run_cli(_model_targets(args), dry_run=args.dry_run, backups=not args.no_backups,
                   validate=not args.skip_validation, verbose=args.verbose)


_MODEL_COMMANDS = {
    "table": _cmd_table,
    "report": _cmd_report,
    "clone-report": _cmd_clone,
    "f-filters": _cmd_f_filters,
    "i-filters": _cmd_i_filters,
}


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
    raise SystemExit(forge_main())
