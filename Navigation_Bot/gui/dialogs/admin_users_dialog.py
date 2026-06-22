from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox,
                             QComboBox,
                             QDialog,
                             QFormLayout,
                             QHBoxLayout,
                             QLabel,
                             QLineEdit,
                             QMessageBox,
                             QPushButton,
                             QTableWidget,
                             QTableWidgetItem,
                             QVBoxLayout)

from Navigation_Bot.core.infrastructure.api.api_client import NavigationApiError


ROLES = ("admin", "dispatcher", "viewer")


class AdminUsersDialog(QDialog):
    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.setWindowTitle("Пользователи и роли")
        self.resize(760, 460)

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Username", "Имя", "Роль", "Активен", "API-ключи", "Обновлен"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._fill_from_selection)
        layout.addWidget(self.table)

        form = QFormLayout()
        self.username_edit = QLineEdit()
        self.display_name_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("оставьте пустым, чтобы не менять")
        self.password_confirm_edit = QLineEdit()
        self.password_confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_confirm_edit.setPlaceholderText("повторите новый пароль")
        self.role_combo = QComboBox()
        self.role_combo.addItems(ROLES)
        self.active_check = QCheckBox("активен")
        self.active_check.setChecked(True)
        self._editing_existing = False
        self._selected_user_id: int | None = None

        form.addRow("Username", self.username_edit)
        form.addRow("Имя", self.display_name_edit)
        form.addRow("Password", self.password_edit)
        form.addRow("Подтверждение", self.password_confirm_edit)
        form.addRow("Роль", self.role_combo)
        form.addRow("", self.active_check)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.status_label = QLabel("")
        btn_refresh = QPushButton("Обновить")
        btn_new = QPushButton("Очистить")
        btn_save = QPushButton("Сохранить")
        btn_close = QPushButton("Закрыть")
        btn_refresh.clicked.connect(self.refresh)
        btn_new.clicked.connect(self.clear_form)
        btn_save.clicked.connect(self.save_user)
        btn_close.clicked.connect(self.accept)
        buttons.addWidget(self.status_label, 1)
        buttons.addWidget(btn_refresh)
        buttons.addWidget(btn_new)
        buttons.addWidget(btn_save)
        buttons.addWidget(btn_close)
        layout.addLayout(buttons)

        self.refresh()

    def refresh(self) -> None:
        try:
            payload = self.api_client.get("/api/v1/users")
        except NavigationApiError as exc:
            QMessageBox.warning(self, "Пользователи", str(exc))
            return

        rows = payload.get("items", []) if isinstance(payload, dict) else []
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self._set_row(row_index, row)
        self.status_label.setText(f"Пользователей: {len(rows)}")

    def save_user(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username:
            QMessageBox.warning(self, "Пользователи", "Введите username.")
            return
        if not self._editing_existing and not password:
            QMessageBox.warning(self, "Пользователи", "Для нового пользователя введите пароль.")
            return
        if password and len(password) < 8:
            QMessageBox.warning(self, "Пользователи", "Пароль должен содержать минимум 8 символов.")
            return
        if password != self.password_confirm_edit.text():
            QMessageBox.warning(self, "Пользователи", "Пароли не совпадают.")
            return

        request_payload = {"username": username,
                           "display_name": self.display_name_edit.text().strip(),
                           "password": password,
                           "role": self.role_combo.currentText(),
                           "is_active": self.active_check.isChecked()}
        try:
            if self._selected_user_id is None:
                response = self.api_client.post("/api/v1/users", json=request_payload)
            else:
                response = self.api_client.put(f"/api/v1/users/{self._selected_user_id}", json=request_payload)
        except NavigationApiError as exc:
            QMessageBox.warning(self, "Пользователи", str(exc))
            return

        saved_user = response.get("user", {}) if isinstance(response, dict) else {}
        if saved_user.get("id") is not None:
            self._selected_user_id = int(saved_user["id"])
        self.password_edit.clear()
        self.password_confirm_edit.clear()
        self._editing_existing = True
        self.refresh()

    def clear_form(self) -> None:
        self.username_edit.clear()
        self.display_name_edit.clear()
        self.password_edit.clear()
        self.password_confirm_edit.clear()
        self.role_combo.setCurrentText("viewer")
        self.active_check.setChecked(True)
        self._editing_existing = False
        self._selected_user_id = None
        self.username_edit.setReadOnly(False)
        self.username_edit.setFocus()

    def _fill_from_selection(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        self._selected_user_id = int(self.table.item(row, 0).text())
        self.username_edit.setText(self.table.item(row, 1).text())
        self.username_edit.setReadOnly(False)
        self.display_name_edit.setText(self.table.item(row, 2).text())
        self.password_edit.clear()
        self.password_confirm_edit.clear()
        self.role_combo.setCurrentText(self.table.item(row, 3).text())
        self.active_check.setChecked(self.table.item(row, 4).text() == "да")
        self._editing_existing = True

    def _set_row(self, row_index: int, row: dict[str, Any]) -> None:
        values = [
            row.get("id", ""),
            row.get("username", ""),
            row.get("display_name", ""),
            row.get("role", ""),
            "да" if row.get("is_active") else "нет",
            row.get("active_api_key_count", 0),
            row.get("updated_at", ""),
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column == 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row_index, column, item)
