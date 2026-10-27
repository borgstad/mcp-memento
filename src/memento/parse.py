from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import orgparse

from memento.errors import MementoError


@dataclass(frozen=True)
class NodeEntry:
    id_p: int | None
    title: str
    body: str
    body_start: int
    body_end: int
    level: int | None = None  # None for file-level node, 1.. for headings
    heading_start: int | None = None  # byte offset of '*' for heading entries; None for file-level


@dataclass(frozen=True)
class ParsedFile:
    file_uuid: str
    file_title: str
    raw: bytes
    entries: list[NodeEntry]


def _line_offsets(data: bytes) -> list[int]:
    offsets = [0]
    for i, byte in enumerate(data):
        if byte == 0x0A:
            offsets.append(i + 1)
    if not data or data[-1] != 0x0A:
        offsets.append(len(data))
    return offsets


def _skip_property_drawer(data: bytes, line_offsets: list[int], start_line: int) -> int:
    """Given a 1-indexed line where the drawer might start, return the 1-indexed line just past it.

    If line `start_line` is not `:PROPERTIES:` (case-insensitive, possibly indented), return start_line unchanged.
    """
    if start_line < 1 or start_line > len(line_offsets) - 1:
        return start_line
    line_text = data[line_offsets[start_line - 1] : line_offsets[start_line]].strip().lower()
    if line_text != b":properties:":
        return start_line
    line = start_line + 1
    while line < len(line_offsets):
        text = data[line_offsets[line - 1] : line_offsets[line]].strip().lower()
        line += 1
        if text == b":end:":
            return line
    return line


def _skip_leading_keywords(data: bytes, line_offsets: list[int], start_line: int, stop_line: int) -> int:
    """Skip leading `#+keyword: value` lines and blank lines from start_line up to (but not including) stop_line."""
    line = start_line
    while line < stop_line:
        chunk = data[line_offsets[line - 1] : line_offsets[line]]
        stripped = chunk.strip()
        if not stripped or stripped.startswith(b"#+"):
            line += 1
            continue
        break
    return line


def _byte_range(line_offsets: list[int], start_line: int, end_line_exclusive: int) -> tuple[int, int]:
    max_line_exclusive = len(line_offsets)
    if start_line < 1:
        start_line = 1
    if start_line >= max_line_exclusive:
        return line_offsets[-1], line_offsets[-1]
    if end_line_exclusive < start_line:
        end_line_exclusive = start_line
    if end_line_exclusive > max_line_exclusive:
        end_line_exclusive = max_line_exclusive
    return line_offsets[start_line - 1], line_offsets[end_line_exclusive - 1]


def _strip_for_display(body: str) -> str:
    return body.strip()


def load(path: Path) -> ParsedFile:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise MementoError("io_error", f"cannot read {path}: {exc}") from exc

    text = raw.decode("utf-8", errors="replace")
    root = orgparse.loads(text)
    line_offsets = _line_offsets(raw)
    total_lines = len(line_offsets) - 1

    headings = list(root[1:])
    first_heading_line = headings[0].linenumber if headings else total_lines + 1

    # Root body byte range: past top property drawer + leading #+keywords, up to first heading.
    after_drawer = _skip_property_drawer(raw, line_offsets, 1)
    after_keywords = _skip_leading_keywords(raw, line_offsets, after_drawer, first_heading_line)
    root_start, root_end = _byte_range(line_offsets, after_keywords, first_heading_line)

    file_uuid_prop = root.properties.get("ID") or root.properties.get("Id") or root.properties.get("id") or ""
    file_title = ""
    # orgparse exposes #+title via root.heading? No -- it stays in body. Extract here.
    for line_no in range(1, first_heading_line):
        line_text = raw[line_offsets[line_no - 1] : line_offsets[line_no]].decode("utf-8", errors="replace").strip()
        if line_text.lower().startswith("#+title:"):
            file_title = line_text.split(":", 1)[1].strip()
            break

    entries: list[NodeEntry] = [
        NodeEntry(
            id_p=None,
            title=file_title,
            body=_strip_for_display(raw[root_start:root_end].decode("utf-8", errors="replace")),
            body_start=root_start,
            body_end=root_end,
        )
    ]

    for idx, node in enumerate(headings, start=1):
        heading_line = node.linenumber
        heading_start, _ = _byte_range(line_offsets, heading_line, heading_line + 1)
        # body_start: line after heading, then skip the heading's own property drawer if any
        body_first_line = _skip_property_drawer(raw, line_offsets, heading_line + 1)
        # body_end: line of next heading at any depth, or total_lines + 1 for EOF
        next_line = headings[idx].linenumber if idx < len(headings) else total_lines + 1
        start, end = _byte_range(line_offsets, body_first_line, next_line)
        body_text = raw[start:end].decode("utf-8", errors="replace")
        entries.append(
            NodeEntry(
                id_p=idx,
                title=str(node.heading),
                body=_strip_for_display(body_text),
                body_start=start,
                body_end=end,
                level=node.level,
                heading_start=heading_start,
            )
        )

    return ParsedFile(file_uuid=file_uuid_prop, file_title=file_title, raw=raw, entries=entries)


def subtree_end_byte(entries: list[NodeEntry], target_idx: int, file_size: int) -> int:
    """Byte offset after the target heading's full subtree (descendants included).

    For an insertion at `--after <ref>` or `--parent <ref>`, the new heading must be placed
    AFTER every descendant of the target so existing nesting is preserved.
    """
    target = entries[target_idx]
    if target.level is None:
        raise ValueError("subtree_end_byte is undefined for the file-level node")
    for entry in entries[target_idx + 1 :]:
        if entry.level is not None and entry.level <= target.level:
            assert entry.heading_start is not None
            return entry.heading_start
    return file_size
