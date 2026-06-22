from types import SimpleNamespace
from unittest import TestCase

from LogistX.onec.race_card_verifier import RaceCardVerifier


def _ctx():
    return SimpleNamespace(
        race_name="Рейс (уэ) ВТ000009125 от 19.06.2026 10:15:16",
        meta={"unit": "Н 109 ОУ 790 SITRAK C7H 4X2",}
    )


class RaceCardVerifierTests(TestCase):
    def test_verifies_race_and_plate_with_latin_ocr_letters(self):
        recognized = """
        Номер: BT000009125
        Организация: Руссия Логистик
        Транспорт: H 109 OY 790
        """
        verifier = RaceCardVerifier(ocr_func=lambda _path: recognized)

        result = verifier.verify(_ctx(), "unused.png")

        self.assertTrue(result.ok)
        self.assertTrue(result.race_ok)
        self.assertTrue(result.unit_ok)

    def test_reports_each_mismatched_field(self):
        result = RaceCardVerifier(ocr_func=lambda _path: "другая карточка").verify(_ctx(), "unused.png")

        self.assertFalse(result.ok)
        self.assertEqual(result.failed_fields, ["номер рейса", "номер машины"])
