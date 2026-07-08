from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QGridLayout,
                             QGroupBox,
                             QHBoxLayout,
                             QLabel,
                             QLineEdit,
                             QLayout,
                             QPushButton,
                             QSizePolicy,
                             QTextEdit,
                             QVBoxLayout,
                             QWidget)

from LogistX.config.paths import SITES_DB_FILE
from Navigation_Bot.core.infrastructure.persistence.sites_db_registry import SitesDbRegistry
from Navigation_Bot.gui.dialogs.base_dialog import BaseDialog
from Navigation_Bot.gui.dialogs.components.address_edit_models import AddressBlocksCodec, AddressPointDraft
from Navigation_Bot.gui.dialogs.components.create_race_lazy_parser import CreateRaceLazyParser
from Navigation_Bot.gui.dialogs.components.create_race_suggestions import CreateRaceSuggestions
from Navigation_Bot.gui.dialogs.sites_db_editor_dialog import SitesDbEditorDialog
from Navigation_Bot.gui.widgets.address_point_editor import AddressPointEditor


class CreateRaceDialog(BaseDialog):
    """
    Диалог создания новой задачи / рейса.

    Собирает поля рейса и встроенные точки погрузки/выгрузки в legacy-buffer,
    который дальше обрабатывает NewTaskWorkflowService.
    """

    ADDRESS_SECTION_MIN_HEIGHT = 220

    def __init__(self, task_repository, log_func=None, parent=None):
        super().__init__(title="Создать рейс", size=(1000, 760), parent=parent, log_func=log_func)
        self.task_repository = task_repository
        self.sites_registry = SitesDbRegistry(log_func=self.log, path=SITES_DB_FILE)
        self.suggestions = CreateRaceSuggestions(task_repository=task_repository, log=self.log)
        self.lazy_parser = CreateRaceLazyParser(task_repository=task_repository, log=self.log)
        self.load_codec = AddressBlocksCodec("Погрузка")
        self.unload_codec = AddressBlocksCodec("Выгрузка")

        self.load_entries: list[AddressPointEditor] = []
        self.unload_entries: list[AddressPointEditor] = []
        self._buffer: dict[str, Any] = {"Погрузка": [], "Выгрузка": []}
        self._upload_to_google = False

        self._build_ui()
        self._install_completers()
        self.add_load_entry()
        self.add_unload_entry()

    # --- UI
    def _build_ui(self) -> None:
        self.edit_ts = QLineEdit()
        self.edit_phone = QLineEdit()
        self.edit_ka = QLineEdit()
        self.edit_fio = QLineEdit()
        self.edit_fio2 = QLineEdit()
        self.edit_lazy = QTextEdit()

        self.edit_ts.setPlaceholderText(" А123БВ 777")
        self.edit_phone.setPlaceholderText(" 79001234567")
        self.edit_ka.setPlaceholderText("КА")
        self.edit_fio.setPlaceholderText("ФИО")
        self.edit_fio2.setPlaceholderText("ФИО")
        self.edit_lazy.setPlaceholderText("Исходная заявка")
        self.edit_lazy.setFixedHeight(120)

        self.edit_ts.setFixedWidth(140)
        self.edit_phone.setFixedWidth(140)
        self.edit_ka.setMinimumWidth(350)
        self.edit_fio.setMinimumWidth(390)
        self.edit_fio2.setMinimumWidth(390)

        top_grid = QGridLayout()
        top_grid.setHorizontalSpacing(12)
        top_grid.setVerticalSpacing(12)
        top_grid.setColumnStretch(5, 1)
        top_grid.addWidget(QLabel("ТС:"), 0, 0)
        top_grid.addWidget(self.edit_ts, 0, 1)
        top_grid.addWidget(QLabel("Телефон:"), 0, 2)
        top_grid.addWidget(self.edit_phone, 0, 3)
        top_grid.addWidget(QLabel("ФИО:"), 0, 4)
        top_grid.addWidget(self.edit_fio, 0, 5)
        top_grid.addWidget(QLabel("КА:"), 1, 0)
        top_grid.addWidget(self.edit_ka, 1, 1, 1, 3)
        top_grid.addWidget(QLabel("ФИО2:"), 1, 4)
        top_grid.addWidget(self.edit_fio2, 1, 5)
        self.root.addLayout(top_grid)

        lazy_group = QGroupBox("Лентяй:")
        lazy_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        lazy_layout = QVBoxLayout(lazy_group)
        lazy_layout.setContentsMargins(8, 8, 8, 8)
        lazy_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        lazy_layout.addWidget(self.edit_lazy)
        lazy_group.setFixedHeight(lazy_group.sizeHint().height())
        self.root.addWidget(lazy_group)

        self.load_section, self.load_points_layout = self._build_points_section(
            title="Погрузка",
            button_text="Добавить точку",
            callback=self.add_load_entry,
        )
        self.unload_section, self.unload_points_layout = self._build_points_section(
            title="Выгрузка",
            button_text="Добавить точку",
            callback=self.add_unload_entry,
        )
        self.root.addWidget(self.load_section, 0, Qt.AlignmentFlag.AlignTop)
        self.root.addWidget(self.unload_section, 0, Qt.AlignmentFlag.AlignTop)

        self.btn_save = self.make_button("Сохранить",
                                         lambda: self._accept_if_valid(upload_to_google=False))
        self.btn_save_send = self.make_button("Сохранить и отправить",
                                              lambda: self._accept_if_valid(upload_to_google=True))
        self.btn_cancel = self.make_button("Отмена", self.reject)
        self.add_button_row(right=(self.btn_save, self.btn_save_send, self.btn_cancel))

    def _build_points_section(self, *, title: str, button_text: str, callback) -> tuple[QGroupBox, QVBoxLayout]:
        group = QGroupBox(title)
        group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        group.setMinimumHeight(self.ADDRESS_SECTION_MIN_HEIGHT)

        wrapper = QVBoxLayout(group)
        wrapper.setSpacing(8)
        wrapper.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)

        header = QHBoxLayout()
        header.addStretch(1)
        button = QPushButton(button_text)
        button.clicked.connect(callback)
        header.addWidget(button)
        wrapper.addLayout(header)

        points_widget = QWidget(group)
        points_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        points_layout = QVBoxLayout(points_widget)
        points_layout.setContentsMargins(0, 0, 0, 0)
        points_layout.setSpacing(10)
        points_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)

        wrapper.addWidget(points_widget)
        return group, points_layout

    # --- completers
    def _install_completers(self) -> None:
        self.suggestions.install(ts_editor=self.edit_ts,
                                 carrier_editor=self.edit_ka,
                                 driver_editor=self.edit_fio,
                                 second_driver_editor=self.edit_fio2)

    # --- address entries
    def add_load_entry(self, address: str = "", date: str = "", time: str = "") -> AddressPointEditor:
        return self._add_entry("Погрузка", self.load_entries, self.load_points_layout, address, date, time)

    def add_unload_entry(self, address: str = "", date: str = "", time: str = "") -> AddressPointEditor:
        return self._add_entry("Выгрузка", self.unload_entries, self.unload_points_layout, address, date, time)

    def _add_entry(self,
                   prefix: str,
                   entries: list[AddressPointEditor],
                   layout: QVBoxLayout,
                   address: str = "",
                   date: str = "",
                   time: str = "") -> AddressPointEditor:
        point = AddressPointDraft(address=str(address or ""),
                                  date=str(date or ""),
                                  time=str(time or ""))
        editor = AddressPointEditor(prefix=prefix,
                                    point=point,
                                    sites_registry=self.sites_registry,
                                    on_delete=self.remove_entry,
                                    on_edit_sites=self.open_sites_editor,
                                    on_address_changed=None,
                                    log=self.log,
                                    parent=layout.parentWidget())
        editor.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        entries.append(editor)
        layout.addWidget(editor)
        self._refresh_points_section(layout)
        return editor

    def remove_entry(self, editor: AddressPointEditor) -> None:
        if editor in self.load_entries:
            self.load_entries.remove(editor)
            self.load_points_layout.removeWidget(editor)
        elif editor in self.unload_entries:
            self.unload_entries.remove(editor)
            self.unload_points_layout.removeWidget(editor)
        else:
            return
        editor.deleteLater()
        self._refresh_points_section(self.load_points_layout)
        self._refresh_points_section(self.unload_points_layout)

    def _refresh_points_section(self, layout: QVBoxLayout) -> None:
        widget = layout.parentWidget()
        if widget is None:
            return
        section = widget.parentWidget()
        widget.adjustSize()
        widget.updateGeometry()
        if section is not None:
            section.setMinimumHeight(0)
            section.setMaximumHeight(16777215)
            section.setFixedHeight(max(section.sizeHint().height(), self.ADDRESS_SECTION_MIN_HEIGHT))
            section.adjustSize()
            section.updateGeometry()

    def open_sites_editor(self, prefill_address: str = "") -> None:
        dialog = SitesDbEditorDialog(parent=self,
                                     prefill_address=prefill_address,
                                     log_func=self.log)
        dialog.exec()
        self.sites_registry.reload()
        for editor in [*self.load_entries, *self.unload_entries]:
            editor.refresh_site_match()

    # --- helpers
    def _sync_buffer(self) -> None:
        self._buffer["Погрузка"], load_meta = self._build_blocks(self.load_codec, self.load_entries)
        self._buffer["Выгрузка"], unload_meta = self._build_blocks(self.unload_codec, self.unload_entries)
        for meta in (load_meta, unload_meta):
            if meta.get("Время отправки"):
                self._buffer["Время отправки"] = meta["Время отправки"]
            if meta.get("Транзит"):
                self._buffer["Транзит"] = meta["Транзит"]

    def _apply_lazy_text_if_needed(self) -> None:
        self._buffer = self.lazy_parser.apply_if_needed(self.edit_lazy.toPlainText(), self._buffer)

    @staticmethod
    def _build_blocks(codec: AddressBlocksCodec,
                      entries: list[AddressPointEditor]) -> tuple[list[dict[str, str]], dict[str, str]]:
        points = [entry.to_draft() for entry in entries]
        blocks = codec.serialize(points, "")
        metadata: dict[str, str] = {}
        for entry in entries:
            metadata.update(entry.metadata())
        return blocks, metadata

    # --- actions
    def _accept_if_valid(self, *, upload_to_google: bool = False) -> None:
        self._sync_buffer()
        self._apply_lazy_text_if_needed()

        ts = self.edit_ts.text().strip()
        ka = self.edit_ka.text().strip()
        fio = self.edit_fio.text().strip()

        if not ts:
            self.warn("Проверка", "Заполни поле ТС.")
            return

        if not ka:
            self.warn("Проверка", "Заполни поле КА.")
            return

        if not fio:
            self.warn("Проверка", "Заполни поле ФИО.")
            return

        if not self._buffer.get("Погрузка"):
            self.warn("Проверка", "Добавь погрузку.")
            return

        if not self._buffer.get("Выгрузка"):
            self.warn("Проверка", "Добавь выгрузку.")
            return

        self._upload_to_google = bool(upload_to_google)
        self.accept()

    # --- public
    def get_payload(self) -> dict:
        self._sync_buffer()
        self._apply_lazy_text_if_needed()
        return {"ts": self.edit_ts.text().strip(),
                "phone": self.edit_phone.text().strip(),
                "ka": self.edit_ka.text().strip(),
                "fio": self.edit_fio.text().strip(),
                "fio2": self.edit_fio2.text().strip(),
                "lazy": self.edit_lazy.toPlainText().strip(),
                "buffer": dict(self._buffer),
                "upload_to_google": self._upload_to_google}
