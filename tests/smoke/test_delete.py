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


def test_delete_section_removes_heading_and_body(roam_db: Path, roam_dir: Path):
    target = roam_dir / "migration-notes.org"
    pre = target.read_text()
    assert "** Constraints" in pre

    result = _run("delete", "73f8e2a0:2", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["deleted"] is True
    assert payload["title"] == "Constraints"

    post = target.read_text()
    assert "** Constraints" not in post
    assert "Latency budget is 200ms" not in post
    # Surrounding sections survive.
    assert "* Goals" in post
    assert "* Risks" in post


def test_delete_section_removes_descendants_too(roam_db: Path, roam_dir: Path):
    # Architecture's "Boundaries" (id_p=2) has a deeper "Resolver internals" descendant.
    target = roam_dir / "architecture.org"
    pre = target.read_text()
    assert "*** Resolver internals" in pre

    result = _run("delete", "aa11bb22-0001:2", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr

    post = target.read_text()
    assert "* Boundaries" not in post
    assert "*** Resolver internals" not in post
    assert "File-UUID prefix lookup" not in post
    # Earlier sections survive.
    assert "* Components" in post


def test_delete_file_requires_explicit_flag(roam_db: Path, roam_dir: Path):
    target = roam_dir / "migration-notes.org"
    assert target.exists()
    result = _run("delete", "73f8e2a0", env=_env(roam_db, roam_dir))
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["error"] == "invalid_input"
    assert target.exists(), "file must NOT be deleted without --file"


def test_delete_file_with_flag_unlinks(roam_db: Path, roam_dir: Path):
    target = roam_dir / "migration-notes.org"
    assert target.exists()
    result = _run("delete", "73f8e2a0", "--file", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["deleted"] is True
    assert payload["title"] == "Migration Notes"
    assert not target.exists()


def test_delete_section_returns_post_state(roam_db: Path, roam_dir: Path):
    result = _run("delete", "73f8e2a0:2", env=_env(roam_db, roam_dir))
    payload = json.loads(result.stdout)
    titles = [s["title"] for s in payload["file"]["sections"]]
    assert "Constraints" not in titles
    # All other titles remain.
    assert {"Migration Notes", "Goals", "Risks", "Next steps"}.issubset(set(titles))


def test_delete_section_out_of_range(roam_db: Path, roam_dir: Path):
    result = _run("delete", "73f8e2a0:99", env=_env(roam_db, roam_dir))
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["error"] == "not_found"


def test_delete_invalid_ref(roam_db: Path, roam_dir: Path):
    result = _run("delete", "path/to/file.org", env=_env(roam_db, roam_dir))
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)["error"] == "invalid_input"
