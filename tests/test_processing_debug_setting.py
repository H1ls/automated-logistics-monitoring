from types import SimpleNamespace
from unittest import TestCase

from Navigation_Bot.core.application.services.navigation.logistx_race_service import LogistxRaceService
from Navigation_Bot.core.settings.settings_schema import SECTIONS


class ProcessingDebugSettingTests(TestCase):
    def test_debug_checkbox_is_after_timeout(self):
        fields = SECTIONS["processing"][1]

        self.assertEqual(list(fields), ["timeout_seconds", "debug_mode"])
        self.assertIs(fields["debug_mode"][1], bool)

    def test_runtime_change_updates_existing_onec_session(self):
        service = LogistxRaceService(logger=lambda *_: None,executor=None,browser_session=None,debug_mode=False)
        artifacts = SimpleNamespace(enabled=False)
        service.onec_bot = SimpleNamespace(session=SimpleNamespace(artifacts=artifacts))

        service.set_debug_mode(True)

        self.assertTrue(service.debug_mode)
        self.assertTrue(artifacts.enabled)

