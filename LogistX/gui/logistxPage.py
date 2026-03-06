# logistxPage.py
import json
import re
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                             QAbstractItemView)

from LogistX.controllers.oneCReportImporter import OneCReportImporter
from Navigation_Bot.gui.dialogs.sitesDbEditorDialog import SitesDbEditorDialog


class LogistXPage(QWidget):
    COL_PLAY = 0
    COL_TS = 1
    COL_RACE = 2
    COL_FROM = 3
    COL_TO = 4
    COL_PLAN = 5
    COL_FACT = 6
    COL_STATUS = 7
    fact_clicked = pyqtSignal(int)

    def __init__(self, parent=None, log_func=print):
        super().__init__(parent)
        self.log = log_func

        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.btn_refresh = QPushButton("Обновить")
        self.btn_import_1c = QPushButton("Импорт из 1С (RDP)")
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_import_1c)
        top.addStretch(1)
        lay.addLayout(top)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "▶", "ТС", "Рейс", "Отправление",
            "Назначение", "План",
            "Факт Wialon", "Статус"
        ])
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

        lay.addWidget(self.table)

        self.sample_path = Path("LogistX/config") / "logistx_sample.json"
        self.btn_refresh.clicked.connect(self.load_sample)
        self.btn_import_1c.clicked.connect(self.import_from_1c_rdp)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.sites_db = self._load_sites_db()
        self.rows = []
        self.table.setWordWrap(True)
        # self.fact_clicked.connect(lambda i: self.log(f"▶ нажата строка {i+1}"))

    def _capture_view_state(self) -> tuple[int, int]:
        """Запоминает положение скролла и выделенную строку"""
        try:
            scroll_value = self.table.verticalScrollBar().value()
            selected_row = self.table.currentRow()
        except Exception:
            scroll_value, selected_row = 0, -1
        return scroll_value, selected_row

    def _restore_view_state(self, scroll_value: int, selected_row: int):
        """Восстанавливает скролл и выделение (после перерисовки)"""
        try:
            self.table.verticalScrollBar().setValue(scroll_value)
            if 0 <= selected_row < self.table.rowCount():
                self.table.selectRow(selected_row)
        except Exception as e:
            self.log(f"❌ LogistX restore_view_state: {e}")

    def _extract_raw_address(self, row: int, col: int) -> str:
        if row < 0 or row >= len(self.rows):
            return ""
        obj = self.rows[row]
        if col == self.COL_FROM:
            return str(obj.get("Рейс.Пункт отправления", "") or "")
        if col == self.COL_TO:
            return str(obj.get("Рейс.Пункт назначения", "") or "")
        return ""

    def on_cell_double_clicked(self, row: int, col: int):
        if col not in (self.COL_FROM, self.COL_TO):
            return

        addr = self._extract_raw_address(row, col).strip()
        if not addr:
            return

        dlg = SitesDbEditorDialog(parent=self, prefill_address=addr, log_func=self.log)
        dlg.exec()

        self.sites_db = self._load_sites_db()
        geofence = self._resolve_geofence(addr)

        text = self._format_tag_address(geofence, addr)

        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem("")
            self.table.setItem(row, col, item)

        item.setText(text)

        self.table.resizeRowToContents(row)

    def load_sample(self):
        try:
            p = self.sample_path.resolve()
            self.log(f"📄 LogistX читаю JSON: {p}")
            if p.exists():
                self.log(f"   mtime={p.stat().st_mtime} size={p.stat().st_size}")
            if not self.sample_path.exists():
                self.log(f"❌ Нет файла: {self.sample_path}")
                return
            data = json.loads(self.sample_path.read_text(encoding="utf-8") or "[]")
            if isinstance(data, dict):  # на всякий
                data = [data]
            self.set_rows(data)
            self.log(f"✅ LogistX: загружено рейсов: {len(data)}")
        except Exception as e:
            self.log(f"❌ Ошибка чтения LogistX JSON: {e}")

    def set_rows(self, rows: list[dict]):
        scroll_value, selected_row = self._capture_view_state()

        self.rows = rows
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(0)
            for obj in rows:
                r = self.table.rowCount()
                self.table.insertRow(r)
                btn = QPushButton("▶")
                btn.setFixedWidth(32)
                btn.clicked.connect(lambda _, row=r: self.fact_clicked.emit(row))
                self.table.setCellWidget(r, self.COL_PLAY, btn)

                addr_from = (
                        obj.get("Рейс.Пункт отправления")
                        or obj.get("Пункт отправления")
                        or obj.get("Отправление")
                        or "")
                addr_to = (
                        obj.get("Рейс.Пункт назначения")
                        or obj.get("Пункт назначения")
                        or obj.get("Назначение")
                        or "")

                addr_from = str(addr_from)
                addr_to = str(addr_to)

                gf_from = self._resolve_geofence(addr_from)
                gf_to = self._resolve_geofence(addr_to)

                from_cell = self._format_tag_address(gf_from, addr_from)
                to_cell = self._format_tag_address(gf_to, addr_to)

                values = [
                    obj.get("ТС", ""),
                    obj.get("Рейс", ""),
                    from_cell,
                    to_cell,
                    obj.get("Плановая дата освобождения разгрузка", ""),
                    "",
                    ""]

                for i, v in enumerate(values):
                    self.table.setItem(r, i + 1, QTableWidgetItem(str(v)))
            self.table.resizeRowsToContents()
            self._highlight_missing_tags()

        finally:
            self.table.blockSignals(False)
            # важно: восстановление после того как Qt успел пересчитать layout
            QTimer.singleShot(0, lambda: self._restore_view_state(scroll_value, selected_row))

    def _load_sites_db(self) -> list[dict]:
        # путь подстрой: если sites_db.json у тебя в корневом config
        path = Path("LogistX/config") / "sites_db.json"
        try:
            if not path.exists():
                return []
            data = json.loads(path.read_text(encoding="utf-8") or "[]")
            return data if isinstance(data, list) else []
        except Exception as e:
            self.log(f"❌ Ошибка чтения sites_db.json: {e}")
            return []

    # Helpers

    def _highlight_missing_tags(self):
        pale_red = QColor(255, 220, 220)  # бледно-красный
        transparent = QColor(0, 0, 0, 0)

        for row in range(self.table.rowCount()):
            has_tags = self._row_has_tags(row)

            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)

                # кнопка ▶ — это widget, пропускаем
                if col == self.COL_PLAY:
                    continue

                if not item:
                    continue

                if has_tags:
                    item.setBackground(transparent)
                else:
                    item.setBackground(pale_red)

    def _row_has_tags(self, row: int) -> bool:
        """Проверяет, есть ли 🏷 в колонках Погрузка и Назначение"""
        from_item = self.table.item(row, self.COL_FROM)
        to_item = self.table.item(row, self.COL_TO)

        from_text = from_item.text() if from_item else ""
        to_text = to_item.text() if to_item else ""

        return ("🏷" in from_text) and ("🏷" in to_text)

    def _format_tag_address(self, geofence: str, address: str) -> str:
        geofence = (geofence or "").strip()
        address = (address or "").strip()
        if geofence:
            return f"🏷 {geofence}\n{address}"
        return address

    def _norm(self, s: str) -> str:
        s = (s or "").lower().replace("ё", "е")
        s = re.sub(r"[^\w\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _resolve_geofence(self, address: str) -> str:
        addr_n = self._norm(address)
        if not addr_n:
            return ""
        best = ""
        best_score = 0
        for obj in self.sites_db:
            aliases = obj.get("aliases") or []
            if not isinstance(aliases, list):
                continue
            score = 0
            for a in aliases:
                a_n = self._norm(str(a))
                if a_n and a_n in addr_n:
                    score += 1
            if score > best_score:
                best_score = score
                best = str(obj.get("geofence", "") or "")
        return best if best_score > 0 else ""

    # --- 1C (RDP) import ---

    def import_from_1c_rdp(self):
        importer = OneCReportImporter(log_func=self.log)
        count = importer.run()
        self.log(f"🧪 OneC import result: count={count}")

        # временно: всегда перечитываем файл
        self.load_sample()
