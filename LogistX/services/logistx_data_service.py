from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from LogistX.config.paths import LOGISTX_SAMPLE
from Navigation_Bot.core.json_store import JsonStore
from Navigation_Bot.core.logging import normalize_log_func


class LogistXDataService:
    def __init__(self, sample_path: Path = LOGISTX_SAMPLE, log_func: Callable[[str], None] | None = None):
        self.sample_path = sample_path
        self.log = normalize_log_func(log_func)

    def load_rows(self) -> list[dict]:
        if not self.sample_path.exists():
            self.log(f"❌ Нет файла: {self.sample_path}")
            return []

        try:
            data = json.loads(self.sample_path.read_text(encoding="utf-8") or "[]")
        except Exception as e:
            self.log(f"❌ Ошибка чтения LogistX JSON: {e}")
            return []

        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else []

    def save_rows(self, rows: list[dict]) -> bool:
        try:
            JsonStore(log_func=self.log).save_in_json(rows, self.sample_path)
            self.log(f"💾 LogistX: сохранено строк: {len(rows)}")
            return True
        except Exception as e:
            self.log(f"❌ Ошибка сохранения LogistX JSON: {e}")
            return False
