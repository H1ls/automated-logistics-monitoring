import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv, set_key


class SecretsManager:
    """Менеджер для .env."""

    def __init__(self, env_file: Optional[Path] = None):
        self.env_file = env_file or self.default_env_file()

        if self.env_file.exists():
            load_dotenv(self.env_file, override=False)

    @staticmethod
    def default_env_file() -> Path:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            base = Path(__file__).resolve().parents[2]

        return base / ".env"

    @staticmethod
    def get_wialon_credentials_optional() -> tuple[str, str]:
        return os.getenv("WIALON_USERNAME", ""), os.getenv("WIALON_PASSWORD", "")

    @staticmethod
    def get_wialon_credentials() -> tuple[str, str]:
        username = os.getenv("WIALON_USERNAME")
        password = os.getenv("WIALON_PASSWORD")

        if not username or not password:
            raise ValueError("WIALON_USERNAME и WIALON_PASSWORD должны быть "
                             "установлены в .env файле или переменных окружения" )

        return username, password

    def set_wialon_credentials(self, username: str, password: str) -> None:
        self.env_file.parent.mkdir(parents=True, exist_ok=True)
        self.env_file.touch(exist_ok=True)

        set_key(str(self.env_file), "WIALON_USERNAME", username, quote_mode="always")
        set_key(str(self.env_file), "WIALON_PASSWORD", password, quote_mode="always")

        os.environ["WIALON_USERNAME"] = username
        os.environ["WIALON_PASSWORD"] = password
        load_dotenv(self.env_file, override=True)

    @staticmethod
    def get_google_credentials_path() -> str:
        path = os.getenv("GOOGLE_CREDENTIALS_PATH")
        if not path:
            raise ValueError("GOOGLE_CREDENTIALS_PATH должен быть установлен")
        return path
