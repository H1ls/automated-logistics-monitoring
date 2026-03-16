# LogistX/onec/steps/find_race.py
from __future__ import annotations


class FindRaceStep:
    stage = "find_race"

    def __init__(self, session, errors, log_func=print):
        self.session = session
        self.errors = errors
        self.log = log_func

    def run(self, ctx):
        search_text = ctx.get_search_text()
        self.log(f"🔎 Ищу рейс: {search_text}")

        self.session.click_anchor("race_list_focus")
        self.session.sleep(0.15)

        self.session.hotkey("ctrl", "f")
        self.session.sleep(0.15)

        self.session.paste_text(search_text)
        self.session.press("enter")
        self.session.sleep(0.25)

        err = self.errors.handle_generic()
        if err:
            raise RuntimeError(f"Ошибка при поиске рейса: {err.kind}")