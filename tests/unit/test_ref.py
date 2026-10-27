from __future__ import annotations

import pytest

from memento import ref
from memento.errors import MementoError


def test_bare_prefix():
    r = ref.parse("73f8e2a0")
    assert r.file_uuid == "73f8e2a0"
    assert r.id_p is None


def test_prefix_with_id_p():
    r = ref.parse("73f8e2a0:3")
    assert r.file_uuid == "73f8e2a0"
    assert r.id_p == 3


def test_full_uuid_accepted():
    r = ref.parse("73f8e2a0-1234-5678-90ab-cdef12345678:7")
    assert r.file_uuid == "73f8e2a0-1234-5678-90ab-cdef12345678"
    assert r.id_p == 7


def test_path_like_rejected():
    with pytest.raises(MementoError) as exc:
        ref.parse("path/to/file.org")
    assert exc.value.code == "invalid_input"


def test_dot_org_rejected():
    with pytest.raises(MementoError) as exc:
        ref.parse("migration-notes.org")
    assert exc.value.code == "invalid_input"


def test_empty_rejected():
    with pytest.raises(MementoError) as exc:
        ref.parse("")
    assert exc.value.code == "invalid_input"


@pytest.mark.parametrize("bad", ["73f8:0", "73f8:-1", "73f8:abc", "73f8:1.5", "73f8:"])
def test_invalid_id_p_rejected(bad: str):
    with pytest.raises(MementoError) as exc:
        ref.parse(bad)
    assert exc.value.code == "invalid_input"
