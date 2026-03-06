# LogistX/controllers/onec/race_writer.py
from __future__ import annotations

from typing import Any

from LogistX.controllers.base import OneCBase
from LogistX.controllers.scenarios.departure_fix import DepartureFixScenario
from LogistX.controllers.scenarios.cargo_times_and_rating import CargoTimesAndRatingScenario


class OneCRaceWriter:
    """
    Фасад: единая точка входа.
    Внутри — композиция сценариев.
    """
    def __init__(self, rdp_activator, log_func=print, ui_map_path=None):
        self.base = OneCBase(rdp_activator=rdp_activator, log_func=log_func, ui_map_path=ui_map_path)
        self.cargo = CargoTimesAndRatingScenario(self.base)
        self.departure = DepartureFixScenario(self.base)

    def close_race(self, payload: dict) -> bool:
        """
        Здесь ты соберёшь единый flow:
        - activate RDP / открыть рейс
        - cargo.fill(...)
        - departure.fix(...)
        - сохранить/закрыть
        """
        # пример:
        # self.base.rdp_activator.activate()
        # self.cargo.fill_times_with_vision(payload)
        # self.departure.fix_departure_flow(payload)
        return True