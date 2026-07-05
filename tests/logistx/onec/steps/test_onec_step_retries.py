from types import SimpleNamespace
from LogistX.onec.race_card_verifier import RaceCardVerification
from LogistX.onec.steps.capture_race_ui import CaptureRaceUiStep
from LogistX.onec.steps.open_race import OpenRaceStep

class _RetryArtifacts:

    def __init__(self):
        self.full_captures = []

    def capture_full(self, stage, name):
        path = f'{stage}__{name}.png'
        self.full_captures.append(path)
        return path

class _RetrySession:

    def __init__(self):
        self.searches = []
        self.sleeps = []

    def find_template_on_shot(self, shot_path, template_name):
        self.searches.append((shot_path, template_name))
        if len(self.searches) == 2:
            return SimpleNamespace(center=(100, 200), score=0.95)
        return None

    def sleep(self, seconds):
        self.sleeps.append(seconds)

class TestCaptureRaceUiRetry:

    def test_retries_missing_anchor_with_fresh_full_screenshot(self):
        session = _RetrySession()
        artifacts = _RetryArtifacts()
        step = CaptureRaceUiStep(session, errors=None, log_func=lambda *_: None, artifacts=artifacts, find_attempts=3)
        point = step._find_with_retries('initial.png', 'wait_load', 'wait_load')
        assert (point.x, point.y) == (100, 200)
        assert artifacts.full_captures == ['capture_race_ui__retry_wait_load_2.png']
        assert session.sleeps == [0.35]

class _OpenUiMap:

    def get_optional_template(self, name):
        return 'header.png' if name == 'race_form_header' else None

class _OpenSession:

    def __init__(self, clipboard):
        self.ui_map = _OpenUiMap()
        self.clipboard = clipboard

    def clear_clipboard(self):
        pass

    def hotkey(self, *_args):
        pass

    def sleep(self, _seconds):
        pass

    def copy_clipboard(self):
        return self.clipboard

    def find_template_global(self, _name):
        return object()

class _OpenArtifacts:

    def __init__(self):
        self.captures = 0

    def capture_rect(self, *_args):
        self.captures += 1
        return 'race.png'

class _Verifier:

    def __init__(self):
        self.calls = 0

    def verify(self, _ctx, _path):
        self.calls += 1
        return RaceCardVerification(ok=True, race_ok=True, unit_ok=True, expected_race='ВТ000009140', expected_plate='О 996 ОР 790', recognized_text='race and plate')

class TestOpenRaceFallback:

    @staticmethod
    def _ctx():
        return SimpleNamespace(race_name='Рейс (уэ) ВТ000009140 от 19.06.2026', meta={'unit': 'О 996 ОР 790 SITRAK'}, state={})

    def test_uses_ocr_only_when_clipboard_did_not_confirm_race(self):
        artifacts = _OpenArtifacts()
        verifier = _Verifier()
        step = OpenRaceStep(_OpenSession(clipboard=''), errors=None, log_func=lambda *_: None, artifacts=artifacts, race_card_verifier=verifier)
        assert step._is_race_opened(self._ctx())
        assert verifier.calls == 1
        assert artifacts.captures == 1

    def test_clipboard_success_skips_ocr(self):
        artifacts = _OpenArtifacts()
        verifier = _Verifier()
        step = OpenRaceStep(_OpenSession(clipboard='ВТ000009140'), errors=None, log_func=lambda *_: None, artifacts=artifacts, race_card_verifier=verifier)
        assert step._is_race_opened(self._ctx())
        assert verifier.calls == 0
        assert artifacts.captures == 0
