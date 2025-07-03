from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFormLayout
)
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import CONFIG_JSON
"""TO DO 1.Добавить кнопку "Сбросить настройки" при клике load_data(from_default=True)

"""


class GenericSettingsDialog(QDialog):
    def __init__(self, parent,
                 title: str,
                 section_index: int,
                 section_key: str,
                 custom_key: str,
                 default_key: str,
                 fields: dict[str, tuple[str, type]],
                 file_path: str = str(CONFIG_JSON)):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(500)

        self.section_key = section_key
        self.custom_key = custom_key
        self.default_key = default_key
        self.fields_meta = fields
        self.fields_edits = {}
        self.json_manager = JSONManager(file_path=file_path)

        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout()
        form = QFormLayout()

        for key, (label, _) in self.fields_meta.items():
            edit = QLineEdit()
            edit.setObjectName(key)
            form.addRow(QLabel(label), edit)
            self.fields_edits[key] = edit

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Сохранить")
        cancel_btn = QPushButton("Отмена")
        save_btn.clicked.connect(self.save)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def load_data(self):
        try:
            data = self.json_manager.load_json()
            if not isinstance(data, dict):
                return

            section = data.get(self.section_key, {})
            current = section.get("custom", {})
            default = section.get("default", {})

            for key, edit in self.fields_edits.items():
                if key in current:
                    edit.setText(str(current[key]))
                elif key in default:
                    edit.setText(str(default[key]))

        except Exception as e:
            if hasattr(self.parent(), "log"):
                self.parent().log(f"⚠️ Ошибка загрузки настроек: {e}")
            else:
                print(f"⚠️ Ошибка загрузки настроек: {e}")

    def save(self):
        try:
            data = self.json_manager.load_json()
            if not isinstance(data, dict):
                data = {}

            if self.section_key not in data:
                data[self.section_key] = {}

            section = data[self.section_key]
            section["custom"] = {}

            for key, edit in self.fields_edits.items():
                cast_type = self.fields_meta[key][1]
                value = edit.text()
                try:
                    section["custom"][key] = cast_type(value)
                except ValueError:
                    section["custom"][key] = value

            self.json_manager.save_in_json(data)

            if hasattr(self.parent(), "log"):
                self.parent().log(f"📝 Настройки '{self.windowTitle()}' сохранены.")
            self.done(QDialog.DialogCode.Accepted)

        except Exception as e:
            if hasattr(self.parent(), "log"):
                self.parent().log(f"❌ Ошибка сохранения: {e}")
            else:
                print(f"❌ Ошибка сохранения: {e}")
