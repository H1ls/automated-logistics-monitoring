from __future__ import annotations

from PyQt6.QtWidgets import QPushButton, QToolButton, QMenu
from PyQt6.QtGui import QAction


class SheetTabsController:
    """
    Управляет нижними кнопками-вкладками (локальные + Google Sheets) и меню "Листы ▼".
    Вся логика вкладок вынесена из Gui.py.
    """

    def __init__(self, gui):
        self.gui = gui  # NavigationGUI

    def activate_saved_tab(self):
        """Активировать сохранённую вкладку (или первую видимую), как будто пользователь кликнул."""
        gui = self.gui

        k = getattr(gui, "_active_tab_key", None)
        tabs_by_key = getattr(gui, "_tabs_by_key", {}) or {}
        btns_by_key = getattr(gui, "_tab_buttons_by_key", {}) or {}

        # 1) пробуем сохранённую
        tab = tabs_by_key.get(k) if k else None
        btn = btns_by_key.get(k) if k else None

        if tab and btn and btn.isVisible():
            self.on_tab_clicked(tab, btn)
            return True

        # 2) fallback: первая видимая таб-кнопка
        for key, b in btns_by_key.items():
            if b and b.isVisible():
                t = tabs_by_key.get(key)
                if t:
                    gui._active_tab_key = key  # чтобы память обновилась на корректную вкладку
                    self.on_tab_clicked(t, b)
                    return True

        return False

    def build(self):
        """Пересоздать кнопки вкладок и меню."""
        gui = self.gui

        try:
            # очистить layout
            while gui.sheet_tabs_layout.count():
                item = gui.sheet_tabs_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

            if not getattr(gui, "gsheet", None):
                return

            worksheets = gui.gsheet.list_worksheets() or []
            if not worksheets:
                gui.log("⚠️ Не удалось получить список листов Google Sheets.")
                return

            # ---- читаем скрытые вкладки из ui_settings (по key) ----
            hidden = set()
            try:
                tabs_cfg = (gui.ui_settings.data.get("tabs", {}) or {})
                hidden = set(tabs_cfg.get("hidden_keys", []) or [])
            except Exception:
                hidden = set()

            # ---- формируем единый список вкладок ----
            tabs = []
            for t in getattr(gui, "local_tabs", []) or []:
                tabs.append({"kind": "local", "key": t["key"], "title": t["title"]})

            current_ws_index = getattr(gui.gsheet, "worksheet_index", 0)
            for ws in worksheets:
                idx = ws["index"]
                title = ws["title"]
                key = f"gs:{title}"  # стабильный ключ по названию
                tabs.append({"kind": "gsheet", "key": key, "title": title, "ws_index": idx})

            # маппинги
            gui._tabs_by_key = {t["key"]: t for t in tabs}
            gui._tabs_order = [t["key"] for t in tabs]

            gui._tab_buttons = []
            gui._tab_buttons_by_key = {}

            # восстановить активную вкладку из ui_settings (если есть)
            try:
                tabs_cfg = (gui.ui_settings.data.get("tabs", {}) or {})
                saved_active = tabs_cfg.get("active_key")
                if saved_active:
                    gui._active_tab_key = saved_active
            except Exception:
                pass

            active_key = getattr(gui, "_active_tab_key", None)
            if not active_key:
                active_key = None
                for t in tabs:
                    if t["kind"] == "gsheet" and t.get("ws_index") == current_ws_index:
                        active_key = t["key"]
                        break
                gui._active_tab_key = active_key

            # ---- кнопки вкладок ----
            for t in tabs:
                key = t["key"]
                title = t["title"]

                btn = QPushButton(title)
                btn.setCheckable(True)

                visible = key not in hidden
                btn.setVisible(visible)

                if key == gui._active_tab_key:
                    btn.setChecked(True)

                btn.clicked.connect(lambda _, tab=t, b=btn: self.on_tab_clicked(tab, b))

                gui.sheet_tabs_layout.addWidget(btn)
                gui._tab_buttons.append(btn)
                gui._tab_buttons_by_key[key] = btn

            # спейсер + выпадающее меню
            gui.sheet_tabs_layout.addStretch()

            gui.sheet_filter_button = QToolButton(gui)
            gui.sheet_filter_button.setText("Листы ▼")
            gui.sheet_filter_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

            menu = QMenu(gui)
            gui._tab_actions = {}

            for t in tabs:
                key = t["key"]
                title = t["title"]

                act = QAction(title, gui)
                act.setCheckable(True)
                act.setChecked(key not in hidden)
                act.toggled.connect(lambda checked, k=key: self.on_tab_visibility_toggled(k, checked))

                menu.addAction(act)
                gui._tab_actions[key] = act

            gui.sheet_filter_button.setMenu(menu)
            gui.sheet_tabs_layout.addWidget(gui.sheet_filter_button)



        except Exception as e:
            gui.log(f"❌ SheetTabsController.build: {e}")

    def on_tab_clicked(self, tab: dict, clicked_btn: QPushButton):
        gui = self.gui

        # отметить чек на кнопках
        for btn in getattr(gui, "_tab_buttons", []):
            btn.setChecked(btn is clicked_btn)

        gui._active_tab_key = tab["key"]
        # сохранить активную вкладку
        if getattr(gui, "ui_settings", None):
            tabs_cfg = gui.ui_settings.data.setdefault("tabs", {})
            tabs_cfg["active_key"] = gui._active_tab_key
            try:
                gui.ui_settings._schedule_save()
            except Exception:
                pass

        # локальная вкладка
        if tab.get("kind") == "local":
            key = tab["key"]

            # создать страницу при первом открытии
            if key not in gui._local_pages_by_key:
                if key == "local:pincodes":
                    from Navigation_Bot.gui.main_window.PinCodesPage import PinCodesPage
                    page = PinCodesPage(
                        xlsx_path=gui.pincodes_xlsx_path,
                        json_path=gui.pincodes_json_path,
                        log_func=gui.log,
                        parent=gui.stack,
                    )
                    gui.stack.addWidget(page)
                    gui._local_pages_by_key[key] = page

            page = gui._local_pages_by_key.get(key)
            if page:
                gui.stack.setCurrentWidget(page)
            return

        # Google вкладка
        gui.stack.setCurrentWidget(gui.page_gsheet)

        ws_index = tab.get("ws_index", 0)
        gui.gsheet.set_active_worksheet(ws_index)

        json_path = gui._get_sheet_json_path()
        gui.data_context.set_filepath(json_path)

        gui.reload_and_show()

    def on_tab_visibility_toggled(self, tab_key: str, visible: bool):
        gui = self.gui

        btn = getattr(gui, "_tab_buttons_by_key", {}).get(tab_key)
        if not btn:
            return

        btn.setVisible(visible)

        # если скрыли активную вкладку — переключаемся на первую видимую
        if not visible and btn.isChecked():
            btn.setChecked(False)

            for k in getattr(gui, "_tabs_order", []):
                b = getattr(gui, "_tab_buttons_by_key", {}).get(k)
                if b and b.isVisible():
                    self.on_tab_clicked(gui._tabs_by_key[k], b)
                    break

        # сохранить hidden_keys
        if getattr(gui, "ui_settings", None):
            tabs_cfg = gui.ui_settings.data.setdefault("tabs", {})
            hidden = set(tabs_cfg.get("hidden_keys", []) or [])

            if visible:
                hidden.discard(tab_key)
            else:
                hidden.add(tab_key)

            tabs_cfg["hidden_keys"] = sorted(hidden)

            # сохранить как ui_settings обычно делает (таймером)
            try:
                gui.ui_settings._schedule_save()
            except Exception:
                try:
                    gui.ui_settings._flush()
                except Exception:
                    pass
