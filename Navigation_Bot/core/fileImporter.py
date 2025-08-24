# -*- coding: utf-8 -*-
"""
Navigation_Bot/core/fileImporter.py
Однофайловый скелет для локальной проверки извлечения заявок из PDF/XLSM.

Запуск:
    1) Укажи путь к файлу: TEST_PATH = r"...\Барков ....pdf"  (или .xlsm)
    2) pip install PyPDF2 openpyxl
    3) python Navigation_Bot/core/fileImporter.py
"""

from __future__ import annotations
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# >>> УКАЖИ ПУТЬ ДЛЯ ТЕСТА (pdf или xlsm)
TEST_PATH = r"C:\Users\Hils\PycharmProjects\pet.project\Navigation_Bot\pdf\Барков [МА-0293926] Софрино - Воронеж 15.08.2025.pdf"


# ------------------------ Utils ------------------------

def clean_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\x00", " ").replace("\u00A0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"[ ]{2,}", " ", s)
    return s.strip()


# Заменяем экзотические точки/двоеточия и тонкие пробелы на обычные
def normalize_for_datetime(text: str) -> str:
    if not text:
        return ""
    t = text
    # тонкие пробелы
    t = t.replace("\u00A0", " ").replace("\u2009", " ").replace("\u202F", " ").replace("\u2007", " ")
    # разные «точки»
    dot_chars = "[\.\u2024\u2027\u2219\u2022·•]"
    t = re.sub(rf"(\d)\s*{dot_chars}\s*(\d)", r"\1.\2", t)
    # разные «двоеточия»
    colon_chars = "[:\u2236\u02D0\uFE13\uFE55\uA789\uFF1A]"
    t = re.sub(rf"(\d)\s*{colon_chars}\s*(\d)", r"\1:\2", t)
    # иногда дата и время разделены кучей переносов — оставим один пробел
    t = re.sub(r"(\d{1,2}\.\d{1,2}\.\d{4})[ \t]*[\r\n]+[ \t]*(\d{1,2}:\d{2}(?::\d{2})?)", r"\1 \2", t)
    return t


# --- [PATCH] надёжный парсер дат/времени из текста ---

_DT_RE = re.compile(r"(?P<date>\d{1,2}\.\d{1,2}\.\d{4})\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)")


def _join_broken_dt_lines(text: str) -> str:
    """
    Склеивает случаи, когда дата и время разорваны переводом строки:
    '15.08.2025\n16:00:00' -> '15.08.2025 16:00:00'
    """
    # перенос сразу после даты
    text = re.sub(
        r"(\d{1,2}\.\d{1,2}\.\d{4})[ \t]*[\r\n]+[ \t]*(\d{1,2}:\d{2}(?::\d{2})?)",
        r"\1 \2",
        text
    )
    # перенос между цифрами даты (редко, но бывает при кривом pdf)
    text = re.sub(
        r"(\d{1,2}\.\d{1,2})[ \t]*[\r\n]+[ \t]*(\.\d{4})",
        r"\1\2",
        text
    )
    return text


def _find_dt_near_label(text: str, label_patterns: list[str]) -> tuple[str, str] | None:
    """
    Ищет первую дату-время в «окне» после любой из меток (до ~200 символов).
    Возвращает (date, time) либо None.
    """
    for pat in label_patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            tail = text[m.end(): m.end() + 200]  # небольшое «окно» после ярлыка
            mdt = _DT_RE.search(tail)
            if mdt:
                return mdt.group("date"), mdt.group("time")
    return None


def _fallback_two_dts(text: str) -> list[tuple[str, str]]:
    """
    Запасной вариант: берём первые две встреченные «дата+время» во всём документе.
    """
    found = []
    for m in _DT_RE.finditer(text):
        found.append((m.group("date"), m.group("time")))
        if len(found) == 2:
            break
    return found


def cut_tail_company(s: str) -> str:
    """Обрезаем всё после реквизитов, чтобы КА не разрастался."""
    if not s:
        return ""
    s = s.strip()
    s = re.split(r"\b(ИНН|КПП|ОГРН|ОКПО|БИК|р/с|к/с)\b", s, maxsplit=1, flags=re.IGNORECASE)[0]
    return s.strip(" ,;—-")


