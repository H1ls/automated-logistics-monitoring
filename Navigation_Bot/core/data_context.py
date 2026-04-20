import json
from pathlib import Path
from Navigation_Bot.core.exceptions import (DataContextError, FileOperationError, JSONFormatError)
from Navigation_Bot.core.json_manager import JSONManager


class DataContext:
    """Централизованное хранилище JSON-данных"""

    def __init__(self, filepath, log_func=None):
        self.filepath = filepath
        self.manager = JSONManager(filepath, log_func=log_func)
        self.log = log_func
        try:
            self.data = self.manager.load_json() or []
        except JSONFormatError:
            # JSON невалидный - это ошибка конфигурации
            raise
        except FileNotFoundError:
            # Файл не существует - может быть это нормально (первый запуск)
            self.log(f"⚠️ Файл данных не найден, будет создан: {filepath}")
            self.data = []
        except Exception as e:
            # Неожиданное - логируем с полной информацией
            self.log(f"❌ Ошибка инициализации контекста: {type(e).__name__}: {e}")
            raise DataContextError(f"Cannot initialize DataContext from {filepath}") from e

    def set_filepath(self, filepath: str):
        """Сменить файл, с которым работает контекст"""
        filepath = Path(filepath)

        # Валидируем путь
        if not filepath.parent.exists():
            raise FileOperationError(f"Directory does not exist: {filepath.parent}")

        try:
            self.filepath = str(filepath)
            self.manager = JSONManager(str(filepath), log_func=self.log)
            self.data = self.manager.load_json() or []
            # self.log(f"✅ Контекст переключен на: {filepath}")
        except FileNotFoundError:
            self.log(f"⚠️ Файл не найден, создам новый: {filepath}")
            self.data = []
        except json.JSONDecodeError as e:
            self.log(f"❌ JSON невалидный в {filepath}: {e.msg} (строка {e.lineno})")
            raise JSONFormatError(f"Invalid JSON in {filepath}") from e
        except Exception as e:
            self.log(f"❌ Неожиданная ошибка: {type(e).__name__}: {e}")
            raise DataContextError(f"Cannot load {filepath}") from e

    def reload(self):
        try:
            self.data = self.manager.load_json() or []
        except Exception as e:
            self.log(f"❌ Ошибка reload: {e}")
            raise DataContextError(f"Cannot reload data") from e

    def save(self):
        try:
            # Используем безопасное сохранение
            self.manager.save_in_json(self.data, self.filepath)
        except Exception as e:
            self.log(f"❌ Ошибка сохранения: {e}")
            raise DataContextError(f"Cannot save to {self.filepath}") from e

    #TODO: Почистить ▼
    def get(self):
        return self.data

    def set(self, new_data):
        self.data = new_data
        self.save()

    def append(self, entry: dict):
        self.data.append(entry)
        self.save()
