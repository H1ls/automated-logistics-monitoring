from pathlib import Path
import sys


def app_root() -> Path:
    # если запущено как exe
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # если из PyCharm
    return Path(__file__).resolve().parent.parent.parent


ROOT_DIR = app_root()
CONFIG_DIR = ROOT_DIR / "config"

CONFIG_JSON = CONFIG_DIR / "config.json"

COOKIES_FILE = CONFIG_DIR / "cookies.pkl"
CREDENTIALS_WIALON = CONFIG_DIR / "Credentials_wialon.json"

UI_SETTINGS_FILE = CONFIG_DIR / "ui_settings.json"

DATASET_DIR = CONFIG_DIR / "datasets"
DATASET_FILE = DATASET_DIR / "addresses.jsonl"
BATCH_PROGRESS_FILE = CONFIG_DIR / "batch_progress.json"
NOTE_MEDIA_DIR = CONFIG_DIR / "media" / "notes"
CLIPBOARD_MEDIA_DIR = NOTE_MEDIA_DIR

# === Pin codes ===
PIN_XLSX_FILEPATH = CONFIG_DIR / "Обновленный РЕЕСТР ПИН ТОПЛИВНЫЕ КАРТЫ.xlsx"
PIN_JSON_FILEPATH = CONFIG_DIR / "pincodes_cache.json"
PIN_CARD_IMAGES_DIR = CONFIG_DIR / "pin_card_images"


VERSION = "05072026"
