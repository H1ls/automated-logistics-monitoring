# pet.project\Navigation_Bot\core\application\services\app_services.py
from __future__ import annotations

from Navigation_Bot.core.application.services.google_sync_service import GoogleSyncService
from Navigation_Bot.core.application.services.json_history_service import JsonHistoryService
from Navigation_Bot.core.application.services.task_edit_service import TaskEditService
from Navigation_Bot.gui.app.app_context import AppContext
from Navigation_Bot.bots.google_sheets_manager import GoogleSheetsManager
from Navigation_Bot.core.repositories.json_task_repository import JsonTaskRepository
from Navigation_Bot.core.hotkey_manager import HotkeyManager
from Navigation_Bot.core.NavigationProcessor.navigation_processor import NavigationProcessor
from Navigation_Bot.core.settings.settings_controller import SettingsController
from Navigation_Bot.core.application.services.tasks_service import TasksService
from Navigation_Bot.gui.controllers.table_context_menu_Controller import TableContextMenuController
from Navigation_Bot.gui.dialogs.combined_settings_dialog import CombinedSettingsDialog
from Navigation_Bot.gui.widgets.row_high_lighter import RowHighlighter
from Navigation_Bot.gui.widgets.table.table_manager import TableManager
from Navigation_Bot.gui.widgets.table_sort_controller import TableSortController
from Navigation_Bot.core.application.services.new_task_workflow_service import NewTaskWorkflowService
from Navigation_Bot.core.application.services.editable_field_workflow_service import EditableFieldWorkflowService
from Navigation_Bot.core.application.services.address_edit_workflow_service import AddressEditWorkflowService


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
        return self._build_context()

    def _build_data_layer(self) -> None:
        g = self.gui
        g.loading.show("Инициализация контекста данных…", "Загрузка JSON")

        json_path = g._get_sheet_json_path()
        g.task_repository = JsonTaskRepository(json_path, log_func=g.log)
        # g.task_repository = g.task_repository  # legacy alias

    def _build_settings_layer(self) -> None:
        g = self.gui
        g.loading.show("Инициализация настроек…", "Подготовка диалога настроек")

        g.settings_controller = SettingsController(g)
        g.settings_ui = CombinedSettingsDialog(g)

    def _build_google_and_services(self) -> None:
        g = self.gui
        g.loading.show("Инициализация Google Sheets…", "Подготовка к загрузке")

        g.gsheet = GoogleSheetsManager(log_func=None)
        g.gsheet.started.connect(lambda: g.loading.show("Загрузка из Google Sheets…"))
        g.gsheet.finished.connect(lambda: g.hide_loading())
        g.gsheet.error.connect(lambda err: (g.hide_loading(), g.log(f"❌ {err}")))
        g.gsheet.log_message.connect(g.log)

        g.loading.show("Инициализация сервисов задач…", "Подготовка")
        g.task_edit_service = TaskEditService(log=g.log, )
        g.status_event_service = JsonHistoryService(filepath="config/status_events.json",
                                                    time_field="created_at",
                                                    log=g.log, )
        g.tasks_service = TasksService(task_repository=g.task_repository,
                                       log=g.log,
                                       status_event_service=g.status_event_service, )

        g.google_sync_service = GoogleSyncService(gsheet=g.gsheet,
                                                  tasks_service=g.tasks_service,
                                                  task_repository=g.task_repository,
                                                  log=g.log, )
        # TODO: Убарть хардкод на filepath
        g.navigation_history_service = JsonHistoryService(filepath="config/navigation_history.json",
                                                          time_field="collected_at",
                                                          log=g.log, )

        g.route_estimate_history_service = JsonHistoryService(filepath="config/route_estimate_history.json",
                                                              time_field="calculated_at",
                                                              log=g.log, )
        g.note_history_service = JsonHistoryService(filepath="config/notes_history.json",
                                                    time_field="created_at",
                                                    log=g.log, )
        # -----
        g.new_task_workflow_service = NewTaskWorkflowService(tasks_service=g.tasks_service,
                                                             task_edit_service=g.task_edit_service,
                                                             google_sync_service=g.google_sync_service,
                                                             log=g.log, )

        g.editable_field_workflow_service = EditableFieldWorkflowService(tasks_service=g.tasks_service,
                                                                         log=g.log, )
        g.address_edit_workflow_service = AddressEditWorkflowService(task_repository=g.task_repository,
                                                                     tasks_service=g.tasks_service,
                                                                     task_edit_service=g.task_edit_service,
                                                                     log=g.log, )

    def _build_table_layer(self) -> None:
        g = self.gui
        g.loading.show("Инициализация таблицы…", "Создание менеджера таблицы")

        g.table_manager = TableManager(table_widget=g.table,
                                       task_repository=g.task_repository,
                                       log_func=g.log,
                                       on_row_click=None,
                                       on_edit_id_click=g.open_id_editor,
                                       # new_task_workflow=g.new_task_workflow_service,
                                       editable_field_workflow=g.editable_field_workflow_service,
                                       address_edit_workflow=g.address_edit_workflow_service,
                                       reload_callback=g.reload_and_show, )

        g.row_highlighter = RowHighlighter(table=g.table, task_repository=g.task_repository, log=g.log, hours_default=2, )

    def _build_processing_layer(self) -> None:
        g = self.gui
        g.loading.show("Инициализация процессора…", "Подготовка браузера и обработчика")

        g.processor = NavigationProcessor(task_repository=g.task_repository,
                                          logger=g.log,
                                          gsheet=g.gsheet,
                                          display_callback=g.reload_and_show,
                                          single_row=g._single_row_processing,
                                          updated_rows=g.updated_rows,
                                          executor=g.executor,
                                          highlight_callback=g.row_highlighter.highlight_for,
                                          browser_rect=getattr(g, "browser_rect", None),
                                          ui_bridge=g.ui_bridge,
                                          tasks_service=g.tasks_service,
                                          navigation_history_service=g.navigation_history_service,
                                          route_estimate_history_service=g.route_estimate_history_service,
                                          )

    def _build_ui_controllers(self) -> None:
        g = self.gui
        g.loading.show("Инициализация контроллеров…", "Подготовка сортировки и горячих клавиш")

        g.sort_controller = TableSortController(task_repository=g.task_repository, log=g.log, )
        g.hotkeys = HotkeyManager(log_func=g.log, )

        g.loading.show("Инициализация меню…", "Подготовка контекстного меню")
        g.table_context_menu = TableContextMenuController(gui=g,
                                                          tasks_service=g.tasks_service,
                                                          google_sync_service=g.google_sync_service, )
        g.table_context_menu.install()

    def _wire_components(self) -> None:
        g = self.gui

        g.row_highlighter.set_key_to_visual_mapper(g.table_manager.visual_row_by_index_key)

        g.table_manager.on_row_click = g.processor.on_row_click
        g.table_manager.row_renderer.on_row_click = g.processor.on_row_click

        def _after_display():
            g.row_highlighter.reapply_from_json()
            g.row_highlighter.highlight_expired_unloads()

        g.table_manager.after_display = _after_display

    def _build_context(self) -> AppContext:
        g = self.gui
        g.loading.show("Завершение инициализации…", "Создание контекста зависимостей")

        ctx = AppContext(task_repository=g.task_repository,
                         gsheet=g.gsheet,

                         tasks_service=g.tasks_service,
                         task_edit_service=g.task_edit_service,
                         google_sync_service=g.google_sync_service,

                         new_task_workflow_service=g.new_task_workflow_service,
                         editable_field_workflow_service=g.editable_field_workflow_service,
                         address_edit_workflow_service=g.address_edit_workflow_service,

                         settings_controller=g.settings_controller,
                         settings_ui=g.settings_ui,
                         table_manager=g.table_manager,
                         row_highlighter=g.row_highlighter,
                         processor=g.processor,
                         sort_controller=g.sort_controller,
                         hotkeys=g.hotkeys,
                         table_context_menu=g.table_context_menu,

                         ui_bridge=getattr(g, "ui_bridge", None), )

        g.ctx = ctx
        return ctx

    def shutdown(self):
        g = self.gui

        try:
            g.ui_settings.save_window(g)
        except Exception as e:
            g.log(f"⚠️ Не удалось сохранить настройки окна: {e}")

        try:
            if getattr(g, "hotkeys", None):
                g.hotkeys.stop()
        except Exception as e:
            g.log(f"⚠️ Не удалось остановить hotkeys: {e}")

        try:
            if getattr(g, "executor", None):
                g.executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            g.log(f"⚠️ Не удалось остановить executor: {e}")

        try:
            proc = getattr(g, "processor", None)
            browser_session = getattr(proc, "browser_session", None) if proc else None

            if browser_session and hasattr(browser_session, "stop"):
                browser_session.stop()
        except Exception as e:
            g.log(f"⚠️ Не удалось закрыть браузер: {e}")
