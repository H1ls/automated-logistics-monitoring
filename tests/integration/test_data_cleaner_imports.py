class TestDataCleanerImport:

    def test_compact_vehicle_key_is_imported_from_its_owner_module(self):
        from Navigation_Bot.bots.data_cleaner import compact_vehicle_key
        assert compact_vehicle_key(' а 123 вс 77 ') == 'А123ВС77'

    def test_vehicle_lookup_keys_include_regionless_plate_key(self):
        from Navigation_Bot.core.repositories.vehicle_registry_fields import vehicle_lookup_keys
        assert vehicle_lookup_keys(' C 955 MA 716 ') == ['C955MA716', 'C955MA']
        assert vehicle_lookup_keys('C955MA') == ['C955MA']

    def test_postgres_vehicle_repository_lookup_matches_regionless_plate(self):
        from Navigation_Bot.core.repositories.postgres_vehicle_repository import PostgresVehicleRepository

        class FakeResult:

            def fetchall(self):
                return [{'monitoring_id': 27645253, 'monitoring_name': 'C955MA790', 'plate_number': '', 'vehicle_full_name': 'C 955 MA 716'}]

        class FakeConnection:

            def execute(self, *args, **kwargs):
                return FakeResult()
        lookup = PostgresVehicleRepository(FakeConnection()).registry_lookup()
        assert lookup['C955MA']['monitoring_id'] == 27645253

    def test_vehicle_monitoring_id_prefers_api_field(self):
        from Navigation_Bot.core.domain.task_identity import vehicle_monitoring_id
        assert vehicle_monitoring_id({'vehicle_monitoring_id': 27645253}) == 27645253
        assert vehicle_monitoring_id({'id': '27645253'}) == 27645253
