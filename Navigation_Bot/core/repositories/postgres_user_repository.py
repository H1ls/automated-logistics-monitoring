from __future__ import annotations

import hashlib
import secrets
from typing import Any

VALID_ROLES = {"admin", "dispatcher", "viewer"}
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
MIN_PASSWORD_LENGTH = 8


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    password = password or ""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS)
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not password or not stored_hash:
        return False
    try:
        scheme, iterations_raw, salt, expected = stored_hash.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iterations_raw)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
        return secrets.compare_digest(digest, expected)
    except (TypeError, ValueError):
        return False


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

    def has_active_password_users(self) -> bool:
        row = self.connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM app_users
                WHERE is_active = true
                  AND password_hash <> ''
            ) AS has_users
            """).fetchone()

        return bool(row and row["has_users"])

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

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        username = (username or "").strip()
        if not username or not password:
            return None

        row = self.connection.execute(
            """
            SELECT id, username, display_name, role, is_active, password_hash
            FROM app_users
            WHERE username = %(username)s
              AND is_active = true
            """,
            {"username": username},
        ).fetchone()

        if not row or not verify_password(password, row["password_hash"]):
            return None

        return {"id": row["id"],
                "username": row["username"],
                "display_name": row["display_name"],
                "role": row["role"],
                "is_active": row["is_active"]}

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
                COUNT(k.id) FILTER (
                    WHERE k.revoked_at IS NULL
                      AND (k.expires_at IS NULL OR k.expires_at > CURRENT_TIMESTAMP)
                ) AS active_api_key_count
            FROM app_users u
            LEFT JOIN api_keys k ON k.user_id = u.id
            GROUP BY u.id
            ORDER BY u.id
            """).fetchall()

        return [dict(row) for row in rows]

    def create_user(self,
                    *,
                    username: str,
                    display_name: str = "",
                    role: str = "viewer",
                    is_active: bool = True,
                    password: str = "", ) -> \
    dict[str, Any]:

        username = username.strip()
        role = role.strip().lower()
        if not username:
            raise ValueError("username_required")
        if role not in VALID_ROLES:
            raise ValueError("invalid_role")

        existing = self.connection.execute(
            "SELECT password_hash FROM app_users WHERE username = %(username)s",
            {"username": username},
        ).fetchone()
        if not existing and not password:
            raise ValueError("password_required")
        if password and len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError("password_too_short")

        password_hash = hash_password(password) if password else None
        row = self.connection.execute(
            """
            INSERT INTO app_users (username, display_name, password_hash, role, is_active)
            VALUES (%(username)s, %(display_name)s, COALESCE(%(password_hash)s, ''), %(role)s, %(is_active)s)
            ON CONFLICT (username) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                password_hash = CASE
                    WHEN EXCLUDED.password_hash <> '' THEN EXCLUDED.password_hash
                    ELSE app_users.password_hash
                END,
                role = EXCLUDED.role,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, username, display_name, role, is_active, created_at, updated_at
            """,
            {
                "username": username,
                "display_name": display_name.strip(),
                "password_hash": password_hash,
                "role": role,
                "is_active": bool(is_active),
            },
        ).fetchone()
        return dict(row)

    def update_user(self,
                    user_id: int,
                    *,
                    username: str,
                    display_name: str = "",
                    role: str = "viewer",
                    is_active: bool = True,
                    password: str = "") -> dict[str, Any]:
        username = username.strip()
        role = role.strip().lower()
        if not username:
            raise ValueError("username_required")
        if role not in VALID_ROLES:
            raise ValueError("invalid_role")
        if password and len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError("password_too_short")

        conflict = self.connection.execute(
            """
            SELECT 1
            FROM app_users
            WHERE username = %(username)s
              AND id <> %(user_id)s
            """,
            {"username": username, "user_id": int(user_id)},
        ).fetchone()
        if conflict:
            raise ValueError("username_already_exists")

        password_hash = hash_password(password) if password else None
        row = self.connection.execute(
            """
            UPDATE app_users
            SET username = %(username)s,
                display_name = %(display_name)s,
                password_hash = COALESCE(%(password_hash)s, password_hash),
                role = %(role)s,
                is_active = %(is_active)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(user_id)s
            RETURNING id, username, display_name, role, is_active, created_at, updated_at
            """,
            {"user_id": int(user_id),
             "username": username,
             "display_name": display_name.strip(),
             "password_hash": password_hash,
             "role": role,
             "is_active": bool(is_active)},
        ).fetchone()
        if not row:
            raise ValueError("user_not_found")
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

    def revoke_user_api_keys_by_name(self, user_id: int, name: str) -> int:
        cursor = self.connection.execute(
            """
            UPDATE api_keys
            SET revoked_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %(user_id)s
              AND name = %(name)s
              AND revoked_at IS NULL
            """,
            {"user_id": int(user_id), "name": name.strip()},
        )
        return int(cursor.rowcount or 0)

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
