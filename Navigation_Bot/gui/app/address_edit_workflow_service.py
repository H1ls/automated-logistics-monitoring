from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from Navigation_Bot.gui.dialogs.address_edit_dialog import AddressEditDialog


@dataclass(slots=True)
class AddressEditWorkflowService:
    task_repository: Any
    tasks_service: Any
    task_edit_service: Any
    log: Callable[[str], None] | None = None

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    @staticmethod
    def resolve_prefix(col_name: str) -> str | None:
        col_name = (col_name or "").strip()
        if "Погрузка" in col_name:
            return "Погрузка"
        if "Выгрузка" in col_name:
            return "Выгрузка"
        return None

    def edit_address(self, *, real_idx: int, col_name: str, parent=None) -> tuple[bool, dict | None, str | None]:
        prefix = self.resolve_prefix(col_name)
        if not prefix:
            return False, None, "unsupported_column"

        if not self.tasks_service:
            return False, None, "tasks_service_missing"

        if not self.task_edit_service:
            return False, None, "task_edit_service_missing"

        row_data = self.tasks_service.get_row(real_idx)
        if not row_data:
            return False, None, "row_not_found"

        dialog = AddressEditDialog(row_data=row_data,
                                   prefix=prefix,
                                   parent=parent,
                                   log_func=self.log)

        if not dialog.exec():
            return False, None, "cancelled"

        result = dialog.get_result()
        if not result:
            return False, None, "empty_result"

        data_block, meta = result
        if not data_block:
            return False, None, "empty_block"

        if prefix == "Погрузка":
            ok, patch, err = self.task_edit_service.build_load_patch(data_block, meta)
        else:
            ok, patch, err = self.task_edit_service.build_unload_patch(data_block,
                                                                       meta,
                                                                       processed=dialog.get_processed())

        if not ok:
            self._log(f"build_patch error: {err}")
            return False, None, err

        patch[dialog.raw_key] = dialog.get_raw_value()

        ok, updated_row, err = self.tasks_service.apply_patch(real_idx, patch)
        if not ok:
            self._log(f"apply_patch error: {err}")
            return False, None, err

        return True, updated_row, None
