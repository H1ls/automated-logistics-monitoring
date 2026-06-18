from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Annotated, Any, Callable

from fastapi import Depends, Header, HTTPException, Request, status

from Navigation_Bot.core.repositories.postgres_user_repository import PostgresUserRepository


def postgres_connection(request: Request) -> Iterator:
    pool = getattr(request.app.state, "postgres_pool", None)
    if pool is None:
        raise RuntimeError("PostgreSQL pool is not initialized")
    with pool.connection() as connection:
        yield connection


Connection = Annotated[Any, Depends(postgres_connection)]


def current_user(connection: Connection,
                 x_api_key: Annotated[str | None,
                 Header(alias="X-API-Key")] = None, ) -> dict[str, Any]:
    repository = PostgresUserRepository(connection)
    env_api_key = os.getenv("NAV_API_KEY", "").strip()

    if x_api_key:
        user = repository.get_user_by_api_key(x_api_key)
        if user:
            return user

        if env_api_key and x_api_key == env_api_key:
            return {"id": None,
                    "username": "env_admin",
                    "display_name": "Environment Admin",
                    "role": "admin",
                    "is_active": True,
                    "api_key_id": None,
                    }
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_api_key")

    if env_api_key or repository.has_active_admin_api_keys():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="api_key_required")

    return {"id": None,
            "username": "dev_admin",
            "display_name": "Development Admin",
            "role": "admin",
            "is_active": True,
            "api_key_id": None, }


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]


def require_roles(*roles: str) -> Callable[[CurrentUser], dict[str, Any]]:
    allowed = {role.strip().lower() for role in roles}

    def dependency(user: CurrentUser) -> dict[str, Any]:
        if user.get("role") not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_role")
        return user

    return dependency
