from Navigation_Bot.webDriverManager import WebDriverManager
from Navigation_Bot.mapsBot import MapsBot
import json
import time


def test_mapsbot_on_selected_data():
    browser = WebDriverManager()
    browser.start_browser()
    browser.open_yandex_maps()
    maps_bot = MapsBot(browser, sheets_manager=None)

    with open("C:/Users/Hils/PycharmProjects/pet.project/seleni_get/config/selected_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    print("\n--- Тест: маршруты для первых 3 машин ---")

    for i, car in enumerate(data[:3], 1):
        start_coords = "53.24764,50.28859"
        unload_info = car.get("Выгрузка", [{}])[0]
        destination_address = unload_info.get("Выгрузка 1", "")

        if not destination_address:
            print(f"[{i}] Пропуск: отсутствует адрес выгрузки")
            continue

        print(f"[{i}] Откуда: {start_coords} | Куда: {destination_address}")

        maps_bot.enter_route(start_coords, destination_address)
        routes = maps_bot.get_route_info()

        if routes:
            for j, (duration, distance) in enumerate(routes, 1):
                print(f"  Маршрут {j}: Время = {duration}, Расстояние = {distance}")
        else:
            print(f"  Маршруты не найдены")

        time.sleep(2)
    browser.driver.quit()

test_mapsbot_on_selected_data()
