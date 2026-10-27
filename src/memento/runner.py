from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

from memento import create, links, parse, ref, resolve, search, sync, usage
from memento.errors import MementoError


SHORT_CHARS = 100


def _short(body: str) -> str:
    return body[:SHORT_CHARS]


def _emit(payload: dict) -> int:
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


def cmd_read(value: str, full: bool, whole: bool = False, link_format: links.LinkFormat = links.LinkFormat.INLINE) -> int:
    parsed_ref = ref.parse(value)
    resolver = resolve.build_resolver()
    resolved = resolver.lookup(parsed_ref.file_uuid)
    parsed = parse.load(resolved.file_path)

    if parsed_ref.id_p is None or whole:
        return _emit_whole_file(resolved.file_uuid, parsed, full=full, link_format=link_format)
    return _emit_single_section(resolved.file_uuid, parsed_ref.id_p, parsed, link_format=link_format)


def _emit_whole_file(file_uuid: str, parsed: parse.ParsedFile, full: bool, link_format: links.LinkFormat) -> int:
    body_key = "content" if full else "short"
    sections = []
    for entry in parsed.entries:
        ref_str = file_uuid if entry.id_p is None else f"{file_uuid}:{entry.id_p}"
        rendered_body = links.render(entry.body, link_format)
        sections.append(
            {
                "ref": ref_str,
                "title": entry.title,
                body_key: rendered_body if full else _short(rendered_body),
            }
        )
    return _emit({"sections": sections})


def _emit_single_section(file_uuid: str, id_p: int, parsed: parse.ParsedFile, link_format: links.LinkFormat) -> int:
    headings = parsed.entries[1:]
    if id_p < 1 or id_p > len(headings):
        raise MementoError(
            "not_found",
            f"id_p {id_p} out of range (file has {len(headings)} headings)",
        )
    entry = headings[id_p - 1]
    return _emit({"ref": f"{file_uuid}:{id_p}", "title": entry.title, "content": links.render(entry.body, link_format)})


