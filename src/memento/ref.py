from __future__ import annotations

from dataclasses import dataclass

from memento.errors import MementoError


@dataclass(frozen=True)
class Ref:
    file_uuid: str
    id_p: int | None

    def __str__(self) -> str:
        return self.file_uuid if self.id_p is None else f"{self.file_uuid}:{self.id_p}"


def parse(value: str) -> Ref:
    if not value:
        raise MementoError("invalid_input", "empty identifier")
    if "/" in value or value.endswith(".org"):
        raise MementoError("invalid_input", "path-like identifiers are not accepted")

    head, sep, tail = value.partition(":")
    if not head:
        raise MementoError("invalid_input", "missing file UUID")

    if not sep:
        return Ref(file_uuid=head, id_p=None)

    if not tail:
        raise MementoError("invalid_input", "missing id_p after ':'")

    try:
        id_p = int(tail)
    except ValueError as exc:
        raise MementoError("invalid_input", f"id_p must be a positive integer, got {tail!r}") from exc

    if id_p < 1:
        raise MementoError("invalid_input", f"id_p must be >= 1, got {id_p}")

    return Ref(file_uuid=head, id_p=id_p)
