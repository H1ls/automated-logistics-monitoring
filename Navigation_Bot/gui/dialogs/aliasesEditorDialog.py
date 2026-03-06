from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit

class AliasesEditorDialog(QDialog):
    def __init__(self, parent=None, aliases=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование списка значений (aliases)")
        self.resize(520, 360)

        lay = QVBoxLayout(self)
        self.edit = QPlainTextEdit(self)
        lay.addWidget(self.edit)

        btns = QHBoxLayout()
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Отмена")
        btns.addStretch(1)
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        lay.addLayout(btns)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        aliases = aliases or []
        self.edit.setPlainText("\n".join(aliases))

    def get_aliases(self) -> list[str]:
        text = self.edit.toPlainText().replace("\r\n", "\n").replace("\r", "\n")
        return [line.strip() for line in text.split("\n") if line.strip()]