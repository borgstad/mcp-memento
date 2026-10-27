from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from memento import usage
from memento.mcp_server import CliError, handle_call_tool


@pytest.fixture
def usage_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "usage.db"
    monkeypatch.setenv("MEMENTO_USAGE_DB", str(path))
    return path


def _call(name: str, arguments: dict | None = None):
    return asyncio.run(handle_call_tool(name, arguments or {}))


def test_record_writes_row(usage_db: Path, memento_env):
    _call("memento_list")
    rows = usage.summarize()
    assert rows["totals"]["calls"] == 1
    assert rows["by_tool"][0]["tool"] == "memento_list"
    assert rows["by_tool"][0]["calls"] == 1
    assert rows["by_tool"][0]["errors"] == 0


def test_record_captures_output_size(usage_db: Path, memento_env):
    _call("memento_read", {"ref": "73f8e2a0"})
    summary = usage.summarize()
    by = {entry["tool"]: entry for entry in summary["by_tool"]}
    assert by["memento_read"]["calls"] == 1
    assert by["memento_read"]["output_chars"] > 0
    assert by["memento_read"]["output_words"] > 0


def test_record_captures_errors(usage_db: Path, memento_env):
    with pytest.raises(CliError):
        _call("memento_read", {"ref": "ffffffffffff"})
    summary = usage.summarize()
    assert summary["by_tool"][0]["errors"] == 1
    assert summary["totals"]["calls"] == 1


def test_summarize_filters_by_tool(usage_db: Path, memento_env):
    _call("memento_list")
    _call("memento_read", {"ref": "73f8e2a0"})
    only_read = usage.summarize(tool="memento_read")
    assert only_read["totals"]["calls"] == 1
    assert only_read["by_tool"][0]["tool"] == "memento_read"


def test_summarize_filters_by_since(usage_db: Path, memento_env):
    _call("memento_list")
    # Far-future `since` filters everything out.
    summary = usage.summarize(since="2999-01-01")
    assert summary["totals"]["calls"] == 0
    assert summary["by_tool"] == []


def test_record_best_effort_when_db_unwritable(monkeypatch: pytest.MonkeyPatch, memento_env, capsys):
    # Point the DB at a path that can never be opened.
    monkeypatch.setenv("MEMENTO_USAGE_DB", "/proc/0/nope/usage.db")
    # The tool call must still succeed despite the telemetry failure.
    result = _call("memento_list")
    assert result and result[0].text


def test_usage_cli_command_returns_summary(usage_db: Path, memento_env):
    _call("memento_list")
    # Now invoke the CLI subprocess to read the summary.
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    env["MEMENTO_USAGE_DB"] = str(usage_db)
    result = subprocess.run(
        [sys.executable, "-m", "memento.cli", "usage"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["totals"]["calls"] == 1
