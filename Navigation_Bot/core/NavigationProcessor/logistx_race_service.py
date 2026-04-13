from __future__ import annotations

from LogistX.onec.bot import OneCBot
from LogistX.onec.context import RaceContext


class LogistxRaceService:
    """
    Сервис закрытия рейса в LogistX / 1C.

    Отвечает за:
    - подготовку зависимостей OneCBot / WialonReportsBot
    - сбор RaceContext
    - запуск сценария close_race
    - возврат (ctx, result)
    """

    def __init__(self, logger, executor, browser_session, ui_bridge=None, rdp_activator=None):
        self.log = logger
        self.executor = executor
        self.browser_session = browser_session
        self.ui_bridge = ui_bridge
        self.rdp_activator = rdp_activator or (lambda: True)

        self.onec_bot = None

    def _uilog(self, msg: str) -> None:
        if self.ui_bridge:
            self.ui_bridge.log.emit(msg)
        else:
            self.log(msg)

    @staticmethod
    def geofence_from_cell_text(s: str) -> str:
        s = (s or "").strip()
        if s.startswith("🏷"):
            first = s.splitlines()[0]
            return first.replace("🏷", "").strip()
        return ""

    def ensure_dependencies(self) -> None:
        """
        Готовим браузерную сессию + reportsbot + onec_bot.
        """
        self.browser_session.ensure_ready()
        reportsbot = self.browser_session.ensure_reportsbot()

        if not self.onec_bot:
            self.onec_bot = OneCBot(rdp_activator=self.rdp_activator, reportsbot=reportsbot, log_func=self.log, )

    def build_job_data_from_page(self, page, row: int) -> dict:
        """
        Собирает job_data из строки LogistXPage.
        """
        obj = page.rows[row]

        race_no = str(obj.get("Рейс", "") or "").strip()
        unit = str(obj.get("ТС", "") or "").strip()

        from_item = page.table.item(row, page.COL_FROM)
        to_item = page.table.item(row, page.COL_TO)

        load_zone = self.geofence_from_cell_text(from_item.text() if from_item else "")
        unload_zone = self.geofence_from_cell_text(to_item.text() if to_item else "")

        return {"row": row,
                "obj": obj,
                "race_no": race_no,
                "unit": unit,
                "load_zone": load_zone,
                "unload_zone": unload_zone, }

    def _build_context(self, job_data: dict) -> RaceContext:
        obj = job_data["obj"]
        row = int(job_data["row"])
        race_no = str(job_data["race_no"] or "").strip()
        unit = str(job_data["unit"] or "").strip()
        load_zone = str(job_data["load_zone"] or "").strip()
        unload_zone = str(job_data["unload_zone"] or "").strip()

        if not race_no:
            raise ValueError("Пустой 'Рейс' в строке")
        if not unit:
            raise ValueError("Пустой 'ТС' в строке")
        if not load_zone:
            raise ValueError("Не определена geofence погрузки")
        if not unload_zone:
            raise ValueError("Не определена geofence выгрузки")

        return RaceContext(race_name=race_no,
                           race_search_text=race_no,
                           meta={"row": row,
                                 "unit": unit,
                                 "load_zone": load_zone,
                                 "unload_zone": unload_zone,

                                 # что уже было сохранено по строке ранее
                                 "saved_status_1c": obj.get("status_1c", ""),
                                 "saved_status_text": obj.get("status_text", ""),
                                 "saved_departure_dt_1c": obj.get("departure_dt_1c", ""),
                                 "saved_onec_progress": obj.get("onec_progress", {}) or {},
                                 "saved_wialon_payload": obj.get("wialon_payload", {}) or {}, }, )

    def run_close_race(self, job_data: dict):
        """
        Синхронный запуск close_race.
        Возвращает (ctx, result).
        """
        self.ensure_dependencies()
        ctx = self._build_context(job_data)
        result = self.onec_bot.close_race(ctx)
        return ctx, result

    def close_race_async(self, job_data: dict, on_done=None):
        """
        Асинхронный запуск close_race.
        on_done(ctx, result, job_data) будет вызван в GUI-потоке, если есть ui_bridge.
        """
        self.ensure_dependencies()

        fut = self.executor.submit(self.run_close_race, job_data)

        if not on_done:
            def on_done(ctx, result, _job):
                race_no = getattr(ctx, "race_name", "") or _job.get("race_no", "")
                if result.get("ok"):
                    self._uilog(f"✅ {race_no}: {result.get('message')}")
                else:
                    self._uilog(f"❌ {race_no}: {result.get('message')}")

        def _apply():
            try:
                ctx, result = fut.result()
                on_done(ctx, result, job_data)
            except Exception as e:
                self._uilog(f"❌ Ошибка close_race_async: {e}")

        if self.ui_bridge:
            fut.add_done_callback(lambda _f: self.ui_bridge.call.emit(_apply))
        else:
            fut.add_done_callback(lambda _f: _apply())