def split_dt(dt: str) -> Tuple[str, str]:
    """'15.08.2025 16:00:00' (даже с переносом) -> ('15.08.2025','16:00:00')"""
    if not dt:
        return "", ""
    m = re.match(r"\s*(\d{1,2}\.\d{1,2}\.\d{4})\s*(?:\n|\r|\t| )+\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*$", dt)
    if m:
        return m.group(1), m.group(2)
    m2 = re.match(r"\s*(\d{1,2}\.\d{1,2}\.\d{4})\s*$", dt)
    if m2:
        return m2.group(1), ""
    return dt.strip(), ""


# ------------------------ Readers ------------------------

def read_pdf_text(path: str) -> str:
    """Базовое извлечение текста из PDF."""
    try:
        from PyPDF2 import PdfReader
    except Exception as e:
        raise RuntimeError("Установи PyPDF2: pip install PyPDF2") from e

    reader = PdfReader(path)
    pages = []
    for p in reader.pages:
        txt = p.extract_text() or ""
        pages.append(txt)
    return "\n".join(pages)


def read_xlsm_text(path: str) -> str:
    """Склеиваем все видимые ячейки в один текстовый блоб."""
    try:
        import openpyxl
    except Exception as e:
        raise RuntimeError("Установи openpyxl: pip install openpyxl") from e

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True, keep_vba=True)
    chunks: List[str] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for val in row:
                if val is None:
                    continue
                s = str(val).strip()
                if s:
                    chunks.append(s)
    return "\n".join(chunks)


# ------------------------ Extractor ------------------------

# общий datetime (дата и время могут быть на соседних строках)
DATETIME_RX = re.compile(
    r"\b(\d{1,2}\.\d{1,2}\.\d{4})\b(?:[ \t]*[\r\n][ \t]*)?\b(\d{1,2}:\d{2}(?::\d{2})?)\b"
)


def find_dt_after(text: str, anchor_keywords: List[str]) -> tuple[str, str]:
    """
    Ищем первый datetime после ближайшего к началу вхождения любого из anchor_keywords.
    Возвращает (date, time) либо ("","").
    """
    if not text:
        return "", ""
    pos = None
    for kw in anchor_keywords:
        m = re.search(kw, text, re.IGNORECASE)
        if m:
            pos = m.end()
            break
    if pos is None:
        return "", ""
    m = DATETIME_RX.search(text, pos)
    if not m:
        return "", ""
    return m.group(1), m.group(2)


def nearest_datetime_after(text: str, anchors: list[str]) -> tuple[str, str]:
    """
    Берём все datetime в тексте и выбираем тот, что идёт после ближайшего найденного якоря,
    с минимальной дистанцией (match.start - anchor_end).
    """
    if not text:
        return "", ""
    # где заканчивается ближайший к началу якорь
    anchor_pos = None
    for kw in anchors:
        m = re.search(kw, text, re.IGNORECASE)
        if m:
            anchor_pos = m.end()
            break
    if anchor_pos is None:
        return "", ""

    best = None
    for m in DATETIME_RX.finditer(text):
        if m.start() >= anchor_pos:
            dist = m.start() - anchor_pos
            if best is None or dist < best[0]:
                best = (dist, m.group(1), m.group(2))
    return (best[1], best[2]) if best else ("", "")


