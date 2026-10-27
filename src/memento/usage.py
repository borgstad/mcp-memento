from __future__ import annotations

import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger("memento.usage")

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "memento" / "usage.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    ts TEXT NOT NULL,
    tool TEXT NOT NULL,
    input_chars INTEGER NOT NULL,
    input_words INTEGER NOT NULL,
    output_chars INTEGER NOT NULL,
    output_words INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    exit_code INTEGER NOT NULL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS usage_ts_tool ON usage(ts, tool);
"""


def db_path() -> Path:
    env = os.environ.get("MEMENTO_USAGE_DB")
    return Path(os.path.expanduser(env)) if env else DEFAULT_DB_PATH


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    _ensure_schema(conn)
    return conn


def count_chars_words(text: str) -> tuple[int, int]:
    return len(text), len(text.split())


def record(
    tool: str,
    input_text: str,
    output_text: str,
    latency_ms: int,
    exit_code: int,
    error: str | None = None,
) -> None:
    """Best-effort write. Telemetry failures must never break the user-facing operation."""
    try:
        path = db_path()
        conn = _open(path)
        try:
            ic, iw = count_chars_words(input_text)
            oc, ow = count_chars_words(output_text)
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO usage (ts, tool, input_chars, input_words, output_chars, output_words, latency_ms, exit_code, error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ts, tool, ic, iw, oc, ow, latency_ms, exit_code, error),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"memento.usage: record failed: {exc}", file=sys.stderr)


def summarize(since: str | None = None, tool: str | None = None) -> dict[str, Any]:
    """Aggregate usage. Returns a dict suitable for direct JSON emission.

    `since` is an ISO date or datetime string (compared lexicographically thanks to ISO ordering).
    """
    path = db_path()
    if not path.exists():
        return {"since": since, "tool": tool, "totals": _empty_totals(), "by_tool": []}

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        where_parts: list[str] = []
        params: list[Any] = []
        if since:
            where_parts.append("ts >= ?")
            params.append(since)
        if tool:
            where_parts.append("tool = ?")
            params.append(tool)
        where = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        totals_row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(input_chars), 0), COALESCE(SUM(input_words), 0),"
            " COALESCE(SUM(output_chars), 0), COALESCE(SUM(output_words), 0),"
            " COALESCE(SUM(latency_ms), 0)"
            f" FROM usage{where}",
            params,
        ).fetchone()
        totals = {
            "calls": totals_row[0],
            "input_chars": totals_row[1],
            "input_words": totals_row[2],
            "output_chars": totals_row[3],
            "output_words": totals_row[4],
            "latency_ms": totals_row[5],
        }

        by_tool_rows = conn.execute(
            "SELECT tool, COUNT(*), COALESCE(SUM(input_chars), 0), COALESCE(SUM(output_chars), 0),"
            " COALESCE(SUM(output_words), 0), COALESCE(AVG(latency_ms), 0),"
            " SUM(CASE WHEN exit_code <> 0 THEN 1 ELSE 0 END)"
            f" FROM usage{where} GROUP BY tool ORDER BY tool",
            params,
        ).fetchall()
        by_tool = [
            {
                "tool": row[0],
                "calls": row[1],
                "input_chars": row[2],
                "output_chars": row[3],
                "output_words": row[4],
                "avg_latency_ms": int(round(row[5])),
                "errors": row[6],
            }
            for row in by_tool_rows
        ]
    finally:
        conn.close()

    return {"since": since, "tool": tool, "totals": totals, "by_tool": by_tool}


def _empty_totals() -> dict[str, int]:
    return {
        "calls": 0,
        "input_chars": 0,
        "input_words": 0,
        "output_chars": 0,
        "output_words": 0,
        "latency_ms": 0,
    }
