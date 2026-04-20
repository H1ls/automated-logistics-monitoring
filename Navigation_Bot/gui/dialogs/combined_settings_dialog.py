import json

from PyQt6.QtCore import pyqtSignal, QRect, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QStyledItemDelegate,
                             QLineEdit, QSpinBox, QCheckBox, QPushButton, QHBoxLayout, QMessageBox,
                             QStyle, QStyleOptionViewItem, QApplication, QRadioButton, QGroupBox, QLabel)

from Navigation_Bot.core.json_manager import JSONManager as JM
from Navigation_Bot.core.paths import CONFIG_JSON
from Navigation_Bot.core.settings.settings_schema import SECTIONS
from Navigation_Bot.gui.dialogs.dialog_helpers import button_row_trailing


class LayoutModeTab(QWidget):
    """Вкладка для выбора режима размещения окон Navigation Manager и WebDriver."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_mode = "vertical"  # по умолчанию
        self.current_monitor = "second"  # по умолчанию использовать второй монитор
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Описание
        desc = QLabel("Выберите монитор и режим расположения окон Navigation Manager и браузера (Wialon/Yandex).\n"
                      "Оба окна занимают по 1/2 выбранного экрана."
                      )
        desc.setStyleSheet("color: #666; font-size: 10px; margin-bottom: 10px;")
        root.addWidget(desc)

        # ========== Группа 1: Выбор монитора ==========
        monitor_layout = QVBoxLayout()
        monitor_layout.setContentsMargins(0, 0, 0, 0)

        self.rb_monitor_first = QRadioButton("📺 Первый монитор")
        monitor_layout.addWidget(self.rb_monitor_first)

        first_desc = QLabel("Использовать основной/первый монитор для размещения")
        first_desc.setStyleSheet("color: #888; margin-left: 20px; font-size: 9px;")
        monitor_layout.addWidget(first_desc)

        self.rb_monitor_second = QRadioButton("📺 Второй монитор (рекомендуется)")
        self.rb_monitor_second.setChecked(True)
        monitor_layout.addWidget(self.rb_monitor_second)

        second_desc = QLabel("Использовать дополнительный/второй монитор для размещения")
        second_desc.setStyleSheet("color: #888; margin-left: 20px; font-size: 9px;")
        monitor_layout.addWidget(second_desc)

        monitor_box = QGroupBox("📺 Выбор монитора")
        monitor_box.setLayout(monitor_layout)
        root.addWidget(monitor_box)

        # ========== Группа 2: Режим размещения ==========
        mode_layout = QVBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)

        # Вариант 1: Вертикальное разделение (верх/низ)
        self.rb_vertical = QRadioButton("📊 Вертикальное разделение (верхний/нижний)")
        self.rb_vertical.setChecked(True)
        mode_layout.addWidget(self.rb_vertical)

        vertical_desc = QLabel("Navigation Manager сверху (1/2 экрана)\n"
                               "Браузер снизу (1/2 экрана)"
                               )
        vertical_desc.setStyleSheet("color: #888; margin-left: 20px; font-size: 9px;")
        mode_layout.addWidget(vertical_desc)

        # Вариант 2: Горизонтальное разделение (лево/право)
        self.rb_horizontal = QRadioButton("📱 Горизонтальное разделение (левый/правый)")
        mode_layout.addWidget(self.rb_horizontal)

        horizontal_desc = QLabel("Браузер слева (1/2 экрана)\n"
                                 "Navigation Manager справа (1/2 экрана)")
        horizontal_desc.setStyleSheet("color: #888; margin-left: 20px; font-size: 9px;")
        mode_layout.addWidget(horizontal_desc)

        # Диаграмма
        diagram = QLabel("""
    ┌─ Вертикально        ┌─ Горизонтально
    ├─ ┌────────────┐     ├─ ┌───────┬───────┐
    │  │ Навигация  │     │  │       │       │
    │  ├────────────┤     │  │Браузер│ Нави  │
    │  │  Браузер   │     │  │       │       │
    └─ └────────────┘     └─ └───────┴───────┘""")

        # diagram.setStyleSheet("font-family: monospace; color: #999; font-size: 8px; margin-top: 5px;")
        diagram.setStyleSheet("""font-family: Consolas, Courier New, monospace;font-size: 12px;""")
        mode_layout.addWidget(diagram)

        mode_box = QGroupBox("🔄 Режим разделения")
        mode_box.setLayout(mode_layout)
        root.addWidget(mode_box)

        root.addStretch()

    def values(self) -> dict:
        """Возвращает выбранные режим и монитор."""
        mode = "horizontal" if self.rb_horizontal.isChecked() else "vertical"
        monitor = "first" if self.rb_monitor_first.isChecked() else "second"
        return {"mode": mode, "monitor": monitor}

    def load_values(self, values: dict):
        """Загружает значения из конфига."""
        mode = values.get("mode", "vertical")
        monitor = values.get("monitor", "second")

        if mode == "horizontal":
            self.rb_horizontal.setChecked(True)
        else:
            self.rb_vertical.setChecked(True)

        if monitor == "first":
            self.rb_monitor_first.setChecked(True)
        else:
            self.rb_monitor_second.setChecked(True)

        self.current_mode = mode
        self.current_monitor = monitor


class CombinedSettingsDialog(QDialog):
    settings_changed = pyqtSignal(set)
    clear_json_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.resize(650, 350)
        self._forms = {}  # section_key -> SectionForm
        self._dirty = set()  # какие секции менялись с момента открытия
        self.gui = parent  # сохраняем ссылку на gui для удобства

        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        for section_key, (title, fields) in SECTIONS.items():
            # Специальная обработка для вкладки режима размещения окон
            if section_key == "layout_mode":
                form = LayoutModeTab(self)
                # Загружаем текущее значение из gui.ui_settings (это же, что будет обновляться)
                layout_config = parent.ui_settings.data.get("layout_mode", {})

                # Поддерживаем оба формата: строка (legacy) и объект (новый)
                if isinstance(layout_config, str):
                    # Мигрируем старый формат
                    load_values = {"mode": layout_config, "monitor": "second"}
                else:
                    load_values = layout_config

                form.load_values(load_values)
                # Отслеживаем изменения
                form.rb_vertical.toggled.connect(lambda _=None, s=section_key: self._dirty.add(s))
                form.rb_horizontal.toggled.connect(lambda _=None, s=section_key: self._dirty.add(s))
                form.rb_monitor_first.toggled.connect(lambda _=None, s=section_key: self._dirty.add(s))
                form.rb_monitor_second.toggled.connect(lambda _=None, s=section_key: self._dirty.add(s))
            else:
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

        self.btn_save = QPushButton("Сохранить")
        self.btn_cancel = QPushButton("Отмена")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel.clicked.connect(self.reject)
        root.addLayout(button_row_trailing(self.btn_save, self.btn_cancel))

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

    def clear_json(self):
        """Очистка основного JSON через parent (NavigationGUI)."""
        parent_gui = self.parent()
        if not parent_gui:
            QMessageBox.warning(self, "Ошибка", "Родительское окно не найдено.")
            return

        reply = QMessageBox.question(self,
                                     "Подтверждение очистки",
                                     "Вы действительно хотите очистить все данные из JSON?\nЭто действие необратимо.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply != QMessageBox.StandardButton.Yes:
            return

        data_context = getattr(parent_gui, "data_context", None)
        table_manager = getattr(parent_gui, "table_manager", None)

        if data_context is not None:
            data_context.set([])

        if table_manager is not None:
            # table_manager.display()
            parent_gui.reload_and_show()

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

            # Специальная обработка для layout_mode
            if s_key == "layout_mode":
                # Сохраняем напрямую в gui.ui_settings в формате {"mode": ..., "monitor": ...}
                if self.gui and hasattr(self.gui, 'ui_settings'):
                    self.gui.ui_settings.data["layout_mode"] = val
                    self.gui.ui_settings._schedule_save()
            else:
                # Для остальных секций используем стандартный формат
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

        self.btn_reset = QPushButton("Сбросить (default)")
        self.btn_reset.clicked.connect(self.reset_to_default)

        self.btn_clear_json = QPushButton("Очистить JSON")
        if isinstance(parent, CombinedSettingsDialog):
            self.btn_clear_json.clicked.connect(parent.clear_json)

        self.layout().addLayout(button_row_trailing(self.btn_reset, self.btn_clear_json))

    def values(self) -> dict:
        out = {}
        for key, editor in self._widgets.items():
            _, tp, _ = self.fields_spec[key]
            if isinstance(editor, QCheckBox):
                raw = editor.isChecked()
            elif isinstance(editor, QSpinBox):
                raw = editor.value()
            else:
                raw = editor.text().strip()

            if tp is int:
                try:
                    out[key] = int(raw)
                except (TypeError, ValueError):
                    out[key] = 0
            elif tp is bool:
                out[key] = bool(raw)
            else:
                out[key] = str(raw)
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
                except (TypeError, ValueError):
                    editor.setValue(0)
            else:
                editor.setText("" if val is None else str(val))


class VerticalTextDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        # Даем Qt нарисовать ячейку (фон, выделение, фокус, бордеры) БЕЗ текста
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        text = opt.text  # сохраняем текст
        opt.text = ""  # очищаем, чтобы базовый стиль текст не рисовал

        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        # Рисуем только повернутый текст поверх уже готовой ячейки
        if not text:
            return

        painter.save()
        rect = opt.rect

        painter.translate(rect.x(), rect.y() + rect.height())
        painter.rotate(-90)

        painter.drawText(QRect(0, 0, rect.height(), rect.width()), Qt.AlignmentFlag.AlignCenter, text)

        painter.restore()


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
