from __future__ import annotations

from Navigation_Bot.core.SettingsController import SettingsController
from Navigation_Bot.core.dataContext import DataContext
from Navigation_Bot.core.navigationProcessor import NavigationProcessor
from Navigation_Bot.gui.dialogs.combinedSettingsDialog import CombinedSettingsDialog
from Navigation_Bot.gui.controllers.tableContextMenuController import TableContextMenuController
from Navigation_Bot.gui.widgets.rowHighlighter import RowHighlighter
from Navigation_Bot.gui.widgets.tableManager import TableManager
from Navigation_Bot.gui.widgets.tableSortController import TableSortController
from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager
from Navigation_Bot.core.hotkeyManager import HotkeyManager


class AppServices:
    """
    Собирает все сервисы/менеджеры приложения и вешает их на gui.
    """

    def __init__(self, gui):
        self.gui = gui

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

        # 4) закрыть Selenium
        try:
            wdm = getattr(g, "driver_manager", None)

            if not wdm:
                proc = getattr(g, "processor", None)
                wdm = getattr(proc, "driver_manager", None) if proc else None

            if wdm and hasattr(wdm, "stop_browser"):
                wdm.stop_browser()
            elif wdm and getattr(wdm, "driver", None):
                try:
                    wdm.driver.quit()
                except Exception:
                    pass
                wdm.driver = None
        except Exception as e:
            g.log(f"⚠️ Не удалось закрыть браузер: {e}")

    def build(self):
        g = self.gui

        # --- DataContext ---
        json_path = g._get_sheet_json_path()
        g.data_context = DataContext(json_path, log_func=g.log)
        g.json_data = g.data_context.get()  # совместимость

        # --- Settings ---
        g.settings_controller = SettingsController(g)
        g.settings_ui = CombinedSettingsDialog(g)

        # --- GoogleSheets ---
        g.gsheet = GoogleSheetsManager(log_func=None)
        g.gsheet.started.connect(lambda: g.show_loading("Загрузка из Google Sheets…"))
        g.gsheet.finished.connect(lambda: g.hide_loading())
        g.gsheet.error.connect(lambda err: (g.hide_loading(), g.log(f"❌ {err}")))

        g.gsheet.log_message.connect(g.log)

        # --- TableManager ---
        g.table_manager = TableManager(
            table_widget=g.table,
            data_context=g.data_context,
            log_func=g.log,
            on_row_click=None,
            on_edit_id_click=g.open_id_editor,
            gsheet=g.gsheet,
            reload_callback=g.reload_and_show)

        # --- Highlighter / Processor / Sort ---
        g.row_highlighter = RowHighlighter(
            table=g.table,
            data_context=g.data_context,
            log=g.log,
            hours_default=2)
        busy_callback = g.table_manager.set_row_busy
        g.processor = NavigationProcessor(
            data_context=g.data_context,
            logger=g.log,
            gsheet=g.gsheet,
            filepath=str(g.INPUT_FILEPATH),
            display_callback=g.reload_and_show,
            single_row=g._single_row_processing,
            updated_rows=g.updated_rows,
            executor=g.executor,
            highlight_callback=g.row_highlighter.highlight_for,
            browser_rect=getattr(g, "browser_rect", None),
            ui_bridge=g.ui_bridge,)


        g.sort_controller = TableSortController(data_context=g.data_context, log=g.log)
        g.hotkeys = HotkeyManager(log_func=g.log)
        # --- Context menu ---
        g.table_context_menu = TableContextMenuController(gui=g)
        g.table_context_menu.install()

        # связи
        g.row_highlighter.set_key_to_visual_mapper(g.table_manager.visual_row_by_index_key)
        g.table_manager.on_row_click = g.processor.on_row_click

        def _after_display():
            g.row_highlighter.reapply_from_json()
            g.row_highlighter.highlight_expired_unloads()

        g.table_manager.after_display = _after_display
