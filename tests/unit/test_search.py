from __future__ import annotations

from pathlib import Path

from memento import resolve, search


def test_search_returns_section_refs(roam_db: Path, roam_dir: Path, monkeypatch):
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DB", str(roam_db))
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DIR", str(roam_dir))
    resolver = resolve.build_resolver()
    matches = search.search("Stateless CLI", resolver)
    refs = [m.ref for m in matches]
    assert "aa11bb22-0001-0002-0003-000000000001:2" in refs


def test_search_file_title_match_yields_bare_uuid(roam_db: Path, roam_dir: Path, monkeypatch):
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DB", str(roam_db))
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DIR", str(roam_dir))
    resolver = resolve.build_resolver()
    matches = search.search("Migration", resolver)
    refs = [m.ref for m in matches]
    # The file-level node "Migration Notes" matches via title; its ref is bare uuid (no :id_p).
    assert "73f8e2a0-1234-5678-90ab-cdef12345678" in refs


def test_search_snippet_is_bounded(roam_db: Path, roam_dir: Path, monkeypatch):
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DB", str(roam_db))
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DIR", str(roam_dir))
    resolver = resolve.build_resolver()
    matches = search.search("latency", resolver)
    for match in matches:
        assert len(match.snippet) <= search.SNIPPET_MAX


def test_search_empty_query_returns_empty(roam_db: Path, roam_dir: Path, monkeypatch):
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DB", str(roam_db))
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DIR", str(roam_dir))
    resolver = resolve.build_resolver()
    assert search.search("", resolver) == []
