import pytest
from LogistX.onec.steps.submit import SubmitStep

class _UiMap:

    def get_optional_template(self, name):
        return 'header.png' if name == 'race_form_header' else None

class _Session:

    def __init__(self, header_states):
        self.ui_map = _UiMap()
        self.header_states = iter(header_states)

    def find_template_global(self, _name):
        return next(self.header_states, True)

    def sleep(self, _seconds):
        pass

class _Errors:

    def detect(self):
        return None

    def close_error_dialog(self):
        pass

class TestSubmitStep:

    def test_requires_two_consecutive_absent_header_checks(self):
        step = SubmitStep(_Session([True, False, True, False, False]), _Errors(), log_func=lambda *_: None, checkbox_controller=object(), submit_timeout=1)
        step._wait_submission_confirmed()

    def test_fails_when_race_form_remains_open(self):
        step = SubmitStep(_Session([True]), _Errors(), log_func=lambda *_: None, checkbox_controller=object(), submit_timeout=0.1)
        with pytest.raises(RuntimeError, match='карточка рейса осталась открыта'):
            step._wait_submission_confirmed()
