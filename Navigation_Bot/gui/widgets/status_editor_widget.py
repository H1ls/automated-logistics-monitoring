from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QVBoxLayout, QWidget


class StatusEditorWidget(QWidget):
    def __init__(self, processed: list[bool], loads: list[str], distance: float, parent=None):
        super().__init__(parent)
        self._loads = loads
        self._distance = distance
        self._processed = (processed + [False] * len(loads))[:len(loads)]

        self._cbs: list[QCheckBox] = []
        self._build_ui()

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        for idx, text in enumerate(self._loads):
            self._append_checkbox(text, self._processed[idx])

    def add_item(self, text: str, processed: bool = False) -> None:
        self._loads.append(text)
        self._processed.append(bool(processed))
        self._append_checkbox(text, processed)

    def remove_item(self, index: int) -> None:
        if not (0 <= index < len(self._cbs)):
            return
        checkbox = self._cbs.pop(index)
        self._loads.pop(index)
        self._processed.pop(index)
        self._layout.removeWidget(checkbox)
        checkbox.deleteLater()

    def set_item_text(self, index: int, text: str) -> None:
        if not (0 <= index < len(self._cbs)):
            return
        self._loads[index] = text
        self._cbs[index].setText(text)

    def _append_checkbox(self, text: str, processed: bool) -> None:
        checkbox = QCheckBox(text)
        checkbox.setChecked(bool(processed) or self._distance < 1.0)
        checkbox.stateChanged.connect(self._on_state_changed)
        self._layout.addWidget(checkbox)
        self._cbs.append(checkbox)

    def _on_state_changed(self, _):
        for i, cb in enumerate(self._cbs):
            self._processed[i] = cb.isChecked()

    def get_processed(self) -> list[bool]:
        return [cb.isChecked() for cb in self._cbs]
