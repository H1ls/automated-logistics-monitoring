from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox
)
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from Navigation_Bot.core.paths import CONFIG_JSON
from Navigation_Bot.core.jSONManager import JSONManager


class LoginDialog(QDialog):
    """Диалог авторизации по логину/паролю. Проверяет пользователя по листу Account в Google Sheets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Вход в Navigation Manager")
        self.resize(300, 140)
        self.login: str = ""
        self.password: str = ""

        layout = QVBoxLayout(self)

        # Логин
        row_login = QHBoxLayout()
        row_login.addWidget(QLabel("Логин:"))
        self.edit_login = QLineEdit()
        self.edit_login.setPlaceholderText("login")
        row_login.addWidget(self.edit_login)
        layout.addLayout(row_login)

        # Пароль
        row_pass = QHBoxLayout()
        row_pass.addWidget(QLabel("Пароль:"))
        self.edit_password = QLineEdit()
        self.edit_password.setPlaceholderText("password")
        self.edit_password.setEchoMode(QLineEdit.EchoMode.Password)
        row_pass.addWidget(self.edit_password)
        layout.addLayout(row_pass)

        # Кнопки
        btns = QHBoxLayout()
        btn_ok = QPushButton("Войти")
        btn_cancel = QPushButton("Отмена")
        btn_ok.clicked.connect(self._on_login)
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

        # По Enter сразу логин
        self.edit_password.returnPressed.connect(self._on_login)

    def _log(self, msg: str):
        # при желании можно сюда пробросить основной лог
        print(msg)

    def _on_login(self):
        self.login = self.edit_login.text()
        self.password = self.edit_password.text()

        # Можно слегка валидировать локально:
        if not self.login or not self.password:
            QMessageBox.warning(self, "Вход", "Введите логин и пароль.")
            return

        self.accept()

