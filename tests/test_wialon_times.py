from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase

from LogistX.onec.steps.fetch_wialon_times import FetchWialonTimesStep
from LogistX.onec.wialon_times import WialonMeta, WialonTimesPolicy, WialonTimesService


class WialonMetaTests(TestCase):
    def test_reads_and_validates_context_metadata(self):
        ctx = SimpleNamespace(meta={"unit": " Truck ", "load_zone": " Load ", "unload_zone": " Unload "})

        meta = WialonMeta.from_context(ctx)

        self.assertEqual(meta, WialonMeta("Truck", "Load", "Unload"))

    def test_precheck_does_not_require_load_zone(self):
        ctx = SimpleNamespace(meta={"unit": "Truck", "unload_zone": "Unload"})

        meta = WialonMeta.from_context(ctx, require_load_zone=False)

        self.assertEqual(meta.load_zone, "")


class WialonTimesPolicyTests(TestCase):
    def test_guard_clears_recent_unload_without_mutating_source(self):
        source = {
            "unload_in": "21.06.2026 12:00:00",
            "unload_out": "21.06.2026 12:50:00",
        }
        policy = WialonTimesPolicy(
            unload_out_guard_minutes=20,
            now_func=lambda: datetime(2026, 6, 21, 13, 0, 0),
            log_func=lambda *_: None,
        )

        result = policy.apply(source)

        self.assertEqual(result["unload_out"], "")
        self.assertEqual(source["unload_out"], "21.06.2026 12:50:00")

    def test_rejects_invalid_time_and_reversed_interval(self):
        policy = WialonTimesPolicy()

        with self.assertRaisesRegex(RuntimeError, "некорректное время"):
            policy.apply({"load_in": "invalid"})
        with self.assertRaisesRegex(RuntimeError, "load_out раньше load_in"):
            policy.apply({
                "load_in": "21.06.2026 13:00:00",
                "load_out": "21.06.2026 12:00:00",
            })

    def test_rejects_out_without_in(self):
        with self.assertRaisesRegex(RuntimeError, "unload_out .* unload_in"):
            WialonTimesPolicy().apply({"unload_out": "21.06.2026 12:00:00"})

    def test_future_unload_out_is_cleared_without_mutating_source(self):
        source = {
            "unload_in": "21.06.2026 12:00:00",
            "unload_out": "21.06.2026 14:00:00",
        }
        policy = WialonTimesPolicy(
            now_func=lambda: datetime(2026, 6, 21, 13, 0, 0),
            log_func=lambda *_: None,
        )

        result = policy.apply(source)

        self.assertEqual(result["unload_out"], "")
        self.assertEqual(source["unload_out"], "21.06.2026 14:00:00")


class _ReportsBot:
    def __init__(self):
        self.kwargs = None

    def run_geo_report_for_trip(self, **kwargs):
        self.kwargs = kwargs
        return {"load_in": "value"}


class WialonTimesServiceTests(TestCase):
    def test_service_only_forwards_explicit_report_parameters(self):
        reportsbot = _ReportsBot()
        service = WialonTimesService(reportsbot, log_func=lambda *_: None)
        meta = WialonMeta("Truck", "Load", "Unload")

        result = service.fetch_trip(meta, "from", "to")

        self.assertEqual(result, {"load_in": "value"})
        self.assertEqual(reportsbot.kwargs["unit"], "Truck")
        self.assertEqual(reportsbot.kwargs["load_zone"], "Load")
        self.assertEqual(reportsbot.kwargs["unload_zone"], "Unload")


class _Service:
    def fetch_trip(self, meta, date_from, date_to):
        self.meta = meta
        self.interval = date_from, date_to
        return {"raw": True}


class _Policy:
    def apply(self, payload):
        self.payload = payload
        return {
            "load_in": "21.06.2026 10:00:00",
            "load_out": "21.06.2026 11:00:00",
            "unload_in": "21.06.2026 12:00:00",
            "unload_out": "21.06.2026 13:00:00",
        }


class FetchWialonTimesStepTests(TestCase):
    def test_step_transfers_policy_result_to_context(self):
        service = _Service()
        policy = _Policy()
        step = FetchWialonTimesStep(
            log_func=lambda *_: None,
            service=service,
            policy=policy,
        )
        ctx = SimpleNamespace(
            departure_dt="21.06.2026 09:00",
            meta={"unit": "Truck", "load_zone": "Load", "unload_zone": "Unload"},
            state={},
            load_in=None,
            load_out=None,
            unload_in=None,
            unload_out=None,
        )

        step.run(ctx)

        self.assertEqual(policy.payload, {"raw": True})
        self.assertEqual(ctx.load_in, "21.06.2026 10:00:00")
        self.assertEqual(ctx.unload_out, "21.06.2026 13:00:00")
        self.assertEqual(ctx.state["wialon_payload"]["load_out"], "21.06.2026 11:00:00")
