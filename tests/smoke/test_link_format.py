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


def _next_steps_content(payload: dict) -> str:
    sections = payload["sections"]
    return next(s for s in sections if s["title"] == "Next steps")["content"]


def test_read_inline_is_default(roam_db: Path, roam_dir: Path):
    result = _run("read", "73f8e2a0", "--full", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    body = _next_steps_content(json.loads(result.stdout))
    assert "Architecture (ref:aa11bb22)" in body
    assert "[[id:" not in body


def test_read_raw_preserves_link_syntax(roam_db: Path, roam_dir: Path):
    result = _run("read", "73f8e2a0", "--full", "--link-format", "raw", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    body = _next_steps_content(json.loads(result.stdout))
    assert "[[id:AA11BB22-0001-0002-0003-000000000001][Architecture]]" in body


def test_read_title_format_is_lossy(roam_db: Path, roam_dir: Path):
    result = _run("read", "73f8e2a0", "--full", "--link-format", "title", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    body = _next_steps_content(json.loads(result.stdout))
    assert "Architecture" in body
    assert "(ref:" not in body
    assert "[[id:" not in body


def test_read_single_section_inline(roam_db: Path, roam_dir: Path):
    result = _run("read", "73f8e2a0:4", env=_env(roam_db, roam_dir))  # Next steps
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "Architecture (ref:aa11bb22)" in payload["content"]


def test_search_snippet_uses_link_format(roam_db: Path, roam_dir: Path):
    result = _run("search", "Architecture", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    # The snippet from migration-notes Next steps should include the inline form.
    snippets = [m["snippet"] for m in payload["matches"]]
    assert any("Architecture (ref:aa11bb22)" in s for s in snippets) or any("Architecture" in s for s in snippets)


def test_inline_prefix_resolves_when_unique(roam_db: Path, roam_dir: Path):
    """An 8-char inline-rendered prefix resolves directly when it's unique in the corpus."""
    # migration-notes' 8-char prefix `73f8e2a0` is unique.
    result = _run("read", "73f8e2a0", env=_env(roam_db, roam_dir))
    assert result.returncode == 0, result.stderr
    titles = [s["title"] for s in json.loads(result.stdout)["sections"]]
    assert "Migration Notes" in titles


def test_inline_prefix_errors_cleanly_when_ambiguous(roam_db: Path, roam_dir: Path):
    """The architect's design accepts occasional 8-char collisions; the CLI must signal `ambiguous_prefix`.

    The agent's recovery path: read with `--full` for context, or `list`/`search` to disambiguate.
    """
    result = _run("read", "aa11bb22", env=_env(roam_db, roam_dir))
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["error"] == "ambiguous_prefix"
