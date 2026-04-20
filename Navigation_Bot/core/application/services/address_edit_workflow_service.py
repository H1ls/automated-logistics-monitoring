from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from Navigation_Bot.gui.dialogs.address_edit_dialog import AddressEditDialog


@dataclass(slots=True)
class AddressEditWorkflowService:
    """
    Сценарий редактирования Погрузки/Выгрузки:
    - открывает AddressEditDialog
    - собирает patch через TaskEditService
    - сохраняет через TasksService

    Для новой строки возвращает preview-данные, но не сохраняет задачу.
    """

    data_context: Any
    tasks_service: Any
    task_edit_service: Any
    log: Callable[[str], None] | None = None

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    @staticmethod
    def resolve_prefix(col_name: str) -> str | None:
        if col_name in ["Погрузка", "Время погрузки"]:
            return "Погрузка"
        if col_name in ["Выгрузка", "Время выгрузки"]:
            return "Выгрузка"
        return None

    def edit_new_entry_block(self, *, prefix: str, parent, ) -> tuple[bool, dict | None, str | None]:

        temp_entry = {"Погрузка": [], "Выгрузка": []}

        dialog = AddressEditDialog(row_data=temp_entry,
                                   full_data=[],
                                   prefix=prefix,
                                   parent=parent,
                                   disable_save=True,
                                   data_context=self.data_context,
                                   log_func=self.log, )

        if not dialog.exec():
            return False, None, "dialog_cancelled"

        data_block, meta = dialog.get_result()
        if not data_block:
            return False, None, "empty_block"

        result = {"prefix": prefix,
                  "data_block": data_block,
                  "meta": meta or {},
                  }
        return True, result, None

    def edit_existing_entry_block(self,
                                  *,
                                  real_idx: int,
                                  prefix: str,
                                  parent, ) -> tuple[bool, dict | None, str | None]:

        json_data = self.data_context.get() or []
        if not (0 <= real_idx < len(json_data)):
            return False, None, "row_out_of_range"

        dialog = AddressEditDialog(row_data=json_data[real_idx],
                                   full_data=json_data,
                                   prefix=prefix,
                                   parent=parent,
                                   data_context=self.data_context,
                                   log_func=self.log, )

        if not dialog.exec():
            return False, None, "dialog_cancelled"

        data_block, meta = dialog.get_result()
        if not data_block:
            return False, None, "empty_block"

        if prefix == "Погрузка":
            ok, patch, err = self.task_edit_service.build_load_patch(data_block, meta)
        else:
            ok, patch, err = self.task_edit_service.build_unload_patch(data_block, meta)

        if not ok:
            return False, None, err

        ok, updated_row, err = self.tasks_service.apply_patch(real_idx, patch)
        if not ok:
            return False, None, err

        return (True, {"updated_row": updated_row,
                       "prefix": prefix,
                       "patch": patch, },
                None)
