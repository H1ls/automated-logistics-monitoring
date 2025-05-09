from Navigation_Bot.requirements import *

""" 4. Работа с Selenium и навигацией"""


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

        self.sheets_manager.save_json(data, input_filepath)
        print(f"Обработка завершена. Данные сохранены.")
