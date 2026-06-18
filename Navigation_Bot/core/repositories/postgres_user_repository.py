from __future__ import annotations

import hashlib
import secrets
from typing import Any

VALID_ROLES = {"admin", "dispatcher", "viewer"}


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


class PostgresUserRepository:
    def __init__(self, connection):
        self.connection = connection

    def has_active_api_keys(self) -> bool:
        row = self.connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM api_keys
                WHERE revoked_at IS NULL
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            ) AS has_keys
            """).fetchone()

        return bool(row and row["has_keys"])

    def has_active_admin_api_keys(self) -> bool:
        row = self.connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM api_keys k
                JOIN app_users u ON u.id = k.user_id
                WHERE k.revoked_at IS NULL
                  AND (k.expires_at IS NULL OR k.expires_at > CURRENT_TIMESTAMP)
                  AND u.is_active = true
                  AND u.role = 'admin'
            ) AS has_keys
            """).fetchone()

        return bool(row and row["has_keys"])

    def get_user_by_api_key(self, api_key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT
                u.id,
                u.username,
                u.display_name,
                u.role,
                u.is_active,
                k.id AS api_key_id
            FROM api_keys k
            JOIN app_users u ON u.id = k.user_id
            WHERE k.key_hash = %(key_hash)s
              AND k.revoked_at IS NULL
              AND (k.expires_at IS NULL OR k.expires_at > CURRENT_TIMESTAMP)
              AND u.is_active = true
            """, {"key_hash": hash_api_key(api_key)}, ).fetchone()

        if not row:
            return None

        self.connection.execute(
            """
            UPDATE api_keys
            SET last_used_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(api_key_id)s
            """, {"api_key_id": row["api_key_id"]})

        return {"id": row["id"],
                "username": row["username"],
                "display_name": row["display_name"],
                "role": row["role"],
                "is_active": row["is_active"],
                "api_key_id": row["api_key_id"]}

    def list_users(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT
                u.id,
                u.username,
                u.display_name,
                u.role,
                u.is_active,
                u.created_at,
                u.updated_at,
                COUNT(k.id) FILTER (WHERE k.revoked_at IS NULL) AS active_api_key_count
            FROM app_users u
            LEFT JOIN api_keys k ON k.user_id = u.id
            GROUP BY u.id
            ORDER BY u.id
            """).fetchall()

        return [dict(row) for row in rows]

    def create_user(self, *, username: str, display_name: str = "", role: str = "viewer", is_active: bool = True, ) -> \
    dict[str, Any]:

        username = username.strip()
        role = role.strip().lower()
        if not username:
            raise ValueError("username_required")
        if role not in VALID_ROLES:
            raise ValueError("invalid_role")

        row = self.connection.execute(
            """
            INSERT INTO app_users (username, display_name, role, is_active)
            VALUES (%(username)s, %(display_name)s, %(role)s, %(is_active)s)
            ON CONFLICT (username) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                role = EXCLUDED.role,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, username, display_name, role, is_active, created_at, updated_at
            """,
            {
                "username": username,
                "display_name": display_name.strip(),
                "role": role,
                "is_active": bool(is_active),
            },
        ).fetchone()
        return dict(row)

    def create_api_key(self,*,user_id: int,name: str = "",expires_at: str | None = None,) -> dict[str, Any]:
        user_exists = self.connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM app_users
                WHERE id = %(user_id)s
            ) AS user_exists
            """,
            {"user_id": int(user_id)},
        ).fetchone()
        if not user_exists or not user_exists["user_exists"]:
            raise ValueError("user_not_found")

        api_key = f"nav_{secrets.token_urlsafe(32)}"
        row = self.connection.execute(
            """
            INSERT INTO api_keys (user_id, key_hash, name, expires_at)
            VALUES (%(user_id)s, %(key_hash)s, %(name)s, %(expires_at)s::timestamptz)
            RETURNING id, user_id, name, expires_at, created_at
            """,
            {
                "user_id": int(user_id),
                "key_hash": hash_api_key(api_key),
                "name": name.strip(),
                "expires_at": expires_at,
            }
        ).fetchone()
        result = dict(row)
        result["api_key"] = api_key
        return result

    def revoke_api_key(self, key_id: int) -> bool:
        row = self.connection.execute(
            """
            UPDATE api_keys
            SET revoked_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(key_id)s
              AND revoked_at IS NULL
            RETURNING id
            """,
            {"key_id": int(key_id)},
        ).fetchone()
        return row is not None
