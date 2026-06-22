from __future__ import annotations
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton, QTextEdit,
                             QMessageBox, )

from Navigation_Bot.gui.dialogs.address_edit_dialog import AddressEditDialog


class CreateRaceDialog(QDialog):
    """
    Диалог создания новой задачи / рейса.

    Диалог:
    - собирает простые поля (ТС, Телефон, КА, ФИО)
    - хранит буфер Погрузка/Выгрузка
    - открывает AddressEditDialog для редактирования сложных блоков
    - НЕ сохраняет ничего сам, только возвращает payload
    """

    def __init__(self, task_repository, log_func=None, parent=None):
        super().__init__(parent)
        self.task_repository = task_repository
        self.log = log_func or print

        self._buffer = {"Погрузка": [],
                        "Выгрузка": [],}
        self._upload_to_google = False

        self.setWindowTitle("Создать рейс")
        self.resize(760, 720)

        self._build_ui()

    # --- UI
    def _build_ui(self):
        root = QVBoxLayout(self)

        form = QFormLayout()

        self.edit_ts = QLineEdit()
        self.edit_phone = QLineEdit()
        self.edit_ka = QLineEdit()
        self.edit_fio = QLineEdit()

        self.edit_ts.setPlaceholderText("Например: А123БВ 777")
        self.edit_phone.setPlaceholderText("Например: 79001234567")
        self.edit_ka.setPlaceholderText("КА")
        self.edit_fio.setPlaceholderText("ФИО")

        form.addRow("ТС:", self.edit_ts)
        form.addRow("Телефон:", self.edit_phone)
        form.addRow("КА:", self.edit_ka)
        form.addRow("ФИО:", self.edit_fio)

        root.addLayout(form)

        # --- кнопки редактирования адресов ---
        addr_btns = QHBoxLayout()

        self.btn_edit_load = QPushButton("Редактировать погрузку")
        self.btn_edit_unload = QPushButton("Редактировать выгрузку")

        self.btn_edit_load.clicked.connect(self._edit_load)
        self.btn_edit_unload.clicked.connect(self._edit_unload)

        addr_btns.addWidget(self.btn_edit_load)
        addr_btns.addWidget(self.btn_edit_unload)

        root.addLayout(addr_btns)

        # --- preview погрузки ---
        root.addWidget(QLabel("Погрузка:"))
        self.preview_load = QTextEdit()
        self.preview_load.setReadOnly(True)
        self.preview_load.setMinimumHeight(180)
        root.addWidget(self.preview_load)

        # --- preview выгрузки ---
        root.addWidget(QLabel("Выгрузка:"))
        self.preview_unload = QTextEdit()
        self.preview_unload.setReadOnly(True)
        self.preview_unload.setMinimumHeight(220)
        root.addWidget(self.preview_unload)

        # --- кнопки действий ---
        actions = QHBoxLayout()
        actions.addStretch()

        self.btn_save = QPushButton("Сохранить")
        self.btn_save_send = QPushButton("Сохранить и отправить")
        self.btn_cancel = QPushButton("Отмена")

        self.btn_save.clicked.connect(lambda: self._accept_if_valid(upload_to_google=False))
        self.btn_save_send.clicked.connect(lambda: self._accept_if_valid(upload_to_google=True))
        self.btn_cancel.clicked.connect(self.reject)

        actions.addWidget(self.btn_save)
        actions.addWidget(self.btn_save_send)
        actions.addWidget(self.btn_cancel)

        root.addLayout(actions)

        self._refresh_previews()

    # --- helpers
    @staticmethod
    def _format_points(blocks: list[dict], prefix: str) -> str:
        if not isinstance(blocks, list):
            return ""

        points = []
        comment = ""

        for d in blocks:
            if not isinstance(d, dict):
                continue

            if "Комментарий" in d:
                comment = str(d.get("Комментарий", "")).strip()
                continue

            if f"{prefix} другое" in d:
                comment = str(d.get(f"{prefix} другое", "")).strip()
                continue

            if any(k.startswith(f"{prefix} ") for k in d.keys()):
                points.append(d)

        lines: list[str] = []

        for i, block in enumerate(points, 1):
            date = block.get(f"Дата {i}", "")
            time = block.get(f"Время {i}", "")
            address = block.get(f"{prefix} {i}", "")

            dt = f"{date} {time}".strip()
            if dt and dt != "Не указано Не указано":
                lines.append(dt)

            if address:
                lines.append(address)

            if i < len(points):
                lines.append("____________________")

        if comment:
            if lines:
                lines.append("")
            lines.append("Комментарий:")
            lines.append(comment)

        return "\n".join(lines)

    def _refresh_previews(self):
        self.preview_load.setPlainText(self._format_points(self._buffer.get("Погрузка", []), "Погрузка"))
        self.preview_unload.setPlainText(self._format_points(self._buffer.get("Выгрузка", []), "Выгрузка"))

    def _open_address_editor(self, prefix: str):
        temp_entry = {"Погрузка": self._buffer.get("Погрузка", []),
                      "Выгрузка": self._buffer.get("Выгрузка", []), }

        dialog = AddressEditDialog(row_data=temp_entry,
                                   prefix=prefix,
                                   parent=self,
                                   log_func=self.log, )

        if dialog.exec():
            data_block, meta = dialog.get_result()
            if not data_block:
                return

            self._buffer[prefix] = data_block

            if meta.get("Время отправки"):
                self._buffer["Время отправки"] = meta["Время отправки"]

            if meta.get("Транзит"):
                self._buffer["Транзит"] = meta["Транзит"]

            self._refresh_previews()

    # --- actions
    def _edit_load(self):
        self._open_address_editor("Погрузка")

    def _edit_unload(self):
        self._open_address_editor("Выгрузка")

    def _accept_if_valid(self, *, upload_to_google: bool = False):
        ts = self.edit_ts.text().strip()
        ka = self.edit_ka.text().strip()
        fio = self.edit_fio.text().strip()

        if not ts:
            QMessageBox.warning(self, "Проверка", "Заполни поле ТС.")
            return

        if not ka:
            QMessageBox.warning(self, "Проверка", "Заполни поле КА.")
            return

        if not fio:
            QMessageBox.warning(self, "Проверка", "Заполни поле ФИО.")
            return

        if not self._buffer.get("Погрузка"):
            QMessageBox.warning(self, "Проверка", "Добавь погрузку.")
            return

        if not self._buffer.get("Выгрузка"):
            QMessageBox.warning(self, "Проверка", "Добавь выгрузку.")
            return

        self._upload_to_google = bool(upload_to_google)
        self.accept()

    # --- public
    def get_payload(self) -> dict:
        return {"ts": self.edit_ts.text().strip(),
                "phone": self.edit_phone.text().strip(),
                "ka": self.edit_ka.text().strip(),
                "fio": self.edit_fio.text().strip(),
                "buffer": dict(self._buffer),
                "upload_to_google": self._upload_to_google, }
