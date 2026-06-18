from __future__ import annotations

import os
from dataclasses import dataclass

from Navigation_Bot.core.secrets_manager import SecretsManager

DEFAULT_POSTGRES_DSN = "postgresql://pet_user:pet_password@localhost:5432/pet_project"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    backend: str
    postgres_dsn: str
    api_base_url: str
    api_key: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        SecretsManager()
        backend = os.getenv("DB_BACKEND", "postgres").strip().lower() or "postgres"
        postgres_dsn = os.getenv("POSTGRES_DSN", DEFAULT_POSTGRES_DSN).strip() or DEFAULT_POSTGRES_DSN
        api_base_url = os.getenv("NAV_API_BASE_URL", DEFAULT_API_BASE_URL).strip() or DEFAULT_API_BASE_URL
        api_key = os.getenv("NAV_API_KEY", "").strip()
        return cls(backend=backend,
                   postgres_dsn=postgres_dsn,
                   api_base_url=api_base_url,
                   api_key=api_key)

    @property
    def is_postgres(self) -> bool:
        return self.backend in {"postgres", "postgresql"}

    @property
    def is_api(self) -> bool:
        return self.backend == "api"
