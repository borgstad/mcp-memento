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


def test_search_body_substring_section_level(roam_db: Path, roam_dir: Path):
    result = _run("search", "latency", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["query"] == "latency"
    refs = [m["ref"] for m in payload["matches"]]
    assert "73f8e2a0-1234-5678-90ab-cdef12345678:1" in refs
    assert "73f8e2a0-1234-5678-90ab-cdef12345678:2" in refs


def test_search_title_match(roam_db: Path, roam_dir: Path):
    result = _run("search", "Architecture", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    refs = [m["ref"] for m in payload["matches"]]
    assert "aa11bb22-0001-0002-0003-000000000001" in refs


def test_search_case_insensitive(roam_db: Path, roam_dir: Path):
    upper = _run("search", "LATENCY", env=_env(roam_db, roam_dir))
    lower = _run("search", "latency", env=_env(roam_db, roam_dir))
    assert upper.returncode == 0 and lower.returncode == 0
    assert json.loads(upper.stdout)["matches"] == json.loads(lower.stdout)["matches"]


def test_search_no_matches(roam_db: Path, roam_dir: Path):
    result = _run("search", "thisstringneverappearsanywhere", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["matches"] == []


def test_search_empty_query_errors(roam_db: Path, roam_dir: Path):
    result = _run("search", "", env=_env(roam_db, roam_dir))
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["error"] == "invalid_input"


def test_search_match_shape(roam_db: Path, roam_dir: Path):
    result = _run("search", "resolver", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["matches"], "expected at least one match"
    for match in payload["matches"]:
        assert set(match.keys()) == {"ref", "title", "snippet"}
        assert match["snippet"]


def test_search_excludes_untagged_file(roam_db: Path, roam_dir: Path):
    """`untagged.org` has no :memento: tag and mentions 'latency'; the match must NOT surface."""
    result = _run("search", "latency", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    refs = [m["ref"] for m in json.loads(result.stdout)["matches"]]
    assert not any(r.startswith("cc77dd88") for r in refs), refs
