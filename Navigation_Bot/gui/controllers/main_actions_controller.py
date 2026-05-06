import json
from pathlib import Path

from PyQt6.QtWidgets import QMessageBox

from Navigation_Bot.gui.dialogs.create_race_dialog import CreateRaceDialog
from Navigation_Bot.gui.dialogs.iD_manager_dialog import IDManagerDialog
from Navigation_Bot.gui.dialogs.navigation_history_dialog import NavigationHistoryDialog
from Navigation_Bot.gui.dialogs.tracking_id_editor import TrackingIdEditor


class MainActionsController:
    def __init__(self, gui):
        self.gui = gui

    def open_wialon(self) -> None:
        gui = self.gui
        gui.loading.show("Запуск Wialon…")

        def job():
            try:
                gui.processor.browser_session.ensure_ready()
            except Exception as e:
                if getattr(gui, "ui_bridge", None):
                    gui.ui_bridge.log.emit(f"❌ Ошибка запуска Wialon: {e}")
                else:
                    gui.log(f"❌ Ошибка запуска Wialon: {e}")
            finally:
                gui.ui_bridge.call.emit(lambda: gui.loading.hide())

        gui.executor.submit(job)

    def load_from_google(self) -> None:
        gui = self.gui
        gui._reload_after_gsheet = True

        try:
            json_path = gui._get_sheet_json_path()
            gui.task_repository.set_filepath(json_path)

            if not getattr(gui, "google_sync_service", None):
                gui.log("⚠️ GoogleSyncService не подключён")
                return

            gui.google_sync_service.load_current_sheet_async(
                executor=gui.executor,
                on_started=lambda: gui.loading.show("Загрузка из Google Sheets", "Получение данных"),
                on_success=lambda: gui.ui_bridge.call.emit(self._on_google_load_success),
                on_error=lambda err: gui.ui_bridge.call.emit(lambda: self._on_google_load_error(err)),
            )
        except Exception as e:
            gui.log(f"❌ Ошибка в NavigationGUI._load_from_google\n {e}")

    def _on_google_load_success(self) -> None:
        self.gui.hide_loading()
        self.gui.reload_and_show()

    def _on_google_load_error(self, err: str) -> None:
        self.gui.hide_loading()
        self.gui.log(f"❌ Ошибка загрузки из Google: {err}")

    def open_create_race_dialog(self) -> None:
        gui = self.gui
        try:
            dialog = CreateRaceDialog(task_repository=gui.task_repository, log_func=gui.log, parent=gui)

            if not dialog.exec():
                return

            if not getattr(gui, "new_task_workflow_service", None):
                gui.log("⚠️ NewTaskWorkflowService не подключён")
                return

            ok, new_task, err = gui.new_task_workflow_service.create_from_dialog_payload(dialog.get_payload(),
                                                                                         upload_to_google=True,)

            if not ok:
                gui.log(f"❌ Не удалось создать рейс: {err}")
                return

            gui.reload_and_show()
            gui.log(f"✅ Рейс создан (index={new_task.get('index')})")
        except Exception as e:
            gui.log(f"❌ Ошибка в _open_create_race_dialog: {e}")

    def open_id_editor(self, row: int) -> None:
        gui = self.gui
        car = gui.json_data[row]
        dialog = TrackingIdEditor(car, log_func=gui.log, parent=gui)
        if dialog.exec():
            gui.task_repository.set(gui.json_data)
            gui.reload_and_show()

    def open_id_manager(self) -> None:
        gui = self.gui
        dialog = IDManagerDialog(gui)
        if dialog.exec():
            gui.reload_and_show()
            gui.log("✅ Id_car.json перезаписан")

    def open_navigation_history_dialog(self) -> None:
        gui = self.gui
        try:
            task_index = self._selected_task_index()
            if not task_index:
                return

            nav_service = getattr(gui, "navigation_history_service", None)
            route_service = getattr(gui, "route_estimate_history_service", None)
            note_service = getattr(gui, "note_history_service", None)

            if not nav_service:
                gui.log("⚠️ NavigationHistoryService не подключён")
                return

            dialog = NavigationHistoryDialog(
                task_index=task_index,
                nav_rows=nav_service.get_by_task_index(task_index),
                route_rows=route_service.get_by_task_index(task_index) if route_service else [],
                note_rows=note_service.get_by_task_index(task_index) if note_service else [],
                note_history_service=note_service,
                parent=gui,
            )
            dialog.exec()
        except Exception as e:
            gui.log(f"❌ Ошибка открытия истории навигации: {e}")

    def _selected_task_index(self):
        gui = self.gui
        row = gui.table.currentRow()
        if row < 0:
            gui.log("⚠️ Выбери строку для просмотра истории навигации")
            return None

        real_idx = gui.table_manager._visual_to_real(row)
        if real_idx is None:
            gui.log("⚠️ Не удалось определить реальную строку")
            return None

        data = gui.task_repository.get() or []
        if not (0 <= real_idx < len(data)):
            gui.log("⚠️ Строка не найдена")
            return None

        task_index = data[real_idx].get("index")
        if not task_index:
            gui.log("⚠️ У строки нет index")
            return None
        return task_index

    def on_btn_process_all_clicked(self) -> None:
        progress = self._load_batch_progress()
        if progress and progress.get("remaining_rows"):
            choice = self._ask_resume_batch(progress)
            if choice == QMessageBox.StandardButton.Yes:
                self.gui.processor.resume_batch_processing()
                return
            if choice == QMessageBox.StandardButton.Cancel:
                return

        self.gui.processor.process_all()

    def _load_batch_progress(self) -> dict | None:
        progress_file = Path("config/batch_progress.json")
        if not progress_file.exists():
            return None

        try:
            return json.loads(progress_file.read_text(encoding="utf-8"))
        except Exception as e:
            self.gui.log(f"⚠️ Ошибка проверки прогресса: {e}")
            return None

    def _ask_resume_batch(self, progress: dict):
        processed = progress.get("processed_count", 0)
        total = progress.get("total_count", 0)

        return QMessageBox.question(
            self.gui,
            "Возобновить обработку",
            f"Обнаружена прерванная обработка:\n"
            f"Завершено: {processed} из {total} ТС\n\n"
            f"Возобновить с того же места?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
        )
