from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SYNC_TIMEOUT_SECS = 5
DISABLE_ENV = "MEMENTO_NO_SYNC"


def _elisp_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _eval(form: str) -> None:
    if os.environ.get(DISABLE_ENV):
        return
    try:
        result = subprocess.run(
            ["emacsclient", "--eval", form],
            capture_output=True,
            text=True,
            timeout=SYNC_TIMEOUT_SECS,
        )
    except (FileNotFoundError, OSError) as exc:
        print(f"memento.sync: emacsclient unavailable, org-roam DB will be stale until manual sync ({exc})", file=sys.stderr)
        return
    except subprocess.TimeoutExpired:
        print(f"memento.sync: emacsclient timed out after {SYNC_TIMEOUT_SECS}s", file=sys.stderr)
        return
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        print(f"memento.sync: emacsclient returned {result.returncode}: {stderr[:300]}", file=sys.stderr)


def update_file(path: Path) -> None:
    """Best-effort sync of a single file's row in org-roam.db after a write."""
    _eval(f"(org-roam-db-update-file {_elisp_string(str(path))})")


def clear_file(path: Path) -> None:
    """Best-effort removal of a file's row from org-roam.db after the file is unlinked."""
    _eval(f"(org-roam-db-clear-file {_elisp_string(str(path))})")
