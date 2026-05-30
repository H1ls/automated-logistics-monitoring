from __future__ import annotations
from Navigation_Bot.gui.main_window.pin_codes_page import PinCodesPage


class LocalPagesController:
    """
    Управляет локальными страницами GUI:
    - хранит реестр фабрик
    - создаёт страницы по key
    - кэширует уже созданные страницы
    - вешает обработчики на специальные локальные страницы (например LogistX)
    """

    def __init__(self, gui):
        self.gui = gui
        self._pages_by_key: dict[str, object] = {}
        self._factories: dict[str, callable] = {}

    def setup(self) -> None:
        """
        Регистрирует локальные страницы и сохраняет связанные пути/настройки.
        """
        g = self.gui

        g.local_tabs = self._default_local_tabs()
        g.pincodes_xlsx_path = g.PIN_XLSX_FILEPATH
        g.pincodes_json_path = g.PIN_JSON_FILEPATH

        self._factories = {
            "local:pincodes": self._build_page_pincodes,
            "local:logistx": self._build_page_logistx,
        }

    def get_or_create_page(self, key: str):
        if key in self._pages_by_key:
            return self._pages_by_key[key]

        factory = self._factories.get(key)
        if not factory:
            return None

        page = factory()
        if page is not None:
            self._pages_by_key[key] = page
        return page

    @staticmethod
    def _default_local_tabs() -> list[dict]:
        # локальный импорт, чтобы не тащить сюда зависимость при module import
        from Navigation_Bot.gui.settings.sheet_tab_definitions import default_local_tabs
        return default_local_tabs()

    def _build_page_pincodes(self):

        g = self.gui
        page = PinCodesPage(xlsx_path=g.pincodes_xlsx_path,
                            json_path=g.pincodes_json_path,
                            log_func=g.log,
                            parent=g.stack,
                            )

        g.stack.addWidget(page)
        return page

    def _build_page_logistx(self):
        from LogistX.gui.logistx_page import LogistXPage

        g = self.gui
        page = LogistXPage(log_func=g.log, parent=g.stack)
        page.fact_clicked.connect(lambda row: self._on_logistx_fact_clicked(page, row))
        g.stack.addWidget(page)
        return page

    def _on_logistx_fact_clicked(self, page, row: int):
        """
        Обработчик кнопки ▶ на странице LogistX.
        UI сам формирует job_data, а processor не зависит от QWidget.
        """
        g = self.gui

        try:
            job_data = page.build_close_race_job(row)
            if not job_data:
                return

            def _on_done(ctx, result: dict, _job: dict):
                page.apply_close_race_result(row=row, ctx=ctx, result=result)
                race_no = getattr(ctx, "race_name", "") or _job.get("race_no", "")
                if result.get("ok"):
                    g.ui_bridge.log.emit(f"✅ {race_no}: {result.get('message')}")
                else:
                    g.ui_bridge.log.emit(f"❌ {race_no}: {result.get('message')}")

            g.processor.logistx_race_service.close_race_async(job_data, on_done=_on_done)

        except Exception as e:
            if getattr(g, "ui_bridge", None):
                g.ui_bridge.log.emit(f"❌ LogistX ▶ ошибка: {e}")
            else:
                g.log(f"❌ LogistX ▶ ошибка: {e}")
