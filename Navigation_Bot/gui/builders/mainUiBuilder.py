from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QPushButton, QTextEdit,
    QLabel, QHeaderView, QAbstractItemView, QTableWidgetItem, QToolButton, QMenu,
    QStackedWidget
)
from PyQt6.QtGui import QGuiApplication

from PyQt6.QtCore import Qt

from Navigation_Bot.gui.widgets.smooth_scroll import SmoothScrollController
from Navigation_Bot.gui.widgets.globalSearchBar import GlobalSearchBar
from Navigation_Bot.gui.controllers.logController import LogController


class MainUiBuilder:
    def build(self, gui):
        """
        Собирает UI и заполняет gui.* полями:
        - кнопки
        - table
        - search_bar
        - log_box + logger + gui.log
        - stack/page_gsheet
        - sheet_tabs_layout
        """
        layout = QVBoxLayout()
        top = QHBoxLayout()

        # --- Верхние кнопки ---
        gui.btn_load_google = QPushButton("Загрузить Задачи")
        gui.btn_process_all = QPushButton("▶ Пробежать все ТС")
        gui.btn_refresh_table = QPushButton("🔄 Обновить")
        gui.btn_settings = QPushButton("Настройки ⚙️")

        for btn in [gui.btn_load_google, gui.btn_process_all, gui.btn_refresh_table, gui.btn_settings]:
            btn.setFixedHeight(28)
            btn.setFixedWidth(130)

        top.addWidget(gui.btn_load_google)
        top.addWidget(gui.btn_process_all)
        top.addWidget(gui.btn_refresh_table)
        top.addWidget(gui.btn_settings)

        # --- Таблица ---
        gui.table = QTableWidget()

        gui.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        gui.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        header = gui.table.horizontalHeader()
        header.setMinimumSectionSize(30)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        gui.table.verticalScrollBar().setSingleStep(20)
        gui.smooth_scroll = SmoothScrollController(gui.table, speed=0.18)

        gui.table.setColumnCount(9)

        gui.table.setHorizontalHeaderLabels([
            "", "id", "ТС", "КА", "Погрузка", "Выгрузка", "гео", "Время прибытия", "Запас"
        ])
        gui.table.setHorizontalHeaderItem(0, QTableWidgetItem("🔍"))

        hdr = gui.table.horizontalHeader()
        hdr.setSectionsClickable(True)
        hdr.sectionClicked.connect(gui._on_header_clicked)

        gui.table.setWordWrap(True)

        gui.table.setColumnWidth(0, 40)
        gui.table.setColumnWidth(1, 40)   # id
        gui.table.setColumnWidth(2, 82)   # ТС
        gui.table.setColumnWidth(3, 30)   # КА
        gui.table.setColumnWidth(4, 270)  # Погрузка
        gui.table.setColumnWidth(5, 275)  # Выгрузка
        gui.table.setColumnWidth(6, 168)  # гео
        gui.table.setColumnWidth(7, 65)   # Время прибытия
        gui.table.setColumnWidth(8, 60)   # Запас

        gui.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        gui.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        gui.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)

        gui.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        gui.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        gui.table.setColumnHidden(1, True)

        # --- Панель глобального поиска ---
        gui.search_bar = GlobalSearchBar(gui.table, gui.log, gui)
        gui.search_bar.hide()

        # --- Лог ---
        gui.log_box = QTextEdit()
        gui.log_box.setReadOnly(True)
        gui.log_box.setFixedHeight(150)

        # создаём LogController и ПЕРЕКИДЫВАЕМ gui.log на UI-лог
        gui.logger = LogController(gui.log_box, enabled_getter=lambda: gui._log_enabled)
        gui.log = gui.logger.log

        # --- Шапка лога (Лог + очистка) ---
        log_header = QHBoxLayout()
        log_label = QLabel("Лог:")
        gui.btn_clear_log = QPushButton("Очистить лог")
        gui.btn_clear_log.setFixedHeight(24)
        gui.btn_clear_log.setFixedWidth(120)
        log_header.addWidget(log_label)
        log_header.addStretch()
        log_header.addWidget(gui.btn_clear_log)

        # --- Страницы (Google + локальные) ---
        gui.stack = QStackedWidget()

        gui.page_gsheet = QWidget()
        page_layout = QVBoxLayout(gui.page_gsheet)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(gui.table)

        gui.stack.addWidget(gui.page_gsheet)

        # --- Вкладки листов снизу ---
        gui.sheet_tabs_layout = QHBoxLayout()

        # --- Сборка главного layout ---
        layout.addLayout(top)
        layout.addWidget(gui.search_bar)
        layout.addWidget(gui.stack)
        layout.addLayout(gui.sheet_tabs_layout)
        layout.addLayout(log_header)
        layout.addWidget(gui.log_box)

        gui.setLayout(layout)
