# Связь вкладок Google Sheets с БД

## Кратко

Вкладки Google Sheets сейчас не сохраняются в БД как отдельный справочник.

Они живут во время работы приложения:

- в `GoogleSheetsManager._worksheets_cache`;
- в runtime-маппингах GUI: `gui._tabs_by_key`, `gui._tabs_order`, `gui._tab_buttons_by_key`.

Связь задач с БД выполняется через `source_key` активной вкладки. Для каждого активного листа строится ключ вида:

```text
sheet_{worksheet_index}_{worksheet_title}
```

Этот ключ передается в API при чтении и записи задач.

## Поток зависимости

```text
Google Spreadsheet
    |
    | spreadsheet.worksheets()
    v
GoogleSheetsManager._worksheets_cache
    |
    | get_worksheets_list()
    v
SheetTabsController.build()
    |
    | создает словари вкладок: {kind, key, title, ws_index}
    v
gui._tabs_by_key / gui._tabs_order / gui._tab_buttons_by_key
    |
    | пользователь нажимает вкладку Google
    v
SheetTabsController.on_tab_clicked()
    |
    | google_sync_service.switch_worksheet(ws_index)
    v
GoogleSheetsManager.set_active_worksheet()
    |
    | задает gsheet.sheet и gsheet.worksheet_index
    v
NavigationGUI._get_sheet_source_key()
    |
    | sheet_{index}_{title}
    v
ApiTaskRepository.set_source_key(source_key)
    |
    | GET/POST /api/v1/tasks с source_key
    v
задачи в БД разделены по source_key
```

## Где загружаются вкладки

`Navigation_Bot/bots/google_sheets_manager.py`

- `load_settings()` открывает таблицу и загружает листы:

```python
self._worksheets_cache = spreadsheet.worksheets()
self.sheet = self._worksheets_cache[self.worksheet_index]
```

- `get_worksheets_list()` обновляет кеш листов и возвращает метаданные вкладок:

```python
self._worksheets_cache = spreadsheet.worksheets()
return [{"title": ws.title, "index": ws.index} for ws in self._worksheets_cache]
```

Важно: это только runtime-кеш. Он не сохраняется как таблица в БД.

## Где GUI хранит вкладки

`Navigation_Bot/gui/controllers/sheet_tabs_controller.py`

`SheetTabsController.build()` вызывает:

```python
worksheets = gui.gsheet.get_worksheets_list()
```

Затем каждый лист превращается во вкладку GUI:

```python
tabs.append({
    "kind": "gsheet",
    "key": f"gs:{title}",
    "title": title,
    "ws_index": idx,
})
```

И сохраняется в полях GUI:

```python
gui._tabs_by_key = {t["key"]: t for t in tabs}
gui._tabs_order = [t["key"] for t in tabs]
gui._tab_buttons_by_key[key] = btn
```

Эти структуры тоже существуют только во время работы приложения.

## Где выбирается активный лист

`Navigation_Bot/gui/controllers/sheet_tabs_controller.py`

Когда пользователь нажимает вкладку Google:

```python
ok, err = gui.google_sync_service.switch_worksheet(ws_index)
gui.task_repository.set_source_key(gui._get_sheet_source_key(), reload=False)
gui.reload_and_show()
```

`Navigation_Bot/core/application/services/google/google_sync_service.py`

```python
def switch_worksheet(self, ws_index: int):
    self.gsheet.set_active_worksheet(ws_index)
```

`Navigation_Bot/bots/google_sheets_manager.py`

```python
self.sheet = cache[index]
self.worksheet_index = index
```

## Где строится source_key

`Navigation_Bot/gui/main_window/navigation_gui.py`

```python
def _get_sheet_source_key(self) -> str:
    if not hasattr(self, "ctx") or not hasattr(self.ctx, "gsheet") or not getattr(self.ctx.gsheet, "sheet", None):
        return "default"

    index = getattr(self.ctx.gsheet, "worksheet_index", 0) or 0
    title = getattr(self.ctx.gsheet.sheet, "title", f"sheet_{index}") or f"sheet_{index}"
    return f"sheet_{index}_{title}"
```

Это текущая логическая связь между листом Google и записями в БД.

## Где source_key используется в слое БД/API

`Navigation_Bot/core/repositories/api_task_repository.py`

`set_source_key()` сохраняет активный источник:

```python
self.current_source_key = new_source_key
```

Чтение использует его:

```python
self.client.get(
    "/api/v1/tasks",
    params={
        "source_key": self.current_source_key,
        "strict_source_key": "true",
        ...
    },
)
```

