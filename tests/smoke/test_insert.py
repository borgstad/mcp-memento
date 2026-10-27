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


def test_insert_default_appends_top_level(roam_db: Path, roam_dir: Path):
    result = _run(
        "insert",
        "73f8e2a0-1234-5678-90ab-cdef12345678",
        "New Section",
        "--body",
        "appended body",
        env=_env(roam_db, roam_dir),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"ref", "inserted", "file"}
    assert payload["inserted"] is True
    sections = payload["file"]["sections"]
    assert sections[-1]["title"] == "New Section"
    assert sections[-1]["ref"] == payload["ref"]
    # File content carries the new heading as level 1.
    file_text = (roam_dir / "migration-notes.org").read_text()
    assert "\n* New Section\nappended body\n" in file_text


def test_insert_after_makes_sibling_at_same_level(roam_db: Path, roam_dir: Path):
    # Insert as a sibling after id_p=2 ("Constraints", level 2).
    result = _run(
        "insert",
        "73f8e2a0-1234-5678-90ab-cdef12345678",
        "Sibling Of Constraints",
        "--after",
        "73f8e2a0:2",
        "--body",
        "sibling body",
        env=_env(roam_db, roam_dir),
    )
    assert result.returncode == 0, result.stderr
    file_text = (roam_dir / "migration-notes.org").read_text()
    # The new heading must appear at level 2 (`** `), AFTER Constraints, BEFORE the next `* Risks`.
    constraints_idx = file_text.index("** Constraints")
    new_idx = file_text.index("** Sibling Of Constraints")
    risks_idx = file_text.index("* Risks")
    assert constraints_idx < new_idx < risks_idx


def test_insert_parent_nests_one_level_deeper(roam_db: Path, roam_dir: Path):
    # Insert as a child of id_p=3 ("Risks", level 1).
    result = _run(
        "insert",
        "73f8e2a0-1234-5678-90ab-cdef12345678",
        "Mitigation",
        "--parent",
        "73f8e2a0:3",
        "--body",
        "use a lockfile",
        env=_env(roam_db, roam_dir),
    )
    assert result.returncode == 0, result.stderr
    file_text = (roam_dir / "migration-notes.org").read_text()
    risks_idx = file_text.index("* Risks")
    mitigation_idx = file_text.index("** Mitigation")
    next_steps_idx = file_text.index("* Next steps")
    assert risks_idx < mitigation_idx < next_steps_idx


def test_insert_preserves_other_sections_byte_identical(roam_db: Path, roam_dir: Path):
    """Heading insertion must not corrupt any unrelated section body."""
    target = roam_dir / "migration-notes.org"
    from memento import parse

    pre = parse.load(target)
    _run(
        "insert",
        "73f8e2a0-1234-5678-90ab-cdef12345678",
        "Appended Section",
        "--body",
        "appended body",
        env=_env(roam_db, roam_dir),
    )
    post = parse.load(target)
    # All pre-existing entries (file-level + 4 headings) keep identical body content.
    pre_bodies = [(e.title, e.body) for e in pre.entries]
    post_bodies = [(e.title, e.body) for e in post.entries]
    for pre_pair in pre_bodies:
        assert pre_pair in post_bodies, pre_pair


def test_insert_after_and_parent_mutually_exclusive(roam_db: Path, roam_dir: Path):
    result = _run(
        "insert",
        "73f8e2a0-1234-5678-90ab-cdef12345678",
        "X",
        "--after",
        "73f8e2a0:1",
        "--parent",
        "73f8e2a0:1",
        env=_env(roam_db, roam_dir),
    )
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)["error"] == "invalid_input"


def test_insert_target_must_be_file_ref(roam_db: Path, roam_dir: Path):
    result = _run(
        "insert",
        "73f8e2a0-1234-5678-90ab-cdef12345678:1",
        "X",
        env=_env(roam_db, roam_dir),
    )
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)["error"] == "invalid_input"


def test_insert_empty_heading_rejected(roam_db: Path, roam_dir: Path):
    result = _run(
        "insert",
        "73f8e2a0-1234-5678-90ab-cdef12345678",
        "",
        env=_env(roam_db, roam_dir),
    )
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)["error"] == "invalid_input"


def test_insert_after_out_of_range(roam_db: Path, roam_dir: Path):
    result = _run(
        "insert",
        "73f8e2a0-1234-5678-90ab-cdef12345678",
        "Stray",
        "--after",
        "73f8e2a0:99",
        env=_env(roam_db, roam_dir),
    )
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["error"] == "not_found"


def test_insert_level_override(roam_db: Path, roam_dir: Path):
    result = _run(
        "insert",
        "73f8e2a0-1234-5678-90ab-cdef12345678",
        "Deep Override",
        "--level",
        "3",
        "--body",
        "deeply",
        env=_env(roam_db, roam_dir),
    )
    assert result.returncode == 0, result.stderr
    file_text = (roam_dir / "migration-notes.org").read_text()
    assert "\n*** Deep Override\ndeeply\n" in file_text
