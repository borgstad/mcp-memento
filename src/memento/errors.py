from __future__ import annotations

import json
import sys
from dataclasses import dataclass


EXIT_CODES = {
    "not_found": 1,
    "ambiguous_prefix": 1,
    "db_unavailable": 1,
    "invalid_input": 2,
    "io_error": 3,
}


@dataclass
class MementoError(Exception):
    code: str
    message: str

    def __post_init__(self) -> None:
        if self.code not in EXIT_CODES:
            raise ValueError(f"unknown error code: {self.code}")
        super().__init__(self.message)


def emit(code: str, message: str) -> int:
    sys.stdout.write(json.dumps({"error": code, "message": message}, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return EXIT_CODES[code]
