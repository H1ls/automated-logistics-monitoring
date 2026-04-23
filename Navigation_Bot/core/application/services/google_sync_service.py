from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from Navigation_Bot.core.application.mappers.google_row_mapper import GoogleRowMapper


@dataclass(slots=True)
class GoogleSyncService:
    """
    Координирует синхронизацию между локальным хранилищем и Google Sheets.

    Не должен вызываться для простых локальных операций (create/update/delete row).
    Вызывается для операций, которые трогают Google:
    - refresh_row_by_index: читать из Google одну строку
    - load_current_sheet: загрузить весь лист
    - upload_new_task: загрузить новую задачу в Google
    """

    gsheet: Any
    tasks_service: Any
    data_context: Any
    cleaner: Any | None = None
    log: Callable[[str], None] | None = None

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def _get_cleaner(self):
        if self.cleaner is not None:
            return self.cleaner
        from Navigation_Bot.bots.data_cleaner import DataCleaner
        return DataCleaner(data_context=self.data_context, log_func=self._log)

    # --- Helpers: common
    def _ensure_google_ready(self) -> tuple[bool, None, str | None]:
        if not getattr(self.gsheet, "sheet", None):
            return False, None, "google_not_initialized"
        return True, None, None

    def _reload_context(self) -> None:
        self.data_context.reload()

    # --- Helpers: refresh_row_by_index
    def _fetch_google_row_dh(self, index_key: int) -> tuple[bool, list[str] | None, str | None]:
        try:
            rng = f"D{index_key}:H{index_key}"
            rows = self.gsheet.sheet.get(rng)
            if not rows or not rows[0]:
                return False, None, f"Row {index_key} is empty in Google"

            dh = list(rows[0])
            while len(dh) < 5:
                dh.append("")

            return True, dh, None
        except Exception as e:
            return False, None, str(e)

    def _find_local_row_index(self, index_key: int) -> tuple[bool, int | None, str | None]:
        real_idx = self.tasks_service.find_real_idx_by_index_key(index_key)
        if real_idx is None:
            return False, None, f"Row with index {index_key} not found locally"
        return True, real_idx, None

    def _build_patch_from_google_row(self, index_key: int, dh: list[str]) -> tuple[bool, dict | None, str | None]:
        try:
            patch = GoogleRowMapper.build_row(index_key, dh)
            return True, patch, None
        except Exception as e:
            return False, None, str(e)

    def _apply_google_patch_to_row(self, real_idx: int, patch: dict) -> tuple[bool, str | None]:
        ok, _, err = self.tasks_service.apply_patch(real_idx, patch)
        if not ok:
            return False, err
        return True, None

    def _clean_single_row(self, index_key: int) -> tuple[bool, str | None]:
        try:
            cleaner = self._get_cleaner()
            cleaner.start_clean(only_indexes={index_key})
            return True, None
        except Exception as e:
            return False, str(e)

    def _reload_and_get_row(self, index_key: int) -> tuple[bool, dict | None, str | None]:
        try:
            self._reload_context()
            real_idx = self.tasks_service.find_real_idx_by_index_key(index_key)
            if real_idx is None:
                return False, None, f"Row with index {index_key} disappeared after refresh"

            updated_row = self.tasks_service.get_row(real_idx)
            return True, updated_row, None
        except Exception as e:
            return False, None, str(e)

    # --- Public: refresh one row
    def refresh_row_by_index(self, index_key: int) -> tuple[bool, dict | None, str | None]:
        """
        Перезагрузить одну строку из Google по её index_key.

        Процесс:
        1. Читает диапазон D-H из Google для этого index_key
        2. Обновляет локальное хранилище через TasksService
        3. Очищает только эту строку через DataCleaner
        4. Возвращает обновлённую строку или ошибку
        """
        try:
            # проверить Google
            ok,_, err = self._ensure_google_ready()
            if not ok:
                return False, None, err
            # получить строку
            ok, dh, err = self._fetch_google_row_dh(index_key)
            if not ok:
                return False, None, err
            # найти локальный индекс
            ok, real_idx, err = self._find_local_row_index(index_key)
            if not ok:
                return False, None, err
            # собрать patch
            ok, patch, err = self._build_patch_from_google_row(index_key, dh)
            if not ok:
                return False, None, err
            # применить patch
            ok, err = self._apply_google_patch_to_row(real_idx, patch)
            if not ok:
                return False, None, err
            # почистить строку
            ok, err = self._clean_single_row(index_key)
            if not ok:
                return False, None, err

            return self._reload_and_get_row(index_key)

        except Exception as e:
            self._log(f"❌ GoogleSyncService.refresh_row_by_index: {e}")
            return False, None, str(e)

    # --- Helpers: load_current_sheet
    def _fetch_current_sheet_rows(self) -> tuple[bool, dict[int, list[str]] | None, str | None]:
        try:
            rows = self.gsheet.load_data()
            if not rows:
                return False, None, "no_rows_from_google"
            return True, rows, None
        except Exception as e:
            return False, None, str(e)

    def _sync_new_rows(self, rows: dict[int, list[str]]) -> tuple[bool, dict | None, str | None]:
        return self.tasks_service.add_only_missing_rows_from_google(rows)

    def _remove_completed(self, active_indexes: set[int]) -> tuple[bool, dict | None, str | None]:
        return self.tasks_service.remove_completed_tasks(active_indexes)

    def _clean_local_data(self) -> tuple[bool, str | None]:
        try:
            cleaner = self._get_cleaner()
            cleaner.start_clean()
            return True, None
        except Exception as e:
            return False, str(e)

    def _reload_after_sheet_sync(self) -> tuple[bool, str | None]:
        try:
            self._reload_context()
            return True, None
        except Exception as e:
            return False, str(e)

    # --- Public: load full current sheet
    def load_current_sheet(self) -> tuple[bool, str | None]:
        """
        Синхронно загрузить текущий лист из Google.

        Процесс:
        1. load_data()
        2. добавить новые строки
        3. удалить завершённые
        4. DataCleaner.start_clean()
        5. reload() контекста
        """
        try:
            # проверить Google
            ok,_, err = self._ensure_google_ready()
            if not ok:
                return False, err
            # получить rows
            ok, rows, err = self._fetch_current_sheet_rows()
            if not ok:
                return False, err
            # добавить новые
            ok, add_stats, err = self._sync_new_rows(rows)
            if not ok:
                return False, err or "add_only_missing_rows_failed"

            # удалить завершённые
            active_indexes = set(rows.keys())
            ok, remove_stats, err = self._remove_completed(active_indexes)
            if not ok:
                return False, err or "remove_completed_tasks_failed"
            # почистить локальные данные
            ok, err = self._clean_local_data()
            if not ok:
                return False, err
            # reload
            ok, err = self._reload_after_sheet_sync()
            if not ok:
                return False, err

            self._log(f"🌎 Загрузка из Google: добавлено {add_stats['added']}, "
                      f"удалено завершённых {remove_stats['deleted']}")
            return True, None

        except Exception as e:
            self._log(f"❌ GoogleSyncService.load_current_sheet: {e}")
            return False, str(e)

    # --- Async wrapper
    def load_current_sheet_async(self,
                                 executor,
                                 on_success: Callable[[], None] | None = None,
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

    # --- Other public methods
    def upload_new_task(self, task: dict) -> tuple[bool, str | None]:
        """
        Выгрузить новую задачу в Google.
        Предполагает, что локально она уже сохранена.
        """
        try:
            ok,_, err = self._ensure_google_ready()
            if not ok:
                return False, err

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
        Возвращает (ok, error_message)
        """
        try:
            self.gsheet.set_active_worksheet(ws_index)
            return True, None
        except Exception as e:
            self._log(f"❌ GoogleSyncService.switch_worksheet: {e}")
            return False, str(e)
