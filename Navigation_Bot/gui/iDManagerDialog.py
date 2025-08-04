from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel
)
from PyQt6.QtCore import Qt
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import ID_FILEPATH

class IDManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактор ID-справочника")
        self.resize(500, 600)

        # загрузили данные
        self.entries = JSONManager(ID_FILEPATH).load_json()

        # UI
        vbox = QVBoxLayout(self)

        # 1) строка поиска
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по ТС или ID...")
        vbox.addWidget(self.search)

        # 2) таблица
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["ИДОбъекта", "ТС"])
        self.table.horizontalHeader().setStretchLastSection(True)
        vbox.addWidget(self.table)

        # 3) кнопки Сохранить/Отмена
        hbox = QHBoxLayout()
        btn_ok = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        hbox.addStretch()
        hbox.addWidget(btn_ok)
        hbox.addWidget(btn_cancel)
        vbox.addLayout(hbox)

        # заполнить таблицу
        self._populate_table(self.entries)

        # фильтрация
        self.search.textChanged.connect(self._on_filter)

    def _populate_table(self, entries):
        self.table.setRowCount(0)
        for ent in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            # ИД
            item_id = QTableWidgetItem(str(ent.get("ИДОбъекта в центре мониторинга", "")))
            item_id.setFlags(item_id.flags() | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item_id)
            # ТС
            item_ts = QTableWidgetItem(ent.get("ТС", ""))
            item_ts.setFlags(item_ts.flags() | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, item_ts)

    def _on_filter(self, text):
        text = text.lower()
        for i in range(self.table.rowCount()):
            id_item = self.table.item(i, 0).text().lower()
            ts_item = self.table.item(i, 1).text().lower()
            match = text in id_item or text in ts_item
            self.table.setRowHidden(i, not match)

    def accept(self):
        # собрать из таблицы
        new_list = []
        for i in range(self.table.rowCount()):
            if self.table.isRowHidden(i):
                continue
            raw_id = self.table.item(i, 0).text().strip()
            raw_ts = self.table.item(i, 1).text().strip()
            if not raw_id.isdigit() or not raw_ts:
                continue
            new_list.append({
                "ИДОбъекта в центре мониторинга": int(raw_id),
                "Центр мониторинга": "Виалон",
                "ТС": raw_ts,
                "Наименование": raw_ts.replace(" ", "")
            })
        self.entries = new_list
        super().accept()


