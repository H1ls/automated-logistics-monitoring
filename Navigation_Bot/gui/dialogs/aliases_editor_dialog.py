from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem

from Navigation_Bot.gui.dialogs.base_dialog import BaseDialog


class AliasesEditorDialog(BaseDialog):
    """Редактор aliases как списка отдельных значений."""

    def __init__(self, parent=None, aliases=None):
        super().__init__(title="Aliases адреса", size=(560, 420), parent=parent)

        self.root.addWidget(QLabel("Значения, по которым адрес будет распознаваться:"))

        self.alias_input = QLineEdit()
        self.alias_input.setPlaceholderText("Введите alias и нажмите Enter")
        self.root.addWidget(self.alias_input)

        self.aliases_list = QListWidget()
        self.root.addWidget(self.aliases_list)

        self.btn_add = self.make_button("Добавить", self._add_from_input)
        self.btn_remove = self.make_button("Удалить выбранное", self._remove_selected)
        self.add_button_row(left=(self.btn_add, self.btn_remove))

        self.btn_ok, self.btn_cancel = self.add_ok_cancel_buttons()

        self.alias_input.returnPressed.connect(self._add_from_input)
        for alias in aliases or []:
            self._add_alias(str(alias).strip())

    def _add_from_input(self) -> None:
        value = self.alias_input.text().strip()
        if not value:
            return
        self._add_alias(value)
        self.alias_input.clear()

    def _add_alias(self, value: str) -> None:
        if not value or value in self.get_aliases():
            return
        item = QListWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.aliases_list.addItem(item)

    def _remove_selected(self) -> None:
        for item in self.aliases_list.selectedItems():
            self.aliases_list.takeItem(self.aliases_list.row(item))

    def get_aliases(self) -> list[str]:
        result: list[str] = []
        seen = set()
        for row in range(self.aliases_list.count()):
            value = self.aliases_list.item(row).text().strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
