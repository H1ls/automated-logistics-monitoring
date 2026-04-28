import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class SecretsManager:
    """Безопасное управление credentials"""

    def __init__(self, env_file: Optional[Path] = None):
        if env_file is None:
            if getattr(sys, "frozen", False):
                # если exe — берем рядом с exe
                base = Path(sys.executable).resolve().parent
            else:
                # если PyCharm
                base = Path(__file__).resolve().parents[2]

            env_file = base / ".env"

        if env_file.exists():
            load_dotenv(env_file)

    @staticmethod
    def get_wialon_credentials() -> tuple[str, str]:
        username = os.getenv('WIALON_USERNAME')
        password = os.getenv('WIALON_PASSWORD')

        if not username or not password:
            raise ValueError("WIALON_USERNAME и WIALON_PASSWORD должны быть "
                             "установлены в .env файле или переменных окружения")

        return username, password

    @staticmethod
    def get_google_credentials_path() -> str:
        path = os.getenv('GOOGLE_CREDENTIALS_PATH')
        if not path:
            raise ValueError("GOOGLE_CREDENTIALS_PATH должен быть установлен")
        return path
