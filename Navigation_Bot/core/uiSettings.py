from __future__ import annotations
from typing import Dict, Any
from PyQt6.QtCore import QPoint, QSize, QTimer
from PyQt6.QtWidgets import QWidget, QTableWidget
from Navigation_Bot.core.paths import UI_SETTINGS_FILE
from Navigation_Bot.core.jSONManager import JSONManager


class UiSettingsManager:
    """
    Хранит/восстанавливает:
      - размер/позицию окна
      - ширины колонок таблицы
      - высоты строк таблицы (если пользователь вручную менял)
    Хранение — в config/ui_settings.json
    """

    def __init__(self, log_func=print):
        self.log = log_func or (lambda *_: None)
        self.store = JSONManager(str(UI_SETTINGS_FILE), log_func=self.log)
        data = self.store.load_json() or {}
        if not isinstance(data, dict):
            data = {}
        self.data: Dict[str, Any] = data

        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush)

    def _schedule_save(self, delay_ms=200):
        self._save_timer.start(delay_ms)

    def _flush(self):
        self.store.save_in_json(self.data, str(UI_SETTINGS_FILE))

    def apply_window(self, widget: QWidget):
        win = self.data.get("window", {})
        size = win.get("size")
        pos = win.get("pos")
        try:
            if size and isinstance(size, list) and len(size) == 2:
                widget.resize(QSize(size[0], size[1]))
            if pos and isinstance(pos, list) and len(pos) == 2:
                widget.move(QPoint(pos[0], pos[1]))
        except Exception as e:
            self.log(f"⚠️ Не удалось применить размеры окна: {e}")

    def save_window(self, widget: QWidget):
        self.data.setdefault("window", {})
        self.data["window"]["size"] = [widget.size().width(), widget.size().height()]
        self.data["window"]["pos"] = [widget.pos().x(), widget.pos().y()]
        self._schedule_save()

    def apply_table(self, table: QTableWidget):
        tbl = self.data.get("table", {})
        # ширины колонок
        widths: Dict[str, int] = tbl.get("column_widths", {})
        for i in range(table.columnCount()):
            if str(i) in widths:
                try:
                    table.setColumnWidth(i, int(widths[str(i)]))
                except Exception:
                    pass
        # высоты строк (после заполнения таблицы удобнее дергать отдельно — см. apply_row_heights)
        # здесь ничего не делаем

    def apply_row_heights(self, table: QTableWidget):
        tbl = self.data.get("table", {})
        heights: Dict[str, int] = tbl.get("row_heights", {})

        vhdr = table.verticalHeader()
        # Блокируем сигналы, чтобы не ловить sectionResized во время восстановления
        prev_blocked = vhdr.signalsBlocked()
        table.setUpdatesEnabled(False)
        vhdr.blockSignals(True)
        try:
            rc = table.rowCount()
            for r in range(rc):
                h = heights.get(str(r))
                if h:
                    try:
                        h_int = int(h)
                        if h_int > 0:
                            table.setRowHeight(r, h_int)
                    except Exception:
                        pass
        finally:
            vhdr.blockSignals(prev_blocked)
            table.setUpdatesEnabled(True)

    def on_col_resized(self, logical_index: int, old: int, new: int, table: QTableWidget):
        tbl = self.data.setdefault("table", {})
        widths: Dict[str, int] = tbl.setdefault("column_widths", {})
        widths[str(logical_index)] = int(new)
        self._schedule_save()

    def on_row_resized(self, logical_index: int, old: int, new: int, table: QTableWidget):
        tbl = self.data.setdefault("table", {})
        heights: Dict[str, int] = tbl.setdefault("row_heights", {})
        heights[str(logical_index)] = int(new)
        self._schedule_save()
