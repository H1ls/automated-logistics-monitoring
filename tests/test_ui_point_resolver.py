from types import SimpleNamespace
from unittest import TestCase

from LogistX.onec.steps.ui_point_resolver import UiPointResolver


class _UiMap:
    def __init__(self, anchors=None, templates=None):
        self.anchors = anchors or {}
        self.templates = templates or {}

    def get_optional_anchor(self, name):
        return self.anchors.get(name)

    def get_optional_template(self, name):
        return self.templates.get(name)


class _Session:
    def __init__(self, anchors=None, templates=None, matches=None):
        self.ui_map = _UiMap(anchors=anchors, templates=templates)
        self.matches = matches or {}
        self.clicks = []
        self.template_searches = []

    def find_template_global(self, name):
        self.template_searches.append(name)
        center = self.matches.get(name)
        return SimpleNamespace(center=center) if center else None

    def click(self, x, y):
        self.clicks.append((x, y))


class UiPointResolverTests(TestCase):
    def test_context_point_has_priority_over_anchor_and_template(self):
        session = _Session(
            anchors={"cargo_tab": (30, 40)},
            templates={"cargo_tab": "cargo.png"},
            matches={"cargo_tab": (50, 60)},
        )
        ctx = SimpleNamespace(state={"ui_points": {"cargo_tab": {"x": "10", "y": "20"}}})

        point = UiPointResolver(session).click("cargo_tab", ctx=ctx)

        self.assertEqual((point.x, point.y, point.source), (10, 20, "ctx.state"))
        self.assertEqual(session.clicks, [(10, 20)])
        self.assertEqual(session.template_searches, [])

    def test_anchor_is_used_when_context_point_is_missing(self):
        session = _Session(anchors={"cargo_tab": (30, 40)})

        point = UiPointResolver(session).resolve("cargo_tab", ctx=SimpleNamespace(state={}))

        self.assertEqual((point.x, point.y, point.source), (30, 40, "ui_map.anchor"))

    def test_template_is_used_when_context_and_anchor_are_missing(self):
        session = _Session(
            templates={"cargo_tab": "cargo.png"},
            matches={"cargo_tab": (50, 60)},
        )

        point = UiPointResolver(session).resolve("cargo_tab")

        self.assertEqual((point.x, point.y, point.source), (50, 60, "ui_map.template"))

    def test_missing_point_has_contextual_error(self):
        with self.assertRaisesRegex(RuntimeError, "UI-точка 'cargo_tab'"):
            UiPointResolver(_Session()).resolve("cargo_tab")

    def test_malformed_context_point_is_not_silently_ignored(self):
        session = _Session(anchors={"cargo_tab": (30, 40)})
        ctx = SimpleNamespace(state={"ui_points": {"cargo_tab": {"x": 10}}})

        with self.assertRaisesRegex(RuntimeError, "Некорректная UI-точка"):
            UiPointResolver(session).resolve("cargo_tab", ctx=ctx)

