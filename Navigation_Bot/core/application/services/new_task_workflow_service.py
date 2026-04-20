from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class NewTaskWorkflowService:
    """
    Сценарий создания новой задачи / рейса из диалога.

    Отвечает за:
    - нормализацию payload из CreateRaceDialog
    - сбор task через TaskEditService
    - сохранение task через TasksService
    - опциональную выгрузку в Google через GoogleSyncService
    """

    tasks_service: Any
    task_edit_service: Any
    google_sync_service: Any | None = None
    log: Callable[[str], None] | None = None

    def _log(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    @staticmethod
    def _normalize_payload(payload: dict) -> tuple[str, str, str, str, dict]:
        payload = payload or {}

        ts = str(payload.get("ts", "") or "").strip()
        phone = str(payload.get("phone", "") or "").strip()
        ka = str(payload.get("ka", "") or "").strip()
        fio = str(payload.get("fio", "") or "").strip()
        comment = str(payload.get("comment", "") or "").strip()
        buffer = dict(payload.get("buffer", {}) or {})

        # Общий комментарий кладём в существующий формат:
        # через блок {"Комментарий": "..."} в Погрузка
        if comment:
            load_blocks = list(buffer.get("Погрузка", []) or [])
            load_blocks = [blk for blk in load_blocks
                            if not (isinstance(blk, dict) and "Комментарий" in blk)
                           ]

            load_blocks.append({"Комментарий": comment})
            buffer["Погрузка"] = load_blocks

        ts_phone = f"{ts} {phone}".strip()
        return ts_phone, ka, fio, comment, buffer

    def create_from_buffer(self,*,ts_phone: str,ka: str,fio: str,buffer: dict,upload_to_google: bool = True,
                           ) -> tuple[bool, dict | None, str | None]:
        if not self.task_edit_service:
            return False, None, "task_edit_service_missing"

        if not self.tasks_service:
            return False, None, "tasks_service_missing"

        ok, task, err = self.task_edit_service.build_task_from_buffer(ts_phone=ts_phone,
                                                                      ka=ka,
                                                                      fio=fio,
                                                                      buffer=buffer, )
        if not ok:
            return False, None, err

        ok, new_task, err = self.tasks_service.add_task(task)
        if not ok:
            return False, None, err

        if upload_to_google and self.google_sync_service:
            ok_google, err_google = self.google_sync_service.upload_new_task(new_task)
            if not ok_google:
                # локально задача уже создана — это не фатал для всей операции
                self._log(f"⚠️ Задача создана локально, но не выгружена в Google: {err_google}")
            else:
                self._log("☁️ Рейс выгружен в Google")

        return True, new_task, None

    def create_from_dialog_payload(self, payload: dict, *, upload_to_google: bool = True, ) -> tuple[
        bool, dict | None, str | None]:
        if not isinstance(payload, dict):
            return False, None, "invalid_payload"

        ts_phone, ka, fio, _comment, buffer = self._normalize_payload(payload)

        return self.create_from_buffer(ts_phone=ts_phone,
                                       ka=ka,
                                       fio=fio,
                                       buffer=buffer,
                                       upload_to_google=upload_to_google, )
