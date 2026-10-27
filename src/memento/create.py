from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from memento.errors import MementoError
from memento.resolve import TAG_FILTER


FILENAME_MAX_LEN = 100


def slugify(title: str) -> str:
    """Title -> filename stem. Mirrors org-roam-mcp's `_title_to_filename`."""
    slug = re.sub(r"[^\w\s-]", "", title)
    slug = re.sub(r"[-\s]+", "-", slug)
    slug = slug.strip("-").lower()
    if len(slug) > FILENAME_MAX_LEN:
        slug = slug[:FILENAME_MAX_LEN]
    return slug


def render_template(node_id: str, title: str, body: str | None) -> bytes:
    lines = [
        ":PROPERTIES:",
        f":ID: {node_id}",
        ":END:",
        "",
        f"#+title: {title}",
        f"#+filetags: :{TAG_FILTER}:",
        "",
    ]
    if body:
        lines.append(body.rstrip("\n"))
        lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def _candidate_paths(roam_dir: Path, stem: str):
    yield roam_dir / f"{stem}.org"
    for counter in range(1, 10_000):
        yield roam_dir / f"{stem}_{counter}.org"


def write_new_file(roam_dir: Path, title: str, body: str | None) -> tuple[str, Path]:
    """Write a new memento file. Returns (file_uuid, path)."""
    stripped = title.strip()
    if not stripped:
        raise MementoError("invalid_input", "title must not be empty")
    stem = slugify(stripped)
    if not stem:
        raise MementoError("invalid_input", f"title {title!r} slugifies to empty")

    node_id = str(uuid.uuid4())
    payload = render_template(node_id, stripped, body)

    last_error: OSError | None = None
    for candidate in _candidate_paths(roam_dir, stem):
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            continue
        except OSError as exc:
            last_error = exc
            break
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            return node_id, candidate
        except OSError as exc:
            try:
                os.unlink(candidate)
            except OSError:
                pass
            raise MementoError("io_error", f"cannot write {candidate}: {exc}") from exc

    raise MementoError(
        "io_error",
        f"could not pick a free filename for title {title!r} under {roam_dir}"
        + (f": {last_error}" if last_error else ""),
    )
