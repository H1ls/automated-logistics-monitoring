from Navigation_Bot.requirements import *


class JSONManager:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load_json(self) -> Any:
        if not os.path.exists(self.file_path):
            return []  # Возвращаем пустой список, если файла нет
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError:
            print(f"Ошибка: Файл {self.file_path} содержит некорректный JSON.")
            return []

    def save_json(self, data: Any) -> None:
        try:
            with open(self.file_path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Ошибка сохранения JSON: {e}")

    def update_json(self, new_data: Any) -> None:
        """Добавляет новые данные в JSON без удаления старых записей."""
        existing_data = self.load_json()
        if isinstance(existing_data, list) and isinstance(new_data, list):
            existing_data.extend(new_data)
        elif isinstance(existing_data, dict) and isinstance(new_data, dict):
            existing_data.update(new_data)
        else:
            print("Ошибка: Тип данных JSON не совпадает.")
            return
        self.save_json(existing_data)
