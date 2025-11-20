SECTIONS = {
    "wialon_selectors": (
        "Wialon",
        {
            "search_input_xpath": ("XPath поиска", str, True),
            "unit_block_xpath": ("XPath блока ТС", str, True),
            "address_selector": ("CSS адреса", str, True),
            "copy_button_selector": ("CSS копирования координат", str, True),
            "speed_selector": ("CSS скорости", str, False),
            "gps_sats_xpath": ("XPath иконки GPS/спутников", str, False),
            "text_tooltip-gps": ("CSS tooltip GPS", str, False),
        }
    ),
    "yandex_selectors": (
        "Я.Карты",
        {
            "route_button": ("CSS кнопка маршрута", str, True),
            "close_route": ("CSS закрытия маршрута", str, False),
            "from_input": ("XPath Откуда", str, True),
            "to_input": ("XPath Куда", str, True),
            "route_item": ("CSS Результат маршрута", str, True),
            "route_duration": ("CSS длительности", str, True),
            "route_distance": ("CSS расстояния", str, True),
        }
    ),
    "google_config": (
        "Google",
        {
            "creds_file": ("Путь к creds.json", str, True),
            "sheet_id": ("ID таблицы", str, True),
            "worksheet_index": ("Индекс листа", int, True),
            "column_index": ("Индекс колонки", int, True),
            "file_path": ("Путь к JSON-файлу", str, True),
        }
    ),
}
