from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (QApplication, QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QRadioButton, QSpinBox, QStyle, QStyledItemDelegate,
                             QStyleOptionViewItem, QVBoxLayout, QWidget)

from Navigation_Bot.core.secrets_manager import SecretsManager
from Navigation_Bot.gui.dialogs.components.dialog_helpers import button_row_trailing


class LayoutModeTab(QWidget):
    """Вкладка для выбора режима размещения окон Navigation Manager и WebDriver."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_mode = "vertical"
        self.current_monitor = "second"
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        desc = QLabel("Выберите монитор и режим расположения окон Navigation Manager и браузера (Wialon/Yandex).\n"
                      "Оба окна занимают по 1/2 выбранного экрана.")
        desc.setStyleSheet("color: #666; font-size: 10px; margin-bottom: 10px;")
        root.addWidget(desc)

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

        mode_layout = QVBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)

        self.rb_vertical = QRadioButton("📊 Вертикальное разделение (верхний/нижний)")
        self.rb_vertical.setChecked(True)
        mode_layout.addWidget(self.rb_vertical)

        vertical_desc = QLabel("Navigation Manager сверху (1/2 экрана)\n"
                               "Браузер снизу (1/2 экрана)")
        vertical_desc.setStyleSheet("color: #888; margin-left: 20px; font-size: 9px;")
        mode_layout.addWidget(vertical_desc)

        self.rb_horizontal = QRadioButton("📱 Горизонтальное разделение (левый/правый)")
        mode_layout.addWidget(self.rb_horizontal)

        horizontal_desc = QLabel("Браузер слева (1/2 экрана)\n"
                                 "Navigation Manager справа (1/2 экрана)")
        horizontal_desc.setStyleSheet("color: #888; margin-left: 20px; font-size: 9px;")
        mode_layout.addWidget(horizontal_desc)

        diagram = QLabel("""
    ┌─ Вертикально        ┌─ Горизонтально
    ├─ ┌────────────┐     ├─ ┌───────┬───────┐
    │  │ Навигация  │     │  │       │       │
    │  ├────────────┤     │  │Браузер│ Нави  │
    │  │  Браузер   │     │  │       │       │
    └─ └────────────┘     └─ └───────┴───────┘""")
        diagram.setStyleSheet("""font-family: Consolas, Courier New, monospace;font-size: 12px;""")
        mode_layout.addWidget(diagram)

        mode_box = QGroupBox("🔄 Режим разделения")
        mode_box.setLayout(mode_layout)
        root.addWidget(mode_box)

        root.addStretch()

    def values(self) -> dict:
        mode = "horizontal" if self.rb_horizontal.isChecked() else "vertical"
        monitor = "first" if self.rb_monitor_first.isChecked() else "second"
        return {"mode": mode, "monitor": monitor}

    def load_values(self, values: dict):
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


class SectionForm(QWidget):
    def __init__(
        self,
        section_key: str,
        section_title: str,
        fields_spec: dict,
        section_config: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.section_key = section_key
        self.fields_spec = fields_spec
        self._widgets = {}
        self._default_values = dict((section_config or {}).get("default", {}) or {})

        self.setLayout(QVBoxLayout())
        form = QFormLayout()
        self.layout().addLayout(form)

        custom = (section_config or {}).get("custom", {}) or {}

        for key, (label, tp, required) in fields_spec.items():
            if tp is bool:
                editor = QCheckBox()
                editor.setChecked(bool(custom.get(key, self._default_values.get(key, False))))
            elif tp is int:
                editor = QSpinBox()
                editor.setRange(-999999, 999999)
                editor.setValue(int(custom.get(key, self._default_values.get(key, 0))))
            else:
                editor = QLineEdit()
                val = custom.get(key, self._default_values.get(key, ""))
                editor.setText("" if val is None else str(val))
                if required:
                    editor.setPlaceholderText("Обязательное поле")

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
        self.btn_clear_json = QPushButton("Очистить JSON")
        self.btn_reset_onec_ui = QPushButton("Сбросить координаты 1С")

        if hasattr(parent, "clear_json") and hasattr(parent, "clear_onec_ui_coordinates"):
            self.btn_reset.clicked.connect(self.reset_to_default)
            self.btn_clear_json.clicked.connect(parent.clear_json)
            self.btn_reset_onec_ui.clicked.connect(parent.clear_onec_ui_coordinates)

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
        for key, editor in self._widgets.items():
            if key not in self.fields_spec:
                continue

            val = self._default_values.get(key, "")
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
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        text = opt.text
        opt.text = ""

        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

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
        row.addStretch()

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
