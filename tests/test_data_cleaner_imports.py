import unittest


class DataCleanerImportTests(unittest.TestCase):
    def test_compact_vehicle_key_is_imported_from_its_owner_module(self):
        from Navigation_Bot.bots.data_cleaner import compact_vehicle_key

        self.assertEqual(compact_vehicle_key(" а 123 вс 77 "), "А123ВС77")


if __name__ == "__main__":
    unittest.main()
