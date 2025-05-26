from selenium import webdriver
from Navigation_Bot.mapsBot import MapsBot
import time

def test_mapsbot_single_route():
    driver = webdriver.Chrome()
    driver.get("https://yandex.ru/maps")
    driver.maximize_window()
    time.sleep(3)

    bot = MapsBot(driver, log_func=print)
    bot.click_route_button()
    bot.enter_route("56.201596, 37.552626", "Москва")
    routes = bot.get_route_info()

    if routes:
        print(f"✅ Получено маршрутов: {len(routes)}")
        for r in routes:
            print(f" - {r}")
    else:
        print("❌ Не удалось получить маршруты.")

    input("Нажми Enter для выхода...")
    driver.quit()

test_mapsbot_single_route()


