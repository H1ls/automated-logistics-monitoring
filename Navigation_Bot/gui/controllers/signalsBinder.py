from PyQt6.QtGui import QShortcut, QKeySequence


class SignalsBinder:
    def __init__(self, gui):
        self.gui = gui

    def bind(self):
        g = self.gui

        # таблица
        g.table.cellDoubleClicked.connect(g.table_manager.edit_cell_content)
        g.table.itemChanged.connect(g.table_manager.save_to_json_on_edit)

        # кнопки
        g.btn_settings.clicked.connect(lambda: g.settings_ui.exec())
        g.btn_process_all.clicked.connect(g.processor.process_all)
        g.btn_refresh_table.clicked.connect(g.reload_and_show)
        g.btn_load_google.clicked.connect(g._load_from_google)

        # лог
        g.btn_clear_log.clicked.connect(g.logger.clear)

        # настройки
        g.settings_ui.settings_changed.connect(g.settings_controller.on_settings_changed)

        # горячие клавиши

        QShortcut(QKeySequence("F11"), g).activated.connect(g.hotkeys.start)
        QShortcut(QKeySequence("F12"), g).activated.connect(g.hotkeys.stop)
        QShortcut(QKeySequence("Ctrl+F"), g).activated.connect(g._toggle_search_bar)
