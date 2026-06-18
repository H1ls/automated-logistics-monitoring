from __future__ import annotations

import re


class GoogleRowMapper:
    PLATE_LETTERS = "АВЕКМНОРСТУХABEKMHOPCTYX"
    PLATE_RE = re.compile(rf"^[{PLATE_LETTERS}]\d{{3}}[{PLATE_LETTERS}]{{2}}\d{{2,3}}$")
    PLATE_PREFIX_RE = re.compile(rf"^\s*([{PLATE_LETTERS}])\s*(\d{{3}})\s*([{PLATE_LETTERS}]{{2}})\s*(.*)$")

    @staticmethod
    def _format_plate(value: str) -> str:
        compact = re.sub(r"\s+", "", value or "")
        if len(compact) >= 8:
            return compact[:6] + " " + compact[6:]
        return compact

    @staticmethod
    def _phone_digits(value: str) -> str:
        return re.sub(r"\D+", "", value or "")

    @staticmethod
    def _looks_like_phone(value: str) -> bool:
        return len(value) >= 10 and value[:1] in {"7", "8", "9"}

    @staticmethod
    def _phone_text(value: str) -> str:
        return str(value or "").strip(" \t\r\n,;")

    @classmethod
    def _split_ts_phone(cls, value: str) -> tuple[str, str]:
        text = str(value or "").strip()
        parsed = cls._split_by_plate_prefix(text)
        if parsed is not None:
            return parsed

        parts = text.split()
        if len(parts) > 1:
            phone_text = cls._phone_text(parts[-1])
            phone = cls._phone_digits(phone_text)
            plate = "".join(parts[:-1])
            if cls._looks_like_phone(phone) and cls.PLATE_RE.match(plate):
                return cls._format_plate(plate), phone_text

        compact = re.sub(r"\s+", "", text)
        for plate_len in (9, 8):
            plate = compact[:plate_len]
            phone_text = cls._phone_text(compact[plate_len:])
            phone = cls._phone_digits(phone_text)
            if cls.PLATE_RE.match(plate) and cls._looks_like_phone(phone):
                return cls._format_plate(plate), phone_text

        number, phone = compact[:9], compact[9:]
        return cls._format_plate(number), phone

    @classmethod
    def _split_by_plate_prefix(cls, text: str) -> tuple[str, str] | None:
        match = cls.PLATE_PREFIX_RE.match(text)
        if not match:
            return None

        letter, digits, letters, tail = match.groups()
        tail = tail.lstrip()
        for region_len in (3, 2):
            region = tail[:region_len]
            rest = tail[region_len:].lstrip()
            if not region.isdigit():
                continue
            phone_text = cls._phone_text(rest)
            phone = cls._phone_digits(phone_text)
            if cls._looks_like_phone(phone):
                return cls._format_plate(f"{letter}{digits}{letters}{region}"), phone_text

        return None

    @staticmethod
    def build_row(google_sheet_row: int, dh: list[str]) -> dict:
        d = dh[0] if len(dh) > 0 else ""
        e = dh[1] if len(dh) > 1 else ""
        f = dh[2] if len(dh) > 2 else ""
        g = dh[3] if len(dh) > 3 else ""
        h = dh[4] if len(dh) > 4 else ""

        formatted_ts, phone = GoogleRowMapper._split_ts_phone(d)

        return {"index": google_sheet_row,
                "google_sheet_row": google_sheet_row,
                "ТС": formatted_ts,
                "Телефон": phone,
                "ФИО": e,
                "КА": f,
                "Погрузка": g,
                "Выгрузка": h,
                "raw_load": g,
                "raw_unload": h, }
