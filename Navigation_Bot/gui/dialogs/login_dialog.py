from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from Navigation_Bot.gui.dialogs.dialog_helpers import button_row_trailing


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вход в Navigation Manager")
        self.resize(360, 150)
        self.username = ""
        self.password = ""

        layout = QVBoxLayout(self)

        row_username = QHBoxLayout()
        row_username.addWidget(QLabel("Username:"))
        self.edit_username = QLineEdit()
        self.edit_username.setPlaceholderText("username")
        row_username.addWidget(self.edit_username)
        layout.addLayout(row_username)

        row_password = QHBoxLayout()
        row_password.addWidget(QLabel("Password:"))
        self.edit_password = QLineEdit()
        self.edit_password.setPlaceholderText("password")
        self.edit_password.setEchoMode(QLineEdit.EchoMode.Password)
        row_password.addWidget(self.edit_password)
        layout.addLayout(row_password)

        btn_ok = QPushButton("Войти")
        btn_cancel = QPushButton("Отмена")
        btn_ok.clicked.connect(self._on_login)
        btn_cancel.clicked.connect(self.reject)
        layout.addLayout(button_row_trailing(btn_ok, btn_cancel))

        self.edit_password.returnPressed.connect(self._on_login)

    def _on_login(self) -> None:
        self.username = self.edit_username.text().strip()
        self.password = self.edit_password.text()
        if not self.username or not self.password:
            self.edit_username.setFocus()
            return
        self.accept()
