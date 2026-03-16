# LogistX/onec/context.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RaceContext:
    race_name: str
    race_search_text: str | None = None

    departure_dt: str | None = None
    load_in: str | None = None
    load_out: str | None = None
    unload_in: str | None = None
    unload_out: str | None = None

    driver_rating: int | None = None
    driver_comment: str | None = None

    meta: dict = field(default_factory=dict)

    # сюда бот может складывать промежуточные данные
    state: dict = field(default_factory=dict)

    def get_search_text(self) -> str:
        return self.race_search_text or self.race_name