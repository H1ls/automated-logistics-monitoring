from PyQt6.QtGui import QShortcut, QKeySequence


class SignalsBinder:
    def __init__(self, gui):
        self.gui = gui



    def bind(self):
        gui = self.gui

        # таблица
        gui.table.cellDoubleClicked.connect(gui.table_manager.edit_cell_content)
        gui.table.itemChanged.connect(gui.table_manager.save_to_json_on_edit)

        # кнопки
        gui.btn_settings.clicked.connect(lambda: gui.settings_ui.exec())

        gui.btn_process_all.clicked.connect(gui.processor.process_all)
        gui.btn_refresh_table.clicked.connect(gui.reload_and_show)
        gui.btn_wialon.clicked.connect(gui._open_wialon)
        gui.btn_load_google.clicked.connect(gui._load_from_google)

        # лог
        gui.btn_clear_log.clicked.connect(gui.logger.clear)

        # настройки
        gui.settings_ui.settings_changed.connect(gui.settings_controller.on_settings_changed)

        # горячие клавиши

        QShortcut(QKeySequence("F11"), gui).activated.connect(gui.hotkeys.start)
        QShortcut(QKeySequence("F12"), gui).activated.connect(gui.hotkeys.stop)
        QShortcut(QKeySequence("Ctrl+F"), gui).activated.connect(gui._toggle_search_bar)
