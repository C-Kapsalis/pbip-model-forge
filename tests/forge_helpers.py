"""Shared helpers for the pbip-model-forge command tests.

The CLI is driven in-process through ``pbip_model_forge.cli.forge_main`` so a
test can monkeypatch library seams (for example the i-Applied Filters
validator). Output is captured with redirect_stdout / redirect_stderr.
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import shutil
import sys
import zlib
from pathlib import Path
from dataclasses import dataclass

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC_DIR))

from pbip_model_forge.cli import forge_main  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class Run:
    code: int
    out: str
    err: str

    @property
    def text(self) -> str:
        return self.out + self.err


class lazy_module:
    """Import a module on first attribute access (keeps collection green
    while the proposed API does not exist yet)."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, attr: str):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


def forge(*args: object) -> Run:
    """Run ``pbip-forge ARGS`` in-process and capture exit code and output."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = forge_main([str(a) for a in args])
        except SystemExit as exc:  # argparse errors and explicit exits
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    return Run(int(code or 0), out.getvalue(), err.getvalue())


def copy_fixture(name: str, dest: Path) -> Path:
    target = dest / Path(name).name
    shutil.copytree(FIXTURES / name, target)
    return target


def tree(root: Path) -> dict[str, bytes]:
    """Every file under root (hidden ones included) -> bytes."""
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def raw_deflate_b64(payload: bytes) -> str:
    """Raw DEFLATE (level 9, window 15, no zlib header) then base64."""
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return base64.b64encode(c.compress(payload) + c.flush()).decode("ascii")


def inflate_b64(b64: str) -> bytes:
    return zlib.decompress(base64.b64decode(b64), -15)


def entered_data_tmdl(table: str, payloads: list[str]) -> str:
    """A table file whose partition(s) hold the given encoded payloads."""
    text = f"table '{table}'\n\tlineageTag: {table.lower()}\n\n"
    for i, b64 in enumerate(payloads):
        text += (
            f"\tpartition '{table} {i}' = m\n\t\tmode: import\n\t\tsource =\n\t\t\t\tlet\n"
            "\t\t\t\t    Source = Table.FromRows(Json.Document(Binary.Decompress("
            f"Binary.FromText(\"{b64}\", BinaryEncoding.Base64), Compression.Deflate)), "
            "let _t = ((type nullable text) meta [Serialized.Text = true]) in "
            "type table [A = _t, B = _t])\n\t\t\t\tin\n\t\t\t\t    Source\n\n"
        )
    return text
