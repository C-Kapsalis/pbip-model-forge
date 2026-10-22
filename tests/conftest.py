"""Keep every test's writes out of the repository.

`pbip-forge clone-report` writes into the current working directory when no
target directory is given, and `pbip-forge report blank` writes its report
folder next to the model it is given. A test that calls either without a
target leaves a report folder in the repository root, and `git add -A` then
commits it.

Running the suite must not change the repository. This fixture runs the test
in its own temporary directory — so a command that writes to the working
directory writes to the temporary directory — and it fails the test if the
repository gains a report folder.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _is_report_folder(path: Path) -> bool:
    """A report folder is one that holds `.platform` or `definition.pbir`."""
    if not path.is_dir():
        return False
    return (path / ".platform").is_file() or (path / "definition.pbir").is_file()


@pytest.fixture(autouse=True)
def _run_in_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Run the test in the temporary directory; fail if the repository changes."""
    before = set(os.listdir(REPO_ROOT))
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    for name in sorted(set(os.listdir(REPO_ROOT)) - before):
        path = REPO_ROOT / name
        if _is_report_folder(path):
            raise AssertionError(
                f"the test wrote a report folder into the repository root: "
                f"{path} — give the command an explicit target directory "
                f"under tmp_path")
