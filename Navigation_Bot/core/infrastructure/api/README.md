# Navigation Bot API

FastAPI-адаптер между desktop GUI и PostgreSQL. API отвечает за HTTP-контракт, аутентификацию, роли, транзакционный доступ к данным, аудит и пакетные операции.

## Место в архитектуре

```text
GUI
  -> NavigationApiClient
  -> ApiTaskRepository / ApiVehicleRepository / API history services
  -> FastAPI routes
  -> PostgreSQL repositories / PostgreSQL history services
  -> psycopg connection pool
  -> PostgreSQL
```

Состав пакета:

- `main.py` — фабрика FastAPI и lifecycle PostgreSQL pool;
- `routes.py` — `/api/v1` endpoint-ы и правила доступа;
- `schemas.py` — Pydantic-модели запросов;
- `dependencies.py` — соединение из pool, проверка ключа и ролей;
- `api_client.py` — синхронный HTTP-клиент GUI;
- `check_api.py` — вывод зарегистрированных маршрутов;
- `auth_smoke.py` — проверка матрицы ролей;
- `load_smoke.py` — функциональная и нагрузочная проверка tasks API.

PostgreSQL-реализации находятся в `Navigation_Bot.core.repositories`, история — в `Navigation_Bot.core.application.services.postgres_history_services`, схема и pool — в `Navigation_Bot.core.storage`.

## Запуск

Из корня проекта:

```powershell
$env:POSTGRES_DSN = "postgresql://pet_user:pet_password@localhost:5432/pet_project"
.\.venv\Scripts\uvicorn.exe Navigation_Bot.core.infrastructure.api.main:app `
  --host 127.0.0.1 `
  --port 8000
```

При старте API применяет `core/storage/postgres_schema.sql`, затем открывает pool. При остановке pool закрывается.

Доступные служебные страницы:

- Swagger: `http://127.0.0.1:8000/docs`;
- ReDoc: `http://127.0.0.1:8000/redoc`;
- префикс API: `http://127.0.0.1:8000/api/v1`.

`GET /api/v1/health` требует роль с правом чтения, кроме начального dev-admin режима.

## Настройки сервера

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `POSTGRES_DSN` | `postgresql://pet_user:pet_password@localhost:5432/pet_project` | Подключение к БД |
| `POSTGRES_POOL_MIN_SIZE` | `2` | Минимум подключений |
| `POSTGRES_POOL_MAX_SIZE` | `10` | Максимум подключений |
| `POSTGRES_POOL_TIMEOUT` | `10` | Ожидание подключения, секунд |
| `NAV_GUI_SESSION_HOURS` | `12` | Срок ключа, выданного `/auth/login`; ограничивается диапазоном 1–168 часов |
| `NAV_API_KEY` | — | Необязательный env-admin ключ |

Для 30–50 GUI-клиентов начните с `2/10/10` и увеличивайте `POSTGRES_POOL_MAX_SIZE` только по результатам замеров и с учётом лимита подключений PostgreSQL.

## Аутентификация

### Вход GUI

GUI отправляет логин и пароль:

```http
POST /api/v1/auth/login
Content-Type: application/json

{"username":"dispatcher1","password":"strong-password"}
```

API отзывает предыдущий ключ пользователя с именем `GUI session`, создаёт новый временный ключ и возвращает его в поле `api_key`. Последующие запросы используют:

```http
X-API-Key: nav_...
```

В БД хранится только hash ключа. Значение `nav_...` нельзя восстановить после выдачи.

### Первичная настройка

Если активных пользователей с паролем ещё нет, первый запрос `/auth/login` создаёт активного `admin` с переданными логином и паролем. Пароль должен пройти правила `PostgresUserRepository`.

Для API-инициализации также существует dev-admin режим: пока нет активного admin API-ключа и не задан `NAV_API_KEY`, запросы без `X-API-Key` получают временные права администратора. После появления admin-ключа этот режим автоматически выключается.

`NAV_API_KEY` на сервере действует как env-admin ключ. Это режим эксплуатации/восстановления, а не пользовательская GUI-сессия.

### Роли

| Роль | Чтение | Запись рабочих данных | Пользователи, ключи, audit log |
|---|---|---|---|
| `admin` | да | да | да |
| `dispatcher` | да | да | нет |
| `viewer` | да | нет | нет |

Проверить текущую сессию:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/me" `
  -Headers @{"X-API-Key"=$env:NAV_API_KEY}
