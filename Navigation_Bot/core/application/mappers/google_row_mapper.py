from __future__ import annotations

import re


class GoogleRowMapper:
    @staticmethod
    def build_row(index_key: int, dh: list[str]) -> dict:
        d = dh[0] if len(dh) > 0 else ""
        e = dh[1] if len(dh) > 1 else ""
        f = dh[2] if len(dh) > 2 else ""
        g = dh[3] if len(dh) > 3 else ""
        h = dh[4] if len(dh) > 4 else ""

        raw_ts = re.sub(r"\s+", "", d)
        number, phone = raw_ts[:9], raw_ts[9:]
        formatted_ts = number[:6] + " " + number[6:] if len(number) >= 9 else number

        return {"index": index_key,
                "ТС": formatted_ts,
                "Телефон": phone,
                "ФИО": e,
                "КА": f,
                "Погрузка": g,
                "Выгрузка": h,
                "raw_load": g,
                "raw_unload": h, }
