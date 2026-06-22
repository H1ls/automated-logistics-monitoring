from __future__ import annotations

import os
import time
from threading import Lock
from typing import Any, Callable


class TaskTableController:
    """Координирует обновление репозитория и отрисовку основной таблицы задач."""

    def __init__(
        self,
        *,
        task_repository: Any,
        sort_controller: Any,
        table_manager: Any,
        row_highlighter: Any,
        on_rows_changed: Callable[[list[dict[str, Any]]], None],
        open_id_manager: Callable[[], None],
    ) -> None:
        self.task_repository = task_repository
        self.sort_controller = sort_controller
        self.table_manager = table_manager
        self.row_highlighter = row_highlighter
        self.on_rows_changed = on_rows_changed
        self.open_id_manager = open_id_manager

        self._data_lock = Lock()
        self._last_reload_signature: tuple[str, bool] | None = None
        self._last_reload_at = 0.0

    def reload_and_show(self) -> None:
        with self._data_lock:
            source_key = getattr(self.task_repository, "current_source_key", "")
            use_incremental = self._use_incremental_refresh()
            signature = (source_key, use_incremental)
            now = time.monotonic()
            if use_incremental and self._last_reload_signature == signature and now - self._last_reload_at < 0.25:
                return

            self._last_reload_signature = signature
            self._last_reload_at = now
            if use_incremental:
                self.task_repository.refresh_incremental_or_reload()
            else:
                self.task_repository.reload()
            self.on_rows_changed(self.task_repository.get())

        self.display_current_data()

    def display_current_data(self) -> None:
        with self._data_lock:
            self.on_rows_changed(self.task_repository.get())

        view_order = self.sort_controller.build_view_order()
        self.table_manager.display(reload_from_file=False, view_order=view_order)
        self.row_highlighter.set_view_order(view_order)
        self.row_highlighter.highlight_expired_unloads()
        self.row_highlighter.reapply_from_rows()

    def on_header_clicked(self, logical_index: int) -> None:
        if logical_index == 0:
            self.open_id_manager()
            return

        sort_by = {2: None, 8: "buffer", 7: "arrival"}.get(logical_index, ...)
        if sort_by is ...:
            return
        self.sort_controller.current = sort_by
        self.reload_and_show()

    @staticmethod
    def _use_incremental_refresh() -> bool:
        return os.getenv("NAV_API_INCREMENTAL_REFRESH", "").strip().lower() in {"1", "true", "yes", "on"}
