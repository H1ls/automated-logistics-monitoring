from __future__ import annotations

from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QTextEdit, QFileDialog, QLabel, QListWidget

from Navigation_Bot.core.paths import NOTE_MEDIA_DIR
from Navigation_Bot.gui.dialogs.base_dialog import BaseDialog


class AddNoteDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(title="Добавить заметку", size=(600, 400), parent=parent)

        self.media_paths: list[str] = []

        self.root.addWidget(QLabel("Текст заметки:"))

        self.text_edit = QTextEdit()
        self.root.addWidget(self.text_edit)

        self.root.addWidget(QLabel("Прикреплённые файлы:"))

        self.files_list = QListWidget()
        self.root.addWidget(self.files_list)

        self.btn_add_file = self.make_button("Прикрепить фото/видео", self._add_file)
        self.btn_paste_clipboard = self.make_button("Вставить из буфера", self._paste_from_clipboard)
        self.btn_save = self.make_button("Сохранить", self.accept)
        self.btn_cancel = self.make_button("Отмена", self.reject)
        self.add_button_row(
            left=(self.btn_add_file, self.btn_paste_clipboard),
            right=(self.btn_save, self.btn_cancel),
        )

    def _paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        # 1) Если в буфере картинка
        image = clipboard.image()
        if not image.isNull():
            media_dir = NOTE_MEDIA_DIR
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
        paths, _ = QFileDialog.getOpenFileNames(self,
            "Выбрать фото/видео",
            "",
            "Media files (*.png *.jpg *.jpeg *.webp *.mp4 *.mov *.avi);;All files (*.*)")

        for path in paths:
            if path and path not in self.media_paths:
                self.media_paths.append(path)
                self.files_list.addItem(Path(path).name)

    def get_payload(self) -> dict:
        return {"text": self.text_edit.toPlainText().strip(),
                "media_paths": list(self.media_paths), }
