from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton
)
from PyQt6.QtCore import Qt
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import ID_FILEPATH


class IDManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактор ID-справочника")
        self.resize(450, 600)

        self.original_entries = JSONManager(ID_FILEPATH).load_json() or []
        self.changed_rows = set()
        self._initializing = True

        # --- Собираем UI
        vbox = QVBoxLayout(self)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по любому полю...")
        vbox.addWidget(self.search)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "ИД-Объекта",
            "Наименование",
            "ТС",
            "Центр мониторинга"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        vbox.addWidget(self.table)

        hbox = QHBoxLayout()
        btn_ok = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        hbox.addStretch()
        hbox.addWidget(btn_ok)
        hbox.addWidget(btn_cancel)
        vbox.addLayout(hbox)

        self._populate_table(self.original_entries)
        self._initializing = False

        self.search.textChanged.connect(self._on_filter)
        self.table.itemChanged.connect(self._on_item_changed)
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

    def _populate_table(self, entries):
        """Заполняем таблицу из списка словарей."""
        self._initializing = True
        self.table.setRowCount(0)
        for ent in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)

            item_id = QTableWidgetItem(str(ent.get("ИДОбъекта в центре мониторинга", "")))
            item_id.setFlags(item_id.flags() | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item_id)

            item_name = QTableWidgetItem(ent.get("Наименование", ""))
            item_name.setFlags(item_name.flags() | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, item_name)

            item_ts = QTableWidgetItem(ent.get("ТС", ""))
            item_ts.setFlags(item_ts.flags() | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, item_ts)

            item_center = QTableWidgetItem(ent.get("Центр мониторинга", ""))
            item_center.setFlags(item_center.flags() | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, item_center)
        self._initializing = False

    def _on_filter(self, text: str):
        """Фильтрация строк по любому полю."""
        text = text.lower()
        for i in range(self.table.rowCount()):
            visible = False
            for j in range(self.table.columnCount()):
                cell = self.table.item(i, j)
                if cell and text in cell.text().lower():
                    visible = True
                    break
            self.table.setRowHidden(i, not visible)

    def _on_item_changed(self, item: QTableWidgetItem):
        """Запоминаем, в каких строках что-либо изменилось."""
        if self._initializing:
            return
        self.changed_rows.add(item.row())

    def accept(self):
        """При сохранении обновляем записи, чьи строки были изменены, и сохраняем JSON."""
        for row in self.changed_rows:
            id_text     = self.table.item(row, 0).text().strip()
            name_text   = self.table.item(row, 1).text().strip()
            ts_text     = self.table.item(row, 2).text().strip()
            center_text = self.table.item(row, 3).text().strip()

            if not id_text.isdigit():
                continue
            obj_id = int(id_text)

            ent = self.original_entries[row]
            ent["ИДОбъекта в центре мониторинга"] = obj_id
            ent["Наименование"]                   = name_text
            ent["ТС"]                             = ts_text
            ent["Центр мониторинга"]             = center_text

        JSONManager(ID_FILEPATH).save_in_json(self.original_entries)
        super().accept()
