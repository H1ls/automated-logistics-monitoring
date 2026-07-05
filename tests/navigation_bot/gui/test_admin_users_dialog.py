import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
from Navigation_Bot.gui.dialogs.admin_users_dialog import AdminUsersDialog

class _ApiClient:

    def __init__(self):
        self.put_calls = []

    def get(self, _path):
        return {'items': [{'id': 7, 'username': 'old-name', 'display_name': 'Admin', 'role': 'admin', 'is_active': True, 'active_api_key_count': 1, 'updated_at': ''}]}

    def put(self, path, *, json=None):
        self.put_calls.append((path, json))
        return {'ok': True, 'user': {'id': 7, **json}}

    def post(self, _path, *, json=None):
        raise AssertionError(f'existing user must not use POST: {json}')

class TestAdminUsersDialog:

    def setup_class(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_existing_user_username_is_updated_by_id(self):
        client = _ApiClient()
        dialog = AdminUsersDialog(client)
        dialog.table.selectRow(0)
        self.app.processEvents()
        assert not dialog.username_edit.isReadOnly()
        dialog.username_edit.setText('new-name')
        dialog.save_user()
        assert client.put_calls[0][0] == '/api/v1/users/7'
        assert client.put_calls[0][1]['username'] == 'new-name'
