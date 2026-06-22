from pathlib import Path
from unittest import TestCase

from Navigation_Bot.core.infrastructure.persistence.sites_db_registry import SitesDbRegistry
from Navigation_Bot.gui.dialogs.address_edit_models import AddressBlocksCodec


class AddressBlocksCodecTests(TestCase):
    def test_parse_sorts_points_and_keeps_comments_out_of_points(self):
        codec = AddressBlocksCodec("Выгрузка")

        points, comment = codec.parse([
            {"Выгрузка 3": "C", "Дата 3": "03.06.2026", "Время 3": "12:00"},
            {"Выгрузка другое": "Старый комментарий"},
            {"Выгрузка 1": "A", "Дата 1": "", "Время 1": ""},
            {"Комментарий": "Новый комментарий"}
        ])

        self.assertEqual([point.address for point in points], ["A", "C"])
        self.assertEqual(comment, "Старый комментарий\nНовый комментарий")

    def test_serialize_compacts_sequence_numbers(self):
        codec = AddressBlocksCodec("Выгрузка")
        points, _ = codec.parse([
            {"Выгрузка 1": "A"},
            {"Выгрузка 3": "C"},
        ])

        result = codec.serialize(points, "Комментарий")

        self.assertEqual(result[0]["Выгрузка 1"], "A")
        self.assertEqual(result[1]["Выгрузка 2"], "C")
        self.assertEqual(result[2], {"Комментарий": "Комментарий"})


class SitesDbRegistryTests(TestCase):
    def test_match_selects_alias_with_highest_score(self):
        registry = SitesDbRegistry(path=Path("missing-sites-db.json"))
        registry.items = [
            {"site_id": "1", "geofence": "First", "aliases": ["Alpha"]},
            {"site_id": "2", "geofence": "Second", "aliases": ["Alpha", "Beta"]},
        ]

        match = registry.match("Alpha / Beta")

        self.assertIsNotNone(match)
        self.assertEqual(match.site_id, "2")
        self.assertEqual(match.score, 2)
        self.assertEqual(registry.resolve_geofence("Alpha / Beta"), "Second")

    def test_collect_point_addresses_uses_real_sequence_keys(self):
        addresses = SitesDbRegistry.collect_point_addresses([
            {"Выгрузка 3": "C"},
            {"Выгрузка другое": "Не точка"},
            {"Комментарий": "Не точка"},
            {"Выгрузка 1": "A"},
        ], "Выгрузка")

        self.assertEqual(addresses, ["A", "C"])
