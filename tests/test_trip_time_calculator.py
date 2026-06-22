from types import SimpleNamespace
from unittest import TestCase

from LogistX.onec.steps.fill_times import FillTimesStep
from LogistX.onec.trip_time_calculator import TripTimeCalculator, TripTimeInput


class TripTimeCalculatorTests(TestCase):
    def test_calculates_lateness_stay_and_rating_items(self):
        result = TripTimeCalculator().calculate(TripTimeInput(
            load_arrive_deadline="21.06.2026 10:00:00",
            load_in="21.06.2026 11:01:00",
            load_out="21.06.2026 18:50:00",
            unload_arrive_deadline="22.06.2026 20:00:00",
            unload_in="22.06.2026 19:00:00",
            unload_out="23.06.2026 01:00:00",
        ))

        self.assertEqual(result["load_lateness_minutes"], 61)
        self.assertEqual(result["load_late_hours"], 2)
        self.assertEqual(result["unload_lateness_minutes"], 0)
        self.assertEqual(result["load_stay_minutes"], 469)
        self.assertEqual(result["load_stay_hours"], 8)
        self.assertEqual(result["load_over_6h_hours"], 2)
        self.assertEqual(result["driver_rating_items"], [
            {"kind": "Опоздание на погрузку", "hours": 2},
            {"kind": "Простой на погрузке", "hours": 2},
        ])

    def test_stay_remainder_of_exactly_45_minutes_is_not_rounded_up(self):
        result = TripTimeCalculator().calculate(TripTimeInput(
            load_in="21.06.2026 10:00:00",
            load_out="21.06.2026 17:45:00",
        ))

        self.assertEqual(result["load_stay_hours"], 7)
        self.assertEqual(result["load_over_6h_hours"], 1)
        self.assertEqual(result["driver_rating_items"], [])

    def test_missing_values_do_not_create_deviations(self):
        result = TripTimeCalculator().calculate(TripTimeInput())

        self.assertIsNone(result["load_lateness_minutes"])
        self.assertIsNone(result["load_stay_minutes"])
        self.assertEqual(result["load_late_hours"], 0)
        self.assertEqual(result["driver_rating_items"], [])


class _Calculator:
    def __init__(self):
        self.source = None

    def calculate(self, source):
        self.source = source
        return {"driver_rating_items": [{"kind": "test", "hours": 1}], "value": 42}


class FillTimesCalculatorIntegrationTests(TestCase):
    def test_fill_step_only_transfers_context_to_calculator_and_stores_result(self):
        calculator = _Calculator()
        step = FillTimesStep.__new__(FillTimesStep)
        step.calculator = calculator
        step.log = lambda *_: None
        ctx = SimpleNamespace(
            state={},
            load_in="load-in",
            load_out="load-out",
            unload_in="unload-in",
            unload_out="unload-out",
            load_arrive_deadline="load-deadline",
            unload_arrive_deadline="unload-deadline",
        )

        step._store_calc(ctx)

        self.assertEqual(calculator.source.load_in, "load-in")
        self.assertEqual(calculator.source.unload_arrive_deadline, "unload-deadline")
        self.assertEqual(ctx.state["calc"]["value"], 42)

