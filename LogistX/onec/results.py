# LogistX/onec/results.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BotResult:
    ok: bool
    stage: str
    message: str
    recovered: bool = False

    @classmethod
    def success(cls, stage: str, message: str = "OK", recovered: bool = False):
        return cls(ok=True, stage=stage, message=message, recovered=recovered)

    @classmethod
    def fail(cls, stage: str, message: str):
        return cls(ok=False, stage=stage, message=message)