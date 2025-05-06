from Navigation_Bot.dataCleaner import DataCleaner
from Navigation_Bot.googleSheetsManager import GoogleSheetsManager
from Navigation_Bot.mapsBot import MapsBot
from Navigation_Bot.navigationBot import NavigationBot
from Navigation_Bot.webDriverManager import WebDriverManager

input_filepath = "config/selected_data.json"
id_filepath = "config/Id_car.json"
sheets_manager = GoogleSheetsManager(
    creds_file="config/Credentials_wialon.json",
    sheet_id="1uz2ZXlCBltsD8s96GNuQELDEJ5_qCBuDFP2dvxeNqsU",
    worksheet_index=3,
    column_index=14)

browser_manager = WebDriverManager()


def start_navi():
    browser_manager.start_browser()
    browser_manager.login_wialon()
    browser_manager.setup_wialon()
    navi = NavigationBot(browser_manager.driver, sheets_manager)
    navi.press_car(input_filepath)


def start_yandex(browser_manager, sheets_manager):
    browser_manager.start_browser()
    browser_manager.open_yandex_maps()
    maps_bot = MapsBot(browser_manager, sheets_manager)
    maps_bot.process_navigation_from_json(input_filepath)


# start_yandex()
def dataC(sheets_manager, input_filepath, id_filepath):
    cleaner = DataCleaner(sheets_manager, input_filepath, id_filepath)
    # Очистка номеров машин
    cleaner.clean_vehicle_names()
    # Добавление ID
    cleaner.add_id_to_data()
    # Очистка адресов (Погрузка/Выгрузка)
    cleaner.start_clean()

start_navi()
# dataC(sheets_manager, input_filepath, id_filepath)
# start_yandex(browser_manager,sheets_manager)