# Алиасы/шаблоны под твои кейсы
RX = {
    # КА: «Наименование ...», «КА:», «Контрагент:», «Заказчик:»
    "customer_name": re.compile(r"(?:Наименование|Наим\.?)\s*[:\-–]?\s*(?P<name>[^\n\r]+)", re.IGNORECASE),
    "customer": re.compile(r"(?:КА|Контрагент|Заказчик)\s*[:\-–]?\s*(?P<name>[^\n\r]+)", re.IGNORECASE),

    # ФИО водителя
    "driver": re.compile(r"(?:Ф\.?\s*И\.?\s*О\.?\s*водителя|Водитель)\s*[:\-–]?\s*(?P<name>[^\n\r]+)", re.IGNORECASE),

    # ТС длинной строкой
    "vehicle_long": re.compile(
        r"(?:Марка[, ]*номер[^:\n]*тягача[^:\n]*прицепа|Марка.*тягача.*прицепа)\s*[:\-–]?\s*(?P<text>[^\n\r]+)",
        re.IGNORECASE
    ),
    # номера
    "plate_1": re.compile(r"[АВЕКМНОРСТУХ]\s?\d{3}\s?[АВЕКМНОРСТУХ]{2}\s?\d{2,3}", re.IGNORECASE),
    "plate_2": re.compile(r"[АВЕКМНОРСТУХ]{2}\s?\d{4}\s?\d{2,3}", re.IGNORECASE),

    # Адреса
    "load_addr": re.compile(
        r"(?:Факт\.?\s*адрес\s*загрузки|Адрес\s*загрузки|Адрес\s*погрузки|Погрузка)\s*[:\-–]?\s*(?P<addr>.+)",
        re.IGNORECASE
    ),
    "unload_addr": re.compile(
        r"(?:Адрес\s*выгрузки|Адрес\s*разгрузки|Выгрузка)\s*[:\-–]?\s*(?P<addr>.+)",
        re.IGNORECASE
    ),

    # Дата/время: допускаем «ата и время ...» (битая "Д")
    "load_dt": re.compile(
        r"(?:(?:[Дд]ата|ата)\s*и\s*время\s*подачи\s*транспортного\s*средства|"
        r"(?:[Дд]ата|ата)\s*и\s*время\s*погрузки|Время\s*погрузки|Подача\s*ТС)"
        r"(?:[^0-9\n\r]{0,50})"
        r"(?P<dt>\b\d{1,2}\.\d{1,2}\.\d{4}\b(?:[ \t]*\n[ \t]*)?\b\d{1,2}:\d{2}(?::\d{2})?)",
        re.IGNORECASE
    ),

    "unload_dt": re.compile(
        r"(?:(?:[Дд]ата|ата)\s*и\s*время\s*разгрузки\s*транспортного\s*средства(?:\s*в\s*(?P<city>[\w\-\.\s]+))?|"
        r"(?:[Дд]ата|ата)\s*и\s*время\s*выгрузки|Время\s*выгрузки|(?:[Дд]ата|ата)\s*выгрузки)"
        r"(?:[^0-9\n\r]{0,50})"  # <-- допускаем до 50 нецифровых символов перед датой
        r"(?P<dt>\b\d{1,2}\.\d{1,2}\.\d{4}\b(?:[ \t]*\n[ \t]*)?\b\d{1,2}:\d{2}(?::\d{2})?)",
        re.IGNORECASE
    ),

    "date_only": re.compile(r"(\d{1,2}\.\d{1,2}\.\d{4})"),

}


