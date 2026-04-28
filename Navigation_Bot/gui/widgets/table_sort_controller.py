from datetime import datetime


class TableSortController:
    def __init__(self, task_repository, log):
        self.task_repository = task_repository
        self.log = log
        self.current = None  # None / "buffer" / "arrival"

    def build_view_order(self) -> list[int]:
        data = self.task_repository.get() or []
        order = list(range(len(data)))

        if self.current is None:
            order.sort(key=lambda i: (data[i].get("index", 999999)))
            return order

        if self.current == "buffer":
            def buf(i):
                try:
                    return int(data[i].get("Маршрут", {}).get("buffer_minutes", 999999))
                except:
                    return 999999
            order.sort(key=buf)
            return order

        if self.current == "arrival":
            def arr(i):
                try:
                    val = data[i].get("Маршрут", {}).get("время прибытия")
                    return datetime.strptime(val, "%d.%m.%Y %H:%M")
                except:
                    return datetime.max
            order.sort(key=arr)
            return order

        return order
