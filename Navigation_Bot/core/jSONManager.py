import os
import json
import logging
from typing import Any
from pathlib import Path
from Navigation_Bot.core.paths import CONFIG_JSON


class JSONManager:
    def __init__(self, file_path: str = None, log_func=None):
        self.file_path = file_path
        self.log = log_func or print
        self.data = self.load_json(file_path)  # ← загружаем один раз и храним в self.data

    def load_json(self, file_path: str = None) -> Any:
        path = file_path or self.file_path
        if not path or not os.path.exists(path):
            return []

        try:
            with open(path, "r", encoding="utf-8") as file:
                content = file.read().strip()
                if not content:
                    return []
                return json.loads(content)
        except json.JSONDecodeError:
            self.log(f"Ошибка чтения JSON: {path}")
            return []

    def reload(self):
        self.data = self.load_json(self.file_path) or []

    def save(self):
        self.save_in_json(self.data, self.file_path)

    def save_in_json(self, data, filepath=None):
        filepath = Path(filepath or self.file_path)  # ← если не передан, берём сохранённый
        filepath.parent.mkdir(parents=True, exist_ok=True)
        try:
            with filepath.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            self.log(f"❌ Ошибка сохранения JSON: {e}")

    def update_json(self, new_data: Any, file_path: str = None) -> None:
        existing = self.load_json(file_path)
        if isinstance(existing, list) and isinstance(new_data, list):
            existing.extend(new_data)
        elif isinstance(existing, dict) and isinstance(new_data, dict):
            existing.update(new_data)
        else:
            self.log("Форматы данных не совпадают")
            return
        self.save_in_json(existing, file_path)

    @staticmethod
    def get_selectors(section: str, CONFIG_JSON) -> dict:
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                config = json.load(f)

            section_data = config.get(section, {})
            custom = section_data.get("custom", {})
            default = section_data.get("default", {})

            if custom:
                return custom
            if default:
                return default
            raise ValueError(f"⛔ Нет селекторов в разделе '{section}'")

        except Exception as e:
            print(f"❌ Ошибка при загрузке селекторов '{section}': {e}")
            return {}