def extract_fields(text: str) -> Dict:
    """
    Нормализуем в формат:
    {
      "ТС": str, "КА": str, "ФИО": str,
      "Погрузка": [{"Погрузка 1": addr, "Дата 1": date, "Время 1": time}],
      "Выгрузка": [{"Выгрузка 1": addr, "Дата 1": date, "Время 1": time}],
      "_debug": {...}
    }
    """
    T = text or ""

    # --- инициализация рабочих переменных (чтобы не ловить NameError) ---
    load_addr: Optional[str] = None
    load_dt: Optional[str] = None
    unload_addr: Optional[str] = None
    unload_dt: Optional[str] = None
    unload_city: Optional[str] = None
    d_f = t_f = ""  # fallback для погрузки
    d_f2 = t_f2 = ""  # fallback для выгрузки

    result = {
        "ТС": "",
        "КА": "",
        "ФИО": "",
        "Погрузка": [],
        "Выгрузка": [],
        "_debug": {},
    }

    # --- КА ---
    name = ""
    m = RX["customer_name"].search(T)
    if m:
        name = clean_text(m.group("name"))
    else:
        m = RX["customer"].search(T)
        if m:
            name = clean_text(m.group("name"))
    result["КА"] = cut_tail_company(name)

    # --- Водитель ---
    if m := RX["driver"].search(T):
        result["ФИО"] = clean_text(m.group("name"))

    # --- ТС ---
    if m := RX["vehicle_long"].search(T):
        result["ТС"] = clean_text(m.group("text"))
    else:
        plates = set()
        for rx in ("plate_1", "plate_2"):
            for m2 in RX[rx].finditer(T):
                plates.add(clean_text(m2.group(0)))
        if plates:
            result["ТС"] = "; ".join(sorted(plates))

    # --- Погрузка: адрес/дата-время ---
    if m := RX["load_addr"].search(T):
        load_addr = clean_text(m.group("addr"))

    if m := RX["load_dt"].search(T):
        load_dt = clean_text(m.group("dt"))

    # fallback: первый datetime после якорей
    # fallback: ближайший datetime после якорей
    if not load_dt:
        d_f, t_f = nearest_datetime_after(T, ["подач", "погруз", "загруз"])

    if load_addr or load_dt or (d_f and t_f):
        d, t = (d_f, t_f) if (d_f and t_f) else split_dt(load_dt or "")
        result["Погрузка"].append({
            "Погрузка 1": load_addr or "",
            "Дата 1": d or "",
            "Время 1": t or "",
        })

    # --- Выгрузка: адрес/дата-время ---
    if m := RX["unload_addr"].search(T):
        unload_addr = clean_text(m.group("addr"))

    if m := RX["unload_dt"].search(T):
        unload_dt = clean_text(m.group("dt"))
        unload_city = (m.groupdict() or {}).get("city")
        if unload_city:
            unload_city = clean_text(unload_city)

    if not unload_dt and "срок доставки" in T.lower():
        m = RX["date_only"].search(T)
        if m:
            unload_dt = m.group(1)

    if not unload_dt:
        d_f2, t_f2 = nearest_datetime_after(T, ["разгруз", "выгруз", "доставк", "в Воронеж", "Воронеж"])

    if unload_addr or unload_dt or unload_city or (d_f2 and t_f2):
        d, t = (d_f2, t_f2) if (d_f2 and t_f2) else split_dt(unload_dt or "")
        addr = unload_addr or ""
        if not addr and unload_city:
            addr = unload_city
        result["Выгрузка"].append({
            "Выгрузка 1": addr,
            "Дата 1": d or "",
            "Время 1": t or "",
        })

    # --- debug-флаги
    # DEBUG-подсветка найденных дат
    result["_debug"]["found_load_dt"] = load_dt or (d_f and t_f and f"{d_f} {t_f}") or ""
    result["_debug"]["found_unload_dt"] = unload_dt or (d_f2 and t_f2 and f"{d_f2} {t_f2}") or ""

    return result


# ------------------------ Runner ------------------------

def detect_and_read(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")
    if p.suffix.lower() == ".pdf":
        return read_pdf_text(str(p))
    if p.suffix.lower() == ".xlsm":
        return read_xlsm_text(str(p))
    raise ValueError("Поддерживаются только .pdf и .xlsm")


def _fmt_block(kind: str, data: dict) -> str:
    arr = data.get(kind) or []
    if not arr:
        return ""
    x = arr[0]
    key = "Погрузка 1" if kind == "Погрузка" else "Выгрузка 1"
    return f"{x.get('Дата 1', '')} {x.get('Время 1', '')} | {x.get(key, '')}".strip()


def main():
    path = TEST_PATH
    print(f"\n[INFO] Парсим файл: {path}\n")

    try:
        raw = detect_and_read(path)
        norm = normalize_for_datetime(raw)
    except Exception as e:
        print(f"[ERROR] Не удалось прочитать файл: {e}")
        return

    bad_ratio = raw.count("�") / max(len(raw), 1)
    if bad_ratio > 0.02:
        print("[WARN] Похоже, текст PDF кодирован некорректно (много �). Возможны пропуски дат/символов.")

    data = extract_fields(norm)

    print("\n--- JSON ---")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    print("\nИТОГО:")
    print(f"  КА: {data.get('КА', '')}")
    print(f"  ТС: {data.get('ТС', '')}")
    print(f"  Водитель: {data.get('ФИО', '')}")
    print(f"  Погрузка: {_fmt_block('Погрузка', data)}")
    print(f"  Выгрузка: {_fmt_block('Выгрузка', data)}")


if __name__ == "__main__":
    main()
