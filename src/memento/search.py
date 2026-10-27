from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memento import links, parse, resolve


SNIPPET_RADIUS = 40
SNIPPET_MAX = 120


@dataclass(frozen=True)
class Match:
    ref: str
    title: str
    snippet: str


def _snippet(body: str, idx: int, qlen: int) -> str:
    start = max(0, idx - SNIPPET_RADIUS)
    end = min(len(body), idx + qlen + SNIPPET_RADIUS)
    chunk = body[start:end].replace("\n", " ")
    if start > 0:
        chunk = "..." + chunk
    if end < len(body):
        chunk = chunk + "..."
    return chunk[:SNIPPET_MAX]


def _first_match(haystack: str, needle_lower: str) -> int | None:
    if not needle_lower:
        return None
    idx = haystack.lower().find(needle_lower)
    return idx if idx >= 0 else None


def search(
    query: str,
    resolver: resolve.CompositeResolver,
    link_format: links.LinkFormat = links.LinkFormat.INLINE,
) -> list[Match]:
    needle = query.lower()
    if not needle:
        return []
    matches: list[Match] = []
    for resolved in resolver.iter_files():
        try:
            parsed = parse.load(resolved.file_path)
        except Exception:
            continue
        for entry in parsed.entries:
            ref_str = resolved.file_uuid if entry.id_p is None else f"{resolved.file_uuid}:{entry.id_p}"
            rendered_body = links.render(entry.body, link_format)
            title_idx = _first_match(entry.title, needle)
            body_idx = _first_match(rendered_body, needle)
            if title_idx is not None:
                matches.append(Match(ref=ref_str, title=entry.title, snippet=entry.title))
            elif body_idx is not None:
                matches.append(
                    Match(ref=ref_str, title=entry.title, snippet=_snippet(rendered_body, body_idx, len(needle)))
                )
    return matches
