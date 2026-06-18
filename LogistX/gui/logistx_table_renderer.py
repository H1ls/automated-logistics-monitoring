from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QAbstractItemView, QPushButton, QTableWidget, QTableWidgetItem

from Navigation_Bot.core.sites_db_registry import SitesDbRegistry


class LogistXTableRenderer:
    COL_PLAY = 0
    COL_TS = 1
    COL_RACE = 2
    COL_FROM = 3
    COL_TO = 4
    COL_PLAN = 5
    COL_FACT = 6
    COL_STATUS = 7

    def __init__(self, table: QTableWidget, log_func: Callable[[str], None] | None = None):
        self.table = table
        self.log = log_func or print
        self.sites_db = SitesDbRegistry(log_func=self.log)
        self._on_play_clicked: Callable[[int], None] | None = None
        self._source_to_visual: dict[int, int] = {}

    def setup(self) -> None:
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["▶", "ТС", "Рейс", "Отправление",
                                              "Назначение", "План", "Факт Wialon", "Статус"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(header.ResizeMode.Fixed)

        self.table.setColumnWidth(self.COL_PLAY, 32)
        self.table.setColumnWidth(self.COL_TS, 95)
        self.table.setColumnWidth(self.COL_RACE, 100)
        self.table.setColumnWidth(self.COL_FROM, 260)
        self.table.setColumnWidth(self.COL_TO, 240)
        self.table.setColumnWidth(self.COL_PLAN, 75)
        self.table.setColumnWidth(self.COL_FACT, 115)
        self.table.setColumnWidth(self.COL_STATUS, 90)
        self.table.setWordWrap(True)

    def set_on_play_clicked(self, callback: Callable[[int], None]) -> None:
        self._on_play_clicked = callback

    def reload_sites_db(self) -> None:
        self.sites_db.reload()

    def render_rows(self, rows: list[dict]) -> None:
        self.render_entries(list(enumerate(rows)))

    def render_entries(self, entries: list[tuple[int, dict]]) -> None:
        scroll_value, selected_row = self._capture_view_state()

        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            self._source_to_visual.clear()
            for source_idx, obj in entries:
                self._render_row(source_idx, obj)
            self.table.resizeRowsToContents()
            self._highlight_missing_tags()
        finally:
            self.table.blockSignals(False)
            QTimer.singleShot(0, lambda: self._restore_view_state(scroll_value, selected_row))

    def update_address_cell(self, source_idx: int, col: int, address: str) -> None:
        row = self._source_to_visual.get(source_idx)
        if row is None:
            return

        geofence = self.resolve_geofence(address)
        text = self.format_tag_address(geofence, address)

        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem("")
            self.table.setItem(row, col, item)

        item.setText(text)
        self.table.resizeRowToContents(row)
        self._highlight_missing_tags()

    def mark_rows_pending_hide(self, source_indexes: set[int]) -> None:
        pending_brush = QColor(255, 242, 204)
        for source_idx in source_indexes:
            row = self._source_to_visual.get(source_idx)
            if row is None:
                continue
            for col in range(self.table.columnCount()):
                if col == self.COL_PLAY:
                    continue
                item = self.table.item(row, col)
                if item:
                    item.setBackground(pending_brush)

    def mark_hidden_rows(self, source_indexes: set[int]) -> None:
        self.mark_rows_pending_hide(source_indexes)

    def build_close_race_job(self, source_idx: int, rows: list[dict]) -> dict | None:
        if source_idx < 0 or source_idx >= len(rows):
            return None

        obj = rows[source_idx] or {}
        visual_row = self._source_to_visual.get(source_idx)
        if visual_row is None:
            from_text = self.format_tag_address(self.resolve_geofence(self._raw_from_address(obj)), self._raw_from_address(obj))
            to_text = self.format_tag_address(self.resolve_geofence(self._raw_to_address(obj)), self._raw_to_address(obj))
        else:
            from_text = self._cell_text(visual_row, self.COL_FROM)
            to_text = self._cell_text(visual_row, self.COL_TO)

        return {
            "row": int(source_idx),
            "obj": obj,
            "race_no": str(obj.get("Рейс", "") or "").strip(),
            "unit": str(obj.get("ТС", "") or "").strip(),
            "load_zone": self.geofence_from_cell_text(from_text),
            "unload_zone": self.geofence_from_cell_text(to_text),
        }

    def apply_close_race_result(self, source_idx: int, rows: list[dict], ctx, result: dict) -> bool:
        if source_idx < 0 or source_idx >= len(rows):
            return False

        obj = rows[source_idx] or {}

        state = getattr(ctx, "state", {}) or {}
        precheck = state.get("mini_wialon_precheck") or {}
        progress = state.get("onec_progress") or {}

        status_1c = str(state.get("close_status", "") or "")
        status_text = str(precheck.get("status_text", "") or "")
        precheck_payload = precheck.get("payload") or {}

        final_payload = {
            "load_in": getattr(ctx, "load_in", "") or "",
            "load_out": getattr(ctx, "load_out", "") or "",
            "unload_in": getattr(ctx, "unload_in", "") or "",
            "unload_out": getattr(ctx, "unload_out", "") or "",
        }

        if not any(final_payload.values()):
            final_payload = {
                "load_in": str(precheck_payload.get("load_in", "") or ""),
                "load_out": str(precheck_payload.get("load_out", "") or ""),
                "unload_in": str(precheck_payload.get("unload_in", "") or ""),
                "unload_out": str(precheck_payload.get("unload_out", "") or ""),
            }

        obj["status_1c"] = status_1c
        obj["status_text"] = status_text
        obj["departure_dt_1c"] = getattr(ctx, "departure_dt", "") or ""
        obj["wialon_payload"] = final_payload
        obj["onec_progress"] = progress
        obj["last_result"] = {
            "ok": bool(result.get("ok")),
            "stage": str(result.get("stage", "") or ""),
            "message": str(result.get("message", "") or ""),
        }

        visual_row = self._source_to_visual.get(source_idx)
        if visual_row is None:
            return True

        if result.get("ok"):
            fact_text = (
                f"Отправление: {getattr(ctx, 'departure_dt', '') or ''}\n"
                f"Погр(въезд): {getattr(ctx, 'load_in', '') or ''}\n"
                f"Погр(выезд): {getattr(ctx, 'load_out', '') or ''}\n"
                f"Выгр(въезд): {getattr(ctx, 'unload_in', '') or ''}\n"
                f"Выгр(выезд): {getattr(ctx, 'unload_out', '') or ''}"
            )
            self.table.setItem(visual_row, self.COL_FACT, QTableWidgetItem(fact_text))
        elif self.table.item(visual_row, self.COL_FACT) is None:
            self.table.setItem(visual_row, self.COL_FACT, QTableWidgetItem(""))

        status_map = {
            "in_transit": "Ещё в пути",
            "on_unload": "Ещё на выгрузке",
            "ready_to_close": "Можно закрывать",
            "closed": "Закрыт",
            "error": "Ошибка",
        }
        precheck_text = str(precheck.get("status_text", "") or "")
        result_message = str(result.get("message", "") or "")
        status = status_map.get(status_1c, "") or precheck_text or result_message
        self.table.setItem(visual_row, self.COL_STATUS, QTableWidgetItem(status or "—"))
        self.table.resizeRowToContents(visual_row)
        return True

    def resolve_geofence(self, address: str) -> str:
        return self.sites_db.resolve_geofence(address)

    @staticmethod
    def format_tag_address(geofence: str, address: str) -> str:
        geofence = (geofence or "").strip()
        address = (address or "").strip()
        if geofence:
            return f"🏷 {geofence}\n{address}"
        return address

    @staticmethod
    def geofence_from_cell_text(value: str) -> str:
        value = (value or "").strip()
        if value.startswith("🏷"):
            return value.splitlines()[0].replace("🏷", "").strip()
        return ""

    def _render_row(self, source_idx: int, obj: dict) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._source_to_visual[source_idx] = row

        btn = QPushButton("▶")
        btn.setFixedWidth(32)
        btn.clicked.connect(lambda _=False, idx=source_idx: self._emit_play_clicked(idx))
        self.table.setCellWidget(row, self.COL_PLAY, btn)

        addr_from = self._raw_from_address(obj)
        addr_to = self._raw_to_address(obj)

        values = [
            obj.get("ТС", ""),
            obj.get("Рейс", ""),
            self.format_tag_address(self.resolve_geofence(addr_from), addr_from),
            self.format_tag_address(self.resolve_geofence(addr_to), addr_to),
            obj.get("Плановая дата освобождения разгрузка", ""),
            "",
            "",
        ]

        for idx, value in enumerate(values):
            self.table.setItem(row, idx + 1, QTableWidgetItem(str(value)))

    def _emit_play_clicked(self, row: int) -> None:
        if self._on_play_clicked:
            self._on_play_clicked(row)

    def visual_row_for_source(self, source_idx: int) -> int | None:
        return self._source_to_visual.get(source_idx)

    @classmethod
    def _raw_from_address(cls, obj: dict) -> str:
        return cls._first_value(obj, "Рейс.Пункт отправления", "Пункт отправления", "Отправление")

    @classmethod
    def _raw_to_address(cls, obj: dict) -> str:
        return cls._first_value(obj, "Рейс.Пункт назначения", "Пункт назначения", "Назначение")

    @staticmethod
    def _first_value(obj: dict, *keys: str) -> str:
        for key in keys:
            value = obj.get(key)
            if value:
                return str(value)
        return ""

    def _highlight_missing_tags(self) -> None:
        pale_red = QColor(255, 220, 220)
        transparent = QColor(0, 0, 0, 0)

        for row in range(self.table.rowCount()):
            has_tags = self._row_has_tags(row)

            for col in range(self.table.columnCount()):
                if col == self.COL_PLAY:
                    continue

                item = self.table.item(row, col)
                if not item:
                    continue

                item.setBackground(transparent if has_tags else pale_red)

    def _row_has_tags(self, row: int) -> bool:
        return ("🏷" in self._cell_text(row, self.COL_FROM)) and ("🏷" in self._cell_text(row, self.COL_TO))

    def _cell_text(self, row: int, col: int) -> str:
        item = self.table.item(row, col)
        return item.text() if item else ""

    def _capture_view_state(self) -> tuple[int, int]:
        try:
            return self.table.verticalScrollBar().value(), self.table.currentRow()
        except Exception:
            return 0, -1

    def _restore_view_state(self, scroll_value: int, selected_row: int) -> None:
        try:
            self.table.verticalScrollBar().setValue(scroll_value)
            if 0 <= selected_row < self.table.rowCount():
                self.table.selectRow(selected_row)
        except Exception as e:
            self.log(f"❌ LogistX restore_view_state: {e}")
