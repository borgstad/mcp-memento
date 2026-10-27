from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "memento.cli", *args],
        capture_output=True,
        text=True,
        env=full_env,
    )


def _env(roam_db: Path, roam_dir: Path) -> dict[str, str]:
    return {"MEMENTO_ORG_ROAM_DB": str(roam_db), "MEMENTO_ORG_ROAM_DIR": str(roam_dir)}


def test_list_returns_tagged_files(roam_db: Path, roam_dir: Path):
    result = _run("list", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"files"}
    refs = {f["ref"] for f in payload["files"]}
    assert "73f8e2a0-1234-5678-90ab-cdef12345678" in refs
    assert "aa11bb22-0001-0002-0003-000000000001" in refs
    assert "aa11bb22-9999-9999-9999-999999999999" in refs


def test_list_excludes_untagged(roam_db: Path, roam_dir: Path):
    result = _run("list", env=_env(roam_db, roam_dir))
    refs = {f["ref"] for f in json.loads(result.stdout)["files"]}
    assert "cc77dd88-0000-0000-0000-000000000000" not in refs


def test_list_entry_shape(roam_db: Path, roam_dir: Path):
    result = _run("list", env=_env(roam_db, roam_dir))
    payload = json.loads(result.stdout)
    for entry in payload["files"]:
        assert set(entry.keys()) == {"ref", "title"}
        assert isinstance(entry["title"], str)
