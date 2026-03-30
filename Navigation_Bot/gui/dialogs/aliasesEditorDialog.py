from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QPlainTextEdit

from Navigation_Bot.gui.dialogs.dialog_helpers import button_row_trailing


class AliasesEditorDialog(QDialog):
    """Многострочный редактор списка aliases (по одному значению на строку)."""

    def __init__(self, parent=None, aliases=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование списка значений (aliases)")
        self.resize(520, 360)

        lay = QVBoxLayout(self)
        self.edit = QPlainTextEdit(self)
        lay.addWidget(self.edit)

        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Отмена")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        lay.addLayout(button_row_trailing(self.btn_ok, self.btn_cancel))

        aliases = aliases or []
        self.edit.setPlainText("\n".join(aliases))

    def get_aliases(self) -> list[str]:
        text = self.edit.toPlainText().replace("\r\n", "\n").replace("\r", "\n")
        return [line.strip() for line in text.split("\n") if line.strip()]