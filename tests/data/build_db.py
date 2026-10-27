"""Build a minimal org-roam.db pointing at a roam directory's .org files.

Used by the test conftest to materialise an in-tree fixture index without committing
absolute paths. Also runnable directly for manual inspection:

    uv run python tests/data/build_db.py <roam_dir> <output.db>
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path


_ID_LINE = re.compile(rb":ID:\s+([0-9A-Fa-f-]+)\s*$", re.MULTILINE)
_TITLE_LINE = re.compile(rb"#\+title:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_FILETAGS_LINE = re.compile(rb"^#\+filetags:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_TAG_TOKEN = re.compile(r":([^:\s]+):")


def _extract_top_id_title_tags(org_path: Path) -> tuple[str, str, list[str]] | None:
    head = org_path.read_bytes()[:4096]
    id_match = _ID_LINE.search(head)
    title_match = _TITLE_LINE.search(head)
    tags_match = _FILETAGS_LINE.search(head)
    if not id_match:
        return None
    file_uuid = id_match.group(1).decode("ascii")
    title = title_match.group(1).decode("utf-8") if title_match else org_path.stem
    tags: list[str] = []
    if tags_match:
        tags_text = tags_match.group(1).decode("utf-8")
        tags = _TAG_TOKEN.findall(tags_text)
    return file_uuid, title, tags


def build(roam_dir: Path, db_path: Path, heading_rows: list[tuple[str, str, int]] | None = None) -> None:
    """Build a fixture org-roam.db.

    `heading_rows` lets a test inject synthetic level>0 rows to verify the level=0 filter.
    Each tuple is (id, file_path_str, level).
    """
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY,
                file TEXT NOT NULL,
                level INTEGER NOT NULL,
                pos INTEGER,
                todo TEXT,
                priority TEXT,
                scheduled TEXT,
                deadline TEXT,
                title TEXT,
                properties TEXT,
                olp TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE tags (
                node_id TEXT NOT NULL,
                tag TEXT NOT NULL
            )
            """
        )
        for org_path in sorted(roam_dir.glob("*.org")):
            extracted = _extract_top_id_title_tags(org_path)
            if extracted is None:
                continue
            file_uuid, title, tags = extracted
            # org-roam stores values as string-literals (surrounded by double quotes).
            conn.execute(
                "INSERT INTO nodes (id, file, level, pos, title) VALUES (?, ?, ?, ?, ?)",
                (
                    f'"{file_uuid}"',
                    f'"{org_path.resolve()}"',
                    0,
                    1,
                    f'"{title}"',
                ),
            )
            for tag in tags:
                conn.execute(
                    "INSERT INTO tags (node_id, tag) VALUES (?, ?)",
                    (f'"{file_uuid}"', f'"{tag}"'),
                )
        for heading_id, file_path, level in heading_rows or []:
            conn.execute(
                "INSERT INTO nodes (id, file, level, pos, title) VALUES (?, ?, ?, ?, ?)",
                (f'"{heading_id}"', f'"{file_path}"', level, 1, '"injected"'),
            )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.stderr.write("usage: build_db.py <roam_dir> <output.db>\n")
        sys.exit(2)
    build(Path(sys.argv[1]), Path(sys.argv[2]))
