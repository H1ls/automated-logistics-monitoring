from pathlib import Path
import sys

def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[2]


ROOT_DIR = app_root()

LOGISTX_DIR = ROOT_DIR / "LogistX"
LOGISTX_CONFIG_DIR = LOGISTX_DIR / "config"
LOGISTX_ASSETS_DIR = LOGISTX_DIR / "assets"
LOGISTX_TMP_DIR = LOGISTX_DIR / "tmp"

REPORTS_SELECTORS = LOGISTX_CONFIG_DIR / "wialon_reports_selectors.json"
ONEC_UI_MAP = LOGISTX_CONFIG_DIR / "onec_ui_map_v2.json"
ONEC_TEMPLATES_DIR = LOGISTX_ASSETS_DIR / "onec_templates"
LOGISTX_SAMPLE = LOGISTX_CONFIG_DIR / "logistx_sample.json"
ONEC_UNCLOSED_RACES_XLSX = LOGISTX_CONFIG_DIR / "1c_unclosed_races.xlsx"
SITES_DB_FILE = LOGISTX_CONFIG_DIR / "sites_db.json"
TESSERACT_LOCAL_EXE = ROOT_DIR / "Tesseract-OCR" / "tesseract.exe"
