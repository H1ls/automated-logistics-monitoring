# Google Sheets tabs to DB dependency

## Summary

Вкладки Google Sheets сейчас не сохраняются в БД как отдельный справочник.

Они живут во время работы приложения:

- в `GoogleSheetsManager._worksheets_cache`;
- в runtime-маппингах GUI: `gui._tabs_by_key`, `gui._tabs_order`, `gui._tab_buttons_by_key`.

Связь задач с БД выполняется через `source_key` активной вкладки. Для каждого активного листа строится ключ вида:

```text
sheet_{worksheet_index}_{worksheet_title}
```

Этот ключ передается в API при чтении и записи задач.

## Dependency Flow

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
    | creates tab dicts: {kind, key, title, ws_index}
    v
gui._tabs_by_key / gui._tabs_order / gui._tab_buttons_by_key
    |
    | user clicks Google tab
    v
SheetTabsController.on_tab_clicked()
    |
    | google_sync_service.switch_worksheet(ws_index)
    v
GoogleSheetsManager.set_active_worksheet()
    |
    | sets gsheet.sheet and gsheet.worksheet_index
    v
NavigationGUI._get_sheet_source_key()
    |
    | sheet_{index}_{title}
    v
ApiTaskRepository.set_source_key(source_key)
    |
    | GET/POST /api/v1/tasks with source_key
    v
DB tasks separated by source_key
```

## Where Tabs Are Loaded

`Navigation_Bot/bots/google_sheets_manager.py`

- `load_settings()` opens the spreadsheet and loads worksheets:

```python
self._worksheets_cache = spreadsheet.worksheets()
self.sheet = self._worksheets_cache[self.worksheet_index]
```

- `get_worksheets_list()` refreshes the worksheet cache and returns tab metadata:

```python
self._worksheets_cache = spreadsheet.worksheets()
return [{"title": ws.title, "index": ws.index} for ws in self._worksheets_cache]
```

Important: this is only runtime cache. It is not persisted as a DB table.

## Where GUI Stores Tabs

`Navigation_Bot/gui/controllers/sheet_tabs_controller.py`

`SheetTabsController.build()` calls:

```python
worksheets = gui.gsheet.get_worksheets_list()
```

Then converts each worksheet to a GUI tab:

```python
tabs.append({
    "kind": "gsheet",
    "key": f"gs:{title}",
    "title": title,
    "ws_index": idx,
})
```

And stores the tabs in GUI fields:

```python
gui._tabs_by_key = {t["key"]: t for t in tabs}
gui._tabs_order = [t["key"] for t in tabs]
gui._tab_buttons_by_key[key] = btn
```

These structures are also runtime-only.

## Where Active Worksheet Is Selected

`Navigation_Bot/gui/controllers/sheet_tabs_controller.py`

When the user clicks a Google tab:

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

## Where Source Key Is Built

`Navigation_Bot/gui/main_window/navigation_gui.py`

```python
def _get_sheet_source_key(self) -> str:
    if not hasattr(self, "ctx") or not hasattr(self.ctx, "gsheet") or not getattr(self.ctx.gsheet, "sheet", None):
        return "default"

    index = getattr(self.ctx.gsheet, "worksheet_index", 0) or 0
    title = getattr(self.ctx.gsheet.sheet, "title", f"sheet_{index}") or f"sheet_{index}"
    return f"sheet_{index}_{title}"
```

This is the current logical link between a Google worksheet and DB records.

## Where Source Key Is Used In DB/API Layer

`Navigation_Bot/core/repositories/api_task_repository.py`

`set_source_key()` stores the active source:

```python
self.current_source_key = new_source_key
```

Reads use it:

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

Writes use it:

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

Batch writes also use it:

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

## Where Rows From Active Sheet Are Loaded

`Navigation_Bot/core/application/services/google/google_sync_service.py`

`load_current_sheet()` handles active worksheet sync:

```python
rows = self.gsheet.load_data()
self.tasks_service.add_only_missing_rows_from_google(rows)
self.tasks_service.remove_completed_tasks(set(rows.keys()))
self.task_repository.reload()
```

`Navigation_Bot/bots/google_sheets_manager.py`

`load_data()` reads only the active worksheet:

```python
values_list = self.sheet.batch_get(["D3:H", "M3:M"], major_dimension="ROWS")
```

It returns:

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

Then `ApiTaskRepository` sends changed rows to API with the current `source_key`.

## Important Startup Detail

`Navigation_Bot/gui/app/app_services.py`

`_build_data_layer()` currently runs before `_build_google_and_services()`:

```python
c.task_repository = ApiTaskRepository(c.api_client, log=g.log)
c.task_repository.set_source_key(g._get_sheet_source_key())
```

At this point `gsheet` may not exist yet, so `_get_sheet_source_key()` can return:

```text
default
```

Later the source key is corrected when:

- user clicks a Google tab;
- user loads from Google;
- settings controller rebuilds/switches tabs.

## Current Storage Model

Current model:

```text
Google worksheet list -> runtime GUI/cache only
Active worksheet -> source_key
Tasks -> persisted in DB/API with source_key
```

Missing model, if we want explicit worksheet-to-DB binding:

```text
worksheets table / registry:
    sheet_id
    worksheet_index
    worksheet_title
    source_key
    active/hidden metadata
    created_at/updated_at
```

That table does not exist in the current code path.
