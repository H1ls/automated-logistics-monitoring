from unittest import TestCase

from Navigation_Bot.core.repositories.postgres_user_repository import (PostgresUserRepository,
                                                                         hash_password,
                                                                         verify_password)


class PasswordHashTests(TestCase):
    def test_password_is_salted_and_verifiable(self):
        password = "correct-horse"

        first = hash_password(password)
        second = hash_password(password)

        self.assertNotEqual(first, second)
        self.assertNotIn(password, first)
        self.assertTrue(verify_password(password, first))
        self.assertFalse(verify_password("wrong-password", first))

    def test_invalid_hash_is_rejected(self):
        self.assertFalse(verify_password("password", "invalid"))


class _NewUserConnection:
    def execute(self, _query, _params=None):
        return self

    def fetchone(self):
        return None


class UserPasswordPolicyTests(TestCase):
    def setUp(self):
        self.repository = PostgresUserRepository(_NewUserConnection())

    def test_new_user_requires_password(self):
        with self.assertRaisesRegex(ValueError, "password_required"):
            self.repository.create_user(username="new-user")

    def test_new_user_rejects_short_password(self):
        with self.assertRaisesRegex(ValueError, "password_too_short"):
            self.repository.create_user(username="new-user", password="short")


class _RevokeConnection:
    rowcount = 3

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        return self


class GuiSessionTests(TestCase):
    def test_previous_gui_sessions_can_be_revoked(self):
        connection = _RevokeConnection()

        count = PostgresUserRepository(connection).revoke_user_api_keys_by_name(7, "GUI session")

        self.assertEqual(count, 3)
        self.assertEqual(connection.params, {"user_id": 7, "name": "GUI session"})
