from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest


TESTS_DIR = Path(__file__).resolve().parent
ROAM_FIXTURE_DIR = TESTS_DIR / "data" / "roam"

sys.path.insert(0, str(TESTS_DIR / "data"))
import build_db  # noqa: E402


MIGRATION_NOTES_UUID = "73f8e2a0-1234-5678-90ab-cdef12345678"
ARCHITECTURE_UUID = "aa11bb22-0001-0002-0003-000000000001"
TOOLING_UUID = "aa11bb22-9999-9999-9999-999999999999"
SHARED_PREFIX = "aa11bb22"


@pytest.fixture(autouse=True)
def isolate_side_effects(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Tests must never write to the user's real telemetry DB or invoke emacsclient.

    Points `MEMENTO_USAGE_DB` at a per-test tmp file and sets `MEMENTO_NO_SYNC=1`
    so the org-roam sync helper is a no-op during the test run.
    """
    usage_db = tmp_path_factory.mktemp("usage") / "usage.db"
    monkeypatch.setenv("MEMENTO_USAGE_DB", str(usage_db))
    monkeypatch.setenv("MEMENTO_NO_SYNC", "1")


@pytest.fixture(scope="session")
def roam_fixture_dir() -> Path:
    return ROAM_FIXTURE_DIR


@pytest.fixture
def roam_dir(tmp_path: Path) -> Path:
    """Per-test copy of the real roam fixtures so update tests don't dirty the repo."""
    target = tmp_path / "roam"
    shutil.copytree(ROAM_FIXTURE_DIR, target)
    return target


@pytest.fixture
def roam_db(tmp_path: Path, roam_dir: Path) -> Path:
    db_path = tmp_path / "org-roam.db"
    build_db.build(roam_dir, db_path)
    return db_path


@pytest.fixture
def memento_env(monkeypatch: pytest.MonkeyPatch, roam_db: Path, roam_dir: Path) -> None:
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DB", str(roam_db))
    monkeypatch.setenv("MEMENTO_ORG_ROAM_DIR", str(roam_dir))


@pytest.fixture
def roam_db_with_heading_rows(tmp_path: Path, roam_dir: Path) -> Path:
    """Variant with injected level>0 rows, used to verify the level=0 filter."""
    db_path = tmp_path / "org-roam.db"
    heading_rows = [
        (f"{MIGRATION_NOTES_UUID[:8]}-heading-row-0001", str(roam_dir / "migration-notes.org"), 1),
        (f"{ARCHITECTURE_UUID[:8]}-heading-row-0002", str(roam_dir / "architecture.org"), 2),
    ]
    build_db.build(roam_dir, db_path, heading_rows=heading_rows)
    return db_path
