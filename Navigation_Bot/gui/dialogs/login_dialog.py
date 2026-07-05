from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit

from Navigation_Bot.gui.dialogs.base_dialog import BaseDialog


class LoginDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(title="Вход в Navigation Manager", size=(360, 150), parent=parent)
        self.username = ""
        self.password = ""

        row_username = QHBoxLayout()
        row_username.addWidget(QLabel("Username:"))
        self.edit_username = QLineEdit()
        self.edit_username.setPlaceholderText("username")
        row_username.addWidget(self.edit_username)
        self.root.addLayout(row_username)

        row_password = QHBoxLayout()
        row_password.addWidget(QLabel("Password:"))
        self.edit_password = QLineEdit()
        self.edit_password.setPlaceholderText("password")
        self.edit_password.setEchoMode(QLineEdit.EchoMode.Password)
        row_password.addWidget(self.edit_password)
        self.root.addLayout(row_password)

        self.add_ok_cancel_buttons(ok_text="Войти", ok_callback=self._on_login)

        self.edit_password.returnPressed.connect(self._on_login)

    def _on_login(self) -> None:
        self.username = self.edit_username.text().strip()
        self.password = self.edit_password.text()
        if not self.username or not self.password:
            self.edit_username.setFocus()
            return
        self.accept()
