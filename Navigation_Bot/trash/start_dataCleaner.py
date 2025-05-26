from Navigation_Bot.dataCleaner import DataCleaner
from Navigation_Bot.jSONManager import JSONManager

input_filepath = "../../config/selected_data.json"
id_filepath = "../../config/Id_car.json"
jsons = JSONManager()
cleaner = DataCleaner(jsons, input_filepath, id_filepath)
# После получения данных, обрабатываем новые записи
cleaner.clean_vehicle_names()  # Очистка номеров машин
cleaner.add_id_to_data()  # Добавление ID в записи
cleaner.start_clean()  # Очистка Погрузка/Выгрузка
