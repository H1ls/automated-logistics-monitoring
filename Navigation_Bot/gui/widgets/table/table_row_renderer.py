from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QTableWidgetItem, QPushButton, QWidget, QHBoxLayout, QLabel, )
from PyQt6.QtCore import Qt

from Navigation_Bot.core.domain.task_identity import row_identity_for_gui


class TableRowRenderer:
    """
    Отвечает за отрисовку одной обычной строки таблицы.
    Не знает про сохранение данных и workflow.
    """
    DEFAULT_FUTURE_LOAD_THRESHOLD_HOURS: int = 3

    def __init__(self, *, table, log_func, formatter, row_action_controller, on_row_click, on_edit_id_click, ):

        self.table = table
        self.log = log_func
        self.formatter = formatter
        self.row_action_controller = row_action_controller
        self.on_row_click = on_row_click
        self.on_edit_id_click = on_edit_id_click
        self.future_load_highlight_enabled = True
        self.future_load_threshold_hours = self.DEFAULT_FUTURE_LOAD_THRESHOLD_HOURS

    def apply_settings(self, settings: dict):
        highlight = settings.get("highlight", {}) or {}
        enabled_types = highlight.get("enabled_types")
        if isinstance(enabled_types, list):
            self.future_load_highlight_enabled = "future_load" in {str(v) for v in enabled_types}
        else:
            self.future_load_highlight_enabled = True

        try:
            self.future_load_threshold_hours = max(0, int(highlight.get("future_load_threshold_hours",
                                                                        self.DEFAULT_FUTURE_LOAD_THRESHOLD_HOURS)))
        except (TypeError, ValueError):
            self.future_load_threshold_hours = self.DEFAULT_FUTURE_LOAD_THRESHOLD_HOURS

    def render_row(self, *, row_idx: int, row: dict, real_idx: int):
        self.table.insertRow(row_idx)
        self._render_row_actions(row_idx, row, real_idx)
        self._render_row_id_cell(row_idx, row, real_idx)
        self._render_row_main_cells(row_idx, row)
        self._render_row_route_cells(row_idx, row)
        self._highlight_future_load(row_idx, row)

    def _set_cell(self, row: int, col: int, value, editable: bool = False):
        item = QTableWidgetItem("" if value is None else str(value))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if not editable:
            item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    def _set_readonly_cell(self, row: int, col: int, value):
        item = QTableWidgetItem("" if value is None else str(value))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, col, item)

    def _render_row_actions(self, row_idx: int, row: dict, real_idx: int):
        btn = QPushButton("▶" if row.get("id") else "🛠", self.table)

        row_identity = row_identity_for_gui(row)
        self.row_action_controller.register_button(row_identity, btn)

        if not row.get("id"):
            btn.setStyleSheet("color: red;")
            btn.clicked.connect(lambda _=False, idx=real_idx: self.on_edit_id_click(idx))
        else:
            btn.clicked.connect(lambda _=False, idx=real_idx: self.on_row_click(idx))

        self.table.setCellWidget(row_idx, 0, btn)

    def _render_row_id_cell(self, row_idx: int, row: dict, real_idx: int):
        id_value = str(row.get("id", ""))
        container = QWidget(self.table)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(id_value, container)
        btn_tool = QPushButton("🛠", container)
        btn_tool.setFixedWidth(30)
        btn_tool.clicked.connect(lambda _=False, idx=real_idx: self.on_edit_id_click(idx))

        layout.addWidget(label)
        layout.addWidget(btn_tool)
        layout.addStretch()
        self.table.setCellWidget(row_idx, 1, container)

    def _render_row_main_cells(self, row_idx: int, row: dict):
        if isinstance(row.get("loads"), list) or isinstance(row.get("unloads"), list):
            self._render_row_main_cells_view(row_idx, row)
            return

        ts = row.get("ТС", "")
        phone = row.get("Телефон", "")
        self._set_cell(row_idx, 2, f"{ts}\n{phone}" if phone else ts, editable=True)

        self._set_cell(row_idx, 3, row.get("КА", ""), editable=True)
        self._set_cell(row_idx, 4, self.formatter.field_with_datetime(row,
                                                                      "Погрузка",
                                                                      separator_table=self.table,
                                                                      separator_col=4,
                                                                      ), )

        self._set_cell(row_idx, 5, self.formatter.unload_text_with_status(row,
                                                                          separator_table=self.table,
                                                                          separator_col=5,
                                                                          ), )

        self._set_cell(row_idx, 6, row.get("гео", ""))

    def _render_row_route_cells(self, row_idx: int, row: dict):
        route_estimate = row.get("route_estimate") if isinstance(row.get("route_estimate"), dict) else {}
        if route_estimate:
            self._set_readonly_cell(row_idx, 7, route_estimate.get("arrival_time", "—"))
            self._set_readonly_cell(row_idx, 8, route_estimate.get("time_buffer_text", "—"))
            return

        route = row.get("Маршрут", {}) or {}
        arrival = route.get("время прибытия", "—")
        buffer = self.formatter.route_buffer_text(route)

        self._set_readonly_cell(row_idx, 7, arrival)
        self._set_readonly_cell(row_idx, 8, buffer)

    def _render_row_main_cells_view(self, row_idx: int, row: dict):
        ts = row.get("vehicle_plate") or row.get("ТС", "")
        phone = row.get("driver_phone") or row.get("Телефон", "")
        self._set_cell(row_idx, 2, f"{ts}\n{phone}" if phone else ts, editable=True)

        self._set_cell(row_idx, 3, row.get("carrier_name") or row.get("КА", ""), editable=True)
        self._set_cell(
            row_idx,
            4,
            self.formatter.points_text(row.get("loads") or [], separator_table=self.table, separator_col=4),
        )
        self._set_cell(
            row_idx,
            5,
            self.formatter.unload_points_text_with_status(row, separator_table=self.table, separator_col=5),
        )

        navigation = row.get("navigation") if isinstance(row.get("navigation"), dict) else {}
        self._set_cell(row_idx, 6, navigation.get("geo_text") or row.get("гео", ""))

    def _highlight_future_load(self, row_idx: int, row: dict):
        if not self.future_load_highlight_enabled:
            return

        loads = row.get("loads")
        if isinstance(loads, list) and loads and isinstance(loads[0], dict):
            date_str = str(loads[0].get("date") or "")
            time_str = str(loads[0].get("time") or "")
            ts = row.get("vehicle_plate") or row.get("ТС", "—")
            self._highlight_future_load_by_datetime(row_idx, date_str, time_str, ts)
            return

        pg = row.get("Погрузка", [])
        if not (pg and isinstance(pg, list) and isinstance(pg[0], dict)):
            return

        date_str = pg[0].get("Дата 1", "")
        time_str = pg[0].get("Время 1", "")

        ts = row.get("ТС", "—")
        self._highlight_future_load_by_datetime(row_idx, date_str, time_str, ts)

    def _highlight_future_load_by_datetime(self, row_idx: int, date_str: str, time_str: str, ts: str):
        try:
            if time_str and time_str.count(":") == 1:
                time_str += ":00"
            dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")

            if dt > datetime.now() + timedelta(hours=self.future_load_threshold_hours):
                for col in range(self.table.columnCount()):
                    item = self.table.item(row_idx, col)
                    if item:
                        item.setBackground(QColor(210, 235, 255))
        except Exception:
            self.log(f"❗️Ошибка при анализе ДАТЫ/ВРЕМЕНИ у ТС: {ts} (строка {row_idx + 1})",
                     severity="error",
                     audience="user+",  )
