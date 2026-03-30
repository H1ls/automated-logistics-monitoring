from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton
)

from Navigation_Bot.core.dataContext import DataContext
from Navigation_Bot.core.paths import ID_FILEPATH
from Navigation_Bot.gui.dialogs.dialog_helpers import button_row_trailing

_ID = "ИДОбъекта в центре мониторинга"
_NAME = "Наименование"
_TS = "ТС"
_CENTER = "Центр мониторинга"


class IDManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактор ID-справочника")
        self.resize(550, 600)

        self.log_func = getattr(parent, "log", print)
        self.context = DataContext(ID_FILEPATH, log_func=self.log_func)
        self.original_entries = self.context.get()  # это тот же список, что внутри DataContext
        self.changed_rows = set()
        self._initializing = True

        # --- Собираем UI ---
        vbox = QVBoxLayout(self)

        # Поиск
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по любому полю...")
        vbox.addWidget(self.search)

        add_layout = QHBoxLayout()

        self.new_id = QLineEdit()
        self.new_id.setPlaceholderText("ИД-Объекта")

        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("Наименование (пример: К532СМ750)")

        btn_add = QPushButton("Добавить")
        btn_add.clicked.connect(self._on_add_entry)

        add_layout.addWidget(self.new_id)
        add_layout.addWidget(self.new_name)
        add_layout.addWidget(btn_add)

        vbox.addLayout(add_layout)

        # Таблица
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ИД-Объекта", _NAME, _TS, _CENTER])
        self.table.horizontalHeader().setStretchLastSection(True)
        vbox.addWidget(self.table)

        btn_ok = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        vbox.addLayout(button_row_trailing(btn_ok, btn_cancel))

        # Заполняем таблицу
        self._populate_table(self.original_entries)
        self._initializing = False

        # Сигналы
        self.search.textChanged.connect(self._on_filter)
        self.table.itemChanged.connect(self._on_item_changed)
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

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
            self._editable_item(str(ent.get(_CENTER, ""))),
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
        if len(name_text) >= 7:
            ts_text = f"{name_text[0]} {name_text[1:4]} {name_text[4:6]} {name_text[6:]}"
        else:
            # если формат неожиданный - просто пишем как есть
            ts_text = name_text

        center_text = "Виалон"

        # Добавляем в оригинальный список
        new_entry = {_ID: obj_id, _NAME: name_text, _TS: ts_text, _CENTER: center_text}

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

    # Сохранение
    def accept(self):
        """При сохранении обновляем записи, чьи строки были изменены, и сохраняем через DataContext."""
        for row in self.changed_rows:
            id_text = self.table.item(row, 0).text().strip()
            name_text = self.table.item(row, 1).text().strip()
            ts_text = self.table.item(row, 2).text().strip()
            center_text = self.table.item(row, 3).text().strip()

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
            ent[_CENTER] = center_text

        self.context.save()
        super().accept()
