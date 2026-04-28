# pet.project\Navigation_Bot\core\repositories\json_task_repository.py
import json
from pathlib import Path
from Navigation_Bot.core.exceptions import (DataContextError, FileOperationError, JSONFormatError)
from Navigation_Bot.core.json_manager import JSONManager
from Navigation_Bot.core.domain.entities.task import Task
from Navigation_Bot.core.domain.mappers.task_mapper import TaskMapper

class JsonTaskRepository:
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

    def get(self):
        return self.data

    def set(self, new_data):
        self.data = new_data
        self.save()

    def append(self, entry: dict):
        self.data.append(entry)
        self.save()

    # --- Новый repository API: Task-уровень ---

    def list_tasks(self) -> list[Task]:
        self.reload()
        return [
            TaskMapper.from_dict(row)
            for row in self.data
            if isinstance(row, dict)
        ]

    def get_by_index(self, index_key: int) -> Task | None:
        self.reload()

        for row in self.data:
            if isinstance(row, dict) and row.get("index") == index_key:
                return TaskMapper.from_dict(row)

        return None

    def save_task(self, task: Task) -> None:
        self.reload()

        task.ensure_processing_consistency()
        task_dict = TaskMapper.to_dict(task)

        index_key = task.index
        for i, row in enumerate(self.data):
            if isinstance(row, dict) and row.get("index") == index_key:
                self.data[i] = task_dict
                self.save()
                return

        self.data.append(task_dict)
        self.save()

    def replace_all(self, tasks: list[Task]) -> None:
        new_data = []

        for task in tasks:
            task.ensure_processing_consistency()
            new_data.append(TaskMapper.to_dict(task))

        self.set(new_data)

    def delete_by_index(self, index_key: int) -> bool:
        self.reload()

        for i, row in enumerate(self.data):
            if isinstance(row, dict) and row.get("index") == index_key:
                self.data.pop(i)
                self.save()
                return True

        return False