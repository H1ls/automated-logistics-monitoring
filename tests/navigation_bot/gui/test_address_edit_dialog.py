import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
from Navigation_Bot.gui.dialogs.address_edit_dialog import AddressEditDialog

class TestAddressEditDialog:

    def setup_class(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_unload_checkboxes_follow_added_and_removed_points(self):
        blocks = [{'Выгрузка 1': 'A'}, {'Выгрузка 2': 'B'}, {'Выгрузка 3': 'C'}]
        dialog = AddressEditDialog({'Выгрузка': blocks, 'processed_unloads': [False, False, False]}, 'Выгрузка')
        dialog.status_editor._cbs[2].setChecked(True)
        dialog.remove_entry(dialog.entries[1])
        dialog.add_entry('D')
        dialog.status_editor._cbs[1].setChecked(True)
        dialog.status_editor._cbs[2].setChecked(True)
        result, _ = dialog.get_result()
        assert len(dialog.entries) == 3
        assert len(dialog.status_editor._cbs) == 3
        assert dialog.get_processed() == [False, True, True]
        assert [result[index][f'Выгрузка {index + 1}'] for index in range(3)] == ['A', 'C', 'D']

    def test_unload_reorder_updates_result_and_processed_flags(self):
        blocks = [{'Выгрузка 1': 'A'}, {'Выгрузка 2': 'B'}]
        dialog = AddressEditDialog({'Выгрузка': blocks, 'processed_unloads': [False, True]}, 'Выгрузка')
        dialog._move_entry(dialog.entries[1], 0)
        result, _ = dialog.get_result()
        assert [result[index][f'Выгрузка {index + 1}'] for index in range(2)] == ['B', 'A']
        assert dialog.get_processed() == [True, False]

    def test_load_editor_has_no_unload_status_checkboxes(self):
        dialog = AddressEditDialog({'Погрузка': [{'Погрузка 1': 'A'}]}, 'Погрузка')
        assert dialog.status_editor is None

    def test_unload_checkboxes_appear_from_two_points(self):
        dialog = AddressEditDialog({'Выгрузка': [{'Выгрузка 1': 'A'}]}, 'Выгрузка')
        assert dialog.status_editor is None
        dialog.add_entry('B')
        assert dialog.status_editor is not None
        assert len(dialog.status_editor._cbs) == 2
        dialog.remove_entry(dialog.entries[1])
        assert dialog.status_editor is None
