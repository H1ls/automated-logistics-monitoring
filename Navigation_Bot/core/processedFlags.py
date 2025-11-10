from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox


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
            # если distance<1, ставим True по-умолчанию
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


def init_processed_flags(new_data: list[dict], old_data: list[dict], loads_key: str = "Выгрузка") -> None:
    def unique_key(row: dict) -> str:
        return f'{row.get("ТС", "")}_{row.get("id", "")}'

    old_map = {unique_key(r): r.get("processed", []) for r in old_data}

    for row in new_data:
        key = unique_key(row)
        prev_flags = old_map.get(key, [])
        unloads = row.get(loads_key, []) or []

        def _is_real_point(d) -> bool:
            if not isinstance(d, dict):
                return False
            pref = f"{loads_key} "
            return any(k.startswith(pref) for k in d.keys())

        cnt = sum(_is_real_point(d) for d in unloads)
        if cnt == 0:
            row["processed"] = []
            continue

        existing_flags = row.get("processed", [])
        if len(existing_flags) == cnt:
            continue  # ничего не меняем

        base_flags = existing_flags if len(existing_flags) > len(prev_flags) else prev_flags

        row["processed"] = (base_flags + [False] * cnt)[:cnt]
