from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable, TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QHBoxLayout, QTableWidget, QPushButton, QTextEdit,
                             QHeaderView, QAbstractItemView, QTableWidgetItem, QStackedWidget, QWidget, QVBoxLayout,
                             QLabel, QProgressBar)

from Navigation_Bot.gui.controllers.log_controller import LogController
from Navigation_Bot.gui.widgets.global_search_bar import GlobalSearchBar
from Navigation_Bot.gui.widgets.smooth_scroll import SmoothScrollController

if TYPE_CHECKING:
    from Navigation_Bot.gui.settings.ui_settings import UiSettingsManager


@dataclass(slots=True)
class MainUi:
    btn_load_google: QPushButton
    btn_create_race: QPushButton
    btn_process_all: QPushButton
    btn_refresh_table: QPushButton
    btn_wialon: QPushButton
    btn_settings: QPushButton
    btn_navigation_history: QPushButton
    btn_admin_users: QPushButton
    btn_clear_log: QPushButton
    table: QTableWidget
    smooth_scroll: SmoothScrollController
    log_box: QTextEdit
    logger: LogController
    search_bar: GlobalSearchBar
    stack: QStackedWidget
    page_gsheet: QWidget
    loading_overlay: QWidget
    loading_card: QWidget
    loading_label: QLabel
    loading_bar: QProgressBar
    sheet_tabs_layout: QHBoxLayout


