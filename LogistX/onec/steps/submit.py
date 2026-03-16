# LogistX/onec/steps/submit.py
from __future__ import annotations


class SubmitStep:
    stage = "submit"

    def __init__(self, session, errors, log_func=print):
        self.session = session
        self.errors = errors
        self.log = log_func

    def run(self, ctx):
        self.log("💾 Вношу документ")

        btn = self.session.ui_map.get_optional_anchor("submit_button")
        if btn:
            self.session.click(*btn)
            self.session.sleep(0.8)
        else:
            self.session.submit_ctrl_enter()

        err = self.errors.detect()
        if err:
            self.errors.close_error_dialog()
            raise RuntimeError(f"Ошибка при внесении документа: {err.kind}")

        self.log("✅ Внесение завершено")