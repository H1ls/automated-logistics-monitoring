# LogistX/onec/scenarios/base.py
from __future__ import annotations

from LogistX.onec.results import BotResult
from PIL import Image, ImageDraw
from pathlib import Path


class ScenarioError(Exception):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.message = message


class BaseScenario:
    name = "base"

    def __init__(self, session, error_handler, log_func=print):
        self.session = session
        self.errors = error_handler
        self.log = log_func

    def starts(self, ctx) -> BotResult:
        raise NotImplementedError

    def fail(self, stage: str, message: str):
        raise ScenarioError(stage, message)

    def check_generic_error(self):
        info = self.errors.handle_generic()
        return info
