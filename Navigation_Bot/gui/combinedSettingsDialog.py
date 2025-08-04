from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QWidget, QFormLayout, QLabel, QLineEdit
)
from Navigation_Bot.core.jSONManager import JSONManager
from Navigation_Bot.core.paths import CONFIG_JSON
from Navigation_Bot.bots.navigationBot import NavigationBot
from Navigation_Bot.bots.mapsBot import MapsBot
from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager

class CombinedSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.resize(600, 400)

        # JSON-менеджер
        self.json_manager = JSONManager(file_path=str(CONFIG_JSON))

        # Мета-информация по трём секциям
        self.sections = {
            "wialon_selectors": (
                "Wialon", {
                    "search_input_xpath": ("XPath поиска", str),
                    "unit_block_xpath":    ("XPath блока ТС", str),
                    "address_selector":    ("CSS адреса", str),
                    "copy_button_selector":("CSS копирования координат", str),
                    "speed_selector":      ("CSS скорости", str),
                }
            ),
            "yandex_selectors": (
                "Я.Карты", {
                    "route_button":   ("CSS кнопка маршрута", str),
                    "close_route":    ("CSS закрытия маршрута", str),
                    "from_input":     ("XPath Откуда", str),
                    "to_input":       ("XPath Куда", str),
                    "route_item":     ("CSS Результат маршрута", str),
                    "route_duration": ("CSS длительности", str),
                    "route_distance": ("CSS расстояния", str),
                }
            ),
            "google_config": (
                "Google", {
                    "creds_file":      ("Путь к creds.json", str),
                    "sheet_id":        ("ID таблицы", str),
                    "worksheet_index": ("Индекс листа", int),
                    "column_index":    ("Индекс колонки", int),
                    "file_path":       ("Путь к JSON-файлу", str),
                }
            )
        }

        # UI
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Для каждого раздела — своя форма
        self.dialogs = {}
        for section_key, (tab_name, meta) in self.sections.items():
            widget = QWidget()
            form = QFormLayout(widget)
            edits = {}

            # создаём поле
            for key, (label, _) in meta.items():
                edit = QLineEdit()
                form.addRow(QLabel(label), edit)
                edits[key] = edit

            self.tabs.addTab(widget, tab_name)
            self.dialogs[section_key] = {
                "meta": meta,
                "edits": edits
            }

        # Кнопки
        btn_row = QHBoxLayout()
        btn_save   = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        btn_save.clicked.connect(self._on_save)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        # подгружаем сразу
        self._load_all()

    def _load_all(self):
        """Загрузить все секции из JSON."""
        data = self.json_manager.load_json() or {}
        for section_key, cfg in self.dialogs.items():
            section = data.get(section_key, {})
            custom = section.get("custom", {})
            default = section.get("default", {})
            for key, edit in cfg["edits"].items():
                if key in custom:
                    edit.setText(str(custom[key]))
                elif key in default:
                    edit.setText(str(default[key]))

    def _on_save(self):
        """Сохранить все секции и принять диалог."""
        data = self.json_manager.load_json() or {}
        for section_key, cfg in self.dialogs.items():
            meta  = cfg["meta"]
            edits = cfg["edits"]
            sec   = data.setdefault(section_key, {})
            sec["custom"] = {}
            for key, edit in edits.items():
                val = edit.text()
                cast = meta[key][1]
                try:
                    sec["custom"][key] = cast(val)
                except:
                    sec["custom"][key] = val
        self.json_manager.save_in_json(data)
        if hasattr(self.parent(), "log"):
            self.parent().log("📝 Настройки сохранены.")
        self.accept()

    @staticmethod
    def open_all_settings(gui):
        dlg = CombinedSettingsDialog(parent=gui)
        if not dlg.exec():
            return
        try:
            # Wialon-бот
            if hasattr(gui, "driver_manager") and gui.driver_manager.driver:
                gui.navibot = NavigationBot(gui.driver_manager.driver, log_func=gui.log)
            # Я.Карты-бот
            if hasattr(gui, "driver_manager") and gui.driver_manager.driver:
                gui.mapsbot = MapsBot(gui.driver_manager.driver, log_func=gui.log)
            # Google Sheets
            gui.gsheet = GoogleSheetsManager(log_func=gui.log)

            gui.log("🔁 Все боты пересозданы с новыми настройками")
        except Exception as e:
            gui.log(f"❌ Ошибка при пересоздании ботов: {e}")
