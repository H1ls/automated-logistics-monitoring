from unittest import TestCase

from LogistX.onec.checkbox import CheckboxController


class _Session:
    def __init__(self):
        self.clicks = []

    def click(self, x, y):
        self.clicks.append((x, y))

    def sleep(self, _seconds):
        pass


class _Checkbox(CheckboxController):
    def __init__(self, session, states):
        self.session = session
        self.states = iter(states)
        self.log = lambda *_: None

    def is_checked(self, center, stage, name):
        return next(self.states)


class CheckboxControllerTests(TestCase):
    def test_does_not_click_checked_checkbox(self):
        session = _Session()

        changed = _Checkbox(session, [True]).ensure_checked((10, 20), "stage", "name")

        self.assertFalse(changed)
        self.assertEqual(session.clicks, [])

    def test_clicks_once_and_verifies_checkbox(self):
        session = _Session()

        changed = _Checkbox(session, [False, True]).ensure_checked((10, 20), "stage", "name")

        self.assertTrue(changed)
        self.assertEqual(session.clicks, [(10, 20)])
