# LogistX/controllers/onec/errors.py
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pyautogui
import pytesseract
from PIL import Image

from .session import OneCSession


@dataclass
class ErrorInfo:
    kind: str
    text: str = ""
    finish_dt: datetime | None = None


class OneCErrorHandler:
    def __init__(self, session: OneCSession, log_func=print):
        self.session = session
        self.log = log_func
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if not pytesseract.pytesseract.tesseract_cmd:
            default_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if Path(default_path).exists():
                pytesseract.pytesseract.tesseract_cmd = default_path
            else:
                found = shutil.which("tesseract")
                if found:
                    pytesseract.pytesseract.tesseract_cmd = found

    def is_error_dialog_present(self) -> bool:
        # 1. быстрый поиск по заголовку окна ошибки, error_header_region — только шапка окна
        try:
            if self.session.find_template_in_region("error_title_1c", "error_header_region"):
                self.log("✅ Ошибка найден по заголовку 1C")
                return True
        except Exception:
            pass

        # 2. fallback по кнопке OK, error_search_region — всё окно с кнопкой
        try:
            if self.session.find_template_in_region("error_ok_button",
                                                    "error_search_region"):
                self.log("✅ Ошибка найден по кнопке OK")
                return True
        except Exception:
            pass

        return False

    def read_error_text(self) -> str:
        regions = []

        cfg_region = self.session.ui_map.get_optional_region("error_text_region")
        if cfg_region:
            regions.append(cfg_region)

        # fallback как в старом twoCRaceWriter
        regions.append((960, 450, 400, 130))

        for i, region in enumerate(regions, start=1):
            path = self.session.tmp_dir / f"error_text_{i}.png"
            img = pyautogui.screenshot(region=region)
            img.save(path)

            try:
                with Image.open(path) as pil:
                    text = pytesseract.image_to_string(pil, lang="rus+eng")
                    text = " ".join((text or "").split())
                    if text:
                        self.log(f"📖 OCR error text[{i}]: {text}")
                        return text
            except Exception as e:
                self.log(f"❌ OCR error_text failed: {e}")

        return ""

    def _extract_finish_dt(self, text: str) -> datetime | None:
        if not text:
            return None

        norm = " ".join(text.split())
        low = norm.lower()
        dt_re = r"\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{2}:\d{2}"

        m = re.search(r"выполнен\s+(.*?)(?:ответственн|$)", low, flags=re.IGNORECASE)
        if m:
            tail = m.group(1)
            found = re.findall(dt_re, tail)
            dts = []
            for s in found:
                try:
                    dts.append(datetime.strptime(s, "%d.%m.%Y %H:%M:%S"))
                except Exception:
                    pass
            if dts:
                return max(dts)

        m = re.search(r"выполнен\s+(" + dt_re + r")", low, flags=re.IGNORECASE)
        if m:
            s = m.group(1)
            try:
                return datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
            except Exception:
                pass

        matches = []
        matches += re.findall(r"выполнен\s+(" + dt_re + r")", low, flags=re.IGNORECASE)
        matches += re.findall(r"(" + dt_re + r")\s+выполнен", low, flags=re.IGNORECASE)

        dts = []
        for s in matches:
            try:
                dts.append(datetime.strptime(s, "%d.%m.%Y %H:%M:%S"))
            except Exception:
                pass

        return max(dts) if dts else None

    def detect(self) -> ErrorInfo | None:
        if not self.is_error_dialog_present():
            return None

        text = self.read_error_text()
        low = text.lower()

        if "выполнен" in low or "пересекается" in low or "дата отправления" in low or "дата выполнения" in low:
            return ErrorInfo(kind="date_conflict", text=text, finish_dt=self._extract_finish_dt(text), )

        if "недостаточно прав" in low or "прав доступа" in low:
            return ErrorInfo(kind="access_denied", text=text)

        if "обязательное поле" in low or "не заполнено" in low:
            return ErrorInfo(kind="validation_error", text=text)

        return ErrorInfo(kind="unknown_dialog", text=text)

    def close_error_dialog(self):
        self.log("→ Закрываю диалог ошибки")
        self.session.press("enter")
        self.session.sleep(0.2)

    def handle_generic(self) -> ErrorInfo | None:
        info = self.detect()
        if not info:
            return None

        self.log(f"⚠️ Обнаружена ошибка: {info.kind}; text={info.text}")
        self.close_error_dialog()
        return info

    def safe_abort(self, reason: str = ""):
        self.log(f"🛑 safe_abort: {reason}")
        self.session.safe_close_card()
