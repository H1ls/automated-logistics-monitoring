from PyQt6.QtGui import QShortcut, QKeySequence


class SignalsBinder:
    def __init__(self, gui):
        self.gui = gui

    def bind(self):
        gui = self.gui

        # таблица
        gui.table.cellDoubleClicked.connect(gui.table_manager.edit_cell_content)
        gui.table.itemChanged.connect(gui.table_manager.save_table_item_on_edit)

        # кнопки
        gui.action_load_google.triggered.connect(gui.actions.load_from_google)
        gui.action_create_race.triggered.connect(gui.actions.open_create_race_dialog)
        gui.action_refresh_table.triggered.connect(gui.reload_and_show)
        gui.action_process_all.triggered.connect(gui.actions.on_btn_process_all_clicked)
        gui.action_wialon.triggered.connect(gui.actions.open_wialon)
        gui.action_yandex_maps.triggered.connect(gui.actions.open_yandex_maps)
        gui.action_navigation_history.triggered.connect(gui.actions.open_navigation_history_dialog)
        gui.action_admin_users.triggered.connect(gui.actions.open_admin_users_dialog)
        gui.action_settings.triggered.connect(lambda: gui.settings_ui.exec())
        gui.chk_use_task_date_filter.toggled.connect(gui.date_task_from.setEnabled)
        gui.chk_use_task_date_filter.toggled.connect(gui.date_task_to.setEnabled)
        gui.chk_show_completed.toggled.connect(lambda checked: gui._ensure_completed_default_date_filter() if checked else None)
        gui.btn_apply_task_filter.clicked.connect(lambda: (gui.apply_task_filters(), gui.btn_task_filter.menu().hide()))
        gui.btn_cancel_task_filter.clicked.connect(lambda: gui.btn_task_filter.menu().hide())

        # лог
        gui.btn_clear_log.clicked.connect(gui.logger.clear)

        # настройки
        gui.settings_ui.settings_changed.connect(gui.settings_controller.on_settings_changed)

        # горячие клавиши
        QShortcut(QKeySequence("F11"), gui).activated.connect(gui.hotkeys.start)
        QShortcut(QKeySequence("F12"), gui).activated.connect(gui.hotkeys.stop)
        QShortcut(QKeySequence("F5"), gui).activated.connect(gui.reload_and_show)
        QShortcut(QKeySequence("Ctrl+F"), gui).activated.connect(gui._toggle_search_bar)
