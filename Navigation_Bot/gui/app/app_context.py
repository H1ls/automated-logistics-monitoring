from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any


@dataclass(slots=True)
class AppContext:
    """
    Контейнер зависимостей GUI. Убрать доступ через gui.* и оставлять только gui.ctx.*.
    """

    # --- данные / интеграции ---
    data_context: Any
    gsheet: Any

    # --- базовые application services ---
    tasks_service: Any
    task_edit_service: Any
    google_sync_service: Any

    # --- workflow services ---
    new_task_workflow_service: Any
    editable_field_workflow_service: Any
    address_edit_workflow_service: Any

    # --- UI / controllers ---
    settings_controller: Any
    settings_ui: Any
    table_manager: Any
    row_highlighter: Any
    processor: Any
    sort_controller: Any
    hotkeys: Any
    table_context_menu: Any

    # --- опционально ---
    ui_bridge: Optional[Any] = None