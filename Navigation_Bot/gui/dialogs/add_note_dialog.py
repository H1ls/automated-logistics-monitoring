from __future__ import annotations

from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QFileDialog, QLabel,
                             QListWidget)


class AddNoteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Добавить заметку")
        self.resize(600, 400)

        self.media_paths: list[str] = []

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Текст заметки:"))

        self.text_edit = QTextEdit()
        layout.addWidget(self.text_edit)

        layout.addWidget(QLabel("Прикреплённые файлы:"))

        self.files_list = QListWidget()
        layout.addWidget(self.files_list)

        buttons = QHBoxLayout()

        self.btn_add_file = QPushButton("Прикрепить фото/видео")
        self.btn_paste_clipboard = QPushButton("Вставить из буфера")
        self.btn_save = QPushButton("Сохранить")
        self.btn_cancel = QPushButton("Отмена")

        buttons.addWidget(self.btn_add_file)
        buttons.addWidget(self.btn_paste_clipboard)
        buttons.addStretch()
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_cancel)

        layout.addLayout(buttons)

        self.btn_add_file.clicked.connect(self._add_file)
        self.btn_paste_clipboard.clicked.connect(self._paste_from_clipboard)
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def _paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        # 1) Если в буфере картинка
        image = clipboard.image()
        if not image.isNull():
            media_dir = Path("config/media/clipboard")
            media_dir.mkdir(parents=True, exist_ok=True)

            filename = datetime.now().strftime("clip_%Y%m%d_%H%M%S.png")
            path = media_dir / filename

            if image.save(str(path), "PNG"):
                self.media_paths.append(str(path))
                self.files_list.addItem(path.name)
            return

        # 2) Если в буфере лежат файлы
        if mime.hasUrls():
            for url in mime.urls():
                path = url.toLocalFile()
                if path and path not in self.media_paths:
                    self.media_paths.append(path)
                    self.files_list.addItem(Path(path).name)
            return

        # 3) Если в буфере текст
        text = clipboard.text().strip()
        if text:
            self.text_edit.insertPlainText(text)

    def _add_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выбрать фото/видео",
            "",
            "Media files (*.png *.jpg *.jpeg *.webp *.mp4 *.mov *.avi);;All files (*.*)"
        )

        for path in paths:
            if path and path not in self.media_paths:
                self.media_paths.append(path)
                self.files_list.addItem(Path(path).name)

    def get_payload(self) -> dict:
        return {"text": self.text_edit.toPlainText().strip(),
                "media_paths": list(self.media_paths), }
