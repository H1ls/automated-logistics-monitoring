from Navigation_Bot.core.jSONManager import JSONManager

class DataContext:
    """Централизованное хранилище JSON-данных"""

    def __init__(self, filepath, log_func=print):
        self.filepath = filepath
        self.manager = JSONManager(filepath, log_func=log_func)
        self.log = log_func
        self.data = self.manager.load_json() or []

    def reload(self):
        self.data = self.manager.load_json() or []
        return self.data

    def save(self):
        self.manager.save_in_json(self.data, self.filepath)

    def get(self):
        return self.data

    def set(self, new_data):
        self.data = new_data
        self.save()

    def append(self, entry: dict):
        self.data.append(entry)
        self.save()
