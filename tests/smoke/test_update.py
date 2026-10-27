from __future__ import annotations

import hashlib
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


def test_update_section_preserves_surrounding_bytes(roam_db: Path, roam_dir: Path):
    """Updating a section keeps every line outside the targeted body byte-identical.

    Verified by parsing the file before and after and asserting that all entries
    other than the target retain identical body bytes, and that the pre-target
    prefix of the file is byte-identical.
    """
    from memento import parse

    target_path = roam_dir / "migration-notes.org"
    pre = parse.load(target_path)
    target_entry = next(e for e in pre.entries if e.id_p == 2)

    result = _run("update", "73f8e2a0:2", "--content", "NEW CONSTRAINT", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "ref": "73f8e2a0-1234-5678-90ab-cdef12345678:2",
        "title": "Constraints",
        "updated": True,
    }

    post = parse.load(target_path)
    assert post.entries[2].body == "NEW CONSTRAINT"
    # All other entries have identical body content.
    for pre_entry, post_entry in zip(pre.entries, post.entries):
        if pre_entry.id_p == 2:
            continue
        assert pre_entry.body == post_entry.body, f"entry id_p={pre_entry.id_p} body changed"
    # The bytes before the target's body must be byte-identical.
    assert pre.raw[: target_entry.body_start] == post.raw[: target_entry.body_start]


def test_update_preserves_descendant_headings(roam_db: Path, roam_dir: Path):
    """Updating 'Goals' (id_p=1) must leave its child '** Constraints' heading line untouched."""
    target = roam_dir / "migration-notes.org"
    original = target.read_bytes()
    assert b"** Constraints" in original

    result = _run("update", "73f8e2a0:1", "--content", "REWRITTEN GOALS", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr

    updated = target.read_bytes()
    assert b"** Constraints" in updated
    assert b"REWRITTEN GOALS" in updated
    # The Constraints heading and its body must survive.
    assert b"Latency budget is 200ms" in updated


def test_update_file_level_body(roam_db: Path, roam_dir: Path):
    target = roam_dir / "migration-notes.org"
    original = target.read_bytes()

    result = _run("update", "73f8e2a0", "--content", "NEW INTRO LINE", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "ref": "73f8e2a0-1234-5678-90ab-cdef12345678",
        "title": "Migration Notes",
        "updated": True,
    }

    updated = target.read_bytes()
    assert b"NEW INTRO LINE" in updated
    # Headings and their bodies survive verbatim.
    for marker in [b"* Goals", b"** Constraints", b"* Risks", b"* Next steps", b"Halve inference latency", b"Int8 quantization"]:
        assert marker in updated, marker


def test_update_missing_content_errors(roam_db: Path, roam_dir: Path):
    result = _run("update", "73f8e2a0:1", env=_env(roam_db, roam_dir))
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["error"] == "invalid_input"


def test_update_out_of_range_does_not_touch_file(roam_db: Path, roam_dir: Path):
    target = roam_dir / "migration-notes.org"
    pre = target.read_bytes()
    pre_hash = hashlib.sha256(pre).hexdigest()

    result = _run("update", "73f8e2a0:99", "--content", "x", env=_env(roam_db, roam_dir))
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["error"] == "not_found"

    post = target.read_bytes()
    assert hashlib.sha256(post).hexdigest() == pre_hash


def test_update_content_from_file(roam_db: Path, roam_dir: Path, tmp_path: Path):
    content_path = tmp_path / "new.txt"
    content_path.write_text("FROM A FILE")

    result = _run("update", "73f8e2a0:3", "--content-file", str(content_path), env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    assert b"FROM A FILE" in (roam_dir / "migration-notes.org").read_bytes()


def test_round_trip_read_update_read(roam_db: Path, roam_dir: Path):
    env = _env(roam_db, roam_dir)

    update = _run("update", "73f8e2a0:2", "--content", "200ms remains the budget.", env=env)
    assert update.returncode == 0, update.stderr

    read = _run("read", "73f8e2a0:2", env=env)
    assert read.returncode == 0, read.stderr
    payload = json.loads(read.stdout)
    assert payload["content"] == "200ms remains the budget."


def test_update_append_extends_existing_body(roam_db: Path, roam_dir: Path):
    env = _env(roam_db, roam_dir)
    pre = _run("read", "73f8e2a0:2", env=env)
    pre_content = json.loads(pre.stdout)["content"]

    update = _run("update", "73f8e2a0:2", "--append", "--content", "Extra context line.", env=env)
    assert update.returncode == 0, update.stderr

    post = _run("read", "73f8e2a0:2", env=env)
    post_content = json.loads(post.stdout)["content"]
    assert pre_content in post_content
    assert "Extra context line." in post_content
    # Pre-existing content stays first; the appended line follows after a blank line separator.
    assert post_content.startswith(pre_content)
    assert post_content.endswith("Extra context line.")
