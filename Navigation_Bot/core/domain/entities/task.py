from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from Navigation_Bot.core.domain.value_objects.arrival_forecast import ArrivalForecast
from Navigation_Bot.core.domain.value_objects.navigation_state import NavigationState
from Navigation_Bot.core.domain.value_objects.processing_state import ProcessingState
from Navigation_Bot.core.domain.value_objects.route_point import RoutePoint
from Navigation_Bot.core.domain.value_objects.route_plan import RoutePlan
from Navigation_Bot.core.domain.value_objects.vehicle import Vehicle
from Navigation_Bot.core.domain.value_objects.carrier import Carrier
from Navigation_Bot.core.domain.value_objects.driver import Driver


@dataclass(slots=True)
class Task:
    """
    Главная сущность текущего приложения.
    Пока это ещё не полноценный Trip из CRM,
    но уже нормальная доменная модель вместо сырого dict.
    """
    index: int = 0

    vehicle: Vehicle = field(default_factory=Vehicle)
    driver: Driver = field(default_factory=Driver)
    carrier: Carrier | None = None

    route_plan: RoutePlan = field(default_factory=RoutePlan)
    navigation: NavigationState = field(default_factory=NavigationState)
    forecast: ArrivalForecast = field(default_factory=ArrivalForecast)
    processing: ProcessingState = field(default_factory=ProcessingState)

    comm_load: str = ""
    comm_unload: str = ""
    raw_load: str = ""
    raw_unload: str = ""

    highlight_until: str | None = None

    def ensure_processing_consistency(self) -> None:
        self.processing.ensure_size(len(self.route_plan.unloads))

    def get_first_unprocessed_unload_index(self) -> int | None:
        self.ensure_processing_consistency()

        for i in range(len(self.route_plan.unloads)):
            if not self.processing.is_unload_processed(i):
                return i
        return None

    def get_first_unprocessed_unload(self) -> tuple[int, RoutePoint] | None:
        idx = self.get_first_unprocessed_unload_index()
        if idx is None:
            return None
        if idx >= len(self.route_plan.unloads):
            return None
        return idx, self.route_plan.unloads[idx]

    def mark_unload_processed(self, unload_index: int) -> None:
        self.ensure_processing_consistency()
        self.processing.mark_unload_processed(unload_index)

    @property
    def plate_number(self) -> str:
        return self.vehicle.plate_number

    @property
    def monitoring_id(self) -> Optional[int]:
        return self.vehicle.monitoring_id

    @property
    def driver_name(self) -> str:
        return self.driver.full_name

    @property
    def carrier_name(self) -> str:
        return self.carrier.name if self.carrier else ""


