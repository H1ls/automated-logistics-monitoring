from __future__ import annotations

from PyQt6.QtWidgets import (QLabel,
                             QPushButton,
                             QScrollArea,
                             QTextEdit,
                             QVBoxLayout,
                             QWidget)

from LogistX.config.paths import SITES_DB_FILE
from Navigation_Bot.core.infrastructure.persistence.sites_db_registry import SitesDbRegistry
from Navigation_Bot.gui.dialogs.components.address_archive_service import AddressArchiveService
from Navigation_Bot.gui.dialogs.components.address_drag_controller import AddressPointDragController
from Navigation_Bot.gui.dialogs.components.address_edit_models import AddressBlocksCodec, AddressPointDraft
from Navigation_Bot.gui.dialogs.base_dialog import BaseDialog
from Navigation_Bot.gui.dialogs.components.dialog_helpers import button_row_split
from Navigation_Bot.gui.dialogs.components.dialog_resize_controller import DialogResizeController
from Navigation_Bot.gui.dialogs.components.address_result_builder import AddressResultBuilder
from Navigation_Bot.gui.dialogs.sites_db_editor_dialog import SitesDbEditorDialog
from Navigation_Bot.gui.widgets.address_point_editor import AddressPointEditor
from Navigation_Bot.gui.widgets.status_editor_widget import StatusEditorWidget


