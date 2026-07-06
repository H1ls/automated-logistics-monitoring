from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable, TYPE_CHECKING

from PyQt6.QtCore import QDate, QPoint, Qt
from PyQt6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QDateEdit, QHBoxLayout, QHeaderView, QLabel, QMenu,
                             QProgressBar, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit,
                             QVBoxLayout, QWidget, QWidgetAction)

from Navigation_Bot.gui.controllers.log_controller import LogController
from Navigation_Bot.gui.widgets.global_search_bar import GlobalSearchBar
from Navigation_Bot.gui.widgets.smooth_scroll import SmoothScrollController

if TYPE_CHECKING:
    from Navigation_Bot.gui.settings.ui_settings import UiSettingsManager


@dataclass(slots=True)
class MainUi:
    btn_tasks_menu: QPushButton
    btn_processing_menu: QPushButton
    btn_references_menu: QPushButton
    btn_load_google: QPushButton
    btn_create_race: QPushButton
    btn_process_all: QPushButton
    btn_refresh_table: QPushButton
    btn_wialon: QPushButton
    btn_settings: QPushButton
    btn_navigation_history: QPushButton
    btn_task_filter: QPushButton
    btn_admin_users: QPushButton
    btn_clear_log: QPushButton
    chk_show_completed: QCheckBox
    chk_use_task_date_filter: QCheckBox
    date_task_from: QDateEdit
    date_task_to: QDateEdit
    btn_apply_task_filter: QPushButton
    btn_cancel_task_filter: QPushButton
    action_load_google: QAction
    action_create_race: QAction
    action_refresh_table: QAction
    action_process_all: QAction
    action_wialon: QAction
    action_yandex_maps: QAction
    action_navigation_history: QAction
    action_admin_users: QAction
    action_settings: QAction
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
    @staticmethod
    def _search_icon() -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#2f6f9f"), 1.6))
        painter.drawEllipse(3, 3, 7, 7)
        painter.drawLine(9, 9, 13, 13)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _filter_icon() -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#2f3a45"), 1.4))
        painter.setBrush(QBrush(QColor("#2f3a45")))
        painter.drawPolygon(QPoint(2, 3), QPoint(14, 3), QPoint(9, 8), QPoint(9, 13), QPoint(7, 14), QPoint(7, 8))
        painter.end()
        return QIcon(pixmap)

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
        ui.btn_tasks_menu = QPushButton("Задачи")
        ui.btn_processing_menu = QPushButton("Обработка")
        ui.btn_references_menu = QPushButton("Справочники")
        ui.btn_load_google = QPushButton("Загрузить Задачи")
        ui.btn_create_race = QPushButton("Создать рейс")
        ui.btn_process_all = QPushButton("Пробежать все ТС")
        ui.btn_refresh_table = QPushButton("Обновить")
        ui.btn_wialon = QPushButton("Wialon")
        ui.btn_settings = QPushButton("Настройки")
        ui.btn_navigation_history = QPushButton("История")
        ui.btn_task_filter = QPushButton("")
        ui.btn_task_filter.setIcon(self._filter_icon())
        ui.btn_task_filter.setToolTip("Фильтр")
        ui.btn_admin_users = QPushButton("Пользователи")
        ui.btn_admin_users.setVisible(False)
        for btn in [ui.btn_tasks_menu,
                    ui.btn_processing_menu,
                    ui.btn_references_menu]:
            btn.setFixedHeight(28)
            btn.setFixedWidth(130)

        ui.btn_task_filter.setFixedSize(20, 24)

        tasks_menu = QMenu(ui.btn_tasks_menu)
        ui.action_load_google = tasks_menu.addAction("Загрузить задачи")
        ui.action_create_race = tasks_menu.addAction("Создать рейс")
        ui.action_refresh_table = tasks_menu.addAction("Обновить")
        ui.btn_tasks_menu.setMenu(tasks_menu)

        processing_menu = QMenu(ui.btn_processing_menu)
        ui.action_process_all = processing_menu.addAction("Пробежать все ТС")
        ui.action_wialon = processing_menu.addAction("Wialon")
        ui.action_yandex_maps = processing_menu.addAction("Я.Карты")
        ui.btn_processing_menu.setMenu(processing_menu)

        references_menu = QMenu(ui.btn_references_menu)
        ui.action_navigation_history = references_menu.addAction("История")
        ui.action_admin_users = references_menu.addAction("Пользователи")
        ui.action_settings = references_menu.addAction("Настройки")
        ui.btn_references_menu.setMenu(references_menu)

        top.addWidget(ui.btn_tasks_menu)
        top.addWidget(ui.btn_processing_menu)
        top.addWidget(ui.btn_references_menu)
        top.addStretch()
        top.addWidget(ui.btn_task_filter)

        ui.chk_show_completed = QCheckBox("Завершённые")
        ui.chk_use_task_date_filter = QCheckBox("Даты")
        ui.date_task_from = QDateEdit()
        ui.date_task_to = QDateEdit()
        for date_edit in (ui.date_task_from, ui.date_task_to):
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("dd.MM.yyyy")
            date_edit.setFixedWidth(105)
            date_edit.setEnabled(False)
        ui.date_task_from.setDate(QDate.currentDate().addDays(-7))
        ui.date_task_to.setDate(QDate.currentDate())
        ui.btn_cancel_task_filter = QPushButton("Отмена")
        ui.btn_apply_task_filter = QPushButton("OK")
        ui.btn_apply_task_filter.setFixedHeight(24)
        ui.btn_apply_task_filter.setFixedWidth(42)
        ui.btn_apply_task_filter.setStyleSheet("background: #167a3a; color: white; font-weight: 600;")
        ui.btn_cancel_task_filter.setFixedHeight(24)
        ui.btn_cancel_task_filter.setFixedWidth(70)

        filter_menu = QMenu(ui.btn_task_filter)
        filter_menu.setStyleSheet("""
            QMenu {
                background: #f4f4f4;
                border: 1px solid #c7c7c7;
            }
        """)
        filter_panel = QWidget(filter_menu)
        filter_panel.setMinimumWidth(120)
        filter_layout = QVBoxLayout(filter_panel)
        filter_layout.setContentsMargins(6, 6, 6, 6)
        filter_layout.setSpacing(7)
        filter_layout.addWidget(ui.chk_show_completed)
        filter_layout.addWidget(ui.chk_use_task_date_filter)
        filter_layout.addWidget(ui.date_task_from)
        filter_layout.addWidget(ui.date_task_to)

        filter_buttons = QHBoxLayout()
        filter_buttons.setContentsMargins(0, 0, 0, 0)
        filter_buttons.addWidget(ui.btn_cancel_task_filter)
        filter_buttons.addWidget(ui.btn_apply_task_filter)
        filter_layout.addLayout(filter_buttons)

        filter_action = QWidgetAction(filter_menu)
        filter_action.setDefaultWidget(filter_panel)
        filter_menu.addAction(filter_action)
        ui.btn_task_filter.setMenu(filter_menu)

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
        ui.table.setHorizontalHeaderLabels(
            ["", "id", "ТС", "КА", "Погрузка", "Выгрузка", "гео", "Время прибытия", "Запас"]
        )
        search_header = QTableWidgetItem("")
        search_header.setIcon(self._search_icon())
        ui.table.setHorizontalHeaderItem(0, search_header)

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
