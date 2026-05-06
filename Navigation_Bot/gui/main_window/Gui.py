import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
import json
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QWidget
from Navigation_Bot.core.paths import INPUT_FILEPATH
from Navigation_Bot.core.paths import PIN_XLSX_FILEPATH, PIN_JSON_FILEPATH
from Navigation_Bot.gui.builders.main_ui_builder import MainUiBuilder
from Navigation_Bot.core.application.services.app_services import AppServices
from Navigation_Bot.gui.controllers.sheet_tabs_controller import SheetTabsController
from Navigation_Bot.gui.controllers.local_pages_controller import LocalPagesController
from Navigation_Bot.gui.controllers.signals_binder import SignalsBinder
from Navigation_Bot.gui.settings.ui_bridge import UiBridge
from Navigation_Bot.gui.controllers.layout_controller import LayoutController
from Navigation_Bot.gui.dialogs.iD_manager_dialog import IDManagerDialog
from Navigation_Bot.gui.dialogs.tracking_id_editor import TrackingIdEditor
from Navigation_Bot.gui.settings.ui_settings import UiSettingsManager
from Navigation_Bot.gui.dialogs.create_race_dialog import CreateRaceDialog
from Navigation_Bot.gui.controllers.loading_overlay_controller import LoadingOverlayController
from Navigation_Bot.gui.dialogs.navigation_history_dialog import NavigationHistoryDialog


class NavigationGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.log = lambda msg: print(msg)
        self.INPUT_FILEPATH = INPUT_FILEPATH
        self.PIN_XLSX_FILEPATH = PIN_XLSX_FILEPATH
        self.PIN_JSON_FILEPATH = PIN_JSON_FILEPATH

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

        self.loading = LoadingOverlayController(self)
        self.show()
        self.loading.show("Инициализация приложения…", "Подготовка интерфейса")

        QApplication.processEvents()
        self.ui_bridge = UiBridge(self)
        self.ui_settings.apply_window(self)
        self.ui_settings.apply_table(self.table)

        # Читаем режим размещения и выбор монитора из настроек
        self.layout_controller = LayoutController(self)
        self.layout_controller.setup()

        self.local_pages_controller = LocalPagesController(self)

        QTimer.singleShot(0, self._startup_step_local_pages)

    def _startup_step_local_pages(self):
        try:
            self.loading.show("Загрузка локальных данных…", "Подготовка локальных страниц")
            self.local_pages_controller.setup()
        except Exception as e:
            self.log(f"❌ Ошибка startup(local_pages): {e}")
        finally:
            QTimer.singleShot(0, self._startup_step_managers)

    def _startup_step_managers(self):
        try:
            self.loading.show("Инициализация сервисов…", "Создание таблицы и контроллеров")
            self.init_managers()
        except Exception as e:
            self.log(f"❌ Ошибка startup(managers): {e}")
        finally:
            QTimer.singleShot(0, self._startup_step_signals)

    def _startup_step_signals(self):
        try:
            self.loading.show("Привязка сигналов…", "Подготовка событий интерфейса")
            SignalsBinder(self).bind()
        except Exception as e:
            self.log(f"❌ Ошибка startup(signals): {e}")
        finally:
            QTimer.singleShot(0, self._startup_finish)

    def _startup_finish(self):
        try:
            self.loading.show("Готово", "Приложение готово к работе")
        finally:
            QTimer.singleShot(150, self.loading.hide)
            # Запустить таймер обработки диалогов паузы
            self._start_dialog_processor_timer()

    def _open_wialon(self):
        self.loading.show("Запуск Wialon…")

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
                self.ui_bridge.call.emit(lambda: self.loading.hide())

        self.executor.submit(job)

    def closeEvent(self, event):
        """Гарантированная очистка при закрытии окна"""
        try:
            # Остановить таймер обработки диалогов
            if hasattr(self, 'dialog_processor_timer') and self.dialog_processor_timer:
                self.dialog_processor_timer.stop()

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
        if getattr(self, "loading", None):
            self.loading.reposition()

    def get_or_create_local_page(self, key: str):
        if not getattr(self, "local_pages_controller", None):
            return None
        return self.local_pages_controller.get_or_create_page(key)

    def _apply_runtime_settings(self):
        try:
            if getattr(self, "row_highlighter", None):
                self.row_highlighter.apply_settings(self.ui_settings.data)
        except Exception as e:
            self.log(f"⚠️ Не удалось применить runtime-настройки: {e}")

    def init_managers(self):
        self.services = AppServices(self)
        self.services.build()

        self._apply_runtime_settings()

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
            self.task_repository.set_filepath(json_path)

            if not getattr(self, "google_sync_service", None):
                self.log("⚠️ GoogleSyncService не подключён")
                return

            self.google_sync_service.load_current_sheet_async(
                executor=self.executor,
                on_started=lambda: self.loading.show("Загрузка из Google Sheets", "Получение данных"),
                on_success=lambda: self.ui_bridge.call.emit(self._on_google_load_success),
                on_error=lambda err: self.ui_bridge.call.emit(lambda: self._on_google_load_error(err)), )

        except Exception as e:
            self.log(f'❌ Ошибка в NavigationGUI._load_from_google\n {e}')

    def _open_create_race_dialog(self):
        try:
            dialog = CreateRaceDialog(task_repository=self.task_repository, log_func=self.log, parent=self, )

            if not dialog.exec():
                return

            payload = dialog.get_payload()

            if not getattr(self, "new_task_workflow_service", None):
                self.log("⚠️ NewTaskWorkflowService не подключён")
                return

            ok, new_task, err = self.new_task_workflow_service.create_from_dialog_payload(payload,
                                                                                          upload_to_google=True, )

            if not ok:
                self.log(f"❌ Не удалось создать рейс: {err}")
                return

            self.reload_and_show()
            self.log(f"✅ Рейс создан (index={new_task.get('index')})")

        except Exception as e:
            self.log(f"❌ Ошибка в _open_create_race_dialog: {e}")

    def _on_google_load_success(self):
        if getattr(self, "loading", None):
            self.loading.hide()
        self.reload_and_show()

    def _on_google_load_error(self, err: str):
        if getattr(self, "loading", None):
            self.loading.hide()
        self.log(f"❌ Ошибка загрузки из Google: {err}")

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
            self.task_repository.reload()
            self.json_data = self.task_repository.get()

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
            self.task_repository.set(self.json_data)
            self.reload_and_show()

    def open_id_manager(self):
        dlg = IDManagerDialog(self)
        if dlg.exec():
            self.reload_and_show()
            self.log("✅ Id_car.json перезаписан")

    # TODO: Урезать оставить минимум
    def _open_navigation_history_dialog(self):
        try:
            row = self.table.currentRow()
            if row < 0:
                self.log("⚠️ Выбери строку для просмотра истории навигации")
                return

            real_idx = self.table_manager._visual_to_real(row)
            if real_idx is None:
                self.log("⚠️ Не удалось определить реальную строку")
                return

            data = self.task_repository.get() or []
            if not (0 <= real_idx < len(data)):
                self.log("⚠️ Строка не найдена")
                return

            task_index = data[real_idx].get("index")
            if not task_index:
                self.log("⚠️ У строки нет index")
                return

            nav_service = getattr(self, "navigation_history_service", None)
            route_service = getattr(self, "route_estimate_history_service", None)

            if not nav_service:
                self.log("⚠️ NavigationHistoryService не подключён")
                return

            nav_rows = nav_service.get_by_task_index(task_index)

            route_rows = []
            if route_service:
                route_rows = route_service.get_by_task_index(task_index)

            note_rows = []
            note_service = getattr(self, "note_history_service", None)
            if note_service:
                note_rows = note_service.get_by_task_index(task_index)

            dlg = NavigationHistoryDialog(task_index=task_index,
                                          nav_rows=nav_rows,
                                          route_rows=route_rows,
                                          note_rows=note_rows,
                                          note_history_service=note_service,
                                          parent=self, )
            dlg.exec()

        except Exception as e:
            self.log(f"❌ Ошибка открытия истории навигации: {e}")

    # TODO: Оставить обертку - урезать
    def _on_btn_process_all_clicked(self):
        """
        Обработчик кнопки 'Пробежать все ТС'.
        Проверяет наличие прерванного прогресса и возобновляет его,
        или начинает новую обработку.
        """
        import json
        from pathlib import Path

        progress_file = Path("config/batch_progress.json")

        if progress_file.exists():
            try:
                data = json.loads(progress_file.read_text())
                remaining = data.get("remaining_rows", [])

                if remaining:
                    # Есть сохранённый прогресс - предложить возобновить
                    from PyQt6.QtWidgets import QMessageBox

                    processed = data.get("processed_count", 0)
                    total = data.get("total_count", 0)

                    result = QMessageBox.question(
                        self,
                        "Возобновить обработку",
                        f"Обнаружена прерванная обработка:\n"
                        f"Завершено: {processed} из {total} ТС\n\n"
                        f"Возобновить с того же места?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
                    )

                    if result == QMessageBox.StandardButton.Yes:
                        self.processor.resume_batch_processing()
                        return
                    elif result == QMessageBox.StandardButton.Cancel:
                        # Пользователь отменил - ничего не делаем
                        return
                    # No - начнем заново
            except Exception as e:
                self.log(f"⚠️ Ошибка проверки прогресса: {e}")

        # Начать новую обработку
        self.processor.process_all()

    def _start_dialog_processor_timer(self):
        """
        Запустить периодический таймер для обработки запросов на показ диалогов
        из рабочих потоков.
        """
        if hasattr(self, 'dialog_processor_timer') and self.dialog_processor_timer.isActive():
            self.log("⚠️ Таймер диалогов уже активен, пропускаем запуск")
            return

        self.dialog_processor_timer = QTimer()
        self.dialog_processor_timer.timeout.connect(self._process_dialog_requests)

        # Проверяем очередь диалогов каждые 50 мс
        self.dialog_processor_timer.start(50)
        # self.log("✅ Таймер диалогов запущен (интервал 50мс)")

    def _process_dialog_requests(self):
        """
        Обработать ожидающие запросы на показ диалогов.
        Вызывается периодически из главного потока.
        """
        try:
            if hasattr(self, 'processor') and self.processor:
                pending_count = self.processor._dialog_request_queue.qsize()
                if pending_count > 0:
                    pass
                    # self.log(f"🔔 Обработка {pending_count} запросов на диалоги...")
                self.processor.process_pending_dialog_requests()
        except Exception as e:
            print(f"⚠️ Ошибка обработки запросов диалогов: {e}")
            self.log(f"⚠️ Ошибка обработки запросов диалогов: {e}")