class AddressEditDialog(BaseDialog):
    """Редактирует адресные точки и возвращает legacy-блоки для task workflow."""

    def __init__(self,row_data,prefix,parent=None,log_func=None):
        self._base_size = (1000, 500)
        super().__init__(title=f"Редактирование: {prefix}", size=self._base_size, parent=parent, log_func=log_func)

        self.prefix = prefix
        self.row_data = row_data
        self.raw_key = "raw_load" if prefix == "Погрузка" else "raw_unload"

        self.codec = AddressBlocksCodec(prefix)
        self.sites_registry = SitesDbRegistry(log_func=self.log, path=SITES_DB_FILE)
        points, comment = self.codec.parse(self.row_data.get(prefix, []) or [])
        self._processed_seed = self._read_processed_flags()
        self.entries: list[AddressPointEditor] = []
        self.archive_service = AddressArchiveService(log_func=self.log)
        self.drag_controller = AddressPointDragController(self)
        self.resize_controller = DialogResizeController(self, self._base_size)

        self._build_ui(points, comment)

    def _build_ui(self, points: list[AddressPointDraft], comment: str) -> None:
        self.main_layout = self.root

        self.status_editor = self._build_status_editor(points)
        if self.status_editor is not None:
            self.main_layout.addWidget(self.status_editor)

        self.raw_edit = QTextEdit(str(self.row_data.get(self.raw_key) or "").strip())
        self.raw_edit.setPlaceholderText(self.raw_key)
        self.raw_edit.setFixedHeight(50)
        self.main_layout.addWidget(self.raw_edit)

        self.main_layout.addWidget(QLabel("Комментарий:"))
        self.comment_edit = QTextEdit(comment)
        self.comment_edit.setPlaceholderText(f"{self.prefix} другое / комментарий")
        self.comment_edit.setFixedHeight(60)
        self.main_layout.addWidget(self.comment_edit)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.addStretch(1)
        self.scroll_area.setWidget(self.scroll_widget)
        self.main_layout.addWidget(self.scroll_area)
        self.drag_controller.install_on_scroll_widget()

        for point in points:
            self.add_entry(point.address, point.date, point.time, sync_status=False)

        self.btn_add = QPushButton("➕ Добавить точку")
        self.btn_add.clicked.connect(self.add_entry)
        self.btn_archive = QPushButton("📦 В архив")
        self.btn_archive.clicked.connect(self._archive_sample)
        self.btn_save = QPushButton("✅ Сохранить")
        self.btn_save.clicked.connect(self.accept)
        self.main_layout.addLayout(button_row_split((self.btn_add,), (self.btn_archive, self.btn_save)))
        self.schedule_resize_to_content()

    def _build_status_editor(self, points: list[AddressPointDraft]) -> StatusEditorWidget | None:
        if self.prefix != "Выгрузка" or len(points) <= 1:
            return None

        flags = list(self._processed_seed)
        flags = (flags + [False] * len(points))[:len(points)]
        return StatusEditorWidget(processed=flags,
                                  loads=[point.address for point in points],
                                  distance=self.row_data.get("distance", float("inf")))

    def _read_processed_flags(self) -> list[bool]:
        processed = self.row_data.get("processed_unloads")
        if not isinstance(processed, list):
            processed = self.row_data.get("processed", [])
        return [bool(value) for value in processed] if isinstance(processed, list) else []

    def add_entry(self, address="", date="", time="", sync_status=True) -> AddressPointEditor:
        point = AddressPointDraft(address=str(address or ""),
                                  date=str(date or ""),
                                  time=str(time or ""))
        editor = AddressPointEditor(prefix=self.prefix,
                                    point=point,
                                    sites_registry=self.sites_registry,
                                    on_delete=self.remove_entry,
                                    on_edit_sites=self.open_sites_editor,
                                    on_address_changed=self._on_address_changed,
                                    log=self.log,
                                    parent=self.scroll_widget)
        self.entries.append(editor)
        self.drag_controller.install_on_editor(editor)
        self.scroll_layout.insertWidget(max(self.scroll_layout.count() - 1, 0), editor)
        if sync_status:
            if self.status_editor is not None:
                self.status_editor.add_item(point.address)
            elif self.prefix == "Выгрузка" and len(self.entries) > 1:
                self.status_editor = self._build_status_editor(
                    [entry.to_draft() for entry in self.entries])
                if self.status_editor is not None:
                    self.main_layout.insertWidget(0, self.status_editor)
        self.schedule_resize_to_content()
        return editor

    def remove_entry(self, editor: AddressPointEditor) -> None:
        if editor not in self.entries:
            return
        index = self.entries.index(editor)
        self.entries.remove(editor)
        if self.status_editor is not None:
            self.status_editor.remove_item(index)
            if len(self.entries) <= 1:
                self._processed_seed = self.status_editor.get_processed()
                self.main_layout.removeWidget(self.status_editor)
                self.status_editor.deleteLater()
                self.status_editor = None
        self.scroll_layout.removeWidget(editor)
        editor.deleteLater()
        self.schedule_resize_to_content()

    def eventFilter(self, watched, event):
        if self.drag_controller.event_filter(watched, event):
            return True
        return super().eventFilter(watched, event)

    def _move_entry(self, editor: AddressPointEditor, target_index: int) -> None:
        self.drag_controller.move_entry(editor, target_index)

    def schedule_resize_to_content(self) -> None:
        self.resize_controller.schedule()

    def _on_address_changed(self, editor: AddressPointEditor, address: str) -> None:
        if self.status_editor is None or editor not in self.entries:
            return
        self.status_editor.set_item_text(self.entries.index(editor), address)

    def open_sites_editor(self, prefill_address: str = "") -> None:
        dialog = SitesDbEditorDialog(parent=self,
                                     prefill_address=prefill_address,
                                     log_func=self.log)
        dialog.exec()
        self.sites_registry.reload()
        for editor in self.entries:
            editor.refresh_site_match()

    def get_processed(self) -> list[bool] | None:
        return self._result_builder().get_processed()

    def get_raw_value(self) -> str:
        return self.raw_edit.toPlainText().strip()

    def get_result(self) -> tuple[list[dict[str, str]], dict[str, str]]:
        return self._result_builder().build_result(self.comment_edit.toPlainText())

    def _result_builder(self) -> AddressResultBuilder:
        return AddressResultBuilder(codec=self.codec,
                                    entries=self.entries,
                                    status_editor=self.status_editor)

    def _archive_sample(self) -> None:
        self.archive_service.archive_sample(editors=self.entries,
                                            comment=self.comment_edit.toPlainText(),
                                            raw_input=self.get_raw_value())