def _read_content(content: str | None, content_file: str | None) -> str:
    if content is not None:
        return content
    if content_file is not None:
        if content_file == "-":
            return sys.stdin.read()
        try:
            return Path(content_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise MementoError("io_error", f"cannot read {content_file}: {exc}") from exc
    raise MementoError("invalid_input", "missing content: pass --content or --content-file")


def _atomic_replace(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except OSError as exc:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise MementoError("io_error", f"cannot write {path}: {exc}") from exc


_TODO_KEYWORDS = "(?:TODO|DONE|NEXT|WAITING|CANCELLED|STARTED|IN-PROGRESS|HOLD)"
_HEADING_LINE_RE = re.compile(
    r"^(?P<stars>\*+\s+)"
    rf"(?P<todo>{_TODO_KEYWORDS}\s+)?"
    r"(?P<priority>\[#[A-Z]\]\s+)?"
    r"(?P<title>.+?)"
    r"(?P<tags>\s+:(?:[\w@#%]+:)+)?\s*$"
)


def _rewrite_heading_line(line_bytes: bytes, new_title: str) -> bytes:
    line_str = line_bytes.decode("utf-8").rstrip("\n")
    match = _HEADING_LINE_RE.match(line_str)
    if not match:
        raise MementoError("io_error", f"could not parse heading line: {line_str!r}")
    rebuilt = (
        match.group("stars")
        + (match.group("todo") or "")
        + (match.group("priority") or "")
        + new_title.strip()
        + (match.group("tags") or "")
    )
    return (rebuilt + "\n").encode("utf-8")


def cmd_update(
    value: str,
    content: str | None,
    content_file: str | None,
    append: bool = False,
    title: str | None = None,
) -> int:
    parsed_ref = ref.parse(value)
    if content is None and content_file is None and title is None:
        raise MementoError(
            "invalid_input",
            "nothing to update: pass --content, --content-file, or --title",
        )

    resolver = resolve.build_resolver()
    resolved = resolver.lookup(parsed_ref.file_uuid)
    parsed = parse.load(resolved.file_path)

    if parsed_ref.id_p is None:
        target = parsed.entries[0]
        if title is not None:
            raise MementoError(
                "invalid_input",
                "--title is only valid for section refs (with :id_p); file titles are out of scope for v1",
            )
    else:
        headings = parsed.entries[1:]
        if parsed_ref.id_p < 1 or parsed_ref.id_p > len(headings):
            raise MementoError(
                "not_found",
                f"id_p {parsed_ref.id_p} out of range (file has {len(headings)} headings)",
            )
        target = headings[parsed_ref.id_p - 1]

    new_content: str | None = None
    if content is not None or content_file is not None:
        new_content = _read_content(content, content_file)
    if title is not None and not title.strip():
        raise MementoError("invalid_input", "--title must not be empty")

    work = parsed.raw
    if new_content is not None:
        if append:
            existing = target.body
            joiner = "\n" if existing and not existing.endswith("\n") else ""
            new_body = existing + joiner + ("\n" if existing else "") + new_content
        else:
            new_body = new_content
        replacement = _format_replacement(work, target.body_start, target.body_end, new_body)
        work = work[: target.body_start] + replacement + work[target.body_end :]

    if title is not None:
        assert target.heading_start is not None
        line_end = work.find(b"\n", target.heading_start)
        line_end = line_end + 1 if line_end != -1 else len(work)
        new_line = _rewrite_heading_line(work[target.heading_start : line_end], title)
        work = work[: target.heading_start] + new_line + work[line_end:]

    _atomic_replace(resolved.file_path, work)
    sync.update_file(resolved.file_path)

    canonical_ref = resolved.file_uuid if parsed_ref.id_p is None else f"{resolved.file_uuid}:{parsed_ref.id_p}"
    resulting_title = title.strip() if title is not None else target.title
    return _emit({"ref": canonical_ref, "title": resulting_title, "updated": True})


def _format_replacement(raw: bytes, body_start: int, body_end: int, new_body: str) -> bytes:
    original_ends_with_newline = body_end > body_start and raw[body_end - 1 : body_end] == b"\n"
    payload = new_body.encode("utf-8")
    if original_ends_with_newline and not payload.endswith(b"\n"):
        payload += b"\n"
    return payload


def cmd_usage(since: str | None, tool: str | None) -> int:
    payload = usage.summarize(since=since, tool=tool)
    return _emit(payload)


def cmd_list() -> int:
    resolver = resolve.build_resolver()
    files = []
    for resolved in resolver.iter_files():
        try:
            parsed = parse.load(resolved.file_path)
            title = parsed.file_title or ""
        except MementoError:
            title = ""
        files.append({"ref": resolved.file_uuid, "title": title})
    return _emit({"files": files})


def cmd_search(query: str, link_format: links.LinkFormat = links.LinkFormat.INLINE) -> int:
    if not query:
        raise MementoError("invalid_input", "search query must not be empty")
    resolver = resolve.build_resolver()
    matches = search.search(query, resolver, link_format=link_format)
    return _emit(
        {
            "query": query,
            "matches": [{"ref": m.ref, "title": m.title, "snippet": m.snippet} for m in matches],
        }
    )


def _roam_dir_or_error() -> Path:
    roam_dir_env = os.environ.get("MEMENTO_ORG_ROAM_DIR")
    if not roam_dir_env:
        raise MementoError(
            "db_unavailable",
            "MEMENTO_ORG_ROAM_DIR is required to write new files",
        )
    return Path(os.path.expanduser(roam_dir_env))


def _file_section_payload(file_uuid: str, path: Path, link_format: links.LinkFormat = links.LinkFormat.INLINE) -> dict:
    parsed = parse.load(path)
    sections = []
    for entry in parsed.entries:
        ref_str = file_uuid if entry.id_p is None else f"{file_uuid}:{entry.id_p}"
        rendered = links.render(entry.body, link_format)
        sections.append(
            {
                "ref": ref_str,
                "title": entry.title,
                "short": _short(rendered),
            }
        )
    return {"sections": sections}


def cmd_create(title: str, body: str | None) -> int:
    roam_dir = _roam_dir_or_error()
    if not roam_dir.exists():
        raise MementoError("io_error", f"roam directory does not exist: {roam_dir}")
    file_uuid, path = create.write_new_file(roam_dir, title, body)
    sync.update_file(path)
    return _emit(
        {
            "ref": file_uuid,
            "created": True,
            "file": _file_section_payload(file_uuid, path),
        }
    )


def cmd_delete(value: str, allow_file: bool) -> int:
    parsed_ref = ref.parse(value)
    resolver = resolve.build_resolver()
    resolved = resolver.lookup(parsed_ref.file_uuid)

    if parsed_ref.id_p is None:
        if not allow_file:
            raise MementoError(
                "invalid_input",
                "refusing to delete a whole file without --file (pass --file to delete the .org file from disk)",
            )
        parsed = parse.load(resolved.file_path)
        file_title = parsed.file_title
        try:
            os.unlink(resolved.file_path)
        except OSError as exc:
            raise MementoError("io_error", f"cannot remove {resolved.file_path}: {exc}") from exc
        sync.clear_file(resolved.file_path)
        return _emit({"ref": resolved.file_uuid, "title": file_title, "deleted": True})

    parsed = parse.load(resolved.file_path)
    headings = parsed.entries[1:]
    if parsed_ref.id_p < 1 or parsed_ref.id_p > len(headings):
        raise MementoError(
            "not_found",
            f"id_p {parsed_ref.id_p} out of range (file has {len(headings)} headings)",
        )
    target_idx = parsed_ref.id_p  # parsed.entries[0] is the file-level node; headings start at index 1
    target = parsed.entries[target_idx]
    assert target.heading_start is not None
    end = parse.subtree_end_byte(parsed.entries, target_idx, len(parsed.raw))
    new_bytes = parsed.raw[: target.heading_start] + parsed.raw[end:]
    _atomic_replace(resolved.file_path, new_bytes)
    sync.update_file(resolved.file_path)
    return _emit(
        {
            "ref": f"{resolved.file_uuid}:{parsed_ref.id_p}",
            "title": target.title,
            "deleted": True,
            "file": _file_section_payload(resolved.file_uuid, resolved.file_path),
        }
    )


def _format_inserted_heading(level: int, heading_text: str, body: str | None, prepend_blank: bool) -> bytes:
    prefix = b"" if prepend_blank else b"\n"
    chunks: list[bytes] = [prefix, b"*" * level, b" ", heading_text.encode("utf-8"), b"\n"]
    if body:
        chunks.append(body.rstrip("\n").encode("utf-8"))
        chunks.append(b"\n")
    chunks.append(b"\n")
    return b"".join(chunks)


def cmd_insert(
    file_ref_value: str,
    heading_text: str,
    body: str | None,
    after_ref: str | None,
    parent_ref: str | None,
    level_override: int | None,
) -> int:
    if not heading_text.strip():
        raise MementoError("invalid_input", "heading text must not be empty")
    if after_ref is not None and parent_ref is not None:
        raise MementoError("invalid_input", "--after and --parent are mutually exclusive")
    if level_override is not None and level_override < 1:
        raise MementoError("invalid_input", "--level must be a positive integer")

    file_ref = ref.parse(file_ref_value)
    if file_ref.id_p is not None:
        raise MementoError(
            "invalid_input",
            "insert target must be a file ref (no `:id_p`); use --after/--parent for position",
        )

    resolver = resolve.build_resolver()
    resolved = resolver.lookup(file_ref.file_uuid)

    stat_before = resolved.file_path.stat()
    parsed = parse.load(resolved.file_path)

    position_flag = "after" if after_ref is not None else ("parent" if parent_ref is not None else None)
    insertion_offset: int
    new_level: int
    new_id_p: int

    if position_flag is None:
        insertion_offset = len(parsed.raw)
        new_level = level_override if level_override is not None else 1
        new_id_p = len(parsed.entries)  # file-level node is entries[0]; new heading appended -> count
    else:
        position_value = after_ref if position_flag == "after" else parent_ref
        assert position_value is not None
        position_parsed = ref.parse(position_value)
        if position_parsed.id_p is None:
            raise MementoError(
                "invalid_input",
                f"--{position_flag} requires a section ref of the form `<file-uuid>:<id_p>`",
            )
        if position_parsed.file_uuid.lower() not in resolved.file_uuid.lower():
            raise MementoError(
                "invalid_input",
                f"--{position_flag} target must point inside the same file as the insert target",
            )
        headings = parsed.entries[1:]
        if position_parsed.id_p < 1 or position_parsed.id_p > len(headings):
            raise MementoError(
                "not_found",
                f"--{position_flag} id_p {position_parsed.id_p} out of range (file has {len(headings)} headings)",
            )
        target_idx = position_parsed.id_p  # index into parsed.entries (1-based skips file-level)
        target_entry = parsed.entries[target_idx]
        insertion_offset = parse.subtree_end_byte(parsed.entries, target_idx, len(parsed.raw))
        if position_flag == "after":
            assert target_entry.level is not None
            new_level = level_override if level_override is not None else target_entry.level
        else:  # parent
            assert target_entry.level is not None
            new_level = level_override if level_override is not None else target_entry.level + 1
        # New heading lands at the position right after the subtree end; its id_p reflects how many
        # headings precede it in document order after the splice.
        preceding_headings = sum(
            1
            for e in parsed.entries[1:]
            if e.heading_start is not None and e.heading_start < insertion_offset
        )
        new_id_p = preceding_headings + 1

    # Concurrency guard: re-stat before write.
    stat_now = resolved.file_path.stat()
    if stat_now.st_mtime_ns != stat_before.st_mtime_ns or stat_now.st_size != stat_before.st_size:
        raise MementoError(
            "io_error",
            "file changed on disk between parse and write; re-read and retry",
        )

    prepend_blank = insertion_offset == 0 or parsed.raw[max(0, insertion_offset - 2) : insertion_offset].endswith(
        b"\n\n"
    )
    new_segment = _format_inserted_heading(new_level, heading_text.strip(), body, prepend_blank)
    new_bytes = parsed.raw[:insertion_offset] + new_segment + parsed.raw[insertion_offset:]
    _atomic_replace(resolved.file_path, new_bytes)
    sync.update_file(resolved.file_path)

    return _emit(
        {
            "ref": f"{resolved.file_uuid}:{new_id_p}",
            "inserted": True,
            "file": _file_section_payload(resolved.file_uuid, resolved.file_path),
        }
    )
