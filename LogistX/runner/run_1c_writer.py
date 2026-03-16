# LogistX/runner/run_onec_bot_test.py
from __future__ import annotations

import json
import re
from pathlib import Path

from LogistX.onec.bot import OneCBot
from LogistX.onec.context import RaceContext
from Navigation_Bot.bots.webDriverManager import WebDriverManager
from Navigation_Bot.bots.wialonReportsBot import WialonReportsBot


def activate_rdp1():
    print("176.57.78.6:2025 — Подключение к удаленному рабочему столу")

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = BASE_DIR / "config"


def log(msg: str):
    print(msg)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def resolve_geofence(address: str, sites_db: list[dict]) -> str:
    addr_n = norm(address)
    if not addr_n:
        return ""

    best = ""
    best_score = 0

    for obj in sites_db:
        aliases = obj.get("aliases") or []
        if not isinstance(aliases, list):
            continue

        score = 0
        for a in aliases:
            a_n = norm(str(a))
            if a_n and a_n in addr_n:
                score += 1

        if score > best_score:
            best_score = score
            best = str(obj.get("geofence", "") or "")

    return best if best_score > 0 else ""


def build_reportsbot():
    dm = WebDriverManager(log_func=log)

    # если у тебя уже есть готовый прямоугольник браузера — подставь свой
    browser_rect = (0, 0, 1400, 1000)

    driver = getattr(dm, "driver", None)
    if not driver or not dm.is_alive():
        dm.start_browser(browser_rect)
        dm.login_wialon()
        dm.open_yandex_maps()

    return dm, WialonReportsBot(dm.driver, log_func=log)


def make_rdp_activator():
    # сюда подставь свой рабочий активатор RDP окна
    # например from LogistX.utils.rdp import activate_rdp_window
    # return activate_rdp_window

    def _activate():
        # временная заглушка: если окно уже активно
        return True

    return _activate


def main(row_index: int = 0):
    logistx_sample = load_json(CONFIG_DIR / "logistx_sample.json")
    sites_db = load_json(CONFIG_DIR / "sites_db.json")

    row = logistx_sample[row_index]

    race_name = str(row.get("Рейс", "") or "").strip()
    unit = str(row.get("ТС", "") or "").strip()
    from_address = str(row.get("Рейс.Пункт отправления", "") or "").strip()
    to_address = str(row.get("Рейс.Пункт назначения", "") or "").strip()
    # departure_dt = str(row.get("Плановая дата освобождения разгрузка", "") or "").strip()
    departure_dt= race_name.split(" от ", 1)[1][:-3]
    if not race_name:
        raise ValueError("В logistx_sample.json пустое поле 'Рейс'")
    if not unit:
        raise ValueError("В logistx_sample.json пустое поле 'ТС'")

    load_zone = resolve_geofence(from_address, sites_db)
    unload_zone = resolve_geofence(to_address, sites_db)

    if not load_zone:
        raise RuntimeError(f"Не удалось определить geofence погрузки по адресу: {from_address}")
    if not unload_zone:
        raise RuntimeError(f"Не удалось определить geofence выгрузки по адресу: {to_address}")

    log(f"🚚 Рейс: {race_name}")
    log(f"🚛 ТС: {unit}")
    log(f"📍 load_zone: {load_zone}")
    log(f"📍 unload_zone: {unload_zone}")
    log(f"🕒 departure_dt: {departure_dt}")

    driver_manager, reportsbot = build_reportsbot()
    rdp_activator = make_rdp_activator()

    ctx = RaceContext(
        race_name=race_name,
        race_search_text=race_name,
        departure_dt=departure_dt[:16],
        meta={
            "unit": unit,
            "load_zone": load_zone,
            "unload_zone": unload_zone,
            "from_address": from_address,
            "to_address": to_address,
        }
    )

    bot = OneCBot(
        rdp_activator=rdp_activator,
        reportsbot=reportsbot,
        log_func=log,
    )

    result = bot.close_race(ctx)

    print("\n=== RESULT ===")
    print(result)

    print("\n=== CTX ===")
    print({
        "departure_dt": ctx.departure_dt,
        "load_in": ctx.load_in,
        "load_out": ctx.load_out,
        "unload_in": ctx.unload_in,
        "unload_out": ctx.unload_out,
        "state": ctx.state,
    })


if __name__ == "__main__":
    main(1)
