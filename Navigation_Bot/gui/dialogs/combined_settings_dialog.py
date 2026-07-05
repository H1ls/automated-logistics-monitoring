from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QTabWidget

from LogistX.config.paths import ONEC_UI_MAP
from LogistX.onec.steps.capture_race_ui import CaptureRaceUiStep
from LogistX.onec.uimap import UiMap
from Navigation_Bot.core.json_store import JsonStore
from Navigation_Bot.core.paths import CONFIG_JSON
from Navigation_Bot.core.secrets_manager import SecretsManager
from Navigation_Bot.core.settings.settings_schema import SECTIONS
from Navigation_Bot.gui.dialogs.base_dialog import BaseDialog
from Navigation_Bot.gui.dialogs.components.combined_settings_tabs import (HighlightSettingsTab, LayoutModeTab, SectionForm)


class CombinedSettingsDialog(BaseDialog):
    settings_changed = pyqtSignal(set)
    clear_json_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(title="Настройки", size=(650, 350), parent=parent)
        self._forms = {}  # section_key -> SectionForm
        self._dirty = set()  # какие секции менялись с момента открытия
        self.gui = parent  # сохраняем ссылку на gui для удобства
        self.config_store = JsonStore(CONFIG_JSON)
        self.config = self._load_config()

        self.tabs = QTabWidget()
        self.root.addWidget(self.tabs)

        self._build_section_tabs(parent)
        self._build_highlight_tab()

        self.btn_save, self.btn_cancel = self.add_save_cancel_buttons(save_callback=self._on_save)

    def _build_section_tabs(self, parent) -> None:
        for section_key, (title, fields) in SECTIONS.items():
            # Специальная обработка для вкладки режима размещения окон
            if section_key == "layout_mode":
                form = LayoutModeTab(self)
                # Загружаем текущее значение из gui.ui_settings (это же, что будет обновляться)
                layout_config = parent.ui_settings.data.get("layout_mode", {})
                load_values = (
                    {"mode": layout_config, "monitor": "second"}
                    if isinstance(layout_config, str)
                    else layout_config
                )
                form.load_values(load_values)
                # Отслеживаем изменения
                form.rb_vertical.toggled.connect(lambda _=None, s=section_key: self._dirty.add(s))
                form.rb_horizontal.toggled.connect(lambda _=None, s=section_key: self._dirty.add(s))
                form.rb_monitor_first.toggled.connect(lambda _=None, s=section_key: self._dirty.add(s))
                form.rb_monitor_second.toggled.connect(lambda _=None, s=section_key: self._dirty.add(s))
            else:
                form = SectionForm(section_key,
                                   title,
                                   fields,
                                   section_config=self.config.get(section_key, {}),
                                   parent=self)
                for widget in form._widgets.values():
                    if hasattr(widget, "textChanged"):
                        widget.textChanged.connect(lambda _=None, s=section_key: self._dirty.add(s))
                    elif hasattr(widget, "stateChanged"):
                        widget.stateChanged.connect(lambda _=None, s=section_key: self._dirty.add(s))
                    elif hasattr(widget, "valueChanged"):
                        widget.valueChanged.connect(lambda _=None, s=section_key: self._dirty.add(s))

            self._forms[section_key] = form
            self.tabs.addTab(form, title)

    def _build_highlight_tab(self) -> None:
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

    def _validate_required(self) -> tuple[bool, str]:
        for section_key, (title, fields) in SECTIONS.items():
            form = self._forms[section_key]
            for key, (label, field_type, required) in fields.items():
                if not required:
                    continue
                value = form.values().get(key, "")
                if (field_type is str and not str(value).strip()) or (field_type is int and value is None):
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
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not ONEC_UI_MAP.exists():
            QMessageBox.information(self, "Готово", "Файл координат ещё не создан — сбрасывать нечего.")
            return

        try:
            ui_map = UiMap(ONEC_UI_MAP)
            removed = ui_map.clear_anchors(CaptureRaceUiStep.REQUIRED_POINTS)
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сбросить координаты:\n{exc}")
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
                                f"Удалено якорей: {removed}." if removed else "Сохранённых якорей калибровки не было.")

    def _on_save(self):
        ok, message = self._validate_required()
        if not ok:
            QMessageBox.warning(self, "Проверка", message)
            return

        if not self._dirty:
            self.accept()
            return

        cfg = dict(self.config)
        changed = set()

        for section_key in self._dirty:
            form = self._forms[section_key]
            value = form.values()

            if section_key == "highlight":
                self._save_highlight_settings(value)
                changed.add(section_key)
                changed.add("log")
                continue

            if section_key == "layout_mode":
                if self.gui and hasattr(self.gui, "ui_settings"):
                    self.gui.ui_settings.data["layout_mode"] = value
                    self.gui.ui_settings._schedule_save()
            else:
                if section_key == "wialon_selectors" and not self._save_wialon_credentials(form, value):
                    return

                node = cfg.setdefault(section_key, {})
                node.setdefault("default", node.get("default", {}))
                node["custom"] = value

            changed.add(section_key)

        self.config_store.save_in_json(cfg)
        self.config = cfg
        self.settings_changed.emit(changed)
        self.accept()

    def _load_config(self) -> dict:
        data = self.config_store.load_json() or {}
        return data if isinstance(data, dict) else {}

    def _save_highlight_settings(self, value: dict) -> None:
        minutes = int(value.get("duration_minutes", 120))
        enabled_types = list(value.get("enabled_types", []))
        log_audience = value.get("log_audience", "user")
        future_load_threshold_hours = int(value.get("future_load_threshold_hours", 3))
        expired_unload_grace_minutes = int(value.get("expired_unload_grace_minutes", 0))

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

    def _save_wialon_credentials(self, form, value: dict) -> bool:
        username = value.pop("wialon_username", "")
        password = value.pop("wialon_password", "")
        original = getattr(form, "_original_secret_values", {})
        credentials_changed = (
                username != original.get("wialon_username", "")
                or password != original.get("wialon_password", "")
        )

        if not credentials_changed:
            return True

        if not username or not password:
            QMessageBox.warning(self, "Проверка", "Для сохранения Wialon заполните и логин, и пароль.")
            return False

        try:
            SecretsManager().set_wialon_credentials(username, password)
            form._original_secret_values = {
                "wialon_username": username,
                "wialon_password": password,
            }
        except Exception as exc:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить Wialon credentials в .env:\n{exc}")
            return False

        return True
