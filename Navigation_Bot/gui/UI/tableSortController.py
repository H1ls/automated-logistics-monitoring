from datetime import datetime


class TableSortController:
    def __init__(self, data_context, table_manager, log):
        self.data_context = data_context
        self.table_manager = table_manager
        self.log = log
        self.current = None

    def sort_default(self):
        data = self.data_context.get()
        data.sort(key=lambda x: x.get("index", 99999))
        self.current = None
        self.table_manager.display(reload_from_file=False)
        self.log("↩️ Сортировка: по умолчанию (index)")

    def sort_by_buffer(self):
        data = self.data_context.get()

        def buf(row):
            try:
                return int(row.get("Маршрут", {}).get("buffer_minutes", 999999))
            except:
                return 999999

        data.sort(key=buf)
        self.current = "buffer"
        self.table_manager.display(reload_from_file=False)

        self.log("⏳ Сортировка: по запасу времени")

    def sort_by_arrival(self):

        data = self.data_context.get()

        def arr(row):
            try:
                val = row.get("Маршрут", {}).get("время прибытия")
                return datetime.strptime(val, "%d.%m.%Y %H:%M")
            except:
                return datetime.max

        data.sort(key=arr)
        self.current = "arrival"
        self.table_manager.display(reload_from_file=False)
        self.log("🕒 Сортировка: по времени прибытия")
