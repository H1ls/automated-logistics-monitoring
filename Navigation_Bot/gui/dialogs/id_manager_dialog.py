from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QHBoxLayout, QLineEdit, QTableWidget, QTableWidgetItem, QPushButton

from Navigation_Bot.gui.dialogs.base_dialog import BaseDialog
from Navigation_Bot.core.repositories.vehicle_registry_fields import (CENTER_FIELD, DEFAULT_MONITORING_CENTER,
                                                                      ID_FIELD, NAME_FIELD, TS_FIELD,
                                                                      plate_from_monitoring_name)

_ID = ID_FIELD
_NAME = NAME_FIELD
_TS = TS_FIELD
_CENTER = CENTER_FIELD


class IDManagerDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(title="Редактор ID-справочника", size=(400, 600), parent=parent)

        self.log_func = self.log
        self.vehicle_repository = getattr(parent, "vehicle_repository", None)
        if self.vehicle_repository is None:
            raise RuntimeError("IDManagerDialog requires parent.vehicle_repository")
        self.original_entries = [dict(entry) for entry in self.vehicle_repository.list_registry_entries()]
        self.deleted_entries = []
        self.changed_rows = set()
        self._initializing = True

        # --- Собираем UI ---
        # Поиск
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по любому полю...")
        self.root.addWidget(self.search)

        # Таблица
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ИД-Объекта", _NAME, _TS])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.root.addWidget(self.table)

        add_layout = QHBoxLayout()

        self.new_id = QLineEdit()
        self.new_id.setPlaceholderText("ID")

        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("Пример: К532СМ750")

        btn_add = QPushButton("Добавить")
        btn_add.clicked.connect(self._on_add_entry)

        add_layout.addWidget(self.new_id)
        add_layout.addWidget(self.new_name)
        add_layout.addWidget(btn_add)

        self.root.addLayout(add_layout)

        btn_delete = self.make_button("Удалить", self._on_delete_selected)
        btn_ok = self.make_button("Сохранить", self.accept)
        btn_cancel = self.make_button("Отмена", self.reject)
        self.add_button_row(left=(btn_delete,), right=(btn_ok, btn_cancel))

        # Заполняем таблицу
        self._populate_table(self.original_entries)
        self._initializing = False

        # Сигналы
        self.search.textChanged.connect(self._on_filter)
        self.table.itemChanged.connect(self._on_item_changed)

    @staticmethod
    def _editable_item(text: str) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
        return it

    def _row_cells(self, ent: dict) -> list[QTableWidgetItem]:
        return [
            self._editable_item(str(ent.get(_ID, ""))),
            self._editable_item(str(ent.get(_NAME, ""))),
            self._editable_item(str(ent.get(_TS, ""))),
        ]

    def _populate_table(self, entries):
        """Заполняем таблицу из списка словарей."""
        self._initializing = True
        self.table.setRowCount(0)
        for ent in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, item in enumerate(self._row_cells(ent)):
                self.table.setItem(row, col, item)
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

    # Отслеживание изменений в таблице
    def _on_item_changed(self, item: QTableWidgetItem):
        """Запоминаем, в каких строках что-либо изменилось."""
        if self._initializing:
            return
        self.changed_rows.add(item.row())

    # Добавление новой записи из нижней строки ввода
    def _on_add_entry(self):
        id_text = self.new_id.text().strip()
        name_text = self.new_name.text().strip()

        # Валидация нужен числовой ID и непустое Наименование
        if not id_text.isdigit() or not name_text:
            return

        obj_id = int(id_text)
        # Защита от дублей ID при добавлении
        for e in self.original_entries:
            if e.get(_ID) == obj_id:
                self.log_func(f"⚠️ Ошибка: ID {obj_id} уже существует!")
                return

        # Генерация ТС из Наименования, К532СМ750 -> К 532 СМ 750
        ts_text = plate_from_monitoring_name(name_text)

        # Добавляем в оригинальный список
        new_entry = {_ID: obj_id, _NAME: name_text, _TS: ts_text, _CENTER: DEFAULT_MONITORING_CENTER}

        self.original_entries.append(new_entry)

        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, item in enumerate(self._row_cells(new_entry)):
            self.table.setItem(row, col, item)

        # помечаем строку как изменённую
        self.changed_rows.add(row)

        # очищаем только то, что реально вводим
        self.new_id.clear()
        self.new_name.clear()

    def _on_delete_selected(self):
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not selected_rows:
            current_row = self.table.currentRow()
            selected_rows = [current_row] if current_row >= 0 else []

        for row in selected_rows:
            if 0 <= row < len(self.original_entries):
                self.deleted_entries.append(self.original_entries.pop(row))
                self.table.removeRow(row)

        self.changed_rows = {row for row in self.changed_rows if row not in selected_rows}
        deleted_before = {row: sum(1 for removed in selected_rows if removed < row) for row in self.changed_rows}
        self.changed_rows = {row - shift for row, shift in deleted_before.items()}

    # Сохранение
    def accept(self):
        """При сохранении обновляем записи, чьи строки были изменены, и сохраняем через DataContext."""
        delete_entry = getattr(self.vehicle_repository, "delete_registry_entry", None)
        if callable(delete_entry):
            for entry in self.deleted_entries:
                delete_entry(entry)

        for row in self.changed_rows:
            id_text = self.table.item(row, 0).text().strip()
            name_text = self.table.item(row, 1).text().strip()
            ts_text = self.table.item(row, 2).text().strip()

            if not id_text.isdigit():
                continue

            obj_id = int(id_text)
            for idx, e in enumerate(self.original_entries):
                if idx == row:
                    continue  # пропускаем текущую строку
                if e.get(_ID) == obj_id:
                    self.log_func(f"⚠️ Ошибка: ID {obj_id} уже существует!")
                    return
            ent = self.original_entries[row]
            ent[_ID] = obj_id
            ent[_NAME] = name_text
            ent[_TS] = ts_text

        self.vehicle_repository.save_registry_entries(self.original_entries)
        super().accept()
