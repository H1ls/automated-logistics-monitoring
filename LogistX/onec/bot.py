# LogistX/onec/bot.py
from __future__ import annotations

from pathlib import Path

from .context import RaceContext
from .errors import OneCErrorHandler
from .session import OneCSession
from .uimap import UiMap
from .scenarios.close_race import CloseRaceScenario


class OneCBot:
    def __init__(self, rdp_activator, reportsbot=None, log_func=print,
                 ui_map_path=None, templates_dir=None, tmp_dir=None, precheck_executor=None, ):
        self.log = log_func
        self.reportsbot = reportsbot
        self.precheck_executor = precheck_executor

        logistx_dir = Path(__file__).resolve().parents[1]

        if ui_map_path is None:
            ui_map_path = logistx_dir / "config" / "onec_ui_map_v2.json"
        if templates_dir is None:
            templates_dir = logistx_dir / "assets" / "onec_templates"
        if tmp_dir is None:
            tmp_dir = logistx_dir / "tmp"

        print("A1 before UiMap")
        self.ui_map = UiMap(ui_map_path)
        print("A2 after UiMap")
        print("A3 before OneCSession")
        self.session = OneCSession(rdp_activator=rdp_activator,ui_map=self.ui_map,
                                   templates_dir=templates_dir,tmp_dir=tmp_dir,log_func=log_func, )
        print("A4 after OneCSession")
        print("A3 before OneCSession")
        self.errors = OneCErrorHandler(self.session, log_func=log_func)
        print("A6 after OneCErrorHandler")
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
