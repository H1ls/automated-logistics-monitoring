from selenium.webdriver.chrome.service import Service
from selenium import webdriver

from seleni_get.data_fetching import get_spreadsheet, refresh_name
from seleni_get.clean_address import start_clean
from seleni_get.rename_json import get_id_for_data, check_up_id_car
from seleni_get.login import open_sky_telecom
from seleni_get.search import press_car

selected_data = "selected_data.json"

input_filepath = "selected_data.json"
output_filepath = "updated_data.json"

service = Service()
driver = webdriver.Chrome(service=service)
driver.maximize_window()


def main():
    """1. Загрузка из Excel"""
    result = get_spreadsheet()
    refresh_name(result)
    """2. Чистка адресов загруженных из Excel"""
    start_clean()

    """3.Проверка идентификаторов машин в JSON, Добавляет поле "id" к каждому элементу для новой data"""
    check_up_id_car()
    get_id_for_data()

    """4. Открытие Google Sky Telecom """
    open_sky_telecom(driver)

    """5. Ввод поисковой машины """
    press_car(driver, selected_data, output_filepath)
    process_car(driver)
    """6.Просчет времени"""
    pass
    """7. Ввод данных в Excel"""
    pass
    input("Нажмите Enter, чтобы закрыть окно браузера...")
    # open_in_cookie(driver)


if __name__ == "__main__":
    main()
