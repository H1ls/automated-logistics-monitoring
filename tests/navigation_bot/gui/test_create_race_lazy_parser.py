import json
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication

from Navigation_Bot.gui.dialogs.create_race_dialog import CreateRaceDialog


LAZY_TEXT_FILE = Path(__file__).with_name("lazy_text_probe_input.txt")

FALLBACK_LAZY_TEXT = '''
Загрузка: 04.07.2026, прибыть к 8:00:00, Новосибирская обл., г. Новосибирск, Станционнуую 80корп.6, Заезд с Дукача
Контакт : 89628260923  ООО "НЕО-ЛОГИСТ"
Разгрузка: 11.07.2026, прибыть к 8:00:00, г.Хабаровск, ул. Тихоокеанская, д.73, кор.3, 8984-2914151
'''


class DummyTaskRepository:
    connection = None
    data = []

    def get(self):
        return []


def test_lazy_text_parser_probe():
    """
    Ручной probe для _apply_lazy_text_if_needed.

    Как пользоваться:
    1. Вставь текст заявки в lazy_text_probe_input.txt рядом с этим тестом.
    2. Запусти:
       python -m pytest tests/navigation_bot/gui/test_create_race_lazy_parser.py -s
    3. Посмотри распарсенный buffer в stdout.
    """
    app = QApplication.instance() or QApplication([])
    dialog = CreateRaceDialog(task_repository=DummyTaskRepository(), log_func=print)

    lazy_text = LAZY_TEXT_FILE.read_text(encoding="utf-8").strip()
    if not lazy_text:
        lazy_text = FALLBACK_LAZY_TEXT.strip()
    dialog.edit_lazy.setPlainText(lazy_text)

    dialog._sync_buffer()
    dialog._apply_lazy_text_if_needed()
    payload = dialog.get_payload()
    buffer = payload["buffer"]

    print("\n=== LAZY PARSER RESULT ===")
    print(json.dumps(buffer, ensure_ascii=False, indent=2))

    assert buffer.get("Погрузка"), "Лентяй не распарсил Погрузку"
    assert buffer.get("Выгрузка"), "Лентяй не распарсил Выгрузку"
    assert buffer.get("raw_load"), "Лентяй не заполнил raw_load"
    assert buffer.get("raw_unload"), "Лентяй не заполнил raw_unload"

    dialog.close()
    app.processEvents()
