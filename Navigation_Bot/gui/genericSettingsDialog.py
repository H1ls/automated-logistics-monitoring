from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QTabWidget, QWidget
)
from Navigation_Bot.core.paths import CONFIG_JSON
from Navigation_Bot.core.jSONManager import JSONManager

"""TO DO 1.Добавить кнопку "Сбросить настройки" при клике load_data(from_default=True)"""


class GenericSettingsDialog(QWidget):
    def __init__(self, section_key: str, fields_meta: dict, parent=None):
        super().__init__(parent)
        self.section_key = section_key
        self.fields_meta = fields_meta  # { key: (label, type), … }
        self.json_manager = JSONManager(file_path=str(CONFIG_JSON))
        self._build_ui()
        self.load_data()

    def _build_ui(self):
        self.form = QFormLayout(self)
        self.edits = {}
        for key, (label, _) in self.fields_meta.items():
            edit = QLineEdit()
            self.form.addRow(QLabel(label), edit)
            self.edits[key] = edit

    def load_data(self):
        data = self.json_manager.load_json() or {}
        section = data.get(self.section_key, {})
        custom = section.get("custom", {})
        default = section.get("default", {})
        for key, edit in self.edits.items():
            if key in custom:
                edit.setText(str(custom[key]))
            elif key in default:
                edit.setText(str(default[key]))

    def save(self):
        data = self.json_manager.load_json() or {}
        section = data.setdefault(self.section_key, {})
        section["custom"] = {}
        for key, edit in self.edits.items():
            txt = edit.text()
            cast = self.fields_meta[key][1]
            try:
                section["custom"][key] = cast(txt)
            except:
                section["custom"][key] = txt
        self.json_manager.save_in_json(data)
