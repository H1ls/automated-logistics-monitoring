from __future__ import annotations

from Navigation_Bot.core.application.services.google_sync_service import GoogleSyncService
from Navigation_Bot.core.application.services.task_edit_service import TaskEditService
from Navigation_Bot.gui.app.appContext import AppContext
from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager
from Navigation_Bot.core.dataContext import DataContext
from Navigation_Bot.core.hotkeyManager import HotkeyManager
from Navigation_Bot.core.NavigationProcessor.navigationProcessor import NavigationProcessor
from Navigation_Bot.core.settings.SettingsController import SettingsController
from Navigation_Bot.core.application.services.tasks_service import TasksService
from Navigation_Bot.gui.controllers.tableContextMenuController import TableContextMenuController
from Navigation_Bot.gui.dialogs.combinedSettingsDialog import CombinedSettingsDialog
from Navigation_Bot.gui.widgets.rowHighlighter import RowHighlighter
from Navigation_Bot.gui.widgets.table.tableManager import TableManager
from Navigation_Bot.gui.widgets.tableSortController import TableSortController
from Navigation_Bot.core.application.services.new_task_workflow_service import NewTaskWorkflowService
from Navigation_Bot.core.application.services.editable_field_workflow_service import EditableFieldWorkflowService
from Navigation_Bot.core.application.services.address_edit_workflow_service import AddressEditWorkflowService

