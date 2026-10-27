from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _run(*args: str, env_override: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    import os

    env = os.environ.copy()
    if env_override is not None:
        for key in ("MEMENTO_ORG_ROAM_DB", "MEMENTO_ORG_ROAM_DIR"):
            env.pop(key, None)
        env.update(env_override)
    return subprocess.run(
        [sys.executable, "-m", "memento.cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_read_compact_whole_file(memento_env):
    result = _run("read", "73f8e2a0-1234-5678-90ab-cdef12345678")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"sections"}
    file_entry, *heading_entries = payload["sections"]
    assert set(file_entry.keys()) == {"ref", "title", "short"}
    assert file_entry["ref"] == "73f8e2a0-1234-5678-90ab-cdef12345678"
    assert file_entry["title"] == "Migration Notes"
    assert file_entry["short"].startswith("We're distilling the large image classifier")
    assert [s["title"] for s in heading_entries] == ["Goals", "Constraints", "Risks", "Next steps"]
    for idx, section in enumerate(heading_entries, start=1):
        assert set(section.keys()) == {"ref", "title", "short"}
        assert section["ref"] == f"73f8e2a0-1234-5678-90ab-cdef12345678:{idx}"


def test_read_full_whole_file(memento_env):
    result = _run("read", "73f8e2a0", "--full")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"sections"}
    for section in payload["sections"]:
        assert set(section.keys()) == {"ref", "title", "content"}


def test_read_single_section_by_prefix(memento_env):
    result = _run("read", "73f8e2a0:2")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload.keys()) == {"ref", "title", "content"}
    assert payload["title"] == "Constraints"
    assert payload["content"] == "Latency budget is 200ms per batch. Must run on the existing GPU queue workers."
    assert payload["ref"] == "73f8e2a0-1234-5678-90ab-cdef12345678:2"


def test_read_ambiguous_prefix(memento_env):
    result = _run("read", "aa11bb22")
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["error"] == "ambiguous_prefix"


def test_read_not_found(memento_env):
    result = _run("read", "ffffffff")
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["error"] == "not_found"


def test_read_invalid_ref_path_like(memento_env):
    result = _run("read", "path/to/file.org")
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["error"] == "invalid_input"


def test_read_invalid_id_p(memento_env):
    for bad in ["73f8e2a0:0", "73f8e2a0:abc", "73f8e2a0:-1"]:
        result = _run("read", bad)
        assert result.returncode == 2, f"expected 2 for {bad!r}, got {result.returncode}\n{result.stderr}"
        assert json.loads(result.stdout)["error"] == "invalid_input"


def test_read_id_p_out_of_range(memento_env):
    result = _run("read", "73f8e2a0:99")
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["error"] == "not_found"


def test_read_whole_expands_section_ref_to_whole_file(memento_env):
    """`--whole` on a section ref returns the whole-file response, ignoring :id_p."""
    section = _run("read", "73f8e2a0:2")
    whole_via_flag = _run("read", "73f8e2a0:2", "--whole")
    whole_direct = _run("read", "73f8e2a0")
    assert section.returncode == 0 and whole_via_flag.returncode == 0 and whole_direct.returncode == 0
    assert json.loads(section.stdout).keys() == {"ref", "title", "content"}
    assert json.loads(whole_via_flag.stdout) == json.loads(whole_direct.stdout)


def test_read_whole_composes_with_full(memento_env):
    whole_full = _run("read", "73f8e2a0:2", "--whole", "--full")
    whole_full_direct = _run("read", "73f8e2a0", "--full")
    assert whole_full.returncode == 0 and whole_full_direct.returncode == 0
    assert json.loads(whole_full.stdout) == json.loads(whole_full_direct.stdout)


def test_read_db_unavailable():
    result = _run("read", "73f8e2a0", env_override={})
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"] == "db_unavailable"
