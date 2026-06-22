import json

from PyQt6.QtCore import pyqtSignal, QRect, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QStyledItemDelegate,
                             QLineEdit, QSpinBox, QCheckBox, QPushButton, QHBoxLayout, QMessageBox,
                             QStyle, QStyleOptionViewItem, QApplication, QRadioButton, QGroupBox, QLabel)

from Navigation_Bot.core.json_store import JsonStore as JM
from Navigation_Bot.core.paths import CONFIG_JSON
from Navigation_Bot.core.secrets_manager import SecretsManager
from Navigation_Bot.core.settings.settings_schema import SECTIONS
from Navigation_Bot.gui.dialogs.dialog_helpers import button_row_trailing
from LogistX.config.paths import ONEC_UI_MAP
from LogistX.onec.steps.capture_race_ui import CaptureRaceUiStep
from LogistX.onec.uimap import UiMap


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

        self.highlight_tab = HighlightSettingsTab(self)
        self.highlight_tab.hours_spin.valueChanged.connect(lambda _=None: self._dirty.add("highlight"))
        self.highlight_tab.minutes_spin.valueChanged.connect(lambda _=None: self._dirty.add("highlight"))
        self.highlight_tab.future_load_hours_spin.valueChanged.connect(lambda _=None: self._dirty.add("highlight"))
        self.highlight_tab.expired_unload_grace_spin.valueChanged.connect(lambda _=None: self._dirty.add("highlight"))
        self.highlight_tab.cb_manual.stateChanged.connect(lambda _=None: self._dirty.add("highlight"))
        self.highlight_tab.cb_expired_unloads.stateChanged.connect(lambda _=None: self._dirty.add("highlight"))
        self.highlight_tab.cb_future_load.stateChanged.connect(lambda _=None: self._dirty.add("highlight"))
        self.highlight_tab.rb_log_user.toggled.connect(lambda _=None: self._dirty.add("highlight"))
        self.highlight_tab.rb_log_user_plus.toggled.connect(lambda _=None: self._dirty.add("highlight"))
        self.highlight_tab.rb_log_admin.toggled.connect(lambda _=None: self._dirty.add("highlight"))

        self._forms["highlight"] = self.highlight_tab
        self.tabs.addTab(self.highlight_tab, "Подсветка")

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

        task_repository = getattr(parent_gui, "task_repository", None)
        table_manager = getattr(parent_gui, "table_manager", None)

        if task_repository is not None:
            task_repository.set([], source="user")

        if table_manager is not None:
            # table_manager.display()
            parent_gui.reload_and_show()

    def clear_onec_ui_coordinates(self):
        """Сброс якорей калибровки 1С (capture_race_ui) в onec_ui_map_v2.json."""
        reply = QMessageBox.question(self,
                                     "Сброс координат 1С",
                                     "Удалить сохранённые координаты калибровки формы рейса в 1С?\n"
                                     "При следующем закрытии рейса калибровка выполнится заново.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not ONEC_UI_MAP.exists():
            QMessageBox.information(self, "Готово", "Файл координат ещё не создан — сбрасывать нечего.")
            return

        try:
            ui_map = UiMap(ONEC_UI_MAP)
            removed = ui_map.clear_anchors(CaptureRaceUiStep.REQUIRED_POINTS)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сбросить координаты:\n{e}")
            return

        parent_gui = self.parent()
        if parent_gui:
            processor = getattr(parent_gui, "processor", None)
            if processor:
                svc = getattr(processor, "logistx_race_service", None)
                if svc is not None:
                    svc.onec_bot = None

        QMessageBox.information(self,
                                "Готово",
                                f"Удалено якорей: {removed}." if removed else "Сохранённых якорей калибровки не было.", )

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
            if s_key == "highlight":
                minutes = int(val.get("duration_minutes", 120))
                enabled_types = list(val.get("enabled_types", []))
                log_audience = val.get("log_audience", "user")
                future_load_threshold_hours = int(val.get("future_load_threshold_hours", 3))
                expired_unload_grace_minutes = int(val.get("expired_unload_grace_minutes", 0))

                if self.gui and hasattr(self.gui, "ui_settings"):
                    node = self.gui.ui_settings.data.setdefault("highlight", {})
                    node["duration_minutes"] = minutes
                    node["enabled_types"] = enabled_types
                    node["future_load_threshold_hours"] = future_load_threshold_hours
                    node["expired_unload_grace_minutes"] = expired_unload_grace_minutes

                    log_node = self.gui.ui_settings.data.setdefault("log", {})
                    log_node["audience"] = log_audience
                    self.gui.ui_settings._schedule_save()

                if self.gui and hasattr(self.gui, "_apply_runtime_settings"):
                    self.gui._apply_runtime_settings()
                if self.gui and hasattr(self.gui, "reload_and_show"):
                    self.gui.reload_and_show()

                changed.add(s_key)
                changed.add("log")
                continue
            # Специальная обработка для layout_mode
            if s_key == "layout_mode":
                # Сохраняем напрямую в gui.ui_settings в формате {"mode": ..., "monitor": ...}
                if self.gui and hasattr(self.gui, 'ui_settings'):
                    self.gui.ui_settings.data["layout_mode"] = val
                    self.gui.ui_settings._schedule_save()
            else:
                # Для остальных секций используем стандартный формат
                if s_key == "wialon_selectors":
                    username = val.pop("wialon_username", "")
                    password = val.pop("wialon_password", "")
                    original = getattr(form, "_original_secret_values", {})
                    credentials_changed = (
                            username != original.get("wialon_username", "")
                            or password != original.get("wialon_password", "")
                    )

                    if credentials_changed:
                        if not username or not password:
                            QMessageBox.warning(
                                self,
                                "Проверка",
                                "Для сохранения Wialon заполните и логин, и пароль.",
                            )
                            return

                        try:
                            SecretsManager().set_wialon_credentials(username, password)
                            form._original_secret_values = {
                                "wialon_username": username,
                                "wialon_password": password,
                            }
                        except Exception as e:
                            QMessageBox.warning(
                                self,
                                "Ошибка",
                                f"Не удалось сохранить Wialon credentials в .env:\n{e}",
                            )
                            return

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

        if section_key == "wialon_selectors":
            secrets = SecretsManager()
            username, password = secrets.get_wialon_credentials_optional()
            self._original_secret_values = {
                "wialon_username": username,
                "wialon_password": password,
            }

            username_edit = QLineEdit()
            username_edit.setText(username)

            password_edit = QLineEdit()
            password_edit.setText(password)
            password_edit.setEchoMode(QLineEdit.EchoMode.Password)

            self._widgets["wialon_username"] = username_edit
            self._widgets["wialon_password"] = password_edit
            form.addRow("Логин", username_edit)
            form.addRow("Пароль", password_edit)

        self.btn_reset = QPushButton("Сбросить (default)")
        # self.btn_reset.clicked.connect(self.reset_to_default)

        self.btn_clear_json = QPushButton("Очистить JSON")
        self.btn_reset_onec_ui = QPushButton("Сбросить координаты 1С")

        dialog = parent
        if isinstance(dialog, CombinedSettingsDialog):
            self.btn_reset.clicked.connect(self.reset_to_default)
            self.btn_clear_json.clicked.connect(dialog.clear_json)
            self.btn_reset_onec_ui.clicked.connect(dialog.clear_onec_ui_coordinates)

        self.layout().addLayout(button_row_trailing(self.btn_reset,
                                                            self.btn_clear_json,
                                                            self.btn_reset_onec_ui))

    def values(self) -> dict:
        out = {}
        for key, editor in self._widgets.items():
            if key not in self.fields_spec:
                out[key] = editor.text().strip()
                continue

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
            if key not in self.fields_spec:
                continue

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


class HighlightSettingsTab(QWidget):
    """Вкладка настроек подсветки строк."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dialog = parent
        self.gui = getattr(parent, "gui", None)
        self._green_line()
        self.load_values()

    def _green_line(self):
        root = QVBoxLayout(self)

        desc = QLabel("Настройки зелёной подсветки строки после нажатия ▶.\n"
                      "Подсветка хранится в JSON у каждой записи.")
        desc.setStyleSheet("color: #666; font-size: 10px; margin-bottom: 10px;")

        root.addWidget(desc)
        row = QHBoxLayout()

        # Левая часть: лейбл + поля
        self.hours_spin = QSpinBox()
        self.hours_spin.setRange(0, 168)
        self.hours_spin.setSuffix(" ч")
        self.hours_spin.setFixedWidth(80)

        self.minutes_spin = QSpinBox()
        self.minutes_spin.setRange(0, 59)
        self.minutes_spin.setSuffix(" м")
        self.minutes_spin.setFixedWidth(80)

        row.addWidget(QLabel("Слежение 🟩:"))
        row.addWidget(self.hours_spin)
        row.addWidget(self.minutes_spin)

        # Пружина, которая раздвигает левую и правую части
        row.addStretch()

        # Правая часть: кнопка сброса
        self.btn_clear_highlights = QPushButton("Сброс")
        self.btn_clear_highlights.clicked.connect(self.clear_all_highlights)
        row.addWidget(self.btn_clear_highlights)

        root.addLayout(row)

        thresholds_row = QHBoxLayout()

        self.future_load_hours_spin = QSpinBox()
        self.future_load_hours_spin.setRange(0, 168)
        self.future_load_hours_spin.setSuffix(" ч")
        self.future_load_hours_spin.setFixedWidth(80)

        self.expired_unload_grace_spin = QSpinBox()
        self.expired_unload_grace_spin.setRange(0, 1440)
        self.expired_unload_grace_spin.setSuffix(" м")
        self.expired_unload_grace_spin.setFixedWidth(80)

        thresholds_row.addWidget(QLabel("Будущая погрузка > now +"))
        thresholds_row.addWidget(self.future_load_hours_spin)
        thresholds_row.addSpacing(16)
        thresholds_row.addWidget(QLabel("Опоздание после"))
        thresholds_row.addWidget(self.expired_unload_grace_spin)
        thresholds_row.addStretch()
        root.addLayout(thresholds_row)

        types_box = QGroupBox("Включённая подсветка")
        types_layout = QVBoxLayout()
        types_layout.setContentsMargins(8, 8, 8, 8)

        self.cb_manual = QCheckBox("Слежение строк (зелёная)")
        self.cb_expired_unloads = QCheckBox("Просроченная выгрузка (красная)")
        self.cb_future_load = QCheckBox("Будущая погрузка (голубая)")

        types_layout.addWidget(self.cb_manual)
        types_layout.addWidget(self.cb_expired_unloads)
        types_layout.addWidget(self.cb_future_load)
        types_box.setLayout(types_layout)
        root.addWidget(types_box)

        log_box = QGroupBox("Уровень вывода лога")
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(8, 8, 8, 8)

        self.rb_log_user = QRadioButton("user")
        self.rb_log_user_plus = QRadioButton("user+")
        self.rb_log_admin = QRadioButton("admin")

        log_layout.addWidget(self.rb_log_user)
        log_layout.addWidget(self.rb_log_user_plus)
        log_layout.addWidget(self.rb_log_admin)
        log_box.setLayout(log_layout)
        root.addWidget(log_box)

        root.addStretch()

    def load_values(self):
        minutes_total = 120
        future_load_threshold_hours = 3
        expired_unload_grace_minutes = 0

        try:
            cfg = self.gui.ui_settings.data.get("highlight", {}) or {}
            minutes_total = int(cfg.get("duration_minutes", 120))
            future_load_threshold_hours = int(cfg.get("future_load_threshold_hours", 3))
            expired_unload_grace_minutes = int(cfg.get("expired_unload_grace_minutes", 0))
        except Exception:
            cfg = {}
            minutes_total = 120
            future_load_threshold_hours = 3
            expired_unload_grace_minutes = 0

        hours = minutes_total // 60
        minutes = minutes_total % 60

        self.hours_spin.setValue(hours)
        self.minutes_spin.setValue(minutes)
        self.future_load_hours_spin.setValue(max(0, future_load_threshold_hours))
        self.expired_unload_grace_spin.setValue(max(0, expired_unload_grace_minutes))

        enabled_types = cfg.get("enabled_types")
        if not isinstance(enabled_types, list):
            enabled_types = ["manual", "expired_unloads", "future_load"]
        enabled_types = {str(v) for v in enabled_types}

        self.cb_manual.setChecked("manual" in enabled_types)
        self.cb_expired_unloads.setChecked("expired_unloads" in enabled_types)
        self.cb_future_load.setChecked("future_load" in enabled_types)

        log_audience = "user"
        try:
            log_cfg = self.gui.ui_settings.data.get("log", {}) or {}
            log_audience = str(log_cfg.get("audience", "user")).strip().lower()
        except Exception:
            log_audience = "user"

        if log_audience == "admin":
            self.rb_log_admin.setChecked(True)
        elif log_audience in {"user+", "user_plus"}:
            self.rb_log_user_plus.setChecked(True)
        else:
            self.rb_log_user.setChecked(True)

    def values(self):
        total = self.hours_spin.value() * 60 + self.minutes_spin.value()
        enabled_types = []
        if self.cb_manual.isChecked():
            enabled_types.append("manual")
        if self.cb_expired_unloads.isChecked():
            enabled_types.append("expired_unloads")
        if self.cb_future_load.isChecked():
            enabled_types.append("future_load")

        if self.rb_log_admin.isChecked():
            log_audience = "admin"
        elif self.rb_log_user_plus.isChecked():
            log_audience = "user+"
        else:
            log_audience = "user"

        return {
            "duration_minutes": total,
            "enabled_types": enabled_types,
            "log_audience": log_audience,
            "future_load_threshold_hours": self.future_load_hours_spin.value(),
            "expired_unload_grace_minutes": self.expired_unload_grace_spin.value(),
        }

    def clear_all_highlights(self):
        if not self.gui:
            QMessageBox.warning(self, "Ошибка", "GUI не найден.")
            return

        reply = QMessageBox.question(self,
                                     "Сброс подсветки",
                                     "Удалить подсветку у всех строк в текущем JSON?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply != QMessageBox.StandardButton.Yes:
            return

        highlighter = getattr(self.gui, "row_highlighter", None)
        if not highlighter:
            QMessageBox.warning(self, "Ошибка", "RowHighlighter не найден.")
            return

        changed = highlighter.clear_all_highlight_until()

        if hasattr(self.gui, "reload_and_show"):
            self.gui.reload_and_show()

        QMessageBox.information(self,
                                "Готово",
                                "Подсветка сброшена." if changed else "Ни у кого нет подсветки.")


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