class AppServices:
    """
    Собирает все сервисы/менеджеры приложения и вешает их на gui.
    """

    def __init__(self, gui):
        self.gui = gui

    def build(self) -> AppContext:
        g = self.gui

        # --- DataContext ---
        g.show_loading("Инициализация контекста данных…", "Загрузка JSON")
        # g.logger = AppLogger(log_func=g.log)
        json_path = g._get_sheet_json_path()
        g.data_context = DataContext(json_path, log_func=g.log)
        g.json_data = g.data_context.get()  # совместимость

        # --- Settings ---
        g.show_loading("Инициализация настроек…", "Подготовка диалога настроек")
        g.settings_controller = SettingsController(g)
        g.settings_ui = CombinedSettingsDialog(g)

        # --- GoogleSheets ---
        g.show_loading("Инициализация Google Sheets…", "Подготовка к загрузке")
        g.gsheet = GoogleSheetsManager(log_func=None)
        g.gsheet.started.connect(lambda: g.show_loading("Загрузка из Google Sheets…"))
        g.gsheet.finished.connect(lambda: g.hide_loading())
        g.gsheet.error.connect(lambda err: (g.hide_loading(), g.log(f"❌ {err}")))

        g.gsheet.log_message.connect(g.log)
        g.show_loading("Инициализация сервиса задач…", "Подготовка")
        g.tasks_service = TasksService(data_context=g.data_context, log=g.log, )
        g.task_edit_service = TaskEditService(log=g.log, )
        g.google_sync_service = GoogleSyncService(gsheet=g.gsheet,
                                                  tasks_service=g.tasks_service,
                                                  data_context=g.data_context,
                                                  log=g.log, )
        g.new_task_workflow_service = NewTaskWorkflowService(tasks_service=g.tasks_service,
                                                             task_edit_service=g.task_edit_service,
                                                             log=g.log, )
        g.editable_field_workflow_service = EditableFieldWorkflowService(tasks_service=g.tasks_service,
                                                                         log=g.log, )
        g.address_edit_workflow_service = AddressEditWorkflowService(data_context=g.data_context,
                                                                     tasks_service=g.tasks_service,
                                                                     task_edit_service=g.task_edit_service,
                                                                     log=g.log,)
        # --- TableManager ---
        g.show_loading("Инициализация таблицы…", "Создание менеджера таблицы")
        g.table_manager = TableManager(table_widget=g.table,
                                       data_context=g.data_context,
                                       log_func=g.log,
                                       on_row_click=None,
                                       on_edit_id_click=g.open_id_editor,
                                       new_task_workflow=g.new_task_workflow_service,
                                       editable_field_workflow=g.editable_field_workflow_service,
                                       address_edit_workflow=g.address_edit_workflow_service,
                                       reload_callback=g.reload_and_show, )

        # --- Highlighter / Processor / Sort ---
        g.show_loading("Инициализация процессора…", "Подготовка браузера и обработчика")
        g.row_highlighter = RowHighlighter(table=g.table,
                                           data_context=g.data_context,
                                           log=g.log,
                                           hours_default=2)

        # busy_callback = g.table_manager.set_row_busy
        g.processor = NavigationProcessor(data_context=g.data_context,
                                          logger=g.log,
                                          gsheet=g.gsheet,
                                          filepath=str(g.INPUT_FILEPATH),
                                          display_callback=g.reload_and_show,
                                          single_row=g._single_row_processing,
                                          updated_rows=g.updated_rows,
                                          executor=g.executor,
                                          highlight_callback=g.row_highlighter.highlight_for,
                                          browser_rect=getattr(g, "browser_rect", None),
                                          ui_bridge=g.ui_bridge, )

        g.show_loading("Инициализация контроллеров…", "Подготовка сортировки и горячих клавиш")
        g.sort_controller = TableSortController(data_context=g.data_context,
                                                log=g.log)
        g.hotkeys = HotkeyManager(log_func=g.log)

        # --- Context menu ---
        g.show_loading("Инициализация меню…", "Подготовка контекстного меню")
        g.table_context_menu = TableContextMenuController(gui=g,
                                                          tasks_service=g.tasks_service,
                                                          google_sync_service=g.google_sync_service, )
        g.table_context_menu.install()

        # связи
        g.row_highlighter.set_key_to_visual_mapper(g.table_manager.visual_row_by_index_key)
        g.table_manager.on_row_click = g.processor.on_row_click
        g.table_manager.row_renderer.on_row_click = g.processor.on_row_click

        def _after_display():
            g.row_highlighter.reapply_from_json()
            g.row_highlighter.highlight_expired_unloads()

        g.table_manager.after_display = _after_display

        # Явный контекст зависимостей (чтобы дальше уходить от gui.* как глобального контейнера)
        g.show_loading("Завершение инициализации…", "Создание контекста зависимостей")
        ctx = AppContext(data_context=g.data_context,
                         # простые операции над задачами/JSON
                         tasks_service=g.tasks_service,
                         gsheet=g.gsheet,
                         settings_controller=g.settings_controller,
                         settings_ui=g.settings_ui,
                         table_manager=g.table_manager,
                         row_highlighter=g.row_highlighter,
                         processor=g.processor,
                         sort_controller=g.sort_controller,
                         hotkeys=g.hotkeys,
                         table_context_menu=g.table_context_menu,
                         ui_bridge=getattr(g, "ui_bridge", None), )

        # сохранить на gui для удобного доступа
        g.ctx = ctx
        return ctx

    def shutdown(self):
        g = self.gui

        # 1) сохранить настройки окна
        try:
            g.ui_settings.save_window(g)
        except Exception as e:
            g.log(f"⚠️ Не удалось сохранить настройки окна: {e}")

        # 2) остановить hotkeys
        try:
            if getattr(g, "hotkeys", None):
                g.hotkeys.stop()
        except Exception as e:
            g.log(f"⚠️ Не удалось остановить hotkeys: {e}")

        # 3) остановить executor
        try:
            if getattr(g, "executor", None):
                g.executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            g.log(f"⚠️ Не удалось остановить executor: {e}")

        # 4) закрыть Selenium через BrowserSession
        try:
            proc = getattr(g, "processor", None)
            browser_session = getattr(proc, "browser_session", None) if proc else None

            if browser_session and hasattr(browser_session, "stop"):
                browser_session.stop()
        except Exception as e:
            g.log(f"⚠️ Не удалось закрыть браузер: {e}")
