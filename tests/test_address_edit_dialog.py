import os
from unittest import TestCase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from Navigation_Bot.gui.dialogs.address_edit_dialog import AddressEditDialog


class AddressEditDialogTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_unload_checkboxes_follow_added_and_removed_points(self):
        blocks = [
            {"Выгрузка 1": "A"},
            {"Выгрузка 2": "B"},
            {"Выгрузка 3": "C"},
        ]
        dialog = AddressEditDialog({"Выгрузка": blocks, "processed_unloads": [False, False, False]}, "Выгрузка")

        dialog.status_editor._cbs[2].setChecked(True)
        dialog.remove_entry(dialog.entries[1])
        dialog.add_entry("D")
        dialog.status_editor._cbs[1].setChecked(True)
        dialog.status_editor._cbs[2].setChecked(True)

        result, _ = dialog.get_result()
        self.assertEqual(len(dialog.entries), 3)
        self.assertEqual(len(dialog.status_editor._cbs), 3)
        self.assertEqual(dialog.get_processed(), [False, True, True])
        self.assertEqual([result[index][f"Выгрузка {index + 1}"] for index in range(3)],
                         ["A", "C", "D"])

    def test_load_editor_has_no_unload_status_checkboxes(self):
        dialog = AddressEditDialog({"Погрузка": [{"Погрузка 1": "A"}]},
                                   "Погрузка")

        self.assertIsNone(dialog.status_editor)

    def test_unload_checkboxes_appear_from_two_points(self):
        dialog = AddressEditDialog({"Выгрузка": [{"Выгрузка 1": "A"}, ]},
                                   "Выгрузка")

        self.assertIsNone(dialog.status_editor)

        dialog.add_entry("B")
        self.assertIsNotNone(dialog.status_editor)
        self.assertEqual(len(dialog.status_editor._cbs), 2)

        dialog.remove_entry(dialog.entries[1])
        self.assertIsNone(dialog.status_editor)
