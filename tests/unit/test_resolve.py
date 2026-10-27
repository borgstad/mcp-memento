from __future__ import annotations

from pathlib import Path

import pytest

from memento import resolve
from memento.errors import MementoError


def test_db_lookup_strips_outer_quotes(roam_db: Path):
    db = resolve.OrgRoamDb(roam_db)
    resolved = db.lookup("73f8e2a0")
    assert not resolved.file_uuid.startswith('"')
    assert not str(resolved.file_path).startswith('"')
    assert resolved.file_uuid == "73f8e2a0-1234-5678-90ab-cdef12345678"
    assert resolved.file_path.name == "migration-notes.org"


def test_db_lookup_case_insensitive(roam_db: Path):
    db = resolve.OrgRoamDb(roam_db)
    upper = db.lookup("73F8E2A0")
    lower = db.lookup("73f8e2a0")
    assert upper.file_uuid == lower.file_uuid


def test_ambiguous_prefix(roam_db: Path):
    db = resolve.OrgRoamDb(roam_db)
    with pytest.raises(MementoError) as exc:
        db.lookup("aa11bb22")
    assert exc.value.code == "ambiguous_prefix"


def test_not_found(roam_db: Path):
    db = resolve.OrgRoamDb(roam_db)
    with pytest.raises(MementoError) as exc:
        db.lookup("ffffffff")
    assert exc.value.code == "not_found"


def test_level_filter_ignores_heading_rows(roam_db_with_heading_rows: Path):
    db = resolve.OrgRoamDb(roam_db_with_heading_rows)
    # The migration-notes file UUID prefix overlaps with an injected heading row;
    # resolver must ignore the heading row and return the file-level node.
    resolved = db.lookup("73f8e2a0")
    assert resolved.file_uuid == "73f8e2a0-1234-5678-90ab-cdef12345678"


def test_directory_scan_fallback(roam_dir: Path):
    scan = resolve.DirectoryScan(roam_dir)
    resolved = scan.lookup("73f8e2a0")
    assert resolved.file_path.name == "migration-notes.org"
    with pytest.raises(MementoError) as exc:
        scan.lookup("aa11bb22")
    assert exc.value.code == "ambiguous_prefix"


def test_db_lookup_is_read_only(roam_db: Path):
    mtime_before = roam_db.stat().st_mtime_ns
    db = resolve.OrgRoamDb(roam_db)
    db.lookup("73f8e2a0")
    mtime_after = roam_db.stat().st_mtime_ns
    assert mtime_before == mtime_after


UNTAGGED_FIXTURE_UUID = "cc77dd88-0000-0000-0000-000000000000"


def test_db_lookup_excludes_untagged_file(roam_db: Path):
    db = resolve.OrgRoamDb(roam_db)
    with pytest.raises(MementoError) as exc:
        db.lookup(UNTAGGED_FIXTURE_UUID)
    assert exc.value.code == "not_found"


def test_db_iter_files_excludes_untagged(roam_db: Path):
    db = resolve.OrgRoamDb(roam_db)
    uuids = {r.file_uuid for r in db.iter_files()}
    assert UNTAGGED_FIXTURE_UUID not in uuids
    assert "73f8e2a0-1234-5678-90ab-cdef12345678" in uuids


def test_directory_scan_excludes_untagged_file(roam_dir: Path):
    scan = resolve.DirectoryScan(roam_dir)
    with pytest.raises(MementoError) as exc:
        scan.lookup(UNTAGGED_FIXTURE_UUID)
    assert exc.value.code == "not_found"


def test_directory_scan_iter_excludes_untagged(roam_dir: Path):
    scan = resolve.DirectoryScan(roam_dir)
    uuids = {r.file_uuid for r in scan.iter_files()}
    assert UNTAGGED_FIXTURE_UUID not in uuids
