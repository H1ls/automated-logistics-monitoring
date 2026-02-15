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

        g.processor = NavigationProcessor(
            data_context=g.data_context,
            logger=g.log,
            gsheet=g.gsheet,
            filepath=str(g.INPUT_FILEPATH),  # см. шаг 2, как прокинем
            display_callback=g.reload_and_show,
            single_row=g._single_row_processing,
            updated_rows=g.updated_rows,
            executor=g.executor,
            highlight_callback=g.row_highlighter.highlight_for,
            browser_rect=getattr(g, "browser_rect", None))

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
