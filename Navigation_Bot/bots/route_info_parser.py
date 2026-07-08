import re
from datetime import datetime

NOT_SPECIFIED = "Не указано"
COMMENT_KEY = "Комментарий"
DATE_KEY = "Дата"
TIME_KEY = "Время"

DATE_RE = re.compile(r"\b(?:[0-3]?\d\.(?:0?[1-9]|1[0-2])(?:\.\d{2,4})?|"
                     r"[0-3]?\d/(?:0?[1-9]|1[0-2])/\d{2,4})\b")

TIME_RE = re.compile(r"\b([0-2]?\d[:\-][0-5]\d(?::[0-5]\d)?)\b")
NUMBERED_RE = re.compile(r"(?<![\wА-Яа-я/:])(\d{1,2})[).]\s*")
ROUTE_LABEL_RE = re.compile(r"\b(Загрузка|Погрузка|Разгрузка|азгрузка|Выгрузка|Выгрузки)\s*:?", flags=re.IGNORECASE)
INLINE_ROUTE_LABEL_RE = re.compile(
    r"\b(?:Загрузка|Погрузка|Разгрузка|Выгрузка|Выгрузки)\s*:?\s*(\d{1,2})\s*:?",
    flags=re.IGNORECASE,
)
AFTER_DATE_TIME_RE = re.compile(r"\s*,?\s*(?:прибыть\s+(?:к|до)|в|к|до)?\s*,?\s*"
                                r"([0-2]?\d[:\-][0-5]\d(?::[0-5]\d)?)", flags=re.IGNORECASE)
AFTER_DATE_TIME_RANGE_RE = re.compile(
    r"\s*,?\s*([0-2]?\d[:\-][0-5]\d)\s+до\s+([0-2]?\d[:\-][0-5]\d)",
    flags=re.IGNORECASE,
)

COMMENT_START_RE = re.compile(r"\b(?:Расположение|координаты|Контрагент|Контактное\s+лицо|Комментарий|"
                              r"Оператор\s+склада|Диспетчер|кладовщики|логисты|ориентир|номер\s+склада|"
                              r"заезд\s+с[о]?|кад\.\s*номер|ВЪЕЗД|В\s+НАВИГАТОР)\b\s*:?"
                              r"|\b(?:Операторы?|Склад|Логист|Рук\.филиала)\s*:"
                              r"|[+78][\d\s()\-]{8,}"
                              r"|\b(?:тел|моб|раб)\.?\s*:?", flags=re.IGNORECASE)
ADDRESS_START_RE = re.compile(
    r"\b(?:Россия|РФ|\bМО\b|Москва|Санкт-Петербург|"
    r"[А-ЯЁ][а-яё-]+(?:ская|ский|ское|ая|ий|ой)\s+"
    r"(?:обл\.?|область|край|респ\.?|республика|р-н|район|АО)|"
    r"[А-ЯЁ][а-яё-]+\s+Респ\.?|"
    r"[А-ЯЁ][а-яё-]+\s+городской\s+округ|"
    r"г\.\s*[А-ЯЁа-яё]|город\s+[А-ЯЁа-яё]|"
    r"ул\.\s*[А-ЯЁа-яё]|ш\.\s*[А-ЯЁа-яё]|"
    r"пер\.\s*[А-ЯЁа-яё]|пр-д\s+[А-ЯЁа-яё]|"
    r"п\.\s*[А-ЯЁа-яё]|пос\.\s*[А-ЯЁа-яё]|поселок\s+[А-ЯЁа-яё]|"
    r"вл\.?\s*\d|владение\s+\d|"
    r"с\.\s*[А-ЯЁа-яё]|село\s+[А-ЯЁа-яё]|д\.\s*[А-ЯЁа-яё])",
    flags=re.IGNORECASE)

END_COMMENT_PATTERNS = (
    r"тел\.?\s*[:.]?\s*\+?\d[\d\s()\-]{8,}",
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
    r"\bЛогист\s*:",
    r"\bСклад\s*:",
    r"\bОператоры\s*:",
    r"\bпо\s+ттн\b")
