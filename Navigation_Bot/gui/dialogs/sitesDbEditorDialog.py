import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from Navigation_Bot.gui.dialogs.aliasesEditorDialog import AliasesEditorDialog
from Navigation_Bot.gui.dialogs.dialog_helpers import button_row_split

SITES_DB_PATH = Path("LogistX/config") / "sites_db.json"

HEADERS = ["Адрес", "site_id", "geofence", "type", "aliases"]


class SitesDbEditorDialog(QDialog):
    def __init__(self, parent=None, prefill_address: str = "", log_func=None):
        super().__init__(parent)
        self.setWindowTitle("Редактор геозон/складов")
        self.resize(900, 850)

        self.log = log_func or print
        self.prefill_address = (prefill_address or "").strip()

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        layout.addWidget(self.table)

        # перенос текста в ячейках
        self.table.setWordWrap(True)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        # ширины колонок
        self.table.setColumnWidth(0, 450)  # Адрес
        self.table.setColumnWidth(1, 150)  # site_id
        self.table.setColumnWidth(2, 150)  # geofence
        self.table.setColumnWidth(3, 60)  # type
        self.table.setColumnWidth(4, 30)  # aliases

        # вертикальный хедер можно сузить
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        # чтобы адрес красиво переносился и строка увеличивалась
        self.table.resizeRowsToContents()
        self.btn_add = QPushButton("➕ Добавить")
        self.btn_del = QPushButton("🗑 Удалить")
        self.btn_save = QPushButton("💾 Сохранить")
        self.btn_close = QPushButton("Закрыть")
        layout.addLayout(
            button_row_split(
                (self.btn_add, self.btn_del),
                (self.btn_save, self.btn_close),
            )
        )

        self.btn_add.clicked.connect(self.add_row)
        self.btn_del.clicked.connect(self.delete_selected_rows)
        self.btn_save.clicked.connect(self.save_json)
        self.btn_close.clicked.connect(self.close)

        self._aliases_by_row = {}  # key: row_index -> list[str]
        self.load_json()

        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        if self.prefill_address:
            self.add_row(address=self.prefill_address)

    def _norm(self, s: str) -> str:
        s = (s or "").strip().lower().replace("ё", "е")
        return s

    def _sort_key(self, obj: dict):
        return (self._norm(obj.get("address", "")),
                self._norm(obj.get("geofence", "")),
                self._norm(obj.get("site_id", "")),
                )

    def edit_aliases(self, row: int):
        cur = self._aliases_by_row.get(row, [])
        dlg = AliasesEditorDialog(self, cur)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_list = dlg.get_aliases()
        self._aliases_by_row[row] = new_list

        item = self.table.item(row, 4)
        if item is None:
            item = QTableWidgetItem("")
            self.table.setItem(row, 4, item)

        # item.setText("…" if new_list else "")
        item.setText("✎" if new_list else "")

    def on_cell_double_clicked(self, row: int, col: int):
        if col != 4:  # aliases column
            return
        self.edit_aliases(row)

    def load_json(self):
        try:
            if not SITES_DB_PATH.exists():
                self.table.setRowCount(0)
                return
            data = json.loads(SITES_DB_PATH.read_text(encoding="utf-8") or "[]")
            if not isinstance(data, list):
                data = []
            data.sort(key=self._sort_key)

            self.table.setRowCount(0)
            for obj in data:
                self._append_obj(obj)
            self.table.resizeRowsToContents()
        except Exception as e:
            self.log(f"❌ Ошибка загрузки sites_db.json: {e}")

    def _append_obj(self, obj: dict):
        r = self.table.rowCount()
        self.table.insertRow(r)

        address = str(obj.get("address", "") or "")
        site_id = str(obj.get("site_id", "") or "")
        geofence = str(obj.get("geofence", "") or "")
        typ = str(obj.get("type", "") or "")
        aliases_list = obj.get("aliases", []) or []
        if not isinstance(aliases_list, list):
            aliases_list = []

        self._aliases_by_row[r] = [str(x).strip() for x in aliases_list if str(x).strip()]

        values = [address, site_id, geofence, typ]
        for c, v in enumerate(values):
            self.table.setItem(r, c, QTableWidgetItem(v))

        # self.table.setItem(r, 4, QTableWidgetItem("…" if self._aliases_by_row[r] else ""))
        self.table.setItem(r, 4, QTableWidgetItem("✎" if self._aliases_by_row[r] else ""))

    def add_row(self, address: str = ""):
        r = self.table.rowCount()

        self.table.insertRow(r)
        for c in range(len(HEADERS)):
            self.table.setItem(r, c, QTableWidgetItem(""))

        self._aliases_by_row[r] = []
        self.table.item(r, 4).setText("")
        if address:
            self.table.item(r, 0).setText(address)
        self.table.resizeRowsToContents()

    def delete_selected_rows(self):
        rows_to_delete = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows_to_delete:
            return

        for r in rows_to_delete:
            self.table.removeRow(r)

            new_map = {}
            for k, v in self._aliases_by_row.items():
                if k == r:
                    continue
                if k > r:
                    new_map[k - 1] = v
                else:
                    new_map[k] = v
            self._aliases_by_row = new_map

    def save_json(self):
        try:
            data = []
            for r in range(self.table.rowCount()):
                address = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
                site_id = (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()
                geofence = (self.table.item(r, 2).text() if self.table.item(r, 2) else "").strip()
                typ = (self.table.item(r, 3).text() if self.table.item(r, 3) else "").strip()
                aliases = self._aliases_by_row.get(r, [])

                if not any([address, site_id, geofence, typ, aliases]):
                    continue

                data.append({"address": address,
                             "site_id": site_id,
                             "geofence": geofence,
                             "type": typ,
                             "aliases": aliases
                             })
            data.sort(key=self._sort_key)
            SITES_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            SITES_DB_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.load_json()
            QMessageBox.information(self, "Сохранено", "sites_db.json успешно сохранён.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")
