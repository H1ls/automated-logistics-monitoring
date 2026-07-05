from __future__ import annotations

from collections.abc import Callable, Sequence

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget

from Navigation_Bot.core.logging import normalize_log_func


class BaseDialog(QDialog):
    def __init__(self, *, title: str, size: tuple[int, int] | None = None, parent=None, log_func=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        if size is not None:
            self.resize(*size)

        parent_log = getattr(parent, "log", None)
        self.log = normalize_log_func(log_func if log_func is not None else parent_log)
        self.root = QVBoxLayout(self)

    def make_button(self, text: str, callback: Callable[[], None] | None = None) -> QPushButton:
        button = QPushButton(text)
        if callback is not None:
            button.clicked.connect(lambda _checked=False: callback())
        return button

    def add_button_row(self, *, left: Sequence[QWidget] = (), right: Sequence[QWidget] = ()) -> QHBoxLayout:
        row = QHBoxLayout()
        for widget in left:
            row.addWidget(widget)
        row.addStretch(1)
        for widget in right:
            row.addWidget(widget)
        self.root.addLayout(row)
        return row

    def add_ok_cancel_buttons(
            self,
            *,
            ok_text: str = "OK",
            cancel_text: str = "Отмена",
            ok_callback: Callable[[], None] | None = None,
            cancel_callback: Callable[[], None] | None = None) -> tuple[QPushButton, QPushButton]:

        ok_button = self.make_button(ok_text, ok_callback or self.accept)
        cancel_button = self.make_button(cancel_text, cancel_callback or self.reject)
        self.add_button_row(right=(ok_button, cancel_button))
        return ok_button, cancel_button

    def add_save_cancel_buttons(self, *,
                                save_text: str = "Сохранить",
                                cancel_text: str = "Отмена",
                                save_callback: Callable[[], None] | None = None,
                                cancel_callback: Callable[[], None] | None = None, ) -> tuple[QPushButton, QPushButton]:

        save_button = self.make_button(save_text, save_callback or self.accept)
        cancel_button = self.make_button(cancel_text, cancel_callback or self.reject)
        self.add_button_row(right=(save_button, cancel_button))
        return save_button, cancel_button

    def add_close_button(self, *, close_text: str = "Закрыть",
                         close_callback: Callable[[], None] | None = None, ) -> QPushButton:
        close_button = self.make_button(close_text, close_callback or self.close)
        self.add_button_row(right=(close_button,))
        return close_button

    def warn(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def info(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)
