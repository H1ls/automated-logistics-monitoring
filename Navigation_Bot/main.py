from googleSheetsManager import GoogleSheetsManager
from navigationBot import NavigationBot
from dataCleaner import DataCleaner
from webDriverManager import WebDriverManager
from mapsBot import MapsBot
from Navigation_Bot.requirements import *

# Инициализация путей
SHEET_ID = "1uz2ZXlCBltsD8s96GNuQELDEJ5_qCBuDFP2dvxeNqsU"
SHEET_NAME = "Sheet1"
CREDENTIALS_FILE = "../config/Credentials_wialon.json"
SELECTED_DATA_PATH = "../config/selected_data.json"
ID_CAR_PATH = "../config/Id_car.json"

# sheets_manager = GoogleSheetsManager(CREDENTIALS_FILE, SHEET_ID, 3, 14)
sheets_manager = GoogleSheetsManager(3, 14)
cleaner = DataCleaner(sheets_manager, SELECTED_DATA_PATH, ID_CAR_PATH)


service = Service()
driver = webdriver.Chrome(service=service)


# Открытие вкладок Wialon и Яндекс.Карт
web_driver_manager = WebDriverManager()
web_driver_manager.start_browser()
web_driver_manager.open_wialon()
web_driver_manager.login_wialon()
web_driver_manager.open_yandex_maps()


# Инициализация ботов
navigation_bot = NavigationBot(driver, sheets_manager)
maps_bot = MapsBot(driver, sheets_manager)

def sync_data():
    print("[SYNC] Начинаем синхронизацию с Google Sheets...")

    # Получаем данные из Google Sheets
    sheets_manager.refresh_name(SELECTED_DATA_PATH)

    # После получения данных, обрабатываем новые записи
    cleaner.clean_vehicle_names()  # Очистка номеров машин
    cleaner.add_id_to_data()       # Добавление ID в записи
    cleaner.start_clean()          # Очистка Погрузка/Выгрузка

    print("[SYNC] Синхронизация завершена.")

# Функция для обработки машин
def process_cars():
    print("[PROCESS] Начинаем обработку машин...")

    # Загружаем данные о машинах
    with open(SELECTED_DATA_PATH, "r", encoding="utf-8") as f:
        cars_data = json.load(f)

    for car_data in cars_data:
        if not car_data.get("ТС"):
            continue

        updated_car_data = navigation_bot.process_car(car_data)

        sheets_manager.save_json([updated_car_data], SELECTED_DATA_PATH)

        maps_bot.enter_route(updated_car_data)

    print("[PROCESS] Обработка машин завершена.")

# Основная логика
def main():
    # Шаг 1: Синхронизация с Google Sheets
    sync_data()

    # Шаг 2: Обработка машин
    process_cars()

    driver.quit()

if __name__ == "__main__":
    main()
