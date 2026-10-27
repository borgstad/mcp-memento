from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from memento.errors import MementoError


TAG_FILTER = "memento"
"""Hard-baked filetag every memento operation restricts to.

A file must carry `:memento:` in its `#+filetags:` line to be visible to the CLI.
Files without the tag are invisible regardless of whether they appear in `org-roam.db`.
"""


@dataclass(frozen=True)
class Resolved:
    file_uuid: str
    file_path: Path


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


class OrgRoamDb:
    def __init__(self, db_path: Path):
        self._db_path = db_path

    def open(self) -> sqlite3.Connection:
        uri = f"file:{self._db_path}?mode=ro"
        try:
            return sqlite3.connect(uri, uri=True)
        except sqlite3.Error as exc:
            raise MementoError("db_unavailable", f"cannot open {self._db_path}: {exc}") from exc

    def lookup(self, file_uuid_prefix: str) -> Resolved:
        conn = self.open()
        try:
            cur = conn.execute(
                "SELECT n.id, n.file FROM nodes n "
                "WHERE n.level = 0 "
                "AND n.id LIKE '\"' || ? || '%' "
                "AND EXISTS (SELECT 1 FROM tags _t WHERE _t.node_id = n.id AND _t.tag = ?) "
                "LIMIT 2",
                (file_uuid_prefix, f'"{TAG_FILTER}"'),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise MementoError("db_unavailable", f"query failed: {exc}") from exc
        finally:
            conn.close()

        if not rows:
            raise MementoError(
                "not_found",
                f"no :{TAG_FILTER}: file matches prefix {file_uuid_prefix!r}",
            )
        if len(rows) > 1:
            raise MementoError(
                "ambiguous_prefix",
                f"prefix {file_uuid_prefix!r} matches {len(rows)} or more :{TAG_FILTER}: files",
            )

        canonical_id = _strip_quotes(rows[0][0])
        file_path = Path(_strip_quotes(rows[0][1]))
        return Resolved(file_uuid=canonical_id, file_path=file_path)

    def iter_files(self):
        conn = self.open()
        try:
            cur = conn.execute(
                "SELECT n.id, n.file FROM nodes n "
                "WHERE n.level = 0 "
                "AND EXISTS (SELECT 1 FROM tags _t WHERE _t.node_id = n.id AND _t.tag = ?) "
                "ORDER BY n.file",
                (f'"{TAG_FILTER}"',),
            )
            for row in cur:
                yield Resolved(file_uuid=_strip_quotes(row[0]), file_path=Path(_strip_quotes(row[1])))
        except sqlite3.Error as exc:
            raise MementoError("db_unavailable", f"query failed: {exc}") from exc
        finally:
            conn.close()


_ID_LINE = re.compile(rb":ID:\s+([0-9A-Fa-f-]+)\s*$", re.MULTILINE)
_FILETAGS_LINE = re.compile(rb"^#\+filetags:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _has_tag(head: bytes, tag: str) -> bool:
    match = _FILETAGS_LINE.search(head)
    if not match:
        return False
    tag_token = f":{tag}:".encode("utf-8").lower()
    return tag_token in match.group(1).lower()


class DirectoryScan:
    def __init__(self, roam_dir: Path):
        self._roam_dir = roam_dir

    def lookup(self, file_uuid_prefix: str) -> Resolved:
        matches: list[Resolved] = []
        prefix_lower = file_uuid_prefix.lower()
        for path in self._roam_dir.rglob("*.org"):
            try:
                head = path.open("rb").read(4096)
            except OSError:
                continue
            id_match = _ID_LINE.search(head)
            if not id_match:
                continue
            if not _has_tag(head, TAG_FILTER):
                continue
            file_uuid = id_match.group(1).decode("ascii")
            if file_uuid.lower().startswith(prefix_lower):
                matches.append(Resolved(file_uuid=file_uuid, file_path=path))
                if len(matches) > 1:
                    break

        if not matches:
            raise MementoError(
                "not_found",
                f"no :{TAG_FILTER}: file under {self._roam_dir} matches prefix {file_uuid_prefix!r}",
            )
        if len(matches) > 1:
            raise MementoError(
                "ambiguous_prefix",
                f"prefix {file_uuid_prefix!r} matches 2 or more :{TAG_FILTER}: files under {self._roam_dir}",
            )
        return matches[0]

    def iter_files(self):
        for path in sorted(self._roam_dir.rglob("*.org")):
            try:
                head = path.open("rb").read(4096)
            except OSError:
                continue
            id_match = _ID_LINE.search(head)
            if not id_match:
                continue
            if not _has_tag(head, TAG_FILTER):
                continue
            yield Resolved(file_uuid=id_match.group(1).decode("ascii"), file_path=path)


class CompositeResolver:
    def __init__(self, db: OrgRoamDb | None, scan: DirectoryScan | None):
        if db is None and scan is None:
            raise MementoError(
                "db_unavailable",
                "no resolution source configured (set MEMENTO_ORG_ROAM_DB or MEMENTO_ORG_ROAM_DIR)",
            )
        self._db = db
        self._scan = scan

    def lookup(self, file_uuid_prefix: str) -> Resolved:
        if self._db is not None:
            try:
                return self._db.lookup(file_uuid_prefix)
            except MementoError as exc:
                if exc.code != "db_unavailable" or self._scan is None:
                    raise
        assert self._scan is not None
        return self._scan.lookup(file_uuid_prefix)

    def iter_files(self):
        if self._db is not None:
            try:
                yield from self._db.iter_files()
                return
            except MementoError as exc:
                if exc.code != "db_unavailable" or self._scan is None:
                    raise
        assert self._scan is not None
        yield from self._scan.iter_files()


def build_resolver() -> CompositeResolver:
    db_env = os.environ.get("MEMENTO_ORG_ROAM_DB")
    roam_dir_env = os.environ.get("MEMENTO_ORG_ROAM_DIR")

    db_path = Path(os.path.expanduser(db_env)) if db_env else None
    db = OrgRoamDb(db_path) if db_path is not None and db_path.exists() else None
    scan = DirectoryScan(Path(os.path.expanduser(roam_dir_env))) if roam_dir_env else None

    if db is None and scan is None:
        raise MementoError(
            "db_unavailable",
            "no resolution source configured: set MEMENTO_ORG_ROAM_DB or MEMENTO_ORG_ROAM_DIR",
        )

    return CompositeResolver(db=db, scan=scan)
