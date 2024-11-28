from selenium.webdriver import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
import json
import time


def web_driver_wait(driver, xpath):
    return WebDriverWait(driver, 15).until(
        EC.visibility_of_element_located((By.XPATH, xpath)))


def clean_car(driver):
    """Функция для управления всплывающими окнами и очистки поля поиска."""
    try:
        # Переключение на элемент меню (например, чтобы сбросить фокус)
        web_driver_wait(driver, "//*[@id='hb_mi_monitoring']").click()

        # Удаление фокуса с активного окна через движение мыши
        action = ActionChains(driver)

        # Движение мыши в произвольное место экрана (например, в верхний угол)
        action.move_by_offset(10, 10).perform()
        time.sleep(0.2)  # Пауза для завершения движения мыши

        # Повторное перемещение мышки для надежности
        action.move_by_offset(200, 200).perform()
        time.sleep(0.2)

        # Очистка поля поиска
        input_element = web_driver_wait(driver,
                                        "//*[@id='monitoring_search_container']//input[@placeholder='Поиск']")
        input_element.click()  # Убедитесь, что поле в фокусе
        input_element.send_keys(Keys.CONTROL + "a")  # Выделение текста
        input_element.send_keys(Keys.BACKSPACE)  # Очистка текста
        print("Успешно выполнили очистку и сброс фокуса")
    except Exception as e:
        print(f"Ошибка в clean_car: {e}")


def load_data(filepath):
    """Загрузка данных из JSON-файла."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(filepath, data):
    """Сохранение данных в JSON-файл."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def find_car_element(driver, car_id):
    """Поиск элемента автомобиля по id."""
    try:
        xpath = f"//*[@id='monitoring_units_custom_name_{car_id}']"
        element = web_driver_wait(driver, xpath=xpath)
        return element
    except Exception as e:
        print(f"Ошибка поиска элемента: {e}")
        return None


def find_gps_car(driver, car_id):
    """Поиск статуса автомобиля со спутниками."""
    try:
        xpath = f"//*[@id='monitoring_units_state_gps_sats_{car_id}']"
        element = web_driver_wait(driver, xpath=xpath)
        action = ActionChains(driver)
        action.move_to_element(element).perform()
        tooltip_element = driver.find_element(By.XPATH, "//div[@class='tooltip-gps']")
        text = tooltip_element.text.strip()
        print(text)  # Не установлена связь со спутниками.\nПоложение определено 279 дн. 11 ч назад.
        if action:
            """если Не установлена больше 2ч"""
    except Exception as e:
        print(f"Ошибка поиска элемента: {e}")
        return None


def speed_car(driver, car_id):
    """Замер движения"""
    pass
    # data - element = "speedEl"


def get_location_and_coordinates(driver):
    """Получение местоположения и координат."""
    location_text = None
    coordinates_info = None

    try:
        # Пять попыток получения данных о местоположении
        for _ in range(5):
            location_info = web_driver_wait(driver, xpath=".//*[@class='location']")
            if location_info.text != "Обработка...":
                location_text = location_info.text
                break
            time.sleep(2)

        # Получение координат
        coordinates_info = web_driver_wait(driver, xpath=".//div[@class='coordinates']")
        latitude = coordinates_info.find_element(By.XPATH, "./div[1]").text
        longitude = coordinates_info.find_element(By.XPATH, "./div[2]").text
        longitude = longitude.strip()

        return location_text, latitude, longitude
    except Exception as e:
        print(f"Ошибка получения местоположения или координат: {e}")
        # return location_text, None, None
        return None, None, None


def process_car(driver, car_data):
    """Обработка одного автомобиля."""
    car_number = car_data["ТС"]
    car_id = car_data.get("id")

    # Ввод номера автомобиля в поиск
    web_driver_wait(driver, xpath="//*[@id='monitoring_search_container']//input[@placeholder='Поиск']").send_keys(
        car_number)

    # Поиск элемента автомобиля
    element = find_car_element(driver, car_id)
    if not element:
        print(f"Элемент для ТС={car_number}, id={car_id} не найден. Пропускаем.")
        return car_data  # Возвращаем данные без изменений

    # Проверяем, что id элемента совпадает
    actual_id = element.get_attribute("id")
    if not actual_id.endswith(str(car_id)):
        print(f"Пропускаем, id не совпадает: ожидалось {car_id}, найдено {actual_id}")
        return car_data

    # Наведение на элемент
    action = ActionChains(driver)
    action.move_to_element(element).perform()

    # Получение местоположения и координат
    location_text, latitude, longitude = get_location_and_coordinates(driver)

    # Обновляем данные
    car_data["гео"] = location_text
    car_data["координаты"] = f"{latitude} {longitude}"
    car_gps["Связь"] = f"{latitude}"
    car_speed["Состояние"] = f"{latitude} {longitude}"
    # car_data["координаты"] = f"{latitude} {longitude}" if latitude and longitude else None

    print(f"Обработано: ТС = {car_number}, Гео = {location_text}, Координаты = {latitude} {longitude}")
    return car_data


def press_car(driver, input_filepath, output_filepath):
    """Основная функция обработки всех машин."""
    # Загружаем данные
    data = load_data(input_filepath)
    processed_data = []

    for ts in data:
        try:
            # Обработка каждого автомобиля
            updated_ts = process_car(driver, ts)
            processed_data.append(updated_ts)
            # Очистка перед обработкой следующего автомобиля
            clean_car(driver)
        except Exception as e:
            print(f"Ошибка обработки ТС: {ts.get('ТС', 'Неизвестно')} - {e}")
            # Сохраняем текущие данные даже при ошибке
            save_data(output_filepath, processed_data)

    # Сохраняем итоговые данные
    save_data(output_filepath, processed_data)
    print(f"Обработка завершена. Результат сохранен в {output_filepath}")
