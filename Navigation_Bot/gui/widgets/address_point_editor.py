from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QHBoxLayout,
                             QLabel,
                             QLineEdit,
                             QPushButton,
                             QSpinBox,
                             QTextEdit,
                             QVBoxLayout,
                             QWidget)

from Navigation_Bot.core.infrastructure.persistence.sites_db_registry import SitesDbRegistry
from Navigation_Bot.gui.dialogs.components.address_edit_models import AddressPointDraft
from Navigation_Bot.core.logging import noop_log, normalize_log_func


class AddressPointEditor(QWidget):
    def __init__(self,
                 *,
                 prefix: str,
                 point: AddressPointDraft,
                 sites_registry: SitesDbRegistry,
                 on_delete: Callable[["AddressPointEditor"], None],
                 on_edit_sites: Callable[[str], None],
                 on_address_changed: Callable[["AddressPointEditor", str], None] | None = None,
                 log: Callable[[str], None] | None = None,
                 parent=None):
        super().__init__(parent)
        self.prefix = prefix
        self.sites_registry = sites_registry
        self.on_delete = on_delete
        self.on_edit_sites = on_edit_sites
        self.on_address_changed = on_address_changed
        self.log = normalize_log_func(log or noop_log)
        self._metadata: dict[str, str] = {}
        self.site_id = ""
        self.geo_tags: list[str] = []

        self._build_ui(point)
        self.refresh_site_match()

    def _build_ui(self, point: AddressPointDraft) -> None:
        wrapper = QVBoxLayout(self)
        wrapper.setSpacing(8)
        wrapper.setContentsMargins(0, 0, 0, 0)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.drag_handle = QPushButton("☰")
        self.drag_handle.setFixedWidth(30)
        self.drag_handle.setToolTip("Перетащить точку")
        self.drag_handle.setProperty("address_drag_handle", True)
        self.drag_handle.setProperty("address_editor", self)
        self.drag_handle.setCursor(Qt.CursorShape.OpenHandCursor)

        btn_geo = QPushButton("🏷")
        btn_geo.setFixedWidth(30)
        btn_geo.setToolTip("Редактор геозон/складов")
        btn_geo.clicked.connect(lambda: self.on_edit_sites(self.address()))

        self.tags_label = QLabel("")
        self.tags_label.setStyleSheet("color: #666;")
        self.tags_label.hide()

        self.departure_date_edit = self._date_edit()
        self.departure_time_edit = self._time_edit()
        self.transit_spin = QSpinBox()
        self.transit_spin.setRange(0, 999)
        self.transit_spin.setSuffix(" ч")

        btn_calculate = QPushButton("🧮")
        btn_calculate.setFixedWidth(30)
        btn_calculate.setToolTip("Рассчитать время прибытия")
        btn_calculate.clicked.connect(self._calculate_arrival)

        top_row.addWidget(self.drag_handle)
        top_row.addWidget(btn_geo)
        top_row.addWidget(QLabel(self.prefix))
        top_row.addWidget(self.tags_label)
        top_row.addStretch()
        top_row.addWidget(QLabel("Дата выезда:"))
        top_row.addWidget(self.departure_date_edit)
        top_row.addWidget(self.departure_time_edit)
        top_row.addWidget(QLabel("Транзит:"))
        top_row.addWidget(self.transit_spin)
        top_row.addWidget(btn_calculate)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        self.address_edit = QTextEdit(point.address)
        self.address_edit.setPlaceholderText("Адрес")
        self.address_edit.setFixedHeight(24)
        self.address_edit.setAcceptDrops(False)
        self.address_edit.textChanged.connect(self._address_changed)

        self.arrival_date_edit = self._date_edit(point.date)
        self.arrival_time_edit = self._time_edit(point.time)

        btn_delete = QPushButton("🗑️")
        btn_delete.setFixedWidth(30)
        btn_delete.setToolTip("Удалить точку")
        btn_delete.clicked.connect(lambda: self.on_delete(self))

        bottom_row.addWidget(self.address_edit, 1)
        bottom_row.addWidget(self.arrival_date_edit)
        bottom_row.addWidget(self.arrival_time_edit)
        bottom_row.addWidget(btn_delete)

        wrapper.addLayout(top_row)
        wrapper.addLayout(bottom_row)

        self.departure_date_edit.editingFinished.connect(
            lambda: self._normalize_date(self.departure_date_edit))
        self.arrival_date_edit.editingFinished.connect(
            lambda: self._normalize_date(self.arrival_date_edit))
        self.departure_time_edit.editingFinished.connect(
            lambda: self._normalize_time(self.departure_time_edit))
        self.arrival_time_edit.editingFinished.connect(
            lambda: self._normalize_time(self.arrival_time_edit))

    @staticmethod
    def _date_edit(value: str = "") -> QLineEdit:
        editor = QLineEdit()
        editor.setInputMask("00.00.0000")
        editor.setPlaceholderText("дд.мм.гггг")
        editor.setFixedWidth(80)
        editor.setAcceptDrops(False)
        if value:
            editor.setText(value)
        return editor

    @staticmethod
    def _time_edit(value: str = "") -> QLineEdit:
        editor = QLineEdit()
        editor.setInputMask("00:00")
        editor.setPlaceholderText("чч:мм")
        editor.setFixedWidth(60)
        editor.setAcceptDrops(False)
        if value:
            editor.setText(value[:5])
        return editor

    def address(self) -> str:
        return self.address_edit.toPlainText().strip()

    def to_draft(self) -> AddressPointDraft:
        return AddressPointDraft(address=self.address(),
                                 date=self._optional_masked_text(self.arrival_date_edit),
                                 time=self._optional_masked_text(self.arrival_time_edit))

    def metadata(self) -> dict[str, str]:
        return dict(self._metadata)

    def archive_dict(self) -> dict[str, str] | None:
        point = self.to_draft()
        if not point.address:
            return None
        return {"Адрес": point.address, "Дата": point.date, "Время": point.time}

    def refresh_site_match(self) -> None:
        match = self.sites_registry.match(self.address())
        if match and match.geofence:
            self.site_id = match.site_id
            self.geo_tags = [match.geofence]
            self.tags_label.setText(f"  🏷 {match.geofence}")
            self.tags_label.show()
            return

        self.site_id = ""
        self.geo_tags = []
        self.tags_label.clear()
        self.tags_label.hide()

    def _address_changed(self) -> None:
        self.refresh_site_match()
        if self.on_address_changed:
            self.on_address_changed(self, self.address())

    def _calculate_arrival(self) -> None:
        try:
            departure_date = datetime.strptime(self.departure_date_edit.text().strip(), "%d.%m.%Y")
            departure_time = datetime.strptime(self.departure_time_edit.text().strip(), "%H:%M").time()
            if self.transit_spin.value() <= 0:
                return
            departure = datetime.combine(departure_date.date(), departure_time)
            arrival = departure + timedelta(hours=self.transit_spin.value())
            self.arrival_date_edit.setText(arrival.strftime("%d.%m.%Y"))
            self.arrival_time_edit.setText(arrival.strftime("%H:%M"))
            self._metadata = {"Время отправки": departure.strftime("%d.%m.%Y %H:%M"),
                              "Транзит": f"{self.transit_spin.value()} ч"}
        except (TypeError, ValueError) as exc:
            self.log(f"[DEBUG] ❌ Ошибка расчёта: {exc}")

    @staticmethod
    def _normalize_date(editor: QLineEdit) -> None:
        text = editor.text().strip()
        if not text:
            return
        parts = text.split(".")
        try:
            if len(parts) == 1 or (len(parts) == 3 and not parts[1] and not parts[2]):
                now = datetime.now()
                editor.setText(f"{int(parts[0]):02d}.{now.month:02d}.{now.year}")
        except ValueError:
            return

    @staticmethod
    def _normalize_time(editor: QLineEdit) -> None:
        text = editor.text().strip().replace("_", "")
        if not text:
            return
        try:
            parts = text.split(":")
            hours = int(parts[0] or 0)
            minutes = int(parts[1] or 0) if len(parts) > 1 else 0
            editor.setText(f"{hours:02d}:{minutes:02d}")
        except ValueError:
            return

    @staticmethod
    def _optional_masked_text(editor: QLineEdit) -> str:
        text = editor.text().strip()
        return text if any(character.isdigit() for character in text) else ""
