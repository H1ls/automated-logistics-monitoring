import os
import re
from datetime import datetime
from typing import List, Dict, Any

from Navigation_Bot.core.repositories.vehicle_registry_fields import compact_vehicle_key
from Navigation_Bot.core.logging import normalize_log_func

"""2. Очистка данных"""


class DataCleaner:
    def __init__(self, task_repository=None,
                 id_context=None,
                 log_func=print):

        self.log = normalize_log_func(log_func)

        if task_repository is None:
            raise RuntimeError("DataCleaner requires task_repository")
        if id_context is None:
            raise RuntimeError("DataCleaner requires vehicle repository")

        self.task_repository = task_repository
        self.vehicle_repository = id_context

        self.task_rows: List[Dict[str, Any]] = self.task_repository.get() or []
        self.vehicle_lookup: dict[str, dict] = self.vehicle_repository.registry_lookup()

        self.date_re = re.compile(r"\b(?:[0-3]?\d\.(?:0?[1-9]|1[0-2])(?:\.\d{2,4})?|[0-3]?\d/(?:0?[1-9]|1[0-2])/\d{2,4})\b")
        self.time_re = re.compile(r"\b([0-2]?\d[:\-][0-5]\d(?::[0-5]\d)?)\b")
        self.numbered_re = re.compile(r"(?<![\wА-Яа-я/])(\d{1,2})[).]\s*")

        self.comment_start_re = re.compile(r"\b(?:Расположение|координаты|Контрагент|Контактное\s+лицо|Комментарий|"
                                           r"Оператор\s+склада|Диспетчер|кладовщики|логисты|ориентир|номер\s+склада|заезд\s+с[о]?)\b\s*:?"
                                           r"|[+78][\d\s()\-]{8,}"
                                           r"|\b(?:тел|моб|раб)\.?\s*:?",
                                           re.IGNORECASE, )

        self.address_start_re = re.compile(r"\b(?:Россия|РФ|МО|Москва|Санкт-Петербург|"
                                           r"[А-ЯЁ][а-яё-]+(?:ская|ский|ское|ая|ий|ой)\s+"
                                           r"(?:обл\.?|область|край|респ\.?|республика|р-н|район|АО)|"
                                           r"[А-ЯЁ][а-яё-]+\s+Респ\.?|"
                                           r"[А-ЯЁ][а-яё-]+\s+городской\s+округ|"
                                           r"г\.?\s*[А-ЯЁа-яё]|город\s+[А-ЯЁа-яё]|"
                                           r"ул\.?\s*[А-ЯЁа-яё]|ш\.?\s*[А-ЯЁа-яё]|"
                                           r"пер\.?\s*[А-ЯЁа-яё]|пр-д\s+[А-ЯЁа-яё]|"
                                           r"п\.?\s*[А-ЯЁа-яё]|пос\.?\s*[А-ЯЁа-яё]|поселок\s+[А-ЯЁа-яё]|"
                                           r"вл\.?\s*\d|владение\s+\d|"
                                           r"с\.?\s*[А-ЯЁа-яё]|д\.?\s*[А-ЯЁа-яё])",
                                           re.IGNORECASE,
                                           )

        self.end_patterns = [r"тел\.?\s*[:.]?\s*\+?\d[\d\s()\-]{8,}",
                             r"моб\.?\s*[:.]?\s*\+?\d[\d\s()\-]{8,}",
                             r"раб\.?\s*[:.]?\s*\+?\d[\d\s()\-]{8,}",
                             r"Контакт:?\s*\+?\d[\d\s()\-]{8,}",
                             r"\sГП\s",
                             r"\sООО\s",
                             r"\(Согласт\s",
                             r"ТТН\s",
                             r"\bГО\b",
                             r"\bтел\.?\s",
                             r"\bООО\b",
                             r"\bПАО\b",
                             r"\bКонтрагент\b",
                             r"\bпо\s+ттн\b", ]

    def _file_exists(self, filepath):
        if not os.path.exists(filepath):
            self.log(f"Файл {filepath} не найден.")
            return False
        return True

    def _parse_info(self, text: str, prefix: str) -> list[dict]:

        if not isinstance(text, str) or not text.strip():
            return []

        normalized = self._normalize_route_text(text)
        points, comments = self._parse_date_anchored_points(normalized, prefix)

        if not points:
            points, comments = self._parse_numbered_points(normalized, prefix)

        if not points:
            address, extra_comments = self._clean_address_parts(self._strip_route_label(normalized))
            comments.extend(extra_comments)
            if address:
                points = [self._make_point(prefix, 1, address, "Не указано", "Не указано")]

        if comments:
            comment = "\n".join(dict.fromkeys(c for c in comments if c))
            if comment:
                points.append({"Комментарий": comment})

        return points

    def _normalize_route_text(self, text: str) -> str:
        text = text.replace("\ufeff", " ").replace("\u200b", " ").replace("\xa0", " ")
        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text.strip(" \n\t|")

    def _strip_route_label(self, text: str) -> str:
        text = re.sub(r"^\s*#+\s*", "", text)
        text = re.sub(r"\b(Загрузка|Погрузка|Разгрузка|Выгрузка|Выгрузки)\s*:?", " ", text,
                      flags=re.IGNORECASE)
        return text.strip(" ,;|\n\t")

    def _parse_date_anchored_points(self, text: str, prefix: str) -> tuple[list[dict], list[str]]:
        matches = list(self.date_re.finditer(text))
        if not matches:
            return [], []

        points: list[dict] = []
        comments: list[str] = []

        raw_first_prefix = self._strip_route_label(text[:matches[0].start()])
        first_prefix_is_address = bool(raw_first_prefix and self.address_start_re.search(raw_first_prefix))
        first_prefix_time = list(self.time_re.finditer(raw_first_prefix))
        first_prefix = self._clean_comment(raw_first_prefix)
        if first_prefix and not first_prefix_is_address and not first_prefix_time:
            comments.append(first_prefix)

        for match_index, match in enumerate(matches):
            start = match.start()
            if match_index == 0:
                if first_prefix_is_address:
                    start = 0
                elif first_prefix_time:
                    start = first_prefix_time[-1].start()
            end = matches[match_index + 1].start() if match_index + 1 < len(matches) else len(text)
            segment = text[start:end]
            date = self._normalize_date(match.group(0))
            time, address = self._extract_datetime_from_segment(segment, match.group(0))
            address = self._strip_route_label(address)

            numbered_addresses, intro = self._split_numbered_sections(address)
            if len(numbered_addresses) > 1:
                if intro and self._looks_like_point(intro):
                    numbered_addresses.insert(0, intro)
                elif intro:
                    comments.append(self._clean_comment(intro))
                for address_part in numbered_addresses:
                    cleaned, extra_comments = self._clean_address_parts(address_part)
                    comments.extend(extra_comments)
                    if cleaned:
                        points.append(self._make_point(prefix, len(points) + 1, cleaned, date, time))
                continue

            cleaned, extra_comments = self._clean_address_parts(address)
            comments.extend(extra_comments)
            if cleaned:
                points.append(self._make_point(prefix, len(points) + 1, cleaned, date, time))

        return points, comments

    def _parse_numbered_points(self, text: str, prefix: str) -> tuple[list[dict], list[str]]:
        body = self._strip_route_label(text)
        sections, intro = self._split_numbered_sections(body)
        comments: list[str] = []
        points: list[dict] = []

        if intro and self._looks_like_point(intro):
            sections.insert(0, intro)
        elif intro:
            comments.append(self._clean_comment(intro))

        for section in sections:
            date = "Не указано"
            time = "Не указано"
            date_match = self.date_re.search(section)
            if date_match:
                date = self._normalize_date(date_match.group(0))
                time, section = self._extract_datetime_from_segment(section[date_match.start():],
                                                                    date_match.group(0))
            else:
                time_match = self.time_re.search(section)
                if time_match:
                    time = self._normalize_time(time_match.group(1))
                    section = section.replace(time_match.group(0), " ", 1)

            cleaned, extra_comments = self._clean_address_parts(section)
            comments.extend(extra_comments)
            if cleaned:
                points.append(self._make_point(prefix, len(points) + 1, cleaned, date, time))

        return points, comments

    def _split_numbered_sections(self, text: str) -> tuple[list[str], str]:
        matches = list(self.numbered_re.finditer(text))
        if not matches:
            return [], text.strip(" ,;|\n\t")

        intro = text[:matches[0].start()].strip(" ,;|\n\t")
        sections: list[str] = []
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section = text[start:end].strip(" ,;|\n\t")
            if section:
                sections.append(section)
        return sections, intro

    def _extract_datetime_from_segment(self, segment: str, date_token: str) -> tuple[str, str]:
        date_match = re.search(re.escape(date_token), segment)
        if not date_match:
            return "Не указано", segment

        before = segment[:date_match.start()]
        after = segment[date_match.end():]
        time = "Не указано"

        before_times = list(self.time_re.finditer(before))
        if before_times:
            time = self._normalize_time(before_times[-1].group(1))
            before = before[:before_times[-1].start()] + " " + before[before_times[-1].end():]
        else:
            after_time = re.match(r"\s*,?\s*(?:прибыть\s+(?:к|до)|в|к|до)?\s*,?\s*"
                                  r"([0-2]?\d[:\-][0-5]\d(?::[0-5]\d)?)",
                                  after,
                                  flags=re.IGNORECASE)
            if after_time:
                time = self._normalize_time(after_time.group(1))
                after = after[after_time.end():]

        address = f"{before} {after}"
        return time, address

    def _normalize_time(self, value: str) -> str:
        value = value.replace("-", ":").strip()
        parts = value.split(":")
        if len(parts) < 2:
            return value
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    def _normalize_date(self, value: str) -> str:
        parts = re.split(r"[./]", value)
        if len(parts) < 2:
            return value

        day = int(parts[0])
        month = int(parts[1])
        if len(parts) >= 3 and parts[2]:
            year = int(parts[2])
            if year < 100:
                year += 2000
        else:
            year = datetime.now().year

        return f"{day:02d}.{month:02d}.{year:04d}"

    def _looks_like_point(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        if self.date_re.search(text) or self.time_re.search(text):
            return True
        return not re.search(r"\b\d+\s*точ", text, flags=re.IGNORECASE)

    def _clean_comment(self, text: str) -> str:
        text = self._strip_route_label(text)
        text = re.sub(r"^\s*\d{1,2}[).]\s*$", "", text)
        text = re.sub(r"\b\d+\s*точк[аи]?\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"[-–—]{2,}.*$", "", text).strip(" ,;|\n\t")
        return text

    def _clean_address_parts(self, addr: str) -> tuple[str, list[str]]:
        comments: list[str] = []
        addr = self._normalize_route_text(addr)
        addr = self._strip_route_label(addr)
        addr = self._normalize_service_phrases(addr)
        addr, inline_comments = self._extract_inline_comments(addr)
        comments.extend(inline_comments)

        addr = re.sub(r"\bприбыть\s+(к|до)\b\s*,?\s*", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\((?:время\s+местное|мск\s*[+-]\s*\d+)\)", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\bМСК\b", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\bтранзит(?:ное\s+время)?\s*[\d.,]+ ?(?:часа|часов|ч)?!?", " ", addr,
                      flags=re.IGNORECASE)
        addr = re.sub(r"\bПрогнозируемое\s+время\s+ПРР\b", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\bРасстояние\s+не\s+задано\b", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\s*-\s*\d+\s*ч\b", " ", addr, flags=re.IGNORECASE)

        for p in self.end_patterns:
            end = re.search(p, addr, flags=re.IGNORECASE)
            if end:
                comment = addr[end.start():].strip(" ,;|\n\t")
                if comment:
                    comments.append(comment)
                addr = addr[: end.start()].strip()
                break

        addr = re.sub(r"[-–—]{2,}.*$", "", addr)
        addr = re.sub(r"\s*\|\s*", "\n", addr)
        addr = self._normalize_address_tail(addr)
        addr = re.sub(r"[ \t]+", " ", addr)
        addr = re.sub(r"\n\s*\n+", "\n", addr)
        return addr.strip(" ,;|\n\t"), [c for c in comments if c]

    def _normalize_service_phrases(self, addr: str) -> str:
        addr = re.sub(r"\bпо\s+ТТН\b\s*,?", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\bпо\s+звонку\b\s*", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\bМ/?О\b", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\bадрес\s*-\s*", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\s+", " ", addr)
        return addr.strip()

    def _normalize_address_tail(self, addr: str) -> str:
        addr = re.sub(r"\b([А-ЯЁ][а-яё-]+)\s+г\.?,?\s*г\.?\s*\1\b", r"г.\1", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\b([А-ЯЁ][а-яё-]+)\s+г\.?\s+г\.?\s*\1\b", r"г.\1", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\b([А-ЯЁ][а-яё-]+)\s+г,?\s+(ул\.?)", r"\1 \2", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\s+\.", ".", addr)
        return addr.rstrip(".")

    def _extract_inline_comments(self, addr: str) -> tuple[str, list[str]]:
        comments: list[str] = []

        local_time = re.search(r"\((?:время\s+местное|мск\s*[+-]\s*\d+)\)", addr, flags=re.IGNORECASE)
        if local_time:
            comments.append(local_time.group(0))
            addr = addr[:local_time.start()] + " " + addr[local_time.end():]

        address_start = self.address_start_re.search(addr)
        if address_start and address_start.start() > 0:
            prefix = addr[:address_start.start()].strip(" ,;|\n\t")
            city_prefix = re.match(r"^[А-ЯЁ][А-ЯЁа-яё-]+(?:\s+г\.?)?$", prefix, flags=re.IGNORECASE)
            if prefix and not city_prefix and not self.date_re.search(prefix):
                comments.append(prefix)
                addr = addr[address_start.start():]

        marker = self.comment_start_re.search(addr)
        if marker:
            comment_start = marker.start()
            if comment_start > 0 and addr[comment_start - 1] == "(" and ")" in addr[comment_start:]:
                comment_start -= 1
            else:
                contact_prefix = re.search(r",\s*([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?\s*/\s*)$", addr[:comment_start])
                if contact_prefix:
                    comment_start = contact_prefix.start(1)
                else:
                    contact_prefix = re.search(r"\s([А-ЯЁ][а-яё]+\s*/\s*)$", addr[:comment_start])
                    if contact_prefix:
                        comment_start = contact_prefix.start(1)
            comment = addr[comment_start:].strip(" ,;|\n\t")
            if comment:
                comments.append(comment)
            addr = addr[:comment_start]

        return addr, comments

    def _clean_address(self, addr: str) -> str:
        cleaned, _ = self._clean_address_parts(addr)
        return cleaned

    @staticmethod
    def _make_point(prefix: str, index: int, address: str, date: str, time: str) -> dict:
        return {f"{prefix} {index}": address,
                f"Дата {index}": date,
                f"Время {index}": time}

    def start_clean(self, only_indexes: set[int] | None = None) -> None:
        """
        1) Один раз сохраняем сырые строки в raw_load / raw_unload (для ML)
        2) Преобразуем строки Погрузка/Выгрузка → список блоков
        3) Чистим поле 'ТС'
        4) Привязываем Wialon ID из таблицы vehicles
        5) Сохраняем через TaskRepository
        """
        # актуальные данные и id-справочник
        self.task_rows = self.task_repository.get() or []
        self.vehicle_lookup = self.vehicle_repository.registry_lookup()

        for item in self.task_rows:
            if only_indexes is not None and item.get("index") not in only_indexes:
                continue
            #  RAW для ML
            if isinstance(item.get("Погрузка"), str) and not item.get("raw_load"):
                item["raw_load"] = item["Погрузка"]

            if isinstance(item.get("Выгрузка"), str) and not item.get("raw_unload"):
                item["raw_unload"] = item["Выгрузка"]

            #  Парсинг в структурированный вид
            if isinstance(item.get("Погрузка"), str):
                item["Погрузка"] = self._parse_info(item["Погрузка"], "Погрузка")

            if isinstance(item.get("Выгрузка"), str):
                item["Выгрузка"] = self._parse_info(item["Выгрузка"], "Выгрузка")

            if not item.get("Погрузка") or not item.get("Выгрузка"):
                self.log(f"⚠️ Пропущена запись {item.get('ТС')} — пустая Погрузка или Выгрузка.")

        self._clean_vehicle_names()
        self._add_id_to_data()

        self.task_repository.set(self.task_rows, source="cleaner")

    def _clean_vehicle_names(self) -> None:
        """Оставляем в 'ТС' только номер (без телефона и переносов)."""
        for row in self.task_rows:
            ts = row.get("ТС", "")
            if isinstance(ts, str) and "\n" in ts:
                row["ТС"] = ts.split("\n", 1)[0].strip()

    def _add_id_to_data(self) -> None:
        """
        Привязка ID к ТС:
          - ключ по справочнику vehicles: monitoring_name/plate_number без пробелов
          - ключ по данным: 'ТС' без пробелов (и без телефона)
        """
        for row in self.task_rows:
            ts = row.get("ТС", "")
            if not isinstance(ts, str) or not ts:
                continue
            ts_clean = ts.split("\n", 1)[0].strip()
            key = compact_vehicle_key(ts_clean)
            found = self._find_vehicle_by_key(key)
            if found is not None:
                row["id"] = found["monitoring_id"]
                if found.get("plate_number"):
                    row["ТС"] = found["plate_number"]
            else:
                self.log(f"❌ Не найден ID для ТС: {ts_clean}")

    def _find_vehicle_by_key(self, key: str) -> dict | None:
        found = self.vehicle_lookup.get(key)
        if found is not None:
            return found

        # Если телефон был склеен с ТС, регион вида 750 может быть разобран как 75.
        # В справочнике такие машины хранятся с полным трехзначным регионом.
        if re.match(r"^[А-ЯЁA-Z]\d{3}[А-ЯЁA-Z]{2}\d{2}$", key):
            return self.vehicle_lookup.get(f"{key}0")

        return None
