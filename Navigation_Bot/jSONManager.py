import os
import json
from typing import Any
import logging

class JSONManager:
    def __init__(self, file_path: str = None,log_func=None):
        self.file_path = file_path
        self.log = log_func or print

    def load_json(self, file_path: str = None) -> Any:
        path = file_path or self.file_path
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError:
            self.log(f"Ошибка чтения JSON: {path}")
            return []

    def save_json(self, data: Any, file_path: str = None) -> None:
        path = file_path or self.file_path
        if not path:
            self.log("Путь к файлу не задан")
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
        except Exception as e:
            self.log(f"Ошибка сохранения JSON: {e}")

    def update_json(self, new_data: Any, file_path: str = None) -> None:
        existing = self.load_json(file_path)
        if isinstance(existing, list) and isinstance(new_data, list):
            existing.extend(new_data)
        elif isinstance(existing, dict) and isinstance(new_data, dict):
            existing.update(new_data)
        else:
            self.log("Форматы данных не совпадают")
            return
        self.save_json(existing, file_path)
