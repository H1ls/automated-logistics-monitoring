# LogistX/onec/bot.py
from __future__ import annotations

from LogistX.config.paths import ONEC_UI_MAP, ONEC_TEMPLATES_DIR, LOGISTX_TMP_DIR
from .context import RaceContext
from .errors import OneCErrorHandler
from .session import OneCSession
from .uimap import UiMap
from .scenarios.close_race import CloseRaceScenario


class OneCBot:
    def __init__(self, rdp_activator, reportsbot=None, log_func=print,
                 ui_map_path=None, templates_dir=None, tmp_dir=None, precheck_executor=None,
                 debug_mode: bool = False, ):
        self.log = log_func
        self.reportsbot = reportsbot
        self.precheck_executor = precheck_executor

        if ui_map_path is None:
            ui_map_path = str(ONEC_UI_MAP)

        if templates_dir is None:
            templates_dir = str(ONEC_TEMPLATES_DIR)

        if tmp_dir is None:
            tmp_dir = str(LOGISTX_TMP_DIR)

        self.ui_map = UiMap(ui_map_path)
        self.session = OneCSession(rdp_activator=rdp_activator,ui_map=self.ui_map,
                                   templates_dir=templates_dir,tmp_dir=tmp_dir,log_func=log_func,
                                   debug_mode=debug_mode, )
        self.errors = OneCErrorHandler(self.session, log_func=log_func)
        # self.log(f"ui_map_path={ui_map_path}")
        # self.log(f"templates_dir={templates_dir}")
        # self.log(f"tmp_dir={tmp_dir}")
    def close_race(self, ctx: RaceContext):
        self.log("🚀 Старт close_race")
        if not self.session.activate():
            return {"ok": False,
                    "stage": "activate",
                    "message": "Не удалось активировать окно RDP/1C", }

        scenario = CloseRaceScenario(self.session, self.errors, reportsbot=self.reportsbot, log_func=self.log,
                                     precheck_executor=self.precheck_executor, )
        result = scenario.run(ctx)

        return {"ok": result.ok,
                "stage": result.stage,
                "message": result.message,
                "recovered": result.recovered, }
