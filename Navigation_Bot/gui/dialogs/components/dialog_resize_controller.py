from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication


class DialogResizeController:
    def __init__(self, dialog, base_size: tuple[int, int]):
        self.dialog = dialog
        self.base_size = base_size

    def schedule(self) -> None:
        QTimer.singleShot(0, self.resize_to_content)

    def resize_to_content(self) -> None:
        self.dialog.layout().activate()
        base_width, base_height = self.base_size
        screen = self.dialog.screen() or QApplication.primaryScreen()
        max_height = int(screen.availableGeometry().height() * 0.9) if screen else 900
        desired_hint = self.dialog.sizeHint().height()
        if hasattr(self.dialog, "scroll_area") and hasattr(self.dialog, "scroll_widget"):
            desired_hint += max(
                0,
                self.dialog.scroll_widget.sizeHint().height() - self.dialog.scroll_area.sizeHint().height(),
            )
        desired_height = max(base_height, min(desired_hint, max_height))
        self.dialog.resize(max(self.dialog.width(), base_width), desired_height)
