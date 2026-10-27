from __future__ import annotations

import re
from enum import Enum


class LinkFormat(str, Enum):
    INLINE = "inline"
    RAW = "raw"
    TITLE = "title"


_LINK_RE = re.compile(r"\[\[id:([0-9a-fA-F-]{36})\]\[([^\]]+)\]\]")
PREFIX_LEN = 8


def render(text: str, fmt: LinkFormat = LinkFormat.INLINE) -> str:
    """Render org-roam `[[id:UUID][Title]]` links in `text` per `fmt`.

    - INLINE: `Title (ref:<8-char-lowercase-prefix>)`
    - RAW:    pass-through (text unchanged)
    - TITLE:  `Title` only (lossy: agent loses the navigation handle)
    """
    if fmt is LinkFormat.RAW:
        return text

    def replace(match: re.Match[str]) -> str:
        uuid = match.group(1)
        title = match.group(2)
        if fmt is LinkFormat.TITLE:
            return title
        prefix = uuid.replace("-", "")[:PREFIX_LEN].lower()
        return f"{title} (ref:{prefix})"

    return _LINK_RE.sub(replace, text)


def parse_format(value: str | None) -> LinkFormat:
    if value is None:
        return LinkFormat.INLINE
    try:
        return LinkFormat(value)
    except ValueError as exc:
        raise ValueError(f"unknown link format {value!r}; expected one of: {[f.value for f in LinkFormat]}") from exc
