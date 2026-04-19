"""
Сервис синхронизации с Google Sheets.
Фасад над GoogleSheetsManager + DataCleaner + TasksService.
Ответственность: координация операций sync, которые трогают несколько компонентов.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class GoogleSyncService:
    """
    Координирует синхронизацию между локальным хранилищем и Google Sheets.
    
    Не должен вызываться для простых локальных операций (create/update/delete row).
    Вызывается для операций, которые трогают Google:
    - refresh_row_by_index: читать из Google одну строку
    - load_current_sheet: загрузить весь лист
    - upload_new_task: загрузить новую задачу в Google
    
    Зависит от:
    - GoogleSheetsManager: для работы с API
    - TasksService: для сохранения результата соглас
    - DataCleaner: для очистки данных
    """

    gsheet: Any  # GoogleSheetsManager
    tasks_service: Any  # TasksService
    data_context: Any  # DataContext
    cleaner: Any | None = None  # DataCleaner (optional, может быть создан в методе)
    log: Callable[[str], None] | None = None

    def _log(self, msg: str):
        """Безопасное логирование."""
        if self.log:
            self.log(msg)

    def _get_cleaner(self):
        if self.cleaner is not None:
            return self.cleaner
        from Navigation_Bot.bots.dataCleaner import DataCleaner
        return DataCleaner(data_context=self.data_context, log_func=self._log)

    def refresh_row_by_index(self, index_key: int) -> tuple[bool, dict | None, str | None]:
        """
        Перезагрузить одну строку из Google по её index_key.
        
        Процесс:
        1. Читает диапазон D-H из Google для этого index_key
        2. Обновляет локальное хранилище через TasksService
        3. Очищает только эту строку через DataCleaner
        4. Возвращает обновлённую задачу или ошибку
        
        Возвращает (ok, updated_task, error_message).
        """
        try:
            if not getattr(self.gsheet, "sheet", None):
                return False, None, "Google Sheets not initialized"

            # 1. Получить строку из Google
            rng = f"D{index_key}:H{index_key}"
            rows = self.gsheet.sheet.get(rng)
            if not rows or not rows[0]:
                return False, None, f"Row {index_key} is empty in Google"

            dh = list(rows[0])
            while len(dh) < 5:
                dh.append("")

            # 2. Найти строку в локальном хранилище по index_key
            real_idx = self.tasks_service.find_real_idx_by_index_key(index_key)
            if real_idx is None:
                return False, None, f"Row with index {index_key} not found locally"

            # d = dh[0] if len(dh) > 0 else ""
            # e = dh[1] if len(dh) > 1 else ""
            # f = dh[2] if len(dh) > 2 else ""
            # g = dh[3] if len(dh) > 3 else ""
            # h = dh[4] if len(dh) > 4 else ""
            #
            # raw_ts = re.sub(r"\s+", "", d)
            # number, phone = raw_ts[:9], raw_ts[9:]
            # formatted_ts = number[:6] + " " + number[6:] if len(number) >= 9 else number
            #
            # patch = {"ТС": formatted_ts,
            #          "Телефон": phone,
            #          "ФИО": e,
            #          "КА": f,
            #          "Погрузка": g,
            #          "Выгрузка": h,
            #          "raw_load": g,
            #          "raw_unload": h, }
            patch = self.tasks_service.build_row_from_google_dh(index_key, dh)

            ok, _, err = self.tasks_service.apply_patch(real_idx, patch)
            if not ok:
                return False, None, err

            # 4. Очистить строку
            cleaner = self._get_cleaner()
            cleaner.start_clean(only_indexes={index_key})

            # 5. Перезагрузить и вернуть
            self.data_context.reload()
            real_idx = self.tasks_service.find_real_idx_by_index_key(index_key)
            if real_idx is None:
                return False, None, f"Row with index {index_key} disappeared after refresh"

            updated_task = self.tasks_service.get_row(real_idx)
            # self._log(f"✅ Row {index_key} refreshed from Google")
            return True, updated_task, None

        except Exception as e:
            self._log(f"❌ GoogleSyncService.refresh_row_by_index: {e}")
            return False, None, str(e)

    def load_current_sheet(self) -> tuple[bool, str | None]:
        """
        Синхронно загрузить текущий лист из Google.

        Процесс:
        1. load_data()
        2. refresh_name(..., update_existing=False)
        3. DataCleaner.start_clean()
        4. reload() контекста
        """
        try:
            if not getattr(self.gsheet, "sheet", None):
                return False, "google_not_initialized"
            rows = self.gsheet.load_data()
            if not rows:
                return False, "no_rows_from_google"

            ok, add_stats, err = self.tasks_service.add_only_missing_rows_from_google(rows)
            if not ok:
                return False, err or "add_only_missing_rows_failed"

            active_indexes = set(rows.keys())

            ok, remove_stats, err = self.tasks_service.remove_completed_tasks(active_indexes)
            if not ok:
                return False, err or "remove_completed_tasks_failed"

            cleaner = self._get_cleaner()
            cleaner.start_clean()

            self.data_context.reload()
            self._log(f"🔄 Загрузка из Google: добавлено {add_stats['added']}, "
                      f"пропущено существующих {add_stats['skipped_existing']}, "
                      f"удалено завершённых {remove_stats['deleted']}")

            return True, None

        except Exception as e:
            self._log(f"❌ GoogleSyncService.load_current_sheet: {e}")
            return False, str(e)

    def load_current_sheet_async(self, executor, on_success: Callable[[], None] | None = None,
                                 on_error: Callable[[str], None] | None = None,
                                 on_started: Callable[[], None] | None = None, ) -> None:
        """
        Асинхронная обёртка для GUI.
        on_started()  — вызывается сразу перед submit
        on_success()  — вызывается после успешной загрузки
        on_error(err) — вызывается при ошибке
        """
        try:
            if on_started:
                on_started()

            def task():
                ok, err = self.load_current_sheet()
                if ok:
                    if on_success:
                        on_success()
                else:
                    if on_error:
                        on_error(err or "Unknown error")

            executor.submit(task)

        except Exception as e:
            if on_error:
                on_error(str(e))
            else:
                self._log(f"❌ GoogleSyncService.load_current_sheet_async: {e}")

    def upload_new_task(self, task: dict) -> tuple[bool, str | None]:
        """
        Выгрузить новую задачу в Google.
        Предполагает, что локально она уже сохранена.
        """
        try:
            if not getattr(self.gsheet, "sheet", None):
                return False, "google_not_initialized"

            if not hasattr(self.gsheet, "upload_new_row"):
                return False, "missing_upload_new_row"

            self.gsheet.upload_new_row(task)
            self._log(f"✅ Новая задача выгружена в Google (index={task.get('index')})")
            return True, None

        except Exception as e:
            self._log(f"⚠️ GoogleSyncService.upload_new_task: {e}")
            return False, str(e)

    def switch_worksheet(self, ws_index: int) -> tuple[bool, str | None]:
        """
        Переключить активный лист в Google.
        Возвращает (ok, error_message).
        """
        try:
            self.gsheet.set_active_worksheet(ws_index)
            # self._log(f"✅ Switched to worksheet {ws_index}")
            return True, None
        except Exception as e:
            self._log(f"❌ GoogleSyncService.switch_worksheet: {e}")
            return False, str(e)
