from __future__ import annotations

import asyncio
import json
from pathlib import Path

from memento.mcp_server import handle_call_tool, handle_list_tools


def _call(name: str, arguments: dict | None = None):
    return asyncio.run(handle_call_tool(name, arguments or {}))


def _payload(result) -> dict:
    assert len(result) == 1
    assert result[0].type == "text"
    return json.loads(result[0].text)


def test_list_tools_surface(memento_env):
    tools = asyncio.run(handle_list_tools())
    names = {t.name for t in tools}
    assert names == {
        "memento_read",
        "memento_update",
        "memento_list",
        "memento_search",
        "memento_create",
        "memento_insert",
        "memento_delete",
        "memento_version",
    }


def test_version_tool(memento_env):
    payload = _payload(_call("memento_version"))
    assert payload["name"] == "memento-mcp"
    assert isinstance(payload["version"], str) and payload["version"]


def test_read_pass_through(memento_env):
    payload = _payload(_call("memento_read", {"ref": "73f8e2a0"}))
    assert set(payload.keys()) == {"sections"}
    titles = [s["title"] for s in payload["sections"]]
    assert titles == ["Migration Notes", "Goals", "Constraints", "Risks", "Next steps"]


def test_read_single_section(memento_env):
    payload = _payload(_call("memento_read", {"ref": "73f8e2a0:2"}))
    assert payload["title"] == "Constraints"
    assert "Latency budget" in payload["content"]


def test_read_full_and_whole_flags(memento_env):
    whole = _payload(_call("memento_read", {"ref": "73f8e2a0:2", "whole": True, "full": True}))
    direct = _payload(_call("memento_read", {"ref": "73f8e2a0", "full": True}))
    assert whole == direct


def test_list_excludes_untagged(memento_env):
    payload = _payload(_call("memento_list"))
    refs = {f["ref"] for f in payload["files"]}
    assert "73f8e2a0-1234-5678-90ab-cdef12345678" in refs
    assert "cc77dd88-0000-0000-0000-000000000000" not in refs


def test_search_pass_through(memento_env):
    payload = _payload(_call("memento_search", {"query": "latency"}))
    assert payload["query"] == "latency"
    refs = [m["ref"] for m in payload["matches"]]
    assert any(r.startswith("73f8e2a0") and ":" in r for r in refs)


def test_create_then_insert_round_trip(monkeypatch, tmp_path, memento_env):
    roam = tmp_path / "new_roam"
    roam.mkdir()
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DIR", str(roam))
    monkeypatch.delenv("MEMENTO_ORG_ROAM_DB", raising=False)

    created = _payload(_call("memento_create", {"title": "MCP Smoke", "body": "intro"}))
    new_ref = created["ref"]
    assert created["created"] is True
    assert created["file"]["sections"][0]["title"] == "MCP Smoke"

    inserted = _payload(
        _call(
            "memento_insert",
            {"file_ref": new_ref, "heading": "First Section", "body": "first body"},
        )
    )
    assert inserted["inserted"] is True
    titles = [s["title"] for s in inserted["file"]["sections"]]
    assert titles == ["MCP Smoke", "First Section"]


def test_update_round_trip(roam_db: Path, roam_dir: Path, monkeypatch):
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DB", str(roam_db))
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DIR", str(roam_dir))

    updated = _payload(_call("memento_update", {"ref": "73f8e2a0:2", "content": "NEW VIA MCP"}))
    assert updated == {
        "ref": "73f8e2a0-1234-5678-90ab-cdef12345678:2",
        "title": "Constraints",
        "updated": True,
    }

    after = _payload(_call("memento_read", {"ref": "73f8e2a0:2"}))
    assert after["content"] == "NEW VIA MCP"