class MainUiBuilder:
    def build(
        self,
        parent: QWidget,
        *,
        ui_settings: UiSettingsManager,
        log_enabled_getter: Callable[[], bool],
        on_header_clicked: Callable[[int], None],
    ) -> MainUi:
        """
        Собирает и возвращает компоненты UI, не записывая их в parent.
        - кнопки
        - table
        - search_bar
        - log_box + logger + ui.log
        - stack/page_gsheet
        - sheet_tabs_layout
        """
        ui = SimpleNamespace()
        layout = QVBoxLayout()
        top = QHBoxLayout()

        # --- Верхние кнопки ---
        ui.btn_load_google = QPushButton("Загрузить Задачи")
        ui.btn_create_race = QPushButton("Создать рейс")
        ui.btn_process_all = QPushButton("▶ Пробежать все ТС")
        ui.btn_refresh_table = QPushButton("🔄 Обновить")
        ui.btn_wialon = QPushButton("Wialon 🌐")
        ui.btn_settings = QPushButton("Настройки ⚙️")
        ui.btn_navigation_history = QPushButton("История")
        ui.btn_admin_users = QPushButton("Пользователи")
        ui.btn_admin_users.setVisible(False)
        for btn in [ui.btn_load_google,
                    ui.btn_create_race,
                    ui.btn_process_all,
                    ui.btn_refresh_table,
                    ui.btn_wialon,
                    ui.btn_settings,
                    ui.btn_navigation_history,
                    ui.btn_admin_users,
                    ]:
            btn.setFixedHeight(28)
            btn.setFixedWidth(130)

        top.addWidget(ui.btn_load_google)
        top.addWidget(ui.btn_create_race)
        top.addWidget(ui.btn_process_all)
        top.addWidget(ui.btn_refresh_table)
        top.addWidget(ui.btn_wialon)
        top.addWidget(ui.btn_settings)
        top.addWidget(ui.btn_navigation_history)
        top.addWidget(ui.btn_admin_users)
        # --- Таблица ---
        ui.table = QTableWidget()

        ui.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        ui.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        header = ui.table.horizontalHeader()
        header.setMinimumSectionSize(30)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        ui.table.verticalScrollBar().setSingleStep(20)
        ui.smooth_scroll = SmoothScrollController(ui.table, speed=0.18)

        ui.table.setColumnCount(9)

        ui.table.setHorizontalHeaderLabels([
            "", "id", "ТС", "КА", "Погрузка", "Выгрузка", "гео", "Время прибытия", "Запас"])

        ui.table.setHorizontalHeaderItem(0, QTableWidgetItem("🔍"))

        hdr = ui.table.horizontalHeader()
        hdr.setSectionsClickable(True)
        hdr.sectionClicked.connect(on_header_clicked)

        ui.table.setWordWrap(True)

        ui.table.setColumnWidth(0, 40)
        ui.table.setColumnWidth(1, 40)  # id
        ui.table.setColumnWidth(2, 82)  # ТС
        ui.table.setColumnWidth(3, 30)  # КА
        ui.table.setColumnWidth(4, 270)  # Погрузка
        ui.table.setColumnWidth(5, 275)  # Выгрузка
        ui.table.setColumnWidth(6, 168)  # гео
        ui.table.setColumnWidth(7, 65)  # Время прибытия
        ui.table.setColumnWidth(8, 60)  # Запас

        ui.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        ui.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        ui.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)

        ui.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        ui.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        ui.table.setColumnHidden(1, True)

        # --- Лог ---
        ui.log_box = QTextEdit()
        ui.log_box.setReadOnly(True)
        ui.log_box.setFixedHeight(150)

        log_audience = (ui_settings.data.get("log", {}) or {}).get("audience", "user")
        ui.logger = LogController(ui.log_box, enabled_getter=log_enabled_getter, audience=log_audience)
        ui.log = ui.logger.log
        ui.log_info = ui.logger.info
        ui.log_success = ui.logger.success
        ui.log_warning = ui.logger.warning
        ui.log_error = ui.logger.error

        # --- Панель глобального поиска ---
        ui.search_bar = GlobalSearchBar(ui.table, ui.log, parent)
        ui.search_bar.hide()
        # --- Шапка лога (Лог + очистка) ---
        log_header = QHBoxLayout()
        log_label = QLabel("Лог:")
        ui.btn_clear_log = QPushButton("Очистить лог")
        ui.btn_clear_log.setFixedHeight(24)
        ui.btn_clear_log.setFixedWidth(120)

        log_header.addWidget(log_label)
        log_header.addStretch()
        log_header.addWidget(ui.btn_clear_log)

        # --- Страницы (Google + локальные) ---
        ui.stack = QStackedWidget()

        ui.page_gsheet = QWidget()
        page_layout = QVBoxLayout(ui.page_gsheet)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(ui.table)

        ui.loading_overlay = QWidget(ui.page_gsheet)
        ui.loading_overlay.setStyleSheet("""
            QWidget {
                background: transparent;
            }
        """)

        # Главный layout оверлея
        overlay_layout = QVBoxLayout(ui.loading_overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- Центральная карточка ---
        ui.loading_card = QWidget()
        ui.loading_card.setFixedSize(320, 90)
        ui.loading_card.setStyleSheet("""
            QWidget {
                background: #2c2c2c;
                border-radius: 12px;
            }
            QLabel {
                color: white;
                font-size: 13px;
            }
        """)

        card_layout = QVBoxLayout(ui.loading_card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setContentsMargins(20, 15, 20, 15)

        ui.loading_label = QLabel("Загрузка…")
        ui.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ui.loading_bar = QProgressBar()
        ui.loading_bar.setFixedWidth(240)
        ui.loading_bar.setRange(0, 0)

        card_layout.addWidget(ui.loading_label)
        card_layout.addWidget(ui.loading_bar)

        overlay_layout.addWidget(ui.loading_card)
        ui.loading_overlay.hide()

        # ______
        ui.stack.addWidget(ui.page_gsheet)

        # --- Вкладки листов снизу ---
        ui.sheet_tabs_layout = QHBoxLayout()

        # --- Сборка главного layout ---
        layout.addLayout(top)
        layout.addWidget(ui.search_bar)
        layout.addWidget(ui.stack)
        layout.addLayout(ui.sheet_tabs_layout)
        layout.addLayout(log_header)
        layout.addWidget(ui.log_box)

        parent.setLayout(layout)
        return MainUi(**{name: getattr(ui, name) for name in MainUi.__slots__})
