from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox

class StatusEditorWidget(QWidget):
    def __init__(self, processed: list[bool], loads: list[str], distance: float, parent=None):
        super().__init__(parent)
        self._processed = list(processed)
        self._loads = loads
        self._distance = distance

        self._cbs: list[QCheckBox] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)

        for idx, text in enumerate(self._loads):
            cb = QCheckBox(text)
            # если distance<1, ставим True по-умолчанию
            checked = self._processed[idx] or self._distance < 1.0
            cb.setChecked(checked)
            cb.stateChanged.connect(self._on_state_changed)
            layout.addWidget(cb)
            self._cbs.append(cb)

    def _on_state_changed(self, _):
        # обновляем внутренний массив при любом клике
        for i, cb in enumerate(self._cbs):
            self._processed[i] = cb.isChecked()

    def get_processed(self) -> list[bool]:
        return self._processed

    def on_accept(self):
        # забираем только из статус-виджета
        self.row_data["processed"] = self.status_editor.get_processed()
        JSONManager().save_in_json(self.full_data, str(INPUT_FILEPATH))
        self.accept()

# Navigation_Bot/core/processedFlags.py
def unique_key(row: dict) -> str:
    return f"{row.get('address')}|{row.get('datetime')}"

def init_processed_flags(
    new_data: list[dict],
    old_data: list[dict],
    loads_key: str = "Выгрузка"
) -> None:
    old_map = { unique_key(r): r.get("processed", []) for r in old_data }
    for row in new_data:
        key = unique_key(row)
        prev_flags = old_map.get(key, [])
        cnt = len(row.get(loads_key, []))
        row["processed"] = (prev_flags + [False] * cnt)[:cnt]
