from pathlib import Path
from Navigation_Bot.core.infrastructure.persistence.sites_db_registry import SitesDbRegistry
from Navigation_Bot.gui.dialogs.components.address_edit_models import AddressBlocksCodec

class TestAddressBlocksCodec:

    def test_parse_sorts_points_and_keeps_comments_out_of_points(self):
        codec = AddressBlocksCodec('Выгрузка')
        points, comment = codec.parse([{'Выгрузка 3': 'C', 'Дата 3': '03.06.2026', 'Время 3': '12:00'}, {'Выгрузка другое': 'Старый комментарий'}, {'Выгрузка 1': 'A', 'Дата 1': '', 'Время 1': ''}, {'Комментарий': 'Новый комментарий'}])
        assert [point.address for point in points] == ['A', 'C']
        assert comment == 'Старый комментарий\nНовый комментарий'

    def test_serialize_compacts_sequence_numbers(self):
        codec = AddressBlocksCodec('Выгрузка')
        points, _ = codec.parse([{'Выгрузка 1': 'A'}, {'Выгрузка 3': 'C'}])
        result = codec.serialize(points, 'Комментарий')
        assert result[0]['Выгрузка 1'] == 'A'
        assert result[1]['Выгрузка 2'] == 'C'
        assert result[2] == {'Комментарий': 'Комментарий'}

class TestSitesDbRegistry:

    def test_match_selects_alias_with_highest_score(self):
        registry = SitesDbRegistry(path=Path('missing-sites-db.json'))
        registry.items = [{'site_id': '1', 'geofence': 'First', 'aliases': ['Alpha']}, {'site_id': '2', 'geofence': 'Second', 'aliases': ['Alpha', 'Beta']}]
        match = registry.match('Alpha / Beta')
        assert match is not None
        assert match.site_id == '2'
        assert match.score == 2
        assert registry.resolve_geofence('Alpha / Beta') == 'Second'

    def test_collect_point_addresses_uses_real_sequence_keys(self):
        addresses = SitesDbRegistry.collect_point_addresses([{'Выгрузка 3': 'C'}, {'Выгрузка другое': 'Не точка'}, {'Комментарий': 'Не точка'}, {'Выгрузка 1': 'A'}], 'Выгрузка')
        assert addresses == ['A', 'C']
