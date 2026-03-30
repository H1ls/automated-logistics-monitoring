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

        best_text = ""
        best_score = -1

        for i, region in enumerate(regions, start=1):
            path = self.session.tmp_dir / f"error_text_{i}.png"
            img = pyautogui.screenshot(region=region)
            img.save(path)

            try:
                with Image.open(path) as pil:
                    variants = []

                    # 1. оригинал
                    variants.append(("orig", pil.copy()))

                    # 2. grayscale x2
                    gray = pil.convert("L")
                    gray = gray.resize((gray.width * 2, gray.height * 2))
                    variants.append(("gray_x2", gray))

                    # 3. threshold x2
                    bw = gray.point(lambda p: 255 if p > 185 else 0)
                    variants.append(("bw_x2", bw))

                    # 4. threshold x3
                    gray3 = pil.convert("L").resize((pil.width * 3, pil.height * 3))
                    bw3 = gray3.point(lambda p: 255 if p > 170 else 0)
                    variants.append(("bw_x3", bw3))

                    for name, var_img in variants:
                        cfg = r'--oem 3 --psm 6'
                        text = pytesseract.image_to_string(var_img, lang="rus+eng", config=cfg)
                        text = " ".join((text or "").split())
                        if not text:
                            continue

                        score = 0
                        low = text.lower()

                        if "выполнен" in low:
                            score += 5
                        if "пересекается" in low:
                            score += 2
                        if re.search(r"\d{2}\.\d{2}\.\d{4}", text):
                            score += 2
                        if re.search(r"\d{1,2}[:\-.; ]\d{2}[:\-.; ]\d{2}", text):
                            score += 3

                        # self.log(f"📖 OCR error text[{i}:{name}]: {text}")

                        if score > best_score:
                            best_score = score
                            best_text = text

            except Exception as e:
                self.log(f"❌ OCR error_text failed: {e}")

        return best_text

    def _normalize_ocr_datetime_text(self, text: str) -> str:
        if not text:
            return ""

        s = " ".join(text.split())

        # 4-40:00 -> 4:40:00
        s = re.sub(r"(?<!\d)(\d{1,2})-(\d{2}:\d{2})(?!\d)", r"\1:\2", s)
        # 4;40:00 -> 4:40:00
        s = re.sub(r"(?<!\d)(\d{1,2});(\d{2}:\d{2})(?!\d)", r"\1:\2", s)
        # 4 40:00 -> 4:40:00
        s = re.sub(r"(?<![\d.])(\d{1,2})\s+(\d{2}:\d{2})(?!\d)", r"\1:\2", s)
        # 0:47.00 -> 0:47:00
        s = re.sub(r"(?<!\d)(\d{1,2}):(\d{2})\.(\d{2})(?!\d)", r"\1:\2:\3", s)
        # 0.47:00 -> 0:47:00
        s = re.sub(r"(?<!\d)(\d{1,2})\.(\d{2}):(\d{2})(?!\d)", r"\1:\2:\3", s)
        # 0-47.00 -> 0:47:00
        s = re.sub(r"(?<!\d)(\d{1,2})-(\d{2})\.(\d{2})(?!\d)", r"\1:\2:\3", s)
        # 9:00:00 -> 9:00:00 (не меняем, но чистим странные пробелы)
        s = re.sub(r"(?<!\d)(\d{1,2})\s*:\s*(\d{2})\s*:\s*(\d{2})(?!\d)", r"\1:\2:\3", s)
        return s

    def _extract_finish_dt(self, text: str) -> datetime | None:
        if not text:
            return None

        norm = self._normalize_ocr_datetime_text(text)
        low = norm.lower()

        m = re.search(r"выполнен\s+(.+?)(?:ответственн|$)", low, flags=re.IGNORECASE)
        if m:
            tail = m.group(1)

            date_m = re.search(r"(\d{2}\.\d{2}\.\d{4})", tail)
            time_m = re.search(r"(?<!\d)(\d{1,2})[:\-.; ](\d{2})[:\-.; ](\d{2})(?!\d)", tail)

            if date_m and time_m:
                date_part = date_m.group(1)
                hh = int(time_m.group(1))
                mm = int(time_m.group(2))
                ss = int(time_m.group(3))
                try:
                    best = datetime.strptime(f"{date_part} {hh:02d}:{mm:02d}:{ss:02d}",
                                             "%d.%m.%Y %H:%M:%S",)

                    self.log(f"🧠 'выполнен': {best:%d.%m.%Y %H:%M:%S}")
                    return best
                except Exception:
                    pass

            self.log(f"⚠️ Не удалось распарсить дату после слова 'выполнен'. tail={tail!r}")
            return None

        dt_re = r"\d{2}\.\d{2}\.\d{4}\s+\d{1,2}[:\-.; ]\d{2}[:\-.; ]\d{2}"
        matches = re.findall(dt_re, low)
        dts = []
        for s in matches:
            try:
                s_norm = re.sub(r"[:\-.; ]", ":", s, count=2)
                dts.append(datetime.strptime(s_norm, "%d.%m.%Y %H:%M:%S"))
            except Exception:
                pass

        if dts:
            best = max(dts)
            # self.log(f"🧠 finish_dt fallback(max dt in text): {best:%d.%m.%Y %H:%M:%S}")
            return best

        return None

    def detect(self) -> ErrorInfo | None:
        if not self.is_error_dialog_present():
            return None

        text = self.read_error_text()
        low = text.lower()

        if "выполнен" in low or "пересекается" in low or "дата отправления" in low or "дата выполнения" in low:
            finish_dt = self._extract_finish_dt(text)
            # self.log(f"🧠 detect(): parsed finish_dt={finish_dt}")
            return ErrorInfo(kind="date_conflict", text=text, finish_dt=finish_dt)

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