SERVICE_PHRASE_PATTERNS = (
    r"\bприбыть\s+(к|до)\b\s*,?\s*",
    r"\((?:время\s+местное|мск\s*[+-]\s*\d+)\)",
    r"\bМСК\b",
    r"\bтранзит(?:ное\s+время)?\s*[\d.,]+ ?(?:часа|часов|ч)?!?",
    r"\bПрогнозируемое\s+время\s+ПРР\b",
    r"\bРасстояние\s+не\s+задано\b",
    r"\s*-\s*\d+\s*ч\b",
)
SERVICE_NORMALIZATION_PATTERNS = (
    (r"\bпо\s+ТТН\b\s*,?", " "),
    (r"\bпо\s+звонку\b\s*", " "),
    (r"\bМ/?О\b", " "),
    (r"\bадрес\s*-\s*", " "),
    (r"\s+", " "),
)
ADDRESS_TAIL_PATTERNS = (
    (r"\b([А-ЯЁ][а-яё-]+)\s+г\.?,?\s*г\.?\s*\1\b", r"г.\1"),
    (r"\b([А-ЯЁ][а-яё-]+)\s+г\.?\s+г\.?\s*\1\b", r"г.\1"),
    (r"\b([А-ЯЁ][а-яё-]+)\s+г,?\s+(ул\.?)", r"\1 \2"),
    (r"\s+\.", "."),
)


