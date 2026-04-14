import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QFrame)
from PyQt6.QtGui import QFont, QColor

from Navigation_Bot.core.paths import INPUT_FILEPATH
from Navigation_Bot.core.paths import PIN_XLSX_FILEPATH, PIN_JSON_FILEPATH
from Navigation_Bot.core.processedFlags import init_processed_flags
from Navigation_Bot.gui.builders.mainUiBuilder import MainUiBuilder
from Navigation_Bot.gui.controllers.sheet_tab_definitions import default_local_tabs
from Navigation_Bot.gui.controllers.appServices import AppServices
from Navigation_Bot.gui.controllers.sheetTabsController import SheetTabsController
from Navigation_Bot.gui.controllers.signalsBinder import SignalsBinder
from Navigation_Bot.gui.controllers.uiBridge import UiBridge
from Navigation_Bot.gui.controllers.windowLayoutManager import WindowLayoutManager, LayoutMode
from Navigation_Bot.gui.dialogs.iDManagerDialog import IDManagerDialog
from Navigation_Bot.gui.dialogs.trackingIdEditor import TrackingIdEditor
from Navigation_Bot.gui.settings.uiSettings import UiSettingsManager


class NavigationGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.log = lambda msg: print(msg)
        self.INPUT_FILEPATH = INPUT_FILEPATH

        self.setWindowTitle("Navigation Manager")
        self.setMinimumSize(800, 600)

        self.executor = ThreadPoolExecutor(max_workers=1)
        self._single_row_processing = True
        self._log_enabled = True
        self._current_sort = None
        self.json_lock = Lock()

        self._row_highlight_until = {}  # {row_idx: datetime_until}
        self.updated_rows = []

        self.ui_settings = UiSettingsManager(log_func=self.log)
        self.init_ui()

        # Создаем загрузочный экран до основной инициализации
        self._create_loading_screen()
        self.show_loading("Инициализация приложения…")

        self.ui_bridge = UiBridge(self)
        self.ui_settings.apply_window(self)
        self.ui_settings.apply_table(self.table)

        # Читаем режим размещения и выбор монитора из настроек
        layout_config = self.ui_settings.data.get("layout_mode", {})

        # Поддерживаем оба формата: строка (legacy) и объект (новый)
        if isinstance(layout_config, str):
            layout_mode_str = layout_config
            monitor_index = 1  # По умолчанию второй монитор
        else:
            layout_mode_str = layout_config.get("mode", LayoutMode.VERTICAL_SPLIT.value)
            # Преобразуем монитор из строки в индекс (0 для первого, 1 для второго)
            monitor_str = layout_config.get("monitor", "second")
            monitor_index = 0 if monitor_str == "first" else 1

        self._layout_manager = WindowLayoutManager(titlebar_offset=30,
                                                   layout_mode=layout_mode_str,
                                                   monitor_index=monitor_index
                                                   )
        self.browser_rect = self._layout_manager.apply_dual_screen_layout(self)

        self.show_loading("Загрузка локальных данных…")
        self.local_page()

        self.show_loading("Инициализация менеджеров…")
        self.init_managers()

        self.show_loading("Привязка сигналов…")
        SignalsBinder(self).bind()

        # Скрываем загрузочный экран когда все готово (быстро, чтобы не мешать)
        QTimer.singleShot(200, self.hide_loading)

    def _open_wialon(self):
        self.show_loading("Запуск Wialon…")

        def job():
            try:
                # self.processor.ensure_driver_and_bots()
                self.processor.browser_session.ensure_ready()
                # ЛОГ будет через UiBridge внутри processor (после шага 1)
            except Exception as e:
                # тоже через мост
                if getattr(self, "ui_bridge", None):
                    self.ui_bridge.log.emit(f"❌ Ошибка запуска Wialon: {e}")
                else:
                    self.log(f"❌ Ошибка запуска Wialon: {e}")
            finally:

                QTimer.singleShot(0, self.hide_loading)

        self.executor.submit(job)

    def closeEvent(self, event):
        """Гарантированная очистка при закрытии окна"""
        try:
            # 1. Закрыть браузер (самое важное)
            if getattr(self, "processor", None) and hasattr(self.processor, "driver_manager"):
                try:
                    self.processor.browser_session.stop_browser()
                except Exception as e:
                    self.log(f"⚠️ Ошибка закрытия браузера: {e}")

            # 2. Shutdown services
            if getattr(self, "services", None):
                self.services.shutdown()
        except Exception as e:
            self.log(f"⚠️ Ошибка shutdown: {e}")
        finally:
            # 3. Shutdown executor (чтобы threads корректно завершились)
            if getattr(self, "executor", None):
                try:
                    self.executor.shutdown(wait=True, timeout=5)
                except Exception:
                    pass

            super().closeEvent(event)

    def resizeEvent(self, event):
        """Обновить позицию splash screen когда окно меняет размер."""
        super().resizeEvent(event)
        if getattr(self, "loading_overlay", None) and self.loading_overlay.isVisible():
            # Позиционируем splash screen в центре окна
            x = (self.width() - 350) // 2
            y = (self.height() - 180) // 2
            self.loading_overlay.move(x, y)

    def _startup_reload(self):
        try:
            if getattr(self, "sheet_tabs_controller", None):
                self.sheet_tabs_controller.activate_saved_tab()
        finally:
            self.hide_loading()

    def _create_loading_screen(self):
        """Создать компактный splash screen для загрузки."""
        # Основной фреймворк - компактный splash screen в центре
        self.loading_overlay = QFrame(self)
        self.loading_overlay.setStyleSheet("QFrame { "
                                           "background-color: rgba(30, 30, 30, 240); "
                                           "border: 2px solid #bcbcbc; "
                                           "border-radius: 10px; "
                                           "}")

        self.loading_overlay.setFrameShape(QFrame.Shape.StyledPanel)

        # Фиксированный размер - компактный 350x180
        self.loading_overlay.setFixedSize(350, 180)

        # Контейнер с содержимым по центру
        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.setContentsMargins(20, 15, 20, 15)
        overlay_layout.setSpacing(10)

        # Иконка загрузки (ротирующиеся символы)
        self.loading_spinner = QLabel("⠋")
        self.loading_spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinner_font = QFont()
        spinner_font.setPointSize(28)
        self.loading_spinner.setFont(spinner_font)
        self.loading_spinner.setStyleSheet("color: #4CAF50;")
        self.loading_spinner.setFixedHeight(40)

        # Символы для анимации спиннера
        self._spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_index = 0

        # Timer для анимации спиннера
        self._spinner_timer = QTimer()
        self._spinner_timer.timeout.connect(self._update_spinner)
        self._spinner_timer.setInterval(80)

        overlay_layout.addWidget(self.loading_spinner)

        # Текст загрузки
        self.loading_label = QLabel("Загрузка…")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_font = QFont()
        label_font.setPointSize(11)
        label_font.setBold(True)
        self.loading_label.setFont(label_font)
        self.loading_label.setStyleSheet("color: #ffffff;")
        self.loading_label.setFixedHeight(20)

        overlay_layout.addWidget(self.loading_label)

        # Доп. сообщение (меньше)
        self.loading_detail = QLabel("Пожалуйста, подождите…")
        self.loading_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_font = QFont()
        detail_font.setPointSize(8)
        self.loading_detail.setFont(detail_font)
        self.loading_detail.setStyleSheet("color: #aaaaaa;")
        self.loading_detail.setFixedHeight(16)
        self.loading_detail.setWordWrap(True)

        overlay_layout.addWidget(self.loading_detail)

        # Изначально скрыт
        self.loading_overlay.hide()

    def _update_spinner(self):
        """Обновить спиннер на следующий кадр анимации."""
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
        self.loading_spinner.setText(self._spinner_frames[self._spinner_index])

    def show_loading(self, text="Загрузка…", detail="Пожалуйста, подождите…"):
        """Показать компактный splash screen с текстом в центре окна."""
        if getattr(self, "loading_label", None):
            self.loading_label.setText(text)

        if getattr(self, "loading_detail", None):
            self.loading_detail.setText(detail)

        if getattr(self, "loading_overlay", None):
            # Позиционируем splash screen в центре окна
            x = (self.width() - 350) // 2
            y = (self.height() - 180) // 2
            self.loading_overlay.move(x, y)
            self.loading_overlay.show()
            self.loading_overlay.raise_()

            # Запускаем анимацию спиннера если не запущена
            if getattr(self, "_spinner_timer", None) and not self._spinner_timer.isActive():
                self._spinner_timer.start()

            # Обновляем дисплей
            self.update()

    def hide_loading(self):
        """Скрыть загрузочный экран."""
        if getattr(self, "loading_overlay", None):
            self.loading_overlay.hide()

        # Останавливаем анимацию
        if getattr(self, "_spinner_timer", None):
            self._spinner_timer.stop()

    # _____END
    def local_page(self):
        self.local_tabs = default_local_tabs()
        self._local_pages_by_key = {}

        self.pincodes_xlsx_path = PIN_XLSX_FILEPATH
        self.pincodes_json_path = PIN_JSON_FILEPATH

        # фабрики локальных страниц по ключу (убираем прямые импорты из SheetTabsController)
        self._local_page_factories = {"local:pincodes": self._build_page_pincodes,
                                      "local:logistx": self._build_page_logistx, }

    def get_or_create_local_page(self, key: str):
        """Создать страницу по ключу (если ещё нет) и вернуть её."""
        if not hasattr(self, "_local_pages_by_key"):
            self._local_pages_by_key = {}

        if key in self._local_pages_by_key:
            return self._local_pages_by_key[key]

        factory = getattr(self, "_local_page_factories", {}).get(key)
        if not factory:
            return None

        page = factory()
        if page:
            self._local_pages_by_key[key] = page
        return page

    def _build_page_pincodes(self):
        # локальный импорт, чтобы не создавать жёсткую зависимость при импорте модулей
        from Navigation_Bot.gui.main_window.PinCodesPage import PinCodesPage

        page = PinCodesPage(xlsx_path=self.pincodes_xlsx_path,
                            json_path=self.pincodes_json_path,
                            log_func=self.log,
                            parent=self.stack, )
        self.stack.addWidget(page)
        return page

    def _build_page_logistx(self):
        # локальный импорт, чтобы убрать прямую зависимость из контроллера вкладок
        from LogistX.gui.logistxPage import LogistXPage

        page = LogistXPage(log_func=self.log, parent=self.stack)
        page.fact_clicked.connect(lambda row: self._on_logistx_fact_clicked(page, row))
        self.stack.addWidget(page)
        return page

    def _on_logistx_fact_clicked(self, page, row: int):
        """
        Обработчик кнопки ▶ на странице LogistX.
        UI сам формирует job_data (читает таблицу), а processor не зависит от QWidget.
        """
        try:
            job_data = page.build_close_race_job(row)
            if not job_data:
                return

            def _on_done(ctx, result: dict, _job: dict):
                page.apply_close_race_result(row=row, ctx=ctx, result=result)
                race_no = getattr(ctx, "race_name", "") or _job.get("race_no", "")
                if result.get("ok"):
                    self.ui_bridge.log.emit(f"✅ {race_no}: {result.get('message')}")
                else:
                    self.ui_bridge.log.emit(f"❌ {race_no}: {result.get('message')}")

            self.processor.logistx_race_service.close_race_async(job_data, on_done=_on_done)
        except Exception as e:
            if getattr(self, "ui_bridge", None):
                self.ui_bridge.log.emit(f"❌ LogistX ▶ ошибка: {e}")
            else:
                self.log(f"❌ LogistX ▶ ошибка: {e}")

    def init_managers(self):
        self.show_loading("Инициализация сервисов…", "Создание таблицы и контроллеров")
        self.services = AppServices(self)
        # build() возвращает ctx и сохраняет его в self.ctx
        self.services.build()

        self.show_loading("Инициализация вкладок…", "Подготовка к работе")
        self.sheet_tabs_controller = SheetTabsController(gui=self)
        self.sheet_tabs_controller.build()

    def init_ui(self):
        MainUiBuilder().build(self)

        # apply_table/resize callbacks должны вешаться ПОСЛЕ создания table
        hdr_h = self.table.horizontalHeader()
        hdr_v = self.table.verticalHeader()
        hdr_h.sectionResized.connect(
            lambda logical, old, new: self.ui_settings.on_col_resized(logical, old, new, self.table))
        hdr_v.sectionResized.connect(
            lambda logical, old, new: self.ui_settings.on_row_resized(logical, old, new, self.table))

    def _load_from_google(self):
        """Загрузить задачи из текущего листа в свой json."""
        self._reload_after_gsheet = True

        try:
            json_path = self._get_sheet_json_path()
            self.data_context.set_filepath(json_path)
            self.gsheet.pull_to_context_async(data_context=self.data_context,
                                              input_filepath=json_path,
                                              executor=self.executor)
            self.reload_and_show()

        except Exception as e:
            self.log(f'❌ Ошибка в NavigationGUI._load_from_google\n {e}')

    def _get_sheet_json_path(self) -> str:
        """
        Возвращает путь к json для текущего листа Google Sheets.
        Например: config/selected_data_3_Kontrol_TS.json
        """
        base = Path(INPUT_FILEPATH)

        if not getattr(self, "gsheet", None) or not getattr(self.gsheet, "sheet", None):
            return str(base)

        index = getattr(self.gsheet, "worksheet_index", 0) or 0
        title = getattr(self.gsheet.sheet, "title", f"sheet_{index}") or f"sheet_{index}"

        safe = re.sub(r"[^0-9A-Za-zА-Яа-я0-9]+", "_", title).strip("_")
        if not safe:
            safe = f"sheet_{index}"

        filename = f"{base.stem}_{index}_{safe}.json"
        return str(base.with_name(filename))

    def _toggle_search_bar(self):
        if self.search_bar.isVisible():
            self.search_bar.hide()
        else:
            self.search_bar.start()

    def reload_and_show(self):
        with self.json_lock:
            self.data_context.reload()
            self.json_data = self.data_context.get()
            init_processed_flags(self.json_data, self.json_data, loads_key="Выгрузка")
            self.data_context.save()

        view_order = self.sort_controller.build_view_order()
        self.table_manager.display(view_order=view_order)
        self.row_highlighter.set_view_order(view_order)  # real_to_visual
        self.row_highlighter.highlight_expired_unloads()  # вызов красной подсветки

    def _on_header_clicked(self, logicalIndex: int):
        if logicalIndex == 0:  # 🔍 — открыть справочник ID
            self.open_id_manager()
            return
        if logicalIndex == 2:
            self.sort_controller.current = None
            self.reload_and_show()
        elif logicalIndex == 8:
            self.sort_controller.current = "buffer"
            self.reload_and_show()
        elif logicalIndex == 7:
            self.sort_controller.current = "arrival"
            self.reload_and_show()

    def open_id_editor(self, row):
        car = self.json_data[row]
        dialog = TrackingIdEditor(car, log_func=self.log, parent=self)
        if dialog.exec():
            self.data_context.set(self.json_data)
            self.reload_and_show()

    def open_id_manager(self):
        dlg = IDManagerDialog(self)
        if dlg.exec():
            self.reload_and_show()
            self.log("✅ Id_car.json перезаписан")

    def switch_layout_mode(self, mode: LayoutMode | str):
        """
        Переключить режим размещения на двух мониторах
        Args:
            mode: LayoutMode.VERTICAL_SPLIT или LayoutMode.HORIZONTAL_SPLIT
                  (или строковые эквиваленты: "vertical" или "horizontal")
        """
        try:
            self._layout_manager.set_layout_mode(mode)

            # Пересчитываем позицию окна NavigationGUI и браузера
            self.browser_rect = self._layout_manager.apply_dual_screen_layout(self)

            # Обновляем browser_rect в processor (для браузера, который ещё не запущен)
            if hasattr(self, "processor") and self.processor:
                self.processor.browser_rect = self.browser_rect

            # Сохраняем выбранный режим в настройки
            if isinstance(mode, LayoutMode):
                mode_str = mode.value
            else:
                mode_str = mode

            # Получаем текущий монитор
            current_monitor_str = "first" if self._layout_manager.monitor_index == 0 else "second"

            # Сохраняем оба параметра в объект
            self.ui_settings.data["layout_mode"] = {
                "mode": mode_str,
                "monitor": current_monitor_str
            }
            self.ui_settings._schedule_save()

            # Перепозиционируем браузер если он открыт
            if self.browser_rect and hasattr(self, "processor") and self.processor.browser_session:
                try:
                    driver_manager = self.processor.browser_session.driver_manager
                    if driver_manager and driver_manager.driver:
                        driver_manager.driver.set_window_rect(self.browser_rect.get("x", 0),
                                                              self.browser_rect.get("y", 0),
                                                              self.browser_rect.get("width", 1024),
                                                              self.browser_rect.get("height", 768)
                                                              )
                        self.log(f"✅ Режим размещения изменен на {mode_str}")
                except Exception as e:
                    self.log(f"⚠️ Ошибка переповиционирования браузера: {e}")
            else:
                self.log(f"✅ Режим размещения изменен на {mode_str}")

        except ValueError as e:
            self.log(f"❌ Ошибка переключения режима: {e}")

    def switch_monitor(self, monitor_index: int):
        """
        Переключить монитор для размещения окон.
        Args:
            monitor_index: 0 для первого монитора, 1 для второго, и т.д.
        """
        try:
            self._layout_manager.set_monitor_index(monitor_index)

            # Пересчитываем позицию окна NavigationGUI и браузера
            self.browser_rect = self._layout_manager.apply_dual_screen_layout(self)

            # Обновляем browser_rect в processor (для браузера, который ещё не запущен)
            if hasattr(self, "processor") and self.processor:
                self.processor.browser_rect = self.browser_rect

            # Сохраняем выбранный монитор в настройки
            monitor_str = "first" if monitor_index == 0 else "second"
            if "layout_mode" not in self.ui_settings.data:
                self.ui_settings.data["layout_mode"] = {}
            elif isinstance(self.ui_settings.data["layout_mode"], str):
                # Миграция старого формата
                mode_str = self.ui_settings.data["layout_mode"]
                self.ui_settings.data["layout_mode"] = {"mode": mode_str,
                                                        "monitor": "second"}

            self.ui_settings.data["layout_mode"]["monitor"] = monitor_str
            self.ui_settings._schedule_save()

            # Перепозиционируем браузер если он открыт
            if self.browser_rect and hasattr(self, "processor") and self.processor.browser_session:
                try:
                    driver_manager = self.processor.browser_session.driver_manager
                    if driver_manager and driver_manager.driver:
                        driver_manager.driver.set_window_rect(self.browser_rect.get("x", 0),
                                                              self.browser_rect.get("y", 0),
                                                              self.browser_rect.get("width", 1024),
                                                              self.browser_rect.get("height", 768)
                                                              )
                        self.log(f"✅ Монитор изменен на {monitor_str}")
                except Exception as e:
                    self.log(f"⚠️ Ошибка переповиционирования браузера: {e}")
            else:
                self.log(f"✅ Монитор изменен на {monitor_str}")

        except ValueError as e:
            self.log(f"❌ Ошибка переключения монитора: {e}")

    def get_layout_mode(self) -> str:
        """Получить текущий режим размещения."""
        return self._layout_manager.layout_mode.value

    def get_monitor_index(self) -> int:
        """Получить текущий индекс монитора."""
        return self._layout_manager.monitor_index
