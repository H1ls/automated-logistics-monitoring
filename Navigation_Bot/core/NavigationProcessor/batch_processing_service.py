import json
import queue
import threading
import traceback
from pathlib import Path

from PyQt6.QtWidgets import QDialog


# TODO: Создать пул ошибок
# TODO: В конце вывод "ТС: какая ошибка \n"

class BatchProcessingService:
    def __init__(self, processor):
        self.processor = processor
        self.log = processor.log
        self._dialog_request_queue = queue.Queue()
        self._dialog_result_queue = queue.Queue()
        self._batch_errors = []
        self._batch_report_lines = []

    def process_all(self):
        ok, rows_with_keys, prev_single_mode = self._prepare_batch_processing()
        if not ok:
            return

        if not rows_with_keys:
            self.processor._single_row_processing = prev_single_mode
            self.processor.row_service.set_single_row_processing(prev_single_mode)
            self.processor._leave_processing("batch")
            self.processor._refresh_ui()
            self.log("ℹ️ Нет строк для обработки.")
            return

        def _run_batch():
            processed_count = 0
            try:
                processed_count = self._run_batch_rows(rows_with_keys)
            except Exception as e:
                self.log(f"❌ Ошибка batch-обработки: {e}")
                self.log(traceback.format_exc())
            finally:
                self._finalize_batch_processing(prev_single_mode, processed_count)

        threading.Thread(target=_run_batch, daemon=True).start()

    def _prepare_batch_processing(self) -> tuple[bool, list[tuple[int, int | None]], bool]:
        processor = self.processor
        if not processor._try_enter_batch_processing():
            self.log("⏳ Уже идёт обработка. Дождись завершения.")
            return False, [], False

        prev_single_mode = processor._single_row_processing
        processor._single_row_processing = False
        processor.row_service.set_single_row_processing(False)

        processor._clear_updated_rows()
        self._batch_errors.clear()
        self._batch_report_lines.clear()
        self.log("▶ Обработка всех ТС...")

        rows_with_keys = processor._get_processible_rows()
        return True, rows_with_keys, prev_single_mode

    def _run_batch_rows(self, rows_with_keys: list[tuple[int, int | None]]) -> int:
        processed_count = 0
        total_count = len(rows_with_keys)
        processor = self.processor

        for processed_count_cur, (row, index_key) in enumerate(rows_with_keys):
            future = processor.executor.submit(processor.process_row_wrapper, row, index_key)
            try:
                success, error_msg, index_key = future.result()
                processed_count = processed_count_cur + 1
                processor._highlight_row(row, index_key)

                row_info = self._get_row_info_for_display(row)
                if not success:
                    self._batch_errors.append(f"❌ {row_info}: {error_msg}")
                    self._batch_report_lines.append(f"❌ {row_info}: {error_msg}")
                else:
                    self._batch_report_lines.append(f"✅ {row_info}")

            except Exception as e:
                self.log(f"❌ Ошибка обработки строки {row}: {e}")
                processed_count = processed_count_cur + 1

                row_info = self._get_row_info_for_display(row)
                self._batch_errors.append(f"❌ {row_info}: {str(e)}")
                self._batch_report_lines.append(f"❌ {row_info}: {str(e)}")

            processor._flush_updated_rows_to_google()

            if processed_count_cur < total_count - 1:
                row_info = self._get_row_info_for_display(row)

                should_continue = self._show_pause_dialog(current_row_idx=row,
                                                          current_row_info=row_info,
                                                          processed_count=processed_count,
                                                          total_count=total_count)

                if not should_continue:
                    self._save_batch_progress(rows_with_keys[processed_count:], total_count, processed_count)
                    self.log(f"⏹ Обработка остановлена пользователем на {processed_count} ТС")
                    break

        return processed_count

    def _get_row_info_for_display(self, row_idx: int) -> str:
        try:
            tasks_service = self.processor.tasks_service
            if not tasks_service:
                return f"ТС #{row_idx}"

            task = tasks_service.get_row(row_idx)
            if not task:
                return f"ТС #{row_idx}"

            ts = task.get("ТС", "")
            fio = task.get("ФИО", "")

            if ts and fio:
                return f"{ts} - {fio}"
            if ts:
                return ts
            return f"ТС #{row_idx}"
        except Exception:
            return f"ТС #{row_idx}"

    def _show_pause_dialog(self, current_row_idx: int, current_row_info: str,
                           processed_count: int, total_count: int) -> bool:
        processor = self.processor
        if not processor.pause_dialog_factory or not processor.gui_parent:
            return True

        try:
            request_id = id(threading.current_thread())
            self._dialog_request_queue.put(
                {"request_id": request_id,
                 "current_row_idx": current_row_idx,
                 "current_row_info": current_row_info,
                 "processed_count": processed_count,
                 "total_count": total_count},
                timeout=1)

            try:
                result = self._dialog_result_queue.get(timeout=120)
                if result.get("request_id") == request_id:
                    return result.get("should_continue", True)

                self.log("⚠️ Ошибка синхронизации диалога паузы")
                return True
            except queue.Empty:
                self.log("⚠️ Таймаут ожидания результата диалога паузы")
                return True

        except Exception as e:
            self.log(f"⚠️ Ошибка при показе диалога паузы: {e}")
            return True

    def process_pending_dialog_requests(self):
        processor = self.processor
        while True:
            try:
                request = self._dialog_request_queue.get_nowait()
            except queue.Empty:
                break

            try:
                dialog = processor.pause_dialog_factory(current_row_idx=request["current_row_idx"],
                                                        current_row_info=request["current_row_info"],
                                                        processed_count=request["processed_count"],
                                                        total_count=request["total_count"],
                                                        timeout_seconds=processor.TIMEOUT_SECONDS,
                                                        parent=processor.gui_parent)

                result = dialog.exec()

                should_continue = True
                if result == QDialog.DialogCode.Rejected and dialog.was_stopped_by_user():
                    should_continue = False

                self._dialog_result_queue.put(
                    {"request_id": request["request_id"],
                     "should_continue": should_continue},
                    timeout=1)

            except Exception as e:
                self.log(f"⚠️ Ошибка обработки диалога паузы: {e}")
                self._dialog_result_queue.put({"request_id": request["request_id"], "should_continue": True},
                                              timeout=1)

    def _save_batch_progress(self, remaining_rows: list[tuple[int, int | None]],
                             total_count: int, processed_count: int):
        try:
            progress_file = Path("config/batch_progress.json")
            progress = {"remaining_rows": remaining_rows,
                        "total_count": total_count,
                        "processed_count": processed_count,
                        "timestamp": __import__("datetime").datetime.now().isoformat()}

            progress_file.parent.mkdir(parents=True, exist_ok=True)
            progress_file.write_text(json.dumps(progress, indent=2))
        except Exception as e:
            self.log(f"⚠️ Ошибка сохранения прогресса: {e}")

    def resume_batch_processing(self):
        progress_file = Path("config/batch_progress.json")

        if not progress_file.exists():
            self.log("ℹ️ Нет сохранённого прогресса для возобновления")
            return

        try:
            data = json.loads(progress_file.read_text())
            remaining_rows = data.get("remaining_rows", [])
            total_count = data.get("total_count", 0)
            processed_count = data.get("processed_count", 0)

            if not remaining_rows:
                progress_file.unlink()
                self.log("✅ Обработка уже завершена")
                return

            remaining_rows = [(r[0], r[1]) for r in remaining_rows]

            self.log(f"▶ Возобновление обработки: {processed_count} из {total_count} завершено")
            self._continue_batch_with_rows(remaining_rows, processed_count)
            progress_file.unlink()

        except Exception as e:
            self.log(f"❌ Ошибка возобновления batch: {e}")

    def _continue_batch_with_rows(self, rows_with_keys: list[tuple[int, int | None]], prev_processed: int):
        processor = self.processor
        if not processor._try_enter_batch_processing():
            self.log("⏳ Уже идёт обработка. Дождись завершения.")
            return

        prev_single_mode = processor._single_row_processing
        processor._single_row_processing = False
        processor.row_service.set_single_row_processing(False)

        processor._clear_updated_rows()

        def _run_batch():
            processed_count = 0
            try:
                processed_count = self._run_batch_rows(rows_with_keys)
            except Exception as e:
                self.log(f"❌ Ошибка batch-обработки: {e}")
                self.log(traceback.format_exc())
            finally:
                self._finalize_batch_processing(prev_single_mode, prev_processed + processed_count)

        threading.Thread(target=_run_batch, daemon=True).start()

    def _finalize_batch_processing(self, prev_single_mode: bool, processed_count: int) -> None:
        processor = self.processor
        processor._flush_updated_rows_to_google()

        if self._batch_report_lines:
            total = len(self._batch_report_lines)
            errors = len(self._batch_errors)
            ok = total - errors
            self.log(f"📋 Отчет пробежки: ✅ {ok} / ❌ {errors} / всего {total}")
            for line in self._batch_report_lines:
                self.log(f"  {line}")

        processor._leave_processing("batch")
        processor._single_row_processing = prev_single_mode
        processor.row_service.set_single_row_processing(prev_single_mode)

        processor._refresh_ui()
        self.log(f"✅ Пробежка завершена, ({processed_count} ТС)")