```

Управление пользователями и постоянными ключами:

```text
GET  /api/v1/users
POST /api/v1/users
PUT  /api/v1/users/{user_id}
POST /api/v1/users/{user_id}/api-keys
POST /api/v1/api-keys/{key_id}/revoke
```

## Endpoint-ы

### Системные и административные

```text
POST /api/v1/auth/login
GET  /api/v1/me
GET  /api/v1/health
GET  /api/v1/audit-log
```

### Рейсы

```text
GET  /api/v1/tasks
POST /api/v1/tasks
POST /api/v1/tasks/batch
POST /api/v1/tasks/{row_identity}/complete
POST /api/v1/tasks/complete/batch
```

Неявная полная загрузка запрещена: `GET /tasks` без `limit`, `updated_since` или `full=true` возвращает `400`.

Постраничная загрузка:

```text
GET /api/v1/tasks?source_key=sheet-id&strict_source_key=true&limit=100&offset=0
```

Инкрементальная загрузка:

```text
GET /api/v1/tasks?source_key=sheet-id&strict_source_key=true&limit=100&updated_since=2026-06-18T10:00:00Z
```

Ответ содержит `count`, `total`, `items`, `limit`, `offset` и `next_offset`. Значение `next_offset: null` означает последнюю страницу. `full=true` оставлен для ручной диагностики, а не штатной нагрузки.

Изменение рейса защищено optimistic locking по `updated_at`; устаревшая версия получает `409 Conflict` с `detail.error = task_conflict`.

### История рейса

Для `notes`, `status-events`, `route-estimates` и `navigation` доступны чтение и одиночная запись:

```text
GET  /api/v1/tasks/{trip_number}/{resource}
POST /api/v1/tasks/{trip_number}/{resource}
```

Пакетная запись:

```text
POST /api/v1/tasks/{trip_number}/notes/batch
POST /api/v1/tasks/{trip_number}/status-events/batch
POST /api/v1/tasks/{trip_number}/route-estimates/batch
POST /api/v1/tasks/{trip_number}/navigation/batch
```

### Транспорт

```text
GET  /api/v1/vehicles
POST /api/v1/vehicles
GET  /api/v1/vehicles/{monitoring_id}/navigation
```

Точные тела запросов и ответы всегда доступны в Swagger.

## Audit log

Запись выполняется для изменений рейсов, транспорта, заметок, событий, навигации, расчётов маршрута, пользователей и API-ключей. Запись содержит пользователя, роль, тип и ID сущности, действие, изменённые поля, snapshots и время.

```text
GET /api/v1/audit-log?entity_type=tasks&entity_id=42&limit=100
```

Чтение доступно только `admin`. Batch-операции используют компактные audit-записи без полного snapshot каждой строки.

## Настройки клиента GUI

```powershell
$env:NAV_API_BASE_URL = "http://127.0.0.1:8000"
$env:NAV_API_TASK_PAGE_SIZE = "500"
$env:NAV_API_INCREMENTAL_REFRESH = "1"
.\.venv\Scripts\python.exe main.py
```

Первый reload загружает страницы полностью. При включённом incremental refresh следующие обновления запрашивают изменения по `updated_since`; завершённые, архивные и отменённые рейсы удаляются из локального active-списка. При ошибке GUI возвращается к полной постраничной загрузке.

Для отладки без формы входа можно задать `NAV_GUI_SKIP_LOGIN=1` и `NAV_API_KEY`, но обычный сценарий использует `/auth/login`.

## Проверки

Список зарегистрированных маршрутов:

```powershell
.\.venv\Scripts\python.exe -m Navigation_Bot.core.infrastructure.api.check_api
```

Проверка ролей:

```powershell
$env:NAV_ADMIN_API_KEY = "nav_admin..."
$env:NAV_DISPATCHER_API_KEY = "nav_dispatcher..."
$env:NAV_VIEWER_API_KEY = "nav_viewer..."

.\.venv\Scripts\python.exe -m Navigation_Bot.core.infrastructure.api.auth_smoke `
  --base-url http://127.0.0.1:8000
```

Ожидаемая матрица: viewer — только чтение; dispatcher — чтение/запись без admin endpoint-ов; admin — полный доступ.

Базовая нагрузочная проверка:

```powershell
.\.venv\Scripts\python.exe -m Navigation_Bot.core.infrastructure.api.load_smoke `
  --base-url http://127.0.0.1:8000 `
  --api-key $env:NAV_API_KEY `
  --clients 10 `
  --iterations 30 `
  --batch-size 3 `
  --reuse-rows
```

Регрессионный прогон для 30 клиентов:

```powershell
.\.venv\Scripts\python.exe -m Navigation_Bot.core.infrastructure.api.load_smoke `
  --base-url http://127.0.0.1:8000 `
  --api-key $env:NAV_API_KEY `
  --clients 30 `
  --iterations 50 `
  --batch-size 3 `
  --reuse-rows `
  --page-limit 100 `
  --max-get-p95-ms 500 `
  --max-batch-p95-ms 1000
```

Проверка incremental-контракта:

```powershell
.\.venv\Scripts\python.exe -m Navigation_Bot.core.infrastructure.api.load_smoke `
  --base-url http://127.0.0.1:8000 `
  --api-key $env:NAV_API_KEY `
  --incremental-check
```

Очистка созданных smoke-рейсов:

```powershell
.\.venv\Scripts\python.exe -m Navigation_Bot.core.infrastructure.api.load_smoke `
  --api-key $env:NAV_API_KEY `
  --clients 30 `
  --iterations 50 `
  --batch-size 3 `
  --cleanup-generated
```

`--complete`, `--cleanup-generated` и особенно `--purge-generated` изменяют данные. Используйте их только на тестовой БД или с явно выделенными smoke-рейсами.
