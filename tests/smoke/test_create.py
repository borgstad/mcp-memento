from __future__ import annotations

import json
import os
import re
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


def _env(roam_dir: Path) -> dict[str, str]:
    return {"MEMENTO_ORG_ROAM_DIR": str(roam_dir)}


def test_create_writes_canonical_template(tmp_path: Path):
    roam = tmp_path / "roam"
    roam.mkdir()
    result = _run("create", "My New Note", "--body", "first line of body", env=_env(roam))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"ref", "created", "file"}
    assert payload["created"] is True
    new_ref = payload["ref"]
    assert re.fullmatch(r"[0-9a-f-]{36}", new_ref), new_ref

    written = roam / "my-new-note.org"
    assert written.exists()
    contents = written.read_text()
    assert contents.startswith(":PROPERTIES:\n")
    assert f":ID: {new_ref}" in contents
    assert "\n#+title: My New Note\n" in contents
    assert "\n#+filetags: :memento:\n" in contents
    assert "first line of body" in contents


def test_create_filename_collision_disambiguates(tmp_path: Path):
    roam = tmp_path / "roam"
    roam.mkdir()
    r1 = _run("create", "Note", env=_env(roam))
    r2 = _run("create", "Note", env=_env(roam))
    r3 = _run("create", "Note", env=_env(roam))
    assert r1.returncode == r2.returncode == r3.returncode == 0
    assert (roam / "note.org").exists()
    assert (roam / "note_1.org").exists()
    assert (roam / "note_2.org").exists()


def test_create_empty_title_rejected(tmp_path: Path):
    roam = tmp_path / "roam"
    roam.mkdir()
    result = _run("create", "", env=_env(roam))
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["error"] == "invalid_input"


def test_create_unslugifiable_title_rejected(tmp_path: Path):
    roam = tmp_path / "roam"
    roam.mkdir()
    result = _run("create", "!!!", env=_env(roam))
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["error"] == "invalid_input"


def test_create_without_roam_dir_errors():
    result = subprocess.run(
        [sys.executable, "-m", "memento.cli", "create", "Note"],
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"] == "db_unavailable"


def test_create_response_embeds_file_section_payload(tmp_path: Path):
    roam = tmp_path / "roam"
    roam.mkdir()
    result = _run("create", "Sample", "--body", "hello", env=_env(roam))
    payload = json.loads(result.stdout)
    sections = payload["file"]["sections"]
    assert len(sections) == 1
    assert sections[0]["title"] == "Sample"
    assert sections[0]["short"] == "hello"
    assert sections[0]["ref"] == payload["ref"]
