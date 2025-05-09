from Navigation_Bot.requirements import *
class GoogleSheetsManager:
    def __init__(self, creds_file, sheet_id, worksheet_index, column_index):
        self.creds_file = creds_file
        self.sheet_id = sheet_id
        self.worksheet_index = worksheet_index
        self.column_index = column_index
        self.file_path = "config/selected_data.json"
        self.creds = Credentials.from_service_account_file(
            self.creds_file, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        self.client = gspread.authorize(self.creds)
        self.sheet = self.client.open_by_key(self.sheet_id).get_worksheet(self.worksheet_index)

    def append_to_cell(self, path):
        """
        Добавляет текст в ячейку столбца 13 на строке, указанной в index из JSON.
        :param json_data: JSON-данные (словарь или список словарей)
        """
        json_data = self.open_json(path)
        if isinstance(json_data, list):
            # Если json_data — это список, обрабатываем каждый элемент
            for item in json_data:
                self._process_item(item)
        elif isinstance(json_data, dict):
            # Если json_data — это словарь, обрабатываем его
            self._process_item(json_data)
        else:
            print("❌ Ошибка: json_data должен быть словарем или списком словарей.")

    def _process_item(self, item):
        """
        Обрабатывает один элемент JSON (словарь).
        :param item: Словарь с данными
        """
        try:
            # Извлекаем индекс строки из JSON
            row_index = item["index"]
            if not row_index:
                print("❌ Ошибка: индекс строки не найден в JSON.")
                return

            # Получаем текущее время
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Формируем текст для добавления
            geo = item["гео"]
            coor = item["коор"]
            new_text = f"{current_time}, едет, {geo}, {coor}"

            # Получаем текущие данные из ячейки
            cell_value = self.sheet.cell(row_index, 13).value  # Колонка 13 (M), строка из index

            # Объединяем старые и новые данные
            updated_value = f"{cell_value}\n{new_text}" if cell_value else new_text

            # Обновляем ячейку
            self.sheet.update_cell(row_index, 13, updated_value)
            print(f"✅ Данные успешно добавлены в строку {row_index}, колонку 13.")
        except Exception as e:
            print(f"❌ Ошибка при добавлении данных: {e}")

    def load_data(self):
        return self.sheet.get_all_values()

    def refresh_name(self, rows, file_path):
        """Обновляет JSON без удаления существующих записей"""
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as file:
                try:
                    existing_data = json.load(file)
                except json.JSONDecodeError:
                    existing_data = []
        else:
            existing_data = []

        existing_indexes = {entry["index"] for entry in existing_data}
        new_entries = []

        for i, row in enumerate(rows[2:], start=3):
            if len(row) < self.column_index or row[self.column_index - 1].strip() != "Готов":
                row[3] = re.sub(r'\s+', '', row[3])[:6] + ' ' + re.sub(r'\s+', '', row[3])[6:9]

                if i not in existing_indexes:
                    new_entries.append({
                        "index": i,
                        "ТС": row[3],
                        "ФИО": row[5],
                        "Погрузка": row[7],
                        "Выгрузка": row[8],
                    })

        updated_data = existing_data + new_entries
        self.save_json(updated_data, file_path)

        print(f"Обновлено: добавлено {len(new_entries)} новых записей.")

    def check_up_id_car(self, id_filepath):
        """Удаляет первое слово в 'Наименование', если в строке 3 слова"""
        if not os.path.exists(id_filepath):
            return
        with open(id_filepath, "r", encoding="utf-8") as file:
            try:
                data = json.load(file)
            except json.JSONDecodeError:
                return
        if isinstance(data, list):
            for item in data:
                if "Наименование" in item:
                    words = item["Наименование"].split()
                    if len(words) == 3:
                        item["Наименование"] = ' '.join(words[1:])

    def save_json(self, data: Any, file_path: str) -> None:
        try:
            with open(file_path, "w", encoding="utf-8") as json_file:
                json.dump(data, json_file, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Ошибка при сохранении данных в файл: {e}")


class DataCleaner:
    def __init__(self, sheets_manager, input_filepath, id_filepath):
        """Инициализация путей к JSON-файлам"""
        self.sheets_manager = sheets_manager
        self.selected_data_path = input_filepath
        self.id_car_path = id_filepath
        self.end_patterns = [
            r"тел\s*\d[\d\s\-]{8,}",
            r"Контакт:?\s*\d[\d\s\-]{8,}",
            r"\sГП\s",
            r"\sООО\s",
            r"\(Согласт\s",
            r"ТТН\s",
            r"\ГО\s",
            r"\тел\s",
            r"\ООО\s",
            r"\Контрагент\s",
            r"\по ТТН\s",
            r"контакт\s*\d{1,2}:\d{2}",
            r'\по ттн\s'
        ]

    def _parse_info(self, text, address="Точка"):
        """Вырезает дату, время и адрес из данных Google Sheets"""
        unload_pattern = re.compile(
            r"(\d+\))?\s*(\d{1,2}\.\d{2}\.\d{4})\s*,?\s*(\d{1,2}[:\-]\d{2}(?::\d{2})?)?\s*,?\s*(.*?)(?=\d+\)|$)",
            re.DOTALL
        )
        time_pattern = re.compile(r"\b(\d{1,2}[:\-]\d{2}(?::\d{2})?)\b")
        results = []

        for i, match in enumerate(unload_pattern.finditer(text), 1):
            date = match.group(2)
            time = match.group(3) or "Не указано"
            address_info = match.group(4).strip()

            address_info = re.sub(r"\bприбыть\s+(к|до)\b\s*,?\s*", "", address_info)

            if time == "Не указано":
                time_match = time_pattern.search(address_info)
                if time_match:
                    time = time_match.group(1)
                    address_info = address_info.replace(time_match.group(0), "").strip()

            address_info = re.sub(r"^,\s*", "", address_info)

            for pattern in self.end_patterns:
                end_match = re.search(pattern, address_info)
                if end_match:
                    address_info = address_info[: end_match.start()].strip()
                    break

            results.append({f"{address} {i}": address_info, f"Дата {i}": date, f"Время {i}": time})

        return results

    def start_clean(self):
        """Обрабатывает поля 'Погрузка' и 'Выгрузка' в selected_data.json"""
        if not os.path.exists(self.selected_data_path):
            return

        with open(self.selected_data_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        for item in data:
            if "Погрузка" in item and isinstance(item["Погрузка"], str):
                item["Погрузка"] = self._parse_info(item["Погрузка"], "Погрузка")
            if "Выгрузка" in item and isinstance(item["Выгрузка"], str):
                item["Выгрузка"] = self._parse_info(item["Выгрузка"], "Выгрузка")

        self.sheets_manager.save_json(data, self.selected_data_path)

    def clean_vehicle_names(self):
        """Исправляет номер машины (Наименование) для работы с навигацией"""
        if not os.path.exists(self.id_car_path):
            return

        with open(self.id_car_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        for item in data:
            if "Наименование" in item and isinstance(item["Наименование"], str):
                words = item["Наименование"].split()
                if len(words) == 3:
                    item["Наименование"] = ' '.join(words[1:])
        self.sheets_manager.save_json(data, self.id_car_path)

    def add_id_to_data(self):
        """Добавляет 'id' к каждому элементу JSON, если найдено соответствие"""
        if not os.path.exists(self.selected_data_path) or not os.path.exists(self.id_car_path):
            print("Нет пути к id или car_data")
            return

        with open(self.selected_data_path, "r", encoding="utf-8") as file1:
            json1 = json.load(file1)
        with open(self.id_car_path, "r", encoding="utf-8") as file2:
            json2 = json.load(file2)

        lookup = {entry["Наименование"]: entry["ИДОбъекта в центре мониторинга"] for entry in json2}

        for item in json1:
            if item["ТС"] in lookup:
                item["id"] = lookup[item["ТС"]]
        self.sheets_manager.save_json(json1, self.selected_data_path)
        print(f'Присвоение id в json')


class MapsBot:
    def __init__(self, web_driver_manager, sheets_manager):
        self.web_driver_manager = web_driver_manager
        self.sheets_manager = sheets_manager

    def enter_route(self, start_coords, destination_address):
        """Заполняет поле 'Откуда' и 'Куда' на карте"""
        try:
            driver = self.web_driver_manager.driver
            driver.switch_to.window(driver.window_handles[0])

            self._fill_input("//input[@placeholder='Откуда']", start_coords)
            self._fill_input("//input[@placeholder='Куда']", destination_address)

            self.web_driver_manager("//div[contains(@class, 'route-snippet-view') and contains(@class, '_type_auto')]")
        except Exception as e:
            print(f"Ошибка в 'enter_route': {e}")

    def _clean_input(self):
        def clear_element(locator):
            element = self.web_driver_manager.web_driver_wait(locator)
            element.send_keys(Keys.CONTROL, "a", Keys.BACKSPACE)
            WebDriverWait(self.web_driver_manager.driver, 3).until(lambda d: element.get_attribute("value") == "")

        clear_element("//input[@placeholder='Откуда']")
        clear_element("//input[@placeholder='Куда']")

    def _fill_input(self, xpath, value):
        """Заполняет поле ввода"""
        element = self.web_driver_manager.web_driver_wait(xpath)
        element.clear()
        element.send_keys(value)
        element.send_keys(Keys.ENTER)
        # Удалить ?
        WebDriverWait(self.web_driver_manager.driver, 3).until(lambda d: element.get_attribute("value") == value)

    def get_route_info(self):
        try:
            self.web_driver_manager.web_driver_wait(
                "//div[contains(@class, 'route-snippet-view') and contains(@class, '_type_auto')]")

            elements = self.web_driver_manager.driver.find_elements(
                By.XPATH,
                "//div[contains(@class, 'route-snippet-view') and contains(@class, '_type_auto') and @aria-hidden='false']")
            if not elements:
                print("Ошибка: Маршруты не найдены. Возможно, не загрузились.")
                return []

            routes = []
            for element in elements:
                try:
                    duration = element.find_element(By.XPATH,
                                                    ".//div[contains(@class, 'auto-route-snippet-view__route-duration')]").text.strip()
                    distance = element.find_element(By.XPATH,
                                                    ".//div[contains(@class, 'auto-route-snippet-view__route-subtitle')]").text.strip()
                    routes.append((duration, distance))
                except NoSuchElementException:
                    print("Маршрут найден, но не удалось извлечь данные.")

            if not routes:
                print("Ошибка: Не удалось извлечь данные о маршрутах.")
            else:
                print(f"Найдено {len(routes)} маршрутов: {routes}")
            self._clean_input()
            return routes

        except TimeoutException:
            print("Ошибка: Тайм-аут ожидания маршрутов.")
            return []
        except Exception as e:
            print(f"Ошибка в 'get_route_info': {e}")
            return []

    def calculate_arrival_time(self, avg_time, unload_datetime):
        """Рассчитывает время прибытия и проверяет, успевает ли машина на выгрузку"""
        arrival_time = datetime.now() + timedelta(minutes=avg_time)
        time_buffer = (unload_datetime - arrival_time).total_seconds() / 60  # Запас времени в минутах
        buffer_hours = int(time_buffer // 60)
        buffer_minutes = int(time_buffer % 60)
        return {
            "время прибытия": arrival_time.strftime("%d.%m.%Y %H:%M"),
            "время разгрузки": unload_datetime.strftime("%d.%m.%Y %H:%M"),
            "on_time": arrival_time <= unload_datetime,
            "time_buffer": f"{buffer_hours}:{buffer_minutes:02d}"  # Запас времени в формате часы:минуты
        }

    def process_navigation_from_json(self, input_filepath):
        """Обрабатывает JSON-файл с маршрутами"""
        try:
            with open(input_filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            for car in data:
                start_coords = car.get("коор")
                unload_info = car.get("Выгрузка", [{}])[0]
                destination_address = unload_info.get("Выгрузка 1")
                unload_datetime = self._parse_datetime(unload_info.get("Дата 1"), unload_info.get("Время 1"))

                if not (start_coords and destination_address and unload_datetime):
                    print(f"Пропуск машины {car.get('ТС')}: некорректные данные")
                    continue

                self.enter_route(start_coords, destination_address)
                routes = self.get_route_info()

                if not routes:
                    print(f"Нет маршрутов для {car.get('ТС')}")
                    continue

                avg_time, avg_distance = self._calculate_average_route(routes)
                arrival_result = self.calculate_arrival_time(avg_time, unload_datetime)

                car["Маршрут"] = {
                    "Среднее время (мин)": avg_time,
                    "Среднее расстояние (км)": avg_distance,
                    "Расчет прибытия": arrival_result
                }

                if int(arrival_result["time_buffer"].split(":")[0]) < 0:
                    print(f"Внимание! Маленький запас времени у {car.get('ТС')} ({arrival_result['time_buffer']})")

                print(f"Обработана {car.get('ТС')}: {car['Маршрут']}")

            self.sheets_manager.save_json(data, input_filepath)
        except Exception as e:
            print(f"Ошибка при обработке JSON: {e}")

    @staticmethod
    def _parse_datetime(date_str, time_str):
        """Парсит дату и время в объект datetime"""
        try:
            return datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _calculate_average_route(routes):
        """Вычисляет среднее расстояние и время"""
        times, distances = zip(*[(MapsBot._convert_time(t), MapsBot._convert_distance(d)) for t, d in routes])
        return round(sum(times) / len(times)), round(sum(distances) / len(distances))

    @staticmethod
    def _convert_time(time_str):
        """Конвертирует '5 ч 30 мин' в минуты"""
        hours = sum(map(int, re.findall(r'(\d+)\s*ч', time_str)))
        minutes = sum(map(int, re.findall(r'(\d+)\s*мин', time_str)))
        return hours * 60 + minutes

    @staticmethod
    def _convert_distance(distance_str):
        """Конвертирует '490 км' в км"""
        return int(re.search(r'(\d+)', distance_str).group(1)) if distance_str else 0

    @staticmethod
    def calculate_time(distance):
        """Рассчитывает время с учётом прогрессии"""
        if distance <= 100:
            return 1  # 100 км - 1 час
        base_time = 1  # Начальная точка (100 км = 1 ч)
        factor = 0.5  # Увеличение времени на каждом шаге
        exponent = math.log2(distance / 100)
        return round(base_time + factor * exponent, 2)


class NavigationBot:
    def __init__(self, driver, sheets_manager):
        self.driver = driver
        self.sheets_manager = sheets_manager  # Используем для работы с JSON

    def web_driver_wait(self, xpath, timeout=15):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.XPATH, xpath))
        )

    def clean_car(self):
        """Закрытие всплывающих окон и очистка поиска"""
        try:
            self.web_driver_wait("//*[@id='hb_mi_monitoring']").click()
            action = ActionChains(self.driver)
            action.move_by_offset(10, 10).perform()
            time.sleep(0.2)
            action.move_by_offset(200, 200).perform()
            time.sleep(0.2)

            input_element = self.web_driver_wait("//*[@id='monitoring_search_container']//input[@placeholder='Поиск']")
            input_element.click()
            input_element.send_keys(Keys.CONTROL + "a")
            input_element.send_keys(Keys.BACKSPACE)
            print("Очистка поиска выполнена.")
        except Exception as e:
            print(f"Ошибка в clean_car: {e}")

    def find_car_element(self, car_id):
        try:
            xpath = f"//*[@id='monitoring_units_custom_name_{car_id}']"
            return self.web_driver_wait(xpath)
        except Exception as e:
            print(f"37/Ошибка поиска автомобиля: {e}")
            return None

    def find_gps_status(self, car_id):
        """Получение информации о связи со спутниками"""
        try:
            xpath = f"//*[@id='monitoring_units_state_gps_sats_{car_id}']"
            element = self.web_driver_wait(xpath)
            action = ActionChains(self.driver)
            action.move_to_element(element).perform()
            tooltip_element = self.driver.find_element(By.XPATH, "//div[@class='tooltip-gps']")
            return tooltip_element.text.strip()
        except Exception as e:
            print(f"Ошибка получения GPS-статуса: {e}")
            return None

    def get_location_and_coordinates(self):
        try:
            for _ in range(5):
                location_info = self.web_driver_wait(".//*[@class='location']")
                if location_info.text != "Обработка...":
                    location_text = location_info.text
                    break
                time.sleep(2)
            else:
                location_text = None

            coord_elements = self.driver.find_elements(By.XPATH, "//div[@class='coordinates']/div")
            coordinates = coord_elements[0].text.strip().replace("\n", ",")

            return location_text, coordinates
        except Exception as e:
            print(f"Ошибка получения местоположения или координат: {e}")
            return None, None, None

    def process_car(self, car_data):
        car_number = car_data.get("ТС")
        car_id = car_data.get("id")
        print(f'process_car {car_number},{car_id} дальше send_keys')
        search_input = self.web_driver_wait("//*[@id='monitoring_search_container']//input[@placeholder='Поиск']")
        time.sleep(1)
        search_input.send_keys(car_number)

        element = self.find_car_element(car_id)
        if not element:
            print(f"ТС {car_number}, id {car_id} не найден.")
            return car_data

        actual_id = element.get_attribute("id")
        if not actual_id.endswith(str(car_id)):
            print(f"Пропуск: ID не совпадает (ожидалось {car_id}, найдено {actual_id})")
            return car_data

        action = ActionChains(self.driver)
        action.move_to_element(element).perform()

        location_text, coordinates = self.get_location_and_coordinates()

        car_data["гео"] = location_text
        car_data["коор"] = coordinates

        print(f"Обработано: ТС {car_number}, Гео: {location_text}, Координаты: {coordinates}")
        return car_data

    def press_car(self, input_filepath):
        with open(input_filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):  # Проверяем, что получили список
            print("Ошибка: Ожидался список, но получен другой тип данных")
            return

        for i, ts in enumerate(data):
            if not isinstance(ts, dict):  # Проверяем, что каждая запись — это словарь
                print(f"Ошибка: Ожидался словарь, но получен {type(ts)} в позиции {i}")
                continue

            try:
                updated_ts = self.process_car(ts)  # Обрабатываем один автомобиль
                data[i] = updated_ts  # Обновляем оригинальный список

                self.clean_car()
            except Exception as e:
                print(f"class NavigationBot -> press_car \n Ошибка обработки ТС {ts.get('ТС', 'Неизвестно')}: {e}")

        # Сохраняем обновлённые данные
        self.sheets_manager.save_json(data, input_filepath)
        print(f"Обработка завершена. Данные сохранены.")

from Navigation_Bot.requirements import *
class WebDriverManager:
    def __init__(self):
        self.config_path = "config/config.json"
        self.cookies_path = "config/cookies.pkl"
        self.driver = None

    def start_browser(self):
        self.driver = webdriver.Chrome()
        self.driver.maximize_window()

    def save_cookies(self):
        with open(self.cookies_path, "wb") as file:
            pickle.dump(self.driver.get_cookies(), file)

    def load_cookies(self):
        try:
            with open(self.cookies_path, "rb") as file:
                cookies = pickle.load(file)
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            print("Куки загружены.")
        except FileNotFoundError:
            print("Файл cookies.pkl не найден, требуется авторизация.")

    def web_driver_wait(self, xpath, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.XPATH, xpath))
        )

    def open_wialon(self):
        self.driver.get("https://wialon.rtmglonass.ru/?lang=ru")
        self.load_cookies()
        self.driver.refresh()
        time.sleep(5)

    def login_wialon(self):
        """Авторизуется в Wialon, если нет сохранённых cookies"""
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        username = data["username"]
        password = data["password"]

        self.driver.get("https://wialon.rtmglonass.ru/?lang=ru")

        self.web_driver_wait("//*[@data-testid='LoginMainEmailInput']").send_keys(username)
        self.web_driver_wait("//*[@data-testid='LoginMainPassInput']").send_keys(password)

        login_button = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//*[@data-testid='LoginMainSubmitButton']"))
        )
        login_button.click()

        print("Авторизация в Wialon")
        self.save_cookies()

    def open_yandex_maps(self):
        self.driver.get("https://yandex.ru/maps")  # Открываем карты в текущей вкладке

        try:
            # Ожидание полной загрузки страницы
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Проверяем, есть ли кнопка "Построить маршрут"
            route_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@class, 'button _view_search _size_medium _link')]"))
            )
            route_button.click()
        except TimeoutException:
            print("Кнопка маршрута не найдена")

    def setup_wialon(self):
        try:
            self.web_driver_wait("//*[@id='hb_mi_monitoring']").click()
        except:
            print(f'в "class WebDriverManager -> setup_wialon"\n Не смог найти class=hb_item_text')