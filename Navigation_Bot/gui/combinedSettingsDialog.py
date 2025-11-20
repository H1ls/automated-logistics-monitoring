from PyQt6.QtWidgets import (QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QStyledItemDelegate,
                             QLineEdit, QSpinBox, QCheckBox, QPushButton, QHBoxLayout, QMessageBox,
                             QTableWidgetItem, QLabel, QStyle, QStyleOptionViewItem, QApplication)

from PyQt6.QtCore import pyqtSignal, QRect, Qt, QTimer
from PyQt6.QtGui import QPainter, QColor

import json

from Navigation_Bot.core.settings_schema import SECTIONS
from Navigation_Bot.core.jSONManager import JSONManager as JM
from Navigation_Bot.core.paths import CONFIG_JSON
from Navigation_Bot.bots.mapsBot import MapsBot
from Navigation_Bot.bots.navigationBot import NavigationBot
from Navigation_Bot.bots.googleSheetsManager import GoogleSheetsManager


class CombinedSettingsDialog(QDialog):
    settings_changed = pyqtSignal(set)
    clear_json_requested = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.resize(650, 350)
        self._forms = {}  # section_key -> SectionForm
        self._dirty = set()  # какие секции менялись с момента открытия

        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        for section_key, (title, fields) in SECTIONS.items():
            form = SectionForm(section_key, title, fields, self)
            # помечаем секцию при любом изменении
            for w in form._widgets.values():
                if hasattr(w, "textChanged"):
                    w.textChanged.connect(lambda _=None, s=section_key: self._dirty.add(s))
                elif hasattr(w, "stateChanged"):
                    w.stateChanged.connect(lambda _=None, s=section_key: self._dirty.add(s))
                elif hasattr(w, "valueChanged"):
                    w.valueChanged.connect(lambda _=None, s=section_key: self._dirty.add(s))

            self._forms[section_key] = form
            self.tabs.addTab(form, title)

        btns = QHBoxLayout()
        self.btn_save = QPushButton("Сохранить")
        self.btn_cancel = QPushButton("Отмена")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(self.btn_save)
        btns.addWidget(self.btn_cancel)
        root.addLayout(btns)

    def _validate_required(self) -> tuple[bool, str]:
        for s_key, (title, fields) in SECTIONS.items():
            form = self._forms[s_key]
            for key, (label, tp, required) in fields.items():
                if not required:
                    continue
                val = form.values().get(key, "")
                if (tp is str and not str(val).strip()) or (tp is int and val is None):
                    return False, f"В секции «{title}» заполните обязательное поле: {label}"
        return True, ""

    def on_settings_changed(self, sections: set):
        if "google_config" in sections:
            self.gsheet = GoogleSheetsManager(log_func=self.log)
            self.log("🔁 GoogleSheetsManager пересоздан по новым настройкам")

        driver = getattr(getattr(self, "processor", None), "driver_manager", None)
        driver = getattr(driver, "driver", None)

        if "wialon_selectors" in sections and driver:
            self.processor.navibot = NavigationBot(driver, log_func=self.log)
            self.log("🔁 NavigationBot пересоздан")

        if "yandex_selectors" in sections:

            dm = getattr(self.processor, "driver_manager", None)
            if dm:
                self.processor.mapsbot = MapsBot(dm, log_func=self.log)
                self.log("🔁 MapsBot пересоздан")
            else:
                self.log("ℹ️ MapsBot обновится при запуске драйвера")

        if {"wialon_selectors", "yandex_selectors"} & sections and not driver:
            self.log("ℹ️ Селекторы применятся при старте веб-драйвера")

    def clear_json(self):
        """Очистка основного JSON через parent (NavigationGUI)."""
        parent_gui = self.parent()
        if not parent_gui:
            QMessageBox.warning(self, "Ошибка", "Родительское окно не найдено.")
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение очистки",
            "Вы действительно хотите очистить все данные из JSON?\nЭто действие необратимо.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        data_context = getattr(parent_gui, "data_context", None)
        table_manager = getattr(parent_gui, "table_manager", None)

        if data_context is not None:
            data_context.set([])

        if table_manager is not None:
            table_manager.display()

    def _on_save(self):
        ok, msg = self._validate_required()
        if not ok:
            QMessageBox.warning(self, "Проверка", msg)
            return

        if not self._dirty:
            self.accept()
            return

        cfg = _read_config()
        changed = set()

        for s_key in self._dirty:
            form = self._forms[s_key]
            val = form.values()
            node = cfg.setdefault(s_key, {})
            node.setdefault("default", node.get("default", {}))
            node["custom"] = val
            changed.add(s_key)

        _save_config(cfg)
        self.settings_changed.emit(changed)
        self.accept()


