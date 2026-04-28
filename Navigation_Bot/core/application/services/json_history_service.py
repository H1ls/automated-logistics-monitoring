from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class JsonHistoryService:
    def __init__(self, filepath: str, time_field: str, log=None):
        self.filepath = Path(filepath)
        self.time_field = time_field
        self.log = log

    def append(self, item: Any) -> None:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        data = self._load_list()

        if hasattr(item, "id"):
            item.id = len(data) + 1

        if self.time_field and hasattr(item, self.time_field):
            if not getattr(item, self.time_field):
                setattr(item, self.time_field, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

        if is_dataclass(item):
            row = asdict(item)
        elif isinstance(item, dict):
            row = dict(item)
        else:
            raise TypeError("JsonHistoryService.append: item must be dataclass or dict")

        data.append(row)
        self._save_list(data)

    def get_by_task_index(self, task_index: int) -> list[dict]:
        data = self._load_list()
        return [row for row in data
                if isinstance(row, dict) and row.get("task_index") == task_index
                ]

    def _load_list(self) -> list:
        if not self.filepath.exists():
            return []

        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8") or "[]")
        except Exception:
            return []

        return data if isinstance(data, list) else []

    def _save_list(self, data: list) -> None:
        self.filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", )
