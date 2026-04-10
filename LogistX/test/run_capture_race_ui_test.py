from __future__ import annotations

import time
from pathlib import Path

import pygetwindow as gw

from LogistX.onec.context import RaceContext
from LogistX.onec.errors import OneCErrorHandler
from LogistX.onec.session import OneCSession
from LogistX.onec.steps.capture_race_ui import CaptureRaceUiStep
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


def print_ctx_points(ctx):
    print("\n=== UI POINTS FROM CTX ===")
    ui_points = (ctx.state or {}).get("ui_points", {})
    for name, point in ui_points.items():
        print(f"{name}: x={point.get('x')}, y={point.get('y')}, "
              f"score={point.get('score')}, source={point.get('source')}")


def main():
    session, errors = build_session()

    if not session.activate():
        raise RuntimeError("Не удалось активировать окно RDP/1C")

    print("Открой карточку рейса в 1С перед запуском этого теста.")
    time.sleep(1.0)
    ctx = RaceContext(race_name="TEST CAPTURE UI")
    session.ui_calibrated = False
    step = CaptureRaceUiStep(session=session,
                             errors=errors,
                             log_func=log,
                             persist_min_score=0.90, )

    print("\n=== RUN CaptureRaceUiStep ===")
    step.run(ctx)

    print_ctx_points(ctx)

    shot_path = session.tmp_dir / "race_form_calibration.png"

    ui_points = []
    for name, data in ((ctx.state or {}).get("ui_points") or {}).items():
        ui_points.append(step.__class__.__dict__["_find_on_shot"])

    from LogistX.onec.steps.capture_race_ui import UiPoint

    overlay_points = []
    for name, data in ((ctx.state or {}).get("ui_points") or {}).items():
        overlay_points.append(
            UiPoint(name=name,
                    x=int(data["x"]),
                    y=int(data["y"]),
                    score=data.get("score"),
                    source=str(data.get("source", "ctx")), ))

    step._save_debug_overlay(shot_path, overlay_points)

    print("\n=== SAVED FILES ===")
    print(f"shot:   {shot_path}")
    print(f"debug:  {session.tmp_dir / 'race_form_calibration_debug.png'}")
    print(f"uimap:  {session.ui_map.path}")

    print("\n✅ CaptureRaceUiStep test finished")


if __name__ == "__main__":
    main()
