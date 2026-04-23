from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class EditableFieldWorkflowService:
    """
    Сценарий сохранения простого редактируемого поля строки.
    """

    tasks_service: Any
    log: Callable[[str], None] | None = None

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def save_field(self,
                   *,
                   real_idx: int,
                   header: str,
                   value: str, ) -> tuple[bool, dict | None, str | None]:
        if not self.tasks_service:
            return False, None, "tasks_service_missing"

        return self.tasks_service.update_editable_field(real_idx=real_idx,header=header,value=value,)
