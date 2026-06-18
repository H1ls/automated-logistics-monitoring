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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        for idx, text in enumerate(self._loads):
            cb = QCheckBox(text)
            checked = self._processed[idx] or self._distance < 1.0
            cb.setChecked(checked)
            cb.stateChanged.connect(self._on_state_changed)
            layout.addWidget(cb)
            self._cbs.append(cb)

    def _on_state_changed(self, _):
        for i, cb in enumerate(self._cbs):
            self._processed[i] = cb.isChecked()

    def get_processed(self) -> list[bool]:
        return self._processed