class RouteInfoParser:
    def parse(self, text: str, prefix: str) -> list[dict]:
        if not isinstance(text, str) or not text.strip():
            return []

        normalized = self._normalize_route_text(text)
        points, comments = self._parse_inline_route_sections(normalized, prefix)
        if points:
            self._append_comment_block(points, comments)
            return points

        points, comments = self._parse_date_anchored_points(normalized, prefix)

        if not points:
            points, comments = self._parse_numbered_points(normalized, prefix)

        if not points:
            self._append_cleaned_point(
                points,
                comments,
                self._strip_route_label(normalized),
                prefix,
                NOT_SPECIFIED,
                NOT_SPECIFIED,
            )

        self._append_comment_block(points, comments)
        return points

    def clean_address(self, addr: str) -> str:
        cleaned, _ = self._clean_address_parts(addr)
        return cleaned

    def _parse_date_anchored_points(self, text: str, prefix: str) -> tuple[list[dict], list[str]]:
        matches = self._point_date_matches(text)
        if not matches:
            return [], []

        points: list[dict] = []
        comments: list[str] = []
        first_prefix_start = self._date_point_start(text, matches[0])

        raw_first_prefix = self._strip_route_label(text[:matches[0].start()])
        first_prefix = self._clean_comment(raw_first_prefix)
        if first_prefix and first_prefix_start == matches[0].start():
            comments.append(first_prefix)

        for index, match in enumerate(matches):
            start = first_prefix_start if index == 0 else match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            segment = text[start:end]
            date = self._normalize_date(match.group(0))
            time, address = self._extract_datetime_from_segment(segment, match.group(0))

            self._append_segment_points(points, comments, self._strip_route_label(address), prefix, date, time)

        return points, comments

    def _parse_inline_route_sections(self, text: str, prefix: str) -> tuple[list[dict], list[str]]:
        matches = list(INLINE_ROUTE_LABEL_RE.finditer(text))
        if len(matches) < 2:
            return [], []

        points: list[dict] = []
        section_comments: list[str] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            section = text[start:end].strip(" ,;|\n\t")
            point, comments = self._parse_single_inline_section(section, prefix)
            if point:
                points.append(self._renumber_point(point, prefix, len(points) + 1))
            if comments:
                section_number = match.group(1)
                text = " ".join(comment for comment in comments if comment.strip(" )("))
                if text:
                    section_comments.append(f"{section_number}: {text}")

        return points, section_comments

    @staticmethod
    def _renumber_point(point: dict, prefix: str, index: int) -> dict:
        old_address_key = next((key for key in point if key.startswith(f"{prefix} ")), None)
        if not old_address_key:
            return point

        old_index = old_address_key.rsplit(" ", 1)[-1]
        return {
            f"{prefix} {index}": point.get(old_address_key),
            f"{DATE_KEY} {index}": point.get(f"{DATE_KEY} {old_index}"),
            f"{TIME_KEY} {index}": point.get(f"{TIME_KEY} {old_index}"),
        }

    def _parse_single_inline_section(self, section: str, prefix: str) -> tuple[dict | None, list[str]]:
        date_match = self._last_point_date_match(section)
        if not date_match:
            address, comments = self._clean_address_parts(section)
            if not address:
                return None, comments
            return self._make_point(prefix, 1, address, NOT_SPECIFIED, NOT_SPECIFIED), comments

        date = self._normalize_date(date_match.group(0))
        time, address = self._extract_datetime_from_segment(section, date_match.group(0))
        address, comments = self._clean_address_parts(address)
        if not address:
            return None, comments
        return self._make_point(prefix, 1, address, date, time), comments

    def _point_date_matches(self, text: str) -> list[re.Match]:
        return [match for match in DATE_RE.finditer(text) if self._is_point_date(text, match)]

    def _last_point_date_match(self, text: str) -> re.Match | None:
        matches = self._point_date_matches(text)
        return matches[-1] if matches else None

    @staticmethod
    def _is_point_date(text: str, match: re.Match) -> bool:
        prefix = text[max(0, match.start() - 24):match.start()].lower()
        if re.search(r"\bдо\s+[0-2]?\d[:\-][0-5]\d\s*$", prefix, flags=re.IGNORECASE):
            return False

        open_paren = text.rfind("(", 0, match.start())
        close_paren = text.rfind(")", 0, match.start())
        if open_paren > close_paren:
            return False

        return True

    def _parse_numbered_points(self, text: str, prefix: str) -> tuple[list[dict], list[str]]:
        sections, intro = self._split_numbered_sections(self._strip_route_label(text))
        comments: list[str] = []
        points: list[dict] = []

        if intro and self._looks_like_point(intro):
            sections.insert(0, intro)
        elif intro:
            comments.append(self._clean_comment(intro))

        for section in sections:
            date, time, address = self._extract_optional_datetime(section)
            self._append_cleaned_point(points, comments, address, prefix, date, time)

        return points, comments

    def _date_point_start(self, text: str, first_date_match: re.Match) -> int:
        raw_prefix = self._strip_route_label(text[:first_date_match.start()])
        if raw_prefix and ADDRESS_START_RE.search(raw_prefix):
            return 0

        prefix_times = list(TIME_RE.finditer(raw_prefix))
        if prefix_times:
            return prefix_times[-1].start()

        return first_date_match.start()

    def _append_segment_points(self, points: list[dict], comments: list[str], address: str,
                               prefix: str, date: str, time: str) -> None:
        sections, intro = self._split_numbered_sections(address)
        if len(sections) <= 1:
            self._append_cleaned_point(points, comments, address, prefix, date, time)
            return

        if intro and self._looks_like_point(intro):
            sections.insert(0, intro)
        elif intro:
            comments.append(self._clean_comment(intro))

        for section in sections:
            self._append_cleaned_point(points, comments, section, prefix, date, time)

    def _append_cleaned_point(self, points: list[dict], comments: list[str], raw_address: str,
                              prefix: str, date: str, time: str) -> None:
        address, extra_comments = self._clean_address_parts(raw_address)
        comments.extend(extra_comments)
        if address:
            points.append(self._make_point(prefix, len(points) + 1, address, date, time))

    @staticmethod
    def _append_comment_block(points: list[dict], comments: list[str]) -> None:
        normalized_comments = [RouteInfoParser._normalize_comment_text(c) for c in comments if c]
        comment = "\n".join(dict.fromkeys(c for c in normalized_comments if c))
        if comment:
            points.append({COMMENT_KEY: comment})

    @staticmethod
    def _normalize_comment_text(comment: str) -> str:
        comment = re.sub(r"\s+‣\s*", "\n‣ ", comment)
        comment = re.sub(r"\s+(ВЪЕЗД\b)", r"\n\1", comment)
        comment = re.sub(r"\s+(Контакт\s*:)", r"\n\1", comment, flags=re.IGNORECASE)
        comment = re.sub(r"(\d)\((пример)", r"\1\n(\2", comment, flags=re.IGNORECASE)
        return comment.strip()

    def _extract_optional_datetime(self, section: str) -> tuple[str, str, str]:
        date_match = DATE_RE.search(section)
        if date_match:
            date = self._normalize_date(date_match.group(0))
            time, address = self._extract_datetime_from_segment(section[date_match.start():], date_match.group(0))
            return date, time, address

        time_match = self._find_standalone_time(section)
        if not time_match:
            return NOT_SPECIFIED, NOT_SPECIFIED, section

        address = section.replace(time_match.group(0), " ", 1)
        return NOT_SPECIFIED, self._normalize_time(time_match.group(1)), address

    @staticmethod
    def _find_standalone_time(text: str) -> re.Match | None:
        for match in TIME_RE.finditer(text):
            if RouteInfoParser._looks_like_phone_fragment(text, match):
                continue
            return match
        return None

    @staticmethod
    def _looks_like_phone_fragment(text: str, match: re.Match) -> bool:
        before = text[max(0, match.start() - 1):match.start()]
        after = text[match.end():match.end() + 1]
        return before == "-" or after == "-"

    @staticmethod
    def _normalize_route_text(text: str) -> str:
        text = text.replace("\ufeff", " ").replace("\u200b", " ").replace("\xa0", " ")
        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text.strip(" \n\t|")

    @staticmethod
    def _strip_route_label(text: str) -> str:
        text = re.sub(r"^\s*#+\s*", "", text)
        text = ROUTE_LABEL_RE.sub(" ", text)
        return text.strip(" ,;|\n\t")

    @staticmethod
    def _split_numbered_sections(text: str) -> tuple[list[str], str]:
        matches = list(NUMBERED_RE.finditer(text))
        if not matches:
            return [], text.strip(" ,;|\n\t")

        intro = text[:matches[0].start()].strip(" ,;|\n\t")
        sections = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            section = text[start:end].strip(" ,;|\n\t")
            if section:
                sections.append(section)
        return sections, intro

    def _extract_datetime_from_segment(self, segment: str, date_token: str) -> tuple[str, str]:
        date_match = re.search(re.escape(date_token), segment)
        if not date_match:
            return NOT_SPECIFIED, segment

        before = segment[:date_match.start()]
        after = segment[date_match.end():]

        after_range = AFTER_DATE_TIME_RANGE_RE.match(after)
        if after_range:
            deadline = self._normalize_time(after_range.group(2))
            time = self._one_hour_before(deadline)
            return time, f"{before} {after[after_range.end():]}"

        if re.match(r"\s*,?\s*Круглосуточно\b", after, flags=re.IGNORECASE):
            return "00:00", f"{before} {after}"

        after_time = AFTER_DATE_TIME_RE.match(after)
        if after_time:
            return self._normalize_time(after_time.group(1)), f"{before} {after[after_time.end():]}"

        before_times = list(TIME_RE.finditer(before))
        if before_times:
            time_match = before_times[-1]
            time = self._normalize_time(time_match.group(1))
            before = before[:time_match.start()] + " " + before[time_match.end():]
            return time, f"{before} {after}"

        return NOT_SPECIFIED, f"{before} {after}"

    @staticmethod
    def _normalize_time(value: str) -> str:
        value = value.replace("-", ":").strip()
        parts = value.split(":")
        if len(parts) < 2:
            return value
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    @staticmethod
    def _one_hour_before(value: str) -> str:
        hours, minutes = value.split(":", 1)
        return f"{max(0, int(hours) - 1):02d}:{int(minutes):02d}"

    @staticmethod
    def _normalize_date(value: str) -> str:
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

    @staticmethod
    def _looks_like_point(text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        if DATE_RE.search(text) or TIME_RE.search(text):
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
        addr, pre_phone_comments = self._extract_person_before_phone(addr)
        comments.extend(pre_phone_comments)
        addr, inline_comments = self._extract_inline_comments(addr)
        comments.extend(inline_comments)

        for pattern in SERVICE_PHRASE_PATTERNS:
            addr = re.sub(pattern, " ", addr, flags=re.IGNORECASE)

        for pattern in END_COMMENT_PATTERNS:
            match = re.search(pattern, addr, flags=re.IGNORECASE)
            if match:
                comment = addr[match.start():].strip(" ,;|\n\t")
                if comment:
                    comments.append(comment)
                addr = addr[:match.start()].strip()
                break

        addr = re.sub(r"[-–—]{2,}.*$", "", addr)
        addr = re.sub(r"\s*\|\s*", "\n", addr)
        addr = re.sub(r"\b(?:Погрузка\s+)?там\s+же!?", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\(ОСН\)", " ", addr, flags=re.IGNORECASE)
        addr = re.sub(r"\bКруглосуточно\b", " ", addr, flags=re.IGNORECASE)
        addr = self._normalize_address_tail(addr)
        addr = re.sub(r"[ \t]+", " ", addr)
        addr = re.sub(r"\n\s*\n+", "\n", addr)
        return addr.strip(" ,;|\n\t"), [c for c in comments if c]

    @staticmethod
    def _extract_person_before_phone(addr: str) -> tuple[str, list[str]]:
        match = re.search(
            r"\s([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})\s+(?=(?:тел\.?|[+78][\d\s()\-]{8,}))",
            addr,
        )
        if not match:
            return addr, []

        comment = addr[match.start(1):].strip(" ,;|\n\t")
        return addr[:match.start(1)].strip(" ,;|\n\t"), [comment] if comment else []

    @staticmethod
    def _normalize_service_phrases(addr: str) -> str:
        for pattern, replacement in SERVICE_NORMALIZATION_PATTERNS:
            addr = re.sub(pattern, replacement, addr, flags=re.IGNORECASE)
        return addr.strip()

    @staticmethod
    def _normalize_address_tail(addr: str) -> str:
        for pattern, replacement in ADDRESS_TAIL_PATTERNS:
            addr = re.sub(pattern, replacement, addr, flags=re.IGNORECASE)
        addr = re.sub(r"^\s*г\.\s*(Г\.\s*)", r"\1", addr, flags=re.IGNORECASE)
        addr = addr.rstrip(" ‣")
        return addr.rstrip(".")

    def _extract_inline_comments(self, addr: str) -> tuple[str, list[str]]:
        comments: list[str] = []
        local_time = re.search(r"\((?:время\s+местное|мск\s*[+-]\s*\d+)\)", addr, flags=re.IGNORECASE)
        if local_time:
            comments.append(local_time.group(0))
            addr = addr[:local_time.start()] + " " + addr[local_time.end():]

        address_start = ADDRESS_START_RE.search(addr)
        if address_start and address_start.start() > 0:
            prefix = addr[:address_start.start()].strip(" .,;|\n\t")
            city_prefix = re.match(r"^[А-ЯЁ][А-ЯЁа-яё-]+(?:\s+г\.?)?$", prefix, flags=re.IGNORECASE)
            if prefix and not city_prefix and not DATE_RE.search(prefix):
                comments.append(prefix)
                addr = addr[address_start.start():]

        marker = COMMENT_START_RE.search(addr)
        if marker:
            comment_start = self._marker_comment_start(addr, marker.start())
            comment = addr[comment_start:].strip(" ,;|\n\t")
            if comment:
                comments.append(comment)
            addr = addr[:comment_start]

        return addr, comments

    @staticmethod
    def _marker_comment_start(addr: str, marker_start: int) -> int:
        bullet_prefix = re.search(r"‣\s*$", addr[:marker_start])
        if bullet_prefix:
            return bullet_prefix.start()

        if marker_start > 0 and addr[marker_start - 1] == "(" and ")" in addr[marker_start:]:
            return marker_start - 1

        for pattern in (r",\s*([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?\s*/\s*)$", r"\s([А-ЯЁ][а-яё]+\s*/\s*)$"):
            contact_prefix = re.search(pattern, addr[:marker_start])
            if contact_prefix:
                return contact_prefix.start(1)
        return marker_start

    @staticmethod
    def _make_point(prefix: str, index: int, address: str, date: str, time: str) -> dict:
        return {
            f"{prefix} {index}": address,
            f"{DATE_KEY} {index}": date,
            f"{TIME_KEY} {index}": time,
        }
