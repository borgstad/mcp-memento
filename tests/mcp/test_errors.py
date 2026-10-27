from __future__ import annotations

import asyncio
import json

import pytest

from memento.mcp_server import CliError, handle_call_tool


def _call(name: str, arguments: dict | None = None):
    return asyncio.run(handle_call_tool(name, arguments or {}))


def _err_payload(exc: CliError) -> dict:
    return json.loads(str(exc))


def test_not_found_surfaces_as_tool_error(memento_env):
    with pytest.raises(CliError) as exc:
        _call("memento_read", {"ref": "ffffffffffff"})
    assert _err_payload(exc.value)["error"] == "not_found"


def test_ambiguous_prefix_surfaces(memento_env):
    with pytest.raises(CliError) as exc:
        _call("memento_read", {"ref": "aa11bb22"})
    assert _err_payload(exc.value)["error"] == "ambiguous_prefix"


def test_invalid_input_path_like(memento_env):
    with pytest.raises(CliError) as exc:
        _call("memento_read", {"ref": "path/to/file.org"})
    assert _err_payload(exc.value)["error"] == "invalid_input"


def test_db_unavailable_when_env_missing(monkeypatch):
    monkeypatch.delenv("MEMENTO_ORG_ROAM_DB", raising=False)
    monkeypatch.delenv("MEMENTO_ORG_ROAM_DIR", raising=False)
    with pytest.raises(CliError) as exc:
        _call("memento_read", {"ref": "73f8e2a0"})
    assert _err_payload(exc.value)["error"] == "db_unavailable"


def test_unknown_tool_name(memento_env):
    with pytest.raises(CliError) as exc:
        _call("memento_does_not_exist")
    assert _err_payload(exc.value)["error"] == "invalid_input"


def test_insert_invalid_target_propagates(memento_env):
    with pytest.raises(CliError) as exc:
        _call("memento_insert", {"file_ref": "73f8e2a0:1", "heading": "X"})
    assert _err_payload(exc.value)["error"] == "invalid_input"


def test_search_empty_query_propagates(memento_env):
    with pytest.raises(CliError) as exc:
        _call("memento_search", {"query": ""})
    assert _err_payload(exc.value)["error"] == "invalid_input"
