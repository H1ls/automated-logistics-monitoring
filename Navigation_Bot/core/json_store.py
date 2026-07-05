import os
import json
from typing import Any
from pathlib import Path
import tempfile
import hashlib

from Navigation_Bot.core.logging import normalize_log_func


class JsonStore:
    def __init__(self, file_path: str = None, log_func=None):
        self.file_path = file_path
        self.log = normalize_log_func(log_func)
        self.data = self.load_json(file_path)

    def save_in_json(self, data, filepath=None):
        """Атомарное сохранение с backup и валидацией"""
        filepath = Path(filepath or self.file_path)

        # 1. Убедимся что директория существует
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # 2. Сначала пишем в temp файл в ТОЙ ЖЕ директории, чтобы гарантировать что это на том же диске
        with tempfile.NamedTemporaryFile(mode='w',
                                         dir=filepath.parent,
                                         delete=False,
                                         encoding='utf-8',
                                         suffix='.tmp') as tmp_file:

            tmp_path = Path(tmp_file.name)
            try:
                json.dump(data, tmp_file, ensure_ascii=False, indent=2)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            except Exception as e:
                self.log(f"❌ Ошибка при записи в temp файл: {e}")
                tmp_path.unlink()  # Удалим temp файл
                raise

        # 3. Проверяем что temp файл валиден
        try:
            with open(tmp_path, 'r', encoding='utf-8') as f:
                json.load(f)  # Парсим, чтобы проверить валидность
            # self.log(f"✅ Temp файл валиден: {tmp_path}")
        except json.JSONDecodeError as e:
            self.log(f"❌ Temp файл невалиден: {e}")
            tmp_path.unlink()
            raise ValueError(f"Generated JSON is invalid: {e}") from e

        # 4. Если есть старый файл - делаем backup
        backup_path = None
        if filepath.exists():
            backup_path = filepath.with_suffix('.json.backup')
            try:
                filepath.rename(backup_path)
                # self.log(f"💾 Backup создан: {backup_path}")
            except Exception as e:
                self.log(f"⚠️ Не удалось создать backup: {e}")
                tmp_path.unlink()
                raise

        # 5. Атомарный rename
        try:
            os.replace(tmp_path, filepath)
            # self.log(f"✅ Сохранено: {filepath}")

            # Удалим backup если сохранение успешно
            if backup_path and backup_path.exists():
                backup_path.unlink()
        except Exception as e:
            # Если rename не удался - восстанавливаем из backup
            if backup_path and backup_path.exists():
                try:
                    backup_path.rename(filepath)
                    self.log(f"⚠️ Восстановлено из backup")
                except:
                    pass
            if tmp_path.exists():
                tmp_path.unlink()
            raise

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
            default = section_data.get("default", {}) or {}
            custom = section_data.get("custom", {}) or {}

            # сначала берём default, поверх накатываем custom
            merged = {**default, **custom}
            if merged:
                return merged

            raise ValueError(f"⛔ Нет селекторов в разделе '{section}'")

        except Exception as e:
            print(f"❌ Ошибка при загрузке селекторов '{section}': {e}")
            return {}
