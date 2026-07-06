from __future__ import annotations

from Navigation_Bot.gui.app.address_edit_workflow_service import AddressEditWorkflowService
from Navigation_Bot.gui.app.app_context import AppContext
from Navigation_Bot.gui.controllers.table_context_menu_controller import TableContextMenuController
from Navigation_Bot.gui.controllers.task_table_controller import TaskTableController
from Navigation_Bot.gui.dialogs.combined_settings_dialog import CombinedSettingsDialog
from Navigation_Bot.gui.widgets.row_high_lighter import RowHighlighter
from Navigation_Bot.gui.widgets.table.table_manager import TableManager
from Navigation_Bot.gui.widgets.table_sort_controller import TableSortController
from Navigation_Bot.bots.google_sheets_manager import GoogleSheetsManager
from Navigation_Bot.core.application.services.navigation.navigation_processor import NavigationProcessor
from Navigation_Bot.core.application.services.editable_field_workflow_service import EditableFieldWorkflowService
from Navigation_Bot.core.application.services.google.google_account_auth_service import GoogleAccountAuthService
from Navigation_Bot.core.application.services.google.google_navigation_writer import GoogleNavigationWriter
from Navigation_Bot.core.application.services.google.google_sync_service import GoogleSyncService
from Navigation_Bot.core.application.services.new_task_workflow_service import NewTaskWorkflowService
from Navigation_Bot.core.application.services.task_edit_service import TaskEditService
from Navigation_Bot.core.application.services.tasks_service import TasksService
from Navigation_Bot.core.infrastructure.api.api_client import NavigationApiClient
from Navigation_Bot.core.database_config import DatabaseConfig
from Navigation_Bot.gui.services.hotkey_manager import HotkeyManager
from Navigation_Bot.core.repositories.api_task_repository import ApiTaskRepository
from Navigation_Bot.core.repositories.api_vehicle_repository import ApiVehicleRepository
from Navigation_Bot.core.settings.settings_controller import SettingsController
from Navigation_Bot.core.application.services.api_history_services import (ApiNavigationHistoryService,
                                                                           ApiNoteHistoryService,
                                                                           ApiRouteEstimateHistoryService,
                                                                           ApiStatusEventService)


