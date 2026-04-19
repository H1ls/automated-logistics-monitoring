from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class NewTaskWorkflowService:
    """
    Сценарий создания новой задачи из строки '➕'.

    Отвечает за:
    - сбор task через TaskEditService
    - сохранение task через TasksService
    """

    tasks_service: Any
    task_edit_service: Any
    log: Callable[[str], None] | None = None

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def create_from_buffer(self, *, ts_phone: str, ka: str, fio: str, buffer: dict) -> tuple[
        bool, dict | None, str | None]:
        if not self.task_edit_service:
            return False, None, "task_edit_service_missing"

        if not self.tasks_service:
            return False, None, "tasks_service_missing"

        ok, task, err = self.task_edit_service.build_task_from_buffer(ts_phone=ts_phone,
                                                                      ka=ka,
                                                                      fio=fio,
                                                                      buffer=buffer,)
        if not ok:
            return False, None, err

        ok, new_task, err = self.tasks_service.add_task(task)
        if not ok:
            return False, None, err

        return True, new_task, None
