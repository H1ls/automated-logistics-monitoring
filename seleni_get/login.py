import json
import pickle
import time
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By


def save_cookies(driver, file_path):
    with open(file_path, "wb") as file:
        pickle.dump(driver.get_cookies(), file)


def load_cookies(driver, file_path):
    with open(file_path, "rb") as file:
        cookies = pickle.load(file)
    for cookie in cookies:
        driver.add_cookie(cookie)


def open_in_cookie(driver):
    driver.get("https://wialon.rtmglonass.ru/?lang=ru")
    load_cookies(driver, "cookies.pkl")  # Загружаем перед работой
    # Шаг 3: Обновить страницу, чтобы сессия активировалась
    driver.refresh()
    time.sleep(5)
    print("Сессия восстановлена!")
    # Теперь вы можете взаимодействовать с сайтом
    # press_car(driver)


def web_driver_wait(driver, xpath):
    some = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.XPATH, xpath)))
    return some


def open_sky_telecom(driver):
    with open("config/config.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    username = data["username"]
    password = data["password"]
    # Откройте страницу входа
    driver.get("https://wialon.rtmglonass.ru/?lang=ru")
    web_driver_wait(driver, "//*[@data-testid='LoginMainEmailInput']").send_keys(username)
    web_driver_wait(driver, "//*[@data-testid='LoginMainPassInput']").send_keys(password)
    login_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
        (By.XPATH, "//*[@data-testid='LoginMainSubmitButton']")))
    login_button.click()
    print("End func- open_sky_telecom")
    # --- Сохранение куков после авторизации ---
    save_cookies(driver, "cookies.pkl")
