#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import pandas as pd
import json
from pathlib import Path
import sys
from datetime import datetime


def clean_fragment(fragment: str) -> str:

    phone_re = re.compile(r'\+?\d[\d\-\s\(\)]{6,}\d')
    trunc_re = re.compile(
        r'(?:тел\.?|контрагент|контакт|комментарий|обязательно|круглосуточно|по ТТН|загрузк|въезд|ГО\b|ООО\b)',
        re.IGNORECASE
    )
    s = fragment.strip()
    s = re.sub(r'\([^)]*\)', '', s)       # удаляем координаты
    s = phone_re.sub('', s)                 # удаляем телефон
    m = trunc_re.search(s)
    if m:
        s = s[:m.start()]
    s = re.sub(r'^\s*\d+[\.\)]\s*', '', s)
    return s.rstrip(" .,:;-—").strip()


def parse_all(text: str) -> list[dict]:

    date_re   = re.compile(r'(\d{1,2}[./]\d{1,2}(?:[./]\d{4})?)')
    time_re   = re.compile(r'(\d{1,2}[:\.]\d{2}(?::\d{2})?)')
    region_re = re.compile(r'\b(?:обл|респ|край|г\.?|пос\.?|р-?н|ул\.?|ш\.?|п\.?|пр-?т)\b', re.IGNORECASE)
    phone_re  = re.compile(r'\+?\d[\d\-\s\(\)]{6,}\d')

    def parse_fragment(frag_text: str) -> dict:
        # урезаем все до даты
        dm = date_re.search(frag_text)
        if dm:
            # срезаем префикс
            frag_text = frag_text[dm.start():]
            ds = dm.group(1).replace('/', '.')
            if ds.count('.') == 1:
                ds = f"{ds}.{datetime.now().year}"
            date = ds
            pos = dm.end() - dm.start()
        else:
            date = "Не указано"
            pos = 0

        # время
        tm = time_re.search(frag_text, pos)
        if tm:
            ts = tm.group(1).replace('.', ':')
            time = ts
            pos = tm.end()
        else:
            time = "Не указано"

        # ищем адрес: следующая строка после позиции pos, содержащая регион
        tail = frag_text[pos:].splitlines()
        for ln in tail:
            s = ln.strip()
            if not s:
                continue
            if phone_re.search(s):
                continue
            if region_re.search(s):
                return {"Дата": date, "Время": time, "Адрес": clean_fragment(s)}
        return {"Дата": date, "Время": time, "Адрес": "Не указано"}

    # разбиваем на части по номерам записей только в начале строки
    parts = re.split(r'(?:^|\n)\s*\d+\s*[)\.]\s*', text)
    # первый элемент — префикс до первой записи, если он не содержит дату, игнорируем
    fragments = []
    if len(parts) > 1:
        # каждый subsequent part содержит фрагмент записи
        for frag in parts[1:]:
            if frag.strip():
                fragments.append(frag)
    else:
        fragments = [text]

    results = []
    for frag in fragments:
        rec = parse_fragment(frag)
        if rec["Адрес"] != "Не указано":
            results.append(rec)
    return results


def read_excel_auto(
    filepath: str,
    sheet_name: str | int | None = None,
    header: int | list[int] | None = None,
    names: list[str] | None = None
) -> pd.DataFrame:
    ext = Path(filepath).suffix.lower()
    engine = 'xlrd' if ext == '.xls' else 'openpyxl'
    try:
        return pd.read_excel(
            io=filepath,
            sheet_name=sheet_name,
            header=header,
            names=names,
            engine=engine
        )
    except ImportError:
        print(f"Ошибка: установите движок для {ext}-файлов: pip install {engine}", file=sys.stderr)
        sys.exit(1)


def main():
    input_file = 'Адреса.xls'
    df = read_excel_auto(
        filepath=input_file,
        sheet_name='raw_text',
        header=None,
        names=['raw_text']
    )
    df['parsed_deliveries'] = df['raw_text'].astype(str).apply(parse_all)

    for idx, recs in df['parsed_deliveries'].iloc[:5].items():
        print(f'=== Строка {idx + 1} ===')
        if recs:
            for e in recs:
                print(f"  Дата: {e['Дата']}; Время: {e['Время']}; Адрес: {e['Адрес']}")
        else:
            print("  (нет записей)")
        print()

    with open('parsed_deliveries.json', 'w', encoding='utf-8') as f:
        json.dump(df.to_dict(orient='records'), f, ensure_ascii=False, indent=2)

    print(f'Готово! Обработано строк: {len(df)}. Результаты в parsed_deliveries.json')

if __name__ == '__main__':
    main()