class SectionForm(QWidget):
    def __init__(self, section_key: str, section_title: str, fields_spec: dict, parent=None):
        super().__init__(parent)
        self.section_key = section_key
        self.fields_spec = fields_spec
        self._widgets = {}

        self.setLayout(QVBoxLayout())
        form = QFormLayout()
        self.layout().addLayout(form)

        # грузим значения custom, для сброса будем смотреть default
        cfg = _read_config()
        section_cfg = cfg.get(section_key, {})
        custom = section_cfg.get("custom", {})
        default = section_cfg.get("default", {})

        # редакторы
        for key, (label, tp, required) in fields_spec.items():
            if tp is bool:
                w = QCheckBox()
                w.setChecked(bool(custom.get(key, default.get(key, False))))
                editor = w
            elif tp is int:
                w = QSpinBox()
                w.setRange(-999999, 999999)
                w.setValue(int(custom.get(key, default.get(key, 0))))
                editor = w
            else:
                w = QLineEdit()
                val = custom.get(key, default.get(key, ""))
                w.setText("" if val is None else str(val))
                if required:
                    w.setPlaceholderText("Обязательное поле")
                editor = w

            self._widgets[key] = editor
            form.addRow(label + (" *" if required else ""), editor)

        btns = QHBoxLayout()
        self.btn_reset = QPushButton("Сбросить (default)")
        self.btn_reset.clicked.connect(self.reset_to_default)

        self.btn_clear_json = QPushButton("Очистить JSON")
        # parent здесь - CombinedSettingsDialog
        if isinstance(parent, CombinedSettingsDialog):
            self.btn_clear_json.clicked.connect(parent.clear_json)

        btns.addStretch(1)
        btns.addWidget(self.btn_reset)
        btns.addWidget(self.btn_clear_json)
        self.layout().addLayout(btns)

        # btns = QHBoxLayout()
        # self.btn_reset = QPushButton("Сбросить (default)")
        # self.btn_reset.clicked.connect(self.reset_to_default)
        # btns.addStretch(1)
        # btns.addWidget(self.btn_reset)
        # self.layout().addLayout(btns)

    # Переписать на читаемый, возможно использовать словари _READERS, _CASTERS (тогда переписать весь class)
    def values(self) -> dict:
        out = {}
        for key, editor in self._widgets.items():
            spec = self.fields_spec[key]
            tp = spec[1]
            if isinstance(editor, QCheckBox):
                val = editor.isChecked()
            elif isinstance(editor, QSpinBox):
                val = editor.value()
            else:
                val = editor.text().strip()
            if tp is int:
                try:
                    val = int(val)
                except:
                    val = 0
            elif tp is bool:
                val = bool(val)
            else:
                val = str(val)
            out[key] = val
        return out

    def reset_to_default(self):
        cfg = _read_config()
        section_cfg = cfg.get(self.section_key, {})
        default = section_cfg.get("default", {})
        # подставляем default в редакторы
        for key, editor in self._widgets.items():
            val = default.get(key, "")
            if isinstance(editor, QCheckBox):
                editor.setChecked(bool(val))
            elif isinstance(editor, QSpinBox):
                try:
                    editor.setValue(int(val))
                except:
                    editor.setValue(0)
            else:
                editor.setText("" if val is None else str(val))


class VerticalTextDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        # 1️⃣ Даем Qt нарисовать ячейку (фон, выделение, фокус, бордеры) БЕЗ текста
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        text = opt.text  # сохраняем текст
        opt.text = ""  # очищаем, чтобы базовый стиль текст не рисовал

        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        # 2️⃣ Рисуем только повернутый текст поверх уже готовой ячейки
        if not text:
            return

        painter.save()
        rect = opt.rect

        painter.translate(rect.x(), rect.y() + rect.height())
        painter.rotate(-90)

        painter.drawText(
            QRect(0, 0, rect.height(), rect.width()),
            Qt.AlignmentFlag.AlignCenter,
            text
        )

        painter.restore()


# class VerticalTextDelegate(QStyledItemDelegate):
#     def paint(self, painter: QPainter, option, index):
#         painter.save()
#
#         rect = option.rect
#         text = index.data()
#
#         # 1️⃣ Фон: выделение / фон из RowHighlighter / база таблицы
#         try:
#             if option.state & QStyle.StateFlag.State_Selected:
#                 # выделенная строка
#                 painter.fillRect(rect, option.palette.highlight())
#             else:
#                 bg_brush = index.data(Qt.ItemDataRole.BackgroundRole)
#                 if bg_brush:
#                     painter.fillRect(rect, bg_brush)
#                 else:
#                     painter.fillRect(rect, option.palette.base())
#         except Exception:
#             # на всякий случай, чтобы делегат не уронил всё приложение
#             painter.fillRect(rect, option.palette.base())
#
#         # 2️⃣ Поворот и текст
#         if text:
#             painter.translate(rect.x(), rect.y() + rect.height())
#             painter.rotate(-90)
#
#             painter.drawText(
#                 QRect(0, 0, rect.height(), rect.width()),
#                 Qt.AlignmentFlag.AlignCenter,
#                 str(text)
#             )
#
#         painter.restore()


# Вспомогательные функции
def _read_config() -> dict:
    try:
        manager = JM(CONFIG_JSON)
        return manager.load_json() or {}
    except Exception:
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}


def _save_config(cfg: dict) -> None:
    try:
        manager = JM(CONFIG_JSON)
        manager.save_in_json(cfg)
    except Exception:
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