Запись тоже использует его:

```python
self.client.post(
    "/api/v1/tasks",
    json={
        "row": row,
        "source": source,
        "source_key": self.current_source_key,
    },
)
```

Пакетная запись также передает `source_key`:

```python
self.client.post(
    "/api/v1/tasks/batch",
    json={
        "rows": rows,
        "source": source,
        "source_key": self.current_source_key,
    },
)
```

## Где загружаются строки активного листа

`Navigation_Bot/core/application/services/google/google_sync_service.py`

`load_current_sheet()` синхронизирует активный лист:

```python
rows = self.gsheet.load_data()
self.tasks_service.add_only_missing_rows_from_google(rows)
self.tasks_service.remove_completed_tasks(set(rows.keys()))
self.task_repository.reload()
```

`Navigation_Bot/bots/google_sheets_manager.py`

`load_data()` читает только активный лист:

```python
values_list = self.sheet.batch_get(["D3:H", "M3:M"], major_dimension="ROWS")
```

Он возвращает:

```python
{
    google_sheet_row: [D, E, F, G, H],
}
```

`Navigation_Bot/core/application/services/tasks_service.py`

```python
GoogleTaskMergeService.merge_rows_into_data(data, rows_map)
self.task_repository.save(source="google")
```

После этого `ApiTaskRepository` отправляет измененные строки в API с текущим `source_key`.

## Точечная перезапись строки из Google

Контекстное меню таблицы содержит действие:

```python
act_refresh = menu.addAction("🔄 Перезаписать из Google")
```

Оно обновляет существующую задачу по `google_sheet_row`, не создавая новую запись:

```text
TableContextMenuController._refresh_row()
    |
    | google_sheet_row(row)
    v
GoogleSyncService.refresh_row_by_google_sheet_row(google_sheet_row)
    |
    | читает D{row}:H{row} из активного листа Google
    v
GoogleRowMapper.build_row()
    |
    | строит patch: ТС, Телефон, ФИО, КА, Погрузка, Выгрузка, raw_load, raw_unload
    v
TasksService.apply_patch(real_idx, patch, source="google")
    |
    | сохраняет старые идентификаторы задачи
    | сбрасывает старые parsed-поля маршрута
    v
TaskRepository.save(source="google")
    |
    | API/PostgreSQL upsert существующей задачи
    v
task_repository.reload()
```

Ключевой инвариант: `google_sheet_row` используется как связь со строкой Google, а `trip_number` / `db_task_id` должны оставаться от старой задачи. Поэтому refresh должен перезаписывать существующую запись в БД, а не создавать новую.

При обновлении `Погрузка` / `Выгрузка` из Google старые разобранные поля:

```text
loads
unloads
processed
processed_unloads
```

удаляются перед пересборкой строки. Это нужно, потому что `TaskMapper` иначе отдавал бы приоритет старым `loads/unloads`, и после reload GUI снова показывал бы старую выгрузку. Свежий текст из Google парсится через `RouteInfoParser`, затем сохраняется в `route_points`.

При активном `source_key` lookup в PostgreSQL ищет существующую задачу по:

```text
google_sheet_row AND (google_worksheet_title = source_key OR google_worksheet_title IS NULL)
```

Точное совпадение `google_worksheet_title = source_key` имеет приоритет. `NULL` оставлен для совместимости со старыми задачами, созданными до разделения листов по `source_key`.

## Важная деталь запуска

`Navigation_Bot/gui/app/app_services.py`

`_build_data_layer()` сейчас выполняется раньше, чем `_build_google_and_services()`:

```python
c.task_repository = ApiTaskRepository(c.api_client, log=g.log)
c.task_repository.set_source_key(g._get_sheet_source_key())
```

В этот момент `gsheet` может еще не существовать, поэтому `_get_sheet_source_key()` может вернуть:

```text
default
```

Позже ключ источника исправляется, когда:

- пользователь нажимает вкладку Google;
- пользователь загружает данные из Google;
- контроллер настроек перестраивает или переключает вкладки.

## Текущая модель хранения

Текущая модель:

```text
список листов Google -> только runtime GUI/cache
активный лист -> source_key
задачи -> сохраняются в БД/API с source_key
```

Отсутствующая модель, если понадобится явная привязка листов к БД:

```text
worksheets table / registry:
    sheet_id
    worksheet_index
    worksheet_title
    source_key
    active/hidden metadata
    created_at/updated_at
```

Такой таблицы в текущем кодовом пути нет.
