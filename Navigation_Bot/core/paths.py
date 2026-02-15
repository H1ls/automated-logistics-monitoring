from pathlib import Path
import os
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = ROOT_DIR / "config"

INPUT_FILEPATH = CONFIG_DIR / "selected_data.json"
ID_FILEPATH = CONFIG_DIR / "Id_car.json"
CONFIG_JSON = CONFIG_DIR / "config.json"
COOKIES_FILE = CONFIG_DIR / "cookies.pkl"
CREDENTIALS_WIALON = CONFIG_DIR / "Credentials_wialon.json"

UI_SETTINGS_FILE = CONFIG_DIR / "ui_settings.json"

DATASET_DIR = CONFIG_DIR / "datasets"
DATASET_FILE = DATASET_DIR / "addresses.jsonl"

# === Pin codes ===
PIN_XLSX_FILEPATH = os.path.join(CONFIG_DIR,"Обновленный РЕЕСТР ПИН ТОПЛИВНЫЕ КАРТЫ.xlsx")
PIN_JSON_FILEPATH = os.path.join(CONFIG_DIR,"pincodes_cache.json")


VERSION = "0.45"
