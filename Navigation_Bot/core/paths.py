from pathlib import Path

from google.auth.environment_vars import CREDENTIALS

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"

INPUT_FILEPATH = CONFIG_DIR / "selected_data.json"
ID_FILEPATH = CONFIG_DIR / "Id_car.json"
CONFIG_JSON = CONFIG_DIR / "config.json"
COOKIES_FILE = CONFIG_DIR / "cookies.pkl"
CREDENTIALS_WIALON = CONFIG_DIR / "Credentials_wialon.json"