class AppServices:
    """
    Composition root GUI-приложения:
    собирает зависимости, связывает их и возвращает AppContext.
    """

    def __init__(self, gui):
        self.gui = gui

    def build(self) -> AppContext:
        self._build_data_layer()
        self._build_settings_layer()
        self._build_google_and_services()
        self._build_table_layer()
        self._build_processing_layer()
        self._build_ui_controllers()
        self._wire_components()
        return self.gui.ctx

    def _build_data_layer(self) -> None:
        g = self.gui
        c = g.ctx
        g.database_config = DatabaseConfig.from_env()
        g.loading.show("Initializing data context...", "FastAPI")
        api_key = getattr(g, "session_api_key", "") or g.database_config.api_key
        c.api_client = NavigationApiClient(g.database_config.api_base_url,
                                           api_key=api_key)
        g.api_user = self._load_api_user()
        g.log(f"API user: {g.api_user.get('username', '')} ({g.api_user.get('role', '')})")
        self._apply_role_permissions()
        c.vehicle_repository = ApiVehicleRepository(c.api_client, log=g.log)
        c.task_repository = ApiTaskRepository(c.api_client, log=g.log)
        c.task_repository.set_source_key(g._get_sheet_source_key())

    def _apply_role_permissions(self) -> None:
        g = self.gui
        role = (g.api_user.get("role") or "").strip().lower()
        can_write = role in {"admin", "dispatcher"}
        can_admin = role == "admin"

        for attr in ("btn_load_google", "btn_create_race", "btn_process_all"):
            button = getattr(g.ui, attr, None)
            if button:
                button.setEnabled(can_write)
        for attr in ("action_load_google", "action_create_race", "action_process_all"):
            action = getattr(g.ui, attr, None)
            if action:
                action.setEnabled(can_write)
        g.ui.btn_admin_users.setVisible(can_admin)
        if getattr(g.ui, "action_admin_users", None):
            g.ui.action_admin_users.setVisible(can_admin)

    def _load_api_user(self) -> dict:
        response = self.gui.ctx.api_client.get("/api/v1/me")
        user = response.get("user", {}) if isinstance(response, dict) else {}
        return user if isinstance(user, dict) else {}

    def _build_settings_layer(self) -> None:
        g = self.gui
        c = g.ctx
        g.loading.show("Инициализация настроек...", "Подготовка диалога настроек")

        c.settings_controller = SettingsController(g)
        c.settings_ui = CombinedSettingsDialog(g)

    def _build_google_and_services(self) -> None:
        g = self.gui
        c = g.ctx
        g.loading.show("Инициализация Google Sheets...", "Подготовка к загрузке")

        c.gsheet = GoogleSheetsManager(log_func=None)
        c.gsheet.started.connect(lambda: g.loading.show("Загрузка из Google Sheets..."))
        c.gsheet.finished.connect(g.hide_loading)
        c.gsheet.error.connect(lambda err: (g.hide_loading(), g.log(f"Ошибка: {err}")))
        c.gsheet.log_message.connect(g.log)
        c.google_navigation_writer = GoogleNavigationWriter(gsheet=c.gsheet, log=g.log)
        c.google_account_auth_service = GoogleAccountAuthService(gsheet=c.gsheet, log=g.log)

        g.loading.show("Инициализация сервисов задач...", "Подготовка")
        c.task_edit_service = TaskEditService(log=g.log)
        c.status_event_service = ApiStatusEventService(c.api_client, log=g.log)
        c.tasks_service = TasksService(task_repository=c.task_repository,
                                       log=g.log,
                                       status_event_service=c.status_event_service)

        c.google_sync_service = GoogleSyncService(gsheet=c.gsheet,
                                                  google_writer=c.google_navigation_writer,
                                                  tasks_service=c.tasks_service,
                                                  task_repository=c.task_repository,
                                                  vehicle_repository=c.vehicle_repository,
                                                  log=g.log)
        c.navigation_history_service = ApiNavigationHistoryService(c.api_client, log=g.log)
        c.route_estimate_history_service = ApiRouteEstimateHistoryService(c.api_client, log=g.log)
        c.note_history_service = ApiNoteHistoryService(c.api_client, log=g.log)

        c.new_task_workflow_service = NewTaskWorkflowService(tasks_service=c.tasks_service,
                                                             task_edit_service=c.task_edit_service,
                                                             google_sync_service=c.google_sync_service,
                                                             log=g.log)

        c.editable_field_workflow_service = EditableFieldWorkflowService(tasks_service=c.tasks_service,
                                                                         log=g.log)
        c.address_edit_workflow_service = AddressEditWorkflowService(task_repository=c.task_repository,
                                                                     tasks_service=c.tasks_service,
                                                                     task_edit_service=c.task_edit_service,
                                                                     log=g.log)

    def _build_table_layer(self) -> None:
        g = self.gui
        c = g.ctx
        g.loading.show("Инициализация таблицы...", "Создание менеджера таблицы")

        c.table_manager = TableManager(table_widget=g.ui.table,
                                       task_repository=c.task_repository,
                                       log_func=g.log,
                                       on_row_click=None,
                                       on_edit_id_click=g.actions.open_id_editor,
                                       editable_field_workflow=c.editable_field_workflow_service,
                                       address_edit_workflow=c.address_edit_workflow_service,
                                       reload_callback=g.reload_and_show)

        c.row_highlighter = RowHighlighter(table=g.ui.table,
                                           task_repository=c.task_repository,
                                           log=g.log,
                                           hours_default=2)

    def _build_processing_layer(self) -> None:
        g = self.gui
        c = g.ctx
        g.loading.show("Инициализация процессора...", "Подготовка браузера и обработчика")

        from Navigation_Bot.gui.dialogs.pause_between_rows_dialog import PauseBetweenRowsDialog

        c.processor = NavigationProcessor(task_repository=c.task_repository,
                                          logger=g.log,
                                          gsheet=c.google_navigation_writer,
                                          display_callback=g.reload_and_show,
                                          single_row=g._single_row_processing,
                                          updated_rows=g.updated_rows,
                                          executor=g.executor,
                                          highlight_callback=c.row_highlighter.highlight_for,
                                          browser_rect=getattr(g, "browser_rect", None),
                                          ui_bridge=c.ui_bridge,
                                          tasks_service=c.tasks_service,
                                          navigation_history_service=c.navigation_history_service,
                                          route_estimate_history_service=c.route_estimate_history_service,
                                          pause_dialog_factory=PauseBetweenRowsDialog,
                                          gui_parent=g)
        c.settings_controller.apply_processing_settings()

    def _build_ui_controllers(self) -> None:
        g = self.gui
        c = g.ctx
        g.loading.show("Инициализация контроллеров...", "Подготовка сортировки и горячих клавиш")

        c.sort_controller = TableSortController(task_repository=c.task_repository, log=g.log)
        c.hotkeys = HotkeyManager(log_func=g.log)
        c.task_table_controller = TaskTableController(task_repository=c.task_repository,
                                                      sort_controller=c.sort_controller,
                                                      table_manager=c.table_manager,
                                                      row_highlighter=c.row_highlighter,
                                                      on_rows_changed=lambda rows: setattr(g, "task_rows", rows),
                                                      open_id_manager=g.actions.open_id_manager )

        g.loading.show("Инициализация меню...", "Подготовка контекстного меню")
        c.table_context_menu = TableContextMenuController(gui=g,
                                                          tasks_service=c.tasks_service,
                                                          google_sync_service=c.google_sync_service)
        c.table_context_menu.install()

    def _wire_components(self) -> None:
        g = self.gui
        c = g.ctx

        c.row_highlighter.set_key_to_visual_mapper(c.table_manager.visual_row_by_row_identity)

        c.table_manager.set_on_row_click(c.processor.on_row_click)

        def _after_display():
            c.row_highlighter.reapply_from_rows()
            c.row_highlighter.highlight_expired_unloads()
            c.row_highlighter.highlight_completed_rows()

        c.table_manager.after_display = _after_display

    def shutdown(self):
        g = self.gui
        c = g.ctx

        try:
            g.ui_settings.save_window(g)
        except Exception as e:
            g.log(f"Не удалось сохранить настройки окна: {e}")

        try:
            if hasattr(c, "hotkeys"):
                c.hotkeys.stop()
        except Exception as e:
            g.log(f"Не удалось остановить hotkeys: {e}")

        try:
            if getattr(g, "executor", None):
                g.executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            g.log(f"Не удалось остановить executor: {e}")

        try:
            proc = c.processor if hasattr(c, "processor") else None
            browser_session = getattr(proc, "browser_session", None) if proc else None

            if browser_session and hasattr(browser_session, "stop"):
                browser_session.stop()
        except Exception as e:
            g.log(f"Не удалось закрыть браузер: {e}")
