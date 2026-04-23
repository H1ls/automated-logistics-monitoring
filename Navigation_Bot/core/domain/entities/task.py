from dataclasses import dataclass, field

from Navigation_Bot.core.domain.value_objects.arrival_forecast import ArrivalForecast
from Navigation_Bot.core.domain.value_objects.contact_info import ContactInfo
from Navigation_Bot.core.domain.value_objects.navigation_state import NavigationState
from Navigation_Bot.core.domain.value_objects.processing_state import ProcessingState
from Navigation_Bot.core.domain.value_objects.route_plan import RoutePlan
from Navigation_Bot.core.domain.value_objects.route_point import RoutePoint
from Navigation_Bot.core.domain.value_objects.vehicle import Vehicle


@dataclass(slots=True)
class Task:
    index: int
    vehicle: Vehicle
    contact: ContactInfo = field(default_factory=ContactInfo)
    carrier_code: str = ""
    route_plan: RoutePlan = field(default_factory=RoutePlan)
    navigation: NavigationState = field(default_factory=NavigationState)
    forecast: ArrivalForecast = field(default_factory=ArrivalForecast)
    processing: ProcessingState = field(default_factory=ProcessingState)
    raw_load: str = ""
    raw_unload: str = ""

    def get_first_unprocessed_unload_index(self) -> int | None:
        unloads = self.route_plan.unloads
        processed = self.processing.processed_unloads

        for i in range(len(unloads)):
            done = processed[i] if i < len(processed) else False
            if not done:
                return i

        return None

    def get_first_unprocessed_unload(self) -> tuple[int, RoutePoint] | None:
        idx = self.get_first_unprocessed_unload_index()
        if idx is None:
            return None

        if idx >= len(self.route_plan.unloads):
            return None

        return idx, self.route_plan.unloads[idx]