from __future__ import annotations

import time
from pathlib import Path

import pygetwindow as gw

from LogistX.onec.context import RaceContext
from LogistX.onec.errors import OneCErrorHandler
from LogistX.onec.session import OneCSession
from LogistX.onec.steps.driver_rating import DriverRatingStep
from LogistX.onec.uimap import UiMap

RDP_TITLE_HINT = "176.57.78.6:2025 — Подключение к удаленному рабочему столу"
RDP_TITLE_FALLBACKS = ["Подключение к удаленному рабочему столу",
                       "Remote Desktop Connection",]


def log(msg: str):
    print(msg)


def find_rdp_window():
    wins = gw.getWindowsWithTitle(RDP_TITLE_HINT)
    if wins:
        return wins[0]

    for hint in RDP_TITLE_FALLBACKS:
        wins = gw.getWindowsWithTitle(hint)
        if wins:
            return wins[0]

    try:
        for title in gw.getAllTitles():
            if not title:
                continue
            if RDP_TITLE_HINT in title:
                wins = gw.getWindowsWithTitle(title)
                if wins:
                    return wins[0]
    except Exception:
        pass

    return None


def activate_rdp():
    w = find_rdp_window()
    if not w:
        raise RuntimeError("Окно RDP не найдено")

    if getattr(w, "isMinimized", False):
        w.restore()
        time.sleep(0.3)

    try:
        w.activate()
        time.sleep(0.4)
    except Exception:
        pass

    try:
        w.maximize()
        time.sleep(0.3)
    except Exception:
        pass


def build_session() -> tuple[OneCSession, OneCErrorHandler]:
    logistx_dir = Path(__file__).resolve().parents[1]

    ui_map_path = logistx_dir / "config" / "onec_ui_map_v2.json"
    templates_dir = logistx_dir / "assets" / "onec_templates"
    tmp_dir = logistx_dir / "tmp"

    ui_map = UiMap(ui_map_path)

    session = OneCSession(rdp_activator=activate_rdp,
                          ui_map=ui_map,
                          templates_dir=templates_dir,
                          tmp_dir=tmp_dir,
                          log_func=log, )
    errors = OneCErrorHandler(session, log_func=log)
    return session, errors


def main():
    session, errors = build_session()
    log("🚀 Старт run_driver_rating_real")

    if not session.activate():
        raise RuntimeError("Не удалось активировать окно RDP/1C")

    # ctx пустой -> items=[] -> DriverRatingStep._add_nothing()
    ctx = RaceContext(race_name="TEST DRIVER RATING EMPTY")

    step = DriverRatingStep(session, errors, log_func=log)

    log("↩️ Возврат на Основную вкладку")
    session.click_anchor("start_page_tab")
    session.sleep(0.5)

    err = errors.handle_generic()
    if err:
        raise RuntimeError(f"Ошибка после перехода на основную вкладку: {err.kind}")

    # Дальше сам step.run() откроет вкладку оценки и выполнит _add_nothing()
    step.run(ctx)

    log("✅ DriverRatingStep real test finished")


if __name__ == "__main__":
    main()
