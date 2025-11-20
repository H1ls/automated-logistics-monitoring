from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QPushButton, QTextEdit,
                             QLabel, QHeaderView, QAbstractItemView, QTableWidgetItem, QToolButton, QMenu)
from PyQt6.QtGui import QShortcut, QKeySequence, QTextCursor, QAction, QGuiApplication

import re
from pathlib import Path
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager
from Navigation_Bot.bots.mapsBot import MapsBot
from Navigation_Bot.bots.navigationBot import NavigationBot

from Navigation_Bot.core.navigationProcessor import NavigationProcessor
from Navigation_Bot.core.paths import INPUT_FILEPATH
from Navigation_Bot.core.processedFlags import init_processed_flags
from Navigation_Bot.core.dataContext import DataContext
from Navigation_Bot.core.hotkeyManager import HotkeyManager
from Navigation_Bot.core.globalSearchBar import GlobalSearchBar
from Navigation_Bot.gui.combinedSettingsDialog import CombinedSettingsDialog
from Navigation_Bot.gui.trackingIdEditor import TrackingIdEditor
from Navigation_Bot.gui.tableManager import TableManager
from Navigation_Bot.gui.iDManagerDialog import IDManagerDialog
from Navigation_Bot.gui.UI.tableSortController import TableSortController
from Navigation_Bot.gui.UI.rowHighlighter import RowHighlighter


class NavigationGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Navigation Manager")
        self.resize(1050, 1033)

        self.executor = ThreadPoolExecutor(max_workers=1)
        self._single_row_processing = True
        self._log_enabled = True
        self._current_sort = None
        self.json_lock = Lock()

        self._row_highlight_until = {}  # {row_idx: datetime_until}

        self.updated_rows = []

        self.init_ui()
        self._setup_dual_screen_layout()
        self.init_managers()
        self.connect_signals()

        self.table_manager.display()

    def init_managers(self):
        json_path = self._get_sheet_json_path()
        self.data_context = DataContext(json_path, log_func=self.log)

        self.json_data = self.data_context.get()  # для обратной совместимости
        self.hotkeys = HotkeyManager(log_func=self.log)
        self.settings_ui = CombinedSettingsDialog(self)

        self.gsheet = GoogleSheetsManager()
        self.gsheet.log_message.connect(self.log)

        self.table_manager = TableManager(table_widget=self.table,
                                          data_context=self.data_context,
                                          log_func=self.log,
                                          on_row_click=None,
                                          on_edit_id_click=self.open_id_editor,
                                          gsheet=self.gsheet)

        self.row_highlighter = RowHighlighter(table=self.table,
                                              data_context=self.data_context,
                                              log=self.log,
                                              hours_default=2)
        self.processor = NavigationProcessor(data_context=self.data_context,
                                             logger=self.log,
                                             gsheet=self.gsheet,
                                             filepath=str(INPUT_FILEPATH),
                                             display_callback=self.reload_and_show,
                                             single_row=self._single_row_processing,
                                             updated_rows=self.updated_rows,
                                             executor=self.executor,
                                             highlight_callback=self.row_highlighter.highlight_for,
                                             browser_rect=getattr(self, "browser_rect", None)
                                             )
        self.sort_controller = TableSortController(data_context=self.data_context,
                                                   table_manager=self.table_manager,
                                                   log=self.log)

        self.table_manager.on_row_click = self.processor.on_row_click
        self.table_manager.after_display = self.row_highlighter.reapply_from_json
        self._build_sheet_tabs()

    def init_ui(self):
        layout = QVBoxLayout()
        top = QHBoxLayout()

        # Верхние кнопки
        self.btn_load_google = QPushButton("Загрузить Задачи")
        self.btn_process_all = QPushButton("▶ Пробежать все ТС")
        self.btn_refresh_table = QPushButton("🔄 Обновить")
        self.btn_settings = QPushButton("Настройки ⚙️")

        for btn in [
            self.btn_load_google,
            self.btn_process_all,
            self.btn_refresh_table,
            self.btn_settings
        ]:
            btn.setFixedHeight(28)
            btn.setFixedWidth(130)

        top.addWidget(self.btn_load_google)
        top.addWidget(self.btn_process_all)
        top.addWidget(self.btn_refresh_table)
        top.addWidget(self.btn_settings)
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "", "id", "ТС", "КА", "Погрузка", "Выгрузка", "гео", "Время прибытия", "Запас"])
        self.table.setHorizontalHeaderItem(0, QTableWidgetItem("🔍"))
        hdr = self.table.horizontalHeader()
        hdr.setSectionsClickable(True)
        hdr.sectionClicked.connect(self._on_header_clicked)

        self.table.setWordWrap(True)
        self.table.setColumnWidth(0, 40)  #
        self.table.setColumnWidth(1, 40)  # id
        self.table.setColumnWidth(2, 82)  # ТС
        self.table.setColumnWidth(3, 30)  # КА
        self.table.setColumnWidth(4, 270)  # Погрузка
        self.table.setColumnWidth(5, 275)  # Выгрузка
        self.table.setColumnWidth(6, 168)  # гео
        self.table.setColumnWidth(7, 65)  # Время прибытия
        self.table.setColumnWidth(8, 60)  # Запас
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.table.setColumnHidden(1, True)

        self.table.setColumnHidden(1, True)

        # 🔎 Панель глобального поиска
        self.search_bar = GlobalSearchBar(self.table, self.log, self)
        self.search_bar.hide()

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(150)

        # шапка лога Лог + кнопка очистки
        log_header = QHBoxLayout()
        log_label = QLabel("Лог:")
        self.btn_clear_log = QPushButton("Очистить лог")
        self.btn_clear_log.setFixedHeight(24)
        self.btn_clear_log.setFixedWidth(120)
        log_header.addWidget(log_label)
        log_header.addStretch()
        log_header.addWidget(self.btn_clear_log)

        layout.addLayout(top)
        layout.addWidget(self.search_bar)

        layout.addWidget(self.table)

        # Ряд кнопок-листов, как в Google Sheets
        self.sheet_tabs_layout = QHBoxLayout()
        layout.addLayout(self.sheet_tabs_layout)

        layout.addLayout(log_header)
        layout.addWidget(self.log_box)

        self.setLayout(layout)

    def _setup_dual_screen_layout(self):
        """
        Если есть второй монитор:
          - Navigation Manager встает в верхнюю половину второго монитора
          - сохраняем прямоугольник нижней половины для браузера
        """
        screens = QGuiApplication.screens()
        if len(screens) < 2:
            self.browser_rect = None
            return

        second = screens[1]  # берём второй экран (index=1)
        geom = second.geometry()

        half_h = geom.height() // 2

        titlebar_offset = 30
        self.setGeometry(
            geom.x(),
            geom.y() + titlebar_offset,
            geom.width(),
            half_h - titlebar_offset)

        self.browser_rect = {
            "x": geom.x(),
            "y": geom.y() + half_h,
            "width": geom.width(),
            "height": geom.height() - half_h, }

    def _load_from_google(self):
        """Загрузить задачи из текущего листа в свой json."""
        try:
            json_path = self._get_sheet_json_path()
            self.data_context.set_filepath(json_path)

            self.gsheet.pull_to_context_async(
                data_context=self.data_context,
                input_filepath=json_path,
                executor=self.executor
            )
            self.reload_and_show()
        except Exception as e:
            self.log(f'❌ Ошибка в NavigationGUI._load_from_google\n {e}')

    def _get_sheet_json_path(self) -> str:
        """
        Возвращает путь к json для текущего листа Google Sheets.
        Например: config/selected_data_3_Kontrol_TS.json
        """
        base = Path(INPUT_FILEPATH)

        if not getattr(self, "gsheet", None) or not getattr(self.gsheet, "sheet", None):
            return str(base)

        index = getattr(self.gsheet, "worksheet_index", 0) or 0
        title = getattr(self.gsheet.sheet, "title", f"sheet_{index}") or f"sheet_{index}"

        safe = re.sub(r"[^0-9A-Za-zА-Яа-я0-9]+", "_", title).strip("_")
        if not safe:
            safe = f"sheet_{index}"

        filename = f"{base.stem}_{index}_{safe}.json"
        return str(base.with_name(filename))

    def connect_signals(self):
        self.table.cellDoubleClicked.connect(self.table_manager.edit_cell_content)

        self.settings_ui.settings_changed.connect(self._on_settings_changed)

        self.btn_settings.clicked.connect(lambda: self.settings_ui.exec())
        self.btn_process_all.clicked.connect(self.processor.process_all)
        # self.btn_refresh_table.clicked.connect(self.table_manager.display)
        self.btn_refresh_table.clicked.connect(self.reload_and_show)
        self.table.itemChanged.connect(self.table_manager.save_to_json_on_edit)
        self.btn_clear_log.clicked.connect(self.clear_log)
        self.btn_load_google.clicked.connect(self._load_from_google)

        QShortcut(QKeySequence("F11"), self).activated.connect(self.hotkeys.start)
        QShortcut(QKeySequence("F12"), self).activated.connect(self.hotkeys.stop)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._toggle_search_bar)

    def _on_settings_changed(self, sections: set):
        if "google_config" in sections:
            self.gsheet = GoogleSheetsManager()
            self.gsheet.log_message.connect(self.log)
            self.log("🔁 GoogleSheetsManager пересоздан по новым настройкам")

        driver = getattr(getattr(self, "processor", None), "driver_manager", None)
        driver = getattr(driver, "driver", None)

        if "wialon_selectors" in sections and driver:
            self.processor.navibot = NavigationBot(driver, log_func=self.log)
            self.log("🔁 NavigationBot пересоздан")

        if "yandex_selectors" in sections:

            dm = getattr(self.processor, "driver_manager", None)
            if dm:
                self.processor.mapsbot = MapsBot(dm, log_func=self.log)
                self.log("🔁 MapsBot пересоздан")
            else:
                self.log("ℹ️ MapsBot обновится при запуске драйвера")

        if {"wialon_selectors", "yandex_selectors"} & sections and not driver:
            self.log("ℹ️ Селекторы применятся при старте веб-драйвера")

    def _on_sheet_button_clicked(self, index: int, clicked_btn: QPushButton):
        for btn in getattr(self, "_sheet_buttons", []):
            btn.setChecked(btn is clicked_btn)

        # переключили лист в менеджере
        self.gsheet.set_active_worksheet(index)

        # переключаем DataContext на json этого листа
        json_path = self._get_sheet_json_path()
        self.data_context.set_filepath(json_path)

        self.reload_and_show()

    def _toggle_search_bar(self):
        if self.search_bar.isVisible():
            self.search_bar.hide()
        else:
            self.search_bar.start()

    def clear_log(self):
        self.log_box.clear()

    def log(self, message: str):
        if not self._log_enabled:
            return

        text = str(message)
        lower = text.lower()
        color = None
        if text.startswith("❌") or "ошибка" in lower or "error" in lower:
            color = "red"
        elif text.startswith("✅") or "успеш" in lower or "успех" in lower:
            color = "green"
        elif text.startswith("⚠") or "предупр" in lower or "warning" in lower:
            color = "#c08000"

        if color:
            self.log_box.append(f'<span style="color:{color};">{text}</span>')
        else:
            self.log_box.append(text)

        # автоскролл
        cursor = self.log_box.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_box.setTextCursor(cursor)

    def reload_and_show(self):
        with self.json_lock:
            self.data_context.reload()
            self.json_data = self.data_context.get()  # обновляем локальный
            init_processed_flags(self.json_data, self.json_data, loads_key="Выгрузка")
            self.data_context.save()

        if self.sort_controller.current == "buffer":
            self.sort_controller.sort_by_buffer()
        elif self.sort_controller.current == "arrival":
            self.sort_controller.sort_by_arrival()
        self.table_manager.display()
        # print("reload_and_show/sort_by_buffer/sort_by_arrival")

    def _on_header_clicked(self, logicalIndex: int):
        if logicalIndex == 0:  # 🔍 — открыть справочник ID
            self.open_id_manager()
            return
        if logicalIndex == 2:  # ТС
            self.sort_controller.sort_default()
            return
        if logicalIndex == 8:  # Запас
            self.sort_controller.sort_by_buffer()
            return
        if logicalIndex == 7:  # Время прибытия
            self.sort_controller.sort_by_arrival()
            return

    def open_id_editor(self, row):
        car = self.json_data[row]
        dialog = TrackingIdEditor(car, log_func=self.log, parent=self)
        if dialog.exec():
            self.data_context.set(self.json_data)
            self.table_manager.display()

    def open_id_manager(self):
        dlg = IDManagerDialog(self)
        if dlg.exec():
            self.table_manager.display()
            self.log("✅ Id_car.json перезаписан")

    def _build_sheet_tabs(self):
        """Создаёт кнопки листов снизу, как в Google Sheets, + фильтр справа."""
        try:
            while self.sheet_tabs_layout.count():
                item = self.sheet_tabs_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

            if not getattr(self, "gsheet", None):
                return

            worksheets = self.gsheet.list_worksheets()
            if not worksheets:
                self.log("⚠️ Не удалось получить список листов Google Sheets.")
                return

            self._sheet_buttons = []
            self._sheet_buttons_by_index = {}

            current_index = getattr(self.gsheet, "worksheet_index", 0)

            for ws in worksheets:
                idx = ws["index"]
                title = ws["title"]

                btn = QPushButton(title)
                btn.setCheckable(True)

                # отметим активный лист
                if idx == current_index:
                    btn.setChecked(True)

                btn.clicked.connect(lambda _, sheet_idx=idx, b=btn: self._on_sheet_button_clicked(sheet_idx, b))

                self.sheet_tabs_layout.addWidget(btn)
                self._sheet_buttons.append(btn)
                self._sheet_buttons_by_index[idx] = btn

            # небольшой растягивающий спейсер перед выпадающим списком
            self.sheet_tabs_layout.addStretch()

            self.sheet_filter_button = QToolButton(self)
            self.sheet_filter_button.setText("Листы ▼")
            self.sheet_filter_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

            menu = QMenu(self)
            self._sheet_actions = {}

            for ws in worksheets:
                idx = ws["index"]
                title = ws["title"]

                act = QAction(title, self)
                act.setCheckable(True)
                act.setChecked(True)  # по умолчанию все видимы
                act.toggled.connect(
                    lambda checked, sheet_idx=idx: self._on_sheet_visibility_toggled(sheet_idx, checked))

                menu.addAction(act)
                self._sheet_actions[idx] = act

            self.sheet_filter_button.setMenu(menu)
            self.sheet_tabs_layout.addWidget(self.sheet_filter_button)
        except:
            print("_build_sheet_tabs")

    def _on_sheet_visibility_toggled(self, sheet_index: int, visible: bool):
        """Показать/скрыть кнопку листа через меню."""
        btn = getattr(self, "_sheet_buttons_by_index", {}).get(sheet_index)
        if not btn:
            return

        btn.setVisible(visible)

        if not visible and btn.isChecked():
            btn.setChecked(False)

            for other_idx, other_btn in getattr(self, "_sheet_buttons_by_index", {}).items():
                if other_btn.isVisible():
                    self._on_sheet_button_clicked(other_idx, other_btn)
                    break
