from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy

from Navigation_Bot.core.domain.entities.pin_code import PinRow


class PinCardWidget(QFrame):
    def __init__(self, row: PinRow, image_path: Path | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("PinPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QGridLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(3)

        supplier_label = self._label("Поставщик", muted=True)
        supplier_value = self._label(row.supplier or "—", selectable=True)

        image_slot = QLabel("Карта")
        image_slot.setObjectName("CardImageSlot")
        image_slot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_slot.setFixedSize(72, 46)
        self._apply_image(image_slot, image_path)

        card_label = self._label("Карта", muted=True)
        card_value = self._label(row.card or "—", selectable=True)

        pin_label = self._label("ПИН", muted=True)
        pin_value = self._label(row.pin or "—", selectable=True)
        pin_value.setObjectName("PinValue")

        layout.addWidget(supplier_label, 0, 0)
        layout.addWidget(supplier_value, 1, 0)
        layout.addWidget(image_slot, 0, 1, 2, 1)
        layout.addWidget(card_label, 0, 2)
        layout.addWidget(card_value, 1, 2)
        layout.addWidget(pin_label, 0, 3)
        layout.addWidget(pin_value, 1, 3)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 2)
        layout.setColumnStretch(3, 1)

    @staticmethod
    def _label(text: str, *, muted: bool = False, selectable: bool = False) -> QLabel:
        label = QLabel(text)
        if muted:
            label.setObjectName("MutedText")
        if selectable:
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    @staticmethod
    def _apply_image(label: QLabel, image_path: Path | None) -> None:
        if not image_path:
            return

        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return

        label.setText("")
        label.setStyleSheet("background: transparent; border: none;")
        label.setPixmap(pixmap.scaled(label.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
