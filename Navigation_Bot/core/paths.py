from pathlib import Path
import sys
import os


def app_root() -> Path:
    # если запущено как exe
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # если из PyCharm
    return Path(__file__).resolve().parent.parent.parent


ROOT_DIR = app_root()
CONFIG_DIR = ROOT_DIR / "config"

ID_FILEPATH = CONFIG_DIR / "Id_car.json"
CONFIG_JSON = CONFIG_DIR / "config.json"
SQLITE_DB_FILEPATH = CONFIG_DIR / "navigation_bot.db"

COOKIES_FILE = CONFIG_DIR / "cookies.pkl"
CREDENTIALS_WIALON = CONFIG_DIR / "Credentials_wialon.json"

UI_SETTINGS_FILE = CONFIG_DIR / "ui_settings.json"

DATASET_DIR = CONFIG_DIR / "datasets"
DATASET_FILE = DATASET_DIR / "addresses.jsonl"

# === Pin codes ===
PIN_XLSX_FILEPATH = os.path.join(CONFIG_DIR,"Обновленный РЕЕСТР ПИН ТОПЛИВНЫЕ КАРТЫ.xlsx")
PIN_JSON_FILEPATH = os.path.join(CONFIG_DIR,"pincodes_cache.json")


VERSION = "27042026"
