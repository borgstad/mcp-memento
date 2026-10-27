from __future__ import annotations

import json

import pytest

from memento.errors import EXIT_CODES, MementoError, emit


@pytest.mark.parametrize("code,expected_exit", list(EXIT_CODES.items()))
def test_emit_json_shape_and_exit(capsys: pytest.CaptureFixture, code: str, expected_exit: int):
    exit_code = emit(code, "human-readable message")
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"error": code, "message": "human-readable message"}
    assert exit_code == expected_exit


def test_unknown_error_code_rejected():
    with pytest.raises(ValueError):
        MementoError("not_a_real_code", "x")
